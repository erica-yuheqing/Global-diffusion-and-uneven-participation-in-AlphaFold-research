#!/usr/bin/env python3
"""Fetch full text using the structured-first source cascade.

Priority:
1. Europe PMC JATS XML
2. Europe PMC free-to-read PDF (including non-OA only when explicitly enabled)
3. OpenAlex GROBID/TEI XML
4. Unpaywall OA PDF
5. OpenAlex best-OA PDF URL
6. Additional verified OA candidates (OpenAIRE/CORE/Semantic Scholar/Crossref)
7. OpenAlex cached PDF

OpenAlex content downloads are treated as paid requests and are disabled unless
both --allow-openalex-content and --max-openalex-content are supplied.
"""

from __future__ import annotations

import argparse
import gzip
import os
import sqlite3
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

from fulltext_pipeline.common import (
    DEFAULT_DB_PATH,
    DEFAULT_FULLTEXT_ROOT,
    add_query_parameter,
    batched,
    connect_db,
    is_elsevier_article_api_url,
    make_user_agent,
    nested_work_path,
    redact_sensitive_text,
    semantic_scholar_download_target,
    sha256_file,
    utc_now,
)
from fulltext_pipeline.stream_download import fetch_to_file
from fulltext_pipeline.oa_recovery_support import (
    BLOCKED_OA_STATUSES, load_cohort, pmc_xml_status, readonly_snapshot,
    status_after_attempt, validate_cohort_in_manifest,
)


@dataclass(frozen=True)
class DownloadCandidate:
    source: str
    url: str
    suffix: str
    expected_format: str
    access_class: str
    license: str | None = None
    uses_openalex_content: bool = False
    oa_provider: str | None = None
    oa_candidate_url: str | None = None
    requires_elsevier_api: bool = False


class OpenAlexContentQuota:
    def __init__(self, allowed: bool, maximum: int) -> None:
        self.allowed = allowed
        self.maximum = max(0, maximum)
        self.used = 0
        self.lock = threading.Lock()

    def reserve(self) -> bool:
        with self.lock:
            if not self.allowed or self.used >= self.maximum:
                return False
            self.used += 1
            return True


class RequestRateLimiter:
    """Thread-safe minimum interval between provider HTTP sends."""

    def __init__(self, requests_per_second: float) -> None:
        self.interval = 1.0 / requests_per_second
        self.next_send = 0.0
        self.lock = threading.Lock()

    def reserve(self) -> bool:
        with self.lock:
            delay = self.next_send - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.next_send = time.monotonic() + self.interval
        return True


_thread_local = threading.local()


