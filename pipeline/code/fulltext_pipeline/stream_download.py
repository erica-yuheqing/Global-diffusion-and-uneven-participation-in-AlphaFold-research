"""Bounded HTTP/body retries and validator-protected full-text checkpoints.

The caller owns the quota and manifest. Every HTTP send, including redirects,
gets one quota reservation and one audit entry; no hidden requests retry loop
is used here. A checkpoint contains a URL fingerprint, never credentials.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from .common import redact_sensitive_text, utc_now


RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)", re.I)
CHUNK_SIZE = 64 * 1024
MAX_REDIRECTS = 5


@dataclass
class TransferResult:
    completed: bool = False
    quota_exhausted: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)


class InvalidRange(ValueError):
    """Do not append these bytes; the next attempt must be a full GET."""


class FileTooLarge(ValueError):
    pass


def checkpoint_path(part: Path) -> Path:
    return part.with_name(part.name + ".json")


def clear_checkpoint(part: Path) -> None:
    checkpoint_path(part).unlink(missing_ok=True)


def strong_etag(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) >= 2
        and value.startswith('"')
        and value.endswith('"')
        and all(ord(char) == 0x21 or 0x23 <= ord(char) <= 0x7E or 0x80 <= ord(char) <= 0xFF
                for char in value[1:-1])
    )


def read_checkpoint(part: Path, fingerprint: str, max_bytes: int) -> dict[str, Any] | None:
    try:
        meta = checkpoint_path(part)
        if meta.stat().st_size > 16384:
            return None
        state = json.loads(meta.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return None
        total = state.get("total")
        size = part.stat().st_size
        if (
            state.get("version") == 1
            and state.get("url_sha256") == fingerprint
            and strong_etag(state.get("etag"))
            and type(total) is int
            and 0 < size < total <= max_bytes
        ):
            return {**state, "offset": size}
    except (OSError, ValueError):
        pass
    return None


def write_checkpoint(part: Path, fingerprint: str, etag: str, total: int) -> None:
    meta = checkpoint_path(part)
    staging = meta.with_name(meta.name + ".tmp")
    staging.write_text(
        json.dumps({"version": 1, "url_sha256": fingerprint, "etag": etag, "total": total}),
        encoding="utf-8",
    )
    staging.replace(meta)


def retry_delay(headers: Mapping[str, str], attempt: int) -> float | None:
    """Honor short Retry-After delays; defer long waits instead of retrying early."""
    value = headers.get("Retry-After")
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                delay = (when - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = float(2**attempt)
        if delay > 30:
            return None
        return max(0.0, delay)
    return float(min(2**attempt, 8))


def origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def fetch_to_file(
    *,
    session: requests.Session,
    url: str,
    source_url: str,
    part: Path,
    max_bytes: int,
    max_attempts: int = 3,
    resume: bool = True,
    headers: Mapping[str, str] | None = None,
    reserve_request: Callable[[], bool] | None = None,
    attempt_log: list[dict[str, Any]] | None = None,
) -> TransferResult:
    """Fetch one candidate; leave a safe partial for retries or later CLI runs.

    ``max_attempts`` counts transfer rounds (initial GET plus retries/Range GETs).
    Redirects are bounded separately, but still consume the shared HTTP quota.
    Resume requires identity encoding, a strong ETag, advertised byte ranges,
    and a known length. Otherwise a retry starts a fresh, bounded download.
    """
    if max_attempts < 1 or max_bytes < 1:
        raise ValueError("max_attempts and max_bytes must be positive")
    # Share the audit list with the caller so even a local cleanup failure after
    # a paid send cannot make that send disappear from the manifest result.
    result = TransferResult(attempts=attempt_log if attempt_log is not None else [])
    fingerprint = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    part.parent.mkdir(parents=True, exist_ok=True)

    for round_index in range(max_attempts):
        state = read_checkpoint(part, fingerprint, max_bytes) if resume else None
        offset = state["offset"] if state else 0
        request_headers = dict(headers or {})
        request_headers["Accept-Encoding"] = "identity"
        if state:
            request_headers.update({"Range": f"bytes={offset}-", "If-Range": state["etag"]})
        response: requests.Response | None = None
        entry: dict[str, Any] | None = None
        delay: float | None = float(min(2**round_index, 8))
        received = 0
        try:
            current_url = url
            visited = {current_url}
            for redirect_index in range(MAX_REDIRECTS + 1):
                if reserve_request is not None and not reserve_request():
                    result.attempts.append({
                        "attempted_at": utc_now(), "outcome": "skipped_paid_quota",
                        "error": "HTTP request cap reached; retained any partial file",
                    })
                    result.quota_exhausted = True
                    return result
                entry = {"attempted_at": utc_now(), "outcome": "error", "bytes": 0}
                result.attempts.append(entry)
                # Session adapters must have automatic retries disabled (the CLI
                # uses Requests' default of zero). Redirects are counted here too.
                response = session.get(
                    current_url, headers=request_headers, stream=True,
                    allow_redirects=False, timeout=(20.0, 300.0),
                )
                entry.update({
                    "http_status": response.status_code,
                    "content_type": response.headers.get("Content-Type", ""),
                })
                if response.status_code not in REDIRECT_STATUSES:
                    break
                location = response.headers.get("Location")
                target = urljoin(current_url, location) if location else ""
                parts = urlsplit(target)
                if (
                    not parts.hostname or parts.scheme not in {"http", "https"}
                    or parts.username or parts.password
                    or (urlsplit(current_url).scheme == "https" and parts.scheme != "https")
                    or target in visited or redirect_index == MAX_REDIRECTS
                ):
                    entry.update(outcome="http_error", error="Invalid, insecure, or excessive redirect")
                    return result
                if origin(target) != origin(current_url):
                    request_headers = {
                        key: value for key, value in request_headers.items()
                        if key.lower() not in {"x-els-apikey", "authorization", "cookie"}
                    }
                entry["outcome"] = "http_redirect"
                response.close()
                response = None
                visited.add(target)
                current_url = target

            assert response is not None and entry is not None
            status = response.status_code
            if status == 416 and offset:
                # Do not equate 416 with a complete file. Restart and verify it.
                clear_checkpoint(part)
                entry.update(outcome="range_restart", error="Range rejected (416); next attempt is a full GET")
            elif status not in {200, 206}:
                entry.update(outcome="http_error", error=f"HTTP {status}")
                if status not in RETRY_STATUSES:
                    return result
                delay = retry_delay(response.headers, round_index)
                if delay is None:
                    entry["error"] += "; Retry-After exceeds 30 seconds; retry in a later run"
                    return result
            else:
                encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
                identity = encoding in {"", "identity"}
                length_header = response.headers.get("Content-Length")
                length = int(length_header) if length_header is not None else None
                if length is not None and length < 0:
                    raise ValueError("Negative Content-Length")
                if length is not None and length > max_bytes:
                    raise FileTooLarge("Content-Length exceeds configured size limit")
                etag = response.headers.get("ETag", "")
                if status == 206:
                    match = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", "").strip())
                    if not state or not identity or not match or etag != state["etag"]:
                        raise InvalidRange("Missing/mismatched range validator, encoding, or Content-Range")
                    start, end, total = map(int, match.groups())
                    expected = end - start + 1
                    if (
                        start != offset or end < start or end >= total
                        or total != state["total"]
                        or (length is not None and length != expected)
                    ):
                        raise InvalidRange("Content-Range does not match the stored prefix/length")
                    if total > max_bytes:
                        raise FileTooLarge("Content-Range total exceeds configured size limit")
                    mode = "ab"
                else:
                    # A server may ignore Range or If-Range may detect a newer
                    # version. A 200 must replace the prefix, never append to it.
                    offset = 0
                    total = length if identity else None
                    expected = total
                    mode = "wb"

                with part.open(mode) as handle:
                    if mode == "wb":
                        clear_checkpoint(part)
                        if (
                            resume and identity and strong_etag(etag) and total
                            and response.headers.get("Accept-Ranges", "").strip().lower() == "bytes"
                        ):
                            write_checkpoint(part, fingerprint, etag, total)
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        if offset + received + len(chunk) > max_bytes:
                            raise FileTooLarge("Downloaded body exceeds configured size limit")
                        handle.write(chunk)
                        received += len(chunk)
                        entry["bytes"] = received

                if expected is not None and received != expected:
                    raise requests.ConnectionError(
                        f"Incomplete body: received {received} bytes, expected {expected}"
                    )
                if status == 206 and offset + received < total:
                    entry.update(outcome="partial", error="Server supplied only part of the requested remainder")
                    delay = 0
                else:
                    clear_checkpoint(part)
                    entry["outcome"] = "success"
                    result.completed = True
                    return result
        except InvalidRange as exc:
            clear_checkpoint(part)
            assert entry is not None
            entry.update(outcome="invalid_range", error=str(exc))
        except FileTooLarge as exc:
            clear_checkpoint(part)
            part.unlink(missing_ok=True)
            assert entry is not None
            entry.update(outcome="too_large", error=str(exc))
            return result
        except requests.RequestException as exc:
            assert entry is not None
            entry.update(outcome="error", error=redact_sensitive_text(exc))
            # The with/finally blocks flush and close the body. A valid prefix
            # and checkpoint survive both exhausted retries and quota deferral.
        except (OSError, ValueError) as exc:
            if entry is None:
                raise
            entry.update(outcome="error", error=redact_sensitive_text(exc))
            return result  # Disk/configuration failures are not network retries.
        finally:
            if response is not None:
                response.close()
        if round_index + 1 < max_attempts and delay:
            time.sleep(delay)
    return result
