"""Approved study links and institution follow-up, local-only; no statistics or API calls."""
from __future__ import annotations

import hashlib
from pathlib import Path

from baseline_features import fingerprint, load_inputs as load_foundations
from common import (MODULE, assert_unchanged, literal, read_json, scalar, sha256)

CONFIG = MODULE / "study_events_config_v1.json"
DECISIONS = MODULE / "version_decisions_user_v1.json"
SOURCE_TABLES = ("works_eligible", "work_institution_membership", "institution_registry")
EXPORTS = {
    "work_study_map": "work_id",
    "study_records": "study_id",
    "version_selection_audit": "study_id,work_id",
    "version_institution_audit": "study_id,institution_id,work_id",
    "institution_study_events": "institution_id,study_id",
    "institution_participation_history": "institution_id",
    "unmerged_doi_audit": "normalized_doi",
}


def check_config(c: dict) -> None:
    expected = {
        "schema_version": "nhb-study-events-config-v1", "protocol_version": "1.3",
        "observation_cutoff": "2025-12-31", "main_years": [2020, 2025], "baseline_years": [2015, 2019],
        "merge_policy": "explicit_approved_work_ids_only_other_records_singletons",
        "representative_rule": "formal_first_then_approved_event_source_then_valid_date_year_work_id",
        "annual_representative": "same_as_citation_representative_metadata_and_attribution_coherent",
        "event_attribution": "earliest_confirmed_observed_version_per_institution_no_union_backdating",
        "override_earlier_member_date": "unusable_for_institution_timing_unless_other_valid_version_available",
        "same_day_entries": "co_initial_not_repeated",
        "followup_boundaries": "(t0,t0+12_calendar_months];(t0+12,t0+24_calendar_months]",
        "main_24m_denominator": "main_first_entry_resolved_complete_window_no_local_event_identification_uncertainty",
        "unobserved_zero_policy": "no_confirmed_entry_has_NULL_followup_not_zero",
        "formal_model_ready": False, "complete_version_deduplication_claimed": False,
    }
    if any(c.get(k) != v for k, v in expected.items()) or c.get("minimum_free_disk_gib", 0) < 10:
        raise ValueError("Study/event settings differ from this version's explicit implementation rules")


def load_inputs(foundation_dir: Path, feature_dir: Path) -> tuple[dict, list[dict]]:
    import pyarrow.parquet as pq
    _, inv = load_foundations(foundation_dir)
    c = read_json(CONFIG)
    check_config(c)
    inv.append(fingerprint(CONFIG))
    fm = feature_dir / "prepare_manifest.json"
    fv = feature_dir / "validation_report.json"
    inv += [fingerprint(fm), fingerprint(fv)]
    m, v = read_json(fm), read_json(fv)
    if (m.get("schema_version") != "nhb-baseline-features-run-v1"
            or v.get("schema_version") != "nhb-baseline-features-validation-v1"
            or not v.get("prior_work_level_features_ready") or v.get("blockers")
            or v.get("prepare_manifest_sha256") != sha256(fm)
            or Path(m["foundation_directory"]).resolve() != foundation_dir.resolve()):
        raise ValueError("Requires matching, independently validated prior features")
    assert_unchanged(m["inputs"])
    current = {str(Path(r["path"]).resolve()): r["sha256"] for r in inv}
    for rec in m["inputs"]:
        key = str(Path(rec["path"]).resolve())
        if key in current and current[key] != rec["sha256"]:
            raise ValueError("Feature run and current foundations/protocol/decisions differ")
    for name, expected in m["outputs"].items():
        path = feature_dir / name
        rec = fingerprint(path)
        if (rec["sha256"] != expected["sha256"] or rec["size_bytes"] != expected["size_bytes"]
                or pq.ParquetFile(path).metadata.num_rows != expected["rows"]):
            raise ValueError("Frozen feature output changed")
        inv.append(rec)
    # This stage needs these additional columns, not merely the earlier feature projection.
    required = {"normalized_doi", "candidate_reviewed", "af_use_label", "adoption_eligible",
                "confirmed_af", "possible_af", "date_status", "event_date", "publication_year",
                "work_id", "work_type", "period", "primary_subfield_id", "cited_by_count",
                "title", "doi", "publication_date", "primary_topic_id", "primary_topic_display_name",
                "primary_subfield_display_name", "citation_status", "journal_or_source_id",
                "journal_or_source_name", "observed_actions_status", "final_observed_actions"}
    if not required.issubset(pq.ParquetFile(foundation_dir / "works_eligible.parquet").schema_arrow.names):
        raise ValueError("Study source lacks necessary label/date/representative fields")
    return c, inv


