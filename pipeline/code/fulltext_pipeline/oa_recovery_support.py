"""Shared, offline safety rules for OA candidates and immutable pilot membership."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .common import normalize_openalex_id, utc_now


COHORT_SCHEMA = "af-oa-recovery-cohort-v1"
BLOCKED_OA_STATUSES = ("http_403", "http_404", "http_410", "invalid_payload")
PMC_XML_RE = re.compile(
    r"^https://www\.ebi\.ac\.uk/europepmc/webservices/rest/(PMC\d+)/fullTextXML$", re.I
)


def readonly_snapshot(path: Path) -> sqlite3.Connection:
    """Run local previews on a consistent in-memory copy, never the live DB."""
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    copy = sqlite3.connect(":memory:")
    try:
        source.backup(copy)
    except BaseException:
        copy.close()
        raise
    finally:
        source.close()
    copy.row_factory = sqlite3.Row
    return copy


def evidence_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {"previous_access_evidence": value}
    return parsed if isinstance(parsed, dict) else {"previous_access_evidence": parsed}


def pmc_xml_status(row: dict[str, Any], url: str, evidence: Any = None) -> str:
    """A PMCID/PMC landing page alone never proves OA XML availability."""
    match = PMC_XML_RE.fullmatch(url)
    if not match:
        return "needs_pmc_check"
    pmcid = match.group(1).upper()
    check = evidence_dict(evidence).get("pmc_check") or {}
    if isinstance(check, dict) and check.get("pmcid") == pmcid:
        if check.get("status") in {"available", "pmc_not_oa", "pmc_unavailable", "pmc_id_mismatch"}:
            return check["status"]
    if str(row.get("pmcid") or "").upper() != pmcid:
        return "needs_pmc_check"
    if row.get("epmc_is_oa") == 0 or row.get("europepmc_status") == "fulltext_not_oa":
        return "pmc_not_oa"
    if row.get("epmc_is_oa") == 1 and row.get("epmc_in_fulltext") == 1:
        return "available"
    return "needs_pmc_check"


def status_after_attempt(current: str, outcome: str, http_status: int | None) -> str:
    if outcome == "success" or current == "downloaded":
        return "downloaded"
    if outcome == "http_error" and http_status in {403, 404, 410}:
        return f"http_{http_status}"
    if outcome == "invalid_payload":
        return "invalid_payload"
    return current


def cohort_digest(work_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(work_ids) + "\n").encode()).hexdigest()


def load_cohort(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != COHORT_SCHEMA:
        raise ValueError("Unrecognized OA recovery cohort schema")
    ids = payload.get("work_ids")
    if not isinstance(ids, list) or not ids or not all(
        isinstance(value, str) and normalize_openalex_id(value) == value for value in ids
    ):
        raise ValueError("Cohort must contain nonempty canonical OpenAlex work IDs")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate work IDs in cohort")
    if payload.get("record_count") != len(ids) or payload.get("ordered_work_id_sha256") != cohort_digest(ids):
        raise ValueError("Cohort count/hash mismatch; do not silently change pilot membership")
    return ids


def checked_cohort(connection, providers: tuple[str, ...], expected_count: int) -> list[str]:
    sets = [
        {row[0] for row in connection.execute(
            "SELECT work_id FROM oa_provider_checks WHERE provider=?", (provider,)
        )} for provider in providers
    ]
    if not sets or any(len(ids) != expected_count or ids != sets[0] for ids in sets):
        raise ValueError(
            f"Cannot recover an unambiguous {expected_count}-work pilot: "
            "all provider check sets must have identical IDs. Use an existing lock file."
        )
    return sorted(sets[0])


def freeze_checked_cohort(connection, path: Path, providers: tuple[str, ...], expected_count: int,
                          *, dry_run: bool = False) -> list[str]:
    ids = checked_cohort(connection, providers, expected_count)
    validate_cohort_in_manifest(connection, ids)
    if path.exists():
        if load_cohort(path) != ids:
            raise ValueError("Existing cohort differs; refusing to overwrite it")
        return ids
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": COHORT_SCHEMA, "created_at_utc": utc_now(),
            "origin": "identical historical oa_provider_checks membership",
            "providers": list(providers), "record_count": len(ids),
            "ordered_work_id_sha256": cohort_digest(ids), "work_ids": ids,
        }
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return ids


def validate_cohort_in_manifest(connection, ids: list[str]) -> None:
    known = {row[0] for row in connection.execute("SELECT work_id FROM works WHERE in_current_corpus=1")}
    if not set(ids) <= known:
        raise ValueError("Cohort contains IDs absent from the current corpus; refusing to shrink the sample")
