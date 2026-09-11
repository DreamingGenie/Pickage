"""Meaning-level regression tests for weighted production event aggregation."""

from __future__ import annotations

import random
import unittest
from collections import Counter
from unittest.mock import patch

import duckdb

from .historical_production_events import aggregate_partition_weighted, validate_weighted_inputs


N = 4


def schema(con):
    con.execute("""CREATE TABLE target_names(
        name VARCHAR, package_id INTEGER, known_package BOOLEAN, partition_id INTEGER)""")
    con.execute("""CREATE TABLE lookups(
        lookup_id BIGINT, declared_name VARCHAR, requirement VARCHAR, partition_id INTEGER)""")
    con.execute("""CREATE TABLE declarations(
        source_package_id INTEGER, source_version VARCHAR, source_name VARCHAR,
        birth_index INTEGER, dependency_error BOOLEAN, original_declaration_index BIGINT,
        declared_name VARCHAR, requirement VARCHAR, lookup_id BIGINT, partition_id INTEGER)""")
    con.execute("""CREATE TABLE target_population(
        package_id INTEGER, name VARCHAR, version VARCHAR, birth_index INTEGER,
        partition_id INTEGER)""")
    con.execute("""CREATE TABLE lookup_intervals(
        lookup_id BIGINT, start_index INTEGER, end_index INTEGER, status VARCHAR,
        normalized_range VARCHAR, target_package_id INTEGER, target_version VARCHAR)""")


def base_fixture(con):
    schema(con)
    con.executemany("INSERT INTO target_names VALUES (?,?,?,?)", [
        ("dep", 20, True, 0), ("other", 30, True, 1), ("unknown", None, False, 0)])
    con.executemany("INSERT INTO target_population VALUES (?,?,?,?,?)", [
        (20, "dep", "1.0.0", 0, 0), (20, "dep", "2.0.0", 1, 0),
        (30, "other", "1.0.0", 0, 1)])
    con.executemany("INSERT INTO lookups VALUES (?,?,?,?)", [
        (10, "dep", "^1", 0), (11, "dep", "^2", 0),
        (12, "other", "*", 1), (13, "dep", None, 0)])


class WeightedEventsTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        base_fixture(self.con)

    def _interval(self, lookup_id, start, end, status, package=None, version=None):
        self.con.execute("INSERT INTO lookup_intervals VALUES (?,?,?,?,?,?,?)",
                         [lookup_id, start, end, status, status, package, version])

    def test_duplicate_raw_declarations_count_one_edge_but_preserve_quality_weight(self):
        self._interval(10, 0, N, "RESOLVED", 20, "1.0.0")
        self.con.executemany("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (1, "1.0.0", "app", 0, False, 0, "dep", "^1", 10, 0),
            (1, "1.0.0", "app", 0, False, 1, "dep", "^1", 10, 0),
        ])
        validate_weighted_inputs(self.con, N)
        result = aggregate_partition_weighted(self.con, N, 0, global_validated=True)
        self.assertEqual(result["partition_id"], 0)
        self.assertEqual(self.con.execute("SELECT sum(dependents_count) FROM p_counts").fetchone()[0], 1)
        rows = self.con.execute("SELECT * FROM p_status_deltas").fetchall()
        self.assertIn((0, "RESOLVED", 2), rows)

    def test_simultaneous_birth_and_winner_switch_uses_a_before_plus_b_once(self):
        self._interval(10, 0, 1, "RESOLVED", 20, "1.0.0")
        self._interval(10, 1, N, "RESOLVED", 20, "2.0.0")
        rows = [(i, "1.0.0", f"source-{i}", 0, False, i, "dep", "^1", 10, 0)
                for i in range(1, 1001)]
        rows.extend((1001 + i, "1.0.0", f"new-{i}", 1, False, 1001 + i,
                     "dep", "^1", 10, 0) for i in range(30))
        self.con.executemany("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        validate_weighted_inputs(self.con, N)
        aggregate_partition_weighted(self.con, N, 0, global_validated=True)
        values = self.con.execute("SELECT package_id,version,start_index,end_index,dependents_count "
                                  "FROM p_counts ORDER BY start_index,version").fetchall()
        self.assertIn((20, "1.0.0", 0, 1, 1000), values)
        self.assertIn((20, "2.0.0", 1, 4, 1030), values)

    def test_unresolved_to_resolved_preserves_prior_source_weight(self):
        self._interval(13, 0, 2, "NO_SATISFYING_VERSION")
        self._interval(13, 2, N, "RESOLVED", 20, "1.0.0")
        self.con.execute("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [1, "1.0.0", "app", 0, False, 0, "dep", None, 13, 0])
        validate_weighted_inputs(self.con, N)
        aggregate_partition_weighted(self.con, N, 0, global_validated=True)
        self.assertEqual(self.con.execute("SELECT start_index,end_index,dependents_count FROM p_counts").fetchall(), [(2, 4, 1)])

    def test_global_mapping_rejects_id_collision_but_allows_multiple_null_ids(self):
        self.con.execute("INSERT INTO target_names VALUES ('alias',20,true,1)")
        with self.assertRaisesRegex(ValueError, "mapping|one-to-one|package"):
            validate_weighted_inputs(self.con, N)
        self.con.execute("DELETE FROM target_names WHERE name='alias'")
        self.con.executemany("INSERT INTO target_names VALUES (?,?,?,?)", [
            ("unknown-2", None, False, 1), ("unknown-3", None, False, 2)])
        validate_weighted_inputs(self.con, N)

    def test_invalid_weight_and_target_birth_are_rejected(self):
        self._interval(10, 0, N, "RESOLVED", 20, "1.0.0")
        self.con.execute("UPDATE target_population SET birth_index=2 WHERE package_id=20 AND version='1.0.0'")
        self.con.execute("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [1, "1.0.0", "app", 0, False, 0, "dep", "^1", 10, 0])
        with self.assertRaisesRegex(ValueError, "birth|born|target"):
            aggregate_partition_weighted(self.con, N, 0)

    def test_missing_lookup_and_wrong_raw_requirement_fail_global_validation(self):
        self.con.execute("INSERT INTO declarations VALUES (1,'1.0.0','app',0,false,0,'dep','^1',999,0)")
        with self.assertRaisesRegex(ValueError, "lookup"):
            validate_weighted_inputs(self.con, N)
        self.con.execute("UPDATE declarations SET lookup_id=10,requirement='different'")
        with self.assertRaisesRegex(ValueError, "lookup"):
            validate_weighted_inputs(self.con, N)

    def test_resolution_cannot_become_unresolved_again(self):
        self._interval(10, 0, 2, "RESOLVED", 20, "1.0.0")
        self._interval(10, 2, N, "NO_SATISFYING_VERSION")
        self.con.execute("INSERT INTO declarations VALUES (1,'1.0.0','app',0,false,0,'dep','^1',10,0)")
        with self.assertRaisesRegex(ValueError, "monotonicity"):
            aggregate_partition_weighted(self.con, N, 0)

    def test_small_buffer_flush_during_live_reader_preserves_counts(self):
        self._interval(10, 0, 1, "RESOLVED", 20, "1.0.0")
        self._interval(10, 1, N, "RESOLVED", 20, "2.0.0")
        self.con.execute("INSERT INTO declarations VALUES (1,'1.0.0','app',0,false,0,'dep','^1',10,0)")
        with patch("pipeline.version_dependents.historical_production_events._BATCH_SIZE", 1):
            metrics = aggregate_partition_weighted(self.con, N, 0)
        self.assertGreater(metrics["event_insert_batches"], 1)
        self.assertEqual(self.con.execute("SELECT version,start_index,end_index,dependents_count FROM p_counts ORDER BY 2").fetchall(),
                         [("1.0.0", 0, 1, 1), ("2.0.0", 1, N, 1)])

    def test_single_connection_random_thousand_lookup_fixture(self):
        rng = random.Random(20260911)
        expected_targets = [set() for _ in range(N)]
        expected_statuses = [dict() for _ in range(N)]
        for lookup_id in range(100, 1100):
            self.con.execute("INSERT INTO lookups VALUES (?,?,?,?)", [lookup_id, "dep", f"r{lookup_id}", 0])
            switch = rng.randrange(1, N)
            self._interval(lookup_id, 0, switch, "RESOLVED", 20, "1.0.0")
            self._interval(lookup_id, switch, N, "RESOLVED", 20, "2.0.0")
            birth = rng.randrange(0, 2)
            self.con.execute("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)",
                             [lookup_id, "1.0.0", f"s{lookup_id}", birth, False,
                              lookup_id, "dep", f"r{lookup_id}", lookup_id, 0])
            for snapshot in range(N):
                if snapshot < birth:
                    continue
                version = "1.0.0" if snapshot < switch else "2.0.0"
                expected_targets[snapshot].add((lookup_id, "1.0.0", 20, version))
                expected_statuses[snapshot]["RESOLVED"] = expected_statuses[snapshot].get("RESOLVED", 0) + 1
        validate_weighted_inputs(self.con, N)
        result = aggregate_partition_weighted(self.con, N, 0, global_validated=True)
        self.assertEqual(result["raw_declarations"], 1000)
        self.assertEqual(self.con.execute("SELECT count(*) FROM w_lookup_summary").fetchone()[0], 1000)
        counts = self.con.execute("SELECT package_id,version,start_index,end_index,dependents_count FROM p_counts").fetchall()
        for snapshot, expected in enumerate(expected_targets):
            actual = {(package_id, version): count for package_id, version, start, end, count in counts
                      if start <= snapshot < end and count > 0}
            expected_counts = Counter((pid, version) for _source, _source_version, pid, version in expected)
            self.assertEqual(actual, dict(expected_counts))
        deltas = self.con.execute("SELECT * FROM p_status_deltas").fetchall()
        active = {}
        for snapshot in range(N):
            for row in deltas:
                if row[0] == snapshot:
                    active[row[1]] = active.get(row[1], 0) + row[2]
            self.assertEqual({k: v for k, v in active.items() if v}, expected_statuses[snapshot])


if __name__ == "__main__":
    unittest.main()
