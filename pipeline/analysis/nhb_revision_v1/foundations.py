"""Work-level SQL transformations, shared by preparation and small synthetic tests.

No study-version merges, outcome models, API calls or implicit missing-value imputation.
"""
from __future__ import annotations

from common import ACTION_STATUSES, id_expression, literal, scalar

EXPORTS = {
    "works_eligible": "work_id",
    "work_countries": "work_id, country_code",
    "work_institutions": "work_id, country_code, institution_id",
    "work_institution_membership": "work_id, institution_id",
    "country_residuals": "work_id, country_code",
    "country_source_differences": "work_id, country_code",
    "authorships": "work_id, author_id, author_position",
    "author_institution_membership": "work_id, author_id, institution_id, country_code",
    "country_registry": "country_code",
    "institution_registry": "institution_id",
    "country_year": "country_code, publication_year",
    "institution_country_year": "institution_id, country_code, publication_year",
    "institution_work_year": "institution_id, publication_year",
    "af_institution_event_candidates": "institution_id, publication_year, work_id",
    "date_audit": "work_id",
    "version_review_candidates": "normalized_doi, work_id",
    "field_inventory": "primary_subfield_id, primary_topic_id",
    "action_review_queue": "work_id",
}


def require_zero(con, sql: str, label: str) -> None:
    n = scalar(con, sql)
    if n:
        raise ValueError(f"{label}: {n} records; no output published")


