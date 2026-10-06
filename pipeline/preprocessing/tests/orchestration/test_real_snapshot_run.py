import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from pipeline.preprocessing.experiments.real_snapshot_run import Experiment, atomic


class RealSnapshotRunTests(unittest.TestCase):
    def test_status_write_retries_transient_windows_sharing_failure(self):
        import os
        replace = os.replace
        calls = []
        def flaky(source, target):
            calls.append(source)
            if len(calls) < 3:
                raise PermissionError('reader holds file')
            return replace(source, target)
        with tempfile.TemporaryDirectory() as directory, patch(
                'pipeline.preprocessing.experiments.real_snapshot_run.os.replace', side_effect=flaky), patch(
                'pipeline.preprocessing.experiments.real_snapshot_run.time.sleep'):
            path = Path(directory) / 'status.json'
            atomic(path, {'status': 'RUNNING'})
            self.assertEqual(json.loads(path.read_text()), {'status': 'RUNNING'})
            self.assertEqual(len(calls), 3)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def make(self, root):
        credentials = root / 'source.env'
        credentials.write_text('MINIO_ROOT_USER=test\nMINIO_ROOT_PASSWORD=test\n')
        (root / 'config.json').write_text(json.dumps({'source': 'http://127.0.0.1:19000',
            'destination': 'http://127.0.0.1:19030', 'source_env': str(credentials)}))
        with patch('pipeline.preprocessing.experiments.real_snapshot_run.client', side_effect=[MagicMock(), MagicMock()]):
            return Experiment(root)

    def test_rejects_changed_source_before_any_destination_write(self):
        with tempfile.TemporaryDirectory() as directory:
            experiment = self.make(Path(directory))
            experiment.source.head_object.return_value = {'ETag': 'new', 'ContentLength': 3}
            with self.assertRaisesRegex(ValueError, 'source object changed'):
                experiment.copy('baseline', [{'key': 'a', 'etag': 'old', 'bytes': 3}])
            experiment.local.upload_file.assert_not_called()
            experiment.local.put_object.assert_not_called()

    def test_preprocess_failure_stops_before_db_and_weekly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = self.make(root)
            experiment.inventory = lambda: {'baseline': [], 'weekly': []}
            experiment.copy = MagicMock()
            experiment.request = lambda label: {}
            experiment.preprocess = MagicMock(side_effect=ValueError('invalid approved input'))
            db = types.SimpleNamespace(load=MagicMock(), configure=MagicMock())
            with patch.dict('sys.modules', {'db_setup': db}), self.assertRaisesRegex(ValueError, 'invalid approved input'):
                experiment.run()
            db.load.assert_not_called()
            experiment.copy.assert_called_once_with('baseline', [])
            state = json.loads((root / 'status.json').read_text())
            self.assertEqual(state['status'], 'FAILED')
            self.assertEqual(state['error'], 'invalid approved input')

    def test_baseline_and_weekly_are_loaded_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = self.make(root)
            experiment.inventory = lambda: {'baseline': [], 'weekly': []}
            experiment.copy = MagicMock()
            experiment.request = lambda label: {'snapshot': label, 'run_id': label}
            experiment.preprocess = MagicMock()
            experiment.local.get_object.side_effect = lambda **kw: {'Body': io.BytesIO(b'{}')}
            db = types.SimpleNamespace(load=MagicMock(return_value={'status': 'PUBLISHED'}), configure=MagicMock())
            with patch.dict('sys.modules', {'db_setup': db}):
                experiment.run()
            self.assertEqual([c.args[3] for c in db.load.call_args_list], ['baseline', 'weekly'])
            self.assertEqual(json.loads((root / 'status.json').read_text())['status'], 'COMPLETE')


if __name__ == '__main__':
    unittest.main()
