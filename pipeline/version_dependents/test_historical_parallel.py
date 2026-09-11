"""Production math parity and coordinator publication/recovery boundaries."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes
from .historical_artifact import _read_json
from .historical_cache import _record
from . import historical_parallel as p
from . import historical_parallel_worker as w
from .historical_parallel_input import from_prepared
from .historical_parallel_benchmark import compare_runs
from .test_historical_production import prepared_fixture


def die_once(task, context):
    marker = Path(task['run_root']) / 'injected-worker-death'
    try:
        with marker.open('x'):
            pass
    except FileExistsError:
        return w.execute(task, context)
    os._exit(17)


@unittest.skipUnless(os.name == 'nt', 'Windows parallel runner')
class ParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vp-')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source'
        cls.source_sha = prepared_fixture(cls.source)
        cls.shards = cls.root / 'input'
        cls.input = from_prepared(prepared_dir=cls.source, manifest_sha256=cls.source_sha, output=cls.shards)
        cls.reference = cls.root / 'baseline'
        p.old.run(prepared_dir=cls.source, manifest_sha256=cls.source_sha, output=cls.reference,
                  algorithm=p.old.WEIGHTED_ALGORITHM, resolver_backend='cpu', min_free_bytes=0)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_job(self, name, **kwargs):
        return p.run(prepared_dir=self.shards, manifest_sha256=self.input['manifest_sha256'],
                     output=self.root / name, min_free_bytes=0, **kwargs)

    def verify(self, name, result):
        self.assertTrue(p.verify_run(run_dir=self.root / name,
                        manifest_sha256=result['run_manifest_sha256'])['verified'])
        groups = compare_runs(self.reference, self.root / name)
        self.assertEqual(len(groups), 13)
        self.assertTrue(all(g['equal'] for g in groups.values()))

    def test_worker_counts_and_resume_preserve_all_thirteen_groups(self):
        self.verify('single', self.run_job('single', workers=1))
        partial = self.run_job('resume', workers=2, max_partitions=1)
        self.assertEqual(partial['run_status'], 'INCOMPLETE')
        pointers = {path: path.read_bytes() for path in (self.root / 'resume' / 'partitions').glob('*/complete.json')}
        complete = self.run_job('resume', workers=4, resume=True)
        self.assertEqual(complete['reused_partitions'], partial['written_partitions'])
        for path, raw in pointers.items():
            self.assertEqual(path.read_bytes(), raw)
        self.verify('resume', complete)
        repeated = self.run_job('resume', workers=2, resume=True)
        self.assertEqual(repeated['written_partitions'], [])
        self.assertEqual(repeated['run_manifest_sha256'], complete['run_manifest_sha256'])
        manifest = _read_json(self.root / 'resume' / 'run_manifest.json')
        for partition in manifest['partitions']:
            receipt = _read_json(self.root / 'resume' / partition['attempt'] / 'receipt.json')
            opened = receipt['metrics']['opened_input_paths']
            self.assertEqual(len(opened), 4)
            self.assertTrue(all(Path(f).parent.name == f"partition={partition['partition_id']:03d}" for f in opened))

    def test_grouped_history_matches_legacy_and_reuses_complete_run(self):
        first = self.run_job('grouped', workers=2, history_layout='grouped')
        self.verify('grouped', first)
        second = self.run_job('grouped', workers=4, history_layout='grouped', resume=True)
        self.assertEqual(first['run_manifest_sha256'], second['run_manifest_sha256'])
        self.assertEqual(second['written_partitions'], [])

    def test_crash_before_accept_and_after_pointer_are_recovered(self):
        for phase in ('CANDIDATE', 'POINTER_PUBLISHED'):
            name = phase.lower()
            original = p._checkpoint
            def crash(root, reached, **values):
                original(root, reached, **values)
                if reached == phase:
                    raise RuntimeError('injected coordinator crash')
            with patch.object(p, '_checkpoint', crash), self.assertRaisesRegex(RuntimeError, 'injected coordinator'):
                self.run_job(name, workers=2)
            candidates = list((self.root / name / 'partitions').glob('*/attempts/*/receipt.json'))
            self.assertGreaterEqual(len(candidates), 1)
            completed = self.run_job(name, workers=4, resume=True)
            self.verify(name, completed)
            self.assertTrue(completed['reused_partitions'])

    def test_worker_death_retries_in_a_new_attempt(self):
        with patch.object(w, 'execute', die_once):
            result = self.run_job('worker-death', workers=2)
        self.verify('worker-death', result)
        lines = (self.root / 'worker-death' / 'progress.jsonl').read_text().splitlines()
        self.assertTrue(any(json.loads(line)['phase'] == 'FAILED' for line in lines))

    def test_tampered_accepted_partition_is_rejected_on_resume(self):
        self.run_job('tamper', workers=1, max_partitions=1)
        path = next((self.root / 'tamper' / 'partitions').glob('*/attempts/*/counts.parquet'))
        with path.open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaises(ValueError):
            self.run_job('tamper', workers=4, resume=True)

    def test_multiple_equal_candidates_adopt_once_and_conflict_fails(self):
        for conflict in (False, True):
            name = 'conflict' if conflict else 'duplicate'
            original = p._checkpoint
            def crash(root, phase, **values):
                if phase == 'CANDIDATE':
                    raise RuntimeError('candidate boundary')
                original(root, phase, **values)
            with patch.object(p, '_checkpoint', crash), self.assertRaisesRegex(RuntimeError, 'candidate boundary'):
                self.run_job(name, workers=1)
            receipt_path = next((self.root / name / 'partitions').glob('*/attempts/*/receipt.json'))
            source = receipt_path.parent
            dest = source.parent / ('a' * 32 if source.name != 'a' * 32 else 'b' * 32)
            shutil.copytree(source, dest)
            assignment = _read_json(dest / 'assignment.json')
            assignment['attempt'] = dest.relative_to(self.root / name).as_posix()
            (dest / 'assignment.json').write_bytes(canonical_bytes(assignment))
            receipt = _read_json(dest / 'receipt.json')
            receipt['attempt_id'] = dest.name
            receipt['assignment_sha256'] = file_sha256(dest / 'assignment.json')
            if conflict:
                import duckdb
                counts = dest / 'counts.parquet'
                with duckdb.connect() as con:
                    con.execute('CREATE TABLE altered AS SELECT * FROM read_parquet(?)', [str(counts)])
                    con.execute('UPDATE altered SET dependents_count=dependents_count+1')
                    counts.unlink()
                    con.execute('COPY altered TO ? (FORMAT PARQUET)', [str(counts)])
                receipt['files'] = [_record(dest / r['name']) for r in receipt['files']]
            (dest / 'receipt.json').write_bytes(canonical_bytes(receipt))
            if conflict:
                with self.assertRaisesRegex(ValueError, 'different results'):
                    self.run_job(name, workers=2, resume=True)
            else:
                self.verify(name, self.run_job(name, workers=2, resume=True))


if __name__ == '__main__':
    unittest.main()
