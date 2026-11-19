"""Synthetic/local tests only. No production source reads and no network calls."""
from __future__ import annotations

import unittest
from datetime import date

from common import checked_date, config, connect, normalize_id, scalar
from foundations import EXPORTS, build, build_works, checks


class Helpers(unittest.TestCase):
    def test_ids_accept_exact_local_and_url(self):
        self.assertEqual(normalize_id(" https://openalex.org/W123 ", "W"), "W123")
        self.assertEqual(normalize_id("I8", "I"), "I8")

    def test_ids_do_not_salvage_substrings(self):
        for value in ("bad-W123", "https://example.org/W123", "W123/", "W123x", None):
            self.assertIsNone(normalize_id(value, "W"))

    def test_dates_january_first_not_automatically_excluded(self):
        self.assertEqual(checked_date("2020-01-01", 2020), (date(2020, 1, 1), "valid"))

    def test_invalid_and_conflicting_dates_stay_unknown(self):
        self.assertEqual(checked_date("2020-02-30", 2020), (None, "invalid"))
        self.assertEqual(checked_date("2020-12-31", 2021), (None, "year_conflict"))
        self.assertEqual(checked_date(None, 2021), (None, "missing"))
        self.assertEqual(checked_date("2020-1-1", 2020), (None, "invalid"))


