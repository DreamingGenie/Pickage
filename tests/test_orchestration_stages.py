"""Native manifest byte/marker normalization, without substituting builders."""
import unittest

from pipeline.curated.storage import json_bytes
from pipeline.downloads.test_bronze import FakeS3
from pipeline.orchestration.stages import describe, prefix_for
from pipeline.orchestration.storage import BUCKET, sha
from tests.test_orchestration_runner import request_fixture


class DescriptorTests(unittest.TestCase):
    def test_preserves_exact_manifest_bytes_and_native_data_prefix(self):
        s3, request = FakeS3(), request_fixture()
        prefix = prefix_for("package_snapshot", request)
        body = json_bytes({"status": "PASSED", "files": [{"path": "package_snapshot.parquet",
                          "bytes": 3, "sha256": "a" * 64}], "quality": {"status": "PASSED"}}) + b"\n"
        s3.put_object(Bucket=BUCKET, Key=prefix + "/run_manifest.json", Body=body)
        s3.put_object(Bucket=BUCKET, Key=prefix + "/_SUCCESS", Body=(sha(body) + "\n").encode())
        descriptor = describe("package_snapshot", request, s3)
        self.assertEqual(descriptor["manifest_sha256"], sha(body))
        self.assertEqual(descriptor["files"][0]["key"], prefix + "/data/package_snapshot.parquet")

    def test_wrong_marker_not_promoted(self):
        s3, request = FakeS3(), request_fixture()
        prefix = prefix_for("downloads", request)
        s3.put_object(Bucket=BUCKET, Key=prefix + "/run_manifest.json", Body=b'{"status":"PASSED","files":[]}')
        s3.put_object(Bucket=BUCKET, Key=prefix + "/_SUCCESS", Body=b"incorrect")
        with self.assertRaisesRegex(ValueError, "not approved"):
            describe("downloads", request, s3)


if __name__ == "__main__":
    unittest.main()