def attach_sources(con, foundation_dir: Path, feature_dir: Path) -> None:
    for name in SOURCE_TABLES:
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({literal(foundation_dir / (name + '.parquet'))})")
    con.execute(f"CREATE VIEW institution_baseline_scale AS SELECT * FROM read_parquet({literal(feature_dir / 'institution_baseline_scale.parquet')})")


def install_decisions(con, decisions: list[dict]) -> None:
    """Bounded parameter insertion, never SQL derived from titles or member text."""
    if len(decisions) > 20:
        raise ValueError("Version decision limit exceeded; review a separate scope")
    con.execute("""CREATE TEMP TABLE approved_decisions(study_id VARCHAR,normalized_doi VARCHAR,
      override_af VARCHAR,override_adoption VARCHAR,override_date DATE,event_source_work_id VARCHAR)""")
    con.execute("CREATE TEMP TABLE approved_members(study_id VARCHAR,work_id VARCHAR)")
    seen, seen_dois = set(), set()
    for d in decisions:
        ids = d["member_work_ids"]
        if d["relation"] != "same_study" or not 2 <= len(ids) <= 100 or any(i in seen for i in ids) or len(ids) != len(set(ids)):
            raise ValueError("Invalid/reused approved version membership")
        seen.update(ids)
        if d["normalized_doi"] in seen_dois:
            raise ValueError("Multiple approved groups for the same DOI need one explicit combined decision")
        seen_dois.add(d["normalized_doi"])
        study = "doi-" + hashlib.sha256(d["normalized_doi"].encode("utf-8")).hexdigest()
        core = d.get("study_core_decision") or {}
        con.execute("INSERT INTO approved_decisions VALUES (?,?,?,?,?,?)", [study, d["normalized_doi"],
                    core.get("af_use_label"), core.get("adoption_eligible"), d.get("event_date_override"),
                    d.get("event_date_source_work_id")])
        con.executemany("INSERT INTO approved_members VALUES (?,?)", [(study, i) for i in ids])
    bad = scalar(con, """SELECT count(*) FROM approved_members a JOIN approved_decisions d USING(study_id)
      LEFT JOIN works_eligible w USING(work_id) WHERE w.work_id IS NULL
        OR w.normalized_doi IS DISTINCT FROM d.normalized_doi""")
    if bad:
        raise ValueError("Approved DOI members missing/different in frozen source")
    if scalar(con, """SELECT count(*) FROM approved_decisions d LEFT JOIN approved_members m
      ON d.study_id=m.study_id AND d.event_source_work_id=m.work_id
      WHERE d.override_date IS NOT NULL AND (m.work_id IS NULL OR d.override_date>DATE '2025-12-31')"""):
        raise ValueError("Approved event date lacks a member anchor or exceeds observation cutoff")
    if scalar(con, """SELECT count(*) FROM approved_decisions d JOIN works_eligible w
      ON w.work_id=d.event_source_work_id WHERE d.override_date IS NOT NULL
        AND (NOT w.candidate_reviewed OR NOT coalesce(w.confirmed_af,false)
          OR w.date_status<>'valid' OR year(d.override_date)<>w.publication_year)"""):
        raise ValueError("User event anchor must be a dated confirmed local member in the stated year")


