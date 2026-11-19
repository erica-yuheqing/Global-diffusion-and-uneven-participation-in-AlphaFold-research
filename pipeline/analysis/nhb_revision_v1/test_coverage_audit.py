"""Small synthetic tests for coverage and version leads; never reads production data."""
from __future__ import annotations

import unittest

from audit_coverage import audit
from common import connect, scalar
from foundations import EXPORTS
from test_foundations import Foundations


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Foundations.setUpClass()
        cls.con = connect(1, 1)
        for name in EXPORTS:
            cls.con.register("fixture_arrow", Foundations.con.execute(f"SELECT * FROM {name}").fetch_arrow_table())
            cls.con.execute(f"CREATE TABLE {name} AS SELECT * FROM fixture_arrow")
            cls.con.unregister("fixture_arrow")
        # Add one record with no attribution/author/date to distinguish missing from observed zeros.
        cls.con.execute("""INSERT INTO works_eligible
          SELECT * REPLACE('W10' AS work_id, 'Missing metadata fixture' AS title,
            NULL AS publication_date, NULL AS event_date, 'missing' AS date_status)
          FROM works_eligible WHERE work_id='W8'""")
        cls.summary = audit(cls.con)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        Foundations.tearDownClass()

    def cohort(self, name):
        return next(row for row in self.summary["coverage_by_cohort"] if row["audit_cohort"] == name)

    def test_missing_attribution_stays_missing(self):
        row = self.cohort("all_eligible")
        self.assertEqual(row["works"], 9)
        self.assertEqual(row["country_missing_works"], 1)
        self.assertEqual(row["institution_missing_works"], 1)
        self.assertEqual(row["both_missing_works"], 1)

    def test_residual_not_missing_country_or_reallocated(self):
        row = self.cohort("main_confirmed_af")
        self.assertEqual(row["works"], 2)
        self.assertEqual(row["country_missing_works"], 0)
        self.assertAlmostEqual(row["unallocated_institution_country_fractional_sum"], 1.5)

    def test_dates_not_dropped_from_counts(self):
        self.assertEqual(self.cohort("all_eligible")["date_unusable_works"], 4)

    def test_reviewed_no_is_not_screen_negative(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM coverage_groups WHERE audit_cohort='all_eligible' AND work_id='W4'"), 1)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM works_eligible WHERE screen_negative"), 3)
        self.assertFalse(scalar(self.con, "SELECT screen_negative FROM works_eligible WHERE work_id='W4'"))

    def test_version_candidates_never_merge(self):
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM version_review_groups"), 1)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM version_review_members"), 2)
        self.assertEqual(scalar(self.con, "SELECT count(*) FROM works_eligible"), 9)
        self.assertFalse(self.summary["ready_for_auto_merges"])

    def test_review_priority_af_members_not_screen_mix_core_conflict(self):
        self.assertEqual(scalar(self.con, "SELECT review_priority FROM version_review_groups"), "P1_AF_related_version_review")
        self.assertEqual(self.summary["version_same_doi_preprint_formal_groups"], 1)

    def test_action_queue_real_status_and_count(self):
        self.assertEqual(self.summary["action_queue_records"], 1)
        by_status = {r["observed_actions_status"]: r["works"] for r in self.summary["action_status_main_confirmed_af"]}
        self.assertEqual(by_status["disagreement_unadjudicated"], 1)

    def test_unknown_author_rows_not_certified_as_complete(self):
        self.assertEqual(self.cohort("baseline")["any_missing_author_id_works"], 1)
        self.assertFalse(self.summary["ready_for_final_denominator"])


if __name__ == "__main__":
    # Avoid unittest discovering the imported Foundations TestCase a second time.
    unittest.main(defaultTest="CoverageTests")
