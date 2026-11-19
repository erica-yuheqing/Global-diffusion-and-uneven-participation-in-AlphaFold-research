"""Independent export/source validation for approved-link study events. No preparation or inference."""
from __future__ import annotations

import argparse
from pathlib import Path

from baseline_features import fingerprint
from common import (MODULE, assert_unchanged, connect, literal, output_dir, read_json, scalar,
                    sha256, utc, write_json)
from study_events import (DECISIONS, EXPORTS, attach_sources, check_config, check_outputs,
                          install_decisions, load_inputs)


def source_checks(con) -> dict:
    """Independently derive label/date and 24-month aggregates from saved events/source relations."""
    result = {}
    con.execute("""CREATE TEMP VIEW expected_version_flags AS
      SELECT m.study_id,w.work_id,w.publication_year,w.date_status,w.event_date,
        coalesce(w.candidate_reviewed AND coalesce(d.override_af,w.af_use_label)='yes'
          AND coalesce(d.override_adoption,w.adoption_eligible)='yes',false) AS is_confirmed,
        CASE WHEN d.override_af IS NOT NULL THEN false ELSE coalesce(w.possible_af,false) END AS is_possible,
        d.override_date,d.event_source_work_id,w.candidate_reviewed
      FROM work_study_map m JOIN works_eligible w USING(work_id) LEFT JOIN approved_decisions d USING(study_id)""")
    result["unexpected_merges"] = int(scalar(con, """SELECT count(*) FROM work_study_map m
      LEFT JOIN approved_members a USING(work_id) WHERE
        m.study_id IS DISTINCT FROM coalesce(a.study_id,'work-'||m.work_id)"""))
    result["study_labels_source_mismatch"] = int(scalar(con, """WITH expected AS (
      SELECT study_id,bool_or(candidate_reviewed) AS reviewed,bool_or(is_confirmed) AS confirmed
      FROM expected_version_flags GROUP BY 1
    ) SELECT count(*) FROM study_records s JOIN expected e USING(study_id)
      WHERE s.candidate_reviewed IS DISTINCT FROM e.reviewed OR s.confirmed_af IS DISTINCT FROM e.confirmed"""))
    result["representative_metadata_incoherent"] = int(scalar(con, """SELECT count(*) FROM study_records s
      JOIN works_eligible w ON w.work_id=s.citation_representative_work_id
      WHERE s.title IS DISTINCT FROM w.title OR s.publication_year IS DISTINCT FROM w.publication_year
        OR s.publication_date IS DISTINCT FROM w.publication_date OR s.work_type IS DISTINCT FROM w.work_type
        OR s.primary_subfield_id IS DISTINCT FROM w.primary_subfield_id OR s.cited_by_count IS DISTINCT FROM w.cited_by_count
        OR s.journal_or_source_id IS DISTINCT FROM w.journal_or_source_id
        OR s.representative_actions_status IS DISTINCT FROM w.observed_actions_status"""))
    result["nonformal_representative_when_formal_available"] = int(scalar(con, """SELECT count(*) FROM study_records s
      WHERE s.work_type='preprint' AND EXISTS(SELECT 1 FROM work_study_map m JOIN works_eligible w USING(work_id)
        WHERE m.study_id=s.study_id AND w.work_type IN ('article','review'))"""))
    result["approved_formal_anchor_not_representative"] = int(scalar(con, """SELECT count(*) FROM approved_decisions d
      JOIN works_eligible w ON w.work_id=d.event_source_work_id JOIN study_records s USING(study_id)
      WHERE w.work_type IN ('article','review') AND s.annual_representative_work_id<>d.event_source_work_id"""))
    con.execute("""CREATE TEMP VIEW expected_institution_version_dates AS
      SELECT v.study_id,i.institution_id,v.work_id,v.is_confirmed,v.is_possible,v.publication_year,
        CASE WHEN v.is_confirmed AND v.date_status='valid' THEN
          CASE WHEN v.work_id=v.event_source_work_id AND v.override_date IS NOT NULL THEN v.override_date
            WHEN v.override_date IS NOT NULL AND v.event_date<v.override_date THEN NULL
            ELSE v.event_date END
          WHEN v.is_possible AND v.date_status='valid' THEN v.event_date END AS dated_evidence
      FROM expected_version_flags v JOIN work_institution_membership i USING(work_id)
      WHERE v.is_confirmed OR v.is_possible""")
    result["institution_event_date_or_label_mismatch"] = int(scalar(con, """WITH expected AS (
      SELECT study_id,institution_id,bool_or(is_confirmed) AS confirmed,
        CASE WHEN bool_or(is_confirmed) THEN min(dated_evidence) FILTER(WHERE is_confirmed)
          ELSE min(dated_evidence) FILTER(WHERE is_possible) END AS expected_date
      FROM expected_institution_version_dates GROUP BY 1,2
    ) SELECT count(*) FROM expected x FULL JOIN institution_study_events e USING(study_id,institution_id)
      WHERE x.confirmed IS DISTINCT FROM e.confirmed_af OR x.expected_date IS DISTINCT FROM e.event_date"""))
    result["institution_date_source_inconsistent"] = int(scalar(con, """SELECT count(*)
      FROM institution_study_events e JOIN expected_institution_version_dates v ON
        v.study_id=e.study_id AND v.institution_id=e.institution_id AND v.work_id=e.event_source_work_id
      WHERE (e.confirmed_af AND NOT v.is_confirmed) OR e.event_date IS DISTINCT FROM v.dated_evidence"""))
    result["history_first_date_mismatch"] = int(scalar(con, """WITH expected AS (
      SELECT institution_id,min(event_date) FILTER(WHERE confirmed_af) AS t0,
        count(*) FILTER(WHERE confirmed_af) AS n FROM institution_study_events GROUP BY 1
    ) SELECT count(*) FROM institution_participation_history h LEFT JOIN expected e USING(institution_id)
      WHERE h.first_observed_confirmed_date IS DISTINCT FROM e.t0 OR h.confirmed_study_units<>coalesce(e.n,0)"""))
    result["history_interval_counts_mismatch"] = int(scalar(con, """WITH expected AS (
      SELECT h.institution_id,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date>h.first_observed_confirmed_date
          AND e.event_date<=h.first_observed_confirmed_date+INTERVAL '12 months') AS b1,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date>h.first_observed_confirmed_date+INTERVAL '12 months'
          AND e.event_date<=h.first_observed_confirmed_date+INTERVAL '24 months') AS b2,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date=h.first_observed_confirmed_date) AS co_initial
      FROM institution_participation_history h LEFT JOIN institution_study_events e USING(institution_id) GROUP BY 1
    ) SELECT count(*) FROM institution_participation_history h JOIN expected x USING(institution_id)
      WHERE h.bin1_confirmed_studies<>x.b1 OR h.bin2_confirmed_studies<>x.b2 OR h.co_initial_studies<>x.co_initial"""))
    result["calendar_endpoints_mismatch"] = int(scalar(con, """SELECT count(*) FROM institution_participation_history
      WHERE month12_end IS DISTINCT FROM CAST(first_observed_confirmed_date+INTERVAL '12 months' AS DATE)
        OR month24_end IS DISTINCT FROM CAST(first_observed_confirmed_date+INTERVAL '24 months' AS DATE)
        OR observation_cutoff<>DATE '2025-12-31'"""))
    result["followup_eligibility_rule_mismatch"] = int(scalar(con, """SELECT count(*) FROM institution_participation_history
      WHERE first_entry_date_resolved IS DISTINCT FROM
          (first_observed_confirmed_date IS NOT NULL AND first_entry_uncertainty_studies=0)
        OR complete_24m_window IS DISTINCT FROM coalesce(month24_end<=observation_cutoff,false)
        OR eligible_24m_distribution IS DISTINCT FROM
          (first_entry_date_resolved AND NOT pre_main_confirmed_participation
            AND year(first_observed_confirmed_date)>=2020 AND complete_24m_window
            AND identification_uncertainty_24m_studies=0)
        OR pre_main_confirmed_participation IS DISTINCT FROM coalesce(first_confirmed_evidence_year<2020,false)
        OR (eligible_24m_distribution AND intervals_covered_24m IS DISTINCT FROM
          (CAST(bin1_confirmed_studies>0 AS INTEGER)+CAST(bin2_confirmed_studies>0 AS INTEGER)))"""))
    return result


