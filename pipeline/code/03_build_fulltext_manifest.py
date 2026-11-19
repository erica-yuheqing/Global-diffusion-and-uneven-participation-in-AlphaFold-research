#!/usr/bin/env python3
"""Build and enrich a resumable full-text availability manifest.

This script never downloads article bodies. It creates the candidate manifest and
queries metadata endpoints only. The resulting SQLite database is the shared state
used by the fetch and extraction stages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

from fulltext_pipeline.common import (
    DEFAULT_DB_PATH,
    DEFAULT_WORKS_DIR,
    EUROPE_PMC_API,
    NCBI_EUTILS,
    OPENALEX_API,
    OPENALEX_CONTENT,
    UNPAYWALL_API,
    batched,
    connect_db,
    first_nonempty,
    json_dumps,
    make_user_agent,
    normalize_doi,
    normalize_openalex_id,
    raise_for_status_redacted,
    redact_sensitive_text,
    request_with_retry,
    set_setting,
    sha256_lines,
    utc_now,
)


OPENALEX_SELECT = ",".join(
    [
        "id",
        "doi",
        "has_content",
        "best_oa_location",
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create/update manifest from local Parquet")
    init_parser.add_argument("--works-dir", type=Path, default=DEFAULT_WORKS_DIR)
    init_parser.add_argument(
        "--priority-file",
        type=Path,
        help="Optional CSV/JSONL/text file containing work_id values to set to priority 0",
    )

    enrich_parser = subparsers.add_parser("enrich", help="Query metadata providers")
    enrich_parser.add_argument(
        "--source",
        choices=["openalex", "europepmc", "unpaywall", "all"],
        default="all",
    )
    enrich_parser.add_argument("--limit", type=int, help="Maximum rows per provider")
    enrich_parser.add_argument("--priority-max", type=int, default=100)
    enrich_parser.add_argument(
        "--work-id",
        action="append",
        default=[],
        help="Restrict enrichment to an exact OpenAlex work ID; repeat as needed",
    )
    enrich_parser.add_argument(
        "--missing-abstract-only",
        action="store_true",
        help="Europe PMC only: select rows whose manifest abstract is blank",
    )
    enrich_parser.add_argument(
        "--refresh-abstract",
        action="store_true",
        help="Europe PMC only: re-query completed rows and keep a longer official abstract",
    )
    retry_group = enrich_parser.add_mutually_exclusive_group()
    retry_group.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry provider requests previously marked error",
    )
    retry_group.add_argument("--force", action="store_true", help="Re-query completed rows")
    enrich_parser.add_argument("--workers", type=int, default=8, help="Unpaywall worker count")
    enrich_parser.add_argument(
        "--openalex-api-key",
        default=os.getenv("OPENALEX_API_KEY"),
        help="Defaults to OPENALEX_API_KEY",
    )
    enrich_parser.add_argument(
        "--email",
        default=os.getenv("UNPAYWALL_EMAIL") or os.getenv("CONTACT_EMAIL"),
        help="Required for Unpaywall; defaults to UNPAYWALL_EMAIL or CONTACT_EMAIL",
    )

    export_parser = subparsers.add_parser("export", help="Export manifest for inspection")
    export_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DB_PATH.parent / "fulltext_manifest.parquet",
    )
    export_parser.add_argument("--format", choices=["parquet", "csv", "jsonl"], default="parquet")

    subparsers.add_parser("summary", help="Print manifest coverage counts")
    return parser.parse_args()


def priority_for_usage(usage: str | None) -> int:
    priorities = {
        "citation_only": 20,
        "direct_use": 30,
        "database_or_resource_use": 30,
        "mention_only": 40,
        "benchmark_or_method_discussion": 40,
    }
    return priorities.get(usage or "", 50)


def read_priority_ids(path: Path | None) -> set[str]:
    if not path:
        return set()
    suffix = path.suffix.lower()
    values: list[str] = []
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "work_id" not in reader.fieldnames:
                raise ValueError("Priority CSV must contain a work_id column")
            values = [row.get("work_id", "") for row in reader]
    elif suffix in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    values.append(record.get("work_id") or record.get("id") or "")
    else:
        values = path.read_text(encoding="utf-8").splitlines()
    return {work_id for value in values if (work_id := normalize_openalex_id(value))}


def initialize_manifest(connection: sqlite3.Connection, works_dir: Path, priority_file: Path | None) -> None:
    import pandas as pd
    import pyarrow.dataset as ds

    if not works_dir.exists():
        raise FileNotFoundError(f"Works directory does not exist: {works_dir}")
    dataset = ds.dataset(works_dir, format="parquet")
    columns = [
        "work_id",
        "doi",
        "title",
        "abstract",
        "publication_year",
        "type",
        "domain_label",
        "is_alphafold_related",
        "af_usage_level",
    ]
    table = dataset.to_table(
        columns=columns,
        filter=ds.field("is_alphafold_related") == True,  # noqa: E712
    )
    frame = table.to_pandas()
    frame["work_id"] = frame["work_id"].map(normalize_openalex_id)
    frame = frame[frame["work_id"].notna()].copy()
    frame["doi"] = frame["doi"].map(normalize_doi)
    frame["abstract_length"] = frame["abstract"].fillna("").astype(str).str.len()
    domains = (
        frame.groupby("work_id")["domain_label"]
        .agg(
            lambda values: "|".join(
                sorted({str(value).strip() for value in values if pd.notna(value) and str(value).strip()})
            )
        )
        .to_dict()
    )
    frame = frame.sort_values(["work_id", "abstract_length"], ascending=[True, False])
    frame = frame.drop_duplicates("work_id", keep="first")
    frame = frame.astype(object).where(pd.notna(frame), None)
    priority_ids = read_priority_ids(priority_file)
    now = utc_now()
    connection.execute("UPDATE works SET in_current_corpus=0")

    rows = []
    for record in frame.to_dict(orient="records"):
        work_id = record["work_id"]
        usage = record.get("af_usage_level")
        priority = 0 if work_id in priority_ids else priority_for_usage(usage)
        abstract = record.get("abstract")
        abstract = str(abstract).strip() if abstract is not None and str(abstract).strip() else None
        rows.append(
            (
                work_id,
                f"https://openalex.org/{work_id}",
                record.get("doi"),
                record.get("title"),
                abstract,
                "local_candidate_dataset" if abstract else None,
                now if abstract else None,
                hashlib.sha256(abstract.encode("utf-8")).hexdigest() if abstract else None,
                record.get("publication_year"),
                record.get("type"),
                usage,
                domains.get(work_id, ""),
                priority,
                now,
            )
        )

    connection.executemany(
        """
        INSERT INTO works(
            work_id, openalex_url, doi, title, abstract,
            abstract_source, abstract_updated_at, abstract_sha256, publication_year,
            work_type, af_usage_level, domain_labels, in_current_corpus, priority, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(work_id) DO UPDATE SET
            openalex_url=excluded.openalex_url,
            doi=COALESCE(excluded.doi, works.doi),
            title=COALESCE(excluded.title, works.title),
            abstract=CASE
                WHEN length(COALESCE(excluded.abstract, '')) > length(COALESCE(works.abstract, ''))
                THEN excluded.abstract ELSE works.abstract END,
            abstract_source=CASE
                WHEN length(COALESCE(excluded.abstract, '')) > length(COALESCE(works.abstract, ''))
                THEN excluded.abstract_source ELSE works.abstract_source END,
            abstract_updated_at=CASE
                WHEN length(COALESCE(excluded.abstract, '')) > length(COALESCE(works.abstract, ''))
                THEN excluded.abstract_updated_at ELSE works.abstract_updated_at END,
            abstract_sha256=CASE
                WHEN length(COALESCE(excluded.abstract, '')) > length(COALESCE(works.abstract, ''))
                THEN excluded.abstract_sha256 ELSE works.abstract_sha256 END,
            publication_year=COALESCE(excluded.publication_year, works.publication_year),
            work_type=COALESCE(excluded.work_type, works.work_type),
            af_usage_level=COALESCE(excluded.af_usage_level, works.af_usage_level),
            domain_labels=excluded.domain_labels,
            in_current_corpus=1,
            priority=excluded.priority,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    connection.execute(
        """
        UPDATE works SET
            europepmc_status=CASE
                WHEN doi IS NULL OR doi='' THEN 'not_applicable_no_doi'
                WHEN europepmc_status='not_applicable_no_doi' THEN 'pending'
                ELSE europepmc_status END,
            unpaywall_status=CASE
                WHEN doi IS NULL OR doi='' THEN 'not_applicable_no_doi'
                WHEN unpaywall_status='not_applicable_no_doi' THEN 'pending'
                ELSE unpaywall_status END
        WHERE in_current_corpus=1
        """
    )
    work_ids = sorted(row[0] for row in rows)
    set_setting(connection, "candidate_count", str(len(work_ids)))
    set_setting(connection, "candidate_work_id_sha256", sha256_lines(work_ids))
    set_setting(connection, "candidate_source", str(works_dir.resolve()))
    set_setting(connection, "candidate_initialized_at", now)
    connection.commit()
    print(f"Manifest initialized: {len(work_ids):,} unique AlphaFold candidates")
    print(f"Candidate fingerprint: {sha256_lines(work_ids)}")


def pending_rows(
    connection: sqlite3.Connection,
    status_column: str,
    *,
    limit: int | None,
    force: bool,
    retry_failed: bool,
    priority_max: int,
    require_doi: bool = False,
    work_ids: list[str] | None = None,
    missing_abstract_only: bool = False,
) -> list[sqlite3.Row]:
    allowed_columns = {"openalex_status", "europepmc_status", "unpaywall_status"}
    if status_column not in allowed_columns:
        raise ValueError(f"Unsupported status column: {status_column}")
    clauses = ["in_current_corpus=1", "priority <= ?"]
    params: list[Any] = [priority_max]
    if force:
        pass
    elif retry_failed:
        clauses.append(f"{status_column} IN ('pending', 'error')")
    else:
        clauses.append(f"{status_column} = 'pending'")
    if require_doi:
        clauses.append("doi IS NOT NULL AND doi <> ''")
    if work_ids:
        clauses.append("work_id IN (" + ",".join("?" for _ in work_ids) + ")")
        params.extend(work_ids)
    if missing_abstract_only:
        clauses.append("NULLIF(TRIM(abstract), '') IS NULL")
    sql = f"SELECT * FROM works WHERE {' AND '.join(clauses)} ORDER BY priority, work_id"  # noqa: S608
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return connection.execute(sql, params).fetchall()


def enrich_openalex(
    connection: sqlite3.Connection,
    *,
    api_key: str | None,
    email: str | None,
    limit: int | None,
    force: bool,
    retry_failed: bool,
    priority_max: int,
    work_ids: list[str] | None = None,
) -> None:
    rows = pending_rows(
        connection,
        "openalex_status",
        limit=limit,
        force=force,
        retry_failed=retry_failed,
        priority_max=priority_max,
        work_ids=work_ids,
    )
    if not rows:
        print("OpenAlex: no rows to enrich")
        return
    session = requests.Session()
    session.headers["User-Agent"] = make_user_agent(email)
    for batch in tqdm(list(batched(rows, 100)), desc="OpenAlex metadata", unit="batch"):
        batch_by_id = {row["work_id"]: row for row in batch}
        params = {
            "filter": "ids.openalex:" + "|".join(batch_by_id),
            "per_page": 100,
            "select": OPENALEX_SELECT,
        }
        if api_key:
            params["api_key"] = api_key
        checked_at = utc_now()
        try:
            response = request_with_retry(session, "GET", f"{OPENALEX_API}/works", params=params)
            raise_for_status_redacted(response, "OpenAlex")
            records = response.json().get("results", [])
        except (requests.RequestException, ValueError) as exc:
            connection.executemany(
                "UPDATE works SET openalex_status='error', updated_at=? WHERE work_id=?",
                [(checked_at, work_id) for work_id in batch_by_id],
            )
            connection.commit()
            print(f"OpenAlex batch failed: {redact_sensitive_text(exc)}", file=sys.stderr)
            continue

        returned: set[str] = set()
        for record in records:
            work_id = normalize_openalex_id(record.get("id"))
            if not work_id or work_id not in batch_by_id:
                continue
            returned.add(work_id)
            has_content = record.get("has_content") or {}
            best_oa = record.get("best_oa_location") or {}
            has_pdf = bool(has_content.get("pdf"))
            has_xml = bool(has_content.get("grobid_xml"))
            pdf_url = f"{OPENALEX_CONTENT}/{work_id}.pdf" if has_pdf else None
            xml_url = f"{OPENALEX_CONTENT}/{work_id}.grobid-xml" if has_xml else None
            doi = normalize_doi(record.get("doi"))
            connection.execute(
                """
                UPDATE works SET
                    doi=COALESCE(?, doi),
                    openalex_status='found',
                    openalex_checked_at=?,
                    has_content_pdf=?,
                    has_content_grobid_xml=?,
                    openalex_pdf_url=?,
                    openalex_tei_url=?,
                    best_oa_landing_url=?,
                    best_oa_pdf_url=?,
                    best_oa_license=?,
                    best_oa_version=?,
                    updated_at=?
                WHERE work_id=?
                """,
                (
                    doi,
                    checked_at,
                    int(has_pdf),
                    int(has_xml),
                    pdf_url,
                    xml_url,
                    best_oa.get("landing_page_url"),
                    best_oa.get("pdf_url"),
                    best_oa.get("license"),
                    best_oa.get("version"),
                    checked_at,
                    work_id,
                ),
            )
        missing = set(batch_by_id) - returned
        connection.executemany(
            """
            UPDATE works SET openalex_status='not_found', openalex_checked_at=?, updated_at=?
            WHERE work_id=?
            """,
            [(checked_at, checked_at, work_id) for work_id in missing],
        )
        connection.commit()


def choose_epmc_record(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return candidate
    current_score = sum(
        [
            bool(current.get("pmcid")),
            current.get("isOpenAccess") == "Y",
            current.get("inEPMC") == "Y",
        ]
    )
    candidate_score = sum(
        [
            bool(candidate.get("pmcid")),
            candidate.get("isOpenAccess") == "Y",
            candidate.get("inEPMC") == "Y",
        ]
    )
    return candidate if candidate_score > current_score else current


def clean_epmc_abstract(value: Any) -> str | None:
    """Normalize Europe PMC's trusted abstract field without retaining markup."""
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split()).strip()
    return text or None


def epmc_fulltext_urls(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return official free-to-read Europe PMC landing and direct PDF URLs."""
    items = (record.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    if isinstance(items, dict):
        items = [items]
    landing_url: str | None = None
    pdf_url: str | None = None
    for item in items:
        if not isinstance(item, dict) or item.get("availabilityCode") != "F":
            continue
        if str(item.get("site") or "").casefold() != "europe_pmc":
            continue
        url = str(item.get("url") or "").strip() or None
        style = str(item.get("documentStyle") or "").casefold()
        if url and style == "pdf" and pdf_url is None:
            pdf_url = url
        elif url and style == "html" and landing_url is None:
            landing_url = url
    pmcid = str(record.get("pmcid") or "").strip()
    if not landing_url and pmcid:
        landing_url = f"https://europepmc.org/articles/{pmcid}"
    return landing_url, pdf_url


def enrich_europepmc(
    connection: sqlite3.Connection,
    *,
    email: str | None,
    limit: int | None,
    force: bool,
    retry_failed: bool,
    priority_max: int,
    work_ids: list[str] | None = None,
    missing_abstract_only: bool = False,
    refresh_abstract: bool = False,
) -> None:
    rows = pending_rows(
        connection,
        "europepmc_status",
        limit=limit,
        force=force or refresh_abstract,
        retry_failed=retry_failed,
        priority_max=priority_max,
        require_doi=True,
        work_ids=work_ids,
        missing_abstract_only=missing_abstract_only,
    )
    if not rows:
        print("Europe PMC: no DOI rows to enrich")
        return
    session = requests.Session()
    session.headers["User-Agent"] = make_user_agent(email)
    for batch in tqdm(list(batched(rows, 20)), desc="Europe PMC metadata", unit="batch"):
        batch_by_doi = {normalize_doi(row["doi"]): row for row in batch}
        query = " OR ".join(f'DOI:"{doi}"' for doi in batch_by_doi if doi)
        params = {"query": query, "format": "json", "resultType": "core", "pageSize": 100}
        if email:
            params["email"] = email
        checked_at = utc_now()
        try:
            response = request_with_retry(
                session,
                "GET",
                f"{EUROPE_PMC_API}/search",
                params=params,
            )
            raise_for_status_redacted(response, "Europe PMC")
            records = response.json().get("resultList", {}).get("result", [])
        except (requests.RequestException, ValueError) as exc:
            connection.executemany(
                "UPDATE works SET europepmc_status='error', updated_at=? WHERE work_id=?",
                [(checked_at, row["work_id"]) for row in batch],
            )
            connection.commit()
            print(f"Europe PMC batch failed: {redact_sensitive_text(exc)}", file=sys.stderr)
            continue

        found: dict[str, dict[str, Any]] = {}
        for record in records:
            doi = normalize_doi(record.get("doi"))
            if doi in batch_by_doi:
                found[doi] = choose_epmc_record(found.get(doi), record)

        for doi, row in batch_by_doi.items():
            record = found.get(doi)
            if not record:
                connection.execute(
                    """
                    UPDATE works SET europepmc_status='no_match', europepmc_checked_at=?, updated_at=?
                    WHERE work_id=?
                    """,
                    (checked_at, checked_at, row["work_id"]),
                )
                continue
            pmcid = record.get("pmcid")
            is_oa = record.get("isOpenAccess") == "Y"
            in_fulltext = record.get("inEPMC") == "Y"
            xml_url = f"{EUROPE_PMC_API}/{pmcid}/fullTextXML" if pmcid and is_oa else None
            efetch_xml_url = (
                f"{NCBI_EUTILS}/efetch.fcgi?db=pmc&id={pmcid}&retmode=xml"
                if pmcid and in_fulltext
                else None
            )
            landing_url, pdf_url = epmc_fulltext_urls(record)
            abstract = clean_epmc_abstract(record.get("abstractText"))
            existing_abstract = str(row["abstract"] or "").strip()
            abstract_update = abstract if abstract and len(abstract) > len(existing_abstract) else None
            abstract_digest = (
                hashlib.sha256(abstract_update.encode("utf-8")).hexdigest()
                if abstract_update
                else None
            )
            if xml_url:
                status = "oa_xml"
            elif in_fulltext:
                status = "fulltext_not_oa"
            else:
                status = "metadata_only"
            if xml_url:
                access_class = "oa_structured_xml"
            elif pdf_url and is_oa:
                access_class = "oa_pdf"
            elif efetch_xml_url or pdf_url:
                access_class = "free_to_read_non_oa"
            elif in_fulltext:
                access_class = "landing_page_only"
            else:
                access_class = "metadata_only"
            connection.execute(
                """
                UPDATE works SET
                    abstract=COALESCE(?, abstract),
                    abstract_source=CASE WHEN ? IS NOT NULL
                        THEN 'europe_pmc_rest_core' ELSE abstract_source END,
                    abstract_updated_at=CASE WHEN ? IS NOT NULL
                        THEN ? ELSE abstract_updated_at END,
                    abstract_sha256=COALESCE(?, abstract_sha256),
                    europepmc_status=?,
                    europepmc_checked_at=?,
                    pmid=?, pmcid=?, epmc_in_fulltext=?, epmc_is_oa=?, epmc_has_pdf=?,
                    epmc_xml_url=?, epmc_efetch_xml_url=?, epmc_pdf_url=?,
                    epmc_landing_url=?, epmc_license=?,
                    epmc_access_class=?, updated_at=?
                WHERE work_id=?
                """,
                (
                    abstract_update,
                    abstract_update,
                    abstract_update,
                    checked_at,
                    abstract_digest,
                    status,
                    checked_at,
                    record.get("pmid"),
                    pmcid,
                    int(in_fulltext),
                    int(is_oa),
                    int(record.get("hasPDF") == "Y"),
                    xml_url,
                    efetch_xml_url,
                    pdf_url,
                    landing_url,
                    record.get("license"),
                    access_class,
                    checked_at,
                    row["work_id"],
                ),
            )
        connection.commit()


_thread_local = threading.local()


def thread_session(email: str | None) -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = make_user_agent(email)
        _thread_local.session = session
    return session


def fetch_unpaywall_record(row: sqlite3.Row, email: str) -> dict[str, Any]:
    doi = normalize_doi(row["doi"])
    assert doi is not None
    checked_at = utc_now()
    try:
        response = request_with_retry(
            thread_session(email),
            "GET",
            f"{UNPAYWALL_API}/{doi}",
            params={"email": email},
        )
        if response.status_code == 404:
            return {"work_id": row["work_id"], "status": "no_match", "checked_at": checked_at}
        raise_for_status_redacted(response, "Unpaywall")
        record = response.json()
        best = record.get("best_oa_location") or {}
        return {
            "work_id": row["work_id"],
            "status": "oa" if record.get("is_oa") else "closed",
            "checked_at": checked_at,
            "is_oa": int(bool(record.get("is_oa"))),
            "oa_status": record.get("oa_status"),
            "pdf_url": best.get("url_for_pdf"),
            "landing_url": first_nonempty(best.get("url_for_landing_page"), best.get("url")),
            "license": best.get("license"),
            "version": best.get("version"),
            "host_type": best.get("host_type"),
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "work_id": row["work_id"],
            "status": "error",
            "checked_at": checked_at,
            "error": redact_sensitive_text(exc),
        }


def enrich_unpaywall(
    connection: sqlite3.Connection,
    *,
    email: str | None,
    limit: int | None,
    force: bool,
    retry_failed: bool,
    priority_max: int,
    workers: int,
    work_ids: list[str] | None = None,
) -> None:
    if not email:
        raise ValueError("Unpaywall requires --email or UNPAYWALL_EMAIL")
    rows = pending_rows(
        connection,
        "unpaywall_status",
        limit=limit,
        force=force,
        retry_failed=retry_failed,
        priority_max=priority_max,
        require_doi=True,
        work_ids=work_ids,
    )
    if not rows:
        print("Unpaywall: no DOI rows to enrich")
        return
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        results = executor.map(lambda row: fetch_unpaywall_record(row, email), rows)
        for result in tqdm(results, total=len(rows), desc="Unpaywall metadata", unit="work"):
            connection.execute(
                """
                UPDATE works SET
                    unpaywall_status=?, unpaywall_checked_at=?, unpaywall_is_oa=?,
                    unpaywall_oa_status=?, unpaywall_pdf_url=?, unpaywall_landing_url=?,
                    unpaywall_license=?, unpaywall_version=?, unpaywall_host_type=?, updated_at=?
                WHERE work_id=?
                """,
                (
                    result["status"],
                    result["checked_at"],
                    result.get("is_oa"),
                    result.get("oa_status"),
                    result.get("pdf_url"),
                    result.get("landing_url"),
                    result.get("license"),
                    result.get("version"),
                    result.get("host_type"),
                    result["checked_at"],
                    result["work_id"],
                ),
            )
            if result["status"] == "error":
                print(
                    f"Unpaywall error for {result['work_id']}: {result.get('error')}",
                    file=sys.stderr,
                )
        connection.commit()


def export_manifest(connection: sqlite3.Connection, output: Path, output_format: str) -> None:
    import pandas as pd

    output.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.read_sql_query(
        "SELECT * FROM works WHERE in_current_corpus=1 ORDER BY priority, work_id",
        connection,
    )
    if output_format == "parquet":
        frame.to_parquet(output, index=False)
    elif output_format == "csv":
        frame.to_csv(output, index=False)
    else:
        frame = frame.astype(object).where(pd.notna(frame), None)
        with output.open("w", encoding="utf-8") as handle:
            for record in frame.to_dict(orient="records"):
                handle.write(json_dumps(record) + "\n")
    print(f"Exported {len(frame):,} rows to {output}")


def print_summary(connection: sqlite3.Connection) -> None:
    queries = {
        "works": "SELECT COUNT(*) FROM works WHERE in_current_corpus=1",
        "with_doi": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND doi IS NOT NULL AND doi <> ''
        """,
        "with_abstract": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND abstract IS NOT NULL AND abstract <> ''
        """,
        "abstract_from_epmc": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND abstract_source='europe_pmc_rest_core'
        """,
        "epmc_oa_xml": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND epmc_xml_url IS NOT NULL
        """,
        "epmc_free_pdf": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND epmc_pdf_url IS NOT NULL
        """,
        "pmc_efetch_xml": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND epmc_efetch_xml_url IS NOT NULL
        """,
        "epmc_free_non_oa_pdf": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND epmc_pdf_url IS NOT NULL AND epmc_is_oa=0
        """,
        "openalex_tei": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND has_content_grobid_xml=1
        """,
        "unpaywall_pdf": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND unpaywall_pdf_url IS NOT NULL
        """,
        "openalex_oa_pdf": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND best_oa_pdf_url IS NOT NULL
        """,
        "openalex_cached_pdf": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND has_content_pdf=1
        """,
        "oa_recovery_works": """
            SELECT COUNT(DISTINCT candidate.work_id)
            FROM oa_recovery_candidates AS candidate
            JOIN works AS work ON work.work_id=candidate.work_id
            WHERE work.in_current_corpus=1
              AND candidate.status IN ('available', 'downloaded')
        """,
        "oa_recovery_candidates": """
            SELECT COUNT(*)
            FROM oa_recovery_candidates AS candidate
            JOIN works AS work ON work.work_id=candidate.work_id
            WHERE work.in_current_corpus=1
              AND candidate.status IN ('available', 'downloaded')
        """,
        "fetch_success": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND fetch_status='success'
        """,
        "parse_success": """
            SELECT COUNT(*) FROM works WHERE in_current_corpus=1 AND parse_status='success'
        """,
        "parse_with_contexts": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND parse_status='success' AND context_count > 0
        """,
        "parse_without_contexts": """
            SELECT COUNT(*) FROM works
            WHERE in_current_corpus=1 AND parse_status='success'
              AND COALESCE(context_count, 0) = 0
        """,
        "evidence_contexts": """
            SELECT COALESCE(SUM(context_count), 0) FROM works
            WHERE in_current_corpus=1 AND parse_status='success'
        """,
        "openalex_paid_attempts": """
            SELECT COUNT(*) FROM fetch_attempts AS attempt
            JOIN works AS work ON work.work_id=attempt.work_id
            WHERE work.in_current_corpus=1
              AND attempt.source IN ('openalex_tei', 'openalex_pdf')
              AND attempt.outcome NOT LIKE 'skipped_%'
        """,
    }
    for label, query in queries.items():
        count = connection.execute(query).fetchone()[0]
        print(f"{label:24s} {count:>8,}")
    print("\nAF usage levels")
    for row in connection.execute(
        """
        SELECT af_usage_level, COUNT(*) AS n FROM works
        WHERE in_current_corpus=1
        GROUP BY af_usage_level ORDER BY n DESC
        """
    ):
        print(f"{str(row['af_usage_level']):24s} {row['n']:>8,}")
    print("\nProvider statuses")
    for column in [
        "openalex_status",
        "europepmc_status",
        "unpaywall_status",
        "fetch_status",
        "parse_status",
        "fetched_source",
        "abstract_source",
        "epmc_access_class",
        "fetched_access_class",
    ]:
        values = connection.execute(
            f"""SELECT {column}, COUNT(*) AS n FROM works
            WHERE in_current_corpus=1 GROUP BY {column} ORDER BY n DESC"""  # noqa: S608
        ).fetchall()
        print(column, {row[column]: row["n"] for row in values})
    print("\nOA recovery provider checks")
    check_rows = connection.execute(
        """
        SELECT check_row.provider, check_row.status, COUNT(*) AS n
        FROM oa_provider_checks AS check_row
        JOIN works AS work ON work.work_id=check_row.work_id
        WHERE work.in_current_corpus=1
        GROUP BY check_row.provider, check_row.status
        ORDER BY check_row.provider, n DESC
        """
    ).fetchall()
    checks: dict[str, dict[str, int]] = {}
    for row in check_rows:
        checks.setdefault(row["provider"], {})[row["status"]] = row["n"]
    for provider, values in checks.items():
        print(provider, values)
    candidate_rows = connection.execute(
        """
        SELECT candidate.provider, COUNT(*) AS candidates,
               COUNT(DISTINCT candidate.work_id) AS works
        FROM oa_recovery_candidates AS candidate
        JOIN works AS work ON work.work_id=candidate.work_id
        WHERE work.in_current_corpus=1
          AND candidate.status IN ('available', 'downloaded')
        GROUP BY candidate.provider ORDER BY candidate.provider
        """
    ).fetchall()
    print(
        "oa_recovery_by_provider",
        {
            row["provider"]: {"works": row["works"], "candidates": row["candidates"]}
            for row in candidate_rows
        },
    )
    candidate_status_rows = connection.execute(
        """
        SELECT candidate.provider, candidate.status, COUNT(*) AS n
        FROM oa_recovery_candidates AS candidate
        JOIN works AS work ON work.work_id=candidate.work_id
        WHERE work.in_current_corpus=1
        GROUP BY candidate.provider, candidate.status
        ORDER BY candidate.provider, n DESC
        """
    ).fetchall()
    candidate_statuses: dict[str, dict[str, int]] = {}
    for row in candidate_status_rows:
        candidate_statuses.setdefault(row["provider"], {})[row["status"]] = row["n"]
    print("oa_candidate_statuses", candidate_statuses)


def main() -> None:
    args = parse_args()
    connection = connect_db(args.db)
    try:
        if args.command == "init":
            initialize_manifest(connection, args.works_dir, args.priority_file)
        elif args.command == "enrich":
            sources = ["openalex", "europepmc", "unpaywall"] if args.source == "all" else [args.source]
            work_ids = []
            for value in args.work_id:
                work_id = normalize_openalex_id(value)
                if not work_id:
                    raise ValueError(f"Invalid OpenAlex work ID: {value}")
                if work_id not in work_ids:
                    work_ids.append(work_id)
            if work_ids:
                known = {
                    row["work_id"]
                    for row in connection.execute(
                        "SELECT work_id FROM works WHERE work_id IN ("
                        + ",".join("?" for _ in work_ids)
                        + ")",
                        work_ids,
                    ).fetchall()
                }
                missing = [work_id for work_id in work_ids if work_id not in known]
                if missing:
                    raise ValueError("Work ID not found in manifest: " + ", ".join(missing))
            if (args.missing_abstract_only or args.refresh_abstract) and sources != ["europepmc"]:
                raise ValueError(
                    "--missing-abstract-only and --refresh-abstract require --source europepmc"
                )
            if "openalex" in sources and not args.openalex_api_key:
                raise ValueError("OpenAlex metadata enrichment requires --openalex-api-key or OPENALEX_API_KEY")
            if "openalex" in sources:
                enrich_openalex(
                    connection,
                    api_key=args.openalex_api_key,
                    email=args.email,
                    limit=args.limit,
                    force=args.force,
                    retry_failed=args.retry_failed,
                    priority_max=args.priority_max,
                    work_ids=work_ids,
                )
            if "europepmc" in sources:
                enrich_europepmc(
                    connection,
                    email=args.email,
                    limit=args.limit,
                    force=args.force,
                    retry_failed=args.retry_failed,
                    priority_max=args.priority_max,
                    work_ids=work_ids,
                    missing_abstract_only=args.missing_abstract_only,
                    refresh_abstract=args.refresh_abstract,
                )
            if "unpaywall" in sources:
                enrich_unpaywall(
                    connection,
                    email=args.email,
                    limit=args.limit,
                    force=args.force,
                    retry_failed=args.retry_failed,
                    priority_max=args.priority_max,
                    workers=args.workers,
                    work_ids=work_ids,
                )
            set_setting(connection, "metadata_last_enriched_at", utc_now())
            connection.commit()
            print_summary(connection)
        elif args.command == "export":
            output = args.output
            desired_suffix = {"parquet": ".parquet", "csv": ".csv", "jsonl": ".jsonl"}[
                args.format
            ]
            if output.suffix.lower() != desired_suffix:
                output = output.with_suffix(desired_suffix)
            export_manifest(connection, output, args.format)
        elif args.command == "summary":
            print_summary(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
