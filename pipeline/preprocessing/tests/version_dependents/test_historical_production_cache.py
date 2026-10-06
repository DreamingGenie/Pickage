"""Focused contracts for the production cache helper."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from pipeline.preprocessing.version_dependents.historical_production_cache import check_tables, daily_totals, serialize_tables, verify_cache, verify_cache_bytes
from pipeline.preprocessing.version_dependents import historical_cache as legacy
from pipeline.preprocessing.tests.version_dependents.test_historical_reference import reference_fixture
from pipeline.preprocessing.version_dependents.historical_cache import create_fixture_cache
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes
from pipeline.preprocessing.requirements_resolution.input import file_sha256


def tables(con, *, count=3):
    con.execute("CREATE TABLE history_count_intervals(package_id INTEGER,version VARCHAR,start_index INTEGER,end_index INTEGER,dependents_count BIGINT)")
    con.execute("CREATE TABLE history_target_population(package_id INTEGER,version VARCHAR,birth_index INTEGER)")
    con.execute("CREATE TABLE history_quality(snapshot_index INTEGER,quality_json VARCHAR)")
    con.execute("INSERT INTO history_target_population VALUES (1,'1.0.0',0),(2,'1.0.0',1),(3,'1.0.0',2)")
    con.execute("INSERT INTO history_count_intervals VALUES (1,'1.0.0',0,3,2),(2,'1.0.0',1,3,1)")
    rows = []
    for i in range(count):
        rows.append((i, json.dumps({"source_versions": 1, "target_versions": i + 1,
            "selected_declarations": 2 + (1 if i > 0 else 0), "resolved_declarations": 2 + (1 if i > 0 else 0), "unresolved_declarations": 0,
            "distinct_edges": 2 + (1 if i > 0 else 0), "duplicate_resolved_declarations": 0,
            "resolution_status": "COMPLETE", "source_status_counts": {"RESOLVED": 1},
            "declaration_status_counts": {"RESOLVED": 2 + (1 if i > 0 else 0)}, "source_null_publication_excluded": 0,
            "source_future_excluded": 0, "excluded_kind_declarations": {"peer_dependencies": 0, "optional_dependencies": 0},
            "target_rejections": {}})))
    con.executemany("INSERT INTO history_quality VALUES (?,?)", rows)


class ProductionCacheTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        self.temp = tempfile.TemporaryDirectory(prefix="production-cache-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tables(self.con)

    def test_daily_totals_uses_birth_prefix_and_interval_events(self):
        totals = daily_totals(self.con, 3)
        self.assertEqual(totals, [
            {"target_versions": 1, "positive_target_versions": 1, "distinct_edges": 2, "max_dependents_count": 2},
            {"target_versions": 2, "positive_target_versions": 2, "distinct_edges": 3, "max_dependents_count": 2},
            {"target_versions": 3, "positive_target_versions": 2, "distinct_edges": 3, "max_dependents_count": 2},
        ])

    def test_check_tables_matches_quality_and_rejects_malformed_quality(self):
        self.assertEqual(check_tables(self.con, 3)[1]["distinct_edges"], 3)
        self.con.execute("UPDATE history_quality SET quality_json='{}' WHERE snapshot_index=1")
        with self.assertRaisesRegex(ValueError, "quality"):
            check_tables(self.con, 3)

    def test_duplicate_target_and_overlapping_interval_are_rejected(self):
        self.con.execute("INSERT INTO history_target_population VALUES (1,'1.0.0',0)")
        with self.assertRaisesRegex(ValueError, "unique"):
            check_tables(self.con, 3)
        self.con.execute("DELETE FROM history_target_population WHERE package_id=1 AND version='1.0.0' AND birth_index=0")
        self.con.execute("INSERT INTO history_target_population VALUES (1,'1.0.0',0)")
        self.con.execute("INSERT INTO history_count_intervals VALUES (1,'1.0.0',2,3,1)")
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_tables(self.con, 3)

    def test_target_birth_and_count_limit_are_rejected(self):
        self.con.execute("UPDATE history_target_population SET birth_index=2 WHERE package_id=1")
        with self.assertRaisesRegex(ValueError, "birth"):
            check_tables(self.con, 3)
        self.con.execute("UPDATE history_target_population SET birth_index=0 WHERE package_id=1")
        self.con.execute("UPDATE history_count_intervals SET dependents_count=2147483648 WHERE package_id=1")
        with self.assertRaisesRegex(ValueError, "count"):
            daily_totals(self.con, 3)

    def test_unknown_table_identifier_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            daily_totals(self.con, 3, counts="history_count_intervals;DROP TABLE history_quality")

    def test_invalid_calendar_sizes_fail_before_reading_tables(self):
        for n in (0, True, 4097, -1):
            with self.subTest(n=n), self.assertRaises(ValueError):
                daily_totals(self.con, n)

    def test_empty_target_and_count_tables_have_zero_totals(self):
        self.con.execute("DELETE FROM history_count_intervals")
        self.con.execute("DELETE FROM history_target_population")
        self.assertEqual(daily_totals(self.con, 3), [
            {"target_versions": 0, "positive_target_versions": 0,
             "distinct_edges": 0, "max_dependents_count": 0} for _ in range(3)])

    def test_quality_index_duplicate_and_out_of_range_are_rejected(self):
        self.con.execute("INSERT INTO history_quality SELECT * FROM history_quality WHERE snapshot_index=0")
        with self.assertRaisesRegex(ValueError, "quality"):
            check_tables(self.con, 3)
        self.con.execute("DELETE FROM history_quality WHERE snapshot_index=0")
        self.con.execute("INSERT INTO history_quality VALUES (3, '{}')")
        with self.assertRaisesRegex(ValueError, "quality"):
            check_tables(self.con, 3)

    def test_invalid_quality_status_and_conservation_are_rejected(self):
        self.con.execute("UPDATE history_quality SET quality_json=? WHERE snapshot_index=0", [json.dumps({
            "source_versions": 1, "target_versions": 1, "selected_declarations": 1,
            "resolved_declarations": 1, "unresolved_declarations": 0, "distinct_edges": 1,
            "duplicate_resolved_declarations": 0, "resolution_status": "NOT_A_STATUS",
            "source_status_counts": {"RESOLVED": 1}, "declaration_status_counts": {"RESOLVED": 1},
            "source_null_publication_excluded": 0, "source_future_excluded": 0,
            "excluded_kind_declarations": {"peer_dependencies": 0, "optional_dependencies": 0},
            "target_rejections": {}})])
        with self.assertRaisesRegex(ValueError, "quality"):
            check_tables(self.con, 3)

    def test_invalid_target_identity_and_interval_identity_are_rejected(self):
        self.con.execute("UPDATE history_target_population SET package_id=NULL WHERE package_id=1")
        with self.assertRaisesRegex(ValueError, "target"):
            check_tables(self.con, 3)
        self.con.execute("UPDATE history_target_population SET package_id=1 WHERE package_id IS NULL")
        self.con.execute("UPDATE history_count_intervals SET version=NULL WHERE package_id=1")
        with self.assertRaisesRegex(ValueError, "count"):
            daily_totals(self.con, 3)

    def test_empty_intervals_produce_zero_positive_and_max(self):
        self.con.execute("DELETE FROM history_count_intervals")
        totals = daily_totals(self.con, 3)
        self.assertEqual([row["positive_target_versions"] for row in totals], [0, 0, 0])
        self.assertEqual([row["distinct_edges"] for row in totals], [0, 0, 0])
        self.assertEqual([row["max_dependents_count"] for row in totals], [0, 0, 0])

    def test_falling_max_intervals_are_calculated_per_date(self):
        self.con.execute("DELETE FROM history_count_intervals")
        self.con.executemany("INSERT INTO history_count_intervals VALUES (?,?,?,?,?)", [
            (1, "1.0.0", 0, 1, 10), (1, "1.0.0", 1, 3, 2),
            (2, "1.0.0", 1, 2, 7)])
        totals = daily_totals(self.con, 3)
        self.assertEqual([row["max_dependents_count"] for row in totals], [10, 7, 2])

    def test_legacy_and_production_checkers_accept_same_fixture(self):
        legacy._check_tables(self.con, 3)
        self.assertEqual(check_tables(self.con, 3)[-1]["target_versions"], 3)

    def test_legacy_and_production_checkers_reject_same_bad_count(self):
        self.con.execute("UPDATE history_count_intervals SET dependents_count=0 WHERE package_id=1")
        with self.assertRaises(ValueError):
            legacy._check_tables(self.con, 3)
        with self.assertRaises(ValueError):
            daily_totals(self.con, 3)

    def _roundtrip_fixture(self):
        fixture = self.root / "fixture.json"
        fixture.write_bytes(canonical_bytes(reference_fixture()))
        source = create_fixture_cache(fixture, self.root / "source-cache")
        manifest = source["manifest"]
        out = self.root / "production-cache"
        with duckdb.connect() as con:
            for name in ("history_count_intervals", "history_target_population", "history_quality"):
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet(?)", [str(Path(source["cache_dir"]) / {
                    "history_count_intervals": "count_intervals.parquet",
                    "history_target_population": "target_population.parquet",
                    "history_quality": "quality.parquet"}[name])])
            result = serialize_tables(con, output=out, calendar=manifest["calendar"],
                                      observed_snapshot_timestamp=manifest["observed_snapshot_timestamp"],
                                      lineage=manifest["lineage"], runtime=manifest["runtime"])
        return out, result

    def test_serialize_and_verify_production_roundtrip(self):
        out, result = self._roundtrip_fixture()
        verified = verify_cache(out, result["manifest_sha256"])
        self.assertEqual(verified["production_cache_sha256"], file_sha256((REPO_ROOT / 'pipeline/preprocessing/version_dependents/historical_production_cache.py')))
        verify_cache_bytes(out, result["manifest_sha256"], verified)

    def test_verify_cache_bytes_rejects_file_corruption(self):
        out, result = self._roundtrip_fixture()
        path = out / "count_intervals.parquet"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "changed|mismatch|invalid parquet"):
            verify_cache_bytes(out, result["manifest_sha256"], result["manifest"])

    def test_verify_cache_rejects_generation_mismatch_when_present(self):
        out, result = self._roundtrip_fixture()
        path = out / "cache_manifest.json"
        body = json.loads(path.read_bytes())
        body["production_cache_sha256"] = "0" * 64
        path.write_bytes(canonical_bytes(body))
        with self.assertRaisesRegex(ValueError, "manifest|generation"):
            verify_cache(out, file_sha256(path))


if __name__ == "__main__":
    unittest.main()
