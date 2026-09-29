import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.postgresql.version_dependents import historical_db_reload as module


class Source:
    def __init__(self, root, digest, output):
        self.expected = {'identities': 1, 'versions': 1}
        self.identity_file = Path(output) / 'identities.tsv'
        self.version_file = Path(output) / 'versions.tsv'
        self.identity_file.parent.mkdir(parents=True, exist_ok=True)
        self.identity_file.write_text('1\tone\n', encoding='utf-8')
        self.version_file.write_text('1\t1.0.0\n', encoding='utf-8')
        self.calendar = [{'snapshot_at': '2023-01-01'}]
        self.quality = {'2023-01-01': {'snapshot_at': '2023-01-01', 'target_versions': 1}}
        self.lineage = {}
        self.rechecks = 0

    def recheck(self):
        self.rechecks += 1

    def prepare_date(self, day):
        counts = self.identity_file.parent / 'counts.tsv'
        counts.write_text('1\t1.0.0\t2023-01-01\t2\n', encoding='utf-8')
        metadata = {'counts': {'package_version_snapshot': 1}, 'manifest': {'files': [
            {'role': 'identities', 'sha256': module.file_sha256(self.identity_file), 'bytes': self.identity_file.stat().st_size},
            {'role': 'counts', 'sha256': module.file_sha256(counts), 'bytes': counts.stat().st_size},
        ]}}
        return metadata, {'identities': self.identity_file, 'counts': counts}

    def close(self):
        pass


class Loader:
    instances = []

    def __init__(self, command, work_dir, schema, plan):
        self.published = []
        self.initialized = False
        self.closed = False
        self.__class__.instances.append(self)

    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def _send(self, sql): return ['fixture-cluster','fixture-db']
    def initialize(self): self.initialized = True
    def publish_day(self, metadata, files, execution_id, before_commit, failpoint=None):
        before_commit()
        self.published.append(execution_id)
        return {'action': 'PUBLISHED', 'rows': 1}
    def inspect_target(self):
        if self.closed:
            raise AssertionError('inspect_target called after loader close')
        return {'exists': bool(self.published), 'completed_dates': len(self.published), 'completed_rows': len(self.published), 'ready':bool(self.published)}


class ReloadCoordinatorTest(unittest.TestCase):
    def plan(self, root):
        return {'schema': 'vd193_reload_test', 'source_run_dir': str(root / 'input' / 'source-run'),
                'source_run_manifest_sha256': 'a' * 64, 'db_command': ['fake-psql'],
                'dates': ['2023-01-01'], 'rows_by_date': {'2023-01-01': 1},
                'generation': {key: 'y' for key in module.REQUIRED_GENERATION}, 'expected_rows': 1,
                'expected_dates': 1, 'execution_prefix': 'test',
                'db_identity': {'system_identifier':'fixture-cluster','current_database':'fixture-db'}}

    def test_run_initializes_once_and_publishes_with_recheck(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan_path = root / 'plan.json'
            plan_path.write_text(json.dumps(self.plan(root)), encoding='utf-8')
            config = {'plan': str(plan_path), 'output': str(root / 'job')}
            with patch.object(module, 'validate_generation'), patch.object(module, 'FullSource', Source), \
                    patch.object(module, 'verify_keys', return_value={'status': 'VERIFIED'}), \
                    patch.object(module, 'file_sha256', side_effect=lambda path: __import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()), \
                    patch.object(module, 'contract', return_value={'x': 'y'}), \
                    patch.object(module, 'inspect_resources', return_value={'host_scratch_ok': True, 'database_disk_ok': True}):
                result = module.ReloadCoordinator(config, loader_factory=Loader, source_factory=Source,
                                                  key_verifier=lambda *args: {'status': 'VERIFIED'}).run()
            self.assertEqual(result['status'], 'READY_FOR_CUTOVER')
            self.assertEqual(Loader.instances[-1].published, ['test-aaaaaaaaaaaaaaaa-20230101'])
            self.assertTrue(Loader.instances[-1].initialized)

    def test_stop_request_is_honored_at_date_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan_path = root / 'plan.json'
            plan_path.write_text(json.dumps(self.plan(root)), encoding='utf-8')
            job = root / 'job'
            job.mkdir()
            (job / 'stop-request.json').write_text('{}', encoding='utf-8')
            config = {'plan': str(plan_path), 'output': str(job)}
            with patch.object(module, 'validate_generation'), patch.object(module, 'FullSource', Source), \
                    patch.object(module, 'verify_keys', return_value={'status': 'VERIFIED'}), \
                    patch.object(module, 'file_sha256', side_effect=lambda path: __import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()), \
                    patch.object(module, 'contract', return_value={'x': 'y'}):
                with self.assertRaises(RuntimeError):
                    module.ReloadCoordinator(config, loader_factory=Loader, source_factory=Source,
                                             key_verifier=lambda *args: {'status': 'VERIFIED'}).run()

    def test_check_is_read_only_and_does_not_initialize(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan_path = root / 'plan.json'
            plan_path.write_text(json.dumps(self.plan(root)), encoding='utf-8')
            config = {'plan': str(plan_path), 'output': str(root / 'job')}
            with patch.object(module, 'validate_generation'), patch.object(module, 'inspect_resources', return_value={}), \
                    patch.object(module, 'file_sha256', side_effect=lambda path: __import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()):
                coordinator = module.ReloadCoordinator(config, loader_factory=Loader, source_factory=Source,
                                                       key_verifier=lambda *args: {'status': 'VERIFIED'})
                result = coordinator.check()
            self.assertEqual(result['status'], 'CHECKED')
            self.assertFalse(Loader.instances[-1].initialized)

    def test_existing_plan_is_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan_path = root / 'plan.json'
            plan = self.plan(root)
            plan_path.write_text(json.dumps(plan), encoding='utf-8')
            job = root / 'job'
            job.mkdir()
            (job / 'plan.json').write_text(json.dumps({**plan, 'expected_rows': 99}), encoding='utf-8')
            config = {'plan': str(plan_path), 'output': str(job)}
            with patch.object(module, 'validate_generation'):
                with self.assertRaisesRegex(ValueError, 'differs'):
                    module.ReloadCoordinator(config, loader_factory=Loader, source_factory=Source,
                                              key_verifier=lambda *args: {'status': 'VERIFIED'}).run()

    def test_code_contract_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan_path = root / 'plan.json'
            plan_path.write_text(json.dumps(self.plan(root)), encoding='utf-8')
            with patch.object(module, 'contract', return_value={key: 'changed' for key in module.REQUIRED_GENERATION}):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    module.ReloadCoordinator({'plan': str(plan_path), 'output': str(root / 'job')},
                                              loader_factory=Loader, source_factory=Source)

    def test_stale_lock_file_does_not_block_after_process_death(self):
        from pipeline.preprocessing.version_dependents.historical_artifact import _run_lock
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.writer.lock').write_bytes(b'0')
            with _run_lock(root):
                self.assertTrue((root / '.writer.lock').exists())


if __name__ == '__main__':
    unittest.main()
