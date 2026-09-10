"""Opt-in tests against local MinIO; only unique test prefixes are written."""
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from pipeline.minio.ingest_raw import client
from .load import run
from .test_support import make_source


@unittest.skipUnless(os.getenv('DOWNLOADS_MINIO_TEST') == '1', 'set DOWNLOADS_MINIO_TEST=1 for local MinIO')
class MinioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        make_source(self.source)
        self.s3 = client()
        self.run_id = 'test-278-' + uuid.uuid4().hex
        self.prefix = f'npm-downloads/v1/run_id={self.run_id}/'
        self.addCleanup(self.cleanup_objects)

    def cleanup_objects(self):
        keys = [item['Key'] for page in self.s3.get_paginator('list_objects_v2').paginate(
            Bucket='pickage-raw', Prefix=self.prefix) for item in page.get('Contents', [])]
        assert self.prefix.startswith('npm-downloads/v1/run_id=test-278-')
        assert all(key.startswith(self.prefix) for key in keys)
        for key in keys:
            self.s3.delete_object(Bucket='pickage-raw', Key=key)
        self.assertEqual(self.s3.list_objects_v2(Bucket='pickage-raw', Prefix=self.prefix).get('KeyCount', 0), 0)

    def execute(self, **kwargs):
        return run(self.source, 'source-1', self.run_id, self.base / 'work', s3=self.s3, **kwargs)

    def test_real_publish_reverify_and_completed_missing_file_no_repair(self):
        first = self.execute()
        before = {item['Key']: (item['ETag'], item['LastModified']) for item in
                  self.s3.list_objects_v2(Bucket='pickage-raw', Prefix=self.prefix)['Contents']}
        second = self.execute()
        after = {item['Key']: (item['ETag'], item['LastModified']) for item in
                 self.s3.list_objects_v2(Bucket='pickage-raw', Prefix=self.prefix)['Contents']}
        self.assertEqual(first['status'], 'PUBLISHED')
        self.assertEqual(second['status'], 'REVERIFIED')
        self.assertEqual(before, after)
        missing_key = self.prefix + 'data/targets_top100k_20260902.csv'
        self.s3.delete_object(Bucket='pickage-raw', Key=missing_key)
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.execute()
        self.assertEqual(self.s3.list_objects_v2(Bucket='pickage-raw', Prefix=missing_key).get('KeyCount', 0), 0)

    def test_real_failure_resume_and_changed_manifest_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'before_success'):
            self.execute(failpoint='before_success')
        self.assertEqual(self.s3.list_objects_v2(Bucket='pickage-raw', Prefix=self.prefix + '_SUCCESS').get('KeyCount', 0), 0)
        self.assertEqual(self.execute()['status'], 'PUBLISHED')
        target = self.source / 'targets_top100k_20260902.csv'
        target.write_text(target.read_text(encoding='utf-8').replace('alpha,1000', 'alpha,1001'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'different input'):
            self.execute()


if __name__ == '__main__':
    unittest.main()
