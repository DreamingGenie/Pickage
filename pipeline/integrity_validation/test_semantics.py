"""Behavioural regression cases for the synthetic integrity-validation fixture."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from .runner import validate_fixture


FIXTURE = Path(__file__).parent / "fixtures" / "normal.json"


def fixture():
    with FIXTURE.open(encoding="utf-8") as stream:
        return json.load(stream)


def status(document):
    return validate_fixture(deepcopy(document))["validation_status"]


class SemanticsTest(unittest.TestCase):
    def test_normal_fixture_is_a_non_publishable_pass(self):
        report = validate_fixture(fixture())
        self.assertEqual(report["validation_status"], "PASS")
        self.assertFalse(report["ready_for_publication"])
        self.assertEqual(report["scope"], "SYNTHETIC_FIXTURE_ONLY")


    def test_per_table_count_error_is_detected_even_when_total_is_unchanged(self):
        document = fixture()
        document["expected_counts"]["public.package"], document["expected_counts"]["public.snapshot"] = 2, 3
        self.assertEqual(status(document), "FAIL")

    def test_pvs_counts_are_checked_individually_even_when_their_sum_is_unchanged(self):
        document = fixture()
        rows = document["tables"]["public.package_version_snapshot"]
        rows[0]["dependents_count"], rows[1]["dependents_count"] = 1, 2
        self.assertEqual(status(document), "FAIL")


    def test_composite_package_version_identity_cannot_cross_snapshot_or_package(self):
        document = fixture()
    # This version exists in the global version table, but did not exist for
    # package 1 at the January snapshot.
        document["tables"]["public.package_version_snapshot"][0]["version"] = "1.1.0"
        self.assertEqual(status(document), "FAIL")


    def test_target_population_missing_or_extra_version_is_detected(self):
        missing = fixture()
        missing["tables"]["validation.target_population"].pop()
        self.assertEqual(status(missing), "FAIL")

        extra = fixture()
        extra["tables"]["validation.target_population"].append(
            {"package_id": 1, "version": "2.0.0", "snapshot_at": "2026-02-01"}
        )
        self.assertEqual(status(extra), "FAIL")


    def test_multiple_source_versions_and_duplicate_edges_and_chain_are_deduplicated(self):
    # The normal fixture includes beta 1.0.0 and 1.1.0 as separate sources,
    # plus an intentional duplicate January edge.
        self.assertEqual(status(fixture()), "PASS")


    def test_null_download_is_not_equivalent_to_zero(self):
        document = fixture()
        document["tables"]["public.package_snapshot"][1]["downloads"] = 0
        self.assertEqual(status(document), "FAIL")


    def test_edge_snapshot_mixing_is_detected(self):
        document = fixture()
        document["tables"]["validation.resolved_edges"][0]["snapshot_at"] = "2026-02-01"
        document["tables"]["validation.resolved_edges"][0]["target_version"] = "2.0.0"
        self.assertEqual(status(document), "FAIL")


    def test_missing_required_json_field_raises_value_error(self):
        document = fixture()
        del document["fixture_id"]
        with self.assertRaises(ValueError):
            validate_fixture(document)
