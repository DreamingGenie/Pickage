"""Isolated PostgreSQL partition publication experiment; never changes public tables."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import time
import uuid

from pipeline.postgresql.postgres import PgLoader
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical_artifact import _publish_json
from .historical_db_benchmark import COLUMNS, copy_into, prepare_input, relation, service_state

BODY = '(package_id integer NOT NULL,version varchar(100) NOT NULL,snapshot_at date NOT NULL,dependents_count integer NOT NULL DEFAULT 0 CONSTRAINT dependents_nonnegative CHECK(dependents_count>=0))'
COMMAND = ['docker','exec','-i','pickage-267-validation','psql','-U','postgres','-d','pickage_267_full_defaulted']


def scan_delta(before, after):
    if set(before)!=set(after):
        raise ValueError('Scan counter relations changed')
    return {name:{field:after[name][field]-value for field,value in counters.items()}
            for name,counters in before.items()}


def plan_relations(value):
    if isinstance(value,dict):
        names={value['Relation Name']} if 'Relation Name' in value else set()
        for child in value.values():names.update(plan_relations(child))
        return names
    if isinstance(value,list):
        return set().union(*(plan_relations(child) for child in value))
    return set()


class PartitionProbe:
    def __init__(self, db, schema, day, refs):
        relation(schema, 'parent')
        if refs not in (schema, 'public'):
            raise ValueError('References must be public or this fixture schema')
        self.db, self.schema, self.refs = db, schema, refs
        self.day = date.fromisoformat(day).isoformat()
        self.end = (date.fromisoformat(day)+timedelta(days=1)).isoformat()
        self.code_hash = file_sha256(Path(__file__))

    def table(self, name):
        return relation(self.schema, name)

    def scalar(self, sql):
        return self.db._send(sql)[0]

    def create(self):
        self.db._send(f'CREATE TABLE {self.table("parent")}{BODY} PARTITION BY RANGE(snapshot_at);')
        self.keys('parent')
        self.db._send(f'CREATE TABLE {self.table("journal")}(snapshot_at date PRIMARY KEY,input_sha text NOT NULL,code_sha text NOT NULL,child_oid oid NOT NULL,rows bigint NOT NULL,quality jsonb NOT NULL);')

    def keys(self, name):
        table = self.table(name)
        self.db._send(f'ALTER TABLE {table} ADD PRIMARY KEY(package_id,version,snapshot_at);')
        self.foreign_keys(name)

    def foreign_keys(self, name):
        self.db._send(f'ALTER TABLE {self.table(name)} ADD CONSTRAINT version_fk FOREIGN KEY(package_id,version) REFERENCES {self.refs}.version(package_id,version), ADD CONSTRAINT snapshot_fk FOREIGN KEY(snapshot_at) REFERENCES {self.refs}.snapshot(snapshot_at);')

    def verify(self, name='day_counts'):
        target, source = self.table(name), self.table('source')
        if self.scalar(f'SELECT count(*) FROM {target} t FULL JOIN {source} s USING(package_id,version,snapshot_at) WHERE t.package_id IS NULL OR s.package_id IS NULL OR t.dependents_count IS DISTINCT FROM s.dependents_count;') != '0':
            raise ValueError('Prepared/published values differ from pinned input')

    def constraints(self, name):
        rows=json.loads(self.scalar(f"SELECT coalesce(json_agg(json_build_object('oid',oid::bigint,'name',conname,'type',contype,'validated',convalidated,'parent',conparentid::bigint) ORDER BY oid),'[]') FROM pg_constraint WHERE conrelid='{self.table(name)}'::regclass;"))
        return rows

    def primary_index(self, name):
        return json.loads(self.scalar(f"SELECT json_build_object('oid',indexrelid::bigint,'valid',indisvalid,'filenode',pg_relation_filenode(indexrelid)) FROM pg_index WHERE indrelid='{self.table(name)}'::regclass AND indisprimary;"))

    def scan_counts(self):
        return json.loads(self.scalar(f"SELECT coalesce(json_object_agg(relname,json_build_object('seq_scan',seq_scan,'seq_tup_read',seq_tup_read,'idx_scan',coalesce(idx_scan,0),'idx_tup_fetch',coalesce(idx_tup_fetch,0))),'{{}}') FROM pg_stat_xact_user_tables WHERE (schemaname='{self.schema}' AND relname='day_counts') OR (schemaname='{self.refs}' AND relname IN ('version','snapshot'));"))

    def prepare(self, path, failpoint=None):
        metrics = {}
        started=time.perf_counter()
        self.db._send('BEGIN;')
        try:
            self.db._send(f"CREATE TABLE {self.table('day_counts')}{BODY}; ALTER TABLE {self.table('day_counts')} ADD CONSTRAINT date_bound CHECK(snapshot_at=DATE '{self.day}');")
            tick=time.perf_counter();copy_into(self.db,self.schema,'day_counts',path)
            metrics['copy_seconds']=time.perf_counter()-tick
            if failpoint=='after_copy':
                raise RuntimeError('injected after_copy')
            tick=time.perf_counter()
            self.db._send(f'ALTER TABLE {self.table("day_counts")} ADD PRIMARY KEY(package_id,version,snapshot_at);')
            metrics['pk_seconds']=time.perf_counter()-tick
            tick=time.perf_counter();self.foreign_keys('day_counts')
            metrics['fk_seconds']=time.perf_counter()-tick
            tick=time.perf_counter();self.verify()
            metrics['verify_seconds']=time.perf_counter()-tick
            self.db._send('COMMIT;')
            metrics['total_seconds']=time.perf_counter()-started
            return metrics
        except Exception:
            self.db._send('ROLLBACK;')
            raise

    def publish(self, input_sha, quality, failpoint=None, observer=None):
        if len(input_sha)!=64 or any(c not in '0123456789abcdef' for c in input_sha):
            raise ValueError('Invalid input hash')
        q=self.db._literal
        table,parent,journal=self.table('day_counts'),self.table('parent'),self.table('journal')
        metrics={}
        tick=time.perf_counter()
        self.db._send(f'BEGIN; LOCK TABLE {parent} IN SHARE UPDATE EXCLUSIVE MODE; LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE;')
        try:
            prior=json.loads(self.scalar(f"SELECT coalesce(json_agg(j),'[]') FROM {journal} j WHERE snapshot_at=DATE '{self.day}';"))
            if prior and (prior[0]['input_sha']!=input_sha or prior[0]['code_sha']!=self.code_hash or prior[0]['quality']!=quality):
                raise ValueError('Published input or generation contract differs')
            child_oid=int(self.scalar(f"SELECT '{table}'::regclass::oid;"))
            attached=self.scalar(f"SELECT count(*) FROM pg_inherits WHERE inhrelid='{table}'::regclass AND inhparent='{parent}'::regclass;")=='1'
            if bool(prior)!=attached:
                raise ValueError('Partition and publication receipt disagree')
            if prior and int(prior[0]['child_oid'])!=child_oid:
                raise ValueError('Published child identity changed')
            self.verify()
            constraints=self.constraints('day_counts')
            if sum(c['type']=='f' for c in constraints)!=2 or not all(c['validated'] for c in constraints):
                raise ValueError('Prepared constraints are not fully validated')
            rows=int(self.scalar(f'SELECT count(*) FROM {table};'))
            if prior and prior[0]['rows']!=rows:
                raise ValueError('Published row count differs')
            if prior:
                self.db._send('COMMIT;')
                return {'action':'REVERIFIED','inserted_rows':0,'child_oid':child_oid}
            before=self.scan_counts()
            pk_before=self.primary_index('day_counts')
            parent_constraints=self.constraints('parent')
            attach_tick=time.perf_counter()
            self.db._send(f"ALTER TABLE {parent} ATTACH PARTITION {table} FOR VALUES FROM ('{self.day}') TO ('{self.end}');")
            metrics['attach_seconds']=time.perf_counter()-attach_tick
            after=self.scan_counts()
            delta=scan_delta(before,after)
            if any(value!=0 for counters in delta.values() for value in counters.values()):
                raise ValueError('Additional data scan observed during attach')
            linked=self.constraints('day_counts')
            old_fk={c['oid'] for c in constraints if c['type']=='f'}
            new_fk={c['oid'] for c in linked if c['type']=='f' and c['validated'] and c['parent']!=0}
            if old_fk!=new_fk:
                raise ValueError('Attach did not reuse both validated foreign keys')
            parent_oids={c['oid'] for c in parent_constraints if c['type'] in ('f','p')}
            if {c['parent'] for c in linked if c['type'] in ('f','p')}!=parent_oids:
                raise ValueError('Child constraints did not attach to corresponding parent constraints')
            pk_after=self.primary_index('day_counts')
            if pk_before!=pk_after or not pk_after['valid']:
                raise ValueError('Primary index was rebuilt or is invalid')
            if self.scalar(f"SELECT count(*) FROM pg_inherits WHERE inhrelid={pk_after['oid']} AND inhparent={self.primary_index('parent')['oid']};")!='1':
                raise ValueError('Primary index is not attached to parent index')
            if observer:observer('after_attach')
            if failpoint=='after_attach':raise RuntimeError('injected after_attach')
            self.db._send(f"INSERT INTO {journal} VALUES(DATE '{self.day}',{q(input_sha)},{q(self.code_hash)},{child_oid},{rows},{q(quality)}::jsonb);")
            if observer:observer('before_commit')
            if failpoint=='before_commit':raise RuntimeError('injected before_commit')
            self.db._send('COMMIT;')
            metrics['publish_seconds']=time.perf_counter()-tick
            if failpoint=='after_commit':raise RuntimeError('injected lost_commit_response')
            return {'action':'PUBLISHED','rows':rows,'child_oid':child_oid,'metrics':metrics,'fk_oids_reused':True,'pk_oid_filenode_reused':True,'scans_before_attach':before,'scans_after_attach':after,'attach_scan_delta':delta}
        except Exception:
            self.db._send('ROLLBACK;')
            raise


def clean(db, schema):
    relation(schema,'parent')
    owner=db._send(f"SELECT nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_namespace WHERE nspname='{schema}';")
    if not owner:return
    if owner!=['t']:raise ValueError('Schema owner changed')
    # Explicit order, no CASCADE, and no service names are allowed.
    for name in ('overlap','day_counts','legacy','parent','journal','source','version','snapshot'):
        db._send(f'DROP TABLE IF EXISTS {relation(schema,name)};')
    db._send(f'DROP SCHEMA {schema};')


def run(output, input_dir=None, expected_metadata_sha=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    schema='vd193_bench_'+uuid.uuid4().hex
    fixture=input_dir is None
    if fixture:
        path=output/'counts.tsv';path.write_bytes(b'1\t1.0.0\t2023-03-06\t0\n2\t2.0.0\t2023-03-06\t7\n')
        receipt={'snapshot':'2023-03-06','file_sha256':file_sha256(path),'rows':2,'zeros':1,'sum':7}
    else:
        metadata_path=Path(input_dir)/'metadata.json'
        if not expected_metadata_sha or file_sha256(metadata_path)!=expected_metadata_sha:
            raise ValueError('Input metadata does not match independently pinned hash')
        metadata=json.loads(metadata_path.read_bytes())
        if sha256(metadata['manifest'])!=metadata['manifest_sha256']:
            raise ValueError('Input manifest hash differs')
        path,receipt=prepare_input(input_dir,output)
    quality=({'calculation_status':'COMPLETE','resolution_status':'PARTIAL'} if fixture else
             json.loads((Path(input_dir)/'metadata.json').read_bytes())['manifest']['quality'])
    plan={'schema':schema,'fixture':fixture,'input':receipt,'code_sha256':file_sha256(Path(__file__))}
    _publish_json(output/'plan.json',plan)
    checks=[]
    def event(message):
        print(json.dumps({'phase':message,'elapsed_seconds':round(time.perf_counter()-start,3)}),flush=True)
    with PgLoader(COMMAND,output) as db:
        before=service_state(db)
        for key in ('version-dependents','package-version'):
            if db._send(f"SELECT pg_try_advisory_lock(hashtextextended('curated:{key}',0));")!=['t']:
                raise ValueError('A service loader is active')
        if any(r['status']=='PREPARING' for r in before):raise ValueError('Service must be paused')
        db._send("SET application_name='vd193-partition-probe'; SET statement_timeout='15min';")
        try:
            db._send(f'CREATE SCHEMA {schema}; REVOKE ALL ON SCHEMA {schema} FROM PUBLIC;')
            p=PartitionProbe(db,schema,receipt['snapshot'],schema if fixture else 'public')
            if fixture:
                db._send(f"CREATE TABLE {schema}.version(package_id int,version varchar(100),PRIMARY KEY(package_id,version)); INSERT INTO {schema}.version VALUES(1,'1.0.0'),(2,'2.0.0'); CREATE TABLE {schema}.snapshot(snapshot_at date PRIMARY KEY); INSERT INTO {schema}.snapshot VALUES('2023-02-27'),('2023-03-06');")
            p.create()
            db._send(f'CREATE TABLE {p.table("source")}{BODY};')
            copy_into(db,schema,'source',path)
            db._send(f'ALTER TABLE {p.table("source")} ADD PRIMARY KEY(package_id,version,snapshot_at); ANALYZE {p.table("source")};')
            totals=json.loads(p.scalar(f"SELECT json_build_object('rows',count(*),'zeros',count(*) FILTER(WHERE dependents_count=0),'sum',sum(dependents_count)) FROM {p.table('source')};"))
            if any(totals[k]!=receipt[k] for k in ('rows','zeros','sum')):raise ValueError('Input totals differ')
            # Legacy conversion is deliberately small; public legacy rows are read only.
            db._send(f'CREATE TABLE {p.table("legacy")}{BODY};')
            if fixture:
                db._send(f"INSERT INTO {p.table('legacy')} VALUES(1,'1.0.0','2023-02-27',3);")
            else:
                db._send(f"INSERT INTO {p.table('legacy')} SELECT {COLUMNS} FROM public.package_version_snapshot WHERE snapshot_at=DATE '2023-02-27' ORDER BY package_id,version,snapshot_at LIMIT 1000;")
            p.keys('legacy')
            db._send(f"ALTER TABLE {p.table('legacy')} ADD CONSTRAINT legacy_bound CHECK(snapshot_at<DATE '{p.day}');")
            def legacy_identity():
                return p.scalar(f"SELECT json_build_object('oid','{p.table('legacy')}'::regclass::oid,'filenode',pg_relation_filenode('{p.table('legacy')}'),'rows',count(*),'sum',sum(dependents_count),'data',md5(string_agg(row(package_id,version,snapshot_at,dependents_count)::text,'|' ORDER BY package_id,version,snapshot_at))) FROM {p.table('legacy')};")
            legacy_before=legacy_identity()
            db._send(f"ALTER TABLE {p.table('parent')} ATTACH PARTITION {p.table('legacy')} FOR VALUES FROM (MINVALUE) TO ('{p.day}');")
            if legacy_before!=legacy_identity():raise ValueError('Legacy physical identity or values changed')
            checks.append('legacy_oid_filenode_values_preserved')
            event('LEGACY_ATTACHED')
            if fixture:
                try:p.prepare(path,'after_copy')
                except RuntimeError as error:
                    if 'injected' not in str(error):raise
                else:raise AssertionError('Prepare failpoint did not fire')
                if p.scalar(f"SELECT to_regclass('{p.table('day_counts')}') IS NULL;")!='t':raise AssertionError('Failed preparation survived')
                checks.append('preparation_rollback')
            prepared=p.prepare(path)
            event('DAY_PREPARED')
            def observe(_):
                actual=db._one_shot(f"SET statement_timeout='3s'; SELECT (SELECT count(*) FROM {p.table('parent')} WHERE snapshot_at=DATE '{p.day}'),(SELECT count(*) FROM {p.table('journal')});")
                if actual!='0|0':raise AssertionError('Uncommitted data or publication became visible')
            if fixture:
                for failpoint in ('after_attach','before_commit'):
                    try:p.publish(receipt['file_sha256'],quality,failpoint,observe)
                    except RuntimeError as error:
                        if 'injected' not in str(error):raise
                    else:raise AssertionError('Publish failpoint did not fire')
                    observe(None)
                    checks.append(failpoint+'_atomic_rollback')
                db._send(f"UPDATE {p.table('day_counts')} SET dependents_count=8 WHERE package_id=2;")
                try:p.publish(receipt['file_sha256'],quality)
                except ValueError:checks.append('prepared_value_tampering_rejected')
                else:raise AssertionError('Tampered prepared table accepted')
                db._send(f"UPDATE {p.table('day_counts')} SET dependents_count=7 WHERE package_id=2;")
            publication=p.publish(receipt['file_sha256'],quality,observer=observe)
            event('DAY_PUBLISHED')
            # A fresh connection/session observes committed publication and can reverify it.
            with PgLoader(COMMAND,output) as reconnect:
                fresh=PartitionProbe(reconnect,schema,p.day,p.refs)
                resumed=fresh.publish(receipt['file_sha256'],quality)
                if resumed['action']!='REVERIFIED' or resumed['inserted_rows']!=0:raise AssertionError('Resume inserted rows')
            checks.append('new_session_resume_without_reinsertion')
            if fixture:
                try:p.publish('f'*64,quality)
                except ValueError:checks.append('different_input_rejected')
                else:raise AssertionError('Different input accepted')
                def reject(sql, text):
                    try:db._one_shot('BEGIN; '+sql+'; ROLLBACK;')
                    except RuntimeError as error:
                        if text not in str(error):raise
                    else:raise AssertionError('Invalid SQL unexpectedly accepted: '+sql)
                for target in ('parent','day_counts'):
                    reject(f"INSERT INTO {p.table(target)} VALUES(99,'missing','{p.day}',0)",'foreign key')
                    reject(f"INSERT INTO {p.table(target)} VALUES(1,'1.0.0','{p.day}',0)",'duplicate key')
                    reject(f"UPDATE {p.table(target)} SET dependents_count=-1 WHERE snapshot_at='{p.day}'",'check constraint')
                    reject(f"UPDATE {p.table(target)} SET dependents_count=NULL WHERE snapshot_at='{p.day}'",'not-null')
                    reject(f"UPDATE {p.table(target)} SET dependents_count=2147483648 WHERE snapshot_at='{p.day}'",'out of range')
                reject(f"INSERT INTO {p.table('day_counts')} VALUES(2,'2.0.0','2023-02-27',0)",'check constraint')
                reject(f"DELETE FROM {schema}.version WHERE package_id=2",'foreign key')
                reject(f"UPDATE {schema}.version SET version='changed' WHERE package_id=2",'foreign key')
                reject(f"DELETE FROM {schema}.snapshot WHERE snapshot_at='{p.day}'",'foreign key')
                db._send(f'CREATE TABLE {p.table("overlap")}{BODY};')
                reject(f"ALTER TABLE {p.table('parent')} ATTACH PARTITION {p.table('overlap')} FOR VALUES FROM ('{p.day}') TO ('{p.end}')",'overlap')
                checks.extend(['parent_child_fk_pk_value_constraints','reference_delete_update_rejected','overlap_rejected'])
                # Simulate COMMIT success whose response the client lost.
                db._send(f"BEGIN; ALTER TABLE {p.table('parent')} DETACH PARTITION {p.table('day_counts')}; DELETE FROM {p.table('journal')}; COMMIT;")
                try:p.publish(receipt['file_sha256'],quality,'after_commit')
                except RuntimeError as error:
                    if 'lost_commit_response' not in str(error):raise
                else:raise AssertionError('Lost response failpoint did not fire')
                if p.publish(receipt['file_sha256'],quality)['inserted_rows']!=0:raise AssertionError('Reinserted after lost response')
                checks.append('lost_commit_response_resume')
            # Exact published values through the parent, including zeros and legacy preservation.
            if p.scalar(f"SELECT count(*) FROM {p.table('source')} s FULL JOIN (SELECT * FROM {p.table('parent')} WHERE snapshot_at=DATE '{p.day}') t USING(package_id,version,snapshot_at) WHERE s.package_id IS NULL OR t.package_id IS NULL OR s.dependents_count IS DISTINCT FROM t.dependents_count;")!='0':raise AssertionError('Parent values differ')
            if legacy_identity()!=legacy_before:raise AssertionError('Legacy rows changed')
            pruning=json.loads('\n'.join(db._send(f"EXPLAIN(FORMAT JSON) SELECT count(*) FROM {p.table('parent')} WHERE snapshot_at=DATE '{p.day}';")))
            if plan_relations(pruning)!={'day_counts'}:raise AssertionError('Unexpected partition in date query plan')
            if service_state(db)!=before:raise AssertionError('Service history changed')
            if file_sha256(path)!=receipt['file_sha256']:raise AssertionError('Source file changed')
            report={'status':'COMPLETE','plan':plan,'prepared':prepared,'publication':publication,'checks':checks,'published_exact_match':True,'legacy_unchanged':True,'service_history_unchanged':True,'date_query_plan':pruning,'total_seconds_before_cleanup':time.perf_counter()-start}
        finally:
            try:
                db._send('ROLLBACK;');clean(db,schema)
            except RuntimeError:
                with PgLoader(COMMAND,output) as recovery:
                    recovery._send("SET statement_timeout='30s';");clean(recovery,schema)
        report['cleanup_complete']=True
        report['total_seconds']=time.perf_counter()-start
        _publish_json(output/'result.json',report)
        event('COMPLETE')
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--input-dir')
    parser.add_argument('--expected-metadata-sha256')
    args=parser.parse_args()
    run(args.output,args.input_dir,args.expected_metadata_sha256)


if __name__=='__main__':main()
