"""Read the actual pinned output format and reject corrupt serving inputs."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from botocore.exceptions import ClientError
import duckdb

from pipeline.curated.storage import json_bytes
from . import load


class S3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        return {'Body': io.BytesIO(self.objects[Key]), 'ETag': 'fixture'}


class LoadInputTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.s3 = S3()
        self.prefix = 'depsdev/v1/package-snapshot/snapshot=2026-08-31/run_id=fixture'
        interval = {'snapshot_at': '2026-08-31', 'snapshot_timestamp': '2026-08-31T21:01:10.517131Z'}
        inputs = {'interval': interval}
        self.manifest = {'dataset': 'package-snapshot', 'status': 'PASSED', 'format_version': 1,
            'snapshot': '2026-08-31', 'run_id': 'fixture', 'snapshot_timestamp': interval['snapshot_timestamp'],
            'interval': interval, 'input_manifest': inputs,
            'input_manifest_sha256': hashlib.sha256(json_bytes(inputs)).hexdigest(),
            'policy': {}, 'policy_sha256': hashlib.sha256(json_bytes({})).hexdigest(),
            'contract_sha256': 'a' * 64, 'counts': {'package_snapshot': 3},
            'required_remote_verification': 'GET_SHA256_ALL_FILES', 'files': []}
        self.service_sql = "CREATE TABLE src(package_id INT,snapshot_at DATE,downloads BIGINT,stars INT,open_issues INT); INSERT INTO src VALUES (1,'2026-08-31',12,0,NULL),(2,'2026-08-31',0,NULL,4),(3,'2026-08-31',NULL,10,0)"
        self.output('package_snapshot', self.service_sql)
        self.output('package_identity', "CREATE TABLE src(package_id INT,name VARCHAR); INSERT INTO src VALUES (1,'alpha'),(2,'beta'),(3,'gamma')")
        self.quality_sql = "CREATE TABLE src(package_id INT,snapshot_at DATE,download_sum BIGINT,data_status VARCHAR,expected_days INT,observed_days INT,valid_days INT,null_reason VARCHAR,quality_reasons VARCHAR[],repository_reason VARCHAR,repository_mapping_status VARCHAR); INSERT INTO src VALUES (1,'2026-08-31',12,'PARTIAL',7,7,6,NULL,['GAP'],'SELECTED','SELECTED'),(2,'2026-08-31',0,'COMPLETE',7,7,7,NULL,[],'SELECTED','SELECTED'),(3,'2026-08-31',NULL,'UNAVAILABLE',7,0,0,'OUTSIDE_TARGET_LIST',[],'SELECTED','SELECTED')"
        self.output('quality', self.quality_sql)

    def output(self, role, sql):
        path = self.root / (role + '.parquet')
        if path.exists():
            path.unlink()
        with duckdb.connect() as con:
            con.execute(sql)
            count = con.execute('SELECT count(*) FROM src').fetchone()[0]
            con.execute('COPY src TO ? (FORMAT PARQUET)', [str(path)])
        body = path.read_bytes()
        self.s3.objects[self.prefix + '/data/' + path.name] = body
        rec = {'path': path.name, 'role': role, 'bytes': len(body),
               'sha256': hashlib.sha256(body).hexdigest(), 'row_count': count}
        self.manifest['files'] = [r for r in self.manifest['files'] if r['role'] != role] + [rec]

    def select(self):
        body = json_bytes(self.manifest)
        sha = hashlib.sha256(body).hexdigest()
        self.s3.objects[self.prefix + '/run_manifest.json'] = body
        self.s3.objects[self.prefix + '/_SUCCESS'] = (sha + '\n').encode()
        self.s3.objects[self.prefix + '/_INPUT.json'] = json_bytes({'manifest_sha256': sha})
        return load.select_run(self.s3, '2026-08-31', 'fixture', sha)

    def prepare(self):
        return load.prepare(self.s3, self.select(), self.root, memory='256MB', threads=1)

    def test_partial_zero_and_independent_null_copy(self):
        result = self.prepare()
        self.assertEqual(result['validation']['nonnull'], {'downloads': 2, 'stars': 2, 'open_issues': 2})
        self.assertEqual((self.root / 'package_snapshot.copy.tsv').read_bytes(),
                         b'1\t2026-08-31\t12\t0\t\\N\n2\t2026-08-31\t0\t\\N\t4\n3\t2026-08-31\t\\N\t10\t0\n')

    def test_copy_escapes_control_line_and_tabs(self):
        self.output('package_identity', "CREATE TABLE src(package_id INT,name VARCHAR); INSERT INTO src VALUES (1,chr(92)||'.'||chr(10)||'x'||chr(9)||'z'),(2,'beta'),(3,'gamma')")
        self.prepare()
        body = (self.root / 'package_identity.copy.tsv').read_bytes()
        self.assertIn(b'1\t\\\\.\\nx\\tz\n', body)
        self.assertNotIn(b'\n\\.\n', body)

    def test_corrupted_remote_file_rejected(self):
        m = self.select()
        self.s3.objects[self.prefix + '/data/package_snapshot.parquet'] += b'corruption'
        with self.assertRaises(ValueError):
            load.prepare(self.s3, m, self.root)

    def test_marker_required(self):
        m = self.select()
        self.s3.objects.pop(self.prefix + '/_SUCCESS')
        with self.assertRaises(ValueError):
            load.select_run(self.s3, '2026-08-31', 'fixture', m['manifest_sha256'])

    def test_manifest_hash_required(self):
        self.select()
        with self.assertRaises(ValueError):
            load.select_run(self.s3, '2026-08-31', 'fixture', '0' * 64)

    def test_unsafe_output_and_missing_role(self):
        original = copy.deepcopy(self.manifest)
        for path in ('../bad.parquet', '/bad.parquet', 'x*.parquet', 'x\\y.parquet'):
            with self.subTest(path=path):
                self.manifest = copy.deepcopy(original)
                self.manifest['files'][0]['path'] = path
                with self.assertRaises(ValueError):
                    self.select()
        self.manifest = original
        self.manifest['files'].pop()
        with self.assertRaises(ValueError):
            self.select()

    def test_duplicate_negative_wrong_date_and_wrong_schema(self):
        for suffix in ("UPDATE src SET package_id=1 WHERE package_id=2",
                       "UPDATE src SET downloads=-1 WHERE package_id=1",
                       "UPDATE src SET snapshot_at='2026-08-30' WHERE package_id=1",
                       'ALTER TABLE src ALTER COLUMN stars TYPE BIGINT'):
            with self.subTest(suffix=suffix):
                self.output('package_snapshot', self.service_sql + ';' + suffix)
                # A fresh cache allows each independently pinned bad fixture to reach its semantic check.
                work = self.root / hashlib.sha256(suffix.encode()).hexdigest()
                work.mkdir()
                with self.assertRaises(ValueError):
                    load.prepare(self.s3, self.select(), work, memory='256MB', threads=1)

    def test_quality_key_or_value_mismatch(self):
        for suffix in ('UPDATE src SET package_id=9 WHERE package_id=1',
                       'UPDATE src SET download_sum=13 WHERE package_id=1',
                       "UPDATE src SET data_status='COMPLETE' WHERE package_id=1"):
            with self.subTest(suffix=suffix):
                self.output('quality', self.quality_sql + ';' + suffix)
                work = self.root / hashlib.sha256(suffix.encode()).hexdigest()
                work.mkdir()
                with self.assertRaises(ValueError):
                    load.prepare(self.s3, self.select(), work, memory='256MB', threads=1)

    def test_changed_completion_blocks_precommit(self):
        metadata = self.select()
        self.s3.objects[self.prefix + '/_SUCCESS'] = b'changed\n'
        with self.assertRaises(ValueError):
            load.revalidate(self.s3, metadata)


if __name__ == '__main__':
    unittest.main()