def build_works(con, c: dict) -> dict:
    require_zero(con, "SELECT count(*)-count(DISTINCT work_id) FROM master", "Duplicate master work_id")
    require_zero(con, "SELECT count(*) FROM master WHERE work_id IS NULL OR NOT regexp_full_match(work_id, 'W[0-9]+')",
                 "Invalid master work_id")
    require_zero(con, "SELECT count(*) FROM master WHERE candidate_reviewed IS NULL", "Unknown review membership")
    require_zero(con, """SELECT count(*) FROM master WHERE candidate_reviewed AND
        (af_use_label IS NULL OR adoption_eligible IS NULL OR
         af_use_label NOT IN ('yes','no','uncertain') OR adoption_eligible NOT IN ('yes','no','uncertain'))""",
                 "Unsupported reviewed core labels")
    allowed = ",".join(literal(s) for s in ACTION_STATUSES)
    require_zero(con, f"""SELECT count(*) FROM master WHERE candidate_reviewed AND
        (observed_actions_status IS NULL OR observed_actions_status NOT IN ({allowed}))""",
                 "Unknown/missing action status on reviewed records; review source contract")
    con.execute("""CREATE TABLE works_eligible AS
      WITH typed AS (
        SELECT work_id, doi, title, publication_year, publication_date,
          lower(replace(trim(work_type), '_', '-')) AS work_type,
          candidate_reviewed, af_use_label, adoption_eligible, observed_actions_status,
          final_observed_actions, primary_topic_id, primary_topic_display_name,
          primary_subfield_id, primary_subfield_display_name,
          cited_by_count, journal_or_source_id, journal_or_source_name
        FROM master
      ), scoped AS (
        SELECT *, CASE
          WHEN publication_date IS NULL OR trim(publication_date)='' THEN 'missing'
          WHEN NOT regexp_full_match(trim(publication_date), '[0-9]{4}-[0-9]{2}-[0-9]{2}')
            OR try_cast(trim(publication_date) AS DATE) IS NULL THEN 'invalid'
          WHEN year(try_cast(trim(publication_date) AS DATE))<>publication_year THEN 'year_conflict'
          ELSE 'valid' END AS date_status,
          candidate_reviewed AND af_use_label='yes' AND adoption_eligible='yes' AS confirmed_af,
          NOT candidate_reviewed AS screen_negative,
          candidate_reviewed AND af_use_label='no' AS reviewed_non_use,
          candidate_reviewed AND af_use_label='yes' AND adoption_eligible='no' AS use_not_adoption,
          candidate_reviewed AND af_use_label<>'no' AND adoption_eligible<>'no' AND
            (af_use_label='uncertain' OR adoption_eligible='uncertain') AS possible_af,
          CASE WHEN cited_by_count IS NULL THEN 'missing'
               WHEN cited_by_count<0 THEN 'invalid_negative'
               WHEN cited_by_count=0 THEN 'reported_zero_not_independently_verified'
               ELSE 'reported_positive' END AS citation_status
        FROM typed WHERE publication_year BETWEEN 2015 AND 2025
          AND work_type IN ('article','review','preprint')
      ) SELECT *, CASE WHEN date_status='valid' THEN cast(trim(publication_date) AS DATE) END AS event_date,
          CASE WHEN publication_year<=2019 THEN 'baseline' ELSE 'main' END AS period,
          NULLIF(regexp_replace(lower(trim(doi)), '^(https?://(dx[.])?doi[.]org/|doi:[ ]*)', ''), '') AS normalized_doi
        FROM scoped""")
    # Unknown labels on screen-negative works are not turned into AF/no-use claims.
    con.execute("""CREATE TABLE date_audit AS SELECT work_id, publication_year, publication_date,
        date_status, confirmed_af, possible_af FROM works_eligible WHERE date_status<>'valid'""")
    con.execute("""CREATE TABLE version_review_candidates AS
        SELECT w.*, d.member_count, d.has_core_status_conflict, d.has_review_membership_mix,
          'exact_normalized_doi_review_only_not_merged' AS review_reason
        FROM works_eligible w JOIN (
          SELECT normalized_doi, count(*) AS member_count,
            count(DISTINCT CASE WHEN candidate_reviewed
              THEN concat(af_use_label,'/',adoption_eligible) END)>1 AS has_core_status_conflict,
            count(DISTINCT candidate_reviewed)>1 AS has_review_membership_mix
          FROM works_eligible WHERE normalized_doi LIKE '10.%/%'
          GROUP BY normalized_doi HAVING count(*)>1
        ) d USING (normalized_doi)""")
    con.execute("""CREATE TABLE field_inventory AS
      SELECT primary_subfield_id, primary_topic_id,
        min(primary_subfield_display_name) AS subfield_name,
        min(primary_topic_display_name) AS topic_name,
        count(*) AS eligible_works,
        count(*) FILTER (WHERE period='baseline') AS baseline_works,
        count(*) FILTER (WHERE period='main') AS main_works,
        count(*) FILTER (WHERE period='main' AND confirmed_af) AS confirmed_af_main_works
      FROM works_eligible GROUP BY primary_subfield_id, primary_topic_id""")
    con.execute("""CREATE TABLE action_review_queue AS SELECT work_id, publication_year, title,
      observed_actions_status, final_observed_actions FROM works_eligible
      WHERE period='main' AND confirmed_af AND observed_actions_status='disagreement_unadjudicated'""")
    return {
        "master_records": scalar(con, "SELECT count(*) FROM master"),
        "eligible_work_records": scalar(con, "SELECT count(*) FROM works_eligible"),
        "baseline_work_records": scalar(con, "SELECT count(*) FROM works_eligible WHERE period='baseline'"),
        "main_work_records": scalar(con, "SELECT count(*) FROM works_eligible WHERE period='main'"),
        "confirmed_af_main_work_records": scalar(con, "SELECT count(*) FROM works_eligible WHERE period='main' AND confirmed_af"),
        "screen_negative_work_records": scalar(con, "SELECT count(*) FROM works_eligible WHERE screen_negative"),
        "action_review_work_records": scalar(con, "SELECT count(*) FROM action_review_queue"),
        "duplicate_doi_candidate_work_records": scalar(con, "SELECT count(*) FROM version_review_candidates"),
        "action_status_counts_all_reviewed": dict(con.execute("SELECT observed_actions_status,count(*) FROM master WHERE candidate_reviewed GROUP BY 1").fetchall()),
        "action_status_counts_main_confirmed_af": dict(con.execute("SELECT observed_actions_status,count(*) FROM works_eligible WHERE period='main' AND confirmed_af GROUP BY 1").fetchall()),
    }


