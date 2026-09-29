"""Exercise the normal history entrypoint with a pinned saved artifact."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import duckdb

from pipeline.postgresql.package_snapshot import history
from pipeline.preprocessing.package_snapshot.history_contract import build_contract_sha256, validator_contract_sha256
from pipeline.preprocessing.package_snapshot.history_policy import policy_document, policy_sha256
from pipeline.preprocessing.tests.package_snapshot import test_quality as legacy_fixture
from pipeline.preprocessing.package_snapshot.quality import QUALITY_SCHEMA_ID, normalize_quality


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
        # Convert the frozen 17-column fixture through the production reader so
        # this resume test exercises the current v2 artifact contract.  The
        # source fixture itself remains legacy and is still covered by
        # test_quality.py.
        quality_v2 = self.root / 'quality-v2.parquet'
        with duckdb.connect() as con:
            fixture.views(con)
            normalize_quality(con, fixture.manifest, producer='history')
            con.execute('COPY quality TO ? (FORMAT PARQUET)', [str(quality_v2)])
        records = []
        for role, original in fixture.files.items():
            if role == 'quality':
                original = quality_v2
            target = output / (role + '.parquet')
            shutil.copyfile(original, target)
            body = target.read_bytes()
            records.append({'role': role, 'path': target.name, 'bytes': len(body),
                            'sha256': hashlib.sha256(body).hexdigest(), 'row_count': 2})
        self.manifest = {
            'dataset': 'package-snapshot', 'format_version': 1, 'status': 'PASSED',
            'snapshot': '2025-12-31', 'snapshot_timestamp': self.interval['snapshot_timestamp'],
            'run_id': 'compat-20251231', 'contract_sha256': validator_contract_sha256(),
            'build_contract_sha256': build_contract_sha256(),
            'quality_schema': QUALITY_SCHEMA_ID,
            'interval': self.interval, 'history_policy': policy_document(),
            'history_policy_sha256': policy_sha256(), 'input_manifest_sha256': 'a' * 64,
            'input_manifest': {k: self.sources[k] for k in ('population', 'candidate', 'repository', 'downloads')},
            'projects_input': self.sources['projects']['2025-12-31'],
            'counts': {'package_snapshot': 2}, 'files': records,
            'required_remote_verification': 'GET_SHA256_ALL_FILES'}
        self.saved = self.day_root / 'run_manifest.json'
        self.saved.write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_matching_build_reuses_after_validator_change(self):
        baseline = {'base_values': {'rows': 3}, 'current': [], 'reference_rows': 2, 'snapshot_rows': 2,
                    'dates': [{'snapshot_at': '2025-12-31', 'rows': 2},
                              {'snapshot_at': '2026-08-31', 'rows': 3}]}
        before = self.saved.read_bytes()
        db_report = {'result': {'action': 'REVERIFIED'}, 'elapsed_seconds': 0}
        original_read_text = Path.read_text

        def changed_validator(path, *args, **kwargs):
            value = original_read_text(path, *args, **kwargs)
            return value + '\n# validator-only change\n' if path.name == 'quality.py' else value

        with (patch.object(Path, 'read_text', new=changed_validator),
              patch.object(history, 'prepare', return_value=self.prepared),
              patch.object(history, 'database_state', return_value=baseline),
              patch.object(history, '_same_or_put'), patch.object(history, 'publish', return_value={}),
              patch.object(history, 'state_cache') as state,
              patch.object(history, 'build_snapshot') as build,
              patch.object(history, 'event'),
              patch.object(history, 'load_snapshot', return_value=db_report) as load):
            expected_validator = history.validator_contract_sha256()
            result = history.run({}, run_id='compat', work_dir=self.root, command=[], s3=object(),
                                 memory='256MB', threads=1, snapshots=['2025-12-31'])
        self.assertEqual(result['status'], 'SELECTED_DATES_PUBLISHED')
        state.assert_not_called()
        build.assert_not_called()
        self.assertEqual(load.call_args.kwargs['copy_input']['validation']['rows'], 2)
        self.assertEqual(load.call_args.kwargs['manifest']['contract_sha256'],
                         self.manifest['contract_sha256'])
        self.assertNotEqual(load.call_args.kwargs['contract_hash'], self.manifest['contract_sha256'])
        self.assertEqual(load.call_args.kwargs['contract_hash'],
                         expected_validator)
        self.assertEqual(before, self.saved.read_bytes())

    def test_invalid_build_contract_fails_before_db_or_publication(self):
        baseline = {'base_values': {'rows': 3}}
        before = self.saved.read_bytes()
        variants = ('missing', 'malformed', 'changed')
        for name in variants:
            with self.subTest(name=name):
                document = deepcopy(self.manifest)
                # Apply the mutation to a copy, avoiding changes to the fixture
                # shared by the other resume tests.
                if name == 'missing':
                    document.pop('build_contract_sha256')
                elif name == 'malformed':
                    document['build_contract_sha256'] = 'invalid'
                else:
                    document['build_contract_sha256'] = 'b' * 64
                self.saved.write_text(json.dumps(document), encoding='utf-8')
                variant_before = self.saved.read_bytes()
                try:
                    with (patch.object(history, 'prepare', return_value=self.prepared),
                          patch.object(history, 'database_state', return_value=baseline) as db,
                          patch.object(history, '_same_or_put') as same_or_put,
                          patch.object(history, 'publish') as publish,
                          patch.object(history, 'prepare_copy') as prepare_copy,
                          patch.object(history, 'load_snapshot') as load,
                          patch.object(history, 'build_snapshot') as build,
                          patch.object(history, 'event')):
                        with self.assertRaisesRegex(ValueError, 'build contract'):
                            history.run({}, run_id='compat', work_dir=self.root, command=[], s3=object(),
                                        memory='256MB', threads=1, snapshots=['2025-12-31'])
                    db.assert_not_called()
                    same_or_put.assert_not_called()
                    publish.assert_not_called()
                    prepare_copy.assert_not_called()
                    load.assert_not_called()
                    build.assert_not_called()
                    self.assertEqual(variant_before, self.saved.read_bytes())
                finally:
                    self.saved.write_bytes(before)

    def test_first_generation_records_build_and_validator_contracts(self):
        work = self.root / 'fresh'
        prepared = {**self.prepared, 'project_files': {'2025-12-31': []},
                    'daily_files': {}, 'verified_files': []}
        baseline = {'base_values': {'rows': 3}, 'current': [], 'reference_rows': 2,
                    'snapshot_rows': 2, 'dates': [{'snapshot_at': '2026-08-31', 'rows': 3}]}
        after = {**baseline, 'dates': [{'snapshot_at': '2025-12-31', 'rows': 2},
                                      {'snapshot_at': '2026-08-31', 'rows': 3}]}
        output = self.day_root / 'output'
        built_files = {role: str(output / (role + '.parquet'))
                       for role in ('package_snapshot', 'package_identity', 'quality')}
        built = {'files': built_files, 'rows': 2, 'quality_schema': QUALITY_SCHEMA_ID,
                 'quality': {}}
        with (patch.object(history, 'prepare', return_value=prepared),
              patch.object(history, 'database_state', side_effect=[baseline, after]),
              patch.object(history, '_same_or_put'), patch.object(history, 'publish', return_value={}),
              patch.object(history, 'state_cache', return_value={}) as state,
              patch.object(history, 'build_snapshot', return_value=built) as build,
              patch.object(history, 'load_snapshot', return_value={'result': {'action': 'LOADED'},
                                                                     'elapsed_seconds': 0}),
              patch.object(history, 'event'), patch.object(history, 'revalidate_files')):
            result = history.run({}, run_id='fresh', work_dir=work, command=[], s3=object(),
                                 memory='256MB', threads=1, snapshots=['2025-12-31'])
        manifest_path = work / 'fresh' / '2025-12-31' / 'run_manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(manifest['build_contract_sha256'], build_contract_sha256())
        self.assertEqual(manifest['contract_sha256'], validator_contract_sha256())
        state.assert_called_once()
        self.assertEqual(state.call_args.args[2], build_contract_sha256())
        build.assert_called_once()
        self.assertEqual(result['status'], 'SELECTED_DATES_PUBLISHED')

    def test_state_cache_reuses_matching_build_and_rejects_mutation(self):
        prepared = {'input_sha256': 'a' * 64}
        cache = self.root / 'state-cache'
        state = {'files': {'candidate': str(self.day_root / 'output' / 'package_snapshot.parquet')},
                 'counts': {}}
        build_hash = build_contract_sha256()
        with patch.object(history, 'prepare_state', return_value=state) as prepare_state:
            first = history.state_cache(prepared, cache, build_hash, '256MB', 1)
            self.assertEqual(first, state)
            prepare_state.assert_called_once()
        with patch.object(history, 'prepare_state') as prepare_state:
            second = history.state_cache(prepared, cache, build_hash, '256MB', 1)
            self.assertEqual(second, state)
            prepare_state.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'different input or code'):
            history.state_cache(prepared, cache, 'b' * 64, '256MB', 1)

    def test_saved_artifact_with_changed_build_contract_is_rejected(self):
        changed = {**self.manifest, 'build_contract_sha256': 'b' * 64}
        with self.assertRaisesRegex(ValueError, 'build contract'):
            history.validate_saved_manifest(changed, self.prepared, self.interval,
                                            'compat-20251231',
                                            build_contract=build_contract_sha256())

    def test_legacy_manifest_without_build_contract_fails_closed(self):
        legacy = {key: value for key, value in self.manifest.items()
                  if key != 'build_contract_sha256'}
        with self.assertRaisesRegex(ValueError, 'build contract'):
            history.validate_saved_manifest(legacy, self.prepared, self.interval,
                                            'compat-20251231',
                                            build_contract=build_contract_sha256())

    def test_malformed_build_contract_fails_closed(self):
        changed = {**self.manifest, 'build_contract_sha256': 'not-a-sha256'}
        with self.assertRaisesRegex(ValueError, 'build contract'):
            history.validate_saved_manifest(changed, self.prepared, self.interval,
                                            'compat-20251231',
                                            build_contract=build_contract_sha256())

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
