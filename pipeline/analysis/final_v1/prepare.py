#!/usr/bin/env python3
"""Build an analysis-ready work table without modifying frozen source data."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from common import (
    CONFIG_PATH,
    FINAL_CSV,
    FINAL_LOCK,
    OUT_DIR,
    PROJECT_ROOT,
    WORKS_GLOB,
    atomic_write_json,
    load_config,
    require_regular_file,
    sha256_bytes,
    sha256_file,
    sql_path,
)


MASTER = OUT_DIR / "works_analysis_master.parquet"
REVIEWED = OUT_DIR / "reviewed_candidates.parquet"
SUMMARY = OUT_DIR / "prepare_summary.json"


def quote_sql_value(value: object) -> str:
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def parquet_inventory() -> tuple[list[dict[str, object]], str]:
    source_dir = WORKS_GLOB.parent
    files = sorted(source_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No source parquet files found in {source_dir}")
    rows: list[dict[str, object]] = []
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Unsafe parquet source: {path}")
        stat = path.stat()
        rows.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return rows, sha256_bytes(payload)


def refuse_existing(force: bool) -> None:
    existing = [path for path in (MASTER, REVIEWED, SUMMARY) if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Derived outputs already exist: {names}; pass --force explicitly")


def main() -> None:
    args = parse_args()
    config = load_config()
    require_regular_file(FINAL_CSV, "final database CSV")
    require_regular_file(FINAL_LOCK, "final database lock")
    inventory, inventory_sha = parquet_inventory()
    refuse_existing(args.force)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    start_year = int(config["main_period"]["start_year"])
    end_year = int(config["main_period"]["end_year"])
    excluded = config["excluded_document_types"]
    excluded_sql = ", ".join(quote_sql_value(value) for value in excluded)
    source_glob = sql_path(WORKS_GLOB)
    final_csv = sql_path(FINAL_CSV)
    master_tmp = MASTER.with_suffix(MASTER.suffix + ".part")
    reviewed_tmp = REVIEWED.with_suffix(REVIEWED.suffix + ".part")
    for path in (master_tmp, reviewed_tmp):
        if path.exists():
            path.unlink()

    connection = duckdb.connect()
    try:
        build_sql = f"""
        COPY (
          WITH source AS (
            SELECT
              regexp_extract(work_id, 'W[0-9]+', 0) AS work_id_norm,
              doi,
              title,
              abstract,
              publication_year,
              publication_date,
              cited_by_count,
              type AS work_type,
              domain_label,
              primary_topic_id,
              primary_topic_display_name,
              primary_field_id,
              primary_field_display_name,
              primary_subfield_id,
              primary_subfield_display_name,
              primary_domain_id,
              primary_domain_display_name,
              journal_or_source_id,
              journal_or_source_name,
              is_alphafold_related AS legacy_is_alphafold_related,
              af_usage_level AS legacy_af_usage_level
            FROM read_parquet('{source_glob}')
            WHERE regexp_extract(work_id, 'W[0-9]+', 0) <> ''
          ), domain_rollup AS (
            SELECT
              work_id_norm,
              string_agg(DISTINCT domain_label, '|' ORDER BY domain_label)
                FILTER (WHERE domain_label IS NOT NULL AND trim(domain_label) <> '') AS domain_labels,
              count(DISTINCT domain_label)
                FILTER (WHERE domain_label IS NOT NULL AND trim(domain_label) <> '') AS domain_count,
              bool_or(coalesce(legacy_is_alphafold_related, false)) AS legacy_screen_positive
            FROM source
            GROUP BY work_id_norm
          ), ranked AS (
            SELECT *, row_number() OVER (
              PARTITION BY work_id_norm
              ORDER BY
                (abstract IS NOT NULL AND trim(abstract) <> '') DESC,
                length(coalesce(abstract, '')) DESC,
                coalesce(cited_by_count, 0) DESC,
                publication_date DESC NULLS LAST,
                coalesce(domain_label, '')
            ) AS representative_rank
            FROM source
          ), final AS (
            SELECT * FROM read_csv_auto('{final_csv}', header=true, all_varchar=false)
          )
          SELECT
            r.work_id_norm AS work_id,
            r.doi,
            r.title,
            r.abstract,
            r.publication_year,
            r.publication_date,
            r.cited_by_count,
            r.work_type,
            d.domain_labels,
            d.domain_count,
            CASE WHEN d.domain_count > 0 THEN 1.0 / d.domain_count ELSE NULL END AS domain_fraction,
            r.primary_topic_id,
            r.primary_topic_display_name,
            r.primary_field_id,
            r.primary_field_display_name,
            r.primary_subfield_id,
            r.primary_subfield_display_name,
            r.primary_domain_id,
            r.primary_domain_display_name,
            r.journal_or_source_id,
            r.journal_or_source_name,
            d.legacy_screen_positive,
            r.legacy_af_usage_level,
            f.work_id IS NOT NULL AS candidate_reviewed,
            CASE WHEN f.work_id IS NULL THEN 'screen_negative' ELSE 'reviewed_candidate' END
              AS screening_status,
            f.evidence_tier,
            f.decision_route,
            f.source_route,
            f.primary_label,
            f.relevance_level,
            f.evidence_level,
            f.af_related_label,
            f.af_use_label,
            f.adoption_eligible,
            f.exclusion_reason,
            f.future_or_hypothetical_only,
            f.observed_actions_status,
            f.final_observed_actions,
            f.model_a_observed_actions,
            f.model_b_observed_actions,
            f.needs_human_review,
            f.confidence,
            f.semantic_heuristic_warning,
            f.semantic_warning_sources,
            f.final_record_sha256,
            f.af_related_label = 'related' AS is_af_related_confirmed,
            f.af_use_label = 'yes' AS is_af_use_confirmed,
            f.af_use_label = 'no' AS is_af_non_use_confirmed,
            f.af_use_label IN ('yes', 'no') AS is_af_use_resolved,
            f.af_use_label = 'uncertain' AS is_af_use_uncertain,
            f.adoption_eligible = 'yes' AS is_adoption_confirmed,
            f.adoption_eligible IN ('yes', 'no') AS is_adoption_resolved,
            f.observed_actions_status IN ('ab_exact_consensus', 'adjudicated')
              AS action_analysis_eligible,
            r.publication_year BETWEEN {start_year} AND {end_year} AS is_main_period,
            replace(lower(coalesce(r.work_type, '')), '_', '-') NOT IN ({excluded_sql})
              AS analytical_document_type_eligible,
            f.work_id IS NULL AS is_screen_negative_comparator
          FROM ranked r
          JOIN domain_rollup d USING (work_id_norm)
          LEFT JOIN final f ON f.work_id = r.work_id_norm
          WHERE r.representative_rank = 1
          ORDER BY r.work_id_norm
        ) TO '{sql_path(master_tmp)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        connection.execute(build_sql)
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet('{sql_path(master_tmp)}')
              WHERE candidate_reviewed
              ORDER BY work_id
            ) TO '{sql_path(reviewed_tmp)}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        counts = connection.execute(
            f"""
            SELECT
              count(*) AS master_records,
              count(DISTINCT work_id) AS unique_work_ids,
              count(*) FILTER (WHERE candidate_reviewed) AS reviewed_candidates,
              count(*) FILTER (WHERE is_screen_negative_comparator) AS screen_negative_comparators,
              count(*) FILTER (WHERE is_af_use_confirmed) AS af_use_yes,
              count(*) FILTER (WHERE is_af_non_use_confirmed) AS af_use_no,
              count(*) FILTER (WHERE is_af_use_uncertain) AS af_use_uncertain,
              count(*) FILTER (WHERE is_adoption_confirmed) AS adoption_yes,
              count(*) FILTER (WHERE candidate_reviewed AND adoption_eligible = 'no') AS adoption_no,
              count(*) FILTER (WHERE candidate_reviewed AND adoption_eligible = 'uncertain') AS adoption_uncertain,
              min(publication_year) AS min_publication_year,
              max(publication_year) AS max_publication_year
            FROM read_parquet('{sql_path(master_tmp)}')
            """
        ).fetchdf().iloc[0].to_dict()
    finally:
        connection.close()

    expected = config["expected_final_database"]
    if int(counts["reviewed_candidates"]) != int(expected["records"]):
        raise ValueError(
            f"Expected {expected['records']:,} matched reviewed candidates; "
            f"found {int(counts['reviewed_candidates']):,}"
        )
    if int(counts["master_records"]) != int(counts["unique_work_ids"]):
        raise ValueError("Prepared master table is not one row per normalized work_id")

    if MASTER.exists():
        MASTER.unlink()
    if REVIEWED.exists():
        REVIEWED.unlink()
    os.replace(master_tmp, MASTER)
    os.replace(reviewed_tmp, REVIEWED)

    summary = {
        "schema_version": "af-final-analysis-prepare-summary-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "reproducibility": {
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "config_path": str(CONFIG_PATH),
            "config_sha256": sha256_file(CONFIG_PATH),
        },
        "sources": {
            "final_csv": {"path": str(FINAL_CSV), "sha256": sha256_file(FINAL_CSV)},
            "final_lock": {"path": str(FINAL_LOCK), "sha256": sha256_file(FINAL_LOCK)},
            "works_parquet_inventory": {
                "root": str(WORKS_GLOB.parent),
                "files": len(inventory),
                "path_size_mtime_manifest_sha256": inventory_sha,
                "note": "This is a metadata inventory fingerprint, not a content hash of 3+ GiB parquet data.",
            },
        },
        "counts": {
            key: value.item() if hasattr(value, "item") else value
            for key, value in counts.items()
        },
        "outputs": {
            "works_analysis_master": {
                "path": str(MASTER),
                "sha256": sha256_file(MASTER),
            },
            "reviewed_candidates": {
                "path": str(REVIEWED),
                "sha256": sha256_file(REVIEWED),
            },
        },
        "id_normalization": "regexp_extract(source work_id, 'W[0-9]+', 0)",
        "raw_sources_modified": False,
    }
    atomic_write_json(SUMMARY, summary, force=args.force)
    print(f"Master records:         {int(counts['master_records']):,}")
    print(f"Reviewed candidates:    {int(counts['reviewed_candidates']):,}")
    print(f"Screen-negative works:  {int(counts['screen_negative_comparators']):,}")
    print(f"Master table:           {MASTER}")
    print(f"Preparation summary:    {SUMMARY}")


if __name__ == "__main__":
    main()
