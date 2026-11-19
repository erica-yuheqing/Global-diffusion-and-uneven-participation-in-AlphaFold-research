#!/usr/bin/env python3
"""Validate the analysis-ready final-v1 tables before any statistical analysis."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from common import (
    CONFIG_PATH,
    OUT_DIR,
    atomic_write_json,
    load_config,
    load_json,
    require_regular_file,
    sha256_file,
    sql_path,
)


MASTER = OUT_DIR / "works_analysis_master.parquet"
REVIEWED = OUT_DIR / "reviewed_candidates.parquet"
PREPARE_SUMMARY = OUT_DIR / "prepare_summary.json"
REPORT = OUT_DIR / "validation_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    require_regular_file(MASTER, "analysis master")
    require_regular_file(REVIEWED, "reviewed candidates")
    require_regular_file(PREPARE_SUMMARY, "preparation summary")
    prepare_summary = load_json(PREPARE_SUMMARY)
    blockers: list[str] = []
    warnings: list[str] = []
    connection = duckdb.connect()
    try:
        overview = connection.execute(
            f"""
            SELECT
              count(*) AS records,
              count(DISTINCT work_id) AS unique_work_ids,
              count(*) FILTER (WHERE candidate_reviewed) AS reviewed_candidates,
              count(*) FILTER (WHERE is_screen_negative_comparator) AS screen_negative_comparators,
              count(*) FILTER (WHERE work_id IS NULL OR work_id = '') AS missing_work_id,
              count(*) FILTER (WHERE publication_year IS NULL) AS missing_publication_year,
              count(*) FILTER (WHERE title IS NULL OR trim(title) = '') AS missing_title,
              count(*) FILTER (WHERE domain_count IS NULL OR domain_count = 0) AS missing_domain,
              count(*) FILTER (WHERE candidate_reviewed AND final_record_sha256 IS NULL)
                AS reviewed_missing_final_hash
            FROM read_parquet('{sql_path(MASTER)}')
            """
        ).fetchdf().iloc[0].to_dict()
        label_counts = connection.execute(
            f"""
            SELECT af_use_label, adoption_eligible, count(*) AS n
            FROM read_parquet('{sql_path(REVIEWED)}')
            GROUP BY af_use_label, adoption_eligible
            ORDER BY n DESC
            """
        ).fetchdf().to_dict(orient="records")
        expected_counts = connection.execute(
            f"""
            SELECT
              count(*) AS records,
              count(*) FILTER (WHERE af_use_label = 'yes') AS af_use_yes,
              count(*) FILTER (WHERE af_use_label = 'no') AS af_use_no,
              count(*) FILTER (WHERE af_use_label = 'uncertain') AS af_use_uncertain,
              count(*) FILTER (WHERE adoption_eligible = 'yes') AS adoption_yes,
              count(*) FILTER (WHERE adoption_eligible = 'no') AS adoption_no,
              count(*) FILTER (WHERE adoption_eligible = 'uncertain') AS adoption_uncertain,
              count(*) FILTER (WHERE observed_actions_status = 'disagreement_unadjudicated')
                AS ab_action_disagreement_unadjudicated,
              count(*) FILTER (WHERE observed_actions_status = 'not_assessed_insufficient_evidence')
                AS actions_not_assessed_insufficient_evidence
            FROM read_parquet('{sql_path(REVIEWED)}')
            """
        ).fetchdf().iloc[0].to_dict()
        allowed = connection.execute(
            f"""
            SELECT
              list(DISTINCT af_use_label ORDER BY af_use_label) AS af_use_values,
              list(DISTINCT adoption_eligible ORDER BY adoption_eligible) AS adoption_values,
              list(DISTINCT relevance_level ORDER BY relevance_level) AS relevance_values,
              list(DISTINCT evidence_level ORDER BY evidence_level) AS evidence_values
            FROM read_parquet('{sql_path(REVIEWED)}')
            """
        ).fetchdf().iloc[0].to_dict()
    finally:
        connection.close()

    if int(overview["records"]) != int(overview["unique_work_ids"]):
        blockers.append("Master table is not unique by normalized work_id")
    expected = config["expected_final_database"]
    for key, expected_value in expected.items():
        actual = int(expected_counts.get(key, -1))
        if actual != int(expected_value):
            blockers.append(f"{key}: expected {expected_value}, found {actual}")
    if int(overview["reviewed_missing_final_hash"]):
        blockers.append("Some reviewed candidates lack final_record_sha256")
    if int(overview["missing_work_id"]):
        blockers.append("Master table contains missing work IDs")
    if int(overview["missing_publication_year"]):
        warnings.append(f"Missing publication year: {int(overview['missing_publication_year']):,}")
    if int(overview["missing_title"]):
        warnings.append(f"Missing title: {int(overview['missing_title']):,}")
    if int(overview["missing_domain"]):
        warnings.append(f"No domain assignment: {int(overview['missing_domain']):,}")
    expected_allowed = {
        "af_use_values": {"no", "uncertain", "yes"},
        "adoption_values": {"no", "uncertain", "yes"},
        "relevance_values": {"R0", "R1", "R2", "R3", "R4", "RU"},
        "evidence_values": {"E0", "E1", "E2", "E3"},
    }
    for field, valid_values in expected_allowed.items():
        found = set(allowed[field])
        if not found <= valid_values:
            blockers.append(f"Unexpected {field}: {sorted(found-valid_values)}")

    report = {
        "schema_version": "af-final-analysis-validation-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reproducibility": {
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "config_path": str(CONFIG_PATH),
            "config_sha256": sha256_file(CONFIG_PATH),
        },
        "ready_for_descriptive_analysis": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "overview": {key: int(value) for key, value in overview.items()},
        "expected_count_checks": {
            key: {"expected": int(value), "actual": int(expected_counts[key])}
            for key, value in expected.items()
        },
        "label_cross_counts": [
            {
                "af_use_label": row["af_use_label"],
                "adoption_eligible": row["adoption_eligible"],
                "n": int(row["n"]),
            }
            for row in label_counts
        ],
        "allowed_value_audit": {
            key: value.tolist() if hasattr(value, "tolist") else list(value)
            for key, value in allowed.items()
        },
        "prepared_master_sha256_from_prepare_summary": prepare_summary["outputs"]
        ["works_analysis_master"]["sha256"],
    }
    atomic_write_json(REPORT, report, force=args.force)
    print(f"Master records:         {int(overview['records']):,}")
    print(f"Reviewed candidates:    {int(overview['reviewed_candidates']):,}")
    print(f"Warnings:               {len(warnings):,}")
    print(f"Blockers:               {len(blockers):,}")
    print(f"Ready:                  {not blockers}")
    print(f"Validation report:      {REPORT}")
    if blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
