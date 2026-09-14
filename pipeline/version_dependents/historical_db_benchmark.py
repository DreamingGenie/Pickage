"""Isolated write benchmarks against real reference tables; never publishes service rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time
import uuid

import duckdb
from pipeline.postgresql.postgres import PgLoader
from pipeline.requirements_resolution.input import file_sha256
from .historical_db_source import copy_text
from .historical_artifact import _publish_json

MODES = ('insert_pk_fk', 'insert_pk_only', 'copy_pk_fk', 'copy_then_constraints')
COLUMNS = 'package_id,version,snapshot_at,dependents_count'


def relation(schema, name):
    if not re.fullmatch(r'vd193_bench_[0-9a-f]{32}', schema) or not re.fullmatch(r'[a-z][a-z0-9_]*', name):
        raise ValueError('Benchmark may only write to its own UUID schema')
    return schema + '.' + name


def copy_into(db, schema, name, path):
    target = relation(schema, name)
    digest = file_sha256(path)
    with path.open('rb') as stream:
        if path.stat().st_size:
            stream.seek(-1, 2)
            if stream.read(1) != b'\n':
                raise ValueError('COPY input must end with LF')
        stream.seek(0)
        db._process.stdin.write((f"COPY {target}({COLUMNS}) FROM STDIN WITH(FORMAT text, NULL '\\N', ENCODING 'UTF8');\n").encode())
        for block in iter(lambda: stream.read(1024*1024), b''):
            db._process.stdin.write(block)
        db._process.stdin.write(b'\\.\n')
        db._process.stdin.flush()
    db._send('SELECT 1;')
    if file_sha256(path) != digest:
        raise ValueError('COPY input changed')


def prepare_input(directory, output, sample_rows=None):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    metadata = json.loads((directory/'metadata.json').read_bytes())
    source = directory/'counts.tsv'
    record = next(r for r in metadata['manifest']['files'] if r['role']=='counts')
    if file_sha256(source)!=record['sha256'] or source.stat().st_size!=record['bytes']:
        raise ValueError('Input file differs from verified source metadata')
    if sample_rows is not None and (type(sample_rows) is not int or not 1<=sample_rows<=record['rows']):
        raise ValueError('Invalid sample size')
    # Parse the COPY transport as raw escaped VARCHAR; do not silently reinterpret versions.
    with duckdb.connect(config={'threads':2,'memory_limit':'2GB'}) as con:
        con.execute('SET enable_progress_bar=false')
        con.execute("CREATE TEMP TABLE raw AS SELECT * FROM read_csv(?, delim='\t', header=false, quote='', escape='', "
                    "columns={'package_id':'INTEGER','version':'VARCHAR','snapshot_at':'DATE','dependents_count':'INTEGER'})", [str(source)])
        # Decode PostgreSQL COPY escaping, including literal backslashes, for round-trip-safe export.
        def unescape(value):
            return re.sub(r'\\([\\tnr])',lambda m:{'\\':'\\','t':'\t','n':'\n','r':'\r'}[m[1]],value)
        con.create_function('copy_unescape',unescape,['VARCHAR'],'VARCHAR')
        if sample_rows is None:
            path=source
            query='SELECT package_id,copy_unescape(version) AS version,snapshot_at,dependents_count FROM raw'
        else:
            # Stratify across the sorted key space rather than taking the first package IDs.
            query=('SELECT package_id,copy_unescape(version) AS version,snapshot_at,dependents_count FROM '
                   '(SELECT *,row_number() OVER(ORDER BY package_id,version) rn FROM raw) '
                   f'WHERE floor((rn-1)*{sample_rows}::DOUBLE/{record["rows"]})<>floor((rn-2)*{sample_rows}::DOUBLE/{record["rows"]})')
            path=output/'counts.tsv'
            copy_text(con,query+' ORDER BY package_id,version',COLUMNS.split(','),path)
        expected=con.execute('SELECT count(*),count(*) FILTER(WHERE dependents_count=0),'
                             'sum(dependents_count),min(snapshot_at)::VARCHAR,max(snapshot_at)::VARCHAR FROM ('+query+')').fetchone()
        if expected[0]!=(sample_rows or record['rows']) or expected[3]!=metadata['snapshot'] or expected[4]!=metadata['snapshot']:
            raise ValueError('Prepared sample count or date mismatch')
    return path, {'source_metadata_sha256':file_sha256(directory/'metadata.json'),'source_counts_sha256':record['sha256'],
                  'file_sha256':file_sha256(path),'rows':expected[0],'zeros':expected[1],'sum':expected[2],
                  'snapshot':metadata['snapshot'],'scope':'FULL_DATE' if sample_rows is None else 'STRATIFIED_SAMPLE'}


def service_state(db):
    rows=db._send("SELECT coalesce(json_agg(row_to_json(e) ORDER BY execution_id),'[]') FROM "
                 "(SELECT execution_id,status,manifest_sha256,contract_sha256,actual_counts,active_attempt_id "
                 "FROM public.etl_load_execution WHERE dataset='version-dependents') e;")
    return json.loads(rows[0])


def cleanup(db, schema):
    relation(schema, 'source')
    owned=db._send(f"SELECT nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_namespace WHERE nspname='{schema}';")
    if not owned:
        return
    if owned!=['t']:
        raise ValueError('Benchmark schema owner changed')
    for name in db._send(f"SELECT tablename FROM pg_tables WHERE schemaname='{schema}';"):
        db._send('DROP TABLE '+relation(schema,name)+';')
    db._send(f'DROP SCHEMA {schema};')


def benchmark(*, command, input_dir, output, modes, repeats=1, sample_rows=None, explain=False):
    if not modes or any(m not in MODES for m in modes) or len(set(modes))!=len(modes):
        raise ValueError('Invalid benchmark modes')
    if type(repeats) is not int or not 1<=repeats<=3:
        raise ValueError('Use 1..3 repeats')
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    path,receipt=prepare_input(input_dir,output,sample_rows)
    schema='vd193_bench_'+uuid.uuid4().hex
    results=[]
    def event(phase,**extra):
        value={'phase':phase,**extra}
        with (output/'progress.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(value)+'\n')
        print(json.dumps(value),flush=True)
    plan={'schema':schema,'input':receipt,'modes':modes,'repeats':repeats,'explain':explain,
          'benchmark_code_sha256':file_sha256(Path(__file__)),'database_command':command}
    _publish_json(output/'plan.json',plan)
    with PgLoader(command,output) as db:
        before=service_state(db)
        if any(r['status']=='PREPARING' for r in before):
            raise ValueError('Service load must be paused before benchmarking')
        if db._send("SELECT pg_try_advisory_lock(hashtextextended('curated:version-dependents',0));")!=['t']:
            raise ValueError('Service load is active')
        if db._send("SELECT pg_try_advisory_lock(hashtextextended('curated:package-version',0));")!=['t']:
            raise ValueError('Reference load is active')
        db._send("SET application_name='vd193-isolated-benchmark'; SET statement_timeout='30min';")
        body='(package_id INTEGER NOT NULL,version VARCHAR(100) NOT NULL,snapshot_at DATE NOT NULL,dependents_count INTEGER NOT NULL DEFAULT 0 CHECK(dependents_count>=0))'
        try:
            db._send(f'CREATE SCHEMA {schema}; REVOKE ALL ON SCHEMA {schema} FROM PUBLIC;')
            db._send(f'CREATE TABLE {relation(schema,"source")}{body};')
            tick=time.monotonic();copy_into(db,schema,'source',path)
            setup_seconds=time.monotonic()-tick
            db._send(f'ALTER TABLE {relation(schema,"source")} ADD PRIMARY KEY(package_id,version,snapshot_at); ANALYZE {relation(schema,"source")};')
            staged=json.loads(db._send(f'SELECT json_build_object(\'rows\',count(*),\'zeros\',count(*) FILTER(WHERE dependents_count=0),\'sum\',sum(dependents_count)) FROM {relation(schema,"source")};')[0])
            if any(staged[k]!=receipt[k] for k in ('rows','zeros','sum')):
                raise ValueError('Staged input differs from source')
            event('STAGED',rows=receipt['rows'],seconds=setup_seconds)
            for repeat in range(repeats):
                order=modes if repeat%2==0 else list(reversed(modes))
                for index,mode in enumerate(order):
                    name=f'trial_{repeat}_{index}'
                    table=relation(schema,name)
                    metrics={}
                    def timed(label,work):
                        tick=time.monotonic();value=work();metrics[label]=time.monotonic()-tick;return value
                    started=time.monotonic()
                    event('TRIAL_START',mode=mode,repeat=repeat)
                    db._send('BEGIN;')
                    db._send(f'CREATE TABLE {table}{body};')
                    def pk(): return db._send(f'ALTER TABLE {table} ADD PRIMARY KEY(package_id,version,snapshot_at);')
                    def fk(): return db._send(f'ALTER TABLE {table} ADD CONSTRAINT version_fk FOREIGN KEY(package_id,version) REFERENCES public.version(package_id,version), ADD CONSTRAINT snapshot_fk FOREIGN KEY(snapshot_at) REFERENCES public.snapshot(snapshot_at);')
                    if mode!='copy_then_constraints':
                        timed('initial_pk_seconds',pk)
                    if mode in ('insert_pk_fk','copy_pk_fk'):
                        timed('initial_fk_seconds',fk)
                    detail=None
                    if mode.startswith('insert'):
                        sql=f'INSERT INTO {table}({COLUMNS}) SELECT {COLUMNS} FROM {relation(schema,"source")};'
                        if explain:
                            sql='EXPLAIN (ANALYZE,BUFFERS,WAL,FORMAT JSON) '+sql
                        response=timed('write_seconds',lambda:db._send(sql))
                        if explain: detail=json.loads('\n'.join(response))
                    else:
                        timed('write_seconds',lambda:copy_into(db,schema,name,path))
                    if mode=='copy_then_constraints':
                        timed('build_pk_seconds',pk)
                        timed('validate_fk_seconds',fk)
                    # Exact values, missing rows, extras and zeros, not merely aggregate equality.
                    mismatch=timed('verify_seconds',lambda:db._send(f'SELECT count(*) FROM {table} t FULL JOIN {relation(schema,"source")} s USING(package_id,version,snapshot_at) WHERE t.package_id IS NULL OR s.package_id IS NULL OR t.dependents_count IS DISTINCT FROM s.dependents_count;'))
                    if mismatch!=['0']:raise ValueError('Output differs from input')
                    if mode!='insert_pk_only':
                        constraints=db._send(f"SELECT count(*) FILTER(WHERE contype='f'),bool_and(convalidated) FROM pg_constraint WHERE conrelid='{table}'::regclass;")
                        if constraints!=['2|t']:raise ValueError('Missing/unvalidated constraints')
                    timed('commit_seconds',lambda:db._send('COMMIT;'))
                    metrics['total_seconds']=time.monotonic()-started
                    sizes=db._send(f"SELECT pg_relation_size('{table}'),pg_indexes_size('{table}');")[0].split('|')
                    result={'mode':mode,'repeat':repeat,'rows':receipt['rows'],'metrics':metrics,'table_bytes':int(sizes[0]),'index_bytes':int(sizes[1]),'exact_match':True,'diagnostic_without_fk':mode=='insert_pk_only','explain':detail}
                    _publish_json(output/f'{name}.json',result);results.append(result)
                    event('TRIAL_COMPLETE',mode=mode,repeat=repeat,seconds=metrics['total_seconds'])
                    db._send(f'DROP TABLE {table};')
            if service_state(db)!=before:raise ValueError('Service execution history changed during experiment')
            if file_sha256(path)!=receipt['file_sha256']:raise ValueError('Input changed during experiment')
            report={'status':'COMPLETE','plan':plan,'results':results,'service_history_unchanged':True,
                    'source_copy_seconds':setup_seconds,'scope':'ISOLATED_TABLES_REAL_REFERENCE_DATA'}
        finally:
            # Never use CASCADE here: unexpected external dependencies must prevent deletion.
            try:
                db._send('ROLLBACK;')
                cleanup(db,schema)
            except RuntimeError:
                # ON_ERROR_STOP can close psql; reconnect only to clean our exact schema.
                with PgLoader(command,output) as recovery:
                    recovery._send("SET statement_timeout='30s';")
                    cleanup(recovery,schema)
        report['cleanup_complete']=True
        _publish_json(output/'result.json',report)
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',required=True);p.add_argument('--output',required=True)
    p.add_argument('--container',default='pickage-267-validation');p.add_argument('--database',default='pickage_267_full_defaulted')
    p.add_argument('--mode',action='append',choices=MODES);p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--sample-rows',type=int);p.add_argument('--explain',action='store_true')
    a=p.parse_args()
    benchmark(command=['docker','exec','-i',a.container,'psql','-U','postgres','-d',a.database],input_dir=a.input_dir,
              output=a.output,modes=a.mode or list(MODES),repeats=a.repeats,sample_rows=a.sample_rows,explain=a.explain)


if __name__=='__main__':main()
