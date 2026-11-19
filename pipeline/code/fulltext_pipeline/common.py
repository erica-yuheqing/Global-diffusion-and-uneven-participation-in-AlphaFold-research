from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


SCHEMA_VERSION = "fulltext-manifest-v3"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FULLTEXT_ROOT = PROJECT_ROOT / "fulltext"
DEFAULT_DB_PATH = DEFAULT_FULLTEXT_ROOT / "manifest" / "fulltext_manifest.sqlite"
DEFAULT_WORKS_DIR = PROJECT_ROOT / "derived_tables" / "works"

OPENALEX_API = "https://api.openalex.org"
OPENALEX_CONTENT = "https://content.openalex.org/works"
EUROPE_PMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNPAYWALL_API = "https://api.unpaywall.org/v2"

DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
OPENALEX_ID_RE = re.compile(r"W\d+$", re.I)
PMC_ARTICLE_PATH_RE = re.compile(r"/(?:pmc/)?articles/(?:PMC)?(\d+)(?:/|$)", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw.lower() in {"", "nan", "none", "null", "<na>"}:
        return None
    doi = DOI_PREFIX_RE.sub("", raw).strip().lower()
    return doi or None


def normalize_openalex_id(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw.lower() in {"", "nan", "none", "null", "<na>"}:
        return None
    short_id = raw.rstrip("/").rsplit("/", 1)[-1].upper()
    return short_id if OPENALEX_ID_RE.fullmatch(short_id) else None


def semantic_scholar_download_target(value: Any) -> tuple[str | None, str | None, str]:
    """Classify an S2 OA locator as direct, PMC-resolvable, or landing-only.

    Semantic Scholar's ``openAccessPdf.url`` sometimes points to a DOI resolver,
    repository record, or PMC article page rather than a PDF.  PMC article pages
    can be converted deterministically to Europe PMC JATS; other landing pages
    remain audit evidence but are not sent to the full-text downloader.
    """
    raw = canonical_text(value)
    if not raw:
        return None, None, "missing"
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None, None, "invalid"
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None, None, "invalid"
    host = parts.hostname.rstrip(".").lower()
    path = parts.path.lower()

    if host in {"www.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"}:
        pmc_match = PMC_ARTICLE_PATH_RE.search(parts.path)
        if pmc_match:
            pmcid = f"PMC{pmc_match.group(1)}"
            return f"{EUROPE_PMC_API}/{pmcid}/fullTextXML", "xml", "pmc_jats"

    if host == "www.ebi.ac.uk" and "/europepmc/webservices/rest/pmc" in path:
        if path.endswith("/fulltextxml"):
            return raw, "xml", "pmc_jats"

    landing_hosts = {"doi.org", "dx.doi.org", "hdl.handle.net"}
    if host in landing_hosts:
        return None, None, "landing_only"

    if host.endswith("sciencedirect.com") and "/science/article/am/pii/" in path:
        return raw, "pdf", "direct_pdf"

    if path.endswith(".pdf") or ".pdf/" in path:
        return raw, "pdf", "direct_pdf"
    if path.endswith(".xml") or ".xml/" in path:
        return raw, "xml", "direct_xml"
    if any(marker in path for marker in ("/download/", "/bitstream/", "/fulltext/", "/full-text/")):
        return raw, "pdf", "direct_pdf"
    return None, None, "landing_only"


def is_elsevier_article_api_url(value: Any) -> bool:
    raw = canonical_text(value)
    if not raw:
        return False
    try:
        parts = urlsplit(raw)
    except ValueError:
        return False
    return (
        parts.hostname is not None
        and parts.hostname.rstrip(".").lower() == "api.elsevier.com"
        and parts.path.lower().startswith("/content/article/")
    )


def safe_work_id(value: str) -> str:
    short_id = normalize_openalex_id(value)
    if not short_id:
        raise ValueError(f"Invalid OpenAlex work ID: {value!r}")
    return short_id


def nested_work_path(root: Path, source: str, work_id: str, suffix: str) -> Path:
    short_id = safe_work_id(work_id)
    digits = short_id[1:]
    first = f"W{digits[:2] or '00'}"
    second = digits[2:4] or "00"
    return root / "raw" / source / first / second / f"{short_id}{suffix}"


def add_query_parameter(url: str, key: str, value: str | None) -> str:
    if not value:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def redact_url(url: str) -> str:
    """Redact credentials and contact details before URLs reach logs or errors."""
    parts = urlsplit(url)
    sensitive_keys = {"api_key", "email", "mailto"}
    query = [
        (key, "REDACTED" if key.lower() in sensitive_keys else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def redact_sensitive_text(value: Any) -> str:
    text = str(value)
    return re.sub(
        r"([?&](?:api_key|email|mailto)=)[^&\s]+",
        r"\1REDACTED",
        text,
        flags=re.I,
    )


def raise_for_status_redacted(response: requests.Response, source: str) -> None:
    if response.ok:
        return
    try:
        detail = canonical_text(response.text[:1000])
    except (OSError, UnicodeError):
        detail = "response body unavailable"
    message = f"{source} HTTP {response.status_code} for {redact_url(response.url)}"
    if detail:
        message += f"; response: {redact_sensitive_text(detail)}"
    raise requests.HTTPError(message, response=response)


def batched(values: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    for start in range(0, len(values), size):
        yield values[start : start + size]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_lines(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def make_user_agent(contact_email: str | None) -> str:
    contact = contact_email or "contact-not-configured"
    return f"AlphaFoldResearchFulltext/1.0 (mailto:{contact})"


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    attempts: int = 5,
    retry_statuses: set[int] | None = None,
    timeout: tuple[float, float] = (20.0, 120.0),
    **kwargs: Any,
) -> requests.Response:
    statuses = retry_statuses or {408, 425, 429, 500, 502, 503, 504}
    last_response: requests.Response | None = None
    for attempt in range(attempts):
        try:
            response = session.request(method, url, timeout=timeout, **kwargs)
            last_response = response
            if response.status_code not in statuses:
                return response
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = min(float(retry_after), 60.0)
            else:
                delay = min(2**attempt, 30)
        except requests.RequestException:
            if attempt == attempts - 1:
                raise
            delay = min(2**attempt, 30)
        time.sleep(delay)
    assert last_response is not None
    return last_response


def connect_db(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=60000")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS works (
            work_id TEXT PRIMARY KEY,
            openalex_url TEXT NOT NULL,
            doi TEXT,
            title TEXT,
            abstract TEXT,
            abstract_source TEXT,
            abstract_updated_at TEXT,
            abstract_sha256 TEXT,
            publication_year INTEGER,
            work_type TEXT,
            af_usage_level TEXT,
            domain_labels TEXT,
            in_current_corpus INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 50,

            openalex_status TEXT NOT NULL DEFAULT 'pending',
            openalex_checked_at TEXT,
            has_content_pdf INTEGER,
            has_content_grobid_xml INTEGER,
            openalex_pdf_url TEXT,
            openalex_tei_url TEXT,
            best_oa_landing_url TEXT,
            best_oa_pdf_url TEXT,
            best_oa_license TEXT,
            best_oa_version TEXT,

            europepmc_status TEXT NOT NULL DEFAULT 'pending',
            europepmc_checked_at TEXT,
            pmid TEXT,
            pmcid TEXT,
            epmc_in_fulltext INTEGER,
            epmc_is_oa INTEGER,
            epmc_has_pdf INTEGER,
            epmc_xml_url TEXT,
            epmc_efetch_xml_url TEXT,
            epmc_pdf_url TEXT,
            epmc_landing_url TEXT,
            epmc_license TEXT,
            epmc_access_class TEXT,

            unpaywall_status TEXT NOT NULL DEFAULT 'pending',
            unpaywall_checked_at TEXT,
            unpaywall_is_oa INTEGER,
            unpaywall_oa_status TEXT,
            unpaywall_pdf_url TEXT,
            unpaywall_landing_url TEXT,
            unpaywall_license TEXT,
            unpaywall_version TEXT,
            unpaywall_host_type TEXT,

            fetch_status TEXT NOT NULL DEFAULT 'pending',
            fetched_source TEXT,
            fetched_format TEXT,
            fetched_source_url TEXT,
            fetched_access_class TEXT,
            fetched_license TEXT,
            local_path TEXT,
            content_sha256 TEXT,
            content_bytes INTEGER,
            fetched_at TEXT,
            fetch_error TEXT,

            parse_status TEXT NOT NULL DEFAULT 'pending',
            parsed_at TEXT,
            parsed_document_path TEXT,
            context_path TEXT,
            context_count INTEGER,
            parse_error TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fetch_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT NOT NULL,
            source TEXT NOT NULL,
            url TEXT,
            attempted_at TEXT NOT NULL,
            outcome TEXT NOT NULL,
            http_status INTEGER,
            content_type TEXT,
            bytes INTEGER,
            access_class TEXT,
            license TEXT,
            error TEXT,
            FOREIGN KEY(work_id) REFERENCES works(work_id)
        );

        CREATE TABLE IF NOT EXISTS oa_provider_checks (
            work_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            checked_at TEXT,
            result_count INTEGER NOT NULL DEFAULT 0,
            response_sha256 TEXT,
            error TEXT,
            PRIMARY KEY(work_id, provider),
            FOREIGN KEY(work_id) REFERENCES works(work_id)
        );

        CREATE TABLE IF NOT EXISTS oa_recovery_candidates (
            candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            url TEXT NOT NULL,
            expected_format TEXT NOT NULL CHECK(expected_format IN ('pdf', 'xml')),
            license TEXT,
            version TEXT,
            landing_url TEXT,
            match_method TEXT NOT NULL,
            access_evidence TEXT,
            response_sha256 TEXT,
            status TEXT NOT NULL DEFAULT 'available',
            discovered_at TEXT NOT NULL,
            last_attempted_at TEXT,
            last_outcome TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(work_id, provider, url),
            FOREIGN KEY(work_id) REFERENCES works(work_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_works_priority ON works(priority, work_id);
        CREATE INDEX IF NOT EXISTS idx_works_openalex_status ON works(openalex_status);
        CREATE INDEX IF NOT EXISTS idx_works_europepmc_status ON works(europepmc_status);
        CREATE INDEX IF NOT EXISTS idx_works_unpaywall_status ON works(unpaywall_status);
        CREATE INDEX IF NOT EXISTS idx_works_fetch_status ON works(fetch_status);
        CREATE INDEX IF NOT EXISTS idx_works_parse_status ON works(parse_status);
        CREATE INDEX IF NOT EXISTS idx_fetch_attempts_work_id ON fetch_attempts(work_id);
        CREATE INDEX IF NOT EXISTS idx_oa_provider_checks_status
            ON oa_provider_checks(provider, status, work_id);
        CREATE INDEX IF NOT EXISTS idx_oa_recovery_candidates_work
            ON oa_recovery_candidates(work_id, status, provider);
        """
    )
    work_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(works)").fetchall()
    }
    if "in_current_corpus" not in work_columns:
        connection.execute(
            "ALTER TABLE works ADD COLUMN in_current_corpus INTEGER NOT NULL DEFAULT 1"
        )
    work_column_migrations = {
        "abstract_source": "TEXT",
        "abstract_updated_at": "TEXT",
        "abstract_sha256": "TEXT",
        "epmc_pdf_url": "TEXT",
        "epmc_efetch_xml_url": "TEXT",
        "epmc_landing_url": "TEXT",
        "epmc_license": "TEXT",
        "epmc_access_class": "TEXT",
        "fetched_source_url": "TEXT",
        "fetched_access_class": "TEXT",
        "fetched_license": "TEXT",
    }
    for column, definition in work_column_migrations.items():
        if column not in work_columns:
            connection.execute(f"ALTER TABLE works ADD COLUMN {column} {definition}")
    # PMC E-Utilities URLs are deterministic from an already verified PMCID.
    # Backfill them locally so OA records also have an official fallback when
    # Europe PMC's fullTextXML endpoint is temporarily missing or stale.
    pmc_rows = connection.execute(
        """
        SELECT work_id, pmcid FROM works
        WHERE epmc_in_fulltext=1
          AND NULLIF(TRIM(pmcid), '') IS NOT NULL
          AND epmc_efetch_xml_url IS NULL
        """
    ).fetchall()
    connection.executemany(
        "UPDATE works SET epmc_efetch_xml_url=? WHERE work_id=?",
        [
            (f"{NCBI_EUTILS}/efetch.fcgi?db=pmc&id={pmcid}&retmode=xml", row["work_id"])
            for row in pmc_rows
            if (pmcid := str(row["pmcid"]).strip()).upper().startswith("PMC")
            and pmcid[3:].isdigit()
        ],
    )
    attempt_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(fetch_attempts)").fetchall()
    }
    for column in ("access_class", "license"):
        if column not in attempt_columns:
            connection.execute(f"ALTER TABLE fetch_attempts ADD COLUMN {column} TEXT")
    # Pre-v3 abstracts have no provider-level provenance. Mark them explicitly as
    # legacy rather than guessing which upstream service supplied them.
    connection.execute(
        """
        UPDATE works SET
            abstract_source=COALESCE(abstract_source, 'legacy_manifest_unattributed'),
            abstract_updated_at=COALESCE(abstract_updated_at, updated_at)
        WHERE NULLIF(TRIM(abstract), '') IS NOT NULL
        """
    )
    missing_abstract_hashes = connection.execute(
        """
        SELECT work_id, abstract FROM works
        WHERE NULLIF(TRIM(abstract), '') IS NOT NULL AND abstract_sha256 IS NULL
        """
    ).fetchall()
    connection.executemany(
        "UPDATE works SET abstract_sha256=? WHERE work_id=?",
        [
            (hashlib.sha256(row["abstract"].encode("utf-8")).hexdigest(), row["work_id"])
            for row in missing_abstract_hashes
        ],
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_works_current_priority "
        "ON works(in_current_corpus, priority, work_id)"
    )
    set_setting(connection, "schema_version", SCHEMA_VERSION)
    connection.commit()


def set_setting(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, value, utc_now()),
    )


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def canonical_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None
