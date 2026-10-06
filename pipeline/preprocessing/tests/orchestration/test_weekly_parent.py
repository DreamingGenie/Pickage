import hashlib
import json
import unittest
from unittest.mock import patch
from botocore.exceptions import ClientError

from pipeline.preprocessing.orchestration import weekly_parent
from pipeline.preprocessing.orchestration.contracts import STAGES


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        value = self.objects.get((Bucket, Key))
        if value is None:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        return {"Body": _Body(value), "ETag": '"' + hashlib.md5(value).hexdigest() + '"'}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, IfMatch=None):
        old = self.objects.get((Bucket, Key))
        if IfNoneMatch == "*" and old is not None:
            raise ValueError("precondition")
        if IfMatch is not None and (old is None or hashlib.md5(old).hexdigest() != IfMatch.strip('"')):
            raise ValueError("precondition")
        self.objects[(Bucket, Key)] = Body


class _Body:
    def __init__(self, value):
        self.value, self.offset = value, 0

    def read(self, size=-1):
        if size < 0:
            size = len(self.value) - self.offset
        result = self.value[self.offset:self.offset + size]
        self.offset += len(result)
        return result

    def close(self):
        pass


def _put(s3, key, value):
    body = json.dumps(value, separators=(",", ":")).encode()
    s3.put_object(Bucket=weekly_parent.BUCKET, Key=key, Body=body)
    return body


class WeeklyParentTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.snapshot = "2026-08-31"
        self.run_id = "parent-1"
        self.prefix = f"depsdev/v1/curated-bundle/snapshot={self.snapshot}/run_id={self.run_id}"
        self.stage = {}
        for name in STAGES:
            stage_prefix = f"depsdev/v1/{name}/snapshot={self.snapshot}/run_id={self.run_id}"
            manifest_key = stage_prefix + "/run_manifest.json"
            manifest_body = _put(self.s3, manifest_key, {"status": "PASSED", "stage": name})
            marker_key = stage_prefix + "/_SUCCESS"
            marker_body = _put(self.s3, marker_key, {"manifest_sha256": hashlib.sha256(manifest_body).hexdigest()})
            self.stage[name] = {"stage": name, "run_id": self.run_id, "snapshot": self.snapshot,
                                "prefix": stage_prefix, "manifest_key": manifest_key,
                                "manifest_sha256": hashlib.sha256(manifest_body).hexdigest(),
                                "marker_key": marker_key, "marker_sha256": hashlib.sha256(marker_body).hexdigest(),
                                "files": [{"bucket": weekly_parent.BUCKET, "key": manifest_key,
                                           "sha256": hashlib.sha256(manifest_body).hexdigest(),
                                           "bytes": len(manifest_body)}]}
        self.request = {"format_version": 1, "snapshot": self.snapshot, "run_id": self.run_id,
                        "calendar_refs": [{"snapshot": self.snapshot}]}
        self.bundle = {"format_version": 2, "status": "COMPLETE", "request": self.request,
                       "stages": self.stage}
        self.bundle_body = json.dumps(self.bundle, separators=(",", ":")).encode()
        _put_bytes(self.s3, self.prefix + "/run_manifest.json", self.bundle_body)
        marker = json.dumps({"manifest_sha256": hashlib.sha256(self.bundle_body).hexdigest()}, separators=(",", ":")).encode()
        _put_bytes(self.s3, self.prefix + "/_SUCCESS", marker)
        self.pointer = {"run_prefix": self.prefix,
                        "manifest_sha256": hashlib.sha256(self.bundle_body).hexdigest(),
                        "snapshot": self.snapshot}

    def test_marker_written_before_pointer_is_repaired_by_replay(self):
        # Simulate a process crash after immutable bundle marker publication.
        weekly_parent.publish_current(self.s3, self.request, self.bundle_body)
        self.assertEqual(json.loads(self.s3.objects[(weekly_parent.BUCKET, weekly_parent.CURRENT)]), self.pointer)
        weekly_parent.publish_current(self.s3, self.request, self.bundle_body, replay=True)
        self.assertEqual(json.loads(self.s3.objects[(weekly_parent.BUCKET, weekly_parent.CURRENT)]), self.pointer)

    def test_parent_manifest_or_marker_mutation_is_rejected(self):
        self.s3.objects[(weekly_parent.BUCKET, self.prefix + "/run_manifest.json")] = b"changed"
        with self.assertRaises(ValueError):
            weekly_parent.read_bundle(self.s3, self.pointer)
        _put_bytes(self.s3, self.prefix + "/run_manifest.json", self.bundle_body)
        # read_bundle checks the immutable parent pointer digest and marker.
        self.s3.objects[(weekly_parent.BUCKET, self.prefix + "/_SUCCESS")] = b"{}"
        with self.assertRaises(ValueError):
            weekly_parent.read_bundle(self.s3, self.pointer)

    def test_package_parent_from_another_bundle_is_rejected(self):
        _put_bytes(self.s3, weekly_parent.CURRENT, json.dumps(self.pointer, separators=(",", ":")).encode())
        request = dict(self.request, format_version=2, parent_bundle=self.pointer,
                       parent={"run_prefix": "depsdev/v1/package-version/snapshot=2026-08-31/run_id=other",
                               "manifest_sha256": "0" * 64, "snapshot": self.snapshot})
        with patch.object(weekly_parent, "verify_descriptor"):
            with self.assertRaisesRegex(ValueError, "outside completed parent bundle"):
                weekly_parent.validate_parent(self.s3, request)

    def test_calendar_history_change_is_rejected(self):
        request = dict(self.request, format_version=2, parent_bundle=self.pointer,
                       parent={"run_prefix": self.stage["package_version"]["prefix"],
                               "manifest_sha256": self.stage["package_version"]["manifest_sha256"],
                               "snapshot": self.snapshot},
                       calendar_refs=[{"snapshot": "2026-08-30"}, {"snapshot": self.snapshot}])
        self.s3.objects[(weekly_parent.BUCKET, weekly_parent.CURRENT)] = json.dumps(self.pointer).encode()
        with patch.object(weekly_parent, "verify_descriptor"):
            with self.assertRaisesRegex(ValueError, "calendar"):
                weekly_parent.validate_parent(self.s3, request)


def _put_bytes(s3, key, body):
    s3.put_object(Bucket=weekly_parent.BUCKET, Key=key, Body=body)


if __name__ == "__main__":
    unittest.main()
