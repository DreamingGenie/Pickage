from __future__ import annotations

import unittest
import json

import duckdb

from pipeline.preprocessing.version_dependents.historical import STATUSES
from pipeline.preprocessing.version_dependents.historical_production_sql import aggregate_partition, finalize_quality
from pipeline.preprocessing.version_dependents.historical_cache import _check_tables


class ProductionSqlTest(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("""
          CREATE TABLE declarations(
            source_package_id INTEGER, source_version VARCHAR, source_name VARCHAR,
            birth_index INTEGER, dependency_error BOOLEAN, original_declaration_index BIGINT,
            declared_name VARCHAR, requirement VARCHAR, lookup_id BIGINT, partition_id INTEGER)
        """)
        self.con.execute("""
          CREATE TABLE lookup_intervals(
            lookup_id BIGINT, start_index INTEGER, end_index INTEGER, status VARCHAR,
            normalized_range VARCHAR, target_package_id INTEGER, target_version VARCHAR)
        """)
        self.con.execute("""
          CREATE TABLE target_population(
            package_id INTEGER, name VARCHAR, version VARCHAR, birth_index INTEGER, partition_id INTEGER)
        """)
        self.con.executemany("INSERT INTO target_population VALUES (?,?,?,?,?)", [
            (20, "dep", "1.0.0", 0, 0), (20, "dep", "1.1.0", 2, 0),
            (21, "dep", "2.0.0", 1, 0)])
        # Each lookup covers the complete calendar, with a target replacement
        # at index 2 for lookup 10.
        self.con.executemany("INSERT INTO lookup_intervals VALUES (?,?,?,?,?,?,?)", [
            (10, 0, 2, "RESOLVED", "^1", 20, "1.0.0"),
            (10, 2, 5, "RESOLVED", "^1", 20, "1.1.0"),
            (11, 0, 5, "NO_SATISFYING_VERSION", "^9", None, None),
            (12, 0, 1, "NO_SATISFYING_VERSION", "^2", None, None),
            (12, 1, 5, "RESOLVED", "^2", 21, "2.0.0"),
        ])

    def tearDown(self):
        self.con.close()

    def _partition(self, rows, pid):
        self.con.executemany("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        result = aggregate_partition(self.con, 5, pid)
        for name in ("p_counts", "p_sources", "p_source_deltas", "p_status_deltas"):
            self.con.execute(f"CREATE OR REPLACE TEMP TABLE {name}_{pid} AS SELECT * FROM {name}")
        return result

    def test_nested_adjacent_and_target_replacement_are_deduplicated(self):
        self._partition([
            (1, "1.0.0", "outside", 0, False, 0, "dep", "^1", 10, 0),
            (1, "1.0.0", "outside", 0, False, 1, "dep", "^1", 10, 0),
            (1, "1.0.0", "outside", 0, False, 2, "dep", "^9", 11, 0),
        ], 0)
        self.assertEqual(self.con.execute("SELECT sum(dependents_count) FROM p_counts").fetchone()[0], 2)
        self.assertEqual(self.con.execute("SELECT count(*) FROM p_counts").fetchone()[0], 2)
        self.assertEqual(self.con.execute("SELECT sum(delta) FROM p_source_deltas").fetchone()[0], 0)

    def test_missing_lookup_and_gapped_lookup_fail(self):
        with self.assertRaisesRegex(ValueError, "missing lookup"):
            self._partition([(1, "1.0.0", "outside", 0, False, 0, "dep", "x", 999, 0)], 0)
        self.con.execute("DELETE FROM declarations")
        self.con.execute("DELETE FROM lookup_intervals WHERE lookup_id=11")
        self.con.execute("INSERT INTO lookup_intervals VALUES (11,0,2,'NO_SATISFYING_VERSION','^9',NULL,NULL)")
        with self.assertRaisesRegex(ValueError, "cover"):
            self._partition([(1, "1.0.0", "outside", 0, False, 0, "dep", "x", 11, 0)], 0)

    def test_finalize_deduplicates_source_quality_across_partitions(self):
        self._partition([(1, "1.0.0", "outside", 0, False, 0, "dep", "^1", 10, 0)], 0)
        self._partition([(1, "1.0.0", "outside", 0, False, 1, "dep", "^1", 10, 1)], 1)
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_sources AS SELECT * FROM p_sources_0 UNION ALL SELECT * FROM p_sources_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_source_deltas AS SELECT * FROM p_source_deltas_0 UNION ALL SELECT * FROM p_source_deltas_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_status_deltas AS SELECT * FROM p_status_deltas_0 UNION ALL SELECT * FROM p_status_deltas_1")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_counts AS SELECT * FROM p_counts_0 UNION ALL SELECT * FROM p_counts_1")
        result = finalize_quality(self.con, 5)
        self.assertEqual(result["source_versions"], 1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM history_quality").fetchone()[0], 5)
        q = self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0]
        self.assertEqual(__import__("json").loads(q)["selected_declarations"], 2)

    def test_bad_declaration_key_and_target_birth_fail(self):
        with self.assertRaisesRegex(ValueError, "duplicate declaration"):
            self._partition([
                (1, "1.0.0", "outside", 0, None, 0, "dep", "x", 11, 0),
                (1, "1.0.0", "outside", 0, None, 0, "dep", "x", 11, 0)], 0)
        self.con.execute("UPDATE target_population SET birth_index=5 WHERE package_id=20 AND version='1.0.0'")
        with self.assertRaisesRegex(ValueError, "born"):
            self._partition([(1, "1.0.0", "outside", 0, False, 0, "dep", "^1", 10, 0)], 0)

    def _finalize_from_partition(self, rows, pid=0):
        self._partition(rows, pid)
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_sources AS SELECT * FROM p_sources")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_source_deltas AS SELECT * FROM p_source_deltas")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_status_deltas AS SELECT * FROM p_status_deltas")
        self.con.execute("CREATE OR REPLACE TEMP VIEW all_counts AS SELECT * FROM p_counts")
        return finalize_quality(self.con, 5)

    def test_successful_finalize_passes_h4_cache_contract_and_preserves_zero_target(self):
        self._finalize_from_partition([
            (1, "1.0.0", "outside", 0, False, 0, "dep", "^1", 10, 0),
        ])
        _check_tables(self.con, 5)
        self.assertEqual(self.con.execute("SELECT count(*) FROM history_count_intervals WHERE package_id=21").fetchone()[0], 0)
        q = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0])
        self.assertEqual(q["resolution_status"], "COMPLETE")
        self.assertEqual(q["source_future_excluded"], 0)

    def test_invalid_and_unsupported_statuses_are_retained_as_partial(self):
        self.con.execute("DELETE FROM lookup_intervals WHERE lookup_id=12")
        self.con.execute("INSERT INTO lookup_intervals VALUES (12,0,5,'UNSUPPORTED_TAG','tag',NULL,NULL)")
        self._finalize_from_partition([
            (1, "1.0.0", "outside", 0, True, 0, "dep", "bad", 11, 0),
            (2, "1.0.0", "outside2", 0, None, 0, "dep", "tag", 12, 0),
        ])
        _check_tables(self.con, 5)
        q = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0])
        self.assertEqual(q["resolution_status"], "PARTIAL")
        self.assertEqual(q["source_status_counts"]["DEPENDENCY_EXTRACTION_ERROR"], 1)
        self.assertEqual(q["source_status_counts"]["DEPENDENCY_EXTRACTION_UNKNOWN"], 1)
        self.assertEqual(q["declaration_status_counts"]["NO_SATISFYING_VERSION"], 1)
        q = json.loads(self.con.execute("SELECT quality_json FROM history_quality WHERE snapshot_index=0").fetchone()[0])
        self.assertEqual(q["declaration_status_counts"]["UNSUPPORTED_TAG"], 1)

    def test_empty_partition_and_bad_target_partition_are_safe_failures(self):
        result = aggregate_partition(self.con, 5, 7)
        self.assertEqual(result["declarations"], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM p_counts").fetchone()[0], 0)
        self.con.execute("UPDATE target_population SET partition_id=-1 WHERE package_id=20 AND version='1.0.0'")
        with self.assertRaisesRegex(ValueError, "target population"):
            aggregate_partition(self.con, 5, 0)


if __name__ == "__main__":
    unittest.main()
