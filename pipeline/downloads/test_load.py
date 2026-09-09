import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .load import run
from .test_bronze import FakeS3
from .test_support import make_source


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.work = self.base / 'work'
        make_source(self.source)

    def test_verify_only_never_connects_and_input_manifest_is_deterministic(self):
        with patch('pipeline.downloads.load.client', side_effect=AssertionError('unexpected S3 connection')):
            first = run(self.source, 'source-1', 'verify-1', self.work, verify_only=True)
            second = run(self.source, 'source-1', 'verify-1', self.work, verify_only=True)
        self.assertEqual(first['status'], 'VERIFIED')
        self.assertEqual(first['manifest_sha256'], second['manifest_sha256'])
        self.assertNotEqual(first['attempt_id'], second['attempt_id'])
        manifest = json.loads(Path(first['manifest_path']).read_bytes())
        raw = [f for f in manifest['files'] if f['role'] == 'raw_response']
        self.assertEqual(raw[0]['row_count'], 3)
        self.assertNotIn('statistics_note', raw[0])
        self.assertEqual(manifest['quality']['downloads_null'], 1)
        self.assertEqual(manifest['quality']['downloads_zero'], 3)

    def test_publish_then_reverify_preserves_objects_and_records_real_status(self):
        s3 = FakeS3()
        first = run(self.source, 'source-1', 'load-1', self.work, s3=s3)
        before = dict(s3.objects)
        second = run(self.source, 'source-1', 'load-1', self.work, s3=s3)
        self.assertEqual(first['status'], 'PUBLISHED')
        self.assertEqual(second['status'], 'REVERIFIED')
        self.assertEqual(before, s3.objects)
        stored = json.loads(Path(second['report_path']).read_text(encoding='utf-8'))
        self.assertEqual(stored['status'], 'REVERIFIED')

    def test_validation_failure_records_attempt_and_does_not_connect(self):
        source_manifest = self.source / 'raw/run=source-1/manifest.json'
        value = json.loads(source_manifest.read_bytes())
        source_manifest.write_text(json.dumps({**value, 'final': False}), encoding='utf-8')
        with patch('pipeline.downloads.load.client', side_effect=AssertionError('unexpected S3 connection')):
            with self.assertRaises(ValueError):
                run(self.source, 'source-1', 'bad-1', self.work)
        report = json.loads(next(self.work.rglob('execution_report.json')).read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['phase'], 'VALIDATE_INPUT')

    def test_upload_failure_is_not_published_and_can_resume(self):
        s3 = FakeS3()
        with self.assertRaisesRegex(RuntimeError, 'before_success'):
            run(self.source, 'source-1', 'resume-1', self.work, s3=s3, failpoint='before_success')
        self.assertFalse(any(key.endswith('/_SUCCESS') for _, key in s3.objects))
        result = run(self.source, 'source-1', 'resume-1', self.work, s3=s3)
        self.assertEqual(result['status'], 'PUBLISHED')

    def test_rejects_execution_artifacts_inside_source_and_invalid_run_id(self):
        for work, run_id in ((self.source / 'reports', 'ok'), (self.work, '../escape')):
            with self.subTest(work=work, run_id=run_id), self.assertRaises(ValueError):
                run(self.source, 'source-1', run_id, work, verify_only=True)
        self.assertFalse((self.source / 'reports').exists())


if __name__ == '__main__':
    unittest.main()
