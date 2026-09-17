"""Input pinning and oracle gates for the isolated engine benchmark."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.spark_experiment.runtime.repository_duckdb_entry import verify_manifest


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.parquet'
        self.source.write_bytes(b'pinned fixture')
        self.manifest = {'input_identity': 'fixture', 'sample': {'package_rows': 1000},
                         'stages': {'repository': {'counts': {'package': 1000},
                                                   'files': {'package': [str(self.source)]}}},
                         'input_files': [{'path': str(self.source), 'bytes': self.source.stat().st_size,
                                          'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest()}]}

    def pin(self):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_hashes_verified_and_tampering_rejected(self):
        path, sha = self.pin()
        self.assertEqual(verify_manifest(path, sha)['input_identity'], 'fixture')
        self.source.write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            verify_manifest(path, sha)

    def test_manifest_tampering_rejected(self):
        path, sha = self.pin()
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            verify_manifest(path, sha)

    def test_unhashed_repository_input_rejected(self):
        self.manifest['stages']['repository']['files']['version'] = [str(self.root / 'unhashed')]
        with self.assertRaisesRegex(ValueError, 'not covered'):
            verify_manifest(*self.pin())

    def test_outside_root_rejected(self):
        self.manifest['input_files'][0]['path'] = str(self.root.parent / 'outside')
        with self.assertRaisesRegex(ValueError, 'outside'):
            verify_manifest(*self.pin())


class ComparisonTest(unittest.TestCase):
    def setUp(self):
        import duckdb
        from pipeline.spark_experiment.job import GROUPS
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trials = []
        for engine in ('spark', 'duckdb'):
            trial = self.root / engine
            self.trials.append(trial)
            for group in GROUPS['repository']:
                directory = trial / 'output' / group
                directory.mkdir(parents=True)
                with duckdb.connect() as con:
                    con.execute('COPY (SELECT 1::INTEGER AS value) TO ? (FORMAT PARQUET)',
                                [str(directory / 'data.parquet')])
            (trial / 'report.json').write_text(json.dumps({
                'engine': engine, 'status': 'COMPUTED', 'input_identity': 'fixture',
                'manifest_sha256': 'manifest', 'code_sha256': 'code',
                'output': str(trial / 'output'), 'result': {'validation': 'PASSED'}}))

    def test_equal_outputs_and_reports_pass(self):
        from pipeline.spark_experiment.runtime.repository_duckdb_entry import compare
        self.assertEqual(compare(self.trials, self.root / 'comparison.json')['status'], 'VERIFIED')

    def test_report_difference_fails_even_when_rows_equal(self):
        from pipeline.spark_experiment.runtime.repository_duckdb_entry import compare
        path = self.trials[1] / 'report.json'
        report = json.loads(path.read_text())
        report['result']['validation'] = 'WRONG'
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'outputs or reports differ'):
            compare(self.trials, self.root / 'comparison.json')
        self.assertEqual(json.loads((self.root / 'comparison.json').read_text())['status'], 'DIFFERENT')

    def test_code_identity_mismatch_rejected(self):
        from pipeline.spark_experiment.runtime.repository_duckdb_entry import compare
        path = self.trials[1] / 'report.json'
        report = json.loads(path.read_text())
        report['code_sha256'] = 'other'
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'code_sha256'):
            compare(self.trials, self.root / 'comparison.json')


if __name__ == '__main__':
    unittest.main()