def thread_session(contact_email: str | None) -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        # Only stream_download controls retries, so every send is quota-counted.
        session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))
        session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
        session.headers.update(
            {
                "User-Agent": make_user_agent(contact_email),
                "Accept": "application/xml,text/xml,application/pdf,application/octet-stream;q=0.8",
            }
        )
        _thread_local.session = session
    return session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--root", type=Path, default=DEFAULT_FULLTEXT_ROOT)
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--limit", type=int, default=20, help="Default safety limit: 20")
    limit_group.add_argument("--all", action="store_true", help="Process all eligible rows")
    limit_group.add_argument(
        "--work-id",
        help="Process one exact OpenAlex work ID (use with --force to replace a success)",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--access-policy",
        choices=["open-access", "free-to-read"],
        default="open-access",
        help=(
            "open-access keeps the prior OA-only policy; free-to-read also permits "
            "official direct files labelled free but non-OA, with provenance retained"
        ),
    )
    parser.add_argument("--cohort-file", type=Path, help="Restrict selection to an immutable OA pilot JSON lock")
    parser.add_argument("--retry-blocked-oa", action="store_true",
                        help="Explicitly retry quarantined OA URLs (403/404/410/invalid payload); requires --oa-recovery-only")
    parser.add_argument("--priority-max", type=int, default=100)
    parser.add_argument("--max-file-mb", type=int, default=100)
    parser.add_argument(
        "--download-attempts", type=int, default=3,
        help="Transfer rounds per source, including the first GET (1-10; default: 3)",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Ignore partial checkpoints and restart interrupted files from byte zero",
    )
    retry_group = parser.add_mutually_exclusive_group()
    retry_group.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed, unavailable, or deferred rows; successful rows remain untouched",
    )
    retry_group.add_argument(
        "--force",
        action="store_true",
        help="Re-download every selected row, including successful rows",
    )
    parser.add_argument(
        "--downloadable-only",
        action="store_true",
        help=(
            "Select only rows with at least one currently usable source URL; "
            "paid OpenAlex URLs count only with --allow-openalex-content"
        ),
    )
    parser.add_argument(
        "--openalex-content-only",
        action="store_true",
        help=(
            "Select and attempt only paid OpenAlex TEI/cached-PDF sources, skipping "
            "free URLs that already failed; requires --allow-openalex-content"
        ),
    )
    parser.add_argument(
        "--oa-recovery-only",
        "--legal-recovery-only",
        dest="oa_recovery_only",
        action="store_true",
        help=(
            "Select and attempt only direct OA candidates discovered by "
            "09_enrich_oa_recovery.py"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Show source choices without downloading")
    parser.add_argument(
        "--allow-openalex-content",
        action="store_true",
        help="Allow paid OpenAlex TEI/PDF content requests",
    )
    parser.add_argument(
        "--max-openalex-content",
        type=int,
        default=0,
        help="Per-run HTTP request cap for paid sources, including retries, Range GETs and redirects",
    )
    parser.add_argument(
        "--openalex-api-key",
        default=os.getenv("OPENALEX_API_KEY"),
        help="Defaults to OPENALEX_API_KEY",
    )
    parser.add_argument(
        "--elsevier-api-key",
        default=os.getenv("ELSEVIER_API_KEY"),
        help=(
            "Defaults to ELSEVIER_API_KEY; required only for Crossref candidates "
            "hosted on api.elsevier.com"
        ),
    )
    parser.add_argument(
        "--ncbi-api-key",
        default=os.getenv("NCBI_API_KEY"),
        help="Optional NCBI key for E-Utilities; defaults to NCBI_API_KEY",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("CONTACT_EMAIL") or os.getenv("UNPAYWALL_EMAIL"),
        help="Contact email used in the User-Agent",
    )
    return parser.parse_args()


def candidate_sources(row: dict[str, Any]) -> list[DownloadCandidate]:
    candidates: list[DownloadCandidate] = []
    if row.get("epmc_xml_url"):
        candidates.append(
            DownloadCandidate(
                "epmc_jats", row["epmc_xml_url"], ".jats.xml", "xml",
                "open_access", row.get("epmc_license"),
            )
        )
    if row.get("epmc_efetch_xml_url"):
        access_class = (
            "open_access" if row.get("epmc_is_oa") else "free_to_read_non_oa"
        )
        candidates.append(
            DownloadCandidate(
                "pmc_efetch_jats", row["epmc_efetch_xml_url"], ".jats.xml", "xml",
                access_class, row.get("epmc_license"),
            )
        )
    if row.get("epmc_pdf_url"):
        access_class = (
            "open_access" if row.get("epmc_is_oa") else "free_to_read_non_oa"
        )
        candidates.append(
            DownloadCandidate(
                "epmc_free_pdf", row["epmc_pdf_url"], ".pdf", "pdf",
                access_class, row.get("epmc_license"),
            )
        )
    if row.get("openalex_tei_url"):
        candidates.append(
            DownloadCandidate(
                "openalex_tei",
                row["openalex_tei_url"],
                ".tei.xml",
                "xml",
                "paid_api",
                row.get("best_oa_license"),
                uses_openalex_content=True,
            )
        )
    if row.get("unpaywall_pdf_url"):
        candidates.append(
            DownloadCandidate(
                "unpaywall_pdf", row["unpaywall_pdf_url"], ".pdf", "pdf",
                "open_access", row.get("unpaywall_license"),
            )
        )
    if row.get("best_oa_pdf_url"):
        candidates.append(
            DownloadCandidate(
                "openalex_oa_pdf", row["best_oa_pdf_url"], ".pdf", "pdf",
                "open_access", row.get("best_oa_license"),
            )
        )
    for item in row.get("_oa_recovery_candidates") or []:
        allowed_statuses = {"available", "downloaded"}
        if row.get("_retry_blocked_oa"):
            allowed_statuses.update(BLOCKED_OA_STATUSES)
        if item.get("status", "available") not in allowed_statuses:
            continue
        retrieval_url = item["url"]
        expected_format = item["expected_format"]
        source = f"{item['provider']}_oa"
        if item["provider"] == "semantic_scholar":
            retrieval_url, expected_format, url_class = semantic_scholar_download_target(
                item["url"]
            )
            if not retrieval_url or not expected_format:
                continue
            if url_class == "pmc_jats":
                if pmc_xml_status(row, retrieval_url, item.get("access_evidence")) != "available":
                    continue
                source = "semantic_scholar_pmc_jats"
        suffix = ".oa.xml" if expected_format == "xml" else ".pdf"
        candidates.append(
            DownloadCandidate(
                source,
                retrieval_url,
                suffix,
                expected_format,
                "open_access",
                item.get("license"),
                oa_provider=item["provider"],
                oa_candidate_url=item["url"],
                requires_elsevier_api=is_elsevier_article_api_url(retrieval_url),
            )
        )
    if row.get("openalex_pdf_url"):
        candidates.append(
            DownloadCandidate(
                "openalex_pdf",
                row["openalex_pdf_url"],
                ".pdf",
                "pdf",
                "paid_api",
                row.get("best_oa_license"),
                uses_openalex_content=True,
            )
        )

    deduplicated: list[DownloadCandidate] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        normalized_url = candidate.url.strip()
        if normalized_url and normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            deduplicated.append(candidate)
    return deduplicated


def active_candidates(
    row: dict[str, Any],
    *,
    openalex_content_only: bool,
    oa_recovery_only: bool,
    elsevier_api_key: str | None,
    access_policy: str = "open-access",
) -> list[DownloadCandidate]:
    candidates = candidate_sources(row)
    if openalex_content_only:
        return [candidate for candidate in candidates if candidate.uses_openalex_content]
    if oa_recovery_only:
        candidates = [candidate for candidate in candidates if candidate.oa_provider]
    if access_policy == "open-access":
        candidates = [
            candidate for candidate in candidates
            if candidate.access_class != "free_to_read_non_oa"
        ]
    return [
        candidate
        for candidate in candidates
        if not candidate.requires_elsevier_api or elsevier_api_key
    ]


def valid_payload(path: Path, expected_format: str) -> tuple[bool, str | None]:
    with path.open("rb") as handle:
        head = handle.read(8192)
    stripped = head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
    if expected_format == "pdf":
        if not stripped.startswith(b"%PDF-"):
            return False, "response is not a PDF"
    elif expected_format == "xml":
        lower = stripped[:2048].lower()
        if not stripped.startswith(b"<"):
            return False, "response is not XML"
        if b"<html" in lower or b"<!doctype html" in lower:
            return False, "received HTML instead of XML"
    return True, None


def unpack_gzip_payload(path: Path, max_bytes: int) -> tuple[bool, str | None]:
    """Expand a gzip-wrapped response in place, with a decompressed-size limit."""
    with path.open("rb") as handle:
        gzip_magic = handle.read(2) == b"\x1f\x8b"
    if not gzip_magic:
        return True, None

    unpacked = path.with_suffix(path.suffix + ".unpacked")
    written = 0
    try:
        with gzip.open(path, "rb") as source, unpacked.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"decompressed payload exceeded {max_bytes} bytes")
                destination.write(chunk)
        unpacked.replace(path)
        return True, None
    except (OSError, EOFError, ValueError) as exc:
        unpacked.unlink(missing_ok=True)
        return False, f"could not unpack gzip payload: {exc}"


def payload_signature(path: Path) -> str:
    """Return a short non-secret byte signature for failed-format diagnostics."""
    with path.open("rb") as handle:
        return handle.read(16).hex()


def download_one(
    row: dict[str, Any],
    *,
    root: Path,
    quota: OpenAlexContentQuota,
    api_key: str | None,
    contact_email: str | None,
    max_bytes: int,
    openalex_content_only: bool,
    oa_recovery_only: bool,
    elsevier_api_key: str | None,
    access_policy: str = "open-access",
    ncbi_api_key: str | None = None,
    ncbi_rate_limiter: RequestRateLimiter | None = None,
    download_attempts: int = 3,
    resume: bool = True,
) -> dict[str, Any]:
    work_id = row["work_id"]
    attempts: list[dict[str, Any]] = []
    deferred_paid_source = False
    candidates = active_candidates(
        row,
        openalex_content_only=openalex_content_only,
        oa_recovery_only=oa_recovery_only,
        elsevier_api_key=elsevier_api_key,
        access_policy=access_policy,
    )
    for candidate in candidates:
        if candidate.uses_openalex_content:
            if not api_key:
                deferred_paid_source = True
                attempts.append(
                    {
                        "source": candidate.source,
                        "url": candidate.url,
                        "outcome": "skipped_no_api_key",
                        "attempted_at": utc_now(),
                        "access_class": candidate.access_class,
                        "license": candidate.license,
                        "oa_provider": candidate.oa_provider,
                        "oa_candidate_url": candidate.oa_candidate_url,
                    }
                )
                continue
        url = candidate.url
        if candidate.uses_openalex_content:
            url = add_query_parameter(url, "api_key", api_key)
        if candidate.source == "pmc_efetch_jats":
            url = add_query_parameter(url, "tool", "alphafold-research")
            if contact_email:
                url = add_query_parameter(url, "email", contact_email)
            if ncbi_api_key:
                url = add_query_parameter(url, "api_key", ncbi_api_key)
        request_headers = (
            {"X-ELS-APIKey": elsevier_api_key}
            if candidate.requires_elsevier_api and elsevier_api_key
            else None
        )
        destination = nested_work_path(root, candidate.source, work_id, candidate.suffix)
        temporary = destination.with_suffix(destination.suffix + ".part")
        candidate_attempts: list[dict[str, Any]] = []
        try:
            transfer = fetch_to_file(
                session=thread_session(contact_email),
                url=url,
                source_url=candidate.url,
                part=temporary,
                max_bytes=max_bytes,
                max_attempts=download_attempts,
                resume=resume,
                headers=request_headers,
                reserve_request=(
                    quota.reserve
                    if candidate.uses_openalex_content
                    else ncbi_rate_limiter.reserve
                    if candidate.source == "pmc_efetch_jats" and ncbi_rate_limiter
                    else None
                ),
                attempt_log=candidate_attempts,
            )
            deferred_paid_source |= transfer.quota_exhausted
            if not transfer.completed:
                continue
            unpacked, unpack_error = unpack_gzip_payload(temporary, max_bytes)
            if not unpacked:
                signature = payload_signature(temporary)
                temporary.unlink(missing_ok=True)
                candidate_attempts[-1].update(
                    outcome="invalid_payload", error=f"{unpack_error}; first_bytes={signature}",
                )
                continue
            valid, validation_error = valid_payload(temporary, candidate.expected_format)
            if not valid:
                signature = payload_signature(temporary)
                temporary.unlink(missing_ok=True)
                candidate_attempts[-1].update(
                    outcome="invalid_payload", error=f"{validation_error}; first_bytes={signature}",
                )
                continue
            stored_bytes = temporary.stat().st_size
            digest = sha256_file(temporary)
            temporary.replace(destination)
            return {
                "work_id": work_id,
                "status": "success",
                "source": candidate.source,
                "format": candidate.expected_format,
                "source_url": candidate.url,
                "access_class": candidate.access_class,
                "license": candidate.license,
                "local_path": str(destination.resolve()),
                "sha256": digest,
                "bytes": stored_bytes,
                "fetched_at": utc_now(),
                "attempts": attempts,
            }
        except (requests.RequestException, OSError, ValueError) as exc:
            if candidate_attempts:
                candidate_attempts[-1].update(outcome="error", error=redact_sensitive_text(exc))
            else:
                candidate_attempts.append({
                    "outcome": "skipped_local_error", "attempted_at": utc_now(),
                    "error": redact_sensitive_text(exc),
                })
        finally:
            for attempt in candidate_attempts:
                attempt.update(
                    source=candidate.source, url=candidate.url,
                    access_class=candidate.access_class, license=candidate.license,
                    oa_provider=candidate.oa_provider, oa_candidate_url=candidate.oa_candidate_url,
                )
            attempts.extend(candidate_attempts)
    if deferred_paid_source:
        status = "deferred_paid_source"
        error = "OpenAlex content exists but API key or paid-file quota was unavailable"
    elif candidates:
        status = "failed"
        error = "All available source candidates failed"
    elif any(
        candidate.access_class == "free_to_read_non_oa"
        for candidate in candidate_sources(row)
    ):
        status = "deferred_non_oa_source"
        error = "Official free-to-read non-OA file exists; use --access-policy free-to-read"
    else:
        status = "unavailable"
        error = "No permitted structured XML or direct file URL in manifest"
    return {
        "work_id": work_id,
        "status": status,
        "error": error,
        "fetched_at": utc_now(),
        "attempts": attempts,
    }


def select_rows(
    connection: sqlite3.Connection,
    *,
    limit: int | None,
    work_id: str | None,
    force: bool,
    retry_failed: bool,
    priority_max: int,
    downloadable_only: bool,
    allow_openalex_content: bool,
    openalex_content_only: bool,
    oa_recovery_only: bool,
    elsevier_api_key: str | None,
    access_policy: str = "open-access",
    cohort_ids: list[str] | None = None,
    retry_blocked_oa: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["in_current_corpus=1", "priority <= ?"]
    params: list[Any] = [priority_max]
    if cohort_ids is not None:
        validate_cohort_in_manifest(connection, cohort_ids)
        clauses.append("work_id IN (" + ",".join("?" for _ in cohort_ids) + ")")
        params.extend(cohort_ids)
    oa_statuses = ("available", "downloaded", *BLOCKED_OA_STATUSES) if retry_blocked_oa else ("available", "downloaded")
    # These statuses are fixed code constants, never user-supplied SQL.
    oa_status_sql = ",".join(f"'{status}'" for status in oa_statuses)
    if work_id:
        clauses.append("work_id = ?")
        params.append(work_id)
    if force:
        pass
    elif retry_failed:
        clauses.append("fetch_status <> 'success'")
    else:
        clauses.append("fetch_status = 'pending'")
    if downloadable_only:
        source_columns = [
            "epmc_xml_url", "epmc_efetch_xml_url", "unpaywall_pdf_url", "best_oa_pdf_url"
        ]
        if access_policy == "free-to-read":
            source_columns.append("epmc_pdf_url")
        if allow_openalex_content:
            source_columns.extend(["openalex_tei_url", "openalex_pdf_url"])
        clauses.append(
            "("
            + " OR ".join(
                f"NULLIF(TRIM({column}), '') IS NOT NULL" for column in source_columns
            )
            + " OR EXISTS ("
            "SELECT 1 FROM oa_recovery_candidates AS oa_downloadable "
            "WHERE oa_downloadable.work_id=works.work_id "
            "AND oa_downloadable.status='available' "
            + (
                ""
                if elsevier_api_key
                else "AND lower(oa_downloadable.url) NOT LIKE "
                "'https://api.elsevier.com/content/article/%' "
            )
            + ")"
            + ")"
        )
    if openalex_content_only:
        clauses.append(
            "(NULLIF(TRIM(openalex_tei_url), '') IS NOT NULL "
            "OR NULLIF(TRIM(openalex_pdf_url), '') IS NOT NULL)"
        )
    if oa_recovery_only:
        clauses.append(
            "EXISTS (SELECT 1 FROM oa_recovery_candidates AS oa_selected "
            "WHERE oa_selected.work_id=works.work_id "
            f"AND oa_selected.status IN ({oa_status_sql}) "
            + (
                ""
                if elsevier_api_key
                else "AND lower(oa_selected.url) NOT LIKE "
                "'https://api.elsevier.com/content/article/%' "
            )
            + ")"
        )
    sql = "SELECT * FROM works WHERE " + " AND ".join(clauses)
    if openalex_content_only:
        sql += """
            ORDER BY
              (
                SELECT COUNT(*) FROM fetch_attempts AS paid_attempt
                WHERE paid_attempt.work_id = works.work_id
                  AND paid_attempt.source IN ('openalex_tei', 'openalex_pdf')
                  AND paid_attempt.outcome NOT LIKE 'skipped_%'
              ),
              COALESCE(fetched_at, ''), priority, work_id
        """
    else:
        sql += " ORDER BY priority, work_id"
    postfilter = oa_recovery_only or downloadable_only
    if limit is not None and not postfilter:
        sql += " LIMIT ?"
        params.append(limit)
    rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
    by_work_id = {row["work_id"]: row for row in rows}
    for row in rows:
        row["_oa_recovery_candidates"] = []
        row["_retry_blocked_oa"] = retry_blocked_oa
    work_ids = list(by_work_id)
    for batch in batched(work_ids, 500):
        placeholders = ",".join("?" for _ in batch)
        candidate_rows = connection.execute(
            f"""
            SELECT work_id, provider, url, expected_format, license, status, access_evidence
            FROM oa_recovery_candidates
            WHERE work_id IN ({placeholders})
              AND status IN ({oa_status_sql})
            ORDER BY
              CASE expected_format WHEN 'xml' THEN 0 ELSE 1 END,
              CASE provider
                WHEN 'openaire' THEN 1
                WHEN 'core' THEN 2
                WHEN 'semantic_scholar' THEN 3
                WHEN 'crossref' THEN 4
                ELSE 9 END,
              candidate_id
            """,  # noqa: S608 -- placeholders are generated, not user data
            list(batch),
        ).fetchall()
        for candidate_row in candidate_rows:
            by_work_id[candidate_row["work_id"]]["_oa_recovery_candidates"].append(
                dict(candidate_row)
            )
    if postfilter:
        rows = [row for row in rows if any(
            not item.uses_openalex_content or allow_openalex_content
            for item in active_candidates(row,openalex_content_only=openalex_content_only,
                                          oa_recovery_only=oa_recovery_only,
                                          elsevier_api_key=elsevier_api_key,
                                          access_policy=access_policy)
        )]
        if limit is not None:
            rows = rows[:limit]
    return rows


def record_result(connection: sqlite3.Connection, result: dict[str, Any]) -> None:
    for attempt in result["attempts"]:
        connection.execute(
            """
            INSERT INTO fetch_attempts(
                work_id, source, url, attempted_at, outcome, http_status,
                content_type, bytes, access_class, license, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["work_id"],
                attempt["source"],
                attempt.get("url"),
                attempt["attempted_at"],
                attempt["outcome"],
                attempt.get("http_status"),
                attempt.get("content_type"),
                attempt.get("bytes"),
                attempt.get("access_class"),
                attempt.get("license"),
                attempt.get("error"),
            ),
        )
        if attempt.get("oa_provider"):
            candidate_key = (result["work_id"],attempt["oa_provider"],
                             attempt.get("oa_candidate_url") or attempt.get("url"))
            prior = connection.execute(
                "SELECT status FROM oa_recovery_candidates WHERE work_id=? AND provider=? AND url=?",
                candidate_key,
            ).fetchone()
            new_status = status_after_attempt(prior["status"] if prior else "available",
                                              attempt["outcome"],attempt.get("http_status"))
            connection.execute(
                """
                UPDATE oa_recovery_candidates SET
                    last_attempted_at=?,
                    last_outcome=?,
                    attempt_count=attempt_count+1,
                    status=?
                WHERE work_id=? AND provider=? AND url=?
                """,
                (
                    attempt["attempted_at"],
                    attempt["outcome"],
                    new_status,
                    *candidate_key,
                ),
            )
    connection.execute(
        """
        UPDATE works SET
            fetch_status=?, fetched_source=?, fetched_format=?, local_path=?,
            fetched_source_url=?, fetched_access_class=?, fetched_license=?,
            content_sha256=?, content_bytes=?, fetched_at=?, fetch_error=?,
            parse_status=CASE WHEN ?='success' THEN 'pending' ELSE parse_status END,
            updated_at=?
        WHERE work_id=?
        """,
        (
            result["status"],
            result.get("source"),
            result.get("format"),
            result.get("local_path"),
            result.get("source_url"),
            result.get("access_class"),
            result.get("license"),
            result.get("sha256"),
            result.get("bytes"),
            result.get("fetched_at"),
            result.get("error"),
            result["status"],
            utc_now(),
            result["work_id"],
        ),
    )


def print_dry_run(
    rows: list[dict[str, Any]],
    allow_paid: bool,
    paid_maximum: int,
    openalex_content_only: bool,
    oa_recovery_only: bool,
    elsevier_api_key: str | None,
    access_policy: str = "open-access",
    ncbi_api_key: str | None = None,
    download_attempts: int = 3,
    resume: bool = True,
) -> None:
    print(f"Eligible rows: {len(rows):,}")
    print(f"OpenAlex paid content allowed: {allow_paid}; hard HTTP request cap: {paid_maximum:,}")
    print(f"Transfer rounds per source: {download_attempts}; checkpoint resume: {resume}")
    print(f"Access policy: {access_policy}")
    if access_policy == "free-to-read":
        print("Non-OA rule: official direct free files only; no paywall or access-control bypass")
    print(f"Elsevier API key configured: {bool(elsevier_api_key)}")
    print(f"NCBI API key configured: {bool(ncbi_api_key)}")
    availability: Counter[str] = Counter()
    first_choice: Counter[str] = Counter()
    paid_first_choice = 0
    paid_candidate_slots = 0
    no_source = 0
    for row in rows:
        candidates = active_candidates(
            row,
            openalex_content_only=openalex_content_only,
            oa_recovery_only=oa_recovery_only,
            elsevier_api_key=elsevier_api_key,
            access_policy=access_policy,
        )
        if not candidates:
            no_source += 1
            continue
        first_choice[candidates[0].source] += 1
        paid_first_choice += int(candidates[0].uses_openalex_content)
        for candidate in candidates:
            availability[candidate.source] += 1
            paid_candidate_slots += int(candidate.uses_openalex_content)
    print("Candidate availability:", dict(availability))
    print("First-choice sources:", dict(first_choice))
    print(f"Rows with no candidate source: {no_source:,}")
    print(f"Paid first-choice attempts if all succeed: {paid_first_choice:,}")
    print(f"Paid candidate slots including fallbacks: {paid_candidate_slots:,}")
    print("Candidate counts exclude retries/redirects; every paid-source HTTP send consumes the cap.")
    for row in rows[:20]:
        sources = [
            candidate.source
            for candidate in active_candidates(
                row,
                openalex_content_only=openalex_content_only,
                oa_recovery_only=oa_recovery_only,
                elsevier_api_key=elsevier_api_key,
                access_policy=access_policy,
            )
        ]
        print(f"{row['work_id']} priority={row['priority']} sources={','.join(sources) or 'none'}")
    if len(rows) > 20:
        print(f"... {len(rows) - 20:,} more rows")


def main() -> None:
    args = parse_args()
    if not 1 <= args.download_attempts <= 10:
        raise SystemExit("--download-attempts must be between 1 and 10 (including the first attempt)")
    if args.max_file_mb < 1 or args.workers < 1 or args.limit < 1:
        raise SystemExit("--max-file-mb, --workers and --limit must be positive")
    special_modes = sum(
        bool(value)
        for value in (
            args.downloadable_only,
            args.openalex_content_only,
            args.oa_recovery_only,
        )
    )
    if special_modes > 1:
        raise SystemExit(
            "Use only one of --downloadable-only, --openalex-content-only, "
            "or --oa-recovery-only"
        )
    if args.retry_blocked_oa and not args.oa_recovery_only:
        raise SystemExit("--retry-blocked-oa requires --oa-recovery-only; it does not bypass PMC OA checks")
    if args.openalex_content_only and not args.allow_openalex_content:
        raise SystemExit("--openalex-content-only requires --allow-openalex-content")
    if args.allow_openalex_content and not args.openalex_api_key:
        raise SystemExit("--allow-openalex-content requires OPENALEX_API_KEY or --openalex-api-key")
    if args.allow_openalex_content and args.max_openalex_content < 1:
        raise SystemExit("Set a positive --max-openalex-content hard cap")
    limit = None if args.all or args.work_id else args.limit
    cohort_ids = load_cohort(args.cohort_file) if args.cohort_file else None
    connection = readonly_snapshot(args.db) if args.dry_run else connect_db(args.db)
    try:
        rows = select_rows(
            connection,
            limit=limit,
            work_id=args.work_id,
            force=args.force,
            retry_failed=args.retry_failed,
            priority_max=args.priority_max,
            downloadable_only=args.downloadable_only,
            allow_openalex_content=args.allow_openalex_content,
            openalex_content_only=args.openalex_content_only,
            oa_recovery_only=args.oa_recovery_only,
            elsevier_api_key=args.elsevier_api_key,
            access_policy=args.access_policy,
            cohort_ids=cohort_ids,
            retry_blocked_oa=args.retry_blocked_oa,
        )
        if args.dry_run:
            print_dry_run(
                rows,
                args.allow_openalex_content,
                args.max_openalex_content,
                args.openalex_content_only,
                args.oa_recovery_only,
                args.elsevier_api_key,
                args.access_policy,
                args.ncbi_api_key,
                args.download_attempts,
                not args.no_resume,
            )
            return
        if not rows:
            print("No eligible rows")
            return
        quota = OpenAlexContentQuota(args.allow_openalex_content, args.max_openalex_content)
        ncbi_rate_limiter = RequestRateLimiter(8.0 if args.ncbi_api_key else 2.5)
        worker = lambda row: download_one(  # noqa: E731
            row,
            root=args.root,
            quota=quota,
            api_key=args.openalex_api_key,
            contact_email=args.email,
            max_bytes=args.max_file_mb * 1024 * 1024,
            openalex_content_only=args.openalex_content_only,
            oa_recovery_only=args.oa_recovery_only,
            elsevier_api_key=args.elsevier_api_key,
            access_policy=args.access_policy,
            ncbi_api_key=args.ncbi_api_key,
            ncbi_rate_limiter=ncbi_rate_limiter,
            download_attempts=args.download_attempts,
            resume=not args.no_resume,
        )
        successes = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            results = executor.map(worker, rows)
            for result in tqdm(results, total=len(rows), desc="Full-text fetch", unit="work"):
                record_result(connection, result)
                successes += int(result["status"] == "success")
                connection.commit()
        print(f"Fetched successfully: {successes:,}/{len(rows):,}")
        print(f"Paid-source HTTP requests (including retries/redirects): {quota.used:,}/{quota.maximum:,}")
        print("Inspect the manifest summary before increasing --limit or using --all.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
