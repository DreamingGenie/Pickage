import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from . import build
from . import input as source
from .test_input import Fixture, SNAPSHOT
from .policy import canonical_bytes


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = Fixture(self.root)

    def run_build(self, **options):
        with patch.object(source, "read_candidate", return_value=self.fixture.candidate):
            return build.run(**self.fixture.args, run_id="integrated", work_dir=self.root / "work",
                             s3=self.fixture.s3, **options)

    def test_full_population_partial_zero_null_and_quality_alignment(self):
        before = dict(self.fixture.s3.objects)
        result = self.run_build(verify_only=True)
        self.assertEqual(before, self.fixture.s3.objects)
        out = Path(result["output_dir"])
        with duckdb.connect() as con:
            rows = con.execute("SELECT package_id,downloads,stars,open_issues FROM read_parquet(?) ORDER BY 1",
                               [str(out / "package_snapshot.parquet")]).fetchall()
            self.assertEqual(rows, [(1, 0, 0, None), (2, 12, 100, 2), (3, None, None, None)])
            quality = con.execute("SELECT package_id,download_sum,data_status,repository_reason,repository_version "
                                  "FROM read_parquet(?) ORDER BY 1", [str(out / "quality.parquet")]).fetchall()
            self.assertEqual(quality, [(1, 0, "COMPLETE", "SELECTED", "1.0.0"),
                                      (2, 12, "PARTIAL", "SELECTED", "2.0.0"),
                                      (3, None, "UNAVAILABLE", "NO_VALID_REPOSITORY", None)])
            columns = {row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)",
                                                   [str(out / "quality.parquet")]).fetchall()}
        expected = {"repository_" + name for name, _ in build.SCHEMAS["selection_files"] if name != "package_id"}
        self.assertTrue(expected <= columns)
        self.assertEqual(result["quality"]["download_partial_sum"], "12")
        self.assertEqual(result["quality"]["download_status"], {"COMPLETE": 1, "PARTIAL": 1, "UNAVAILABLE": 1})
        manifest = json.loads(Path(result["manifest_path"]).read_text())
        self.assertEqual({item["role"] for item in manifest["files"]}, {"package_snapshot", "package_identity", "quality"})
        self.assertEqual(len(manifest["files"]), 3)

    def test_missing_extra_duplicate_and_schema_rows_rejected(self):
        cases = [
            ("download_files", "DELETE FROM changed WHERE package_id=3", "count mismatch"),
            ("repository_files", "UPDATE changed SET package_id=999 WHERE package_id=3", "missing/extra"),
            ("selection_files", "UPDATE changed SET package_id=1 WHERE package_id=3", "duplicate"),
            ("repository_files", "ALTER TABLE changed ALTER stars TYPE BIGINT", "schema mismatch"),
        ]
        self._invalid_cases(cases)

    def test_invalid_metric_coverage_time_and_quality_rows_rejected(self):
        cases = [
            ("download_files", "UPDATE changed SET download_sum=-1 WHERE package_id=1", "values/coverage/status"),
            ("download_files", "UPDATE changed SET data_status='COMPLETE' WHERE package_id=2", "values/coverage/status"),
            ("download_files", "UPDATE changed SET valid_days=8 WHERE package_id=2", "values/coverage/status"),
            ("download_files", "UPDATE changed SET expected_days=8 WHERE package_id=1", "interval coverage"),
            ("download_files", "UPDATE changed SET input_manifest_sha256='wrong' WHERE package_id=1", "lineage"),
            ("repository_files", "UPDATE changed SET stars=-1 WHERE package_id=1", "negative repository"),
            ("repository_files", "UPDATE changed SET snapshot_at=DATE '2026-08-30' WHERE package_id=1", "snapshot mismatch"),
            ("selection_files", "UPDATE changed SET observed_timestamp=TIMESTAMPTZ '2026-08-31T00:00:00Z' WHERE package_id=1", "exact timestamp"),
            ("selection_files", "UPDATE changed SET mapping_status='bad' WHERE package_id=1", "selection status"),
            ("repository_files", "UPDATE changed SET open_issues=1 WHERE package_id=3", "NULL quality mismatch"),
        ]
        self._invalid_cases(cases)

    def _invalid_cases(self, cases):
        original = self.fixture.prepare()
        for index, (group, mutation, message) in enumerate(cases):
            prepared = copy.deepcopy(original)
            path = self.root / f"invalid-{index}.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE changed AS SELECT * FROM read_parquet(?)", [prepared[group][0]])
                con.execute(mutation)
                con.execute("COPY changed TO ? (FORMAT PARQUET)", [str(path)])
            prepared[group] = [str(path)]
            with self.subTest(mutation=mutation), duckdb.connect() as con:
                with self.assertRaisesRegex(ValueError, message):
                    build.validate_inputs(con, prepared)

    def test_publish_callback_failure_retry_and_completed_run_reuses_bytes(self):
        prefix = f"{build.PREFIX}/snapshot={SNAPSHOT}/run_id=integrated"
        with patch.object(build, "revalidate", side_effect=RuntimeError("upstream changed")):
            with self.assertRaisesRegex(RuntimeError, "upstream changed"):
                self.run_build()
        self.assertNotIn((source.BUCKET, prefix + "/_SUCCESS"), self.fixture.s3.objects)
        with patch.object(build, "_build", side_effect=AssertionError("must reuse immutable output")):
            first = self.run_build()
            objects = dict(self.fixture.s3.objects)
            second = self.run_build()
        self.assertEqual(first["status"], "PUBLISHED")
        self.assertEqual(second["status"], "REVERIFIED")
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(objects, self.fixture.s3.objects)

    def test_failure_after_files_resumes_saved_local_artifact(self):
        with self.assertRaisesRegex(RuntimeError, "after_files"):
            self.run_build(failpoint="after_files")
        with patch.object(build, "_build", side_effect=AssertionError("must reuse local artifact")):
            result = self.run_build()
        self.assertEqual(result["status"], "PUBLISHED")

    def test_existing_run_changed_contract_or_missing_output_is_not_overwritten(self):
        result = self.run_build()
        before = dict(self.fixture.s3.objects)
        with patch.object(build, "contract_sha256", return_value="f" * 64):
            with self.assertRaisesRegex(ValueError, "different input, policy, or code"):
                self.run_build()
        self.assertEqual(before, self.fixture.s3.objects)
        key = (source.BUCKET, result["prefix"] + "/data/quality.parquet")
        del self.fixture.s3.objects[key]
        with self.assertRaises(Exception):
            self.run_build()
        self.assertNotIn(key, self.fixture.s3.objects)
        self.assertIn((source.BUCKET, result["prefix"] + "/_SUCCESS"), self.fixture.s3.objects)

    def test_completed_metadata_cannot_hide_changed_service_values(self):
        result = self.run_build()
        manifest = json.loads(Path(result["manifest_path"]).read_text())
        changed = self.root / "changed-output.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE changed AS SELECT * FROM read_parquet(?)",
                        [str(Path(result["output_dir"]) / "package_snapshot.parquet")])
            con.execute("UPDATE changed SET stars=99 WHERE package_id=1")
            con.execute("COPY changed TO ? (FORMAT PARQUET)", [str(changed)])
        body = changed.read_bytes()
        record = next(item for item in manifest["files"] if item["role"] == "package_snapshot")
        record.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        prefix = result["prefix"]
        self.fixture.s3.objects[(source.BUCKET, prefix + "/data/package_snapshot.parquet")] = body
        manifest_body = canonical_bytes(manifest)
        checksum = hashlib.sha256(manifest_body).hexdigest()
        self.fixture.s3.objects[(source.BUCKET, prefix + "/run_manifest.json")] = manifest_body
        self.fixture.s3.objects[(source.BUCKET, prefix + "/_SUCCESS")] = (checksum + "\n").encode()
        self.fixture.s3.objects[(source.BUCKET, prefix + "/_INPUT.json")] = canonical_bytes({"manifest_sha256": checksum})
        before = dict(self.fixture.s3.objects)
        with self.assertRaisesRegex(ValueError, "output values or quality differ"):
            self.run_build()
        self.assertEqual(before, self.fixture.s3.objects)


if __name__ == "__main__":
    unittest.main()
