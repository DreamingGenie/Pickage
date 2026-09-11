"""Contract tests for historical population preparation.

These tests use tiny DuckDB relations and independently calculated expected
values; they do not run the full requirements-resolution pipeline.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from .historical_input import build_populations, load_calendar
from pipeline.requirements_resolution.bridge import discover_runtime


UTC = timezone.utc
OBSERVED = "2026-08-31T21:01:10.517131Z"
T = datetime(2026, 8, 31, 21, 1, 10, 517131)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HistoricalInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-input-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = discover_runtime()
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        self._create_tables()

    def _create_tables(self):
        self.con.execute("CREATE TABLE input_package(package_id INTEGER, name VARCHAR)")
        self.con.execute("CREATE TABLE input_version(package_id INTEGER, version VARCHAR, published_at TIMESTAMP)")
        self.con.execute("""
          CREATE TABLE input_versions_full(
            SnapshotAt TIMESTAMP, Name VARCHAR, Version VARCHAR,
            is_release BOOLEAN, published_at TIMESTAMP, dependency_error BOOLEAN)
        """)
        self.con.execute("""
          CREATE TABLE input_requirements(
            SnapshotAt TIMESTAMP, Name VARCHAR, Version VARCHAR,
            Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[],
            PeerDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[],
            OptionalDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[])
        """)
        self.con.executemany("INSERT INTO input_package VALUES (?, ?)", [(1, "app"), (2, "dep")])
        versions = [
            (1, "1.0.0", T), (1, "1.1.0", T + timedelta(microseconds=1)),
            (1, "2.0.0-beta.1", T), (1, "3.0.0", None),
            (2, "1.0.0", T), (2, "2.0.0", T + timedelta(microseconds=1)),
            (2, "2.0.0-beta.1", T), (2, "not-semver", T),
        ]
        self.con.executemany("INSERT INTO input_version VALUES (?, ?, ?)", versions)
        self.con.executemany("INSERT INTO input_versions_full VALUES (?, ?, ?, ?, ?, ?)", [
            (T, "app", "1.0.0", True, T, False),
            (T, "app", "1.1.0", True, T + timedelta(microseconds=1), False),
            (T, "app", "2.0.0-beta.1", True, T, False),
            (T, "app", "3.0.0", True, None, False),
            (T, "dep", "1.0.0", True, T, False),
            (T, "dep", "2.0.0", True, T + timedelta(microseconds=1), False),
            (T, "dep", "2.0.0-beta.1", True, T, False),
            (T, "dep", "not-semver", True, T, False),
        ])
        rows = [
            (T, "app", "1.0.0", [{"Name": "dep", "Requirement": "^1.0.0"}], [], []),
            (T, "app", "1.1.0", [{"Name": "dep", "Requirement": "^1.0.0"}], [], []),
            (T, "app", "2.0.0-beta.1", None, [], []),
            (T, "app", "3.0.0", [], [], []),
        ]
        self.con.executemany("INSERT INTO input_requirements VALUES (?, ?, ?, ?, ?, ?)", rows)

    def calendar(self, rows=None):
        path = self.root / "calendar.json"
        path.write_text(json.dumps({"calendar": rows or [
            {"snapshot_at": "2026-08-30", "snapshot_timestamp": "2026-08-30T21:01:10.517131Z"},
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": OBSERVED},
        ]}), encoding="utf-8")
        return path

    def build(self, *, observed=OBSERVED, rows=None):
        output = self.root / f"out-{len(list(self.root.iterdir()))}"
        output.mkdir()
        calendar = self.calendar(rows)
        cal = load_calendar(calendar, _sha(calendar), observed)
        return build_populations(self.con, cal, observed, self.runtime, output)

    def snapshot_rows(self):
        columns = ["snapshot_index", "source_versions", "target_versions", "declarations",
                   "missing_requirements_sources", "null_dependency_list_sources",
                   "error_sources", "unknown_error_sources"]
        return [dict(zip(columns, row)) for row in self.con.execute(
            "SELECT snapshot_index,source_versions,target_versions,declarations,"
            "missing_requirements_sources,null_dependency_list_sources,error_sources,unknown_error_sources "
            "FROM snapshot_population ORDER BY snapshot_index").fetchall()]

    def test_calendar_normalizes_offsets_and_returns_microseconds(self):
        path = self.calendar([{"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-09-01T06:01:10.517131+09:00"}])
        result = load_calendar(path, _sha(path), OBSERVED)
        self.assertEqual(result[0]["snapshot_timestamp"], OBSERVED)
        self.assertEqual(result[0]["timestamp_us"], 1788210070517131)
        self.assertEqual(result[0]["snapshot_index"], 0)

    def test_calendar_rejects_naive_duplicate_and_future(self):
        for rows in (
            [{"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:01:10.517131"}],
            [{"snapshot_at": "2026-08-31", "snapshot_timestamp": OBSERVED}, {"snapshot_at": "2026-08-31", "snapshot_timestamp": OBSERVED}],
            [{"snapshot_at": "2026-09-01", "snapshot_timestamp": "2026-09-01T21:01:10.517131Z"}],
        ):
            path = self.calendar(rows)
            with self.assertRaises(ValueError):
                load_calendar(path, _sha(path), OBSERVED)

    def test_calendar_rejects_tampered_sha_and_irregular_order(self):
        path = self.calendar([
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": OBSERVED},
            {"snapshot_at": "2026-08-30", "snapshot_timestamp": "2026-08-30T21:01:10.517131Z"},
        ])
        with self.assertRaises(ValueError):
            load_calendar(path, "0" * 64, OBSERVED)
        with self.assertRaises(ValueError):
            load_calendar(path, _sha(path), OBSERVED)

    def test_population_filters_time_and_semver_with_dense_snapshot_totals(self):
        result = self.build()
        stats = result["statistics"]
        self.assertEqual(stats["eligible_sources"], 5)
        self.assertEqual(stats["eligible_targets"], 2)
        self.assertEqual(stats["selected_declarations_latest"], 1)
        self.assertEqual(stats["dense_target_snapshot_keys"], 2)
        self.assertEqual(stats["prerelease_targets_excluded"], 2)
        self.assertEqual(stats["invalid_semver_targets_excluded"], 1)
        rows = self.snapshot_rows()
        self.assertEqual(rows[0]["source_versions"], 0)
        self.assertEqual(rows[0]["target_versions"], 0)
        self.assertEqual(rows[1]["source_versions"], 5)
        self.assertEqual(rows[1]["target_versions"], 2)
        self.assertEqual(rows[1]["declarations"], 1)

    def test_missing_requirements_null_list_and_source_errors_are_counted(self):
        self.con.execute("INSERT INTO input_version VALUES (1, '4.0.0', ?)", [T])
        self.con.execute("INSERT INTO input_versions_full VALUES (?, 'app', '4.0.0', true, ?, true)", [T, T])
        result = self.build()
        row = self.snapshot_rows()[-1]
        self.assertEqual(row["null_dependency_list_sources"], 1)
        self.assertEqual(row["error_sources"], 1)
        self.assertEqual(row["missing_requirements_sources"], 4)

    def test_duplicate_package_key_fails(self):
        self.con.execute("INSERT INTO input_package VALUES (1, 'app')")
        with self.assertRaises(ValueError):
            self.build()

    def test_duplicate_version_key_fails(self):
        self.con.execute("INSERT INTO input_version VALUES (1, '1.0.0', ?)", [T])
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_raw_fails(self):
        self.con.execute("DELETE FROM input_versions_full WHERE Name='dep' AND Version='1.0.0'")
        with self.assertRaises(ValueError):
            self.build()

    def test_raw_date_mismatch_fails(self):
        self.con.execute("UPDATE input_versions_full SET SnapshotAt=? WHERE Name='dep' AND Version='1.0.0'", [T + timedelta(microseconds=1)])
        with self.assertRaises(ValueError):
            self.build()

    def test_nonrelease_fails(self):
        self.con.execute("UPDATE input_versions_full SET is_release=false WHERE Name='dep' AND Version='1.0.0'")
        with self.assertRaises(ValueError):
            self.build()

    def test_raw_and_requirements_duplicate_keys_fail(self):
        self.con.execute("INSERT INTO input_versions_full VALUES (?, 'dep', '1.0.0', true, ?, false)", [T, T])
        with self.assertRaises(ValueError):
            self.build()

    def test_requirements_duplicate_key_fails(self):
        self.con.execute("INSERT INTO input_requirements VALUES (?, 'app', '1.0.0', [], [], [])", [T])
        with self.assertRaises(ValueError):
            self.build()

    def test_observed_timestamp_mismatch_fails(self):
        self.con.execute("UPDATE input_requirements SET SnapshotAt=? WHERE Name='app' AND Version='1.0.0'", [T + timedelta(microseconds=1)])
        with self.assertRaises(ValueError):
            self.build()

    def test_irregular_three_dates_birth_intervals_are_dense_under_local_timezone(self):
        """Versions born before, at, and just after the middle snapshot land correctly."""
        first = datetime(2026, 8, 28, 21, 1, 10, 517131)
        middle = datetime(2026, 8, 30, 21, 1, 10, 517131)
        middle_plus = middle + timedelta(microseconds=1)
        versions = [(1, "0.1.0", first - timedelta(microseconds=1)),
                    (1, "0.2.0", middle), (1, "0.3.0", middle_plus)]
        self.con.executemany("INSERT INTO input_version VALUES (?, ?, ?)", versions)
        self.con.executemany("INSERT INTO input_versions_full VALUES (?, 'app', ?, true, ?, false)",
                             [(T, version, published) for _, version, published in versions])
        calendar = [
            {"snapshot_at": "2026-08-28", "snapshot_timestamp": first},
            {"snapshot_at": "2026-08-30", "snapshot_timestamp": middle},
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": T},
        ]
        calendar = [{**row, "snapshot_timestamp": stamp.isoformat() + "Z"}
                    for row, stamp in zip(calendar, (first, middle, T))]
        path = self.calendar(calendar)
        loaded = load_calendar(path, _sha(path), OBSERVED)
        self.con.execute("SET TimeZone='Asia/Seoul'")
        output = self.root / "irregular-out"
        output.mkdir()
        result = build_populations(self.con, loaded, OBSERVED, self.runtime, output)
        rows = self.snapshot_rows()
        self.assertEqual([(row["source_versions"], row["target_versions"])
                          for row in rows], [(1, 1), (2, 2), (8, 5)])
        self.assertEqual(result["statistics"]["source_snapshot_keys"], 11)
        self.assertEqual(result["statistics"]["dense_target_snapshot_keys"], 8)
        births = dict(self.con.execute(
            "SELECT source_version,birth_index FROM source_population "
            "WHERE source_version IN ('0.1.0','0.2.0','0.3.0')").fetchall())
        self.assertEqual(births, {"0.1.0": 0, "0.2.0": 1, "0.3.0": 2})
        self.assertEqual(self.con.execute(
            "SELECT published_at_us FROM source_population WHERE source_version='0.3.0'").fetchone()[0],
            int(middle_plus.replace(tzinfo=UTC).timestamp() * 1_000_000))


if __name__ == "__main__":
    unittest.main()
