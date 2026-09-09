"""Verify date insertion in disposable PostgreSQL databases, separate from 267.

Set PICKAGE_SNAPSHOT_TEST_CONTAINER to an existing validation container.
Optionally set PICKAGE_SNAPSHOT_CANDIDATE to a prepared candidate JSON file.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import uuid

from .build import snapshot_sql
from .policy import build_calendar, policy_sha256


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = os.environ.get("PICKAGE_SNAPSHOT_TEST_CONTAINER")
CANDIDATE = os.environ.get("PICKAGE_SNAPSHOT_CANDIDATE")


@unittest.skipUnless(CONTAINER, "PICKAGE_SNAPSHOT_TEST_CONTAINER is required")
class SnapshotPostgresTests(unittest.TestCase):
    def sql(self, sql, *, database=None):
        result = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-q", "-A", "-t",
             "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database or self.database],
            input=sql.encode("utf-8"), capture_output=True, timeout=45,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8").strip()

    def setUp(self):
        self.database = "pickage_269_test_" + uuid.uuid4().hex
        self.sql(f'CREATE DATABASE "{self.database}";', database="postgres")
        self.addCleanup(self.drop_database)
        migrations = ROOT / "backend/src/main/resources/db/migration"
        for name in ("V1__init.sql", "V2__add_curated_load_execution.sql"):
            self.sql((migrations / name).read_text(encoding="utf-8"))

    def drop_database(self):
        if not re.fullmatch(r"pickage_269_test_[0-9a-f]{32}", self.database):
            raise ValueError("Refusing to drop a database outside this test's namespace")
        self.sql(f'DROP DATABASE "{self.database}";', database="postgres")

    def assert_reference_only(self):
        self.assertEqual(self.sql(
            "SELECT (SELECT count(*) FROM package), (SELECT count(*) FROM version),"
            "(SELECT count(*) FROM etl_load_execution), (SELECT count(*) FROM etl_dataset_current);"
        ), "0|0|0|0")

    def test_explicit_dates_are_idempotent_and_preserve_existing(self):
        rows = build_calendar(["2026-08-24T21:00:00Z", "2026-08-31T21:00:00Z"])
        self.sql("INSERT INTO snapshot (snapshot_at) VALUES (DATE '2000-01-01');")
        self.sql(snapshot_sql(rows))
        self.sql(snapshot_sql(rows))
        self.assertEqual(self.sql("SELECT snapshot_at FROM snapshot ORDER BY snapshot_at;"),
                         "2000-01-01\n2026-08-24\n2026-08-31")
        self.assert_reference_only()

    def test_failure_rolls_back_all_dates(self):
        rows = build_calendar(["2026-08-24T21:00:00Z", "2026-08-31T21:00:00Z"])
        failing_sql = snapshot_sql(rows).replace("COMMIT;", "SELECT 1/0;\nCOMMIT;")
        with self.assertRaises(RuntimeError):
            self.sql(failing_sql)
        self.assertEqual(self.sql("SELECT count(*) FROM snapshot;"), "0")
        self.assert_reference_only()

    @unittest.skipUnless(CANDIDATE, "PICKAGE_SNAPSHOT_CANDIDATE is required for actual source dates")
    def test_actual_projects_candidate_exact_dates_and_retry(self):
        path = Path(CANDIDATE)
        candidate = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(candidate["policy_sha256"], policy_sha256())
        self.assertEqual(candidate["status"], "LOCAL_VALIDATED")
        self.assertFalse(candidate["db_published"])
        for item in candidate["files"]:
            self.assertIn(item["path"], ("projects-inventory.json", "snapshot-dates.sql"))
            self.assertEqual(item["sha256"], hashlib.sha256((path.parent / item["path"]).read_bytes()).hexdigest())
        inventory = json.loads((path.parent / "projects-inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(candidate["calendar"], build_calendar(inventory["timestamps"]))
        script = (path.parent / "snapshot-dates.sql").read_text(encoding="utf-8")
        self.assertEqual(script, snapshot_sql(candidate["calendar"]))
        expected = [row["snapshot_at"] for row in candidate["calendar"]]
        for attempt in range(2):
            self.sql(script)
            self.assertEqual(self.sql("SELECT snapshot_at FROM snapshot ORDER BY snapshot_at;").splitlines(), expected)
            self.assertEqual(int(self.sql("SELECT count(*) FROM snapshot;")), candidate["snapshot_count"])
        self.assert_reference_only()


if __name__ == "__main__":
    unittest.main()