def build_studies(con, decisions: list[dict]) -> dict:
    install_decisions(con, decisions)
    con.execute("""CREATE TEMP TABLE work_study_map AS
      SELECT w.work_id,coalesce(m.study_id,'work-'||w.work_id) AS study_id,
        CASE WHEN m.study_id IS NULL THEN 'unlinked_single_work_not_certified_unique_study'
          ELSE 'explicit_user_same_study' END AS link_status
      FROM works_eligible w LEFT JOIN approved_members m USING(work_id)""")
    con.execute("""CREATE TEMP TABLE effective_versions AS
      WITH labeled AS (
        SELECT m.study_id,w.work_id,w.publication_year,w.publication_date,w.event_date AS raw_event_date,
          w.date_status,w.work_type,w.period,w.normalized_doi,w.candidate_reviewed,
          coalesce(d.override_af,w.af_use_label) AS effective_af_use_label,
          coalesce(d.override_adoption,w.adoption_eligible) AS effective_adoption_eligible,
          w.possible_af AS raw_possible_af,d.override_date,d.event_source_work_id,
          d.override_af IS NOT NULL AS user_core_override
        FROM work_study_map m JOIN works_eligible w USING(work_id)
        LEFT JOIN approved_decisions d USING(study_id)
      ), flags AS (
        SELECT *,coalesce(candidate_reviewed AND effective_af_use_label='yes'
          AND effective_adoption_eligible='yes',false) AS version_confirmed_af,
          CASE WHEN user_core_override THEN false ELSE coalesce(raw_possible_af,false) END AS version_possible_af
        FROM labeled
      ) SELECT *,CASE WHEN version_confirmed_af AND date_status='valid' THEN
          CASE WHEN override_date IS NOT NULL AND work_id=event_source_work_id THEN override_date
               WHEN override_date IS NOT NULL AND raw_event_date<override_date THEN NULL
               ELSE raw_event_date END END AS confirmed_version_date,
        CASE WHEN version_possible_af AND date_status='valid' THEN raw_event_date END AS possible_version_date,
        CASE WHEN version_confirmed_af AND override_date IS NOT NULL AND work_id<>event_source_work_id
          AND raw_event_date<override_date THEN 'earlier_member_date_conflicts_with_user_event_date'
          WHEN date_status<>'valid' THEN date_status ELSE 'locally_valid_not_publisher_verified' END AS timing_status
      FROM flags""")
    # No silent propagation of a yes across a conflicting approved group.
    conflicts = scalar(con, """SELECT count(*) FROM (SELECT study_id FROM effective_versions
      WHERE candidate_reviewed GROUP BY study_id
      HAVING count(DISTINCT effective_af_use_label||'/'||effective_adoption_eligible)>1)""")
    if conflicts:
        raise ValueError("Unresolved cross-version core labels; needs separate user decision")
    con.execute("""CREATE TEMP TABLE representative_selection AS
      SELECT study_id,work_id FROM (
        SELECT *,row_number() OVER(PARTITION BY study_id ORDER BY
          CASE WHEN work_type IN ('article','review') THEN 0 ELSE 1 END,
          CASE WHEN work_id=event_source_work_id THEN 0 ELSE 1 END,
          CASE WHEN date_status='valid' THEN 0 ELSE 1 END,publication_year,
          raw_event_date NULLS LAST,work_id) AS choice
        FROM effective_versions
      ) WHERE choice=1""")
    con.execute("""CREATE TEMP TABLE study_records AS
      WITH labels AS (
        SELECT study_id,count(*) AS member_work_records,bool_or(candidate_reviewed) AS candidate_reviewed,
          bool_or(version_confirmed_af) AS confirmed_af,bool_or(version_possible_af) AS possible_af,
          min(effective_af_use_label) FILTER(WHERE candidate_reviewed) AS af_use_label,
          min(effective_adoption_eligible) FILTER(WHERE candidate_reviewed) AS adoption_eligible,
          min(publication_year) FILTER(WHERE version_confirmed_af) AS first_confirmed_evidence_year,
          min(confirmed_version_date) AS earliest_confirmed_date,
          bool_or(user_core_override) AS user_core_override
        FROM effective_versions GROUP BY study_id
      ) SELECT l.*,NOT l.candidate_reviewed AS screen_negative,
        s.work_id AS annual_representative_work_id,s.work_id AS citation_representative_work_id,
        w.title,w.doi,w.normalized_doi,w.publication_year,w.publication_date,w.work_type,w.period,
        w.primary_topic_id,w.primary_topic_display_name,w.primary_subfield_id,w.primary_subfield_display_name,
        w.cited_by_count,w.citation_status,w.journal_or_source_id,w.journal_or_source_name,
        w.date_status AS representative_date_status,w.event_date AS representative_publication_date,
        w.observed_actions_status AS representative_actions_status,w.final_observed_actions AS representative_observed_actions,
        'rule_selected_not_individual_user_representative_approval' AS representative_selection_status,
        CASE WHEN l.member_work_records>1 THEN 'explicit_user_link'
          ELSE 'unlinked_singleton_residual_version_duplicates_possible' END AS deduplication_status
      FROM labels l JOIN representative_selection s USING(study_id) JOIN works_eligible w ON w.work_id=s.work_id""")
    con.execute("""CREATE TEMP TABLE version_selection_audit AS
      SELECT e.*,w.af_use_label AS original_af_use_label,w.adoption_eligible AS original_adoption_eligible,
        w.confirmed_af AS original_confirmed_af,s.annual_representative_work_id,s.citation_representative_work_id,
        e.work_id=s.annual_representative_work_id AS selected_representative,
        s.representative_selection_status FROM effective_versions e
      JOIN approved_decisions d USING(study_id) JOIN study_records s USING(study_id)
      JOIN works_eligible w ON w.work_id=e.work_id""")
    con.execute("""CREATE TEMP TABLE version_institution_audit AS
      SELECT e.study_id,i.institution_id,e.work_id,e.raw_event_date,e.confirmed_version_date,
        e.version_confirmed_af,e.version_possible_af,e.timing_status,
        e.work_id=s.annual_representative_work_id AS in_annual_representative
      FROM effective_versions e JOIN approved_decisions d USING(study_id)
      JOIN work_institution_membership i USING(work_id) JOIN study_records s USING(study_id)""")
    con.execute("""CREATE TEMP TABLE unmerged_doi_audit AS
      SELECT w.normalized_doi,count(*) AS work_records,count(DISTINCT m.study_id) AS retained_study_units,
        'same_doi_lead_not_approved_merge_residual_duplicates_possible' AS status
      FROM works_eligible w JOIN work_study_map m USING(work_id) WHERE w.normalized_doi LIKE '10.%/%'
      GROUP BY w.normalized_doi HAVING count(DISTINCT m.study_id)>1""")
    return {"work_records": int(scalar(con, "SELECT count(*) FROM works_eligible")),
            "study_units_after_approved_links": int(scalar(con, "SELECT count(*) FROM study_records")),
            "approved_link_groups": len(decisions),
            "confirmed_af_main_study_units": int(scalar(con, "SELECT count(*) FROM study_records WHERE period='main' AND confirmed_af")),
            "unmerged_same_doi_groups": int(scalar(con, "SELECT count(*) FROM unmerged_doi_audit"))}


