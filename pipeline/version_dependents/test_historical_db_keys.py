import tempfile
from pathlib import Path
import os
import subprocess
import unittest
import uuid

from .historical_db_keys import _calendar_values, _lineage_parts, copy_file, verify_keys


class HistoricalDbKeyValidationUnitTests(unittest.TestCase):
    def test_calendar_normalizes_utc_and_rejects_duplicates(self):
        self.assertEqual(_calendar_values([
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00+00:00"}
        ]), [("2026-08-31", "2026-08-31T21:00:00Z")])
        with self.assertRaises(ValueError):
            _calendar_values([
                {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"},
                {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T22:00:00Z"},
            ])

    def test_lineage_requires_published_identity_fields(self):
        population, calendar = _lineage_parts({
            "population": {"run_id": "population-1", "manifest_sha256": "a" * 64,
                            "snapshot": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"},
            "calendar": {"run_id": "calendar-1", "manifest_sha256": "b" * 64},
        })
        self.assertEqual(population["snapshot_timestamp"], "2026-08-31T21:00:00Z")
        self.assertEqual(calendar["run_id"], "calendar-1")
        with self.assertRaises(ValueError):
            _lineage_parts({"population": {}, "calendar": {}})

    def test_copy_file_streams_only_known_temp_table(self):
        class FakeProcess:
            def __init__(self):
                self.stdin = self
                self.payload = bytearray()
            def write(self, data):
                self.payload.extend(data)
            def flush(self):
                pass
        class FakeDatabase:
            def __init__(self):
                self._process = FakeProcess()
            def _send(self, sql):
                return []
            def _error(self):
                return RuntimeError("failed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identities.copy.tsv"
            path.write_bytes(b"1\talpha\n")
            result = copy_file(FakeDatabase(), "_h7_identities", ("package_id", "name"), path)
            self.assertEqual(result["bytes"], 8)
        with self.assertRaises(ValueError):
            copy_file(FakeDatabase(), "package", ("package_id", "name"), path)


@unittest.skipUnless(os.environ.get("PICKAGE_TEST_CONTAINER"),
                     "PICKAGE_TEST_CONTAINER is required for PostgreSQL key validation tests")
class HistoricalDbKeyValidationIntegrationTests(unittest.TestCase):
    """Each test owns a disposable database and seeds only published lineage."""

    @classmethod
    def setUpClass(cls):
        cls.container = os.environ["PICKAGE_TEST_CONTAINER"]
        cls.database = "pickage_193_keys_" + uuid.uuid4().hex
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls._sql(f'CREATE DATABASE "{cls.database}";', database="postgres")
        # 이름을 직접 적는다. glob 정렬은 문자열 순이라 V10 이 생긴 뒤로 앞 3개가 V1~V3 이 아니다.
        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        names = ("V1__init.sql", "V2__add_curated_load_execution.sql", "V3__add_snapshot_reference_execution.sql")
        cls._sql("BEGIN;\n" + "\n".join((migrations / n).read_text(encoding="utf-8") for n in names) + "\nCOMMIT;")
        cls.command = ["docker", "exec", "-i", cls.container, "psql", "-U", "postgres", "-d", cls.database]

    @classmethod
    def tearDownClass(cls):
        cls._sql(f'DROP DATABASE "{cls.database}" WITH (FORCE);', database="postgres")
        cls.temp.cleanup()

    @classmethod
    def _sql(cls, sql, *, database=None):
        result = subprocess.run(["docker", "exec", "-i", cls.container, "psql", "-X", "-q", "-A", "-t",
                                 "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database or cls.database],
                                input=sql.encode(), capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def setUp(self):
        self._sql("TRUNCATE etl_snapshot_reference,etl_dataset_current,etl_load_attempt,"
                   "etl_load_execution,version,package,snapshot CASCADE;")
        self._sql("""INSERT INTO package VALUES (1,'alpha',NULL),(2,'beta',NULL);
                    INSERT INTO version(version,package_id) VALUES ('1.0.0',1),('2.0.0',1),('1.0.0',2);
                    INSERT INTO snapshot VALUES (DATE '2026-08-30'),(DATE '2026-08-31');
                    BEGIN; SET CONSTRAINTS ALL DEFERRED;
                    INSERT INTO etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,actual_counts,error_message,active_attempt_id) VALUES
                      ('pop-1','package-version','PUBLISHED','2026-08-31','2026-08-31 21:00:00','curated-run','run',repeat('a',64),repeat('c',64),'{}','{}',NULL,NULL,'pop-attempt'),
                      ('cal-1','snapshot-reference','PUBLISHED',NULL,NULL,NULL,'calendar',repeat('b',64),repeat('d',64),'{}','{}',NULL,NULL,'cal-attempt');
                    INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,completed_at) VALUES
                      ('pop-attempt','pop-1','PUBLISHED','COMMIT',clock_timestamp()),('cal-attempt','cal-1','PUBLISHED','COMMIT',clock_timestamp());
                    INSERT INTO etl_dataset_current(dataset,execution_id,snapshot_at,manifest_sha256,manifest)
                      VALUES ('package-version','pop-1','2026-08-31',repeat('a',64),'{}');
                    INSERT INTO etl_snapshot_reference(execution_id,snapshot_at,snapshot_timestamp)
                      VALUES ('cal-1','2026-08-30','2026-08-30 21:00:00+00'),('cal-1','2026-08-31','2026-08-31 21:00:00+00'); COMMIT;""")
        self.identity = self.root / "identities.copy.tsv"
        self.version = self.root / "versions.copy.tsv"
        self.identity.write_bytes("1\talpha\n2\tbeta\n".encode())
        self.version.write_bytes("1\t1.0.0\n1\t2.0.0\n2\t1.0.0\n".encode())
        self.calendar = [{"snapshot_at": "2026-08-30", "snapshot_timestamp": "2026-08-30T21:00:00Z"},
                         {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"}]
        self.lineage = {"population": {"run_id": "curated-run", "manifest_sha256": "a" * 64,
                                        "snapshot": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"},
                        "calendar": {"run_id": "cal-1", "manifest_sha256": "b" * 64}}

    def test_success_and_service_rows_unchanged(self):
        before = self._sql("SELECT count(*) FROM package UNION ALL SELECT count(*) FROM version;")
        result = verify_keys(self.command, self.root, self.identity, self.version,
                             self.calendar, self.lineage, {"identities": 2, "versions": 3})
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(before, self._sql("SELECT count(*) FROM package UNION ALL SELECT count(*) FROM version;"))

    def test_missing_version_and_identity_name_are_rejected(self):
        self.version.write_bytes(b"1\tmissing\n")
        with self.assertRaisesRegex(ValueError, "version composite"):
            verify_keys(self.command, self.root, self.identity, self.version, self.calendar, self.lineage,
                        {"identities": 2, "versions": 1})
        self.identity.write_bytes(b"1\twrong\n2\tbeta\n")
        self.version.write_bytes(b"1\t1.0.0\n1\t2.0.0\n2\t1.0.0\n")
        with self.assertRaisesRegex(ValueError, "ID/name"):
            verify_keys(self.command, self.root, self.identity, self.version, self.calendar, self.lineage,
                        {"identities": 2, "versions": 3})

    def test_date_timestamp_and_lineage_are_rejected(self):
        for calendar, lineage in [
            ([{"snapshot_at": "2026-09-01", "snapshot_timestamp": "2026-09-01T21:00:00Z"}], self.lineage),
            ([{"snapshot_at": "2026-08-30", "snapshot_timestamp": "2026-08-30T20:00:00Z"}], self.lineage),
            (self.calendar, {**self.lineage, "population": {**self.lineage["population"], "run_id": "wrong"}}),
        ]:
            with self.assertRaises(ValueError):
                verify_keys(self.command, self.root, self.identity, self.version, calendar, lineage,
                            {"identities": 2, "versions": 3})

    def test_duplicate_key_is_rejected_by_temp_unique_index(self):
        self.version.write_bytes(b"1\t1.0.0\n1\t1.0.0\n2\t1.0.0\n")
        with self.assertRaisesRegex(RuntimeError, "unique|duplicate"):
            verify_keys(self.command, self.root, self.identity, self.version, self.calendar, self.lineage,
                        {"identities": 2, "versions": 3})


if __name__ == "__main__":
    unittest.main()
