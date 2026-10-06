"""Small tests for full-coverage batching, oracle identity and paired summaries."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from pipeline.preprocessing.experiments.dependents.historical_gpu_suite_benchmark import messages, result_hash, sum_routes, summarize_rounds


class GpuSuiteBenchmarkTests(unittest.TestCase):
    def fixture(self):
        interval = {'start_index': 0, 'end_index': 3, 'status': 'RESOLVED',
                    'normalized_range': '>=1.0.0 <2.0.0-0', 'target_version': '1.0.0'}
        package = {'name': 'dep', 'package_id': 20, 'known_package': True,
                   'candidates': [{'version': '1.0.0', 'birth_index': 0}],
                   'lookups': [(1, '^1')], 'oracle': {1: [{**interval, 'target_package_id': 20}]}}
        return package, [{'requirement': '^1', 'intervals': [interval]}]

    def test_all_lookups_are_batched_without_truncation(self):
        package, _ = self.fixture()
        package['lookups'] = [(i, None if i == 13 else str(i)) for i in range(2701)]
        batches = list(messages(package, 229, 1024))
        self.assertEqual([len(items) for items, _ in batches], [1024, 1024, 653])
        self.assertEqual([item for items, _ in batches for item in items], package['lookups'])
        for items, message in batches:
            self.assertEqual(message['requirements'], [req for _, req in items])
            self.assertEqual(message['name'], package['name'])
            self.assertIs(message['candidates'], package['candidates'])

    def test_zero_lookup_package_has_no_fake_work(self):
        package, _ = self.fixture()
        package['lookups'] = []
        self.assertEqual(list(messages(package, 229, 1024)), [])
        self.assertEqual(result_hash(package, [], [], 229), result_hash(package, [], [], 229))

    def test_invalid_batch_size_rejected(self):
        package, _ = self.fixture()
        for value in (0, 1025, True, 1.5):
            with self.assertRaises(ValueError): list(messages(package, 229, value))

    def test_every_oracle_field_and_lookup_identity_is_checked(self):
        package, result = self.fixture()
        self.assertEqual(len(result_hash(package, package['lookups'], result, 3)), 64)
        for field, replacement in [('target_package_id', 99), ('target_version', '2.0.0'),
                                   ('normalized_range', '*'), ('status', 'NO_SATISFYING_VERSION')]:
            corrupted = copy.deepcopy(package)
            corrupted['oracle'][1][0][field] = replacement
            with self.assertRaises(ValueError): result_hash(corrupted, package['lookups'], result, 3)
        with self.assertRaises(ValueError): result_hash(package, package['lookups'], [], 3)
        wrong = copy.deepcopy(result)
        wrong[0]['requirement'] = '~1'
        with self.assertRaises(ValueError): result_hash(package, package['lookups'], wrong, 3)

    def test_gap_in_result_rejected(self):
        package, result = self.fixture()
        result[0]['intervals'][0]['start_index'] = 1
        with self.assertRaises(ValueError): result_hash(package, package['lookups'], result, 3)

    def test_zero_routes_keep_fields_and_undefined_speedup(self):
        values = dict(numeric_seconds=0.0, normalization_plus_numeric_seconds=0.0, path_seconds=0.0)
        summed = sum_routes([{'cpu': values}, {'cpu': values}], 'cpu')
        self.assertEqual(summed, values)
        summary = summarize_rounds([{'cpu': summed, 'gpu': summed}] * 3)
        self.assertIsNone(summary['cpu_over_gpu_speedup']['path_seconds'])

    def test_summary_uses_total_round_medians(self):
        def metrics(value):
            return dict(numeric_seconds=value, normalization_plus_numeric_seconds=value, path_seconds=value)
        rounds = [{'cpu': metrics(c), 'gpu': metrics(g)} for c, g in [(10, 2), (20, 10), (30, 12)]]
        summary = summarize_rounds(rounds)
        self.assertEqual(summary['cpu_over_gpu_speedup']['path_seconds'], 2)
        self.assertEqual(summary['cpu']['path_seconds']['median_seconds'], 20)


@unittest.skipUnless(os.environ.get('VD_GPU_TESTS') == '1' and importlib.util.find_spec('torch'),
                     'Set VD_GPU_TESTS=1 for isolated CUDA suite integration')
class GpuSuiteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.preprocessing.version_dependents.historical_production import run
        from pipeline.preprocessing.tests.version_dependents.test_historical_production import prepared_fixture
        cls.tmp = tempfile.TemporaryDirectory(prefix='g32-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        digest = prepared_fixture(cls.root / 'in')
        cls.finished = run(prepared_dir=cls.root / 'in', manifest_sha256=digest,
                           output=cls.root / 'run', algorithm='weighted-events-v2')

    def load(self, digest=None):
        from pipeline.preprocessing.experiments.dependents.historical_gpu_suite_input import load_suite
        return load_suite(prepared_dir=self.root / 'in', oracle_run_dir=self.root / 'run',
                          oracle_manifest_sha256=digest or self.finished['run_manifest_sha256'])

    def test_isolated_all_lookup_suite_with_zero_and_unmapped_packages(self):
        from pipeline.preprocessing.experiments.dependents.historical_gpu_suite_benchmark import run_suite
        suite = self.load()
        report = run_suite(prepared_dir=self.root / 'in', oracle_run_dir=self.root / 'run',
                           oracle_manifest_sha256=self.finished['run_manifest_sha256'],
                           output=self.root / 'comparison', repetitions=3, lookup_batch=1, workspace_mib=1)
        self.assertEqual(report['status'], 'COMPLETE')
        self.assertEqual(report['input_rows']['target_names'], 5)
        self.assertEqual(report['compared_lookup_dates'], suite['input_rows']['lookups'] * 3)
        self.assertEqual(report['all_date_mismatches'], 0)
        self.assertTrue(report['repeated_result_hashes_equal'])
        self.assertTrue(any(p['zero_lookup_no_computation'] for p in report['rounds'][0]['packages']))

    def test_changed_production_generation_rejected(self):
        path = self.root / 'run' / 'run_plan.json'
        original = path.read_bytes()
        try:
            plan = json.loads(original)
            plan['generation_contract']['runner_sha256'] = '0' * 64
            path.write_text(json.dumps(plan), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'weighted production plan'):
                self.load()
        finally:
            path.write_bytes(original)

    def test_stale_oracle_receipt_pointer_rejected(self):
        from pipeline.preprocessing.requirements_resolution.input import file_sha256
        path = self.root / 'run' / 'run_manifest.json'
        original = path.read_bytes()
        try:
            manifest = json.loads(original)
            manifest['partitions'][0]['receipt_sha256'] = '0' * 64
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaises(ValueError): self.load(file_sha256(path))
        finally:
            path.write_bytes(original)

    def test_input_change_after_loading_is_detected(self):
        from pipeline.preprocessing.experiments.dependents.historical_gpu_suite_input import reverify_protected_files
        suite = self.load()
        path = self.root / 'in' / 'target_population.parquet'
        original = path.read_bytes()
        try:
            path.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'protected suite input changed'):
                reverify_protected_files(suite)
        finally:
            path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
