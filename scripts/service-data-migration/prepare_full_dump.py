"""M3 only: a full archive and source receipts from one exported MVCC snapshot.

Run detached with stdout/stderr redirected. No CSV, remote connection, source
DDL/DML, automatic retry, or whole-job timeout. A failed run is never reused.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

import local_dump_client as client
import transfer

TABLES = transfer.ROOT_TABLES
CHILD_SCHEMA = transfer.CHILD_SCHEMA


def ident(name):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
        raise ValueError('Invalid SQL identifier')
    return '"' + name + '"'


def psql_command(helper, database, user, application):
    return ['docker','exec','-i','--env','PGCONNECT_TIMEOUT=15',
            '--env','PGAPPNAME='+application, helper,'psql','-X','-q','-A','-t',
            '-v','ON_ERROR_STOP=1','--username',user,'--dbname',database]


class SnapshotKeeper:
    def __init__(self, helper, database, user, directory):
        self.log = (directory/'snapshot-keeper.stderr.log').open('wb')
        self.process = subprocess.Popen(psql_command(helper,database,user,'pickage_341_m3_keeper'),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,
            text=True,encoding='utf-8',bufsize=1)

    def query(self, sql):
        marker = '__m3_done_'+uuid.uuid4().hex
        self.process.stdin.write(sql+'\n\\echo '+marker+'\n')
        self.process.stdin.flush()
        lines = []
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError('Snapshot keeper disconnected; inspect snapshot-keeper.stderr.log')
            if line.strip() == marker:
                return '\n'.join(lines)
            lines.append(line.rstrip('\n'))

    def export(self):
        sql = """BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL lock_timeout='30s';
SET LOCAL statement_timeout=0;
SET LOCAL idle_in_transaction_session_timeout=0;
SET LOCAL DateStyle='ISO, YMD';
LOCK TABLE public.package,public.version,public.snapshot,public.package_snapshot,
           public.package_version_snapshot IN ACCESS SHARE MODE;
SELECT pg_export_snapshot();"""
        token = self.query(sql).strip()
        if not re.fullmatch(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9]+',token):
            raise RuntimeError('Unexpected exported snapshot token')
        return token

    def close(self):
        try:
            if self.process.poll() is None:
                self.query('ROLLBACK;')
                self.process.stdin.write('\\q\n')
                self.process.stdin.flush()
                self.process.wait(timeout=15)
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.log.close()


def capture_catalog(keeper, expected_partitions):
    identity = json.loads(keeper.query("""SELECT json_build_object(
      'database',current_database(),'database_oid',(SELECT oid FROM pg_database WHERE datname=current_database()),
      'server_version',current_setting('server_version'),'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),
      'snapshot_time',transaction_timestamp(),'snapshot_xids',pg_current_snapshot()::text);"""))
    relations = [json.loads(line) for line in keeper.query("""
SELECT json_build_object('schema',n.nspname,'table',c.relname,'oid',c.oid,'kind',c.relkind,
 'estimated_rows',c.reltuples,'table_bytes',pg_table_size(c.oid),'index_bytes',pg_indexes_size(c.oid),
 'bound',pg_get_expr(c.relpartbound,c.oid),
 'columns',(SELECT json_agg(json_build_object('name',a.attname,'type',format_type(a.atttypid,a.atttypmod),
   'not_null',a.attnotnull,'default',pg_get_expr(d.adbin,d.adrelid)) ORDER BY a.attnum)
   FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
   WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped))
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE (n.nspname='public' AND c.relname IN
 ('package','version','snapshot','package_snapshot','package_version_snapshot'))
 OR c.oid IN(SELECT inhrelid FROM pg_inherits WHERE inhparent='public.package_version_snapshot'::regclass)
