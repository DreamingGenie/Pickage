import hashlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pipeline.preprocessing.experiments.real_snapshot_db_resume import DatabaseResume


class DatabaseResumeTests(unittest.TestCase):
    def test_completed_bundle_is_reused_but_changed_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            job = DatabaseResume.__new__(DatabaseResume)
            job.jar = Path(folder) / 'loader.jar'
            job.jar.write_bytes(b'fixture')
            job.jar_sha256 = hashlib.sha256(b'fixture').hexdigest()
            request = {'snapshot': '2026-08-31', 'run_id': 'test'}
            body = json.dumps({'request': request, 'status': 'COMPLETE'}).encode()
            job.baseline_sha256 = hashlib.sha256(body).hexdigest()
            job.local = Mock()
            helper = types.SimpleNamespace(FROZEN_JAR=None)
            for marker, valid in [({'manifest_sha256': job.baseline_sha256}, True), ({}, False)]:
                job.local.get_object.side_effect = [
                    {'Body': io.BytesIO(body)}, {'Body': io.BytesIO(json.dumps(marker).encode())}]
                with patch.dict('sys.modules', {'db_setup': helper}):
                    if valid:
                        self.assertEqual(job.preprocess('baseline', request)['status'], 'COMPLETE')
                        self.assertEqual(helper.FROZEN_JAR, job.jar)
                    else:
                        with self.assertRaisesRegex(ValueError, 'identity changed'):
                            job.preprocess('baseline', request)
            job.jar.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'jar changed'):
                job.check_jar()

    def test_baseline_copy_does_not_repeat_preprocessing(self):
        job = DatabaseResume.__new__(DatabaseResume)
        with patch('pipeline.preprocessing.experiments.real_snapshot_run.Experiment.copy',
                   side_effect=AssertionError('baseline copied again')):
            job.copy('baseline', [])


if __name__ == '__main__':
    unittest.main()
