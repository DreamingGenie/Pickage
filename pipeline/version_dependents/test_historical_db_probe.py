import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from .historical_db_probe import apply_sample, read_catalog


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = os.environ.get("PICKAGE_TEST_CONTAINER")


@unittest.skipUnless(CONTAINER, "PICKAGE_TEST_CONTAINER is required for PostgreSQL probe tests")
class HistoricalDbProbeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "pickage_193_probe_" + uuid.uuid4().hex
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls._sql("CREATE DATABASE \"%s\";" % cls.database, database="postgres")
        migration = (ROOT / "backend/src/main/resources/db/migration/V1__init.sql").read_text(encoding="utf-8")
        cls._sql(migration)
        cls.command = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", cls.database]

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "database", "") and __import__("re").fullmatch(r"pickage_193_probe_[0-9a-f]{32}", cls.database):
            cls._sql("DROP DATABASE \"%s\" WITH (FORCE);" % cls.database, database="postgres")
        if getattr(cls, "temp", None):
            cls.temp.cleanup()

    @classmethod
    def _sql(cls, sql, *, database=None):
        command = ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-q", "-A", "-t",
                   "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database or cls.database]
        result = subprocess.run(command, input=sql.encode(), capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def setUp(self):
        self._sql("TRUNCATE package_version_snapshot,package_snapshot,version,package,snapshot CASCADE;"
                   "INSERT INTO package VALUES (1,'alpha',NULL),(2,'other',NULL);"
                   "INSERT INTO version(version,package_id) VALUES ('1.0.0',1),('2.0.0',1),('1.0.0',2),('v\tquoted',1);"
                   "INSERT INTO snapshot VALUES ('2026-08-30'),('2026-08-31');"
                   "INSERT INTO package_snapshot VALUES (1,'2026-08-30',123,4,5);"
                   "INSERT INTO package_version_snapshot VALUES (1,'1.0.0','2026-08-30',7),(2,'1.0.0','2026-08-30',9);")

    def test_read_catalog_is_bounded_and_read_only(self):
        self.assertEqual(read_catalog(self.command, self.root, ["alpha"], ["2026-08-31"]), {
            "packages": [{"package_id": 1, "name": "alpha"}],
            "versions": [{"package_id": 1, "version": "1.0.0"}, {"package_id": 1, "version": "2.0.0"}, {"package_id": 1, "version": "v\tquoted"}],
            "snapshots": [{"snapshot_at": "2026-08-31"}],
        })
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "2")

    def test_insert_update_zero_and_idempotent_rerun(self):
        counts = [{"package_id": 1, "version": "2.0.0", "snapshot_at": "2026-08-31", "dependents_count": 4},
                  {"package_id": 1, "version": "1.0.0", "snapshot_at": "2026-08-30", "dependents_count": 0}]
        identities = [{"package_id": 1, "name": "alpha"}]
        self.assertEqual(apply_sample(self.command, self.root, counts, identities), {"rows": 2, "changed_rows": 2})
        self.assertEqual(apply_sample(self.command, self.root, counts, identities), {"rows": 2, "changed_rows": 0})
        self.assertEqual(self._sql("SELECT dependents_count FROM package_version_snapshot WHERE package_id=1 AND version='2.0.0' AND snapshot_at='2026-08-31';"), "4")
        self.assertEqual(self._sql("SELECT dependents_count FROM package_version_snapshot WHERE package_id=1 AND version='1.0.0' AND snapshot_at='2026-08-30';"), "0")

    def test_unrelated_rows_are_preserved(self):
        apply_sample(self.command, self.root, [{"package_id": 1, "version": "1.0.0", "snapshot_at": "2026-08-30", "dependents_count": 3}], [{"package_id": 1, "name": "alpha"}])
        self.assertEqual(self._sql("SELECT dependents_count FROM package_version_snapshot WHERE package_id=2;"), "9")
        self.assertEqual(self._sql("SELECT downloads,stars,open_issues FROM package_snapshot WHERE package_id=1;"), "123|4|5")

    def test_count_requires_identity_and_existing_snapshot(self):
        row = {"package_id": 1, "version": "1.0.0", "snapshot_at": "2026-08-31", "dependents_count": 2}
        with self.assertRaises(ValueError):
            apply_sample(self.command, self.root, [row], [])
        with self.assertRaises(ValueError):
            apply_sample(self.command, self.root, [dict(row, snapshot_at="2026-09-01")], [{"package_id": 1, "name": "alpha"}])
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "2")

    def test_copy_text_escaping_preserves_version(self):
        result = apply_sample(self.command, self.root, [{"package_id": 1, "version": "v\tquoted", "snapshot_at": "2026-08-31", "dependents_count": 6}], [{"package_id": 1, "name": "alpha"}])
        self.assertEqual(result["changed_rows"], 1)
        self.assertEqual(self._sql("SELECT dependents_count FROM package_version_snapshot WHERE package_id=1 AND version='v' || chr(9) || 'quoted';"), "6")

    def test_invalid_identity_or_foreign_key_rolls_back(self):
        with self.assertRaises(ValueError):
            apply_sample(self.command, self.root, [{"package_id": 1, "version": "2.0.0", "snapshot_at": "2026-08-31", "dependents_count": 2}], [{"package_id": 1, "name": "wrong"}])
        with self.assertRaises(ValueError):
            apply_sample(self.command, self.root, [{"package_id": 1, "version": "missing", "snapshot_at": "2026-08-31", "dependents_count": 2}], [{"package_id": 1, "name": "alpha"}])
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "2")

    def test_duplicate_negative_null_and_overflow_are_rejected(self):
        base = {"package_id": 1, "version": "2.0.0", "snapshot_at": "2026-08-31", "dependents_count": 1}
        with self.assertRaises(ValueError):
            apply_sample(self.command, self.root, [base, dict(base)], [{"package_id": 1, "name": "alpha"}])
        for value in (-1, None, 2_147_483_648, True):
            with self.assertRaises(ValueError):
                row = dict(base, dependents_count=value)
                apply_sample(self.command, self.root, [row], [{"package_id": 1, "name": "alpha"}])

    def test_production_database_name_is_refused(self):
        production_command = self.command[:-1] + ["postgres"]
        with self.assertRaises(PermissionError):
            apply_sample(production_command, self.root, [], [])