def build_histories(con) -> dict:
    # Date choice is institution-specific, from confirmed versions actually listing that institution.
    con.execute("""CREATE TEMP TABLE institution_study_events AS
      WITH versions AS (
        SELECT e.*,i.institution_id FROM effective_versions e JOIN work_institution_membership i USING(work_id)
        WHERE e.version_confirmed_af OR e.version_possible_af
      ), selected AS (
        SELECT *,row_number() OVER(PARTITION BY study_id,institution_id ORDER BY
          CASE WHEN version_confirmed_af THEN 0 ELSE 1 END,
          CASE WHEN version_confirmed_af AND confirmed_version_date IS NOT NULL THEN 0
            WHEN version_possible_af AND possible_version_date IS NOT NULL THEN 1 ELSE 2 END,
          coalesce(confirmed_version_date,possible_version_date) NULLS LAST,publication_year,work_id) AS choice
        FROM versions
      ), totals AS (
        SELECT study_id,institution_id,bool_or(version_confirmed_af) AS confirmed_af,
          bool_or(version_possible_af) AS any_possible_af_version,
          min(publication_year) FILTER(WHERE version_confirmed_af) AS confirmed_evidence_year,
          min(publication_year) AS earliest_version_evidence_year,
          count(*) FILTER(WHERE version_confirmed_af AND confirmed_version_date IS NULL) AS undated_confirmed_versions,
          min(publication_year) FILTER(WHERE version_confirmed_af AND confirmed_version_date IS NULL)
            AS earliest_undated_confirmed_year
        FROM versions GROUP BY study_id,institution_id
      ) SELECT t.*,NOT t.confirmed_af AND t.any_possible_af_version AS possible_af_only,
        s.work_id AS event_source_work_id,
        CASE WHEN t.confirmed_af THEN s.confirmed_version_date ELSE s.possible_version_date END AS event_date,
        s.publication_year AS source_publication_year,s.timing_status,
        coalesce(t.earliest_undated_confirmed_year<=year(s.confirmed_version_date)
          AND NOT (s.override_date IS NOT NULL AND s.work_id=s.event_source_work_id),false)
          AS within_study_first_date_unresolved,
        'actual_observed_member_no_union_backdating' AS attribution_policy
      FROM totals t JOIN selected s USING(study_id,institution_id) WHERE s.choice=1""")
    con.execute("""CREATE TEMP TABLE institution_first_dates AS
      WITH observed AS (
        SELECT institution_id,count(*) FILTER(WHERE confirmed_af) AS confirmed_study_units,
          count(*) FILTER(WHERE possible_af_only) AS possible_only_study_units,
          min(event_date) FILTER(WHERE confirmed_af) AS first_observed_confirmed_date,
          min(confirmed_evidence_year) FILTER(WHERE confirmed_af) AS first_confirmed_evidence_year
        FROM institution_study_events GROUP BY institution_id
      ) SELECT r.institution_id,o.first_observed_confirmed_date,o.first_confirmed_evidence_year,
        coalesce(o.confirmed_study_units,0) AS confirmed_study_units,
        coalesce(o.possible_only_study_units,0) AS possible_only_study_units,
        coalesce(o.first_confirmed_evidence_year<2020,false) AS pre_main_confirmed_participation,
        b.fixed_cohort_ge1,b.sensitivity_cohort_ge2,b.sensitivity_cohort_ge5,
        b.baseline_papers,b.known_linked_author_ids,
        CASE WHEN b.fixed_cohort_ge1 THEN 'fixed_baseline_cohort'
          ELSE 'later_only_observed_dynamic_not_backdated' END AS institution_cohort,
        r.first_observed_eligible_year
      FROM institution_registry r LEFT JOIN observed o USING(institution_id)
      JOIN institution_baseline_scale b USING(institution_id)""")
    con.execute("""CREATE TEMP TABLE institution_window_audit AS
      SELECT f.institution_id,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date=f.first_observed_confirmed_date) AS co_initial_studies,
        min(e.event_date) FILTER(WHERE e.confirmed_af AND e.event_date>f.first_observed_confirmed_date) AS next_confirmed_date,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date>f.first_observed_confirmed_date
          AND e.event_date<=DATE '2025-12-31') AS later_confirmed_study_units_until_cutoff,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date>f.first_observed_confirmed_date
          AND e.event_date<=f.first_observed_confirmed_date+INTERVAL '12 months') AS bin1_confirmed_studies,
        count(*) FILTER(WHERE e.confirmed_af AND e.event_date>f.first_observed_confirmed_date+INTERVAL '12 months'
          AND e.event_date<=f.first_observed_confirmed_date+INTERVAL '24 months') AS bin2_confirmed_studies,
        count(*) FILTER(WHERE
          (e.confirmed_af AND e.event_date IS NULL AND e.confirmed_evidence_year<=year(f.first_observed_confirmed_date))
          OR (e.confirmed_af AND e.within_study_first_date_unresolved
            AND e.earliest_undated_confirmed_year<=year(f.first_observed_confirmed_date))
          OR (e.possible_af_only AND (e.event_date<f.first_observed_confirmed_date
            OR (e.event_date IS NULL AND e.earliest_version_evidence_year<=year(f.first_observed_confirmed_date))))
        ) AS first_entry_uncertainty_studies,
        count(*) FILTER(WHERE
          (e.possible_af_only AND e.event_date>f.first_observed_confirmed_date
            AND e.event_date<=f.first_observed_confirmed_date+INTERVAL '24 months'
            AND e.event_date<=DATE '2025-12-31')
          OR ((e.confirmed_af AND e.event_date IS NULL OR e.possible_af_only AND e.event_date IS NULL)
            AND make_date(e.earliest_version_evidence_year,12,31)>f.first_observed_confirmed_date
            AND make_date(e.earliest_version_evidence_year,1,1)<=least(
              CAST(f.first_observed_confirmed_date+INTERVAL '24 months' AS DATE),DATE '2025-12-31'))
          OR (e.undated_confirmed_versions>0 AND e.event_date IS NOT NULL
            AND make_date(e.earliest_undated_confirmed_year,12,31)>f.first_observed_confirmed_date
            AND make_date(e.earliest_undated_confirmed_year,1,1)<=least(
              CAST(f.first_observed_confirmed_date+INTERVAL '24 months' AS DATE),DATE '2025-12-31')
            AND e.event_date<>f.first_observed_confirmed_date)
        ) AS identification_uncertainty_24m_studies
      FROM institution_first_dates f LEFT JOIN institution_study_events e USING(institution_id)
      GROUP BY f.institution_id""")
    con.execute("""CREATE TEMP TABLE institution_participation_history AS
      WITH status AS (
        SELECT f.*,a.co_initial_studies,a.next_confirmed_date,a.later_confirmed_study_units_until_cutoff,
          a.bin1_confirmed_studies,a.bin2_confirmed_studies,a.first_entry_uncertainty_studies,
          a.identification_uncertainty_24m_studies,
          CAST(f.first_observed_confirmed_date+INTERVAL '12 months' AS DATE) AS month12_end,
          CAST(f.first_observed_confirmed_date+INTERVAL '24 months' AS DATE) AS month24_end,
          coalesce(f.first_observed_confirmed_date+INTERVAL '24 months'<=DATE '2025-12-31',false) AS complete_24m_window,
          f.first_observed_confirmed_date IS NOT NULL AND a.first_entry_uncertainty_studies=0 AS first_entry_date_resolved,
          CASE WHEN f.first_observed_confirmed_date IS NOT NULL
            THEN CAST(a.bin1_confirmed_studies>0 AS INTEGER)+CAST(a.bin2_confirmed_studies>0 AS INTEGER)
            END AS observed_interval_count_known_dates
        FROM institution_first_dates f JOIN institution_window_audit a USING(institution_id)
      ), eligible AS (
        SELECT *,first_entry_date_resolved AND NOT pre_main_confirmed_participation
          AND year(first_observed_confirmed_date)>=2020 AND complete_24m_window
          AND identification_uncertainty_24m_studies=0 AS eligible_24m_distribution
        FROM status
      ) SELECT *,eligible_24m_distribution AND fixed_cohort_ge1 AS eligible_24m_fixed_cohort,
        eligible_24m_distribution AND sensitivity_cohort_ge2 AS eligible_24m_sensitivity_ge2,
        eligible_24m_distribution AND sensitivity_cohort_ge5 AS eligible_24m_sensitivity_ge5,
        CASE WHEN eligible_24m_distribution THEN observed_interval_count_known_dates END AS intervals_covered_24m,
        CASE WHEN eligible_24m_distribution THEN observed_interval_count_known_dates=2 END AS sustained_24m,
        CASE WHEN eligible_24m_distribution THEN bin1_confirmed_studies+bin2_confirmed_studies>0 END AS repeated_24m,
        CASE WHEN confirmed_study_units=0 AND possible_only_study_units=0 THEN 'no_confirmed_or_possible_event_observed'
          WHEN confirmed_study_units=0 THEN 'possible_only_no_confirmed_entry'
          WHEN first_observed_confirmed_date IS NULL THEN 'confirmed_entry_date_unavailable'
          WHEN NOT first_entry_date_resolved THEN 'first_entry_identification_or_date_uncertainty'
          WHEN pre_main_confirmed_participation THEN 'pre_main_confirmed_participant_separate_cohort'
          WHEN NOT complete_24m_window THEN 'administrative_right_censoring_24m'
          WHEN identification_uncertainty_24m_studies>0 THEN 'complete_window_event_identification_uncertainty'
          ELSE 'complete_identifiable_main_entry_24m' END AS followup_status,
        DATE '2025-12-31' AS observation_cutoff
      FROM eligible""")
    # All output interval counts are based on dates no later than the fixed publication cutoff.
    checks = check_outputs(con)
    if any(checks.values()):
        raise ValueError(f"Study/history invariant failure: {checks}")
    return {"institution_event_rows": int(scalar(con, "SELECT count(*) FROM institution_study_events")),
            "history_institution_ids": int(scalar(con, "SELECT count(*) FROM institution_participation_history")),
            "complete_identifiable_main_entry_24m_institutions": int(scalar(con, "SELECT count(*) FROM institution_participation_history WHERE eligible_24m_distribution")),
            "fixed_cohort_complete_identifiable_24m_institutions": int(scalar(con, "SELECT count(*) FROM institution_participation_history WHERE eligible_24m_fixed_cohort")),
            "checks": checks}


