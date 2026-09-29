"""Contract tests using small real Parquet inputs."""
from pathlib import Path
import tempfile, unittest, duckdb
from pipeline.preprocessing.downloads_interval.aggregate import aggregate
HASHES={k:'a'*64 for k in ('input_manifest_sha256','policy_sha256','aggregation_policy_sha256')}
def parquet(path,ddl,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with duckdb.connect() as c:
        c.execute(ddl)
        if rows:c.executemany('INSERT INTO x VALUES ('+','.join('?' for _ in rows[0])+')',rows)
        c.execute('COPY x TO ? (FORMAT PARQUET)',[str(path)])
def fixture(root,package_rows=((1,'a','r'),(2,'b','r')),target=('a','b'),statuses=None,daily=None,previous='2026-08-24',snapshot='2026-08-27',available=('2026-08-24','2026-08-26')):
    pkg=root/'packages.parquet';parquet(pkg,'CREATE TABLE x(package_id INTEGER,name VARCHAR,repo_url VARCHAR)',list(package_rows)); t=root/'target.csv';t.write_text('name\n'+'\n'.join(target)+'\n',encoding='utf8')
    if statuses is None:statuses=[(n,'READY') for n in dict.fromkeys(target)]
    sf=root/'status.parquet';parquet(sf,'CREATE TABLE x(name VARCHAR,status VARCHAR)',list(statuses)); dfs=[]
    for day,rows in (daily or {}).items():
        p=root/f'date={day}'/'part.parquet';parquet(p,'CREATE TABLE x(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN)',rows);dfs.append(str(p))
    return {'package_files':[str(pkg)],'daily_files':dfs,'target_file':str(t),'status_file':str(sf),'interval':{'snapshot_at':snapshot,'previous_snapshot_at':previous},'available_start':available[0],'available_end':available[1],'lineage':HASHES}
class AggregateContractTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def run_case(self,**kw):return aggregate(fixture(self.root,**kw),self.root/'out')
    def rows(self):
        with duckdb.connect() as c:return c.execute('SELECT * FROM read_parquet(?) ORDER BY package_id',[str(self.root/'out/interval_downloads.parquet')]).fetchall()
    def test_complete_nonzero(self):
        self.run_case(daily={d:[('a',2,False),('b',4,False)] for d in ('2026-08-24','2026-08-25','2026-08-26')});self.assertEqual([r[3] for r in self.rows()],[6,12])
        self.assertEqual(self.rows()[0][4:10], (3,3,3,'COMPLETE',None,[]))
    def test_complete_zero(self):
        self.run_case(daily={d:[('a',0,False),('b',0,False)] for d in ('2026-08-24','2026-08-25','2026-08-26')});self.assertEqual(self.rows()[0][3],0)
        self.assertEqual(self.rows()[0][7], 'COMPLETE')
    def test_partial_zero(self):
        self.run_case(daily={'2026-08-24':[('a',0,False)]});self.assertEqual(self.rows()[0][3],0)
        self.assertEqual(self.rows()[0][4:9], (3,1,1,'PARTIAL',None))
        self.assertEqual(self.rows()[0][9], ['MISSING_DAILY_VALUES','ROW_MISSING'])
    def test_null_gap_and_missing(self):
        self.run_case(daily={'2026-08-24':[('a',None,False)],'2026-08-25':[('a',None,True)]});self.assertEqual(self.rows()[0][3],None)
        self.assertEqual(self.rows()[0][4:9], (3,2,0,'UNAVAILABLE','MISSING_DAILY_VALUES'))
        self.assertEqual(self.rows()[0][9], ['MISSING_DAILY_VALUES','ROW_MISSING','NULL_VALUE','IMPUTED_GAP'])
        with duckdb.connect() as c:
            reasons = c.execute("SELECT reason FROM read_parquet(?) WHERE name='a' AND date=DATE '2026-08-25' ORDER BY reason", [str(self.root/'out/daily_quality.parquet')]).fetchall()
        self.assertEqual(reasons, [('IMPUTED_GAP',),('NULL_VALUE',)])
    def test_first_snapshot(self):
        self.run_case(previous=None,daily={});self.assertIsNone(self.rows()[0][3])
        self.assertEqual(self.rows()[0][4:10], (None,0,0,'UNAVAILABLE','NO_PREVIOUS_SNAPSHOT',['NO_PREVIOUS_SNAPSHOT']))
    def test_partial_overlap(self):
        self.run_case(daily={'2026-08-25':[('a',2,False)]},available=('2026-08-25','2026-08-26'))
        self.assertEqual(self.rows()[0][3:9], (2,3,1,1,'PARTIAL',None))
        self.assertIn('OUTSIDE_AVAILABLE_RANGE', self.rows()[0][9])
    def test_total_nonoverlap(self):
        self.run_case(daily={},available=('2026-09-01','2026-09-02'))
        self.assertEqual(self.rows()[0][3:9], (None,3,0,0,'UNAVAILABLE','OUTSIDE_AVAILABLE_RANGE'))
    def test_outside_population(self):self.run_case(package_rows=((1,'a','r'),),target=('a','b'),statuses=(('a','READY'),('b','READY')))
    def test_unmatched_target_report(self):
        self.run_case(package_rows=((1,'a','r'),),target=('a','b'),statuses=(('a','READY'),('b','READY')));self.assertTrue((self.root/'out/unmatched_packages.parquet').exists())
        with duckdb.connect() as c:
            rows = c.execute('SELECT * FROM read_parquet(?)', [str(self.root/'out/unmatched_packages.parquet')]).fetchall()
        self.assertEqual(rows, [('b','READY',0,'TARGET_NOT_IN_APPROVED_POPULATION')])
    def test_duplicate_target_dedup(self):self.assertEqual(self.run_case(target=('a','a','b'))['quality']['target_duplicate_rows'],1)
    def test_status_set_mismatch(self):
        with self.assertRaises(ValueError):self.run_case(statuses=(('a','READY'),))
    def test_null_or_unknown_status(self):
        with self.assertRaises(ValueError):self.run_case(statuses=(('a',None),('b','READY')))
        with self.assertRaises(ValueError):self.run_case(statuses=(('a','OTHER'),('b','READY')))
    def test_unknown_daily_name(self):
        with self.assertRaises(ValueError):self.run_case(daily={'2026-08-24':[('x',1,False)]})
    def test_not_found_daily(self):
        with self.assertRaises(ValueError):self.run_case(statuses=(('a','NOT_FOUND'),('b','READY')),daily={'2026-08-24':[('a',1,False)]})
    def test_duplicate_daily(self):
        with self.assertRaises(ValueError):self.run_case(daily={'2026-08-24':[('a',1,False),('a',2,False)]})
    def test_negative_daily(self):
        with self.assertRaises(ValueError):self.run_case(daily={'2026-08-24':[('a',-1,False)]})
    def test_overflow_sum(self):
        with self.assertRaises(ValueError):self.run_case(daily={'2026-08-24':[('a',9223372036854775807,False)],'2026-08-25':[('a',1,False)]})
    def test_physical_hive_mismatch(self):
        prep=fixture(self.root,daily={'2026-08-24':[('a',1,False)]})
        with duckdb.connect() as c:
            c.execute("CREATE TABLE x(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN,date DATE)");c.execute("INSERT INTO x VALUES ('a',1,false,'2026-08-25')");c.execute('COPY x TO ? (FORMAT PARQUET)',[prep['daily_files'][0]])
        with self.assertRaises(ValueError):aggregate(prep,self.root/'out2')
    def test_expected_rows_mismatch(self):
        prep=fixture(self.root);prep['expected_package_rows']=999
        with self.assertRaises(ValueError):aggregate(prep,self.root/'out2')
    def test_outside_target_row_retained(self):
        self.run_case(target=('a',),daily={'2026-08-24':[('a',3,False)]})
        self.assertEqual(len(self.rows()),2)
        self.assertEqual(self.rows()[1][3:10], (None,3,0,0,'UNAVAILABLE','OUTSIDE_TARGET_LIST',['OUTSIDE_TARGET_LIST']))
    def test_null_gap_flag_rejected(self):
        with self.assertRaisesRegex(ValueError,'NULL imputed_gap'):
            self.run_case(daily={'2026-08-24':[('a',3,None)]})
    def test_extra_status_rejected(self):
        with self.assertRaisesRegex(ValueError,'name sets differ'):
            self.run_case(statuses=(('a','READY'),('b','READY'),('x','READY')))
    def test_duplicate_package_id_and_name_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate package ID'):
            self.run_case(package_rows=((1,'a','r'),(1,'b','r')))
        with self.assertRaisesRegex(ValueError,'duplicate package name'):
            self.run_case(package_rows=((1,'a','r'),(2,'a','r')))
    def test_duplicate_daily_across_files_rejected(self):
        prep=fixture(self.root,daily={'2026-08-24':[('a',1,False)]})
        other=self.root/'date=2026-08-24'/'other.parquet'
        other.write_bytes(Path(prep['daily_files'][0]).read_bytes())
        prep['daily_files'].append(str(other))
        with self.assertRaisesRegex(ValueError,'duplicate daily'):
            aggregate(prep,self.root/'out')
    def test_exclusive_end_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            self.run_case(daily={'2026-08-27':[('a',2,False)]},available=('2026-08-24','2026-08-27'))
if __name__=='__main__':unittest.main()