def build_relations(con, c: dict) -> dict:
    wid = id_expression("work_id", "W")
    iid = id_expression("institution_id", "I")
    aid = id_expression("author_id", "A")
    # Preserve an invalid-code count; only syntactically valid observed codes can receive weights.
    for source, table in (("countries_raw", "country_raw_normalized"), ("institutions_raw", "institution_raw_normalized")):
        extra = ", CAST(country_source AS VARCHAR) AS country_source" if source == "countries_raw" else (
            f", {iid} AS institution_id, CAST(institution_name AS VARCHAR) AS institution_name, {aid} AS author_id")
        con.execute(f"""CREATE VIEW {table} AS SELECT {wid} AS work_id,
          NULLIF(upper(trim(CAST(country_code AS VARCHAR))), '') AS country_code {extra} FROM {source}""")
        require_zero(con, f"SELECT count(*) FROM {table} WHERE work_id IS NULL", f"Invalid work IDs in {source}")
    con.execute("""CREATE TABLE author_country_pairs AS SELECT DISTINCT a.work_id, a.country_code
      FROM country_raw_normalized a JOIN works_eligible w USING(work_id)
      WHERE regexp_full_match(a.country_code, '[A-Z]{2}')""")
    con.execute("""CREATE TABLE institution_country_pairs AS SELECT DISTINCT a.work_id, a.country_code
      FROM institution_raw_normalized a JOIN works_eligible w USING(work_id)
      WHERE regexp_full_match(a.country_code, '[A-Z]{2}')""")
    con.execute("""CREATE TABLE work_countries AS
      WITH preferred AS (
        SELECT work_id, country_code, 'authorship_countries_table' AS assignment_source FROM author_country_pairs
        UNION ALL SELECT i.work_id, i.country_code, 'whole_work_institution_fallback'
          FROM institution_country_pairs i WHERE NOT EXISTS
            (SELECT 1 FROM author_country_pairs a WHERE a.work_id=i.work_id)
      ) SELECT *, count(*) OVER (PARTITION BY work_id) AS n_countries,
        1.0/count(*) OVER (PARTITION BY work_id) AS country_weight FROM preferred""")
    con.execute("""CREATE TABLE country_source_differences AS
      SELECT coalesce(a.work_id,i.work_id) AS work_id, coalesce(a.country_code,i.country_code) AS country_code,
        a.work_id IS NOT NULL AS in_authorship_set, i.work_id IS NOT NULL AS in_institution_set
      FROM author_country_pairs a FULL OUTER JOIN institution_country_pairs i USING(work_id,country_code)
      WHERE a.work_id IS NULL OR i.work_id IS NULL""")
    con.execute("""CREATE TABLE work_institution_membership AS
      SELECT DISTINCT r.work_id, r.institution_id
      FROM institution_raw_normalized r JOIN works_eligible w USING(work_id)
      WHERE r.institution_id IS NOT NULL""")
    con.execute("""CREATE TABLE work_institutions AS
      WITH distinct_pairs AS (
        SELECT DISTINCT r.work_id, r.institution_id, r.country_code
        FROM institution_raw_normalized r JOIN work_countries c USING(work_id,country_code)
        WHERE r.institution_id IS NOT NULL
      ) SELECT p.*, c.assignment_source, c.country_weight,
        count(*) OVER(PARTITION BY p.work_id,p.country_code) AS n_institutions_in_country,
        c.country_weight/count(*) OVER(PARTITION BY p.work_id,p.country_code) AS institution_weight
        FROM distinct_pairs p JOIN work_countries c USING(work_id,country_code)""")
    con.execute("""CREATE TABLE country_residuals AS
      SELECT c.work_id,c.country_code,c.country_weight,
        coalesce(i.allocated_weight,0.0) AS allocated_weight,
        c.country_weight-coalesce(i.allocated_weight,0.0) AS residual_weight,
        CASE WHEN i.work_id IS NULL THEN 'no_matched_valid_institution' ELSE 'allocated' END AS allocation_status
      FROM work_countries c LEFT JOIN (
        SELECT work_id,country_code,sum(institution_weight) AS allocated_weight
        FROM work_institutions GROUP BY work_id,country_code
      ) i USING(work_id,country_code)""")
    con.execute(f"""CREATE TABLE authorships AS
      SELECT DISTINCT {wid} AS work_id, {aid} AS author_id,
        lower(trim(CAST(author_position AS VARCHAR))) AS author_position, is_corresponding
      FROM authors_raw a WHERE {wid} IN (SELECT work_id FROM works_eligible)""")
    con.execute("""CREATE TABLE author_institution_membership AS
      SELECT DISTINCT r.work_id,r.author_id,r.institution_id,r.country_code
      FROM institution_raw_normalized r JOIN works_eligible w USING(work_id)
      WHERE r.author_id IS NOT NULL AND r.institution_id IS NOT NULL""")
    con.execute("""CREATE TABLE country_registry AS
      SELECT country_code, 'observed_two_letter_code_not_external_economy_mapping' AS code_status FROM (
        SELECT r.country_code FROM country_raw_normalized r JOIN master w USING(work_id)
          WHERE regexp_full_match(r.country_code,'[A-Z]{2}')
        UNION SELECT r.country_code FROM institution_raw_normalized r JOIN master w USING(work_id)
          WHERE regexp_full_match(r.country_code,'[A-Z]{2}')
      )""")
    threshold = int(c["potential_institution_active_rule"]["minimum_observed_baseline_works"])
    if threshold < 1:
        raise ValueError("Baseline active-rule threshold must be positive")
    con.execute(f"""CREATE TABLE institution_registry AS
      WITH names AS (
        SELECT r.institution_id,min(r.institution_name) AS example_name,
          count(DISTINCT r.institution_name) AS observed_name_count
        FROM institution_raw_normalized r JOIN works_eligible w USING(work_id)
        WHERE r.institution_id IS NOT NULL GROUP BY r.institution_id
      ), coverage AS (
        SELECT i.institution_id, min(w.publication_year) AS first_observed_eligible_year,
          count(*) FILTER(WHERE w.period='baseline') AS observed_baseline_works
        FROM work_institution_membership i JOIN works_eligible w USING(work_id) GROUP BY i.institution_id
      ) SELECT n.*,v.first_observed_eligible_year,v.observed_baseline_works,
        v.observed_baseline_works>={threshold} AS provisional_baseline_active,
        CASE WHEN v.observed_baseline_works>0 THEN 'baseline_observed'
          ELSE 'baseline_not_observed_not_proof_of_true_zero' END AS baseline_observation_status
      FROM names n JOIN coverage v USING(institution_id)""")
    return {
        "country_codes_in_master_source_relations": scalar(con, "SELECT count(*) FROM country_registry"),
        "institution_ids_in_eligible_source_relations": scalar(con, "SELECT count(*) FROM institution_registry"),
        "eligible_works_without_country_assignment": scalar(con, "SELECT count(*) FROM works_eligible w WHERE NOT EXISTS (SELECT 1 FROM work_countries c WHERE c.work_id=w.work_id)"),
        "eligible_works_without_valid_institution": scalar(con, "SELECT count(*) FROM works_eligible w WHERE NOT EXISTS (SELECT 1 FROM work_institution_membership i WHERE i.work_id=w.work_id)"),
        "whole_work_country_fallbacks": scalar(con, "SELECT count(DISTINCT work_id) FROM work_countries WHERE assignment_source='whole_work_institution_fallback'"),
        "country_pairs_with_unallocated_institution_share": scalar(con, "SELECT count(*) FROM country_residuals WHERE allocation_status='no_matched_valid_institution'"),
        "invalid_country_source_rows": scalar(con, "SELECT count(*) FROM country_raw_normalized WHERE country_code IS NOT NULL AND NOT regexp_full_match(country_code,'[A-Z]{2}')"),
        "invalid_institution_country_source_rows": scalar(con, "SELECT count(*) FROM institution_raw_normalized WHERE country_code IS NOT NULL AND NOT regexp_full_match(country_code,'[A-Z]{2}')"),
        "source_authorship_country_provenance": dict(con.execute("SELECT coalesce(country_source,'missing'),count(*) FROM country_raw_normalized GROUP BY 1").fetchall()),
        "invalid_or_missing_authorship_author_ids": scalar(con, "SELECT count(*) FROM authorships WHERE author_id IS NULL"),
        "invalid_or_missing_raw_authorship_work_ids": scalar(con, f"SELECT count(*) FROM authors_raw WHERE {wid} IS NULL"),
        "source_authorship_country_orphans_outside_master": scalar(con, "SELECT count(*) FROM country_raw_normalized r WHERE NOT EXISTS(SELECT 1 FROM master w WHERE w.work_id=r.work_id)"),
        "source_institution_orphans_outside_master": scalar(con, "SELECT count(*) FROM institution_raw_normalized r WHERE NOT EXISTS(SELECT 1 FROM master w WHERE w.work_id=r.work_id)"),
        "authorship_country_rows_outside_eligible_scope": scalar(con, "SELECT count(*) FROM country_raw_normalized r WHERE NOT EXISTS(SELECT 1 FROM works_eligible w WHERE w.work_id=r.work_id)"),
        "institution_rows_outside_eligible_scope": scalar(con, "SELECT count(*) FROM institution_raw_normalized r WHERE NOT EXISTS(SELECT 1 FROM works_eligible w WHERE w.work_id=r.work_id)"),
    }


