"""Independent contract tests for the interval based historical calculator.

The optimized result is expanded only inside these tests.  Production output is
expected to keep positive counts and half-open intervals, while the H2 oracle
keeps one result per snapshot and includes zero-count targets.
"""
from __future__ import annotations

import copy
import random
from pathlib import Path
import tempfile
import unittest
import uuid

from pipeline.preprocessing.requirements_resolution.bridge import discover_runtime
from pipeline.preprocessing.version_dependents.historical import compute_optimized
from pipeline.preprocessing.version_dependents.historical_reference import compute_reference
from pipeline.preprocessing.tests.version_dependents.test_historical_reference import T, reference_fixture, tiny_fixture, v, r, _req


def _run(fn, fixture, runtime, root, name, **kwargs):
    # NodeSession opens logs with xb; a single test may invoke the same oracle
    # more than once (for example partition_count=1 and 3).
    log_name = f"{name}-{uuid.uuid4().hex}.log"
    return fn(fixture, runtime=runtime, log_path=Path(root) / log_name, **kwargs)


def _positive_counts(snapshot):
    return {
        (row["package_id"], row["version"]): row["dependents_count"]
        for row in snapshot["counts"]
        if row["dependents_count"] > 0
    }


def _expanded_targets(result):
    """Expand the optimized target birth indexes for comparison purposes."""
    targets = {}
    for row in result["target_population"]:
        key = (row["package_id"], row["version"])
        start = row["birth_index"]
        end = row.get("end_index", len(result["snapshots"]))
        for index in range(start, end):
            targets.setdefault(index, set()).add(key)
    return targets


def _interval_keys(row):
    return tuple(row.get(field) for field in (
        "source_package_id", "source_version", "kind", "declaration_index",
        "declared_name", "requirement", "normalized_range", "status",
        "target_package_id", "target_version"))


def _assert_interval_expansion(test, optimized, reference):
    """Check every optimized interval against the oracle's per-date outcomes."""
    for index, snapshot in enumerate(reference["snapshots"]):
        expected = {
            _interval_keys(row): row
            for row in snapshot["declaration_outcomes"]
        }
        actual = {}
        for row in optimized.get("declaration_intervals", []):
            if row["start_index"] <= index < row["end_index"]:
                actual[_interval_keys(row)] = row
        test.assertEqual(set(actual), set(expected), f"declaration interval at {index}")

        expected_sources = {
            (row["source_package_id"], row["source_version"]): row
            for row in snapshot["source_outcomes"]
        }
        actual_sources = {}
        for row in optimized.get("source_intervals", []):
            if row["start_index"] <= index < row["end_index"]:
                actual_sources[(row["source_package_id"], row["source_version"])] = row
        test.assertEqual(set(actual_sources), set(expected_sources), f"source interval at {index}")
        for key, expected_row in expected_sources.items():
            actual_row = actual_sources[key]
            for field in ("status", "declaration_count", "resolved_count", "unresolved_count"):
                test.assertEqual(actual_row[field], expected_row[field], (index, key, field))


class HistoricalOptimizedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = discover_runtime()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-optimized-")
        self.addCleanup(self.temp.cleanup)

    def compute_pair(self, fixture, *, partition_count=1):
        reference = _run(compute_reference, fixture, self.runtime, self.temp.name, "reference")
        optimized = _run(compute_optimized, fixture, self.runtime, self.temp.name, "optimized",
                          partition_count=partition_count)
        return reference, optimized

    def assert_matches_reference(self, fixture, *, partition_count=1):
        reference, optimized = self.compute_pair(fixture, partition_count=partition_count)
        self.assertFalse(optimized["ready_for_load"])
        self.assertEqual(len(optimized["snapshots"]), len(reference["snapshots"]))
        for expected, actual in zip(reference["snapshots"], optimized["snapshots"]):
            self.assertEqual(actual["snapshot_at"], expected["snapshot_at"])
            self.assertEqual(actual["snapshot_timestamp"], expected["snapshot_timestamp"])
            self.assertEqual(_positive_counts(actual), _positive_counts(expected))
            self.assertEqual(actual["quality"], expected["quality"])
        _assert_interval_expansion(self, optimized, reference)
        return reference, optimized

    def test_golden_result_matches_oracle_and_keeps_zero_targets_out_of_output(self):
        reference, optimized = self.assert_matches_reference(reference_fixture())
        for snapshot in optimized["snapshots"]:
            self.assertTrue(all(row["dependents_count"] > 0 for row in snapshot["counts"]))
        target_keys = {(row["package_id"], row["version"])
                       for row in optimized["target_population"]}
        self.assertIn((2, "1.0.0"), target_keys)
        self.assertEqual(sum(_positive_counts(reference["snapshots"][-1]).values()), 6)
        self.assertEqual(sum(row["dependents_count"]
                             for row in optimized["snapshots"][-1]["counts"]), 6)

    def test_partitioning_does_not_change_counts_quality_or_intervals(self):
        fixture = reference_fixture()
        one = _run(compute_optimized, fixture, self.runtime, self.temp.name, "one", partition_count=1)
        three = _run(compute_optimized, fixture, self.runtime, self.temp.name, "three", partition_count=3)
        self.assertEqual(one["snapshots"], three["snapshots"])
        self.assertEqual(one["target_population"], three["target_population"])
        self.assertEqual(one["declaration_intervals"], three["declaration_intervals"])
        self.assertEqual(one["source_intervals"], three["source_intervals"])

    def test_input_order_is_semantically_irrelevant(self):
        fixture = reference_fixture()
        shuffled = copy.deepcopy(fixture)
        for key in ("packages", "versions", "requirements"):
            random.Random(283).shuffle(shuffled[key])
        _, baseline = self.compute_pair(fixture)
        _, permuted = self.compute_pair(shuffled, partition_count=3)
        self.assertEqual(baseline["snapshots"], permuted["snapshots"])
        self.assertEqual(baseline["target_population"], permuted["target_population"])
        self.assertEqual(baseline["declaration_intervals"], permuted["declaration_intervals"])

    def test_late_winner_and_equal_precedence_produce_nested_intervals(self):
        s1, s2, s3 = "2026-08-29T20:00:00.000000Z", "2026-08-30T20:00:00.000000Z", T
        fixture = tiny_fixture([(1, "app"), (2, "dep"), (3, "tie")], [
            v(1, "1.0.0", s1), v(1, "1.1.0", s2), v(1, "1.2.0", s3),
            v(2, "1.0.0", s1), v(2, "1.2.0", s2), v(2, "1.1.0", s3),
            v(3, "1.0.0+z", s2), v(3, "1.0.0+aa", s3)], [
            r(1, "1.0.0", [_req("dep", "^1.0.0"), _req("tie", "1.0.0")]),
            r(1, "1.1.0", [_req("dep", "^1.0.0")]),
            r(1, "1.2.0", [_req("dep", "=1.0.0")]),
        ], [s1, s2, s3])
        _, optimized = self.assert_matches_reference(fixture)
        dep_intervals = [row for row in optimized["declaration_intervals"]
                          if row["declared_name"] == "dep"]
        self.assertGreaterEqual(len(dep_intervals), 2)
        tie_intervals = [row for row in optimized["declaration_intervals"]
                          if row["declared_name"] == "tie"]
        self.assertTrue(any(row["target_version"] == "1.0.0+z" for row in tie_intervals))
        self.assertTrue(any(row["target_version"] == "1.0.0+aa" for row in tie_intervals))

    def test_duplicate_declarations_and_multiple_sources_count_once(self):
        s1, s2 = "2026-08-30T20:00:00.000000Z", T
        fixture = tiny_fixture([(1, "a"), (2, "dep")], [
            v(1, "1.0.0", s1), v(1, "2.0.0", s2), v(2, "1.0.0", s1)], [
            r(1, "1.0.0", [_req("dep", "1.0.0"), _req("dep", "1.0.0")]),
            r(1, "2.0.0", [_req("dep", "1.0.0")]), r(2, "1.0.0", []),
        ], [s1, s2])
        _, optimized = self.assert_matches_reference(fixture)
        self.assertEqual(optimized["snapshots"][-1]["quality"]["distinct_edges"], 2)
        self.assertEqual(optimized["snapshots"][-1]["quality"]["duplicate_resolved_declarations"], 1)

    def test_direct_chain_self_edge_and_partial_errors_are_preserved(self):
        stamp = T
        fixture = tiny_fixture([(1, "a"), (2, "b"), (3, "c"), (4, "bad")], [
            v(1, "1.0.0", stamp), v(2, "1.0.0", stamp), v(3, "1.0.0", stamp),
            v(4, "1.0.0", stamp, True)], [
            r(1, "1.0.0", [_req("b", "*"), _req("a", "*")]),
            r(2, "1.0.0", [_req("c", "*")]), r(3, "1.0.0", []),
            r(4, "1.0.0", [_req("c", "*"), _req("missing", "*")]),
        ], [stamp])
        _, optimized = self.assert_matches_reference(fixture)
        counts = {(row["package_id"], row["version"]): row["dependents_count"]
                  for row in optimized["snapshots"][0]["counts"]}
        self.assertEqual(counts, {(1, "1.0.0"): 1, (2, "1.0.0"): 1, (3, "1.0.0"): 2})

    def test_known_future_target_status_transitions_match(self):
        s1, s2, s3 = "2026-08-29T20:00:00.000000Z", "2026-08-30T20:00:00.000000Z", T
        fixture = tiny_fixture([(1, "a"), (2, "future")], [
            v(1, "1.0.0", s1), v(2, "1.0.0", s2), v(2, "2.0.0", s3)],
            [r(1, "1.0.0", [_req("future", "^2.0.0")])], [s1, s2, s3])
        _, optimized = self.assert_matches_reference(fixture)
        statuses = [next(row for row in optimized["declaration_intervals"]
                         if row["declaration_index"] == 0 and row["start_index"] <= index < row["end_index"])["status"]
                    for index in range(3)]
        self.assertEqual(statuses, ["NO_ELIGIBLE_TARGET", "NO_SATISFYING_VERSION", "RESOLVED"])

    def test_seeded_small_population_matches_for_multiple_partitionings(self):
        rng = random.Random(20260910)
        packages = [(index, f"p{index}") for index in range(1, 6)]
        stamps = ["2026-08-28T20:00:00.000000Z", "2026-08-29T20:00:00.000000Z", T]
        versions = []
        requirements = []
        for package_id, _ in packages:
            for number, stamp in enumerate(stamps, 1):
                versions.append(v(package_id, f"1.0.{number}", stamp))
                deps = []
                if package_id != 5 and rng.random() < 0.8:
                    target = rng.randint(1, 5)
                    deps.append(_req(f"p{target}", "^1.0.0"))
                    if rng.random() < 0.35:
                        deps.append(_req(f"p{target}", "^1.0.0"))
                requirements.append(r(package_id, f"1.0.{number}", deps))
        fixture = tiny_fixture(packages, versions, requirements, stamps)
        reference, optimized = self.assert_matches_reference(fixture, partition_count=3)
        _, optimized_one = self.compute_pair(fixture, partition_count=1)
        self.assertEqual(optimized["snapshots"], optimized_one["snapshots"])
        self.assertTrue(all(row["quality"]["distinct_edges"] >= 0
                            for row in reference["snapshots"]))


if __name__ == "__main__":
    unittest.main()
