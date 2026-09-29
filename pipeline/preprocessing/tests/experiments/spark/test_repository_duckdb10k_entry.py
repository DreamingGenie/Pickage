"""Tests for the isolated 10k repository benchmark entry point."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.preprocessing.experiments.spark.runtime.repository_duckdb10k_entry import verify_manifest


class Manifest10kTest(unittest.TestCase):
    def _manifest(self, root, count=10000):
        source = root / 'input.parquet'
        source.write_bytes(b'pinned')
        return {'input_identity': 'fixture', 'sample': {'package_rows': count},
                'stages': {'repository': {'counts': {'package': count},
                                           'files': {'package': [str(source)]}}},
                'input_files': [{'path': str(source), 'bytes': source.stat().st_size,
                                 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]}

    def test_requires_pinned_10000_package_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = self._manifest(root, 9999)
            path = root / 'manifest.json'; path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '10000'):
                verify_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_accepts_hashed_10000_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = self._manifest(root)
            path = root / 'manifest.json'; path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(verify_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest())['input_identity'], 'fixture')


if __name__ == '__main__':
    unittest.main()

class FullStageCompareTest(unittest.TestCase):
    def test_compares_file_and_directory_layouts_and_json(self):
        import duckdb
        from pipeline.preprocessing.experiments.spark.job import GROUPS
        from pipeline.preprocessing.experiments.spark.runtime.repository_duckdb10k_entry import compare
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); trials=[]
            for engine in ('spark', 'duckdb'):
                trial=root/engine;trial.mkdir();trials.append(trial);stages={}
                for stage,groups in GROUPS.items():
                    output=trial/stage;stages[stage]={'output':str(output),'result':{}}
                    for group in groups:
                        target = output/'outputs'/(group+'.parquet') if stage=='dependents' else output/group
                        if target.suffix!='.parquet':target=target/'part.parquet'
                        target.parent.mkdir(parents=True,exist_ok=True)
                        sql="SELECT 1::INTEGER AS value"
                        if stage=='package_version' and group=='version/data':
                            sql="SELECT '[\"MIT\"]'::VARCHAR AS licenses, '{\"x\":\"1\"}'::VARCHAR AS dependency"
                        with duckdb.connect() as con:con.execute('COPY ('+sql+') TO ? (FORMAT PARQUET)',[str(target)])
                (trial/'report.json').write_text(json.dumps({'engine':engine,'status':'COMPUTED','input_identity':'x','manifest_sha256':'m','code_sha256':'c','stages':stages}))
            result=compare(trials,root/'comparison.json')
            self.assertEqual(result['status'],'VERIFIED')
            self.assertEqual(set(result['comparisons'][0]['stages']),set(GROUPS))
