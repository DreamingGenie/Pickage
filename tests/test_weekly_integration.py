"""Real producers: full baseline -> weekly min -> failure recovery -> replay."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
from pipeline.orchestration import runner
from pipeline.orchestration.weekly_request import build_request
from pipeline.orchestration.storage import BUCKET, PREFIX
from tests.weekly_fixture import make_weekly_fixture
from tests.orchestration_fixture import BRONZE_RUN, DOWNLOAD_RUN, SNAPSHOT


class WeeklyIntegrationTests(unittest.TestCase):
    def test_real_stages_and_recovery(self):
        with tempfile.TemporaryDirectory(prefix="weekly-") as folder:
            root = Path(folder)
            count = int(os.environ.get("WEEKLY_FIXTURE_PACKAGES", "3"))
            fixture, first = make_weekly_fixture(root / "fixture", count)
            s3 = fixture.s3
            endpoint = os.environ.get("WEEKLY_TEST_ENDPOINT")
            if endpoint:
                # Dedicated local container only. Never accept a production endpoint.
                if endpoint not in ("http://minio:9000", "http://127.0.0.1:19020"):
                    raise ValueError("Weekly integration only allows its isolated local MinIO")
                import boto3
                from botocore.config import Config
                s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id="weekly-local",
                    aws_secret_access_key="weekly-local-test-only", region_name="us-east-1",
                    config=Config(s3={"addressing_style": "path"}))
                from tests.orchestration_fixture import BucketMapS3
                import uuid
                suffix = uuid.uuid4().hex[:12]
                mapping = {b: b + "-" + suffix for b in ("pickage-raw", "pickage-curated")}
                for bucket in mapping.values():
                    s3.create_bucket(Bucket=bucket)
                s3 = BucketMapS3(s3, mapping)
                for (bucket, key), body in fixture.s3.objects.items():
                    s3.put_object(Bucket=bucket, Key=key, Body=body)
            baseline = runner.run(first, s3, root / "work")
            request = build_request(s3, SNAPSHOT, "weekly-test", root / "work",
                bronze_run_id=BRONZE_RUN, download_run_id=DOWNLOAD_RUN,
                options={"workers": 1, "threads": 2, "memory_limit": "1GB", "repository_engine": "native"})
            self.assertEqual(request["snapshot_timestamp"], "2026-08-31T21:01:10Z")
            current_key = PREFIX + "/_current.json"
            before = s3.get_object(Bucket=BUCKET, Key=current_key)["Body"].read()
            def fail(point):
                if point == "before_stage:repository":
                    raise RuntimeError("injected weekly interruption")
            with self.assertRaisesRegex(RuntimeError, "weekly interruption"):
                runner.run(request, s3, root / "work", failpoint=fail)
            self.assertEqual(s3.get_object(Bucket=BUCKET, Key=current_key)["Body"].read(), before)
            # The public one-command entry point resumes its pinned request.
            from pipeline.orchestration.storage import atomic_json
            from pipeline.orchestration.__main__ import main
            atomic_json(root / "work" / "requests" / "weekly-test.json", request)
            with patch("pipeline.minio.ingest_raw.client", return_value=s3):
                self.assertEqual(main(["weekly", "--snapshot", SNAPSHOT, "--run-id", "weekly-test",
                                       "--work-dir", str(root / "work")]), 0)
            second = json.loads(s3.get_object(Bucket=BUCKET,
                Key=runner.run_prefix(request) + "/run_manifest.json")["Body"].read())
            with patch.object(runner, "_default_executor", side_effect=AssertionError("replay executed a stage")):
                self.assertEqual(runner.run(request, s3, root / "work", resume=True), second)
            self.assertEqual(second["status"], "COMPLETE")
            self.assertFalse(second["db_loaded"])
            records = second["stages"]["package_version"]["files"]
            def read(part, query):
                files = []
                for record in records:
                    if part in record["key"]:
                        path = root / (str(len(files)) + "-" + part.strip('/').replace('/', '-') + ".parquet")
                        path.write_bytes(s3.get_object(Bucket=BUCKET, Key=record["key"])["Body"].read())
                        files.append(str(path))
                self.assertTrue(files, part)
                with duckdb.connect() as con:
                    con.read_parquet(files, hive_partitioning=False).create_view("v")
                    return con.execute(query).fetchall()
            self.assertEqual(read("/package/data/", "SELECT count(*) FROM v"), [(count,)])
            self.assertEqual(read("/master_package/data/", "SELECT count(*) FROM v"), [(count + 1,)])
            self.assertEqual(read("/version/data/", "SELECT description,licenses FROM v WHERE description IS NOT NULL AND version='2.0.0'"), [("alpha", '["MIT"]')])
            self.assertEqual(read("/changes/package_upserts.parquet", "SELECT count(*) FROM v WHERE change_type='INSERT'"), [(2,)])
            self.assertEqual(read("/quality/metadata_provenance/", "SELECT source_version FROM v WHERE name='alpha' AND version='3.0.0'"), [("1.0.0",)])
            # Old completed retries cannot rewind the parent of future requests.
            after = s3.get_object(Bucket=BUCKET, Key=current_key)["Body"].read()
            runner.run(first, s3, root / "work", resume=True)
            self.assertEqual(s3.get_object(Bucket=BUCKET, Key=current_key)["Body"].read(), after)
            evidence = {"status": "PASSED", "fixture": "SYNTHETIC_FULL_TO_MIN",
                "packages": count, "stages": list(second["stages"]),
                "baseline_complete": baseline["status"], "weekly_complete": second["status"],
                "failure_recovery": True, "replay_no_stage_execution": True,
                "local_minio": bool(endpoint), "db_loaded": False}
            print("WEEKLY_EVIDENCE " + json.dumps(evidence), flush=True)


if __name__ == "__main__":
    unittest.main()
