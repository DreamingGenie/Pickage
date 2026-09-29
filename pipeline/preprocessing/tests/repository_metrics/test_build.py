"""Publication boundary and immutable-run regression tests, without a server."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError
import duckdb

from pipeline.preprocessing.repository_metrics.build import canonical_bytes, publish_run, run, sha_file, verify_completed


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.fail_output = False

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Bucket, Key]), "ETag": '"etag"'}

    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.fail_output and Key.endswith(".parquet"):
            raise RuntimeError("injected upload failure")
        if kwargs.get("IfNoneMatch") == "*" and (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Bucket, Key] = bytes(Body)
        self.writes.append(Key)
        return {"ETag": '"etag"'}

    def delete_object(self, Bucket, Key, **kwargs):
        self.objects.pop((Bucket, Key), None)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s3 = MemoryS3()
        self.prepared = {"snapshot": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:01:10.517131",
                         "counts": {"package": 2}, "file_records": []}
        self.kwargs = dict(snapshot="2026-08-31", curated_run_id="curated-v2",
                           curated_outputs=self.root / "source/curated", versions_dir=self.root / "source/versions",
                           projects_dir=self.root / "source/projects", candidate_path=self.root / "source/calendar/candidate.json",
                           run_id="run-one", work_dir=self.root / "runs", spark=SimpleNamespace(version="fixture"), engine="native")

    def tearDown(self):
        self.temp.cleanup()

    def _transform(self, spark, inputs, output):
        target = output / "metric/data"
        target.mkdir(parents=True)
        path = target / "part.parquet"
        with duckdb.connect(":memory:") as con:
            con.execute("COPY (SELECT i::INTEGER package_id, DATE '2026-08-31' snapshot_at, "
                        "0::INTEGER stars, NULL::INTEGER open_issues FROM range(1,3) t(i)) "
                        "TO ? (FORMAT PARQUET)", [str(path)])
        return {"output_counts": {"metric/data": 2}, "validation": "PASSED"}

    def _run(self, transform=None, reverify=None, **overrides):
        kwargs = {**self.kwargs, **overrides}
        with patch("pipeline.preprocessing.repository_metrics.input.prepare_inputs", return_value=dict(self.prepared)), \
             patch("pipeline.preprocessing.repository_metrics.input.reverify_inputs", side_effect=reverify), \
             patch("pipeline.preprocessing.repository_metrics.transform.transform", side_effect=transform or self._transform):
            return run(self.s3, **kwargs)

    def test_same_input_reverifies_without_rewriting_outputs(self):
        self.assertEqual(self._run()["status"], "PASSED")
        directory = self.root / "runs/run-one"
        before = sha_file(directory / "run_manifest.json")
        result = self._run(transform=lambda *args: self.fail("must not recompute completed run"))
        self.assertEqual(result["status"], "REVERIFIED")
        self.assertEqual(before, sha_file(directory / "run_manifest.json"))

    def test_input_change_cannot_reuse_run_id(self):
        self._run()
        self.prepared["different_input"] = True
        with self.assertRaisesRegex(ValueError, "different input"):
            self._run()
        verify_completed(self.root / "runs/run-one")

    def test_transform_failure_never_publishes_marker(self):
        def fail(*args):
            raise RuntimeError("injected transform failure")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self._run(transform=fail)
        directory = self.root / "runs/run-one"
        self.assertFalse((directory / "_SUCCESS").exists())
        self.assertFalse((directory / ".writer.lock").exists())
        self.assertEqual(self._run()["status"], "PASSED")

    def test_source_mutation_before_commit_blocks_marker(self):
        with self.assertRaisesRegex(ValueError, "changed"):
            self._run(reverify=ValueError("source changed"))
        self.assertFalse((self.root / "runs/run-one/_SUCCESS").exists())

    def test_missing_marker_recovers_only_after_output_verification(self):
        from pipeline.preprocessing.repository_metrics import build
        original = build.write_json
        def fail_marker(path, value):
            if Path(path).name == "_SUCCESS":
                raise OSError("injected marker failure")
            return original(path, value)
        with patch.object(build, "write_json", side_effect=fail_marker):
            with self.assertRaisesRegex(OSError, "marker failure"):
                self._run()
        directory = self.root / "runs/run-one"
        self.assertTrue((directory / "run_manifest.json").exists())
        self.assertFalse((directory / "_SUCCESS").exists())
        result = self._run(transform=lambda *args: self.fail("must not recompute prepared output"))
        self.assertEqual(result["status"], "REVERIFIED")
        verify_completed(directory)

    def test_missing_marker_cannot_approve_tampered_output(self):
        from pipeline.preprocessing.repository_metrics import build
        original = build.write_json
        def fail_marker(path, value):
            if Path(path).name == "_SUCCESS":
                raise OSError("injected marker failure")
            return original(path, value)
        with patch.object(build, "write_json", side_effect=fail_marker):
            with self.assertRaisesRegex(OSError, "marker failure"):
                self._run()
        directory = self.root / "runs/run-one"
        next(directory.rglob("*.parquet")).write_bytes(b"tampered parquet")
        with self.assertRaises(duckdb.Error):
            self._run(transform=lambda *args: self.fail("must not recompute corrupted output"))
        self.assertFalse((directory / "_SUCCESS").exists())

    def test_output_tampering_blocks_reverification(self):
        self._run()
        path = next((self.root / "runs/run-one").rglob("*.parquet"))
        path.write_bytes(b"invalid parquet")
        with self.assertRaises(Exception):
            self._run()

    def test_remote_failure_has_no_success_and_retry_verifies(self):
        self._run()
        directory = self.root / "runs/run-one"
        self.s3.fail_output = True
        with self.assertRaisesRegex(RuntimeError, "upload failure"):
            publish_run(self.s3, directory)
        self.assertFalse(any(key.endswith("/_SUCCESS") for _, key in self.s3.objects))
        self.s3.fail_output = False
        receipt = publish_run(self.s3, directory)
        self.assertEqual(receipt["status"], "PUBLISHED")
        self.assertEqual(self.s3.writes[-1], receipt["prefix"] + "/_SUCCESS")
        self.assertEqual(publish_run(self.s3, directory)["action"], "REVERIFIED")
        self.assertTrue(all(key.startswith("depsdev/v1/repository-metrics/") for key in self.s3.writes))

    def test_remote_tampering_does_not_repair_completed_run(self):
        self._run()
        directory = self.root / "runs/run-one"
        publish_run(self.s3, directory)
        key = next(k for k in self.s3.objects if k[1].endswith(".parquet"))
        self.s3.objects[key] = b"changed"
        with self.assertRaisesRegex(ValueError, "verification failed"):
            publish_run(self.s3, directory)
        self.assertEqual(self.s3.objects[key], b"changed")

    def test_work_directory_cannot_overlap_source(self):
        with self.assertRaisesRegex(ValueError, "overlaps input"):
            self._run(work_dir=self.root / "source/curated/outputs")

    def test_atomic_json_failure_never_exposes_partial_target(self):
        from pipeline.preprocessing.repository_metrics import build
        for operation in ("fsync", "link"):
            with self.subTest(operation=operation):
                target = self.root / (operation + ".json")
                with patch.object(build.os, operation, side_effect=OSError("injected disk error")):
                    with self.assertRaisesRegex(OSError, "disk error"):
                        build.write_json(target, {"complete": True})
                self.assertFalse(target.exists())
                self.assertFalse(list(self.root.glob("*.pending")))

    def test_atomic_json_cannot_replace_an_existing_target(self):
        from pipeline.preprocessing.repository_metrics import build
        target = self.root / "immutable.json"
        build.write_json(target, {"original": True})
        before = target.read_bytes()
        with self.assertRaises(FileExistsError):
            build.write_json(target, {"replacement": True})
        self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
