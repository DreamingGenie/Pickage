import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.spark_experiment.runtime.repository_profile import Recorder, summarize_actions


class Context:
    def __init__(self):
        self.properties = {'spark.jobGroup.id': 'outer', 'spark.job.description': 'original',
                           'spark.job.interruptOnCancel': 'true'}

    def getLocalProperty(self, key):
        return self.properties.get(key)

    def setLocalProperty(self, key, value):
        self.properties[key] = value

    def setJobGroup(self, group, description):
        self.properties.update({'spark.jobGroup.id': group, 'spark.job.description': description,
                                'spark.job.interruptOnCancel': 'false'})


class ProfileTests(unittest.TestCase):
    def test_action_preserves_result_single_call_and_group(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = Recorder(Path(root) / 'actions.jsonl')
            context = Context()
            old = dict(context.properties)
            obj = SimpleNamespace(sparkSession=SimpleNamespace(sparkContext=context))
            calls = []
            def count(frame):
                calls.append(context.getLocalProperty('spark.jobGroup.id'))
                return 123
            site = [{'function': '_read', 'dataset': 'package', 'line': 30}]
            with recorder.path.open('x') as recorder.stream, patch(
                    'pipeline.spark_experiment.runtime.repository_profile.repository_callsite', return_value=site):
                self.assertEqual(recorder.wrap_action(count, 'count')(obj), 123)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].startswith('repository-profile:'))
            self.assertEqual(context.properties, old)
            summary = summarize_actions(recorder.path)
            self.assertEqual(summary['actions'][0]['status'], 'COMPLETE')
            self.assertFalse(summary['unfinished_actions'])

    def test_failure_is_rethrown_and_group_restored(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = Recorder(Path(root) / 'actions.jsonl')
            context = Context()
            old = dict(context.properties)
            error = ValueError('original failure')
            with recorder.path.open('x') as recorder.stream:
                with self.assertRaises(ValueError) as raised:
                    with recorder.action('failed', context):
                        raise error
            self.assertIs(raised.exception, error)
            self.assertEqual(context.properties, old)
            self.assertEqual(summarize_actions(recorder.path)['actions'][0]['status'], 'FAILED')

    def test_unrelated_action_is_not_instrumented(self):
        recorder = Recorder('unused')
        calls = []
        with patch('pipeline.spark_experiment.runtime.repository_profile.repository_callsite', return_value=[]):
            result = recorder.wrap_action(lambda obj: calls.append(obj) or 42, 'count')('outside')
        self.assertEqual(result, 42)
        self.assertEqual(calls, ['outside'])
        self.assertEqual(recorder.sequence, 0)

    def test_writer_and_output_recount_have_separate_actions(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = Recorder(Path(root) / 'actions.jsonl')
            context = Context()
            spark = SimpleNamespace(sparkContext=context)
            writer = SimpleNamespace(_spark=spark)
            frame = SimpleNamespace(sparkSession=spark)
            site = [{'function': '_write', 'dataset': 'quality/candidates', 'line': 44}]
            with recorder.path.open('x') as recorder.stream, patch(
                    'pipeline.spark_experiment.runtime.repository_profile.repository_callsite', return_value=site):
                recorder.wrap_action(lambda obj, path: None, 'parquet')(writer, '/unused')
                recorder.wrap_action(lambda obj: 100, 'count')(frame)
            labels = {x['label'] for x in summarize_actions(recorder.path)['actions']}
            self.assertEqual(labels, {'_write:quality/candidates:parquet', '_write:quality/candidates:count'})


if __name__ == '__main__':
    unittest.main()
