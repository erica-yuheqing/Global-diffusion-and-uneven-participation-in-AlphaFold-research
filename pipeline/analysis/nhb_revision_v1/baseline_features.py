"""Protocol 1.3 work-level prior foundations, with no outcome-based field selection."""
from __future__ import annotations

from pathlib import Path

from common import (MODULE, SCHEMA, assert_unchanged, literal, read_json, scalar, sha256)

INPUT_TABLES = {
    "works_eligible": {"work_id", "publication_year", "work_type", "period",
                       "primary_subfield_id", "primary_subfield_display_name"},
    "work_institution_membership": {"work_id", "institution_id"},
    "author_institution_membership": {"work_id", "author_id", "institution_id", "country_code"},
    "work_institutions": {"work_id", "institution_id", "country_code"},
    "authorships": {"work_id", "author_id"},
    "institution_registry": {"institution_id", "example_name", "observed_baseline_works"},
}
OUTPUT_TABLES = {
    "institution_baseline_scale": "institution_id",
    "institution_subfield_background": "institution_id,primary_subfield_id NULLS LAST",
    "institution_baseline_partners": "institution_id,partner_institution_id",
    "institution_baseline_collaboration": "institution_id",
    "baseline_subfield_dictionary": "primary_subfield_id NULLS LAST",
}
CONFIG_PATH = MODULE / "baseline_features_config_v1.json"
DECISIONS_PATH = MODULE / "version_decisions_user_v1.json"


