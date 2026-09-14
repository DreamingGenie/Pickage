"""Fault injection for each service key and temporal/quality boundary."""
from copy import deepcopy
from pathlib import Path
import unittest

from .runner import load_fixture, validate_fixture


class BoundaryTests(unittest.TestCase):
    def fixture(self):
        return load_fixture(Path(__file__).parent / "fixtures" / "normal.json")[0]

    def assert_check_fails(self, document, check_id):
        report = validate_fixture(document)
        checks = {row["id"]: row for row in report["checks"]}
        self.assertEqual(checks[check_id]["status"], "FAIL", report)
        self.assertFalse(report["ready_for_publication"])

    def test_duplicate_primary_keys_are_detected_independently_of_row_counts(self):
        checks = {"package": "package_identity", "version": "version_integrity",
                  "snapshot": "snapshot_integrity", "package_snapshot": "package_snapshot_integrity",
                  "package_version_snapshot": "package_version_snapshot_integrity"}
        for table, check_id in checks.items():
            with self.subTest(table=table):
                document = self.fixture()
                qualified = "public." + table
                document["tables"][qualified].append(deepcopy(document["tables"][qualified][0]))
                document["expected_counts"][qualified] += 1
                self.assert_check_fails(document, check_id)

    def test_composite_fk_cannot_use_another_packages_version(self):
        document = self.fixture()
        row = document["tables"]["public.package_version_snapshot"][0]
        # 2.0.0 exists for alpha only; beta exists, but (beta, 2.0.0) does not.
        row["package_id"], row["version"] = 2, "2.0.0"
        self.assert_check_fails(document, "package_version_snapshot_integrity")

    def test_missing_quality_cannot_validate_a_zero_value(self):
        document = self.fixture()
        document["tables"]["validation.source_quality"].pop()
        self.assert_check_fails(document, "source_quality_snapshot_coverage")
        self.assert_check_fails(document, "source_quality_zero_contract")

    def test_publish_time_boundary_uses_microseconds(self):
        document = self.fixture()
        row = document["tables"]["public.version"][0]
        row["published_at"] = "2026-01-01T00:00:00.000001Z"
        self.assertEqual(validate_fixture(document)["validation_status"], "PASS")
        row["published_at"] = "2026-01-01T00:00:00.000002Z"
        self.assert_check_fails(document, "version_snapshot_eligibility")
        row["published_at"] = None
        self.assert_check_fails(document, "version_snapshot_eligibility")

    def test_service_null_and_length_contracts_are_checked(self):
        document = self.fixture()
        document["tables"]["public.version"][0]["dependency"] = None
        self.assert_check_fails(document, "version_integrity")
        document = self.fixture()
        document["tables"]["public.package"][0]["repo_url"] = "x" * 201
        self.assert_check_fails(document, "package_identity")

    def test_duplicate_evidence_does_not_silently_multiply_counts(self):
        for table, check_id in (("source_quality", "source_quality_integrity"),
                                ("expected_package_metrics", "expected_package_metrics"),
                                ("target_population", "target_population_integrity")):
            with self.subTest(table=table):
                document = self.fixture()
                rows = document["tables"]["validation." + table]
                rows.append(deepcopy(rows[0]))
                self.assert_check_fails(document, check_id)


if __name__ == "__main__":
    unittest.main()