def build_panels(con) -> None:
    # This is an observed-work audit panel, NOT a final deduplicated-study result.
    con.execute("""CREATE TABLE country_year AS
      WITH totals AS (
        SELECT c.country_code,w.publication_year,count(*) AS eligible_works,
          sum(c.country_weight) AS eligible_fractional,
          count(*) FILTER(WHERE w.confirmed_af) AS confirmed_af_works,
          sum(CASE WHEN w.confirmed_af THEN c.country_weight ELSE 0 END) AS confirmed_af_fractional,
          count(*) FILTER(WHERE w.screen_negative) AS screen_negative_works,
          sum(CASE WHEN w.screen_negative THEN c.country_weight ELSE 0 END) AS screen_negative_fractional,
          count(*) FILTER(WHERE w.possible_af) AS possible_af_works
        FROM work_countries c JOIN works_eligible w USING(work_id) GROUP BY c.country_code,w.publication_year
      ) SELECT r.country_code,y.publication_year,
        coalesce(t.eligible_works,0) AS eligible_works,coalesce(t.eligible_fractional,0.0) AS eligible_fractional,
        coalesce(t.confirmed_af_works,0) AS confirmed_af_works,coalesce(t.confirmed_af_fractional,0.0) AS confirmed_af_fractional,
        coalesce(t.screen_negative_works,0) AS screen_negative_works,coalesce(t.screen_negative_fractional,0.0) AS screen_negative_fractional,
        coalesce(t.possible_af_works,0) AS possible_af_works,
        'observed_assigned_work_counts_not_verified_national_zero' AS count_interpretation
      FROM country_registry r CROSS JOIN (SELECT range AS publication_year FROM range(2015,2026)) y
      LEFT JOIN totals t USING(country_code,publication_year)""")
    con.execute("""CREATE TABLE institution_country_year AS
      SELECT i.institution_id,i.country_code,w.publication_year,count(*) AS eligible_works,
        sum(i.institution_weight) AS eligible_fractional,
        count(*) FILTER(WHERE w.confirmed_af) AS confirmed_af_works,
        sum(CASE WHEN w.confirmed_af THEN i.institution_weight ELSE 0 END) AS confirmed_af_fractional,
        count(*) FILTER(WHERE w.screen_negative) AS screen_negative_works,
        sum(CASE WHEN w.screen_negative THEN i.institution_weight ELSE 0 END) AS screen_negative_fractional
      FROM work_institutions i JOIN works_eligible w USING(work_id)
      GROUP BY i.institution_id,i.country_code,w.publication_year""")
    con.execute("""CREATE TABLE institution_work_year AS
      SELECT i.institution_id,w.publication_year,count(*) AS eligible_works,
        count(*) FILTER(WHERE w.confirmed_af) AS confirmed_af_works,
        count(*) FILTER(WHERE w.possible_af) AS possible_af_works,
        count(*) FILTER(WHERE w.screen_negative) AS screen_negative_works
      FROM work_institution_membership i JOIN works_eligible w USING(work_id)
      GROUP BY i.institution_id,w.publication_year""")
    # Membership is separate from fractional attribution. A missing country must not erase a timed event.
    con.execute("""CREATE TABLE af_institution_event_candidates AS
      SELECT i.institution_id,w.work_id,w.publication_year,w.event_date,w.date_status,w.period,
        w.confirmed_af,w.possible_af,
        'work_level_not_yet_study_deduplicated' AS event_unit_status
      FROM work_institution_membership i JOIN works_eligible w USING(work_id)
      WHERE w.confirmed_af OR w.possible_af""")


