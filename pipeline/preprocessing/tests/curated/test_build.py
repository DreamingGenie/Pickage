import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

try:
    from pipeline.preprocessing.tests.curated.test_storage import FakeS3
    from pipeline.preprocessing.tests.curated.test_transform import _requirements_file, _requirement, _version, _version_file
except ImportError:  # pragma: no cover - package invocation
    from pipeline.preprocessing.tests.curated.test_storage import FakeS3
    from pipeline.preprocessing.tests.curated.test_transform import _requirements_file, _requirement, _version, _version_file

from pipeline.preprocessing.curated import build
from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.preprocessing.curated.transform import ValidationError


SNAPSHOT = "2026-08-31"
BRONZE_RUN = "bronze-test"


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _parquet_record(s3, table, run_id, path):
    body = path.read_bytes()
    key = f"depsdev/v1/{table}/snapshot={SNAPSHOT}/run_id={run_id}/data/{path.name}"
    s3.put_object(Bucket=build.RAW_BUCKET, Key=key, Body=body)
    return {"key": key, "bytes": len(body), "sha256": _sha(body)}


def _seed_bronze(s3, root, versions, requirements, run_id=BRONZE_RUN, complete=True):
    versions_path = _version_file(root, versions)
    requirements_path = _requirements_file(root, requirements)
    for table, path, rows in (("versions_full", versions_path, versions),
                              ("requirements", requirements_path, requirements)):
        record = _parquet_record(s3, table, run_id, path)
        prefix = f"depsdev/v1/{table}/snapshot={SNAPSHOT}/run_id={run_id}"
        source = {"status": "done", "verify": "ok", "snapshot": SNAPSHOT,
                  "table": table, "rows": len(rows), "gcs_files": 1,
                  "gcs_bytes": record["bytes"]}
        source_body = json_bytes(source)
        s3.put_object(Bucket=build.RAW_BUCKET, Key=prefix + "/source_manifest.json", Body=source_body)
        manifest = {"contract_version": 1, "run_id": run_id, "status": "PASSED",
                    "table": table, "snapshot": SNAPSHOT, "row_count": len(rows),
                    "file_count": 1, "bytes": record["bytes"],
                    "verification": "GET_SHA256_ALL_FILES",
                    "source_manifest_sha256": _sha(source_body), "files": [record]}
        s3.put_object(Bucket=build.RAW_BUCKET, Key=prefix + "/run_manifest.json",
                      Body=json_bytes(manifest))
        if complete:
            s3.put_object(Bucket=build.RAW_BUCKET, Key=prefix + "/_SUCCESS", Body=b"")


def _valid_inputs(names=("b",)):
    versions = [_version(name, "1.0.0", index + 1,
                         repo=f"https://github.com/example/{name}.git")
                for index, name in enumerate(names)]
    requirements = [_requirement(name, "1.0.0") for name in names]
    return versions, requirements


class BuildIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def run_build(self, run_id, bronze_run=BRONZE_RUN):
        return build.run(self.s3, SNAPSHOT, bronze_run, run_id,
                         Path(self.temp.name) / run_id, workers=1, threads=1)

    def test_missing_current_does_not_reset_existing_id_registry(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements)
        self.run_build('curated-1')
        del self.s3.objects[(build.CURATED_BUCKET, build.CURRENT)]
        with self.assertRaisesRegex(ValidationError, 'Current pointer missing'):
            self.run_build('curated-2')
        self.assertNotIn((build.CURATED_BUCKET, build.CURRENT), self.s3.objects)

    def test_complete_run_publishes_outputs_and_current(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements)
        manifest = self.run_build("curated-1")
        prefix = "depsdev/v1/package-version/snapshot=2026-08-31/run_id=curated-1"
        self.assertEqual(manifest["status"], "PASSED")
        self.assertIn((build.CURATED_BUCKET, prefix + "/_SUCCESS"), self.s3.objects)
        pointer = json.loads(self.s3.get_object(Bucket=build.CURATED_BUCKET,
                                                 Key=build.CURRENT)["Body"].read())
        self.assertEqual(pointer["run_prefix"], prefix)

    def test_same_run_reverifies_without_mutating_outputs(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements)
        self.run_build("curated-1")
        before = dict(self.s3.objects)
        self.run_build("curated-1")
        self.assertEqual(self.s3.objects, before)

    def test_second_run_reuses_id_lineage(self):
        first, first_req = _valid_inputs(("b",))
        _seed_bronze(self.s3, self.temp.name, first, first_req, run_id="bronze-1")
        self.run_build("curated-1", "bronze-1")
        second, second_req = _valid_inputs(("a", "b"))
        _seed_bronze(self.s3, self.temp.name, second, second_req, run_id="bronze-2")
        self.run_build("curated-2", "bronze-2")
        pointer = json.loads(self.s3.get_object(Bucket=build.CURATED_BUCKET,
                                                 Key=build.CURRENT)["Body"].read())
        self.assertTrue(pointer["run_prefix"].endswith("run_id=curated-2"))

    def test_incomplete_bronze_blocks_publication(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements, complete=False)
        with self.assertRaises(ValidationError):
            self.run_build("curated-1")
        self.assertNotIn((build.CURATED_BUCKET, build.CURRENT), self.s3.objects)

    def test_failed_transform_leaves_previous_pointer_intact(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements)
        self.run_build("curated-1")
        before = self.s3.objects[(build.CURATED_BUCKET, build.CURRENT)]
        new_versions, new_requirements = _valid_inputs(("a", "b"))
        _seed_bronze(self.s3, self.temp.name, new_versions, new_requirements, run_id="bronze-2")
        with patch.object(build, "transform", side_effect=ValidationError("injected")):
            with self.assertRaises(ValidationError):
                self.run_build("curated-2", "bronze-2")
        self.assertEqual(self.s3.objects[(build.CURATED_BUCKET, build.CURRENT)], before)

    def test_crash_after_manifest_before_success_recovers(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements)
        original = build.put_immutable
        failed = {"value": False}

        def crash_on_success(s3, bucket, key, body):
            if key.endswith("/_SUCCESS") and not failed["value"]:
                failed["value"] = True
                raise RuntimeError("injected crash")
            return original(s3, bucket, key, body)

        with patch.object(build, "put_immutable", side_effect=crash_on_success):
            with self.assertRaises(RuntimeError):
                self.run_build("curated-1")
        self.assertNotIn((build.CURATED_BUCKET, build.CURRENT), self.s3.objects)
        self.run_build("curated-1")
        self.assertIn((build.CURATED_BUCKET, build.CURRENT), self.s3.objects)

    def test_checksum_corruption_on_completed_run_fails(self):
        versions, requirements = _valid_inputs()
        _seed_bronze(self.s3, self.temp.name, versions, requirements)
        manifest = self.run_build("curated-1")
        record = next(row for row in manifest["files"] if "/package/data/" in row["key"])
        key = (build.CURATED_BUCKET, record["key"])
        body, etag = self.s3.objects[key]
        self.s3.objects[key] = (body + b"corrupt", _sha(body + b"corrupt"))
        with self.assertRaises(ValueError):
            self.run_build("curated-1")

    def test_replaying_old_completed_run_never_rolls_current_back(self):
        first, req = _valid_inputs(("b",))
        _seed_bronze(self.s3, self.temp.name, first, req, run_id="bronze-1")
        self.run_build("curated-1", "bronze-1")
        second, req2 = _valid_inputs(("a", "b"))
        _seed_bronze(self.s3, self.temp.name, second, req2, run_id="bronze-2")
        self.run_build("curated-2", "bronze-2")
        before = self.s3.objects[(build.CURATED_BUCKET, build.CURRENT)]
        self.run_build("curated-1", "bronze-1")
        self.assertEqual(self.s3.objects[(build.CURATED_BUCKET, build.CURRENT)], before)


if __name__ == "__main__":
    unittest.main()
