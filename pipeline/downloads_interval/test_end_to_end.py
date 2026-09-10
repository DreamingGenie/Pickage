"""Opt-in full-chain test against a real local MinIO instance."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

import duckdb

from pipeline.minio.ingest_raw import client
from . import load
from .test_input import InputFixture


@unittest.skipUnless(os.getenv("DOWNLOADS_INTERVAL_MINIO_TEST") == "1",
                     "set DOWNLOADS_INTERVAL_MINIO_TEST=1 for local MinIO full-chain test")
class MinioInputToPublishTests(unittest.TestCase):
    """Upload only unique fixture prefixes, then exercise every load phase."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        suffix = uuid.uuid4().hex
        self.fixture = InputFixture(self.root, bronze_run_id="test-interval-278-bronze-" + suffix,
                                    curated_run_id="test-interval-278-curated-" + suffix)
        self.run_id = "test-interval-278-output-" + suffix
        self.s3 = client()
        self.uploaded = []
        self.addCleanup(self.cleanup_objects)
        self.upload_fixture_objects()

    def upload_fixture_objects(self):
        for (bucket, key), body in self.fixture.s3.objects.items():
            self.s3.put_object(Bucket=bucket, Key=key, Body=body)
            self.uploaded.append((bucket, key))

    def cleanup_objects(self):
        output_prefix = f"{load.OUTPUT_PREFIX}/snapshot={self.fixture.snapshot}/run_id={self.run_id}"
        prefixes = {
            "pickage-raw": self.fixture.bronze_prefix + "/",
            "pickage-curated": self.fixture.curated_prefix + "/",
            load.OUTPUT_BUCKET: output_prefix + "/",
        }
        for bucket, prefix in prefixes.items():
            keys = self.list_prefix(bucket, prefix)
            for key in keys:
                self.assertTrue(key.startswith(prefix))
                self.s3.delete_object(Bucket=bucket, Key=key)
            self.assertEqual(self.list_prefix(bucket, prefix), [])

    def list_prefix(self, bucket, prefix):
        return [item["Key"] for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
                for item in page.get("Contents", [])]

    def object_snapshot(self, bucket, prefix):
        return [(item["Key"], item["Size"], item["ETag"])
                for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
                for item in page.get("Contents", [])]

    def test_real_input_aggregate_publish_and_reverify(self):
        args = dict(snapshot=self.fixture.snapshot, bronze_run_id=self.fixture.bronze_run_id,
                    bronze_manifest_sha256=self.fixture.bronze_sha,
                    curated_run_id=self.fixture.curated_run_id,
                    curated_manifest_sha256=self.fixture.curated_sha,
                    candidate_path=self.root / "candidate.json", candidate_sha256="c" * 64,
                    run_id=self.run_id, work_dir=self.root / "work", s3=self.s3,
                    workers=2, threads=1, memory_limit="256MB")
        with patch("pipeline.downloads_interval.input.read_candidate", return_value=self.fixture.candidate):
            first = load.run(**args)
            output_file = Path(first["output_dir"]) / "interval_downloads.parquet"
            with duckdb.connect() as con:
                self.assertEqual(con.execute("SELECT package_id, download_sum, data_status, expected_days, valid_days FROM read_parquet(?)", [str(output_file)]).fetchall(), [(1, 10, "PARTIAL", 7, 1)])
            before = {
                (bucket, prefix): self.object_snapshot(bucket, prefix)
                for bucket, prefix in (
                    ("pickage-raw", self.fixture.bronze_prefix + "/"),
                    ("pickage-curated", self.fixture.curated_prefix + "/"),
                    (load.OUTPUT_BUCKET, f"{load.OUTPUT_PREFIX}/snapshot={self.fixture.snapshot}/run_id={self.run_id}/"),
                )
            }
            second = load.run(**args)
        self.assertEqual(first["status"], "PUBLISHED")
        self.assertEqual(second["status"], "REVERIFIED")
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        after = {
            (bucket, prefix): self.object_snapshot(bucket, prefix)
            for bucket, prefix in (
                ("pickage-raw", self.fixture.bronze_prefix + "/"),
                ("pickage-curated", self.fixture.curated_prefix + "/"),
                (load.OUTPUT_BUCKET, f"{load.OUTPUT_PREFIX}/snapshot={self.fixture.snapshot}/run_id={self.run_id}/"),
            )
        }
        self.assertEqual(before, after)
        output_prefix = f"{load.OUTPUT_PREFIX}/snapshot={self.fixture.snapshot}/run_id={self.run_id}/"
        self.assertTrue(self.list_prefix(load.OUTPUT_BUCKET, output_prefix))


if __name__ == "__main__":
    unittest.main()
