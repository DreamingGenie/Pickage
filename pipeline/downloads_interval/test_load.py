"""Exercise real aggregation and immutable publication with fixed small inputs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import duckdb

from pipeline.downloads.test_bronze import FakeS3
from pipeline.downloads.test_support import make_source
from pipeline.minio.ingest_raw import client
from pipeline.snapshot.policy import build_calendar, policy_sha256 as time_policy_sha256
from . import load


def prepared_fixture(root: Path) -> dict:
    source = root / "source"
    make_source(source)
    packages = root / "packages.parquet"
    with duckdb.connect() as con:
        con.execute("CREATE TABLE p(package_id INTEGER, name VARCHAR, repo_url VARCHAR)")
        con.executemany("INSERT INTO p VALUES (?,?,?)", [
            (1, "alpha", None), (2, "beta", None), (3, "missing", None), (4, "outside", None)])
        con.execute("COPY p TO ? (FORMAT PARQUET)", [str(packages)])
    interval = build_calendar(["2026-08-28T00:00:00Z", "2026-08-31T00:00:00Z"])[1]
    manifest = {"snapshot": "2026-08-31", "fixture": "immutable-input", "interval": interval}
    checksum = hashlib.sha256(load.encoded(manifest)).hexdigest()
    return {"package_files": [str(packages)], "target_file": str(source / "targets_top100k_20260902.csv"),
            "status_file": str(source / "parquet/downloads_status.parquet"),
            "daily_files": [str(source / f"parquet/downloads/date=2026-08-{d}/part-0.parquet")
                            for d in (28, 29, 30)],
            "interval": interval, "available_start": "2026-08-28", "available_end": "2026-08-31",
            "expected_package_rows": 4, "input_manifest": manifest, "input_manifest_sha256": checksum,
            "lineage": {"input_manifest_sha256": checksum, "policy_sha256": time_policy_sha256()}}


class LoadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prepared = prepared_fixture(self.root)
        self.s3 = FakeS3()
        self.run_id = "fixture-run"

    def execute(self, **options):
        arguments = dict(snapshot="2026-08-31", bronze_run_id="bronze-fixture",
                         bronze_manifest_sha256="a" * 64, curated_run_id="curated-fixture",
                         curated_manifest_sha256="b" * 64, candidate_path=self.root / "candidate.json",
                         candidate_sha256="c" * 64, run_id=self.run_id, work_dir=self.root / "work",
                         s3=self.s3, memory_limit="256MB", threads=1)
        arguments.update(options)
        with patch.object(load, "prepare", return_value=copy.deepcopy(self.prepared)), \
                patch.object(load, "revalidate"):
            return load.run(**arguments)

    @property
    def prefix(self):
        return f"{load.OUTPUT_PREFIX}/snapshot=2026-08-31/run_id={self.run_id}/"

    def test_publish_reverify_exact_output_and_no_changes_to_prior_objects(self):
        self.s3.objects[("pickage-raw", "existing")] = b"keep raw"
        self.s3.objects[("pickage-curated", "existing")] = b"keep curated"
        first = self.execute()
        with duckdb.connect() as con:
            rows = con.execute("SELECT package_id,download_sum,data_status FROM read_parquet(?) ORDER BY package_id",
                               [str(Path(first["output_dir"]) / "interval_downloads.parquet")]).fetchall()
        self.assertEqual(rows, [(1, 4800, "PARTIAL"), (2, 1, "COMPLETE"),
                                (3, None, "UNAVAILABLE"), (4, None, "UNAVAILABLE")])
        before = dict(self.s3.objects)
        second = self.execute()
        self.assertEqual(first["status"], "PUBLISHED")
        self.assertEqual(second["status"], "REVERIFIED")
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(before, self.s3.objects)

    def test_failure_before_success_resumes_same_run(self):
        with self.assertRaisesRegex(RuntimeError, "before_success"):
            self.execute(failpoint="before_success")
        self.assertNotIn((load.OUTPUT_BUCKET, self.prefix + "_SUCCESS"), self.s3.objects)
        self.assertEqual(self.execute()["status"], "PUBLISHED")
        failures = [json.loads(p.read_text()) for p in (self.root / "work").rglob("execution_report.json")]
        self.assertEqual(sorted(r["status"] for r in failures), ["FAILED", "PUBLISHED"])

    def test_changed_input_rejected_and_prior_success_preserved(self):
        self.execute()
        before = dict(self.s3.objects)
        self.prepared["input_manifest"]["fixture"] = "changed"
        checksum = hashlib.sha256(load.encoded(self.prepared["input_manifest"])).hexdigest()
        self.prepared["input_manifest_sha256"] = checksum
        self.prepared["lineage"]["input_manifest_sha256"] = checksum
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(before, self.s3.objects)

    def test_completed_run_missing_file_is_not_repaired(self):
        self.execute()
        key = (load.OUTPUT_BUCKET, self.prefix + "data/interval_downloads.parquet")
        del self.s3.objects[key]
        with self.assertRaisesRegex(ValueError, "missing"):
            self.execute()
        self.assertNotIn(key, self.s3.objects)

    def test_verify_only_produces_local_artifacts_without_remote_writes(self):
        result = self.execute(verify_only=True)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(self.s3.objects, {})

    def test_invalid_run_id_never_creates_output(self):
        with self.assertRaises(ValueError):
            self.execute(run_id="../escape")
        self.assertFalse((self.root / "work").exists())


@unittest.skipUnless(os.getenv("DOWNLOADS_INTERVAL_MINIO_TEST") == "1",
                     "set DOWNLOADS_INTERVAL_MINIO_TEST=1 for isolated local MinIO publication")
class MinioPublicationTests(unittest.TestCase):
    """Tests output publication against MinIO; input verification has separate tests."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prepared = prepared_fixture(self.root)
        self.s3 = client()
        self.run_id = "test-interval-278-" + uuid.uuid4().hex
        self.addCleanup(self.cleanup_objects)

    execute = LoadTests.execute
    prefix = LoadTests.prefix

    def objects(self):
        return {item["Key"]: [item["Size"], item["ETag"], item["LastModified"].isoformat()]
                for page in self.s3.get_paginator("list_objects_v2").paginate(
                    Bucket=load.OUTPUT_BUCKET, Prefix=self.prefix) for item in page.get("Contents", [])}

    def cleanup_objects(self):
        self.assertTrue(self.prefix.startswith(load.OUTPUT_PREFIX + "/snapshot=2026-08-31/run_id=test-interval-278-"))
        for key in self.objects():
            self.assertTrue(key.startswith(self.prefix))
            self.s3.delete_object(Bucket=load.OUTPUT_BUCKET, Key=key)
        self.assertEqual(self.objects(), {})

    def test_real_roundtrip_preserves_completed_objects(self):
        self.assertEqual(self.execute()["status"], "PUBLISHED")
        before = self.objects()
        self.assertEqual(self.execute()["status"], "REVERIFIED")
        self.assertEqual(before, self.objects())
        marker = self.s3.get_object(Bucket=load.OUTPUT_BUCKET, Key=self.prefix + "_SUCCESS")["Body"]
        try:
            self.assertEqual(len(marker.read().strip()), 64)
        finally:
            marker.close()

    def test_real_failure_resume_and_immutable_input_binding(self):
        with self.assertRaisesRegex(RuntimeError, "after_files"):
            self.execute(failpoint="after_files")
        self.assertNotIn(self.prefix + "_SUCCESS", self.objects())
        self.assertEqual(self.execute()["status"], "PUBLISHED")
        self.prepared["input_manifest"]["fixture"] = "changed"
        checksum = hashlib.sha256(load.encoded(self.prepared["input_manifest"])).hexdigest()
        self.prepared["input_manifest_sha256"] = checksum
        self.prepared["lineage"]["input_manifest_sha256"] = checksum
        with self.assertRaises(ValueError):
            self.execute()


if __name__ == "__main__":
    unittest.main()
