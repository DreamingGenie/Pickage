import copy
import unittest

from .real_rollups import assess_rollups


class RealRollupTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {"executions": [
            {"dataset": "package-version", "status": "PUBLISHED", "actual_counts": {"package": 1, "version": 2}},
            {"dataset": "package-snapshot", "status": "PUBLISHED", "snapshot_at": "2026-01-01", "actual_counts": {"package_snapshot": 1}},
            {"dataset": "version-dependents", "status": "PUBLISHED", "snapshot_at": "2026-01-01", "actual_counts": {"package_version_snapshot": 2},
             "input_metadata": {"quality": {"zero_target_versions": 1, "positive_target_versions": 1, "distinct_edges": 3, "max_dependents_count": 3}}}]}
        self.scans = {"package": {"rows": 1, "invalid": 0}, "version": {"rows": 2, "invalid": 0},
                      "package_snapshot": [{"snapshot_at": "2026-01-01", "rows": 1, "invalid": 0, "downloads_nonnull": 0, "downloads_sum": None,
                                            "stars_nonnull": 1, "stars_sum": "0", "open_issues_nonnull": 1, "open_issues_sum": "3"}],
                      "package_version_snapshot": [{"snapshot_at": "2026-01-01", "rows": 2, "invalid": 0, "zero_rows": 1, "positive_rows": 1, "dependents_sum": "3", "max_dependents": 3}]}
        self.sources = {"2026-01-01": {"validation": {"rows": 1, "nonnull": {"downloads": 0, "stars": 1, "open_issues": 1}, "sums": {"downloads": None, "stars": "0", "open_issues": "3"}}}}

    def assess(self):
        return {c["id"]: c for c in assess_rollups(self.scans, self.metadata, self.sources)}

    def test_matching(self):
        self.assertTrue(all(c["status"] == "PASS" for c in self.assess().values()))

    def test_null_is_not_zero(self):
        self.scans["package_snapshot"][0]["downloads_sum"] = "0"
        self.assertEqual(self.assess()["package_snapshot_full_rollup"]["status"], "FAIL")

    def test_sum_change_with_same_count(self):
        self.scans["package_version_snapshot"][0]["dependents_sum"] = "4"
        self.assertEqual(self.assess()["package_version_snapshot_full_rollup"]["status"], "FAIL")

    def test_missing_and_duplicate_dates(self):
        self.scans["package_snapshot"] *= 2
        self.scans["package_version_snapshot"] = []
        checks = self.assess()
        self.assertEqual(checks["package_snapshot_full_rollup"]["status"], "FAIL")
        self.assertEqual(checks["package_version_snapshot_full_rollup"]["status"], "FAIL")

    def test_missing_receipt_fails(self):
        self.sources = {}
        self.assertEqual(self.assess()["package_snapshot_full_rollup"]["status"], "FAIL")

    def test_invalid_row_fails(self):
        self.scans["version"]["invalid"] = 1
        self.assertEqual(self.assess()["version_full_rollup"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