ORDER BY n.nspname,c.relname;""").splitlines()]
    roots = {r['table']:r for r in relations if r['schema']=='public'}
    children = [r for r in relations if r['schema']!= 'public']
    if set(roots)!=set(TABLES) or roots['package_version_snapshot']['kind']!='p':
        raise RuntimeError('Unexpected source root tables')
    if len(children)!=expected_partitions:
        raise RuntimeError('Source partition count changed')
    for r in children:
        if r['schema']!=CHILD_SCHEMA or not re.fullmatch(r'd[0-9]{8}',r['table']) or r['kind']!='r':
            raise RuntimeError('Unexpected source child relation')
        if r['columns']!=roots['package_version_snapshot']['columns']:
            raise RuntimeError('Partition columns differ from parent')
    dates = json.loads(keeper.query('SELECT json_agg(snapshot_at ORDER BY snapshot_at) FROM public.snapshot;'))
    return {'identity':identity,'relations':relations,'snapshot_dates':dates}


def receipt_query(relation):
    table = relation['table']
    source = ident(relation['schema'])+'.'+ident(table)
    pvs = relation['schema']==CHILD_SCHEMA
    extras = []
    group = ''
    if pvs:
        extras = ["'snapshot_at',min(snapshot_at)","'last_snapshot_at',max(snapshot_at)",
                  "'dependents_sum',coalesce(sum(dependents_count::numeric),0)::text",
                  "'zero_rows',count(*) FILTER(WHERE dependents_count=0)",
                  "'negative_rows',count(*) FILTER(WHERE dependents_count<0)",
                  "'null_count_rows',count(*) FILTER(WHERE dependents_count IS NULL)"]
    elif table=='package_snapshot':
        extras = ["'snapshot_at',snapshot_at","'downloads_sum',coalesce(sum(downloads::numeric),0)::text",
                  "'downloads_null_rows',count(*) FILTER(WHERE downloads IS NULL)",
                  "'stars_null_rows',count(*) FILTER(WHERE stars IS NULL)",
                  "'open_issues_null_rows',count(*) FILTER(WHERE open_issues IS NULL)"]
        group=' GROUP BY snapshot_at ORDER BY snapshot_at'
    elif table=='version':
        extras = ["'published_at_null_rows',count(*) FILTER(WHERE published_at IS NULL)",
                  "'dependency_null_rows',count(*) FILTER(WHERE dependency IS NULL)"]
    elif table=='package':
        extras=["'repo_url_null_rows',count(*) FILTER(WHERE repo_url IS NULL)"]
    extra = ','+','.join(extras) if extras else ''
    # Hash the original row before adding the hash column to the outer record.
    return f"""SELECT json_build_object('rows',count(*),
      'sum_hi',coalesce(sum(('x'||substr(h,1,16))::bit(64)::bigint),0)::text,
      'sum_lo',coalesce(sum(('x'||substr(h,17,16))::bit(64)::bigint),0)::text{extra})
      FROM (SELECT t.*,md5(row_to_json(t)::text) h FROM ONLY {source} t) s{group};"""


def read_receipt(helper, database, user, snapshot, relation):
    if not re.fullmatch(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9]+',snapshot):
        raise ValueError('Invalid snapshot token')
    started=time.monotonic()
    sql=f"""BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET TRANSACTION SNAPSHOT '{snapshot}';
