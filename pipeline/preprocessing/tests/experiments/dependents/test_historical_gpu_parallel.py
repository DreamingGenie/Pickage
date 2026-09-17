"""CUDA pipeline parity, publication, resume and owner failure boundaries."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import torch
from pipeline.preprocessing.experiments.dependents import historical_gpu_parallel as p
from pipeline.preprocessing.version_dependents.historical_parallel_input import from_prepared
from pipeline.preprocessing.experiments.dependents.historical_parallel_benchmark import compare_runs
from pipeline.preprocessing.tests.version_dependents.test_historical_production import prepared_fixture


@unittest.skipUnless(os.name == 'nt' and torch.cuda.is_available(), 'Windows CUDA required')
class GpuParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vg-')
        cls.root = Path(cls.temp.name)
        source = cls.root / 'source'
        digest = prepared_fixture(source)
        cls.prepared = cls.root / 'input'
        cls.input = from_prepared(prepared_dir=source, manifest_sha256=digest, output=cls.prepared)
        cls.reference = cls.root / 'cpu'
        p.cpu.run(prepared_dir=cls.prepared, manifest_sha256=cls.input['manifest_sha256'],
                  output=cls.reference, workers=2, history_layout='grouped', min_free_bytes=0)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_job(self, name, **kwargs):
        return p.run(prepared_dir=self.prepared, manifest_sha256=self.input['manifest_sha256'],
                     output=self.root / name, min_free_bytes=0, **kwargs)

    def verify(self, name, result):
        self.assertTrue(p.verify_run(run_dir=self.root / name,
                        manifest_sha256=result['run_manifest_sha256'])['verified'])
        groups = compare_runs(self.reference, self.root / name)
        self.assertEqual(len(groups), 13)
        self.assertTrue(all(item['equal'] for item in groups.values()))

    def test_parity_and_resume_across_worker_counts(self):
        partial = self.run_job('resume', workers=1, max_partitions=1)
        self.assertEqual(partial['run_status'], 'INCOMPLETE')
        pointers = {f: f.read_bytes() for f in (self.root / 'resume').glob('partitions/*/complete.json')}
        result = self.run_job('resume', workers=4, resume=True)
        self.verify('resume', result)
        for path, raw in pointers.items(): self.assertEqual(raw, path.read_bytes())
        repeated = self.run_job('resume', workers=2, resume=True)
        self.assertEqual(repeated['written_partitions'], [])
        self.assertEqual(repeated['run_manifest_sha256'], result['run_manifest_sha256'])

    def test_orphan_candidate_recovered(self):
        original = p._checkpoint
        def crash(root, phase, **values):
            original(root, phase, **values)
            if phase == 'CANDIDATE': raise RuntimeError('injected candidate crash')
        with patch.object(p, '_checkpoint', crash), self.assertRaisesRegex(RuntimeError, 'injected candidate'):
            self.run_job('orphan', workers=2)
        self.assertFalse((self.root / 'orphan' / 'run_manifest.json').exists())
        result = self.run_job('orphan', workers=2, resume=True)
        self.assertTrue(result['reused_partitions'])
        self.verify('orphan', result)

    def test_owner_death_aborts_then_resumes_accepted_work(self):
        original = p._compute
        owner_pids = []
        def compute(*args):
            owner = args[-1]
            owner_pids.append(owner.pid)
            checkpoint = p._checkpoint
            def kill(root, phase, **values):
                checkpoint(root, phase, **values)
                if phase == 'ACCEPTED':
                    owner.pool.slots[0]['process'].terminate()
                    owner.pool.slots[0]['process'].join(5)
            with patch.object(p, '_checkpoint', kill): return original(*args)
        with patch.object(p, '_compute', compute), self.assertRaises(p.OwnerError):
            self.run_job('death', workers=2)
        self.assertFalse((self.root / 'death' / 'run_manifest.json').exists())
        result = self.run_job('death', workers=2, resume=True)
        self.assertTrue(result['reused_partitions'])
        self.assertNotIn(result['resources']['gpu_owner_pid'], owner_pids)
        self.verify('death', result)

    def test_tampered_output_rejected(self):
        self.run_job('tamper', workers=1, max_partitions=1)
        target = next((self.root / 'tamper').glob('partitions/*/attempts/*/counts.parquet'))
        with target.open('ab') as stream: stream.write(b'altered')
        with self.assertRaises(ValueError): self.run_job('tamper', workers=2, resume=True)

    def test_locked_resume_does_not_start_another_gpu_owner(self):
        output = self.root / 'locked'
        output.mkdir()
        with p._run_lock(output), patch.object(p, 'Owner') as owner:
            with self.assertRaisesRegex(RuntimeError, 'Another writer'):
                self.run_job('locked', workers=1, resume=True)
            owner.assert_not_called()


if __name__ == '__main__': unittest.main()
