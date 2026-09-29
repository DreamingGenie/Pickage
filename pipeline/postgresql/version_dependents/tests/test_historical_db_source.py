import tempfile
import unittest
from pathlib import Path
import duckdb
from pipeline.postgresql.version_dependents.historical_db_source import copy_text, dense_date


class HistoricalDbSourceTests(unittest.TestCase):
    def setUp(self):
        self.c = duckdb.connect()
        self.c.execute('CREATE TABLE targets(package_id INTEGER,name VARCHAR,version VARCHAR,birth_index INTEGER)')
        self.c.execute("INSERT INTO targets VALUES(1,'alpha','1.0.0',0),(1,'alpha','2.0.0',1),(2,'beta','1.0.0',0)")
        self.c.execute('CREATE TABLE counts(package_id INTEGER,version VARCHAR,snapshot_at DATE,snapshot_timestamp TIMESTAMPTZ,dependents_count BIGINT)')
        self.c.execute("INSERT INTO counts VALUES(1,'1.0.0','2026-08-30','2026-08-30T21:00:00Z',3)")

    def tearDown(self):
        self.c.close()

    def calculate(self):
        return dense_date(self.c,0,'2026-08-30','2026-08-30T21:00:00Z')

    def test_zero_restoration_excludes_future_versions(self):
        self.assertEqual(self.calculate(), {'target_versions':2,'positive_target_versions':1,
            'zero_target_versions':1,'distinct_edges':3,'max_dependents_count':3})
        self.assertEqual(self.c.execute('select package_id,version,dependents_count from day_counts order by package_id').fetchall(),
                         [(1,'1.0.0',3),(2,'1.0.0',0)])

    def test_invalid_positive_rejected(self):
        for expression in ('NULL','0','-1','2147483648'):
            with self.subTest(expression=expression):
                self.c.execute('update counts set dependents_count='+expression)
                with self.assertRaises(ValueError): self.calculate()

    def test_duplicate_future_unknown_and_wrong_time_rejected(self):
        self.c.execute('insert into counts select * from counts')
        with self.assertRaises(ValueError): self.calculate()
        self.c.execute('delete from counts')
        for version,stamp in [('2.0.0','2026-08-30T21:00:00Z'),('3.0.0','2026-08-30T21:00:00Z'),('1.0.0','2026-08-30T22:00:00Z')]:
            self.c.execute('delete from counts')
            self.c.execute("insert into counts values(1,?,'2026-08-30',?,3)",[version,stamp])
            with self.assertRaises(ValueError): self.calculate()

    def test_copy_text_escapes_delimiters_and_literal_null(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'copy.tsv'
            self.c.execute('create table escaped(name varchar,value int)')
            self.c.execute('insert into escaped values (?,0)', ['a\\b\t\n\r\\N'])
            copy_text(self.c,'select * from escaped',('name','value'),path)
            self.assertEqual(path.read_bytes(),b'a\\\\b\\t\\n\\r\\\\N\t0\n')


if __name__ == '__main__':
    unittest.main()
