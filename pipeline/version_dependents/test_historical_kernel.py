"""Adversarial normalized interval inputs and batched fixture boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from .historical import _create_tables, aggregate_interval_tables, compute_optimized
from .historical_reference import compute_reference
from .test_historical import _assert_interval_expansion
from .test_historical_reference import reference_fixture


class HistoricalIntervalKernelTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(config={"threads": 2})
        self.addCleanup(self.con.close)
        _create_tables(self.con)

    def source(self, declarations, pid=1, birth=0):
        self.con.execute("INSERT INTO sources VALUES (?,?,?,false,true,false,?,0,0)",
                         [pid, "1.0.0", birth, declarations])

    def interval(self, declaration, start, end, target=2, pid=1):
        self.con.execute("INSERT INTO declaration_intervals VALUES (?, '1.0.0', ?, 'dependencies', 'dep', '*', '*', ?, ?, ?, ?, ?)",
                         [pid, declaration, "RESOLVED" if target else "NO_SATISFYING_VERSION",
                          target, "1.0.0" if target else None, start, end])

    def test_nested_union_uses_running_max_and_counts_source_only_once(self):
        self.source(3)
        self.interval(0, 0, 6)
        self.interval(1, 0, 1, None)
        self.interval(1, 1, 2)
        self.interval(1, 2, 6, None)
        self.interval(2, 0, 3, None)
        self.interval(2, 3, 5)
        self.interval(2, 5, 6, None)
        aggregate_interval_tables(self.con, 6)
        self.assertEqual(self.con.execute("SELECT start_index,end_index FROM edge_intervals").fetchall(), [(0, 6)])
        self.assertEqual(self.con.execute("SELECT snapshot_index,dependents_count FROM counts ORDER BY 1").fetchall(),
                         [(index, 1) for index in range(6)])
        self.assertEqual(self.con.execute("SELECT start_index,resolved_count FROM source_intervals ORDER BY 1").fetchall(),
                         [(0, 1), (1, 2), (2, 1), (3, 2), (5, 1)])

    def test_adjacent_declarations_union_across_boundary(self):
        self.source(2)
        self.interval(0, 0, 2)
        self.interval(0, 2, 6, None)
        self.interval(1, 0, 2, None)
        self.interval(1, 2, 6)
        aggregate_interval_tables(self.con, 6)
        self.assertEqual(self.con.execute("SELECT start_index,end_index FROM edge_intervals").fetchall(), [(0, 6)])

    def test_equal_interval_rows_have_deterministic_window_order(self):
        for pid in range(1, 121):
            self.source(2, pid=pid)
            for declaration in range(2):
                for index in range(4):
                    self.interval(declaration, index * 4, (index + 1) * 4, target=index + 200, pid=pid)
        aggregate_interval_tables(self.con, 16)
        self.assertEqual(self.con.execute("SELECT snapshot_index,dependents_count FROM counts ORDER BY 1").fetchall(),
                         [(index, 120) for index in range(16)])
        self.assertEqual(self.con.execute("SELECT count(*) FROM edge_intervals").fetchone()[0], 480)

    def test_interval_gap_is_rejected(self):
        self.source(1)
        self.interval(0, 0, 2)
        self.interval(0, 3, 6)
        with self.assertRaisesRegex(ValueError, "gaps"):
            aggregate_interval_tables(self.con, 6)

    def test_interval_overlap_is_rejected_before_counts(self):
        self.source(1)
        self.interval(0, 0, 4)
        self.interval(0, 3, 6)
        with self.assertRaisesRegex(ValueError, "overlap"):
            aggregate_interval_tables(self.con, 6)

    def test_missing_declaration_and_unmapped_source_are_rejected(self):
        self.source(1)
        with self.assertRaisesRegex(ValueError, "omit"):
            aggregate_interval_tables(self.con, 6)
        self.interval(0, 0, 6, pid=99)
        with self.assertRaisesRegex(ValueError, "bounds"):
            aggregate_interval_tables(self.con, 6)

    def test_source_birth_and_final_index_are_enforced(self):
        self.source(1, birth=1)
        self.interval(0, 0, 6)
        with self.assertRaisesRegex(ValueError, "bounds"):
            aggregate_interval_tables(self.con, 6)

    def test_count_over_service_limit_is_rejected(self):
        for pid in (1, 3):
            self.source(1, pid=pid)
            self.interval(0, 0, 6, pid=pid)
        with patch("pipeline.version_dependents.historical.INT_MAX", 1):
            with self.assertRaisesRegex(ValueError, "INT range"):
                aggregate_interval_tables(self.con, 6)

    def test_empty_population_has_no_count_rows(self):
        aggregate_interval_tables(self.con, 6)
        self.assertEqual(self.con.execute("SELECT count(*) FROM counts").fetchone()[0], 0)


class HistoricalAdapterBoundaryTests(unittest.TestCase):
    def compare(self, fixture):
        with tempfile.TemporaryDirectory(prefix="historical-boundary-") as directory:
            root = Path(directory)
            reference = compute_reference(fixture, log_path=root / "reference.log")
            optimized = compute_optimized(fixture, log_path=root / "optimized.log", partition_count=3)
        for expected, actual in zip(reference["snapshots"], optimized["snapshots"], strict=True):
            self.assertEqual([r for r in expected["counts"] if r["dependents_count"]], actual["counts"])
            self.assertEqual(expected["quality"], actual["quality"])
        _assert_interval_expansion(self, optimized, reference)
        return optimized

    def test_more_than_one_lookup_batch_preserves_global_source_dedup(self):
        fixture = reference_fixture()
        fixture["requirements"][0]["dependencies"] = [
            {"name": "dep", "requirement": "^1.0.0" + " " * index} for index in range(130)]
        result = self.compare(fixture)
        self.assertEqual(result["metrics"]["unique_lookups"], 130)
        self.assertEqual(result["snapshots"][-1]["quality"]["duplicate_resolved_declarations"], 129)

    def test_null_names_invalid_specs_and_unsupported_protocols(self):
        fixture = reference_fixture()
        fixture["requirements"][0]["dependencies"] = [None, {}, {"name": "", "requirement": "*"},
            {"name": "bad name", "requirement": "*"}, {"name": "dep", "requirement": None},
            {"name": "dep", "requirement": "a\x00b"}] + [
                {"name": "dep", "requirement": spec} for spec in
                ["latest", "git+https://example.org/repo.git", "https://example.org/p.tgz", "file:../p",
                 "workspace:*", "catalog:default", "link:../p", "portal:../p", "jsr:@a/b", "patch:x"]]
        fixture["requirements"][0]["peer_dependencies"] = [{"name": "dep", "requirement": "*"}]
        fixture["requirements"][0]["optional_dependencies"] = [{"name": "dep", "requirement": "*"}]
        self.compare(fixture)

    def test_no_eligible_sources_and_subset_calendar(self):
        fixture = reference_fixture()
        fixture["calendar"] = fixture["calendar"][:1]
        for row in fixture["versions"]:
            row["published_at"] = None
        result = self.compare(fixture)
        self.assertEqual(result["snapshots"][0]["counts"], [])
        self.assertEqual(result["snapshots"][0]["quality"]["source_versions"], 0)


if __name__ == "__main__":
    unittest.main()
