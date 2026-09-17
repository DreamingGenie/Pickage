"""CLI orchestration boundaries that do not need a database."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.postgresql.snapshot.load import prior_date_load, run


class SnapshotLoadTests(unittest.TestCase):
    def prepared(self):
        candidate = {'calendar': [{'snapshot_at': '2026-08-31'}], 'policy_sha256': 'a'*64,
                     'files': [{'path': 'snapshot-dates.sql', 'sha256': 'b'*64}]}
        return {'candidate': candidate, 'calendar': candidate['calendar'],
                'candidate_sha256': 'c'*64, 'inventory_sha256': 'd'*64}

    def test_verify_only_never_connects(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('pipeline.postgresql.snapshot.load.read_candidate', return_value=self.prepared()), \
                    patch('pipeline.postgresql.snapshot.load.SnapshotLoader') as loader:
                result = run(Path(tmp)/'candidate.json', 'verify', Path(tmp), None, verify_only=True)
            loader.assert_not_called()
            self.assertEqual(result['status'], 'VERIFIED')
            self.assertFalse(result['service_ready'])
            self.assertEqual(json.loads(Path(result['report_path']).read_text())['input']['counts'], {'snapshot': 1})

    def test_invalid_source_leaves_failure_report_and_no_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('pipeline.postgresql.snapshot.load.read_candidate', side_effect=ValueError('source changed')), \
                    patch('pipeline.postgresql.snapshot.load.SnapshotLoader') as loader:
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    run(Path(tmp)/'candidate.json', 'bad', Path(tmp), ['psql'])
            loader.assert_not_called()
            reports = list(Path(tmp).glob('bad/*/execution_report.json'))
            self.assertEqual(len(reports), 1)
            self.assertEqual(json.loads(reports[0].read_text())['status'], 'FAILED')

    def test_execution_id_cannot_escape_work_directory(self):
        with self.assertRaisesRegex(ValueError, 'execution ID'):
            run(Path('.'), '../bad', Path('.'), None, verify_only=True)

    def test_prior_receipt_must_identify_same_candidate_policy_and_dates(self):
        prepared = self.prepared()
        valid = {'status': 'COMMITTED_AND_VERIFIED', 'candidate_sha256': 'c'*64,
                 'policy_sha256': 'a'*64, 'source_sql_sha256': 'b'*64,
                 'expected_dates': ['2026-08-31'], 'database': 'test'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            path.write_text(json.dumps(valid))
            self.assertEqual(prior_date_load(path, prepared)['receipt'], valid)
            for key, wrong in [('status', 'PREPARING'), ('candidate_sha256', 'e'*64),
                               ('policy_sha256', 'f'*64), ('expected_dates', [])]:
                with self.subTest(key=key):
                    path.write_text(json.dumps({**valid, key: wrong}))
                    with self.assertRaisesRegex(ValueError, 'receipt does not match'):
                        prior_date_load(path, prepared)


if __name__ == '__main__':
    unittest.main()
