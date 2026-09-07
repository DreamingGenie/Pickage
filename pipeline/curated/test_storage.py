import hashlib
import tempfile
from pathlib import Path
import unittest

from botocore.exceptions import ClientError

from storage import (compare_and_swap_json, download_files, json_bytes,
                     put_immutable, upload_outputs, verify_files, writer_lock)


class _Body:
    def __init__(self, value):
        self.value = value
        self.offset = 0

    def read(self, size=-1):
        if size < 0:
            size = len(self.value)
        result = self.value[self.offset:self.offset + size]
        self.offset += len(result)
        return result

    def close(self):
        pass


class FakeS3:
    def __init__(self):
        self.objects = {}

    @staticmethod
    def _missing():
        return ClientError({"Error": {"Code": "404"}}, "GetObject")

    def get_object(self, Bucket, Key):
        value = self.objects.get((Bucket, Key))
        if value is None:
            raise self._missing()
        body, etag = value
        return {"Body": _Body(body), "ETag": '"' + etag + '"'}

    def head_object(self, Bucket, Key):
        value = self.objects.get((Bucket, Key))
        if value is None:
            raise self._missing()
        body, etag = value
        return {"ContentLength": len(body), "ETag": '"' + etag + '"'}

    def list_objects_v2(self, Bucket, Prefix):
        return {'Contents': [{'Key': key} for bucket, key in sorted(self.objects)
                             if bucket == Bucket and key.startswith(Prefix)], 'IsTruncated': False}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, IfMatch=None):
        old = self.objects.get((Bucket, Key))
        if IfNoneMatch == "*" and old is not None:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        if IfMatch is not None and (old is None or old[1] != IfMatch.strip('"')):
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        digest = hashlib.md5(Body).hexdigest()
        self.objects[(Bucket, Key)] = (Body, digest)
        return {"ETag": '"' + digest + '"'}

    def delete_object(self, Bucket, Key, IfMatch=None):
        old = self.objects.get((Bucket, Key))
        if old is None or (IfMatch is not None and old[1] != IfMatch.strip('"')):
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "DeleteObject")
        del self.objects[(Bucket, Key)]


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.bucket = "curated"

    def test_json_is_canonical_and_immutable(self):
        self.assertEqual(json_bytes({"b": 1, "a": "한글"}),
                         '{"a":"한글","b":1}'.encode("utf-8"))
        put_immutable(self.s3, self.bucket, "manifest.json", b"abc")
        put_immutable(self.s3, self.bucket, "manifest.json", b"abc")
        with self.assertRaises(ValueError):
            put_immutable(self.s3, self.bucket, "manifest.json", b"changed")

    def test_download_cache_detects_corrupt_file_and_verifies_remote(self):
        body = b"parquet bytes"
        record = {"key": "data/a.parquet", "bytes": len(body),
                  "sha256": hashlib.sha256(body).hexdigest()}
        self.s3.put_object(Bucket=self.bucket, Key=record["key"], Body=body)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / (record["sha256"] + ".parquet")
            target.write_bytes(b"corrupt")
            paths = download_files(self.s3, self.bucket, [record], root)
            self.assertEqual(paths, [target])
            self.assertEqual(target.read_bytes(), body)
            verify_files(self.s3, self.bucket, [record])

    def test_upload_outputs_is_recursive_and_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "nested").mkdir()
            (directory / "nested" / "x.parquet").write_bytes(b"x")
            records = upload_outputs(self.s3, self.bucket, "run-1", directory)
            self.assertEqual(records[0]["key"], "run-1/nested/x.parquet")
            self.assertEqual(records[0]["bytes"], 1)
            (directory / "nested" / "x.parquet").write_bytes(b"y")
            with self.assertRaises(ValueError):
                upload_outputs(self.s3, self.bucket, "run-1", directory)

    def test_writer_lock_releases_only_owned_lock(self):
        with writer_lock(self.s3, self.bucket, "writer.lock", "job-1"):
            self.assertIn((self.bucket, "writer.lock"), self.s3.objects)
            with self.assertRaises(ValueError):
                with writer_lock(self.s3, self.bucket, "writer.lock", "job-2"):
                    pass
        self.assertNotIn((self.bucket, "writer.lock"), self.s3.objects)

    def test_writer_lock_fails_closed_if_replaced(self):
        with self.assertRaises(RuntimeError):
            with writer_lock(self.s3, self.bucket, "writer.lock", "job-1"):
                self.s3.objects[(self.bucket, "writer.lock")] = (b"other", "etag")

    def test_compare_and_swap_requires_expected_etag(self):
        self.assertIsNotNone(compare_and_swap_json(self.s3, self.bucket, "state", {"n": 1}))
        current = self.s3.head_object(Bucket=self.bucket, Key="state")["ETag"]
        compare_and_swap_json(self.s3, self.bucket, "state", {"n": 2}, current)
        with self.assertRaises(ClientError):
            compare_and_swap_json(self.s3, self.bucket, "state", {"n": 3}, current)


if __name__ == "__main__":
    unittest.main()
