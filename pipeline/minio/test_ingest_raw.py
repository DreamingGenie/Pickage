import hashlib
import io
import unittest
from ingest_raw import digest, put_once


class FakeS3:
    def head_object(self, **kwargs):
        return {}

    def get_object(self, **kwargs):
        return {'Body': io.BytesIO(b'original')}

    def put_object(self, **kwargs):
        raise AssertionError('Existing objects must not be overwritten')


class IngestTests(unittest.TestCase):
    def test_stream_hash(self):
        value = b'parquet-test' * 200000
        self.assertEqual(digest(io.BytesIO(value)), hashlib.sha256(value).hexdigest())

    def test_resume_identical_manifest(self):
        put_once(FakeS3(), 'bucket', 'key', b'original')

    def test_resume_changed_manifest_rejected(self):
        with self.assertRaises(ValueError):
            put_once(FakeS3(), 'bucket', 'key', b'changed')


if __name__ == '__main__':
    unittest.main()
