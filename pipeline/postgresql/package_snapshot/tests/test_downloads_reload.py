"""Contract tests for the downloads-only reload (S15P21A506-453).

Each test answers one question: does a break here tell us the reload could corrupt what the
service already shows? Recompute fidelity, the stop-before-UPDATE acceptance rule, invariance of
stars/open_issues, rollback of --verify-only, and idempotent re-verification are the contract.
"""
from __future__ import annotations

from importlib import import_module
import json
import os
from pathlib import Path
import tempfile
import unittest

import duckdb

from pipeline.postgresql.package_snapshot import downloads_reload as reload_module

CONTAINER = os.environ.get("PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER")
BRONZE = {"run_id": "downloads-test-v1", "prefix": "npm-downloads/v1/run_id=downloads-test-v1",
          "manifest_sha256": "b" * 64}


def write_daily_root(root: Path, days: dict, statuses: dict):
    """days: {date: [(name, downloads or None, imputed_gap)]}; statuses: {name: READY|NOT_FOUND}."""
    root.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE statuses(name VARCHAR, status VARCHAR)")
        con.executemany("INSERT INTO statuses VALUES (?,?)", list(statuses.items()))
        con.execute(f"COPY statuses TO '{(root / 'downloads_status.parquet').as_posix()}' (FORMAT PARQUET)")
        for day, rows in days.items():
            con.execute("CREATE OR REPLACE TABLE daily(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN, date DATE)")
            con.executemany("INSERT INTO daily VALUES (?,?,?,?)", [(n, d, g, day) for n, d, g in rows])
            part = root / "downloads" / f"date={day}"
            part.mkdir(parents=True)
            con.execute(f"COPY daily TO '{(part / 'part-0.parquet').as_posix()}' (FORMAT PARQUET)")


class RecomputeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "daily"

    def test_interval_rule_matches_aggregate_semantics(self):
        # Interval [2026-08-24, 2026-08-27): only two of three days exist -> PARTIAL, never an error.
        write_daily_root(self.root, {
            "2026-08-24": [("alpha", 10, False), ("beta", None, False), ("zero", 0, False)],
            "2026-08-25": [("alpha", 20, False), ("beta", 5, True), ("zero", 0, False)],
            "2026-08-27": [("alpha", 999, False)],  # outside [P,S): ignored
        }, {"alpha": "READY", "beta": "READY", "zero": "READY"})
        staging = reload_module.recompute(self.root, {"previous_snapshot_at": "2026-08-24", "snapshot_at": "2026-08-27"},
                                          Path(self.tmp.name) / "out", memory="256MB", threads=1)
        lines = Path(staging["file"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["alpha\t30\t2\t2", "beta\t\\N\t2\t0", "zero\t0\t2\t2"])
        self.assertEqual((staging["rows"], staging["nonnull"], staging["complete"], staging["partial"], staging["unavailable"]),
                         (3, 2, 0, 2, 1))
        self.assertEqual(staging["expected_days"], 3)
        self.assertEqual(staging["daily_dates"], ["2026-08-24", "2026-08-25"])

    def test_daily_name_without_ready_status_is_rejected(self):
        write_daily_root(self.root, {"2026-08-24": [("alpha", 1, False), ("ghost", 1, False)]},
                         {"alpha": "READY", "ghost": "NOT_FOUND"})
        with self.assertRaisesRegex(ValueError, "READY"):
            reload_module.recompute(self.root, {"previous_snapshot_at": "2026-08-24", "snapshot_at": "2026-08-31"},
                                    Path(self.tmp.name) / "out", memory="256MB", threads=1)


@unittest.skipUnless(CONTAINER, "PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER is required")
class DownloadsReloadPostgresTests(unittest.TestCase):
    """Reuse the disposable V1-V3 fixture (packages alpha/beta/gamma, snapshots 08-24 and 08-31)."""

    snapshot = "2026-08-31"

    def setUp(self):
        fixture_type = import_module(".test_postgres", package=__package__).PackageSnapshotPostgresTests
        self.fixture = fixture_type("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.command = self.fixture.command + ["-d", self.fixture.database]
        self.work = Path(self.fixture.work.name)
        self.sql("""INSERT INTO package_snapshot(package_id,snapshot_at,downloads,stars,open_issues) VALUES
            (1,DATE '2026-08-31',30,4,2),(2,DATE '2026-08-31',NULL,8,8),(3,DATE '2026-08-31',NULL,NULL,NULL);""")
        write_daily_root(self.work / "daily", {
            "2026-08-24": [("alpha", 10, False), ("beta", 5, False), ("gamma", None, False)],
            "2026-08-25": [("alpha", 20, False), ("gamma", 3, True)],
        }, {"alpha": "READY", "beta": "READY", "gamma": "READY"})

    def sql(self, statement):
        return self.fixture.sql(statement)

    def rows(self):
        return self.sql("SELECT package_id,coalesce(downloads::text,'NULL'),coalesce(stars::text,'NULL'),"
                        "coalesce(open_issues::text,'NULL') FROM package_snapshot WHERE snapshot_at=DATE '2026-08-31' "
                        "ORDER BY package_id")

    def reload(self, run_id="t1", **options):
        staging = reload_module.recompute(self.work / "daily", {"previous_snapshot_at": "2026-08-24", "snapshot_at": self.snapshot},
                                          self.work / "staging" / run_id, memory="256MB", threads=1)
        return reload_module.reload_snapshot(snapshot=self.snapshot, previous="2026-08-24", rows=3, staging=staging,
                                             bronze=BRONZE, run_id=run_id, work_dir=self.work / "run" / run_id,
                                             command=self.command, vacuum=False, **options)

    def test_updates_only_changed_downloads_and_records_history(self):
        before = self.rows()
        self.assertEqual(before, "1|30|4|2\n2|NULL|8|8\n3|NULL|NULL|NULL")
        report = self.reload()
        result = report["result"]
        self.assertEqual((result["action"], result["counts"]["updated"]), ("UPDATED", 1))
        self.assertEqual(self.rows(), "1|30|4|2\n2|5|8|8\n3|NULL|NULL|NULL")
        quality = result["quality"]
        self.assertEqual((quality["downloads_nonnull_before"], quality["downloads_nonnull_after"]), (1, 2))
        self.assertEqual(quality["acceptance"]["mismatched"], 0)
        self.assertTrue(quality["stars_open_issues_identical"] and quality["rows_identical"])
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='reload-453-t1-2026-08-31'"), "PUBLISHED")
        stored = json.loads(self.sql("SELECT quality_report::text FROM etl_load_attempt WHERE execution_id='reload-453-t1-2026-08-31'"))
        self.assertEqual(stored["changed_rows"], 1)
        self.assertEqual(self.sql("SELECT snapshot_at||'|'||execution_id FROM etl_dataset_current WHERE dataset='package-snapshot'"),
                         "2026-08-31|reload-453-t1-2026-08-31")

    def test_existing_value_that_differs_from_recomputation_stops_without_changes(self):
        self.sql("UPDATE package_snapshot SET downloads=31 WHERE package_id=1 AND snapshot_at=DATE '2026-08-31'")
        with self.assertRaisesRegex(ValueError, "recomputed downloads differ.*mismatched=1"):
            self.reload("t2")
        self.assertEqual(self.rows(), "1|31|4|2\n2|NULL|8|8\n3|NULL|NULL|NULL")
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='reload-453-t2-2026-08-31'"), "FAILED")
        self.assertEqual(self.sql("SELECT count(*) FROM etl_dataset_current WHERE dataset='package-snapshot'"), "0")

    def test_existing_value_without_daily_data_stops_without_changes(self):
        self.sql("UPDATE package_snapshot SET downloads=7 WHERE package_id=3 AND snapshot_at=DATE '2026-08-31'")
        with self.assertRaisesRegex(ValueError, "recomputed downloads differ.*mismatched=1"):
            self.reload("t3")
        self.sql("UPDATE package_snapshot SET downloads=NULL WHERE package_id=3 AND snapshot_at=DATE '2026-08-31'")
        self.sql("INSERT INTO package(package_id,name) VALUES (4,'delta'); "
                 "INSERT INTO package_snapshot VALUES (4,DATE '2026-08-31',9,1,1)")
        with self.assertRaisesRegex(ValueError, "missing_from_staging=1"):
            staging = reload_module.recompute(self.work / "daily", {"previous_snapshot_at": "2026-08-24", "snapshot_at": self.snapshot},
                                              self.work / "staging" / "t3b", memory="256MB", threads=1)
            reload_module.reload_snapshot(snapshot=self.snapshot, previous="2026-08-24", rows=4, staging=staging,
                                          bronze=BRONZE, run_id="t3b", work_dir=self.work / "run" / "t3b",
                                          command=self.command, vacuum=False)
        self.assertEqual(self.rows(), "1|30|4|2\n2|NULL|8|8\n3|NULL|NULL|NULL\n4|9|1|1")

    def test_verify_only_rolls_back_and_the_same_execution_can_then_publish(self):
        report = self.reload("t4", verify_only=True)
        self.assertEqual(report["result"]["status"], "VERIFIED_ROLLED_BACK")
        self.assertEqual(report["result"]["counts"]["updated"], 1)
        self.assertEqual(self.rows(), "1|30|4|2\n2|NULL|8|8\n3|NULL|NULL|NULL")
        self.assertEqual(self.sql("SELECT status||'|'||phase FROM etl_load_attempt WHERE execution_id='reload-453-t4-2026-08-31'"),
                         "FAILED|VERIFY_ONLY")
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='reload-453-t4-2026-08-31'"), "FAILED")
        self.assertEqual(self.reload("t4")["result"]["action"], "UPDATED")
        self.assertEqual(self.rows(), "1|30|4|2\n2|5|8|8\n3|NULL|NULL|NULL")

    def test_second_run_of_a_published_execution_reverifies_without_changes(self):
        self.assertEqual(self.reload("t5")["result"]["action"], "UPDATED")
        second = self.reload("t5")["result"]
        self.assertEqual((second["action"], second["counts"]["updated"]), ("REVERIFIED", 0))
        self.assertEqual(self.sql("SELECT string_agg(status,',' ORDER BY created_at) FROM etl_load_attempt "
                                  "WHERE execution_id='reload-453-t5-2026-08-31'"), "PUBLISHED,REVERIFIED")
        self.assertEqual(self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='reload-453-t5-2026-08-31'"),
                         '{"updated": 1, "verified_rows": 3, "package_snapshot": 3}')


if __name__ == "__main__":
    unittest.main()