def validate(directory: Path, verify_source_content: bool = False) -> dict:
    import pyarrow.parquet as pq
    mp = directory / "prepare_manifest.json"
    manifest = read_json(mp)
    if manifest.get("schema_version") != "nhb-study-events-run-v1":
        raise ValueError("Not a study events v1 artifact")
    check_config(manifest["config"])
    assert_unchanged(manifest["inputs"])
    source = output_dir(Path(manifest["foundation_directory"]), existing=True)
    features = output_dir(Path(manifest["feature_directory"]), existing=True)
    _, source_inv = load_inputs(source, features)
    archived = {str(Path(r["path"]).resolve()): r["sha256"] for r in manifest["inputs"]}
    if any(archived.get(str(Path(r["path"]).resolve())) != r["sha256"] for r in source_inv):
        raise ValueError("Current source/approval chain differs from run")
    if verify_source_content:
        for rec in manifest["inputs"]:
            if sha256(Path(rec["path"])) != rec["sha256"]:
                raise ValueError("Source content changed")
    for name, expected in manifest["snapshots"].items():
        p = directory / name
        if not p.resolve().is_relative_to(directory) or fingerprint(p)["sha256"] != expected["sha256"]:
            raise ValueError("Archived implementation/policy changed")
    for name in ("common.py", "baseline_features.py", "study_events.py", "validate_study_events.py"):
        if sha256(MODULE / name) != manifest["snapshots"][f"code_and_protocol/{name}"]["sha256"]:
            raise ValueError("Validator implementation differs; use archived version or a new run")
    con = connect()
    try:
        attach_sources(con, source, features)
        install_decisions(con, read_json(DECISIONS)["decisions"])
        for name in EXPORTS:
            p = directory / f"{name}.parquet"
            rec, expected = fingerprint(p), manifest["outputs"][p.name]
            if (rec["sha256"] != expected["sha256"] or rec["size_bytes"] != expected["size_bytes"]
                    or pq.ParquetFile(p).metadata.num_rows != expected["rows"]):
                raise ValueError("Export content/row count changed")
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({literal(p)})")
        checks = check_outputs(con)
        checks.update(source_checks(con))
        blockers = [name for name, n in checks.items() if n]
        if scalar(con, "SELECT count(*) FROM study_records") != manifest["study_counts"]["study_units_after_approved_links"]:
            blockers.append("manifest_study_count_mismatch")
        assert_unchanged(manifest["inputs"])
        return {"schema_version": "nhb-study-events-validation-v1", "created_at_utc": utc(),
                "prepare_manifest_sha256": sha256(mp), "checks": checks, "blockers": blockers,
                "approved_link_study_events_ready": not blockers,
                "complete_version_deduplication_claimed": False, "formal_models_ready": False,
                "raw_source_full_hashes_rechecked": verify_source_content}
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=MODULE / "study_events_v1")
    parser.add_argument("--verify-source-content", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="validate without writing/overwriting report")
    args = parser.parse_args()
    directory = output_dir(args.input_dir, existing=True)
    report = validate(directory, args.verify_source_content)
    if not args.dry_run:
        write_json(directory / "validation_report.json", report)
    print(f"Study/event checks: {len(report['checks'])}; blockers: {len(report['blockers'])}")
    print(f"Approved-link study/event foundations ready: {report['approved_link_study_events_ready']}")
    print("Complete version deduplication / formal models ready: False")
    if report["blockers"]:
        print(f"Blockers: {report['blockers']}")
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
