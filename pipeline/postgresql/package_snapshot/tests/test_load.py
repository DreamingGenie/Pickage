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

from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.postgresql.package_snapshot import load
from pipeline.preprocessing.package_snapshot.quality import QUALITY_SCHEMA_ID


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
        # Exact legacy observed producer schema, rather than a reduced mock format.
        self.quality_sql = """CREATE TABLE src AS SELECT id::INTEGER package_id,name,
            DATE '2026-08-31' snapshot_at,DATE '2026-08-24' previous_snapshot_at,
            downloads::BIGINT download_sum,7::INTEGER expected_days,observed::INTEGER observed_days,
            valid::INTEGER valid_days,status data_status,reason null_reason,['GAP'] quality_reasons,
            repeat('a',64) input_manifest_sha256,repeat('b',64) policy_sha256,
            repeat('c',64) aggregation_policy_sha256,'1.0.0' repository_version,
            1::BIGINT repository_ordinal,'https://github.com/org/repo' repository_repo_url,
            'github.com' repository_provider,'org/repo' repository_project_path,
            'org/repo' repository_comparison_project_path,'org/repo' repository_observed_project_path,
            '2026-08-31' repository_snapshot,'2026-08-31T21:01:10.517131Z' repository_snapshot_timestamp,
            TIMESTAMPTZ '2026-08-31T21:01:10.517131Z' repository_observed_timestamp,
            'SELECTED' repository_reason,'MATCHED' repository_mapping_status
            FROM (VALUES (1,'alpha',12,7,6,'PARTIAL',NULL),
                         (2,'beta',0,7,7,'COMPLETE',NULL),
                         (3,'gamma',NULL,0,0,'UNAVAILABLE','OUTSIDE_TARGET_LIST'))
                 AS rows(id,name,downloads,observed,valid,status,reason)"""
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
        self.output('quality', self.quality_sql + ";UPDATE src SET name=chr(92)||'.'||chr(10)||'x'||chr(9)||'z' WHERE package_id=1")
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
                       "UPDATE src SET data_status='COMPLETE' WHERE package_id=1",
                       "UPDATE src SET repository_mapping_status='wrong' WHERE package_id=1",
                       "UPDATE src SET valid_days=NULL WHERE package_id=1",
                       "UPDATE src SET name='wrong' WHERE package_id=1"):
            with self.subTest(suffix=suffix):
                self.output('quality', self.quality_sql + ';' + suffix)
                work = self.root / hashlib.sha256(suffix.encode()).hexdigest()
                work.mkdir()
                with self.assertRaises(ValueError):
                    load.prepare(self.s3, self.select(), work, memory='256MB', threads=1)

    def test_unknown_quality_version_and_mislabeled_legacy_schema_rejected(self):
        for marker in ('package-snapshot-quality-v999', QUALITY_SCHEMA_ID):
            with self.subTest(marker=marker):
                self.manifest['quality_schema'] = marker
                with self.assertRaisesRegex(ValueError, 'quality schema'):
                    self.prepare()

    def test_legacy_schema_missing_or_wrong_typed_column_rejected(self):
        for suffix in ('ALTER TABLE src DROP COLUMN repository_mapping_status',
                       'ALTER TABLE src ALTER COLUMN valid_days TYPE VARCHAR'):
            with self.subTest(suffix=suffix):
                self.output('quality', self.quality_sql + ';' + suffix)
                with self.assertRaisesRegex(ValueError, 'quality schema'):
                    self.prepare()

    def test_observed_quality_cannot_claim_reconstructed_publication_dates(self):
        current_sql = self.quality_sql + ";ALTER TABLE src RENAME TO legacy;" + """
            CREATE TABLE src AS SELECT q.*,m.stars::INTEGER stars,m.open_issues::INTEGER open_issues,
            NULL::TIMESTAMPTZ first_published_at,NULL::TIMESTAMPTZ selected_published_at
            FROM legacy q JOIN (VALUES (1,0,NULL),(2,NULL,4),(3,10,0))
            AS m(package_id,stars,open_issues) USING(package_id)"""
        self.manifest['quality_schema'] = QUALITY_SCHEMA_ID
        for column in ('first_published_at', 'selected_published_at'):
            with self.subTest(column=column):
                self.output('quality', current_sql +
                            f";UPDATE src SET {column}=TIMESTAMPTZ '2024-01-01T00:00:00Z' WHERE package_id=1")
                with self.assertRaisesRegex(ValueError, 'quality values disagree'):
                    self.prepare()

    def test_changed_completion_blocks_precommit(self):
        metadata = self.select()
        self.s3.objects[self.prefix + '/_SUCCESS'] = b'changed\n'
        with self.assertRaises(ValueError):
            load.revalidate(self.s3, metadata)


if __name__ == '__main__':
    unittest.main()
