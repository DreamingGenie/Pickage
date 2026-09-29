"""Pinned local input and output lifecycle tests, with complete Parquet schemas."""
import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from pipeline.postgresql.input import _SCHEMAS
from pipeline.preprocessing.requirements_resolution.input import RAW_SCHEMAS, file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.preprocessing.snapshot.policy import policy_document, policy_sha256
from pipeline.preprocessing.version_dependents.historical_input import prepare_historical_inputs, verify_historical_inputs


STAMP = "2026-08-31T21:01:10.517131Z"


class HistoricalArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-'한글-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        roots = {"curated_outputs": self.root / "curated", "versions_dir": self.root / "versions",
                 "requirements_dir": self.root / "requirements"}
        files, records, counts = {}, [], {}
        with duckdb.connect() as con:
            for table, schema in {**_SCHEMAS, **RAW_SCHEMAS}.items():
                folder = (roots["curated_outputs"] / table / "data" if table in _SCHEMAS
                          else roots["versions_dir" if table == "versions_full" else "requirements_dir"])
                folder.mkdir(parents=True)
                con.execute("CREATE TABLE " + table + "(" + ",".join('"' + n + '" ' + t for n, t in schema) + ")")
                if table == "package":
                    con.execute("INSERT INTO package(package_id,name) VALUES (1,'app'),(2,'dep')")
                elif table == "version":
                    con.execute("INSERT INTO version(package_id,version,published_at) VALUES "
                                "(1,'1.0.0',TIMESTAMP '2026-08-20 12:00:00'),"
                                "(2,'2.0.0',TIMESTAMP '2026-08-31 21:01:10.517131')")
                elif table == "versions_full":
                    con.execute("INSERT INTO versions_full(SnapshotAt,Name,Version,is_release,published_at,dependency_error) "
                                "VALUES (?, 'app','1.0.0',true,TIMESTAMP '2026-08-20 12:00:00',false),"
                                "(?, 'dep','2.0.0',true,TIMESTAMP '2026-08-31 21:01:10.517131',false)", [STAMP, STAMP])
                else:
                    con.execute("INSERT INTO requirements VALUES (?, 'app','1.0.0',"
                                "[{'Name':'dep','Requirement':'^2'}],[],[]),"
                                "(?,'dep','2.0.0',[],[],[])", [STAMP, STAMP])
                path = folder / "fixture.parquet"
                con.execute("COPY " + table + " TO ? (FORMAT PARQUET)", [str(path)])
                files[table] = [str(path)]
                records.append({"table": table, "path": str(path), "bytes": path.stat().st_size,
                                "sha256": file_sha256(path), "rows": 2})
                counts[table] = 2
        prepared = {"dataset": "requirements-resolution-input", "snapshot": "2026-08-31",
                    "snapshot_timestamp": STAMP, "sources": {k: str(v) for k, v in roots.items()},
                    "files": files, "file_records": records, "metadata_records": [], "counts": counts,
                    "snapshot_policy": {"document": policy_document(), "sha256": policy_sha256()},
                    "curated_manifest_sha256": "a" * 64}
        prepared["input_sha256"] = sha256(prepared)
        self.input_path = self.root / "prepared.json"
        self.input_path.write_bytes(canonical_bytes(prepared))
        self.calendar_path = self.root / "calendar.json"
        self.calendar_path.write_bytes(canonical_bytes({"calendar": [
            {"snapshot_at": "2026-08-25", "snapshot_timestamp": "2026-08-25T00:00:00Z"},
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": STAMP}]}))
        self.output = self.root / "output"

    def build(self, **overrides):
        args = dict(input_manifest=self.input_path, input_manifest_sha256=file_sha256(self.input_path),
                    calendar_path=self.calendar_path, calendar_sha256=file_sha256(self.calendar_path),
                    output=self.output, threads=1, memory_limit="512MB", max_temp_size="1GB",
                    expected_snapshot_count=2)
        args.update(overrides)
        return prepare_historical_inputs(**args)

    def test_real_schema_roundtrip_and_independent_histogram(self):
        result = self.build()
        verified = verify_historical_inputs(self.output, result["manifest_sha256"])
        self.assertEqual(verified["dense_target_snapshot_keys"], 3)
        self.assertEqual(verified["snapshots_verified"], 2)
        manifest = json.loads((self.output / "input_manifest.json").read_bytes())
        self.assertFalse(manifest["ready_for_load"])
        self.assertEqual(manifest["count_status"], "NOT_COMPUTED")
        helpers = {Path(path).as_posix().split('/pipeline/')[1] for path in manifest["code_sha256"]}
        self.assertTrue({'preprocessing/requirements_resolution/bridge.py', 'preprocessing/requirements_resolution/input.py',
                         'preprocessing/requirements_resolution/policy.py', 'preprocessing/snapshot/policy.py', "preprocessing/common/curated_input.py"}
                        .issubset(helpers))
        with self.assertRaises(FileExistsError):
            self.build()

    def test_pinned_manifest_rejects_change_before_output_creation(self):
        with self.assertRaisesRegex(ValueError, "Input manifest SHA"):
            self.build(input_manifest_sha256="0" * 64)
        self.assertFalse(self.output.exists())

    def test_mutated_input_never_writes_completion_manifest(self):
        source = self.root / "requirements/fixture.parquet"
        with source.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.output / "input_manifest.json").exists())
        with self.assertRaises(FileExistsError):
            self.build()

    def test_wrong_expected_calendar_count_and_truncated_history_fail_early(self):
        with self.assertRaisesRegex(ValueError, "Expected calendar count"):
            self.build(expected_snapshot_count=229)
        self.assertFalse(self.output.exists())
        document = json.loads(self.calendar_path.read_bytes())
        document["calendar"] = document["calendar"][:1]
        self.calendar_path.write_bytes(canonical_bytes(document))
        with self.assertRaisesRegex(ValueError, "latest observation boundary"):
            self.build(expected_snapshot_count=1)
        self.assertFalse(self.output.exists())

    def test_missing_output_and_wrong_manifest_pin_are_rejected(self):
        result = self.build()
        with self.assertRaisesRegex(ValueError, "manifest SHA"):
            verify_historical_inputs(self.output, "0" * 64)
        (self.output / "target_population.parquet").unlink()
        with self.assertRaisesRegex(ValueError, "file set"):
            verify_historical_inputs(self.output, result["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