class Foundations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = connect(1, 1)
        cls.con.execute("""CREATE TABLE master (
          work_id VARCHAR,doi VARCHAR,title VARCHAR,publication_year BIGINT,publication_date VARCHAR,
          work_type VARCHAR,candidate_reviewed BOOLEAN,af_use_label VARCHAR,adoption_eligible VARCHAR,
          observed_actions_status VARCHAR,final_observed_actions VARCHAR,primary_topic_id VARCHAR,
          primary_topic_display_name VARCHAR,primary_subfield_id VARCHAR,primary_subfield_display_name VARCHAR,
          cited_by_count BIGINT,journal_or_source_id VARCHAR,journal_or_source_name VARCHAR)""")
        records = [
            ("W1", "https://doi.org/10.1/duplicate", 2020, "2020-01-01", "article", True, "yes", "yes", "disagreement_unadjudicated"),
            ("W2", "10.1/b", 2019, "2019-1-1", "article", False, None, None, None),
            ("W3", "10.1/c", 2021, None, "review", True, "uncertain", "uncertain", "not_assessed_insufficient_evidence"),
            ("W4", "10.1/d", 2018, "2018-02-28", "article", True, "no", "no", "ab_exact_consensus"),
            ("W5", "10.1/e", 2021, "2020-01-01", "article", True, "yes", "no", "adjudicated"),
            ("W6", "10.1/f", 2022, "2022-01-01", "article", True, "yes", "yes", "adjudicated"),
            ("W7", "10.1/g", 2017, "2017-05-01", "article", True, "yes", "yes", "adjudicated"),
            ("W8", "DOI:10.1/duplicate", 2019, "2019-05-01", "preprint", False, None, None, None),
            ("W9", "10.1/i", 2020, "2020-06-01", "editorial", False, None, None, None),
        ]
        for wid, doi, year, dt, kind, reviewed, use, adopt, action in records:
            cls.con.execute("INSERT INTO master VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            [wid, doi, wid, year, dt, kind, reviewed, use, adopt, action,
                             None, "T1", "Example topic", "S1", "Example subfield", 0, "S2", "Source"])
        cls.con.execute("""CREATE TABLE countries_raw(work_id VARCHAR,country_code VARCHAR,country_source VARCHAR);
          INSERT INTO countries_raw VALUES
          ('https://openalex.org/W1','US','authorship_countries_field'),
          ('W1','gb','authorship_countries_field'),('W1','US','authorship_countries_field'),
          ('W2',NULL,'missing'),('W3','GB','authorship_countries_field'),
          ('W4','US','authorship_countries_field'),('W5','US','authorship_countries_field'),
          ('W6','RU','authorship_countries_field'),('W7','JP','authorship_countries_field'),
          ('W8','US','authorship_countries_field'),('W9','XK','authorship_countries_field')""")
        cls.con.execute("""CREATE TABLE institutions_raw(work_id VARCHAR,author_id VARCHAR,institution_id VARCHAR,
          institution_name VARCHAR,country_code VARCHAR);
          INSERT INTO institutions_raw VALUES
          ('W1','A1','I1','One','US'),('W1','A2','I2','Two','US'),('W1','A2','I2','Two','US'),
          ('W1','A3','I3','Country mismatch','JP'),('W2','A1','I1','One renamed','US'),
          ('W3','A4','I4','Four','GB'),('W4','A1','I1','One','US'),('W5','A5','I5','Five','US'),
          ('W6','A6','I6','Country unknown',NULL),('W7','A7','I7','Seven','JP'),('W8','A1','I1','One','US')""")
        cls.con.execute("""CREATE TABLE authors_raw(work_id VARCHAR,author_id VARCHAR,author_position VARCHAR,is_corresponding BOOLEAN);
          INSERT INTO authors_raw VALUES ('W1','A1','first',false),('W1','A2','last',true),
          ('W6','A6','first',true),('W7',NULL,'first',false)""")
        cls.counts, cls.report = build(cls.con, config())

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_all_internal_checks_pass(self):
        self.assertTrue(all(x["passed"] for x in self.report))

    def test_period_and_document_types_not_old_2019_main(self):
        self.assertEqual(self.counts["eligible_work_records"], 8)
        self.assertEqual(self.counts["confirmed_af_main_work_records"], 2)
        self.assertEqual(scalar(self.con, "SELECT period FROM works_eligible WHERE work_id='W2'"), "baseline")

    def test_two_yes_rule_and_screen_negative_disjoint(self):
        self.assertFalse(scalar(self.con, "SELECT confirmed_af FROM works_eligible WHERE work_id='W5'"))
        self.assertFalse(scalar(self.con, "SELECT screen_negative FROM works_eligible WHERE work_id='W4'"))
        self.assertTrue(scalar(self.con, "SELECT possible_af FROM works_eligible WHERE work_id='W3'"))

    def test_nested_weights_and_residual_not_renormalized(self):
        self.assertAlmostEqual(scalar(self.con, "SELECT institution_weight FROM work_institutions WHERE work_id='W1' AND institution_id='I1'"), .25)
        self.assertAlmostEqual(scalar(self.con, "SELECT residual_weight FROM country_residuals WHERE work_id='W1' AND country_code='GB'"), .5)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM work_institutions WHERE work_id='W1' AND country_code='JP'"), 0)

    def test_country_whole_work_fallback(self):
        self.assertEqual(scalar(self.con, "SELECT assignment_source FROM work_countries WHERE work_id='W2'"), "whole_work_institution_fallback")

    def test_event_membership_survives_missing_country(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM af_institution_event_candidates WHERE work_id='W6' AND institution_id='I6'"), 1)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM work_institutions WHERE work_id='W6'"), 0)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM af_institution_event_candidates WHERE period='baseline'"), 1)

    def test_regions_kept_no_rd_filter(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM country_registry WHERE country_code='XK'"), 1)

    def test_versions_not_automatically_merged(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM version_review_candidates"), 2)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM works_eligible WHERE work_id IN ('W1','W8')"), 2)
        self.assertFalse(scalar(self.con, "SELECT has_core_status_conflict FROM version_review_candidates WHERE work_id='W1'"))
        self.assertTrue(scalar(self.con, "SELECT has_review_membership_mix FROM version_review_candidates WHERE work_id='W1'"))

    def test_institution_names_do_not_define_identity(self):
        self.assertEqual(scalar(self.con, "SELECT observed_name_count FROM institution_registry WHERE institution_id='I1'"), 2)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM institution_registry WHERE institution_id='I1'"), 1)

    def test_missing_dates_not_removed_from_annual_scope(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM works_eligible WHERE work_id='W3'"), 1)
        self.assertEqual(scalar(self.con, "SELECT date_status FROM works_eligible WHERE work_id='W5'"), "year_conflict")

    def test_action_queue_only_main_confirmed_unadjudicated(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM action_review_queue"), 1)
        self.assertEqual(scalar(self.con, "SELECT work_id FROM action_review_queue"), "W1")

    def test_action_status_histogram_and_queue_agree(self):
        self.assertEqual(self.counts["action_status_counts_main_confirmed_af"]["disagreement_unadjudicated"], 1)
        self.assertEqual(self.counts["action_review_work_records"], 1)

    def test_missing_queue_member_is_a_blocker(self):
        con = connect(1, 1)
        try:
            # Separate in-memory copies: never mutate the shared fixture or production data.
            for name in EXPORTS:
                rows = self.con.execute(f"SELECT * FROM {name}").fetch_arrow_table()
                con.register("fixture_arrow", rows)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM fixture_arrow")
                con.unregister("fixture_arrow")
            con.execute("DELETE FROM action_review_queue WHERE work_id='W1'")
            result = {r["check"]: r for r in checks(con, config()["weight_tolerance"])}
            self.assertFalse(result["action_queue_complete"]["passed"])
        finally:
            con.close()

    def test_unknown_action_status_fails_closed(self):
        con = connect(1, 1)
        try:
            con.register("fixture_arrow", self.con.execute("SELECT * FROM master").fetch_arrow_table())
            con.execute("CREATE TABLE master AS SELECT * FROM fixture_arrow")
            con.execute("UPDATE master SET observed_actions_status='ab_action_disagreement_unadjudicated' WHERE work_id='W1'")
            with self.assertRaisesRegex(ValueError, "Unknown/missing action status"):
                build_works(con, config())
        finally:
            con.close()

    def test_null_reviewed_action_status_fails_closed(self):
        con = connect(1, 1)
        try:
            con.register("fixture_arrow", self.con.execute("SELECT * FROM master").fetch_arrow_table())
            con.execute("CREATE TABLE master AS SELECT * FROM fixture_arrow")
            con.execute("UPDATE master SET observed_actions_status=NULL WHERE work_id='W1'")
            with self.assertRaisesRegex(ValueError, "Unknown/missing action status"):
                build_works(con, config())
        finally:
            con.close()

    def test_reported_zero_citations_not_certified_true_zero(self):
        self.assertEqual(scalar(self.con, "SELECT citation_status FROM works_eligible WHERE work_id='W1'"), "reported_zero_not_independently_verified")


if __name__ == "__main__":
    unittest.main()
