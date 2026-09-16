import json
from pathlib import Path
import tempfile
import unittest

from pipeline.spark_experiment.freeze_raw import freeze, plan_raw, safe_key
from tests.orchestration_fixture import make_fixture


class RawFreezeTests(unittest.TestCase):
    def test_freeze_preserves_source_and_verifies_local_and_shared_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = make_fixture(root/'fixture')
            s3 = fixture.s3
            before = dict(s3.objects)
            def copy_object(*, Bucket, Key, CopySource, CopySourceIfMatch):
                self.assertEqual(s3.head_object(**CopySource)['ETag'], CopySourceIfMatch)
                s3.objects[(Bucket, Key)] = s3.objects[(CopySource['Bucket'], CopySource['Key'])]
            s3.copy_object = copy_object
            result = freeze(s3, fixture.request, root/'frozen', 'experiments/test-freeze/inputs', mib_per_second=50)
            self.assertEqual(result['status'], 'VERIFIED')
            self.assertFalse(result['preprocessing_executed'])
            self.assertFalse(result['all_five_stage_inputs_ready'])
            for identity, body in before.items():
                self.assertEqual(s3.objects[identity], body)
            for row in result['input_files']:
                shared = row['shared_uri'].removeprefix('s3a://pickage-curated/')
                self.assertEqual(Path(row['path']).read_bytes(), s3.objects[('pickage-curated', shared)])
            self.assertTrue((root/'frozen/raw-inputs.json').is_file())
            from pipeline.spark_experiment.frozen_raw_store import FrozenRawS3
            source = FrozenRawS3(root/'frozen/raw-inputs.json')
            row = next(r for r in result['input_files'] if r['bytes'] > 0)
            body = source.get_object(Bucket=row['bucket'], Key=row['key'])['Body']
            self.assertEqual(body.read(), Path(row['path']).read_bytes())
            body.close()
            original = Path(row['path']).read_bytes()
            Path(row['path']).write_bytes(bytes([original[0] ^ 1]) + original[1:])
            body = source.get_object(Bucket=row['bucket'], Key=row['key'])['Body']
            try:
                with self.assertRaisesRegex(ValueError, 'bytes changed'):
                    body.read()
            finally:
                body.close()

    def test_corrupt_copy_never_creates_ready_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = make_fixture(root/'fixture')
            def corrupt(**kwargs):
                fixture.s3.objects[(kwargs['Bucket'], kwargs['Key'])] = b'bad-copy'
            fixture.s3.copy_object = corrupt
            with self.assertRaisesRegex(ValueError, 'SHA/size'):
                freeze(fixture.s3, fixture.request, root/'frozen', 'experiments/corrupt-freeze/inputs', mib_per_second=50)
            self.assertFalse((root/'frozen/raw-inputs.json').exists())
            self.assertNotIn(('pickage-curated', 'experiments/corrupt-freeze/inputs/raw-inputs.json'), fixture.s3.objects)

    def test_reject_unsafe_object_key(self):
        for key in ['../x', '/x', 'a//b', 'a/./b', 'a\\b', 'a:secret']:
            with self.assertRaises(ValueError):
                safe_key(key)


if __name__ == '__main__':
    unittest.main()