def fingerprint(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Expected regular local input: {path}")
    before = path.stat()
    record = {"path": str(path), "size_bytes": before.st_size,
              "mtime_ns": before.st_mtime_ns, "sha256": sha256(path)}
    assert_unchanged([record])
    return record


def check_config(c: dict) -> None:
    expected = {
        "schema_version": "nhb-baseline-features-config-v1", "protocol_version": "1.3",
        "baseline_years": [2015, 2019], "included_types": ["article", "review", "preprint"],
        "primary_subfield_scope": "all_locally_collected_baseline_subfields_no_outcome_selection",
        "institution_paper_counting": "distinct_work_institution_whole_count",
        "author_counting": "distinct_known_author_id_in_observed_author_institution_relation",
        "main_minimum_baseline_works": 1, "sensitivity_minimum_baseline_works": [2, 5],
        "international_pair_rule": "unique_observed_country_per_endpoint_per_work_and_different",
        "no_baseline_features": "NULL_not_true_zero",
        "unit": "work_level_preparation_not_final_independent_study", "formal_models_frozen": False,
    }
    if any(c.get(k) != v for k, v in expected.items()):
        raise ValueError("Feature policy differs from approved protocol 1.3; use a reviewed new version")
    if not 1 <= c.get("max_unordered_pair_work_rows", 0) <= 50000000:
        raise ValueError("Pair-row cap must be 1..50,000,000; do not silently drop large papers")
    if c.get("minimum_free_disk_gib", 0) < 10:
        raise ValueError("Disk safety floor must be at least 10 GiB")


def load_inputs(directory: Path) -> tuple[dict, list[dict]]:
    """Full hashes of selected foundations, metadata/stat checks for upstream raw inputs."""
    import pyarrow.parquet as pq
    manifest_path = directory / "prepare_manifest.json"
    validation_path = directory / "validation_report.json"
    config = read_json(CONFIG_PATH)
    check_config(config)
    protocol = Path(config["protocol_path"])
    inv = [fingerprint(p) for p in (manifest_path, validation_path, CONFIG_PATH, DECISIONS_PATH, protocol)]
    manifest, validation = read_json(manifest_path), read_json(validation_path)
    if (manifest.get("schema_version") != SCHEMA
            or validation.get("schema_version") != "nhb-foundations-validation-v2"
            or not validation.get("work_level_foundations_ready") or validation.get("blockers")
            or validation.get("prepare_manifest_sha256") != inv[0]["sha256"]):
        raise ValueError("Requires validated corrected foundations (out_v2 by default)")
    assert_unchanged(manifest["inputs"])
    decisions = read_json(DECISIONS_PATH)
    template = MODULE / decisions["source_template_relative_path"]
    template_fp = fingerprint(template)
    if (decisions.get("schema_version") != "nhb-version-decisions-user-v1"
            or decisions.get("approval_source") != "user_explicit_adjudication_in_chat"
            or template_fp["sha256"] != decisions["source_template_sha256"]):
        raise ValueError("Version-decision provenance differs from frozen user decision")
    inv.append(template_fp)
    groups = read_json(template)
    coverage_path = MODULE / "coverage_audit_v2" / "coverage_report.json"
    coverage_fp = fingerprint(coverage_path)
    if (groups.get("source_coverage_report_sha256") != coverage_fp["sha256"]
            or decisions["source_coverage_report_sha256"] != coverage_fp["sha256"]):
        raise ValueError("Version decisions and original coverage audit do not match")
    inv.append(coverage_fp)
    coverage = read_json(coverage_path)
    if (coverage.get("prepare_manifest_sha256") != inv[0]["sha256"]
            or coverage.get("validation_report_sha256") != inv[1]["sha256"]):
        raise ValueError("Version review belongs to different foundations/validation")
    # Group text and metadata are data, never executable policy.
    candidates = groups.get("groups", [])
    if not candidates:
        raise ValueError("Version template group list missing")
    by_doi = {g["normalized_doi"]: g for g in candidates}
    approved = {
        "10.1002/pro.5219": (["W4396914184", "W4404444935"],
                            {"af_use_label": "no", "adoption_eligible": "no"}, None, None),
        "10.1101/gad.350914.123": (["W38503515", "W4392937813"], None,
                                 "2024-04-17", "W38503515"),
    }
    if {d["normalized_doi"] for d in decisions["decisions"]} != set(approved) or len(decisions["decisions"]) != 2:
        raise ValueError("Approved version scope differs; requires a new decision version")
    for decision in decisions["decisions"]:
        original = by_doi.get(decision["normalized_doi"])
        if (original is None or sorted(decision["member_work_ids"]) !=
                sorted(m["work_id"] for m in original["members"])):
            raise ValueError("Version member list differs from source template")
        if any(m["publication_year"] < 2020 for m in original["members"]):
            raise ValueError("Baseline version decision requires study-level preparation first")
        if decision["member_years"] != [2024, 2024] or decision["relation"] != "same_study":
            raise ValueError("Unexpected approved decision scope")
        ids, core, date, event = approved[decision["normalized_doi"]]
        if (decision["member_work_ids"] != ids or decision["study_core_decision"] != core
                or decision["event_date_override"] != date or decision["event_date_source_work_id"] != event
                or decision["citation_representative_work_id"] is not None
                or decision["annual_output_representative_work_id"] is not None):
            raise ValueError("Decision fields differ from explicit user approval")
    for name, required in INPUT_TABLES.items():
        path = directory / f"{name}.parquet"
        rec = fingerprint(path)
        expected = manifest["outputs"][path.name]
        pf = pq.ParquetFile(path)
        if (rec["sha256"] != expected["sha256"] or rec["size_bytes"] != expected["size_bytes"]
                or pf.metadata.num_rows != expected["rows"] or not required.issubset(pf.schema_arrow.names)):
            raise ValueError(f"Foundation content/schema differs: {name}")
        rec.update(rows=pf.metadata.num_rows, schema=str(pf.schema_arrow))
        inv.append(rec)
    assert_unchanged(inv)
    return config, inv


def attach_inputs(con, directory: Path) -> None:
    for name in INPUT_TABLES:
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({literal(directory / (name + '.parquet'))})")


def build_features(con, pair_cap: int) -> dict:
    """Only baseline columns enter exposure construction. Registry retains later IDs as unobserved."""
    con.execute("""CREATE TEMP TABLE baseline_works AS
      SELECT work_id,publication_year,NULLIF(trim(primary_subfield_id),'') AS primary_subfield_id,
        primary_subfield_display_name
      FROM works_eligible WHERE period='baseline' AND publication_year BETWEEN 2015 AND 2019
        AND work_type IN ('article','review','preprint')""")
    con.execute("""CREATE TEMP TABLE baseline_members AS
      SELECT DISTINCT i.work_id,i.institution_id,w.publication_year,w.primary_subfield_id
      FROM work_institution_membership i JOIN baseline_works w USING(work_id)""")
    con.execute("""CREATE TEMP TABLE baseline_authors AS
      SELECT DISTINCT a.work_id,a.institution_id,a.author_id,m.primary_subfield_id
      FROM author_institution_membership a JOIN baseline_members m USING(work_id,institution_id)
      WHERE a.author_id IS NOT NULL""")
    con.execute("""CREATE TEMP TABLE baseline_author_coverage AS
      SELECT m.work_id,m.institution_id,
        EXISTS(SELECT 1 FROM baseline_authors a WHERE a.work_id=m.work_id
          AND a.institution_id=m.institution_id) AS institution_author_link_observed,
        EXISTS(SELECT 1 FROM authorships a WHERE a.work_id=m.work_id AND a.author_id IS NULL)
          AS paper_has_missing_author_id,
        NOT EXISTS(SELECT 1 FROM authorships a WHERE a.work_id=m.work_id) AS paper_authorship_absent
      FROM baseline_members m""")
    con.execute("""CREATE TEMP TABLE institution_baseline_scale AS
      WITH papers AS (
        SELECT institution_id,count(*) AS n,min(publication_year) AS first_baseline_year,
          max(publication_year) AS last_baseline_year,count(DISTINCT publication_year) AS observed_baseline_years,
          count(*) FILTER(WHERE primary_subfield_id IS NULL) AS unknown_subfield_works
        FROM baseline_members GROUP BY institution_id
      ), authors AS (
        SELECT institution_id,count(DISTINCT author_id) AS known_author_count
        FROM baseline_authors GROUP BY institution_id
      ), coverage AS (
        SELECT institution_id,count(*) FILTER(WHERE institution_author_link_observed) AS works_with_known_linked_author,
          count(*) FILTER(WHERE paper_has_missing_author_id) AS papers_with_any_missing_author_id,
          count(*) FILTER(WHERE paper_authorship_absent) AS papers_without_authorship_record
        FROM baseline_author_coverage GROUP BY institution_id
      ) SELECT r.institution_id,r.example_name,coalesce(p.n,0) AS observed_baseline_work_records,
        p.n AS baseline_papers,p.first_baseline_year,p.last_baseline_year,p.observed_baseline_years,
        p.unknown_subfield_works,CASE WHEN p.n>0 THEN coalesce(a.known_author_count,0) END AS known_linked_author_ids,
        a.known_author_count AS author_scale_observed_nonzero,
        c.works_with_known_linked_author,c.papers_with_any_missing_author_id,c.papers_without_authorship_record,
        coalesce(p.n>=1,false) AS fixed_cohort_ge1,
        coalesce(p.n>=2,false) AS sensitivity_cohort_ge2,
        coalesce(p.n>=5,false) AS sensitivity_cohort_ge5,
        CASE WHEN p.n IS NULL THEN 'baseline_unobserved_not_true_zero'
          ELSE 'local_baseline_observed_author_and_country_coverage_not_certified_complete' END AS observation_status
      FROM institution_registry r LEFT JOIN papers p USING(institution_id)
      LEFT JOIN authors a USING(institution_id) LEFT JOIN coverage c USING(institution_id)""")
    con.execute("""CREATE TEMP TABLE institution_subfield_background AS
      WITH papers AS (
        SELECT institution_id,primary_subfield_id,count(*) AS subfield_papers
        FROM baseline_members GROUP BY institution_id,primary_subfield_id
      ), authors AS (
        SELECT institution_id,primary_subfield_id,count(DISTINCT author_id) AS known_subfield_author_ids
        FROM baseline_authors GROUP BY institution_id,primary_subfield_id
      ) SELECT p.*,p.primary_subfield_id IS NULL AS subfield_unknown,
        p.subfield_papers*1.0/s.baseline_papers AS paper_share_all_baseline_papers,
        coalesce(a.known_subfield_author_ids,0) AS known_subfield_author_ids,
        CASE WHEN s.known_linked_author_ids>0 THEN coalesce(a.known_subfield_author_ids,0)*1.0/s.known_linked_author_ids
          END AS author_share_known_linked_authors,
        s.known_linked_author_ids AS author_denominator_known_ids
      FROM papers p JOIN institution_baseline_scale s USING(institution_id)
      LEFT JOIN authors a ON p.institution_id=a.institution_id
        AND p.primary_subfield_id IS NOT DISTINCT FROM a.primary_subfield_id""")
    con.execute("""CREATE TEMP TABLE baseline_subfield_dictionary AS
      SELECT primary_subfield_id,min(primary_subfield_display_name) AS example_subfield_name,
        count(DISTINCT primary_subfield_display_name) AS observed_name_variants,count(*) AS baseline_works,
        primary_subfield_id IS NULL AS subfield_unknown
      FROM baseline_works GROUP BY primary_subfield_id""")
    pairs = int(scalar(con, """SELECT coalesce(sum(n*(n-1)//2),0) FROM
      (SELECT work_id,count(*)::BIGINT AS n FROM baseline_members GROUP BY work_id)"""))
    if pairs > pair_cap:
        raise ValueError(f"Baseline unordered pair-work rows {pairs:,} exceed cap {pair_cap:,}; "
                         "review a new bounded plan; no papers silently removed")
    con.execute("""CREATE TEMP TABLE baseline_institution_countries AS
      WITH observed AS (
        SELECT work_id,institution_id,country_code FROM author_institution_membership
        UNION SELECT work_id,institution_id,country_code FROM work_institutions
      ) SELECT m.work_id,m.institution_id,count(DISTINCT o.country_code)
        FILTER(WHERE regexp_full_match(o.country_code,'[A-Z]{2}')) AS observed_country_count,
        min(o.country_code) FILTER(WHERE regexp_full_match(o.country_code,'[A-Z]{2}')) AS observed_country
      FROM baseline_members m LEFT JOIN observed o USING(work_id,institution_id) GROUP BY m.work_id,m.institution_id""")
    con.execute("""CREATE TEMP TABLE baseline_pair_works AS
      SELECT a.work_id,a.institution_id AS left_id,b.institution_id AS right_id,
        a.publication_year,
        ca.observed_country_count=1 AND cb.observed_country_count=1 AS country_comparison_observed,
        CASE WHEN ca.observed_country_count=1 AND cb.observed_country_count=1
          THEN ca.observed_country<>cb.observed_country ELSE false END AS confirmed_international
      FROM baseline_members a JOIN baseline_members b ON a.work_id=b.work_id AND a.institution_id<b.institution_id
      JOIN baseline_institution_countries ca ON ca.work_id=a.work_id AND ca.institution_id=a.institution_id
      JOIN baseline_institution_countries cb ON cb.work_id=b.work_id AND cb.institution_id=b.institution_id""")
    con.execute("""CREATE TEMP VIEW directed_pair_works AS
      SELECT work_id,left_id AS institution_id,right_id AS partner_institution_id,publication_year,
        country_comparison_observed,confirmed_international FROM baseline_pair_works
      UNION ALL SELECT work_id,right_id,left_id,publication_year,country_comparison_observed,confirmed_international
        FROM baseline_pair_works""")
    con.execute("""CREATE TEMP TABLE institution_baseline_partners AS
      SELECT institution_id,partner_institution_id,count(*) AS joint_baseline_work_records,
        min(publication_year) AS first_observed_partnership_year,
        count(*) FILTER(WHERE confirmed_international) AS confirmed_international_work_records,
        count(*) FILTER(WHERE NOT country_comparison_observed) AS country_unknown_or_ambiguous_work_records
      FROM directed_pair_works GROUP BY institution_id,partner_institution_id""")
    con.execute("""CREATE TEMP TABLE institution_baseline_collaboration AS
      WITH partners AS (
        SELECT institution_id,count(*) AS partner_institution_ids,
          count(*) FILTER(WHERE confirmed_international_work_records>0) AS confirmed_international_partner_ids
        FROM institution_baseline_partners GROUP BY institution_id
      ), papers AS (
        SELECT institution_id,count(DISTINCT work_id) AS interinstitutional_work_records,
          count(DISTINCT work_id) FILTER(WHERE confirmed_international) AS confirmed_international_work_records,
          count(DISTINCT work_id) FILTER(WHERE NOT country_comparison_observed) AS country_unknown_or_ambiguous_work_records
        FROM directed_pair_works GROUP BY institution_id
      ) SELECT s.institution_id,
        CASE WHEN s.fixed_cohort_ge1 THEN coalesce(p.partner_institution_ids,0) END AS observed_partner_ids,
        CASE WHEN s.fixed_cohort_ge1 THEN coalesce(p.confirmed_international_partner_ids,0) END AS confirmed_international_partner_ids,
        CASE WHEN s.fixed_cohort_ge1 THEN coalesce(w.interinstitutional_work_records,0) END AS interinstitutional_work_records,
        CASE WHEN s.fixed_cohort_ge1 THEN coalesce(w.confirmed_international_work_records,0) END AS confirmed_international_work_records,
        CASE WHEN s.fixed_cohort_ge1 THEN coalesce(w.country_unknown_or_ambiguous_work_records,0) END AS country_unknown_or_ambiguous_work_records,
        s.observation_status,
        'observed_coaffiliation_lower_bound_not_professional_support_or_complete_partner_census' AS interpretation
      FROM institution_baseline_scale s LEFT JOIN partners p USING(institution_id) LEFT JOIN papers w USING(institution_id)""")
    checks = check_features(con)
    if any(value for value in checks.values()):
        raise ValueError(f"Feature checks failed: {checks}")
    return {"baseline_work_records": scalar(con, "SELECT count(*) FROM baseline_works"),
            "baseline_work_records_with_institution": scalar(con, "SELECT count(DISTINCT work_id) FROM baseline_members"),
            "registry_institutions": scalar(con, "SELECT count(*) FROM institution_baseline_scale"),
            "fixed_cohort_ge1": scalar(con, "SELECT count(*) FROM institution_baseline_scale WHERE fixed_cohort_ge1"),
            "sensitivity_cohort_ge2": scalar(con, "SELECT count(*) FROM institution_baseline_scale WHERE sensitivity_cohort_ge2"),
            "sensitivity_cohort_ge5": scalar(con, "SELECT count(*) FROM institution_baseline_scale WHERE sensitivity_cohort_ge5"),
            "unobserved_baseline_institutions": scalar(con, "SELECT count(*) FROM institution_baseline_scale WHERE NOT fixed_cohort_ge1"),
            "unordered_pair_work_rows": pairs, "checks_nonzero_errors": checks}


def check_features(con) -> dict:
    """Aggregate invariant checks, also run independently on exported tables."""
    queries = {
        "duplicate_scale_keys": "SELECT count(*)-count(DISTINCT institution_id) FROM institution_baseline_scale",
        "duplicate_collaboration_keys": "SELECT count(*)-count(DISTINCT institution_id) FROM institution_baseline_collaboration",
        "duplicate_subfield_keys": "SELECT count(*) FROM (SELECT institution_id,primary_subfield_id FROM institution_subfield_background GROUP BY 1,2 HAVING count(*)>1)",
        "duplicate_partner_keys": "SELECT count(*) FROM (SELECT institution_id,partner_institution_id FROM institution_baseline_partners GROUP BY 1,2 HAVING count(*)>1)",
        "cohort_rule_errors": "SELECT count(*) FROM institution_baseline_scale WHERE fixed_cohort_ge1 IS DISTINCT FROM (observed_baseline_work_records>=1) OR sensitivity_cohort_ge2 IS DISTINCT FROM (observed_baseline_work_records>=2) OR sensitivity_cohort_ge5 IS DISTINCT FROM (observed_baseline_work_records>=5)",
        "unobserved_filled_zero": "SELECT count(*) FROM institution_baseline_scale WHERE NOT fixed_cohort_ge1 AND (baseline_papers IS NOT NULL OR known_linked_author_ids IS NOT NULL OR unknown_subfield_works IS NOT NULL)",
        "paper_partition_errors": "SELECT count(*) FROM institution_baseline_scale s LEFT JOIN (SELECT institution_id,sum(subfield_papers) AS n FROM institution_subfield_background GROUP BY 1) f USING(institution_id) WHERE coalesce(f.n,0)<>s.observed_baseline_work_records",
        "unknown_subfield_partition_errors": "SELECT count(*) FROM institution_baseline_scale s LEFT JOIN (SELECT institution_id,sum(subfield_papers) AS n FROM institution_subfield_background WHERE subfield_unknown GROUP BY 1) f USING(institution_id) WHERE s.fixed_cohort_ge1 AND coalesce(f.n,0)<>s.unknown_subfield_works",
        "invalid_shares": "SELECT count(*) FROM institution_subfield_background WHERE paper_share_all_baseline_papers NOT BETWEEN 0 AND 1 OR author_share_known_linked_authors NOT BETWEEN 0 AND 1 OR subfield_papers<1 OR known_subfield_author_ids<0 OR known_subfield_author_ids>author_denominator_known_ids",
        "paper_share_sum_errors": "SELECT count(*) FROM (SELECT institution_id,sum(paper_share_all_baseline_papers) AS total FROM institution_subfield_background GROUP BY 1 HAVING abs(total-1)>1e-9)",
        "self_or_invalid_pairs": "SELECT count(*) FROM institution_baseline_partners WHERE institution_id=partner_institution_id OR joint_baseline_work_records<1 OR confirmed_international_work_records+country_unknown_or_ambiguous_work_records>joint_baseline_work_records OR first_observed_partnership_year NOT BETWEEN 2015 AND 2019",
        "asymmetric_partner_edges": "SELECT count(*) FROM institution_baseline_partners a LEFT JOIN institution_baseline_partners b ON a.institution_id=b.partner_institution_id AND a.partner_institution_id=b.institution_id WHERE b.institution_id IS NULL OR a.joint_baseline_work_records<>b.joint_baseline_work_records OR a.confirmed_international_work_records<>b.confirmed_international_work_records OR a.country_unknown_or_ambiguous_work_records<>b.country_unknown_or_ambiguous_work_records",
        "collaboration_bound_errors": "SELECT count(*) FROM institution_baseline_collaboration c JOIN institution_baseline_scale s USING(institution_id) WHERE c.confirmed_international_partner_ids>c.observed_partner_ids OR c.confirmed_international_work_records>c.interinstitutional_work_records OR c.interinstitutional_work_records>s.baseline_papers OR (NOT s.fixed_cohort_ge1 AND c.observed_partner_ids IS NOT NULL)",
        "registry_feature_key_errors": "SELECT count(*) FROM institution_baseline_scale s FULL JOIN institution_registry r USING(institution_id) WHERE s.institution_id IS NULL OR r.institution_id IS NULL OR s.observed_baseline_work_records<>r.observed_baseline_works",
    }
    return {key: int(scalar(con, sql)) for key, sql in queries.items()}
