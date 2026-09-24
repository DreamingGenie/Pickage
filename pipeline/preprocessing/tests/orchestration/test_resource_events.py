"""Bounded resource events preserve stage state and terminate on failure."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from pipeline.preprocessing.runtime.resource_events import resource_events


class ResourceEventsTest(unittest.TestCase):
    def test_failure_keeps_original_error_and_emits_final_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'work' / 'fixture' / 'status.json'
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({'status': 'RUNNING', 'phase': 'dependents'}))
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaisesRegex(ValueError, 'fixture failure'):
                with resource_events(root, root / 'work', 'fixture', 28000000000):
                    state.write_text(json.dumps({'status': 'FAILED', 'phase': 'dependents'}))
                    raise ValueError('fixture failure')
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(len(events), 2)
            self.assertEqual([event['status'] for event in events], ['RUNNING', 'FAILED'])
            for event in events:
                self.assertEqual(event['event'], 'PIPELINE_RESOURCES')
                self.assertEqual(event['run_id'], 'fixture')
                self.assertEqual(event['phase'], 'dependents')
                self.assertEqual(event['scratch_limit_bytes'], 28000000000)
                self.assertGreaterEqual(event['scratch_peak_bytes'], event['scratch_used_bytes'])
