"""Frozen old history files remain readable without rewriting their approved bytes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import duckdb

from pipeline.postgresql.package_snapshot.history_load import prepare_copy
from pipeline.preprocessing.package_snapshot.quality import COMMON_SCHEMA, HISTORY_FIELDS, QUALITY_SCHEMA_ID, normalize_quality, validate_quality


class LegacyHistoryQualityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = {role: str(self.root / (role + '.parquet'))
                      for role in ('package_snapshot', 'package_identity', 'quality')}
        self.manifest = {'snapshot': '2025-12-31', 'counts': {'package_snapshot': 2},
                         'interval': {'snapshot_timestamp': '2025-12-31T21:00:00Z',
                                      'previous_snapshot_at': '2025-12-29', 'interval_days': 2}}
        with duckdb.connect() as con:
            con.execute("""CREATE TABLE package_snapshot(package_id INTEGER,snapshot_at DATE,
                downloads BIGINT,stars INTEGER,open_issues INTEGER);
                INSERT INTO package_snapshot VALUES (1,'2025-12-31',10,3,1),(2,'2025-12-31',0,NULL,NULL);
                CREATE TABLE package_identity(package_id INTEGER,name VARCHAR);
                INSERT INTO package_identity VALUES (1,'alpha'),(2,'beta');
                CREATE TABLE quality(package_id INTEGER,snapshot_at DATE,first_published_at TIMESTAMPTZ,
                selected_published_at TIMESTAMPTZ,download_sum BIGINT,stars INTEGER,open_issues INTEGER,
                data_status VARCHAR,expected_days INTEGER,observed_days INTEGER,valid_days INTEGER,
                null_reason VARCHAR,quality_reasons VARCHAR[],repository_reason VARCHAR,repo_url VARCHAR,
                selected_version VARCHAR,observed_timestamp TIMESTAMPTZ);
                INSERT INTO quality VALUES
                (1,'2025-12-31','2024-01-01T00:00:00Z','2024-01-01T00:00:00Z',10,3,1,'PARTIAL',2,2,1,NULL,
                 ['IMPUTED_GAP'],'SELECTED','https://github.com/Org/Repo','1.0','2025-12-31T21:00:00Z'),
                (2,'2025-12-31','2024-01-01T00:00:00Z',NULL,0,NULL,NULL,'COMPLETE',2,2,2,NULL,
                 [],'NO_VALID_REPOSITORY',NULL,NULL,NULL)""")
            for role, path in self.files.items():
                con.execute('COPY ' + role + ' TO ? (FORMAT PARQUET)', [path])

    def views(self, con):
        con.execute("SET TimeZone='UTC'")
        for role, path in self.files.items():
            view = 'quality_raw' if role == 'quality' else role
            con.execute('CREATE TEMP TABLE ' + view + ' AS SELECT * FROM read_parquet(?)', [path])

    def test_legacy_history_revalidation_preserves_files_and_service_values(self):
        before = {role: Path(path).read_bytes() for role, path in self.files.items()}
        with duckdb.connect() as con:
            self.views(con)
            normalize_quality(con, self.manifest, producer='history')
            validate_quality(con, self.manifest, producer='history')
            schema = [(row[0], row[1]) for row in con.execute('DESCRIBE quality').fetchall()]
            self.assertEqual(schema, COMMON_SCHEMA + HISTORY_FIELDS)
            values = con.execute('SELECT name,repository_version,repository_mapping_status '
                                 'FROM quality ORDER BY package_id').fetchall()
            self.assertEqual(values, [('alpha', '1.0', 'MATCHED'), ('beta', None, 'NO_SELECTED_REPOSITORY')])
            self.assertEqual(con.execute('SELECT count(input_manifest_sha256),count(repository_ordinal) '
                                         'FROM quality').fetchone(), (0, 0))
        copied = prepare_copy(self.files, self.manifest, self.root / 'copy', memory='256MB', threads=1)
        self.assertEqual(copied['validation']['rows'], 2)
        self.assertEqual((self.root / 'copy/package_snapshot.copy.tsv').read_bytes(),
                         b'1\t2025-12-31\t10\t3\t1\n2\t2025-12-31\t0\t\\N\t\\N\n')
        self.assertEqual(before, {role: Path(path).read_bytes() for role, path in self.files.items()})

    def test_new_history_schema_rejects_common_field_corruption(self):
        # Normalize the frozen legacy fixture once to exercise the new reader path.
        with duckdb.connect() as con:
            self.views(con)
            normalize_quality(con, self.manifest, producer='history')
            good = self.root / 'v2.parquet'
            con.execute('COPY quality TO ? (FORMAT PARQUET)', [str(good)])
        manifest = {**self.manifest, 'quality_schema': QUALITY_SCHEMA_ID}
        for index, statement in enumerate((
                "UPDATE bad SET repository_mapping_status='wrong' WHERE package_id=1",
                'UPDATE bad SET stars=300 WHERE package_id=1',
                "UPDATE bad SET data_status='COMPLETE' WHERE package_id=1",
                "UPDATE bad SET name='wrong' WHERE package_id=1",
                "UPDATE bad SET selected_published_at=TIMESTAMPTZ '2026-01-01T00:00:00Z' WHERE package_id=1",
                'ALTER TABLE bad DROP COLUMN repository_version',
                'ALTER TABLE bad ALTER COLUMN observed_days TYPE VARCHAR')):
            with self.subTest(statement=statement), duckdb.connect() as con:
                con.execute('CREATE TABLE bad AS SELECT * FROM read_parquet(?)', [str(good)])
                con.execute(statement)
                path = self.root / f'bad-{index}.parquet'
                con.execute('COPY bad TO ? (FORMAT PARQUET)', [str(path)])
                with self.assertRaises(ValueError):
                    prepare_copy({**self.files, 'quality': str(path)}, manifest,
                                 self.root / f'copy-{index}', memory='256MB', threads=1)

    def test_unknown_schema_and_incorrect_producer_rejected(self):
        manifest = deepcopy(self.manifest)
        manifest['quality_schema'] = 'package-snapshot-quality-v999'
        with self.assertRaisesRegex(ValueError, 'unsupported quality schema'):
            prepare_copy(self.files, manifest, self.root / 'unsupported', memory='256MB', threads=1)
        with duckdb.connect() as con:
            self.views(con)
            with self.assertRaisesRegex(ValueError, 'quality schema mismatch'):
                normalize_quality(con, self.manifest, producer='observed')


if __name__ == '__main__':
    unittest.main()