def check_outputs(con) -> dict:
    queries = {
        "work_map_key_errors": "SELECT count(*)-count(DISTINCT work_id) FROM work_study_map",
        "work_map_orphans": "SELECT count(*) FROM work_study_map m FULL JOIN works_eligible w USING(work_id) WHERE m.work_id IS NULL OR w.work_id IS NULL",
        "study_key_errors": "SELECT count(*)-count(DISTINCT study_id) FROM study_records",
        "study_membership_count_errors": "SELECT count(*) FROM study_records s LEFT JOIN (SELECT study_id,count(*) AS n FROM work_study_map GROUP BY 1) m USING(study_id) WHERE s.member_work_records IS DISTINCT FROM m.n",
        "representative_not_member": "SELECT count(*) FROM study_records s LEFT JOIN work_study_map m ON m.study_id=s.study_id AND m.work_id=s.annual_representative_work_id WHERE m.work_id IS NULL OR s.annual_representative_work_id<>s.citation_representative_work_id",
        "screen_negative_reviewed_leak": "SELECT count(*) FROM study_records s JOIN work_study_map m USING(study_id) JOIN works_eligible w USING(work_id) WHERE s.screen_negative AND w.candidate_reviewed",
        "event_duplicate_keys": "SELECT count(*) FROM (SELECT institution_id,study_id FROM institution_study_events GROUP BY 1,2 HAVING count(*)>1)",
        "event_source_not_observed_member": "SELECT count(*) FROM institution_study_events e LEFT JOIN work_study_map m ON m.study_id=e.study_id AND m.work_id=e.event_source_work_id LEFT JOIN work_institution_membership i ON i.work_id=e.event_source_work_id AND i.institution_id=e.institution_id WHERE m.work_id IS NULL OR i.institution_id IS NULL",
        "event_after_cutoff": "SELECT count(*) FROM institution_study_events WHERE event_date>DATE '2025-12-31'",
        "history_duplicate_ids": "SELECT count(*)-count(DISTINCT institution_id) FROM institution_participation_history",
        "history_registry_mismatch": "SELECT count(*) FROM institution_participation_history h FULL JOIN institution_registry r USING(institution_id) WHERE h.institution_id IS NULL OR r.institution_id IS NULL",
        "cohort_changes": "SELECT count(*) FROM institution_participation_history h JOIN institution_baseline_scale b USING(institution_id) WHERE h.fixed_cohort_ge1 IS DISTINCT FROM b.fixed_cohort_ge1 OR h.sensitivity_cohort_ge2 IS DISTINCT FROM b.sensitivity_cohort_ge2 OR h.sensitivity_cohort_ge5 IS DISTINCT FROM b.sensitivity_cohort_ge5",
        "unobserved_followup_filled_zero": "SELECT count(*) FROM institution_participation_history WHERE first_observed_confirmed_date IS NULL AND (intervals_covered_24m IS NOT NULL OR repeated_24m IS NOT NULL OR sustained_24m IS NOT NULL)",
        "ineligible_followup_scored": "SELECT count(*) FROM institution_participation_history WHERE NOT eligible_24m_distribution AND (intervals_covered_24m IS NOT NULL OR sustained_24m IS NOT NULL OR repeated_24m IS NOT NULL)",
        "followup_eligibility_null": "SELECT count(*) FROM institution_participation_history WHERE eligible_24m_distribution IS NULL OR eligible_24m_fixed_cohort IS NULL",
        "fixed_followup_cohort_errors": "SELECT count(*) FROM institution_participation_history WHERE eligible_24m_fixed_cohort IS DISTINCT FROM (eligible_24m_distribution AND fixed_cohort_ge1) OR eligible_24m_sensitivity_ge2 IS DISTINCT FROM (eligible_24m_distribution AND sensitivity_cohort_ge2) OR eligible_24m_sensitivity_ge5 IS DISTINCT FROM (eligible_24m_distribution AND sensitivity_cohort_ge5)",
        "sustained_definition_errors": "SELECT count(*) FROM institution_participation_history WHERE eligible_24m_distribution AND (intervals_covered_24m IS NULL OR intervals_covered_24m NOT BETWEEN 0 AND 2 OR sustained_24m IS DISTINCT FROM (intervals_covered_24m=2) OR repeated_24m IS DISTINCT FROM (bin1_confirmed_studies+bin2_confirmed_studies>0))",
        "censored_entered_complete_denominator": "SELECT count(*) FROM institution_participation_history WHERE eligible_24m_distribution AND (month24_end>observation_cutoff OR NOT first_entry_date_resolved OR pre_main_confirmed_participation OR identification_uncertainty_24m_studies>0)",
        "next_event_not_strictly_after_initial": "SELECT count(*) FROM institution_participation_history WHERE next_confirmed_date<=first_observed_confirmed_date",
    }
    return {key: int(scalar(con, sql)) for key, sql in queries.items()}
