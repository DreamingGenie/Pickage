"""manifest_hash.py 의 순수 로직 테스트. 네트워크를 쓰지 않는다.

    python -m pytest pipeline/minio/test_manifest_hash.py -v
"""
import hashlib
import unittest
from unittest.mock import patch

from .manifest_hash import main


class FakeBody:
    """boto3 StreamingBody 흉내. read(n) 이 한 번 다 준 뒤로는 빈 바이트를 돌려준다."""

    def __init__(self, payload):
        self.payload = payload
        self._sent = False

    def read(self, amount=None):
        if self._sent:
            return b""
        self._sent = True
        return self.payload


class FakeS3:
    def __init__(self, payload):
        self.payload = payload
        self.gets = []

    def get_object(self, Bucket, Key):
        self.gets.append((Bucket, Key))
        return {"Body": FakeBody(self.payload)}


class ManifestHashTests(unittest.TestCase):
    def test_prints_sha256_of_object_bytes(self):
        payload = b'{"model_ver": "3", "candidate_rows": 100}\n'
        fake = FakeS3(payload)
        with patch("pipeline.minio.manifest_hash.client", return_value=fake), \
             patch("builtins.print") as mock_print:
            main(["--bucket", "pickage-vectors",
                  "--key", "model=v3/corpus=x/run_manifest.json"])
        mock_print.assert_called_once_with(hashlib.sha256(payload).hexdigest())

    def test_requests_the_given_bucket_and_key(self):
        fake = FakeS3(b"{}")
        with patch("pipeline.minio.manifest_hash.client", return_value=fake), \
             patch("builtins.print"):
            main(["--bucket", "pickage-vectors",
                  "--key", "model=v3/corpus=x/run_manifest.json"])
        self.assertEqual(fake.gets,
                         [("pickage-vectors", "model=v3/corpus=x/run_manifest.json")])


if __name__ == "__main__":
    unittest.main()
