import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.postgresql.version_dependents import historical_db_load as module


class LoadCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.run=self.root/'calculation'/'run'
        self.run.mkdir(parents=True)
        self.prepared=self.root/'prepared'
        self.prepared.mkdir()
        (self.run/'input_location.json').write_text(json.dumps({'prepared_dir':str(self.prepared)}))
        self.output=self.root/'load'
        self.args=dict(run_dir=self.run,manifest_sha256='a'*64,output=self.output,command=['test'])
        owner=self
        class Source:
            def __init__(self,run,digest,output):
                output.mkdir(parents=True)
                self.output=output
                self.expected={'identities':1,'versions':2}
                self.calendar=[{'snapshot_at':'2026-08-30'},{'snapshot_at':'2026-08-31'}]
                self.lineage={}
                self.identity_file=output/'identities'
                self.version_file=output/'versions'
            def recheck(self): pass
            def close(self): owner.closed=True
            def prepare_date(self,day): return {'snapshot':day},{}
        self.closed=False
        self.source=patch.object(module,'FullSource',Source)
        self.keys=patch.object(module,'verify_keys',return_value={'status':'VERIFIED'})
        self.source.start();self.keys.start()

    def tearDown(self):
        self.source.stop();self.keys.stop();self.temp.cleanup()

    def test_default_never_publishes(self):
        with patch.object(module,'publish_date') as publish:
            result=module.load(**self.args)
        publish.assert_not_called()
        self.assertEqual(result['status'],'KEYS_VERIFIED')
        self.assertTrue(self.closed)

    def test_fail_then_resume_revisits_same_execution_ids(self):
        calls=[]
        def publish(command,work,metadata,files,execution,generation,recheck):
            calls.append(execution)
            if len(calls)==2: raise RuntimeError('crash')
            return {'action':'LOADED' if len(calls)==1 else 'REVERIFIED'}
        with patch.object(module,'publish_date',side_effect=publish):
            with self.assertRaisesRegex(RuntimeError,'crash'): module.load(**self.args,publish=True)
            self.assertEqual(json.loads((self.output/'status.json').read_bytes())['phase'],'FAILED')
            result=module.load(**self.args,publish=True)
        self.assertEqual(calls[:2],calls[2:])
        self.assertEqual(len(result['dates']),2)
        self.assertEqual(result['scope'],'FULL_CALENDAR')

    def test_resume_rejects_changed_target_or_code(self):
        module.load(**self.args)
        with self.assertRaisesRegex(ValueError,'Resume plan'):
            module.load(**{**self.args,'command':['other']})
        with patch.object(module,'contract',return_value={'changed':'b'*64}):
            with self.assertRaisesRegex(ValueError,'Resume plan'): module.load(**self.args)

    def test_source_overlap_rejected_before_writing_plan(self):
        with self.assertRaisesRegex(ValueError,'overlaps'):
            module.load(**{**self.args,'output':self.prepared/'bad'})
        self.assertFalse((self.prepared/'bad').exists())

    def test_source_open_failure_is_recorded(self):
        with patch.object(module,'FullSource',side_effect=ValueError('source changed')):
            with self.assertRaisesRegex(ValueError,'source changed'): module.load(**self.args)
        self.assertEqual(json.loads((self.output/'status.json').read_bytes())['phase'],'FAILED')


if __name__=='__main__':
    unittest.main()
