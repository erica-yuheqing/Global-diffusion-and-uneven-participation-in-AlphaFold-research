#!/usr/bin/env python3
"""Find additional lawful open-access full-text candidates.

This stage targets records whose normal Europe PMC/OpenAlex/Unpaywall cascade
ended as ``unavailable``.  It queries metadata only and stores direct PDF/XML
candidate URLs plus the provider's open-access evidence.  Article bodies remain
the responsibility of ``04_fetch_fulltext.py``.

Automatic matching is deliberately conservative: DOI/PMID only, no title
fuzzy matching, and Crossref links are accepted only when the deposited metadata
also contains a recognized open licence.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sqlite3
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import requests
from tqdm import tqdm

from fulltext_pipeline.common import (
    DEFAULT_DB_PATH,
    EUROPE_PMC_API,
    canonical_text,
    connect_db,
    json_dumps,
    make_user_agent,
    normalize_doi,
    raise_for_status_redacted,
    redact_sensitive_text,
    request_with_retry,
    semantic_scholar_download_target,
    utc_now,
)
from fulltext_pipeline.oa_recovery_support import (
    BLOCKED_OA_STATUSES, PMC_XML_RE, evidence_dict, freeze_checked_cohort,
    load_cohort, pmc_xml_status, readonly_snapshot, status_after_attempt, validate_cohort_in_manifest,
)


OPENAIRE_RESEARCH_PRODUCTS = "https://api.openaire.eu/graph/v3/research-products"
CORE_SEARCH_WORKS = "https://api.core.ac.uk/v3/search/works/"
SEMANTIC_SCHOLAR_PAPER = "https://api.semanticscholar.org/graph/v1/paper"
CROSSREF_WORKS = "https://api.crossref.org/works"

PROVIDERS = ("openaire", "core", "semantic_scholar", "crossref")
OPEN_ACCESS_LABELS = {"open", "open access", "open source", "c_abf2"}
OPEN_LICENSE_MARKERS = (
    "creativecommons.org/licenses/",
    "creativecommons.org/publicdomain/",
    "rightsstatements.org/vocab/noc-cr",
    "nationalarchives.gov.uk/doc/open-government-licence",
)
DIRECT_PATH_MARKERS = (
    ".pdf",
    ".xml",
    "/pdf",
    "/download",
    "/bitstream",
    "/fulltext",
    "/full-text",
    "/jats",
    "/tei",
)

_thread_local = threading.local()
_throttles: dict[str, Any] = {}
_throttle_lock = threading.Lock()
DEFAULT_INTERVALS = {"core": 2.1, "semantic_scholar": 3.1, "openaire": 0.3, "crossref": 0.3, "europepmc": 0.4}


class ProviderPaused(RuntimeError):
    """No network request was made because this provider was rate-limited."""


class ProviderThrottle:
    def __init__(self, interval: float):
        self.interval = interval
        self.last_started = 0.0
        self.paused = False
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            if self.paused:
                raise ProviderPaused("Provider paused after HTTP 429; retry in a later run")
            delay = self.interval - (time.monotonic() - self.last_started)
            if delay > 0:
                time.sleep(delay)
            if self.paused:
                raise ProviderPaused("Provider paused after HTTP 429; retry in a later run")
            self.last_started = time.monotonic()


class PacedSession(requests.Session):
    def __init__(self, throttle):
        super().__init__()
        self.throttle = throttle

    def request(self, *args, **kwargs):
        self.throttle.wait()
        response = super().request(*args, **kwargs)
        if response.status_code == 429:
            self.throttle.paused = True
        return response


def metadata_request(session, method, url, **kwargs):
    # HTTP 429 is returned immediately and pauses this provider for this run;
    # every retry of a transient network/server error still passes the pacer.
    return request_with_retry(session, method, url, attempts=3,
                              retry_statuses={408, 425, 500, 502, 503, 504}, **kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--source",
        choices=[*PROVIDERS, "all"],
        default="all",
        help="Metadata provider to query",
    )
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--limit", type=int, default=20, help="Safety default: 20 works")
    limit_group.add_argument("--all", action="store_true", help="Process all eligible works")
    parser.add_argument(
        "--sample-seed",
        help="Deterministically randomize limited pilot selection (for example 20260825)",
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cohort-file", type=Path, help="Immutable JSON pilot membership; independent of fetch status")
    parser.add_argument("--expected-cohort-size", type=int, default=200)
    parser.add_argument("--request-interval", type=float, help="Override minimum seconds between metadata requests (0-30, exclusive of zero)")
    state_group = parser.add_mutually_exclusive_group()
    state_group.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry new rows and provider checks previously marked error",
    )
    state_group.add_argument("--force", action="store_true", help="Re-query completed checks")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected cohort without making provider requests",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--freeze-checked-pilot", type=Path,
                         help="Locally recover identical historical provider-check IDs into a no-overwrite JSON lock")
    actions.add_argument("--verify-pmc", action="store_true",
                         help="Check pending PMC candidates using Europe PMC metadata only; no article bodies")
    actions.add_argument(
        "--repair-existing", "--classify-existing", dest="repair_existing",
        action="store_true",
        help=(
            "Locally repair PMC/CORE candidates and quarantine failed URLs; no provider requests"
        ),
    )
    parser.add_argument(
        "--core-api-key",
        default=os.getenv("CORE_API_KEY"),
        help="Defaults to CORE_API_KEY; required when CORE is selected",
    )
    parser.add_argument(
        "--semantic-scholar-api-key",
        default=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
        help="Optional; defaults to SEMANTIC_SCHOLAR_API_KEY",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("CONTACT_EMAIL") or os.getenv("UNPAYWALL_EMAIL"),
        help="Contact email for provider User-Agent/polite-pool requests",
    )
    return parser.parse_args()


def session_for(provider: str, email: str | None, api_key: str | None) -> requests.Session:
    sessions = getattr(_thread_local, "oa_sessions", None)
    if sessions is None:
        sessions = {}
        _thread_local.oa_sessions = sessions
    key = (provider, hashlib.sha256((api_key or "").encode()).hexdigest(), email)
    if key not in sessions:
        with _throttle_lock:
            throttle = _throttles.setdefault(provider, ProviderThrottle(DEFAULT_INTERVALS[provider]))
        session = PacedSession(throttle)
        session.headers.update(
            {
                "User-Agent": make_user_agent(email),
                "Accept": "application/json",
            }
        )
        if provider == "core" and api_key:
            session.headers["Authorization"] = f"Bearer {api_key}"
        elif provider == "semantic_scholar" and api_key:
            session.headers["x-api-key"] = api_key
        sessions[key] = session
    return sessions[key]


def response_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_pmid(value: Any) -> str | None:
    raw = canonical_text(value)
    if raw.upper().startswith("PMID:"):
        raw = raw[5:].strip()
    return raw if raw.isdigit() else None


def safe_public_url(value: Any) -> str | None:
    raw = canonical_text(value)
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    hostname = parts.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return None
    return raw


def infer_format(url: str, content_type: Any = None) -> str | None:
    lower_type = canonical_text(content_type).lower()
    lower_url = urlsplit(url).path.lower()
    if "pdf" in lower_type or lower_url.endswith(".pdf") or "/pdf" in lower_url:
        return "pdf"
    if (
        "xml" in lower_type
        or lower_url.endswith(".xml")
        or any(marker in lower_url for marker in ("/jats", "/tei"))
    ):
        return "xml"
    return None


def direct_candidate(value: Any, content_type: Any = None) -> tuple[str, str] | None:
    url = safe_public_url(value)
    if not url:
        return None
    expected_format = infer_format(url, content_type)
    if not expected_format:
        path = urlsplit(url).path.lower()
        if not any(marker in path for marker in DIRECT_PATH_MARKERS):
            return None
        expected_format = "pdf"
    return url, expected_format


def recursive_identifier_values(value: Any, scheme: str) -> set[str]:
    """Collect values only from explicit {scheme/type, value/id} identifier objects."""
    found: set[str] = set()
    if isinstance(value, dict):
        label = canonical_text(value.get("scheme") or value.get("type")).lower()
        identifier = value.get("value") or value.get("id")
        if label == scheme and identifier:
            found.add(canonical_text(identifier))
        for nested in value.values():
            found.update(recursive_identifier_values(nested, scheme))
    elif isinstance(value, list):
        for nested in value:
            found.update(recursive_identifier_values(nested, scheme))
    return found


def exact_identifier_match(record: dict[str, Any], row: dict[str, Any]) -> tuple[bool, str]:
    doi = normalize_doi(row.get("doi"))
    if doi:
        values = {normalize_doi(value) for value in recursive_identifier_values(record, "doi")}
        direct = normalize_doi(record.get("doi"))
        if direct:
            values.add(direct)
        if doi in values:
            return True, "doi"
    pmid = normalize_pmid(row.get("pmid"))
    if pmid:
        values = {normalize_pmid(value) for value in recursive_identifier_values(record, "pmid")}
        if pmid in values:
            return True, "pmid"
    return False, "doi" if doi else "pmid"


def candidate(
    *,
    provider: str,
    url: str,
    expected_format: str,
    match_method: str,
    license_value: Any = None,
    version: Any = None,
    landing_url: Any = None,
    evidence: dict[str, Any],
    status: str = "available",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "url": url,
        "expected_format": expected_format,
        "license": canonical_text(license_value) or None,
        "version": canonical_text(version) or None,
        "landing_url": safe_public_url(landing_url),
        "match_method": match_method,
        "access_evidence": evidence,
        "status": status,
    }


def deduplicate_candidates(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if value["url"] not in seen:
            seen.add(value["url"])
            deduplicated.append(value)
    return deduplicated


def query_openaire(row: dict[str, Any], email: str | None, _: str | None) -> dict[str, Any]:
    doi = normalize_doi(row.get("doi"))
    pmid = normalize_pmid(row.get("pmid"))
    identifier = doi or pmid
    if not identifier:
        return provider_result(row, "openaire", "not_applicable_no_identifier")
    response = metadata_request(
        session_for("openaire", email, None),
        "GET",
        OPENAIRE_RESEARCH_PRODUCTS,
        params={"pid": identifier, "type": "publication", "pageSize": 10},
    )
    raise_for_status_redacted(response, "OpenAIRE")
    payload = response.json()
    digest = response_hash(payload)
    results = payload.get("results") or []
    candidates: list[dict[str, Any]] = []
    exact_results = 0
    for record in results:
        if not isinstance(record, dict):
            continue
        exact, match_method = exact_identifier_match(record, row)
        if not exact:
            continue
        exact_results += 1
        for instance in record.get("instances") or []:
            if not isinstance(instance, dict):
                continue
            access = instance.get("accessRight") or {}
            if isinstance(access, dict):
                access_label = canonical_text(access.get("label") or access.get("code")).lower()
                access_code = canonical_text(access.get("code")).lower()
            else:
                access_label = canonical_text(access).lower()
                access_code = ""
            if access_label not in OPEN_ACCESS_LABELS and access_code not in OPEN_ACCESS_LABELS:
                continue
            urls = instance.get("urls") or []
            if isinstance(urls, str):
                urls = [urls]
            for url_value in urls:
                direct = direct_candidate(url_value)
                if not direct:
                    continue
                url, expected_format = direct
                candidates.append(
                    candidate(
                        provider="openaire",
                        url=url,
                        expected_format=expected_format,
                        match_method=match_method,
                        license_value=instance.get("license"),
                        version=instance.get("type"),
                        evidence={
                            "provider_asserted_access": access_label or access_code,
                            "openaire_id": record.get("id"),
                            "instance_host": instance.get("hostedby"),
                            "instance_source": instance.get("collectedfrom"),
                        },
                    )
                )
    status = "found" if candidates else ("no_usable_open_fulltext" if exact_results else "no_match")
    return provider_result(
        row,
        "openaire",
        status,
        candidates=deduplicate_candidates(candidates),
        result_count=len(results),
        response_sha256=digest,
    )


def core_result_dois(record: dict[str, Any]) -> set[str]:
    raw = record.get("doi") or record.get("dois")
    values = raw if isinstance(raw, list) else [raw]
    return {doi for value in values if (doi := normalize_doi(value))}


def query_core(row: dict[str, Any], email: str | None, api_key: str | None) -> dict[str, Any]:
    doi = normalize_doi(row.get("doi"))
    if not doi:
        return provider_result(row, "core", "not_applicable_no_doi")
    if not api_key:
        raise ValueError("CORE_API_KEY is required")
    response = metadata_request(
        session_for("core", email, api_key),
        "GET",
        CORE_SEARCH_WORKS,
        params={"q": f'doi:"{doi}"', "limit": 10, "offset": 0},
    )
    raise_for_status_redacted(response, "CORE")
    payload = response.json()
    digest = response_hash(payload)
    results = payload.get("results") or []
    candidates: list[dict[str, Any]] = []
    exact_results = 0
    for record in results:
        if not isinstance(record, dict) or doi not in core_result_dois(record):
            continue
        exact_results += 1
        source_fulltext_urls = record.get("sourceFulltextUrls")
        if isinstance(source_fulltext_urls, str):
            source_fulltext_urls = [source_fulltext_urls]
        source_fulltext_urls = [
            url for value in (source_fulltext_urls if isinstance(source_fulltext_urls, list) else [])
            if (url := safe_public_url(value))
        ]
        routes = [(record.get("downloadUrl"), "core_cache"),
                  *((url, "repository_original") for url in source_fulltext_urls)]
        for raw_url, route in routes:
            direct = direct_candidate(raw_url)
            if not direct:
                continue
            url, expected_format = direct
            candidates.append(candidate(
                provider="core",
                url=url,
                expected_format=expected_format,
                match_method="doi",
                license_value=record.get("license"),
                version=record.get("documentType"),
                landing_url=source_fulltext_urls[0] if route == "core_cache" and source_fulltext_urls else None,
                evidence={
                    "core_id": record.get("id"),
                    "repository": record.get("dataProvider"),
                    "oa_aggregator": "CORE",
                    "route": route,
                    "source_fulltext_urls": source_fulltext_urls,
                },
            ))
    status = "found" if candidates else ("no_usable_open_fulltext" if exact_results else "no_match")
    return provider_result(
        row,
        "core",
        status,
        candidates=deduplicate_candidates(candidates),
        result_count=len(results),
        response_sha256=digest,
    )


def query_semantic_scholar(
    row: dict[str, Any], email: str | None, api_key: str | None
) -> dict[str, Any]:
    doi = normalize_doi(row.get("doi"))
    pmid = normalize_pmid(row.get("pmid"))
    if doi:
        external_id = f"DOI:{doi}"
        match_method = "doi"
    elif pmid:
        external_id = f"PMID:{pmid}"
        match_method = "pmid"
    else:
        return provider_result(row, "semantic_scholar", "not_applicable_no_identifier")
    response = metadata_request(
        session_for("semantic_scholar", email, api_key),
        "GET",
        f"{SEMANTIC_SCHOLAR_PAPER}/{quote(external_id, safe=':')}",
        params={"fields": "paperId,title,externalIds,isOpenAccess,openAccessPdf"},
    )
    if response.status_code == 404:
        return provider_result(row, "semantic_scholar", "no_match")
    raise_for_status_redacted(response, "Semantic Scholar")
    payload = response.json()
    digest = response_hash(payload)
    external_ids = payload.get("externalIds") or {}
    exact = (
        normalize_doi(external_ids.get("DOI")) == doi
        if doi
        else normalize_pmid(external_ids.get("PubMed")) == pmid
    )
    if not exact:
        return provider_result(
            row,
            "semantic_scholar",
            "no_match",
            result_count=1,
            response_sha256=digest,
        )
    oa_pdf = payload.get("openAccessPdf") or {}
    original_url = safe_public_url(oa_pdf.get("url"))
    retrieval_url, expected_format, url_class = semantic_scholar_download_target(
        original_url
    )
    candidates: list[dict[str, Any]] = []
    if payload.get("isOpenAccess") is True and retrieval_url and expected_format:
        candidates.append(
            candidate(
                provider="semantic_scholar",
                url=retrieval_url,
                expected_format=expected_format,
                match_method=match_method,
                license_value=oa_pdf.get("license"),
                landing_url=original_url if retrieval_url != original_url else None,
                evidence={
                    "isOpenAccess": True,
                    "paperId": payload.get("paperId"),
                    "oa_status": oa_pdf.get("status"),
                    "disclaimer": oa_pdf.get("disclaimer"),
                    "url_class": url_class,
                    "original_oa_url": original_url,
                },
                status=pmc_xml_status(row, retrieval_url) if url_class == "pmc_jats" else "available",
            )
        )
    return provider_result(
        row,
        "semantic_scholar",
        "found" if candidates else "no_usable_open_fulltext",
        candidates=candidates,
        result_count=1,
        response_sha256=digest,
    )


def recognized_open_license(value: Any) -> bool:
    url = canonical_text(value).lower()
    return any(marker in url for marker in OPEN_LICENSE_MARKERS)


def query_crossref(row: dict[str, Any], email: str | None, _: str | None) -> dict[str, Any]:
    doi = normalize_doi(row.get("doi"))
    if not doi:
        return provider_result(row, "crossref", "not_applicable_no_doi")
    params = {"mailto": email} if email else None
    response = metadata_request(
        session_for("crossref", email, None),
        "GET",
        f"{CROSSREF_WORKS}/{quote(doi, safe='')}",
        params=params,
    )
    if response.status_code == 404:
        return provider_result(row, "crossref", "no_match")
    raise_for_status_redacted(response, "Crossref")
    payload = response.json()
    digest = response_hash(payload)
    record = payload.get("message") or {}
    if normalize_doi(record.get("DOI")) != doi:
        return provider_result(
            row, "crossref", "no_match", result_count=1, response_sha256=digest
        )
    licenses = [
        item
        for item in record.get("license") or []
        if isinstance(item, dict) and recognized_open_license(item.get("URL"))
    ]
    candidates: list[dict[str, Any]] = []
    if licenses:
        for link in record.get("link") or []:
            if not isinstance(link, dict):
                continue
            direct = direct_candidate(link.get("URL"), link.get("content-type"))
            if not direct:
                continue
            link_version = canonical_text(link.get("content-version")).lower()
            compatible_licenses = [
                item
                for item in licenses
                if not canonical_text(item.get("content-version"))
                or not link_version
                or canonical_text(item.get("content-version")).lower() == link_version
            ]
            if not compatible_licenses:
                continue
            license_url = canonical_text(compatible_licenses[0].get("URL"))
            url, expected_format = direct
            candidates.append(
                candidate(
                    provider="crossref",
                    url=url,
                    expected_format=expected_format,
                    match_method="doi",
                    license_value=license_url,
                    version=link.get("content-version"),
                    evidence={
                        "open_license": license_url,
                        "intended_application": link.get("intended-application"),
                        "deposited_by": record.get("publisher"),
                    },
                )
            )
    return provider_result(
        row,
        "crossref",
        "found" if candidates else "no_usable_open_fulltext",
        candidates=deduplicate_candidates(candidates),
        result_count=1,
        response_sha256=digest,
    )


def provider_result(
    row: dict[str, Any],
    provider: str,
    status: str,
    *,
    candidates: list[dict[str, Any]] | None = None,
    result_count: int = 0,
    response_sha256: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "work_id": row["work_id"],
        "provider": provider,
        "status": status,
        "checked_at": utc_now(),
        "result_count": result_count,
        "response_sha256": response_sha256,
        "error": error,
        "candidates": candidates or [],
    }


QUERY_FUNCTIONS: dict[str, Callable[[dict[str, Any], str | None, str | None], dict[str, Any]]] = {
    "openaire": query_openaire,
    "core": query_core,
    "semantic_scholar": query_semantic_scholar,
    "crossref": query_crossref,
}


def safe_query(
    provider: str,
    row: dict[str, Any],
    email: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    try:
        return QUERY_FUNCTIONS[provider](row, email, api_key)
    except ProviderPaused as exc:
        return provider_result(row, provider, "deferred_rate_limit", error=str(exc))
    except Exception as exc:
        return provider_result(
            row,
            provider,
            "error",
            error=redact_sensitive_text(f"{type(exc).__name__}: {exc}"),
        )


def select_rows(
    connection: sqlite3.Connection,
    provider: str,
    *,
    limit: int | None,
    force: bool,
    retry_failed: bool,
    sample_seed: str | None,
    cohort_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    clauses = ["w.in_current_corpus=1"]
    params: list[Any] = [provider]
    if cohort_ids is not None:
        validate_cohort_in_manifest(connection, cohort_ids)
        clauses.append("w.work_id IN (" + ",".join("?" for _ in cohort_ids) + ")")
        params.extend(cohort_ids)
    else:
        clauses.append("w.fetch_status='unavailable'")
    locked_sample = bool(sample_seed and limit is not None)
    if not force and not locked_sample:
        if retry_failed:
            clauses.append("(c.work_id IS NULL OR c.status IN ('pending', 'error'))")
        else:
            clauses.append("(c.work_id IS NULL OR c.status='pending')")
    sql = f"""
        SELECT w.*, c.status AS _provider_check_status
        FROM works AS w
        LEFT JOIN oa_provider_checks AS c
          ON c.work_id=w.work_id AND c.provider=?
        WHERE {' AND '.join(clauses)}
        ORDER BY w.priority, w.work_id
    """
    rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
    if locked_sample:
        rows.sort(
            key=lambda row: hashlib.sha256(
                f"{sample_seed}:{row['work_id']}".encode("utf-8")
            ).digest()
        )
        rows = rows[:limit]
        if not force:
            allowed = {None, "pending", "error"} if retry_failed else {None, "pending"}
            rows = [row for row in rows if row["_provider_check_status"] in allowed]
        return rows
    return rows if limit is None else rows[:limit]


def store_result(connection: sqlite3.Connection, result: dict[str, Any]) -> None:
    if result["status"] != "error":
        connection.execute(
            "UPDATE oa_recovery_candidates SET status='superseded' "
            "WHERE work_id=? AND provider=? "
            "AND status IN ('available','needs_pmc_check','pmc_not_oa','pmc_unavailable','pmc_id_mismatch')",
            (result["work_id"], result["provider"]),
        )
    for item in result["candidates"]:
        upsert_candidate(connection, result["work_id"], item, result["checked_at"], result.get("response_sha256"))
    connection.execute(
        """
        INSERT INTO oa_provider_checks(
            work_id, provider, status, checked_at, result_count,
            response_sha256, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(work_id, provider) DO UPDATE SET
            status=excluded.status,
            checked_at=excluded.checked_at,
            result_count=excluded.result_count,
            response_sha256=excluded.response_sha256,
            error=excluded.error
        """,
        (
            result["work_id"],
            result["provider"],
            result["status"],
            result["checked_at"],
            result["result_count"],
            result.get("response_sha256"),
            result.get("error"),
        ),
    )


def upsert_candidate(connection, work_id, item, discovered_at, response_sha256=None):
    prior = connection.execute(
        "SELECT access_evidence FROM oa_recovery_candidates WHERE work_id=? AND provider=? AND url=?",
        (work_id,item["provider"],item["url"]),
    ).fetchone()
    evidence = evidence_dict(prior["access_evidence"] if prior else None)
    evidence.update(item["access_evidence"])
    status = item.get("status","available")
    if item["provider"] == "semantic_scholar" and PMC_XML_RE.fullmatch(item["url"]):
        work = dict(connection.execute("SELECT * FROM works WHERE work_id=?",(work_id,)).fetchone())
        status = pmc_xml_status(work,item["url"],evidence)
    connection.execute(
        """
        INSERT INTO oa_recovery_candidates(
            work_id,provider,url,expected_format,license,version,landing_url,
            match_method,access_evidence,response_sha256,status,discovered_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(work_id,provider,url) DO UPDATE SET
            expected_format=excluded.expected_format,
            license=COALESCE(excluded.license,oa_recovery_candidates.license),
            version=COALESCE(excluded.version,oa_recovery_candidates.version),
            landing_url=COALESCE(excluded.landing_url,oa_recovery_candidates.landing_url),
            access_evidence=excluded.access_evidence,
            response_sha256=COALESCE(excluded.response_sha256,oa_recovery_candidates.response_sha256),
            status=CASE WHEN oa_recovery_candidates.status IN
                ('downloaded','http_403','http_404','http_410','invalid_payload')
                THEN oa_recovery_candidates.status ELSE excluded.status END
        """,
        (work_id,item["provider"],item["url"],item["expected_format"],item.get("license"),
         item.get("version"),item.get("landing_url"),item["match_method"],
         json_dumps(evidence),response_sha256,status,discovered_at),
    )


def existing_candidates(connection, cohort_ids=None, provider=None):
    clauses = ["w.in_current_corpus=1"]
    params = []
    if cohort_ids is not None:
        validate_cohort_in_manifest(connection, cohort_ids)
        clauses.append("c.work_id IN (" + ",".join("?" for _ in cohort_ids) + ")")
        params.extend(cohort_ids)
    if provider:
        clauses.append("c.provider=?")
        params.append(provider)
    return [dict(row) for row in connection.execute(
        "SELECT c.*,w.pmcid,w.epmc_is_oa,w.epmc_in_fulltext,w.europepmc_status,w.doi,w.pmid "
        "FROM oa_recovery_candidates c JOIN works w ON w.work_id=c.work_id WHERE "
        + " AND ".join(clauses) + " ORDER BY c.candidate_id", params
    )]


def classify_existing_semantic_scholar_candidates(connection, cohort_ids=None):
    counts = Counter()
    for row in existing_candidates(connection, cohort_ids, "semantic_scholar"):
        if row["status"] in {"downloaded", "superseded"}:
            continue
        target_url, expected_format, url_class = semantic_scholar_download_target(safe_public_url(row["url"]))
        evidence = evidence_dict(row["access_evidence"])
        evidence.update(url_class=url_class)
        evidence.setdefault("original_oa_url", row["url"])
        if not target_url or not expected_format:
            status = "landing_only" if url_class == "landing_only" else "invalid"
            connection.execute("UPDATE oa_recovery_candidates SET status=?,access_evidence=? WHERE candidate_id=?",
                               (status,json_dumps(evidence),row["candidate_id"]))
            counts[status] += 1
            continue
        status = pmc_xml_status(row, target_url, evidence) if url_class == "pmc_jats" else "available"
        if target_url != row["url"]:
            # Keep the original landing page; never overwrite an existing
            # derived candidate's newer PMC verification with the parent data.
            connection.execute("UPDATE oa_recovery_candidates SET status='landing_resolved' WHERE candidate_id=?",
                               (row["candidate_id"],))
            exists = connection.execute("SELECT 1 FROM oa_recovery_candidates WHERE work_id=? AND provider=? AND url=?",
                                        (row["work_id"],"semantic_scholar",target_url)).fetchone()
            if not exists:
                evidence["derived_retrieval_url"] = target_url
                upsert_candidate(connection,row["work_id"],candidate(
                    provider="semantic_scholar",url=target_url,expected_format=expected_format,
                    match_method=row["match_method"],license_value=row["license"],version=row["version"],
                    landing_url=row["url"],evidence=evidence,status=status,
                ),utc_now(),row["response_sha256"])
                counts["pmc_converted"] += 1
            continue
        if status == "available" and row["status"] in BLOCKED_OA_STATUSES:
            status = row["status"]
        connection.execute(
            "UPDATE oa_recovery_candidates SET status=?,expected_format=?,access_evidence=? WHERE candidate_id=?",
            (status,expected_format,json_dumps(evidence),row["candidate_id"]),
        )
        counts[status] += 1
    return dict(counts)


def repair_existing(connection, cohort_ids=None):
    counts = Counter()
    # Historical terminal responses are retained, not deleted or silently reset.
    for row in existing_candidates(connection, cohort_ids):
        if row["status"] not in {"available", *BLOCKED_OA_STATUSES}:
            continue
        last = connection.execute(
            "SELECT outcome,http_status FROM fetch_attempts WHERE work_id=? AND url=? "
            "AND outcome NOT LIKE 'skipped_%' AND outcome<>'http_redirect' ORDER BY attempt_id DESC LIMIT 1",
            (row["work_id"],row["url"]),
        ).fetchone()
        if last:
            status = status_after_attempt(row["status"],last["outcome"],last["http_status"])
            if status != row["status"]:
                connection.execute("UPDATE oa_recovery_candidates SET status=? WHERE candidate_id=?",
                                   (status,row["candidate_id"]))
                counts[status] += 1
    counts.update(classify_existing_semantic_scholar_candidates(connection,cohort_ids))
    for row in existing_candidates(connection,cohort_ids,"core"):
        if row["status"] == "superseded":
            continue
        evidence = evidence_dict(row["access_evidence"])
        sources = evidence.get("source_fulltext_urls") or []
        if not isinstance(sources,list):
            sources = []
        for value in [row.get("landing_url"),*sources]:
            direct = direct_candidate(value)
            if not direct:
                continue
            url, expected_format = direct
            exists = connection.execute("SELECT 1 FROM oa_recovery_candidates WHERE work_id=? AND provider='core' AND url=?",
                                        (row["work_id"],url)).fetchone()
            if exists:
                continue
            upsert_candidate(connection,row["work_id"],candidate(
                provider="core",url=url,expected_format=expected_format,match_method=row["match_method"],
                license_value=row["license"],version=row["version"],
                evidence={**evidence,"route":"repository_original","derived_from_candidate_id":row["candidate_id"]},
            ),utc_now(),row["response_sha256"])
            counts["core_repository_added"] += 1
    return dict(counts)


def verify_pmc_candidate(row, email):
    pmcid = PMC_XML_RE.fullmatch(row["url"]).group(1).upper()
    check = {"pmcid":pmcid,"checked_at":utc_now()}
    try:
        response = metadata_request(session_for("europepmc",email,None),"GET",f"{EUROPE_PMC_API}/search",
                                    params={"query":f"PMCID:{pmcid}","format":"json","resultType":"core","pageSize":100})
        raise_for_status_redacted(response,"Europe PMC metadata")
        payload = response.json()
        check["response_sha256"] = response_hash(payload)
        matches = [item for item in ((payload.get("resultList") or {}).get("result") or [])
                   if isinstance(item,dict) and str(item.get("pmcid") or "").upper() == pmcid]
        exact = [item for item in matches if (
            normalize_doi(item.get("doi")) == normalize_doi(row["doi"]) if row.get("doi")
            else item.get("source") == "MED" and normalize_pmid(item.get("id")) == normalize_pmid(row.get("pmid")) and bool(row.get("pmid"))
        )]
        if not matches:
            check["status"] = "pmc_unavailable"
        elif not exact:
            check["status"] = "pmc_id_mismatch"
        else:
            best = max(exact,key=lambda item:(item.get("isOpenAccess")=="Y",item.get("inEPMC")=="Y"))
            check.update(isOpenAccess=best.get("isOpenAccess"),inEPMC=best.get("inEPMC"))
            check["status"] = ("available" if best.get("isOpenAccess")=="Y" and best.get("inEPMC")=="Y"
                               else "pmc_not_oa" if best.get("isOpenAccess")=="N" else "pmc_unavailable")
    except Exception as exc:
        check.update(status="needs_pmc_check",error=redact_sensitive_text(exc))
    return check


def enabled_providers(args: argparse.Namespace) -> list[str]:
    providers = list(PROVIDERS) if args.source == "all" else [args.source]
    if "core" in providers and not args.core_api_key:
        if args.source == "core" and not args.dry_run:
            raise SystemExit("CORE requires CORE_API_KEY or --core-api-key")
        if not args.dry_run:
            providers.remove("core")
            print("CORE skipped: set CORE_API_KEY to enable it", file=sys.stderr)
    return providers


def print_dry_run(provider_rows: dict[str, list[dict[str, Any]]], core_enabled: bool) -> None:
    print("Dry run: no provider requests will be made")
    print(f"CORE API key configured: {core_enabled}")
    for provider, rows in provider_rows.items():
        with_doi = sum(bool(normalize_doi(row.get("doi"))) for row in rows)
        with_pmid = sum(bool(normalize_pmid(row.get("pmid"))) for row in rows)
        print(
            f"{provider:18} selected={len(rows):,} "
            f"with_doi={with_doi:,} with_pmid={with_pmid:,}"
        )
        for row in rows[:5]:
            print(
                f"  {row['work_id']} doi={row.get('doi') or '-'} "
                f"pmid={row.get('pmid') or '-'} abstract={bool(row.get('abstract'))}"
            )


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    if args.expected_cohort_size < 1:
        raise SystemExit("--expected-cohort-size must be positive")
    if args.request_interval is not None and not 0 < args.request_interval <= 30:
        raise SystemExit("--request-interval must be greater than 0 and at most 30 seconds")
    if args.cohort_file and args.sample_seed:
        raise SystemExit("Use --cohort-file without --sample-seed; membership is already fixed")
    if args.sample_seed and args.retry_failed:
        raise SystemExit("Seeded retries can change membership after downloads; freeze the checked pilot and use --cohort-file")
    if args.freeze_checked_pilot and args.cohort_file:
        raise SystemExit("Use --freeze-checked-pilot separately from --cohort-file")
    # Shared per-provider pacers also cover retries. Reset for each CLI invocation.
    _throttles.clear()
    _thread_local.oa_sessions = {}
    for provider, interval in DEFAULT_INTERVALS.items():
        _throttles[provider] = ProviderThrottle(args.request_interval or interval)
    limit = None if args.all else args.limit
    cohort_ids = load_cohort(args.cohort_file) if args.cohort_file else None
    connection = readonly_snapshot(args.db) if args.dry_run or args.freeze_checked_pilot else connect_db(args.db)
    try:
        if cohort_ids is not None:
            validate_cohort_in_manifest(connection,cohort_ids)
            print(f"Locked cohort: {len(cohort_ids):,} works; selection never replaces these IDs")
        if args.freeze_checked_pilot:
            ids = freeze_checked_cohort(connection,args.freeze_checked_pilot,PROVIDERS,
                                        args.expected_cohort_size,dry_run=args.dry_run)
            validate_cohort_in_manifest(connection,ids)
            print(f"{'Would freeze' if args.dry_run else 'Verified/frozen'} {len(ids):,} historical pilot IDs: {args.freeze_checked_pilot}")
            print("No provider requests or manifest changes were made.")
            return
        if args.repair_existing:
            counts = repair_existing(connection,cohort_ids)
            if not args.dry_run:
                connection.commit()
            print("Existing-candidate repair:",counts)
            print("Dry run: only an in-memory copy was changed." if args.dry_run else "Local candidate updates saved; download history retained.")
            print("No provider requests were made.")
            return
        if args.verify_pmc:
            rows = [row for row in existing_candidates(connection,cohort_ids,"semantic_scholar")
                    if PMC_XML_RE.fullmatch(row["url"]) and (
                        row["status"] == "needs_pmc_check" or args.force and
                        row["status"] in {"pmc_not_oa","pmc_unavailable","pmc_id_mismatch",*BLOCKED_OA_STATUSES}
                    )]
            if limit is not None:
                rows = rows[:limit]
            print(f"PMC metadata checks selected: {len(rows):,}; no article downloads")
            if args.dry_run:
                for row in rows[:20]:
                    print(f"  {row['work_id']} {PMC_XML_RE.fullmatch(row['url']).group(1)} status={row['status']}")
                print("Dry run: no provider requests or manifest changes.")
                return
            counts = Counter()
            for row in tqdm(rows,desc="PMC OA verification",unit="candidate"):
                check = verify_pmc_candidate(row,args.email)
                evidence = evidence_dict(row["access_evidence"])
                evidence["pmc_check"] = check
                connection.execute("UPDATE oa_recovery_candidates SET status=?,access_evidence=? WHERE candidate_id=?",
                                   (check["status"],json_dumps(evidence),row["candidate_id"]))
                connection.commit()
                counts[check["status"]] += 1
            print("PMC verification:",dict(counts))
            return
        providers = enabled_providers(args)
        provider_rows = {
            provider: select_rows(
                connection,
                provider,
                limit=limit,
                force=args.force,
                retry_failed=args.retry_failed,
                sample_seed=args.sample_seed,
                cohort_ids=cohort_ids,
            )
            for provider in providers
        }
        if args.dry_run:
            print_dry_run(provider_rows, bool(args.core_api_key))
            return
        for provider in providers:
            rows = provider_rows[provider]
            if not rows:
                print(f"{provider}: no eligible rows")
                continue
            print(f"{provider}: request interval >= {_throttles[provider].interval:g}s across workers; HTTP 429 pauses this provider for this run")
            api_key = (
                args.core_api_key
                if provider == "core"
                else args.semantic_scholar_api_key
                if provider == "semantic_scholar"
                else None
            )
            worker = lambda row: safe_query(provider, row, args.email, api_key)  # noqa: E731
            status_counts: dict[str, int] = {}
            candidate_count = 0
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                results = executor.map(worker, rows)
                for result in tqdm(
                    results,
                    total=len(rows),
                    desc=f"{provider} OA metadata",
                    unit="work",
                ):
                    status = result["status"]
                    if status != "deferred_rate_limit":
                        store_result(connection, result)
                        connection.commit()
                    status_counts[status] = status_counts.get(status, 0) + 1
                    candidate_count += len(result["candidates"])
            print(
                f"{provider}: selected {len(rows):,}; "
                f"checked {len(rows) - status_counts.get('deferred_rate_limit',0):,}; statuses={status_counts}; "
                f"candidate records={candidate_count:,} (PMC candidates require OA verification)"
            )
        print("Metadata enrichment complete. Review the manifest summary before downloading.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
