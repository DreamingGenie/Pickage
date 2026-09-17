"""Meaning-level regression tests for weighted source and quality finalization."""

from __future__ import annotations

import json
import unittest

import duckdb

from pipeline.preprocessing.version_dependents.historical_production_events import aggregate_partition_weighted, validate_weighted_inputs
from pipeline.preprocessing.version_dependents.historical_production_quality import finalize_quality_weighted, summarize_sources
from pipeline.preprocessing.version_dependents.historical_production_sql import aggregate_partition, finalize_quality
from pipeline.preprocessing.tests.version_dependents.test_historical_production_events import base_fixture


N = 4


class WeightedQualityTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        base_fixture(self.con)
        self.con.executemany("INSERT INTO lookup_intervals VALUES (?,?,?,?,?,?,?)", [
            (10, 0, N, "RESOLVED", "^1", 20, "1.0.0"),
            (11, 0, 2, "NO_SATISFYING_VERSION", "^2", None, None),
            (11, 2, N, "RESOLVED", "^2", 20, "2.0.0"),
            (12, 0, N, "RESOLVED", "*", 30, "1.0.0"),
            (14, 0, N, "RESOLVED", "~1", 20, "1.0.0"),
        ])
        self.con.execute("INSERT INTO lookups VALUES (?,?,?,?)", [14, "dep", "~1", 0])

    def _declaration(self, source_id, version, birth, flag, original, name, requirement, lookup, pid):
        self.con.execute("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [source_id, version, f"source-{source_id}", birth, flag, original,
                          name, requirement, lookup, pid])

    def _partition(self, pid, rows):
        for row in rows:
            self._declaration(*row)
        validate_weighted_inputs(self.con, N)
        aggregate_partition_weighted(self.con, N, pid, global_validated=True)
        summarize_sources(self.con, N, pid)
        for name in ("p_counts", "p_status_deltas", "p_source_summary"):
            self.con.execute(f"CREATE OR REPLACE TEMP TABLE {name}_{pid} AS SELECT * FROM {name}")

    def _finalize(self, partitions):
        for pid, rows in partitions:
            self._partition(pid, rows)
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_counts AS SELECT * FROM p_counts_0 UNION ALL SELECT * FROM p_counts_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_status_deltas AS SELECT * FROM p_status_deltas_0 UNION ALL SELECT * FROM p_status_deltas_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_source_summary AS SELECT * FROM p_source_summary_0 UNION ALL SELECT * FROM p_source_summary_1")
        return finalize_quality_weighted(self.con, N)

    def test_duplicate_raw_declarations_quality_two_but_one_edge(self):
        result = self._finalize([(0, [
            (1, "1.0.0", 0, False, 0, "dep", "^1", 10, 0),
            (1, "1.0.0", 0, False, 1, "dep", "^1", 10, 0),
        ]), (1, [])])
        quality = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0])
        self.assertEqual(quality["selected_declarations"], 2)
        self.assertEqual(quality["resolved_declarations"], 2)
        self.assertEqual(quality["distinct_edges"], 1)
        self.assertEqual(quality["duplicate_resolved_declarations"], 1)
        self.assertEqual(result["source_versions"], 1)

    def test_normal_fixture_matches_legacy_quality_json(self):
        rows = [
            (1, "1.0.0", 0, False, 0, "dep", "^1", 10, 0),
            (2, "1.0.0", 0, False, 0, "dep", "^1", 10, 0),
        ]
        self._partition(0, rows)
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_counts AS SELECT * FROM p_counts_0")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_status_deltas AS SELECT * FROM p_status_deltas_0")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_source_summary AS SELECT * FROM p_source_summary_0")
        finalize_quality_weighted(self.con, N)
        weighted = [row[0] for row in self.con.execute(
            "SELECT quality_json FROM history_quality ORDER BY snapshot_index").fetchall()]

        aggregate_partition(self.con, N, 0)
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_sources AS SELECT * FROM p_sources")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_source_deltas AS SELECT * FROM p_source_deltas")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_status_deltas AS SELECT * FROM p_status_deltas")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_counts AS SELECT * FROM p_counts")
        finalize_quality(self.con, N)
        legacy = [row[0] for row in self.con.execute(
            "SELECT quality_json FROM history_quality ORDER BY snapshot_index").fetchall()]
        self.assertEqual(weighted, legacy)

    def test_same_winner_different_lookup_fallback_deduplicates_edge(self):
        result = self._finalize([(0, [
            (1, "1.0.0", 0, False, 0, "dep", "^1", 10, 0),
            (1, "1.0.0", 0, False, 1, "dep", "~1", 14, 0),
        ]), (1, [])])
        quality = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0])
        self.assertEqual(quality["distinct_edges"], 1)
        self.assertEqual(quality["resolved_declarations"], 2)

    def test_fallback_can_reference_two_distinct_versions_on_same_date(self):
        self._finalize([(0, [
            (1, "1.0.0", 0, False, 0, "dep", "^1", 10, 0),
            (1, "1.0.0", 0, False, 1, "dep", "^2", 11, 0),
        ]), (1, [])])
        counts = self.con.execute("SELECT version,dependents_count FROM history_count_intervals WHERE start_index<=2 AND 2<end_index ORDER BY version").fetchall()
        self.assertEqual(counts, [("1.0.0", 1), ("2.0.0", 1)])
        final = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=2").fetchone()[0])
        self.assertEqual(final["distinct_edges"], 2)
        self.assertEqual(final["source_versions"], 1)
        self.assertEqual(final["source_status_counts"], {"RESOLVED": 1})

    def test_partial_and_error_unknown_source_statuses_are_preserved(self):
        result = self._finalize([(0, [
            (1, "1.0.0", 0, True, 0, "dep", "^1", 10, 0),
            (2, "1.0.0", 0, None, 0, "dep", "^1", 10, 0),
            (3, "1.0.0", 0, False, 0, "dep", "^2", 11, 0),
        ]), (1, [])])
        quality = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0])
        self.assertEqual(quality["source_status_counts"]["DEPENDENCY_EXTRACTION_ERROR"], 1)
        self.assertEqual(quality["source_status_counts"]["DEPENDENCY_EXTRACTION_UNKNOWN"], 1)
        self.assertEqual(quality["resolution_status"], "PARTIAL")

    def test_cross_partition_source_birth_or_flag_conflict_is_rejected(self):
        self._partition(0, [(1, "1.0.0", 0, False, 0, "dep", "^1", 10, 0)])
        self._partition(1, [(1, "1.0.0", 1, False, 1, "other", "*", 12, 1)])
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_counts AS SELECT * FROM p_counts_0 UNION ALL SELECT * FROM p_counts_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_status_deltas AS SELECT * FROM p_status_deltas_0 UNION ALL SELECT * FROM p_status_deltas_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_source_summary AS SELECT * FROM p_source_summary_0 UNION ALL SELECT * FROM p_source_summary_1")
        with self.assertRaisesRegex(ValueError, "birth|flag|conflict|differ"):
            finalize_quality_weighted(self.con, N)

    def test_source_status_uses_global_min_max_across_partitions(self):
        self.con.execute("DELETE FROM lookup_intervals WHERE lookup_id=12")
        self.con.executemany("INSERT INTO lookup_intervals VALUES (?,?,?,?,?,?,?)", [
            (12, 0, 2, "NO_SATISFYING_VERSION", "*", None, None),
            (12, 2, N, "RESOLVED", "*", 30, "1.0.0"),
        ])
        self._finalize([(0, [(1, "1.0.0", 0, False, 0, "dep", "^1", 10, 0)]),
                        (1, [(1, "1.0.0", 0, False, 1, "other", "*", 12, 1)])])
        rows = [json.loads(row[0]) for row in self.con.execute(
            "SELECT quality_json FROM history_quality ORDER BY snapshot_index").fetchall()]
        self.assertEqual([r["source_versions"] for r in rows], [1]*N)
        self.assertEqual([r["source_status_counts"] for r in rows],
                         [{"PARTIAL": 1}, {"PARTIAL": 1}, {"RESOLVED": 1}, {"RESOLVED": 1}])
        self.assertEqual([r["resolved_declarations"] for r in rows], [1, 1, 2, 2])
        self.con.execute("UPDATE p_source_summary_1 SET first_any_resolved_index=NULL, last_finite_resolved_index=NULL, never_resolved_count=1")
        self.con.execute("DELETE FROM p_status_deltas_1")
        self.con.executemany("INSERT INTO p_status_deltas_1 VALUES (?,?,?)",
                             [(0, "NO_SATISFYING_VERSION", 1), (N, "NO_SATISFYING_VERSION", -1)])
        self.con.execute("DELETE FROM p_counts_1")
        finalize_quality_weighted(self.con, N)
        final = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=?", [N-1]).fetchone()[0])
        self.assertEqual(final["source_status_counts"], {"PARTIAL": 1})
        self.assertEqual(final["unresolved_declarations"], 1)

    def test_target_birth_and_int32_boundaries_are_checked(self):
        self.con.execute("DROP TABLE target_names; DROP TABLE lookups; DROP TABLE declarations; DROP TABLE lookup_intervals")
        self.con.execute("""CREATE TEMP TABLE all_source_summary(
            source_package_id INTEGER, source_version VARCHAR, birth_index INTEGER,
            dependency_error BOOLEAN, declaration_count BIGINT, never_resolved_count BIGINT,
            first_any_resolved_index INTEGER, last_finite_resolved_index INTEGER)""")
        self.con.execute("CREATE TEMP TABLE all_status_deltas(snapshot_index INTEGER,status VARCHAR,delta BIGINT)")
        self.con.execute("CREATE TEMP TABLE all_counts(package_id INTEGER,version VARCHAR,start_index INTEGER,end_index INTEGER,dependents_count BIGINT)")
        self.con.execute("CREATE TEMP TABLE target_population(package_id INTEGER,name VARCHAR,version VARCHAR,birth_index INTEGER)")

        def scaled(value):
            self.con.execute("DELETE FROM all_source_summary; DELETE FROM all_status_deltas; DELETE FROM all_counts; DELETE FROM target_population")
            self.con.execute("INSERT INTO all_source_summary VALUES (1,'1.0.0',0,false,?,?,0,0)", [value, 0])
            self.con.executemany("INSERT INTO all_status_deltas VALUES (?,?,?)", [(0, "RESOLVED", value), (N, "RESOLVED", -value)])
            self.con.execute("INSERT INTO all_counts VALUES (20,'1.0.0',0,?,?)", [N, value])
            self.con.execute("INSERT INTO target_population VALUES (20,'dep','1.0.0',0)")
            return finalize_quality_weighted(self.con, N)

        scaled(2_147_483_647)
        with self.assertRaisesRegex(ValueError, "target|birth|interval|count"):
            scaled(2_147_483_648)
        scaled(1)
        self.con.execute("UPDATE target_population SET birth_index=2")
        with self.assertRaisesRegex(ValueError, "target|birth|interval"):
            finalize_quality_weighted(self.con, N)


if __name__ == "__main__":
    unittest.main()