def checks(con, tolerance: float) -> list[dict]:
    tests = {
        "eligible_ids_unique": "SELECT count(*)-count(DISTINCT work_id) FROM works_eligible",
        "country_keys_unique": "SELECT count(*) FROM (SELECT work_id,country_code FROM work_countries GROUP BY ALL HAVING count(*)>1)",
        "institution_country_keys_unique": "SELECT count(*) FROM (SELECT work_id,country_code,institution_id FROM work_institutions GROUP BY ALL HAVING count(*)>1)",
        "institution_membership_keys_unique": "SELECT count(*) FROM (SELECT work_id,institution_id FROM work_institution_membership GROUP BY ALL HAVING count(*)>1)",
        "country_weight_conservation": f"SELECT count(*) FROM (SELECT work_id FROM work_countries GROUP BY work_id HAVING abs(sum(country_weight)-1.0)>{tolerance})",
        "nested_weight_and_residual_conservation": f"SELECT count(*) FROM country_residuals WHERE abs(allocated_weight+residual_weight-country_weight)>{tolerance} OR residual_weight < -{tolerance}",
        "nested_allocation_per_country": f"SELECT count(*) FROM country_residuals WHERE allocation_status='allocated' AND abs(allocated_weight-country_weight)>{tolerance}",
        "residual_agrees_with_actual_institution_weights": f"SELECT count(*) FROM country_residuals r LEFT JOIN (SELECT work_id,country_code,sum(institution_weight) AS total FROM work_institutions GROUP BY work_id,country_code) i USING(work_id,country_code) WHERE abs(r.allocated_weight-coalesce(i.total,0))>{tolerance}",
        "institution_nested_formula": f"SELECT count(*) FROM work_institutions WHERE abs(institution_weight-country_weight/n_institutions_in_country)>{tolerance}",
        "positive_weights": "SELECT count(*) FROM work_institutions WHERE institution_weight<=0 OR institution_weight IS NULL",
        "matched_institution_country_only": "SELECT count(*) FROM work_institutions i WHERE NOT EXISTS (SELECT 1 FROM work_countries c WHERE c.work_id=i.work_id AND c.country_code=i.country_code)",
        "af_core_two_yes": "SELECT count(*) FROM works_eligible WHERE confirmed_af AND (NOT candidate_reviewed OR af_use_label<>'yes' OR adoption_eligible<>'yes')",
        "af_definition_complete": "SELECT count(*) FROM works_eligible WHERE confirmed_af IS DISTINCT FROM (candidate_reviewed AND af_use_label='yes' AND adoption_eligible='yes')",
        "comparator_disjoint_from_reviewed": "SELECT count(*) FROM works_eligible WHERE screen_negative AND candidate_reviewed",
        "comparator_definition_complete": "SELECT count(*) FROM works_eligible WHERE screen_negative IS DISTINCT FROM (NOT candidate_reviewed)",
        "year_and_type_scope": "SELECT count(*) FROM works_eligible WHERE publication_year NOT BETWEEN 2015 AND 2025 OR work_type NOT IN ('article','review','preprint') OR publication_year IS NULL OR work_type IS NULL",
        "dates_not_silently_coerced": "SELECT count(*) FROM works_eligible WHERE (date_status='valid')<>(event_date IS NOT NULL)",
        "valid_date_year_matches": "SELECT count(*) FROM works_eligible WHERE event_date IS NOT NULL AND year(event_date)<>publication_year",
        "event_candidates_distinct": "SELECT count(*) FROM (SELECT institution_id,work_id FROM af_institution_event_candidates GROUP BY ALL HAVING count(*)>1)",
        "event_membership_matches_observed_institutions": "SELECT count(*) FROM af_institution_event_candidates e WHERE NOT EXISTS(SELECT 1 FROM work_institution_membership i WHERE i.work_id=e.work_id AND i.institution_id=e.institution_id)",
        "country_panel_unique": "SELECT count(*) FROM (SELECT country_code,publication_year FROM country_year GROUP BY ALL HAVING count(*)>1)",
        "country_panel_grid": "SELECT abs((SELECT count(*) FROM country_year)-11*(SELECT count(*) FROM country_registry))",
        "panel_eligible_fractional_conservation": f"SELECT CASE WHEN abs((SELECT coalesce(sum(eligible_fractional),0) FROM country_year)-(SELECT count(DISTINCT work_id) FROM work_countries))>{tolerance}*greatest(1,(SELECT count(DISTINCT work_id) FROM work_countries)) THEN 1 ELSE 0 END",
        "panel_af_fractional_conservation": f"SELECT CASE WHEN abs((SELECT coalesce(sum(confirmed_af_fractional),0) FROM country_year)-(SELECT count(DISTINCT c.work_id) FROM work_countries c JOIN works_eligible w USING(work_id) WHERE w.confirmed_af))>{tolerance}*greatest(1,(SELECT count(*) FROM works_eligible)) THEN 1 ELSE 0 END",
        "reviewed_action_status_vocabulary": "SELECT count(*) FROM works_eligible WHERE candidate_reviewed AND (observed_actions_status IS NULL OR observed_actions_status NOT IN ('ab_exact_consensus','adjudicated','disagreement_unadjudicated','not_assessed_insufficient_evidence'))",
        "action_queue_scope": "SELECT count(*) FROM action_review_queue q JOIN works_eligible w USING(work_id) WHERE NOT w.confirmed_af OR w.period<>'main' OR w.observed_actions_status<>'disagreement_unadjudicated'",
        "action_queue_complete": "SELECT count(*) FROM works_eligible w WHERE w.period='main' AND w.confirmed_af AND w.observed_actions_status='disagreement_unadjudicated' AND NOT EXISTS(SELECT 1 FROM action_review_queue q WHERE q.work_id=w.work_id)",
        "action_queue_unique": "SELECT count(*)-count(DISTINCT work_id) FROM action_review_queue",
        "action_queue_no_orphan": "SELECT count(*) FROM action_review_queue q WHERE NOT EXISTS(SELECT 1 FROM works_eligible w WHERE w.work_id=q.work_id)",
    }
    report = []
    for name, query in tests.items():
        n = int(scalar(con, query))
        report.append({"check": name, "violations": n, "passed": n == 0})
    return report


def build(con, c: dict) -> tuple[dict, list[dict]]:
    counts = build_works(con, c)
    counts.update(build_relations(con, c))
    build_panels(con)
    report = checks(con, c["weight_tolerance"])
    failed = [x for x in report if not x["passed"]]
    if failed:
        raise ValueError(f"Foundation checks failed: {failed}")
    return counts, report