SET LOCAL statement_timeout=0;
SET LOCAL lock_timeout='30s';
SET LOCAL DateStyle='ISO, YMD';
SET LOCAL max_parallel_workers_per_gather=0;
SET LOCAL work_mem='64MB';
{receipt_query(relation)}
COMMIT;"""
    result = subprocess.run(psql_command(helper,database,user,'pickage_341_m3_validate'),
        input=sql,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Source validation failed for {relation['table']}: {result.stderr[-1500:]}")
    return {'relation':relation['schema']+'.'+relation['table'],'snapshot':snapshot,
            'elapsed_seconds':round(time.monotonic()-started,3),
            'groups':[json.loads(line) for line in result.stdout.splitlines() if line.strip()]}


def add_signatures(groups):
    return {'rows':sum(g['rows'] for g in groups),
            'sum_hi':str(sum(int(g['sum_hi']) for g in groups)),
            'sum_lo':str(sum(int(g['sum_lo']) for g in groups))}


def verify_full_toc(toc, catalog):
    expected={(r['schema'],r['table']) for r in catalog['relations']}
    definitions=set(); data=set()
    for line in toc.splitlines():
        if line.startswith(';'): continue
        match=re.search(r'\bTABLE (DATA )?(\S+) (\S+) ',line)
        if match:
            pair=(match[2],match[3])
            if match[1]: data.add(pair)
            elif match[2]!='ATTACH': definitions.add(pair)
    if definitions!=expected or data!=expected-{('public','package_version_snapshot')}:
        raise RuntimeError('Archive table/data entries do not match the frozen source catalog')


def check_new_run_directory(directory):
    # A detached launcher may already have copied code and opened its logs.
    allowed={'code','launcher.json','stdout.log','stderr.log'}
    if directory.exists():
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError('Run directory must be a real directory')
        for path in directory.iterdir():
            if path.name not in allowed or path.is_symlink():
                raise RuntimeError('Run contains previous artifacts; choose a new directory')
            if (path.name=='code') != path.is_dir():
                raise RuntimeError('Unexpected launcher artifact type')


def save_progress_status(path, payload, started, fallback_directory):
    """Persist mutable progress without allowing a Windows reader lock to stop work."""
    payload['updated_at'] = transfer.utc_now()
    payload['elapsed_seconds'] = round(time.monotonic() - started, 3)
    try:
        transfer.write_json(path, payload)
        return True
    except OSError as exc:
        fallback = fallback_directory / f"status-{os.getpid()}-{uuid.uuid4().hex}.json"
        try:
            fallback.parent.mkdir(parents=True, exist_ok=True)
            fallback_payload = dict(payload)
            fallback_payload['status_path'] = str(path)
            fallback_payload['fallback_at'] = transfer.utc_now()
            fallback_payload['fallback_reason'] = str(exc)
            transfer.write_json(fallback, fallback_payload)
            print(f"[warning] could not update status.json; progress saved to {fallback}", file=sys.stderr)
        except OSError as fallback_exc:
            print(f"[warning] could not save progress status: {fallback_exc}", file=sys.stderr)
        return False


def execute(args):
    directory=args.run_dir.resolve()
    base=args.mount_dir.resolve()
    if directory.parent!=base or not re.fullmatch(r'full-[A-Za-z0-9_-]+',directory.name):
        raise ValueError('Run must be a new full-<id> directory immediately below the helper mount')
    if not 1<=args.validation_workers<=4 or not 1<=args.jobs<=4:
        raise ValueError('Use 1..4 dump/validation workers')
    if not transfer.DB_NAME_PATTERN.fullmatch(args.source_db):
        raise ValueError('Invalid source database name')
    check_new_run_directory(directory)
    directory.mkdir(parents=True,exist_ok=True)
    status_path=directory/'status.json'
    if status_path.exists() or (directory/'archive').exists():
        raise RuntimeError('Existing run cannot be overwritten or resumed with a new snapshot')
    source=client.docker_inspect(args.source_container)
    client.source_details(args.source_container)
    helper=client.helper_name(args.source_container)
    client.validate_helper(client.docker_inspect(helper),source=args.source_container,archive=base)
    if shutil.disk_usage(directory).free<args.minimum_free_gib*1024**3:
        raise RuntimeError('Insufficient local disk for this run')
    report={'status':'RUNNING','phase':'snapshot','started_at':transfer.utc_now(),'pid':os.getpid(),
            'source_container':args.source_container,'source_container_id':source['Id'],
            'source_db':args.source_db,'helper':helper,'jobs':args.jobs,'validation_workers':args.validation_workers,
            'ready_for_transfer':False,'ready_for_service':False,'phases':[],
            'completed_relations':0,'active_relations':[],'free_bytes_before':shutil.disk_usage(directory).free,
            'code_sha256':{name:transfer.sha256_file(Path(__file__).parent/name)
                           for name in ('prepare_full_dump.py','transfer.py','local_dump_client.py')}}
    started=time.monotonic(); keeper=None
    def save():
        save_progress_status(status_path, report, started, directory/'status-fallback')
    def phase(name,action):
        report['phase']=name; save(); at=time.monotonic()
        value=action()
        report['phases'].append({'name':name,'elapsed_seconds':round(time.monotonic()-at,3)})
        save(); return value
    save()
    try:
        keeper=SnapshotKeeper(helper,args.source_db,args.user,directory)
        snapshot=keeper.export(); report['snapshot']=snapshot
        catalog=capture_catalog(keeper,args.expected_partitions)
        transfer.write_json(directory/'source-catalog.json',catalog)
        report['source_snapshot_time']=catalog['identity']['snapshot_time']
        relations=[r for r in catalog['relations'] if r['kind']=='r']
        report['total_relations']=len(relations); save()
        client_parent='/work/'+directory.name
        archive=directory/'archive'
        def dump():
            command=[sys.executable,str(Path(transfer.__file__)),'dump','--source-db',args.source_db,
              '--user',args.user,'--archive-dir',str(archive),'--jobs',str(args.jobs),'--compression','zstd:1',
              '--container',helper,'--container-archive-dir',client_parent,'--snapshot',snapshot]
            with (directory/'dump.stdout.log').open('xb') as out, (directory/'dump.stderr.log').open('xb') as err:
                result=subprocess.run(command,stdout=out,stderr=err)
            if result.returncode: raise RuntimeError('pg_dump/archive verification failed; inspect dump logs')
            manifest=transfer.load_manifest(directory/'archive-manifest.json')
            if manifest.get('snapshot')!=snapshot: raise RuntimeError('Dump snapshot differs from validation snapshot')
            options=argparse.Namespace(container=helper,container_archive_dir=client_parent,
                archive_dir=archive,user=args.user)
            toc=transfer.validate_toc(archive,options)
            verify_full_toc(toc,catalog)
            (directory/'archive-toc.txt').write_text(toc,encoding='utf-8')
            report['archive_bytes']=sum(i['size'] for i in manifest['files'])
            report['archive_files']=len(manifest['files'])
        phase('dump_and_archive_checks',dump)
        receipts=directory/'source-receipts'; receipts.mkdir()
        # Large roots first, then partition leaves. Each relation is scanned once.
        relations.sort(key=lambda r:r['table_bytes'],reverse=True)
        values=[]
        def validate():
            with ThreadPoolExecutor(max_workers=args.validation_workers) as pool:
                pending={}
                iterator=iter(relations)
                def submit_next():
                    relation=next(iterator,None)
                    if relation is not None:
                        future=pool.submit(read_receipt,helper,args.source_db,args.user,snapshot,relation)
                        pending[future]=relation
                for _ in range(args.validation_workers):submit_next()
                while pending:
                    report['active_relations']=[r['schema']+'.'+r['table'] for r in pending.values()];save()
                    future=next(as_completed(pending))
                    relation=pending.pop(future)
                    receipt=future.result()
                    transfer.write_json(receipts/(relation['schema']+'.'+relation['table']+'.json'),receipt)
                    values.append(receipt)
                    report['completed_relations']=len(values);save()
                    if (directory/'STOP_AFTER_CURRENT').exists():
                        raise RuntimeError('Stop requested; completed artifacts retained, a new snapshot is required to restart')
                    submit_next()
        phase('source_validation',validate)
        expected={}
        for table in TABLES:
            selected=[g for receipt in values if receipt['relation']=='public.'+table or
                      (table=='package_version_snapshot' and receipt['relation'].startswith(CHILD_SCHEMA+'.'))
                      for g in receipt['groups']]
            expected[table]=add_signatures(selected)
        transfer.write_json(directory/'expected-signatures.json',expected)
        report['source_rows']={table:s['rows'] for table,s in expected.items()}
        report['source_negative_dependents_rows']=sum(g.get('negative_rows',0) for r in values for g in r['groups'])
        if report['source_negative_dependents_rows']:
            raise RuntimeError('Negative dependents_count detected')
        def seal():
            # Re-hash after validation; both artifacts are tied to the same exported snapshot.
            transfer.verify_manifest(archive)
            files=[directory/'archive-manifest.json',directory/'source-catalog.json',directory/'expected-signatures.json',
                   *sorted(receipts.glob('*.json'))]
            transfer.write_json(directory/'source-validation-manifest.json',{
                'snapshot':snapshot,'source_identity':catalog['identity'],'source_rows':report['source_rows'],
                'comparison':'Exact counts plus probabilistic order-independent MD5-half sums of every row',
                'files':[{'path':p.relative_to(directory).as_posix(),'size':p.stat().st_size,
                          'sha256':transfer.sha256_file(p)} for p in files]})
        phase('seal_validation_and_archive',seal)
        keeper.close();keeper=None
        report['snapshot_released_at']=transfer.utc_now()
        report['status']='M3_COMPLETE'; report['phase']='complete';report['active_relations']=[]
        report['ready_for_transfer']=True
    except BaseException as exc:
        report['status']='FAILED';report['error']=str(exc)
        raise
    finally:
        if keeper:
            try:keeper.close()
            except Exception as exc:report['keeper_cleanup_error']=str(exc)
        report['free_bytes_after']=shutil.disk_usage(directory).free
        save()
        transfer.write_json(directory/'result.json', report)
        print(json.dumps(report,ensure_ascii=False),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--mount-dir',type=Path,default=Path('data/service-data-migration/341/local-dump-probe'))
    p.add_argument('--source-container',default=client.DEFAULT_SOURCE)
    p.add_argument('--source-db',default=client.DEFAULT_DB)
    p.add_argument('--user',default='postgres')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--validation-workers',type=int,default=2)
    p.add_argument('--expected-partitions',type=int,default=229)
    p.add_argument('--minimum-free-gib',type=int,default=100)
    execute(p.parse_args())


if __name__=='__main__':main()
