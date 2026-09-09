import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from botocore.exceptions import ClientError

from pipeline.downloads.bronze import publish


class Body:
    def __init__(self, value):
        self.value, self.offset = value, 0

    def read(self, size=-1):
        if size < 0:
            size = len(self.value) - self.offset
        out = self.value[self.offset:self.offset + size]
        self.offset += len(out)
        return out

    def close(self):
        pass


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.race_keys = set()
        self.race_values = {}
        self.fail_keys = set()

    def _missing(self):
        return ClientError({"Error": {"Code": "404"}}, "GetObject")

    def get_object(self, Bucket, Key):
        value = self.objects.get((Bucket, Key))
        if value is None:
            raise self._missing()
        return {"Body": Body(value)}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None):
        value = Body if isinstance(Body, bytes) else Body.read()
        if (Bucket, Key) in self.fail_keys:
            raise RuntimeError("upload failed")
        if (Bucket, Key) in self.race_keys:
            self.race_keys.remove((Bucket, Key))
            self.objects[(Bucket, Key)] = self.race_values.get((Bucket, Key), value)
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        if IfNoneMatch == "*" and (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[(Bucket, Key)] = value


def _manifest(root, run_id="run-1"):
    path = root / "daily" / "part.csv"
    path.parent.mkdir()
    path.write_bytes(b"a,b\n1,2\n")
    body = path.read_bytes()
    return {"contract_version": 1, "run_id": run_id, "quality": {"status": "PASSED"},
            "files": [{"path": "daily/part.csv", "role": "download", "bytes": len(body),
                       "sha256": hashlib.sha256(body).hexdigest()}]}


class BronzeTests(unittest.TestCase):
    def test_publish_and_reverify(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            first = publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            second = publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            self.assertEqual(first["status"], "PUBLISHED")
            self.assertEqual(second["status"], "REVERIFIED")
            self.assertIn(("raw", "downloads/run-1/_INPUT.json"), s3.objects)

    def test_changed_input_and_completed_missing_object_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            changed = dict(manifest, quality={"status": "CHANGED"})
            with self.assertRaisesRegex(ValueError, "different input"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=changed)
            s3.objects.pop(("raw", "downloads/run-1/data/daily/part.csv"))
            with self.assertRaisesRegex(ValueError, "missing"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)

    def test_failpoint_resumes_and_does_not_overwrite_completed_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            with self.assertRaisesRegex(RuntimeError, "after_files"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest,
                        failpoint="after_files")
            self.assertNotIn(("raw", "downloads/run-1/_SUCCESS"), s3.objects)
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            before = dict(s3.objects)
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            self.assertEqual(before, s3.objects)

    def test_before_success_failure_leaves_manifest_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            with self.assertRaisesRegex(RuntimeError, "before_success"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root,
                        manifest=manifest, failpoint="before_success")
            self.assertIn(("raw", "downloads/run-1/run_manifest.json"), s3.objects)
            self.assertNotIn(("raw", "downloads/run-1/_SUCCESS"), s3.objects)
            result = publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            self.assertEqual(result["status"], "PUBLISHED")

    def test_before_commit_is_required_before_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            checks = []
            def check():
                checks.append(True)
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root,
                    manifest=manifest, before_commit=check)
            self.assertEqual(checks, [True])
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root,
                    manifest=manifest, before_commit=check)
            self.assertEqual(checks, [True, True])

    def test_completed_run_requires_input_and_unchanged_local_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            s3.objects.pop(("raw", "downloads/run-1/_INPUT.json"))
            with self.assertRaisesRegex(ValueError, "missing _INPUT"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            publish(s3, bucket="raw", prefix="downloads/run-2", root=root, manifest=manifest)
            (root / "daily" / "part.csv").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source changed"):
                publish(s3, bucket="raw", prefix="downloads/run-2", root=root, manifest=manifest)

    def test_source_change_and_conditional_race(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            s3.race_keys.add(("raw", "downloads/run-1/_INPUT.json"))
            publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            s3.race_keys.add(("raw", "downloads/run-2/data/daily/part.csv"))
            publish(s3, bucket="raw", prefix="downloads/run-2", root=root, manifest=manifest)
            path = root / "daily" / "part.csv"
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source changed"):
                publish(s3, bucket="raw", prefix="downloads/run-2", root=root, manifest=manifest)

    def test_conditional_race_with_different_object_and_upload_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root, s3 = Path(directory), FakeS3()
            manifest = _manifest(root)
            key = ("raw", "downloads/run-1/data/daily/part.csv")
            s3.race_keys.add(key)
            s3.race_values[key] = b"wrong"  # another publisher won with different bytes
            with self.assertRaisesRegex(ValueError, "verification failed"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)

            s3 = FakeS3()
            s3.fail_keys.add(key)
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                publish(s3, bucket="raw", prefix="downloads/run-1", root=root, manifest=manifest)
            self.assertNotIn(("raw", "downloads/run-1/_SUCCESS"), s3.objects)


if __name__ == "__main__":
    unittest.main()
