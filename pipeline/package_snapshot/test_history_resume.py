"""Exercise the normal history entrypoint with a pinned legacy artifact."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from . import history
from .history_policy import policy_document, policy_sha256
from . import test_quality as legacy_fixture


class HistoryResumeTests(unittest.TestCase):
    def setUp(self):
        fixture = legacy_fixture.LegacyHistoryQualityTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.interval = {**fixture.manifest['interval'], 'snapshot_at': '2025-12-31'}
        self.sources = {'population': {'snapshot': '2026-08-31', 'counts': {'package': 3}},
                        'candidate': {'sha256': 'b' * 64}, 'repository': {}, 'downloads': {},
                        'projects': {'2025-12-31': {'snapshot': '2025-12-31'}}}
        self.prepared = {'input_manifest': self.sources, 'input_sha256': 'a' * 64,
                         'verified_files': [], 'calendar': [self.interval, {'snapshot_at': '2026-08-31'}]}
        self.day_root = self.root / 'compat' / '2025-12-31'
        output = self.day_root / 'output'
        output.mkdir(parents=True)
        records = []
        for role, original in fixture.files.items():
            target = output / (role + '.parquet')
            shutil.copyfile(original, target)
            body = target.read_bytes()
            records.append({'role': role, 'path': target.name, 'bytes': len(body),
                            'sha256': hashlib.sha256(body).hexdigest(), 'row_count': 2})
        self.manifest = {
            'dataset': 'package-snapshot', 'format_version': 1, 'status': 'PASSED',
            'snapshot': '2025-12-31', 'snapshot_timestamp': self.interval['snapshot_timestamp'],
            'run_id': 'compat-20251231', 'contract_sha256': 'f' * 64,
            'interval': self.interval, 'history_policy': policy_document(),
            'history_policy_sha256': policy_sha256(), 'input_manifest_sha256': 'a' * 64,
            'input_manifest': {k: self.sources[k] for k in ('population', 'candidate', 'repository', 'downloads')},
            'projects_input': self.sources['projects']['2025-12-31'],
            'counts': {'package_snapshot': 2}, 'files': records,
            'required_remote_verification': 'GET_SHA256_ALL_FILES'}
        self.saved = self.day_root / 'run_manifest.json'
        self.saved.write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_old_artifact_reaches_real_copy_validation_without_rebuilding(self):
        baseline = {'base_values': {'rows': 3}, 'current': [], 'reference_rows': 2, 'snapshot_rows': 2,
                    'dates': [{'snapshot_at': '2025-12-31', 'rows': 2},
                              {'snapshot_at': '2026-08-31', 'rows': 3}]}
        before = self.saved.read_bytes()
        db_report = {'result': {'action': 'REVERIFIED'}, 'elapsed_seconds': 0}
        with (patch.object(history, 'prepare', return_value=self.prepared),
              patch.object(history, 'database_state', return_value=baseline),
              patch.object(history, '_same_or_put'), patch.object(history, 'publish', return_value={}),
              patch.object(history, 'state_cache') as state,
              patch.object(history, 'build_snapshot') as build,
              patch.object(history, 'event'),
              patch.object(history, 'load_snapshot', return_value=db_report) as load):
            result = history.run({}, run_id='compat', work_dir=self.root, command=[], s3=object(),
                                 memory='256MB', threads=1, snapshots=['2025-12-31'])
        self.assertEqual(result['status'], 'SELECTED_DATES_PUBLISHED')
        state.assert_not_called()
        build.assert_not_called()
        self.assertEqual(load.call_args.kwargs['copy_input']['validation']['rows'], 2)
        self.assertEqual(load.call_args.kwargs['manifest']['contract_sha256'], 'f' * 64)
        self.assertNotEqual(load.call_args.kwargs['contract_hash'], 'f' * 64)
        self.assertEqual(before, self.saved.read_bytes())

    def test_saved_artifact_input_policy_schema_and_paths_are_checked(self):
        changes = [('input_manifest_sha256', 'c' * 64), ('history_policy_sha256', 'd' * 64),
                   ('history_policy', {}), ('quality_schema', 'unknown'), ('projects_input', {}),
                   ('snapshot_timestamp', '2025-12-31T22:00:00Z')]
        for key, value in changes:
            with self.subTest(key=key):
                changed = {**self.manifest, key: value}
                with self.assertRaises(ValueError):
                    history.validate_saved_manifest(changed, self.prepared, self.interval, 'compat-20251231')
        changed = deepcopy(self.manifest)
        changed['files'][0]['path'] = '../outside.parquet'
        with self.assertRaisesRegex(ValueError, 'paths differ'):
            history.validate_saved_manifest(changed, self.prepared, self.interval, 'compat-20251231')


if __name__ == '__main__':
    unittest.main()
