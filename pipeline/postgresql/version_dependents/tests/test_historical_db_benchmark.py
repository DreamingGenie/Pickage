import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.postgresql.version_dependents.historical_db_benchmark import cleanup, prepare_input, relation


class BenchmarkSafetyTests(unittest.TestCase):
    def test_service_schema_and_injected_names_rejected(self):
        for schema, name in [('public', 'version'), ('vd193_bench_'+'a'*32, 'x;DROP SCHEMA public')]:
            with self.assertRaises(ValueError):
                relation(schema, name)

    def test_cleanup_rejects_changed_owner_and_never_cascades(self):
        schema='vd193_bench_'+'a'*32
        db=Mock()
        db._send.return_value=['f']
        with self.assertRaises(ValueError):
            cleanup(db,schema)
        self.assertEqual(db._send.call_count,1)
        db.reset_mock()
        db._send.side_effect=[['t'],['source','trial_0_0'],[],[],[]]
        cleanup(db,schema)
        commands=[call.args[0] for call in db._send.call_args_list]
        self.assertTrue(all('CASCADE' not in sql for sql in commands))
        self.assertEqual(commands[-1],f'DROP SCHEMA {schema};')

    def test_sample_preserves_copy_escaping_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source';source.mkdir()
            path=source/'counts.tsv'
            payload=b'1\ta\\\\b\\t\\n\\r\\\\N\t2023-03-06\t0\n2\t2.0\t2023-03-06\t7\n3\t3.0\t2023-03-06\t2\n'
            path.write_bytes(payload)
            metadata={'snapshot':'2023-03-06','manifest':{'files':[
                {'role':'counts','sha256':file_sha256(path),'bytes':len(payload),'rows':3}]}}
            (source/'metadata.json').write_text(json.dumps(metadata))
            for n in (1,2,3):
                output=Path(root)/str(n);output.mkdir()
                sample,receipt=prepare_input(source,output,n)
                self.assertEqual(receipt['rows'],n)
                self.assertEqual(sample.read_bytes().splitlines()[0],payload.splitlines()[0])
                if n==3:self.assertEqual(sample.read_bytes(),payload)
            path.write_bytes(payload+b'4\t4.0\t2023-03-06\t0\n')
            with self.assertRaisesRegex(ValueError,'differs'):
                prepare_input(source,Path(root),1)


if __name__=='__main__':unittest.main()
