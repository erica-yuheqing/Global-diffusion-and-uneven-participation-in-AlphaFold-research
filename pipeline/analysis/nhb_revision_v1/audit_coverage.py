"""Read-only coverage and version-review leads; no merging, imputation or inference.

Requires the corrected out_v2 and its independent validation. Outputs are new audit artifacts.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from common import (DEFAULT_OUT, MODULE, SCHEMA, assert_unchanged, connect, environment, literal,
                    output_dir, read_json, sha256, utc, write_json)

INPUT_TABLES = ("works_eligible", "work_countries", "work_institution_membership", "country_residuals",
                "authorships", "institution_registry", "version_review_candidates", "field_inventory",
                "action_review_queue")


def records(con, sql: str) -> list[dict]:
    result = con.execute(sql)
    names = [x[0] for x in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def audit(con) -> dict:
    """Uses only known prepared views; bounded output, full aggregate scan of those views."""
    con.execute("""CREATE TEMP TABLE attribution_coverage AS
      SELECT w.work_id,
        EXISTS(SELECT 1 FROM work_countries c WHERE c.work_id=w.work_id) AS country_observed,
        EXISTS(SELECT 1 FROM work_institution_membership i WHERE i.work_id=w.work_id) AS institution_observed,
        coalesce(r.total_residual_weight,0.0) AS unallocated_institution_country_weight
      FROM works_eligible w LEFT JOIN (
        SELECT work_id,sum(residual_weight) AS total_residual_weight FROM country_residuals GROUP BY work_id
      ) r USING(work_id)""")
    con.execute("""CREATE TEMP TABLE authorship_coverage AS
      SELECT work_id,count(*) AS observed_author_rows,
        count(DISTINCT author_id) AS known_distinct_author_ids,
        count(*) FILTER(WHERE author_id IS NULL) AS missing_author_id_rows,
        count(DISTINCT author_id) FILTER(WHERE author_position='first') AS known_first_author_ids,
        count(DISTINCT author_id) FILTER(WHERE author_position='last') AS known_last_author_ids,
        count(*) FILTER(WHERE author_position IS NULL OR author_position NOT IN ('first','middle','last')) AS unknown_position_rows
      FROM authorships GROUP BY work_id""")
    # Project only coverage fields; do not duplicate millions of titles/source strings in memory.
    fields = "w.work_id,w.date_status,w.primary_subfield_id,w.citation_status"
    con.execute(f"""CREATE TEMP VIEW coverage_groups AS
      SELECT {fields}, 'all_eligible' AS audit_cohort FROM works_eligible w
      UNION ALL SELECT {fields}, 'baseline' FROM works_eligible w WHERE period='baseline'
      UNION ALL SELECT {fields}, 'main' FROM works_eligible w WHERE period='main'
      UNION ALL SELECT {fields}, 'main_confirmed_af' FROM works_eligible w WHERE period='main' AND confirmed_af
      UNION ALL SELECT {fields}, 'main_screen_negative' FROM works_eligible w WHERE period='main' AND screen_negative
      UNION ALL SELECT {fields}, 'main_possible_af' FROM works_eligible w WHERE period='main' AND possible_af
      UNION ALL SELECT {fields}, 'main_reviewed_non_use' FROM works_eligible w WHERE period='main' AND reviewed_non_use
      UNION ALL SELECT {fields}, 'main_use_not_adoption' FROM works_eligible w WHERE period='main' AND use_not_adoption""")
    coverage = records(con, """SELECT w.audit_cohort,count(*) AS works,
      count(*) FILTER(WHERE NOT c.country_observed) AS country_missing_works,
      count(*) FILTER(WHERE NOT c.institution_observed) AS institution_missing_works,
      count(*) FILTER(WHERE NOT c.country_observed AND NOT c.institution_observed) AS both_missing_works,
      count(*) FILTER(WHERE w.date_status<>'valid') AS date_unusable_works,
      count(*) FILTER(WHERE a.work_id IS NULL) AS no_authorship_record_works,
      count(*) FILTER(WHERE a.missing_author_id_rows>0) AS any_missing_author_id_works,
      count(*) FILTER(WHERE a.known_first_author_ids=1) AS one_known_first_id_works,
      count(*) FILTER(WHERE a.known_last_author_ids=1) AS one_known_last_id_works,
      count(*) FILTER(WHERE a.known_distinct_author_ids=1 AND a.missing_author_id_rows=0
        AND a.known_first_author_ids=1 AND a.unknown_position_rows=0) AS observed_single_author_first_id_works,
      sum(c.unallocated_institution_country_weight) AS unallocated_institution_country_fractional_sum,
      count(*) FILTER(WHERE w.primary_subfield_id IS NULL OR trim(w.primary_subfield_id)='') AS missing_primary_subfield_works,
      count(*) FILTER(WHERE w.citation_status IN ('missing','invalid_negative')) AS citation_unusable_works,
      count(*) FILTER(WHERE w.citation_status='reported_zero_not_independently_verified') AS reported_zero_citation_works
      FROM coverage_groups w JOIN attribution_coverage c USING(work_id)
      LEFT JOIN authorship_coverage a USING(work_id) GROUP BY w.audit_cohort ORDER BY w.audit_cohort""")
    for row in coverage:
        for key in ("country_missing_works", "institution_missing_works", "date_unusable_works"):
            row[key.removesuffix("_works") + "_fraction"] = row[key] / row["works"] if row["works"] else None
    con.execute("""CREATE TEMP TABLE version_review_groups AS
      SELECT normalized_doi,count(*) AS candidate_work_records,
        count(*) FILTER(WHERE work_type='preprint') AS preprint_records,
        count(*) FILTER(WHERE work_type IN ('article','review')) AS formal_records,
        count(*) FILTER(WHERE confirmed_af AND period='main') AS main_confirmed_af_records,
        count(*) FILTER(WHERE candidate_reviewed) AS reviewed_records,
        bool_or(has_core_status_conflict) AS has_core_status_conflict,
        bool_or(has_review_membership_mix) AS has_review_membership_mix,
        min(publication_year) AS earliest_year,max(publication_year) AS latest_year,
        CASE WHEN bool_or(has_core_status_conflict) THEN 'P0_core_label_review'
          WHEN bool_or(confirmed_af AND period='main') THEN 'P1_AF_related_version_review'
          ELSE 'P2_other_exact_doi_review' END AS review_priority,
        'pending_review_not_a_merge_decision' AS review_status
      FROM version_review_candidates GROUP BY normalized_doi""")
    con.execute("""CREATE TEMP TABLE version_review_members AS
      SELECT v.normalized_doi,v.work_id,v.title,v.publication_year,v.publication_date,v.date_status,
        v.work_type,v.candidate_reviewed,v.af_use_label,v.adoption_eligible,
        v.confirmed_af,v.period,g.review_priority,g.review_status
      FROM version_review_candidates v JOIN version_review_groups g USING(normalized_doi)""")
    summary = {
        "coverage_by_cohort": coverage,
        "date_status_by_year": records(con, "SELECT publication_year,date_status,count(*) AS works FROM works_eligible GROUP BY 1,2 ORDER BY 1,2"),
        "confirmed_af_dates_by_year": records(con, "SELECT publication_year,date_status,count(*) AS works FROM works_eligible WHERE confirmed_af GROUP BY 1,2 ORDER BY 1,2"),
        "action_status_main_confirmed_af": records(con, "SELECT observed_actions_status,count(*) AS works FROM works_eligible WHERE period='main' AND confirmed_af GROUP BY 1 ORDER BY 1"),
        "action_queue_records": con.execute("SELECT count(*) FROM action_review_queue").fetchone()[0],
        "version_review": records(con, "SELECT review_priority,count(*) AS doi_groups,sum(candidate_work_records) AS work_records FROM version_review_groups GROUP BY 1 ORDER BY 1"),
        "version_same_doi_preprint_formal_groups": con.execute("SELECT count(*) FROM version_review_groups WHERE preprint_records>0 AND formal_records>0").fetchone()[0],
        "institution_baseline_coverage": records(con, "SELECT baseline_observation_status,count(*) AS institutions FROM institution_registry GROUP BY 1 ORDER BY 1"),
        "provisional_active_thresholds_not_approved": [
            {"minimum_baseline_works": threshold, "observed_institution_ids": con.execute(
                "SELECT count(*) FROM institution_registry WHERE observed_baseline_works>=?", [threshold]).fetchone()[0]}
            for threshold in (1, 2, 5, 10)
        ],
        "ready_for_auto_merges": False, "ready_for_final_denominator": False,
        "scope": "full aggregate scan of selected prepared tables; work-level, not study-level",
        "limitations": ["No missing values filled; no studies linked or merged",
                        "No-authorship and missing-ID summaries do not certify actual complete author lists",
                        "First/last ID coverage is not a validated leadership cohort",
                        "No baseline observation is not proof of true zero prior capacity",
                        "DOI candidates omit version pairs with different DOIs or no DOI",
                        "Annual dates are accepted as locally observed, not independently verified publisher dates",
                        "Audit cohorts overlap; their counts must not be summed"],
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--output-dir", type=Path, default=MODULE / "coverage_audit_v2")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-gib", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="integrity/metadata only; no new aggregates or files")
    args = parser.parse_args()
    if not 1 <= args.threads <= 16 or not 1 <= args.memory_gib <= 32:
        parser.error("threads 1..16; memory-gib 1..32")
    directory = output_dir(args.input_dir, existing=True)
    destination = output_dir(args.output_dir)
    if destination.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Audit outputs must be separate from frozen foundations")
    manifest_path = directory / "prepare_manifest.json"
    validation_path = directory / "validation_report.json"
    manifest = read_json(manifest_path)
    validation = read_json(validation_path)
    if (manifest["schema_version"] != SCHEMA or
        validation.get("schema_version") != "nhb-foundations-validation-v2" or
        not validation.get("work_level_foundations_ready") or validation.get("blockers") or
        validation["prepare_manifest_sha256"] != sha256(manifest_path)):
        raise ValueError("Requires corrected out_v2 with matching successful independent validation")
    assert_unchanged(manifest["inputs"])
    import pyarrow.parquet as pq
    file_records = []
    for table in INPUT_TABLES:
        p = directory / f"{table}.parquet"
        rec = manifest["outputs"][p.name]
        stat = p.stat()
        if p.is_symlink() or stat.st_size != rec["size_bytes"] or sha256(p) != rec["sha256"]:
            raise ValueError(f"Prepared input integrity failure: {p.name}")
        if pq.ParquetFile(p).metadata.num_rows != rec["rows"]:
            raise ValueError(f"Prepared row count differs: {p.name}")
        file_records.append({"path": str(p), "size_bytes": stat.st_size,
                             "mtime_ns": stat.st_mtime_ns, "sha256": rec["sha256"]})
    if args.dry_run:
        print("Coverage audit dry run: corrected source/validation/output hashes checked; no aggregate scan or files")
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".coverage-incomplete-", dir=destination.parent))
    con = None
    try:
        con = connect(args.threads, args.memory_gib, spill=stage / ".spill")
        for table in INPUT_TABLES:
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({literal(directory / (table + '.parquet'))})")
        summary = audit(con)
        outputs = {}
        for table, order in (("version_review_groups", "review_priority,normalized_doi"),
                             ("version_review_members", "review_priority,normalized_doi,work_id")):
            p = stage / f"{table}.parquet"
            con.execute(f"COPY (SELECT * FROM {table} ORDER BY {order}) TO {literal(p)} (FORMAT PARQUET,COMPRESSION ZSTD)")
            outputs[p.name] = {"sha256": sha256(p), "size_bytes": p.stat().st_size}
        con.close()
        con = None
        assert_unchanged(file_records)
        assert_unchanged(manifest["inputs"])
        summary.update({"schema_version": "nhb-coverage-audit-v2", "created_at_utc": utc(),
                        "environment": environment(), "prepare_manifest_sha256": sha256(manifest_path),
                        "validation_report_sha256": sha256(validation_path), "inputs": file_records,
                        "outputs": outputs, "inputs_modified": False})
        shutil.copyfile(Path(__file__), stage / "audit_coverage.py")
        shutil.copyfile(MODULE / "common.py", stage / "common.py")
        summary["code_sha256"] = {name: sha256(stage / name) for name in ("audit_coverage.py", "common.py")}
        write_json(stage / "coverage_report.json", summary)
        if destination.exists():
            raise FileExistsError("Audit destination appeared; staging retained")
        stage.rename(destination)
        print(f"Action review work records: {summary['action_queue_records']:,}")
        for row in summary["version_review"]:
            print(f"{row['review_priority']}: {row['doi_groups']:,} DOI groups / {row['work_records']:,} work records")
        print(f"Coverage audit saved: {destination}; NEXT review coverage and version leads; no automatic merges")
    except BaseException:
        if con is not None:
            con.close()
        print(f"INCOMPLETE audit retained: {stage}; no published audit", flush=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
