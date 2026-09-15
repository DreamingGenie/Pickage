"""Bounded server pilot: preserve service DB, restore a small archive into a new candidate.

Run on the Ubuntu server after uploading a verified task bundle. Never runs a
full dump or switches the API connection. A failed candidate is retained.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid


TABLES = ('package', 'version', 'snapshot', 'package_snapshot', 'package_version_snapshot')
MONITOR_INTERVAL_SECONDS = 5.0
MAX_MONITOR_SAMPLES = 17_280  # bounded memory for up to 24 hours of monitoring
FULL_SOURCE_VALIDATION_MARKER = 'DEFERRED_BY_USER'
FULL_SOURCE_VALIDATION_REASON = '사용자 결정에 따라 원본 전수 값 검증을 유예하고 복원 후 구조 검증까지만 수행'


def signature_query(table):
    if table not in TABLES:
        raise ValueError('Unknown service table')
    return f"""SELECT json_build_object('rows',count(*),
        'sum_hi',coalesce(sum(('x'||substr(h,1,16))::bit(64)::bigint),0)::text,
        'sum_lo',coalesce(sum(('x'||substr(h,17,16))::bit(64)::bigint),0)::text)
        FROM (SELECT md5(row_to_json(t)::text) h FROM public.{table} t) s;"""


def run(command, *, data=None, env=None, stdout=None):
    result = subprocess.run(command, input=data, env=env, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed ({result.returncode}): {result.stderr.decode("utf-8", "replace")[-3000:]}')
    return result.stdout


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def csv_rows_by_key(data, table):
    """Ignore locale-dependent row order, preserve raw cells (NULL != quoted empty).

    csv.reader locates keys and record boundaries. Comparing the original record
    keeps quoting/JSON/newlines intact instead of collapsing NULL and empty text.
    This in-memory comparison is only for the bounded small pilot.
    """
    lines = list(io.StringIO(data.decode('utf-8'), newline=''))
    reader = csv.reader(lines)
    header = next(reader)
    key_names = ['snapshot_at'] if table == 'snapshot' else ['package_id']
    if table in ('version','package_version_snapshot'): key_names.append('version')
    if table in ('package_snapshot','package_version_snapshot'): key_names.append('snapshot_at')
    positions = [header.index(name) for name in key_names]
    rows = {}
    previous = reader.line_num
    for values in reader:
        if len(values) != len(header): raise ValueError('Invalid CSV record width')
        key = tuple(values[index] for index in positions)
        if key in rows: raise ValueError('Duplicate CSV key')
        rows[key] = ''.join(lines[previous:reader.line_num])
        previous = reader.line_num
    return header, rows


def restore_scope(*, full_restore: bool, benchmark: bool) -> str:
    """Return the bundle contract for the selected server operation."""
    if full_restore:
        return '341-full-server-restore'
    if benchmark:
        return '341-large-server-benchmark'
    return '341-small-server-pilot'


def archive_size_limit(*, full_restore: bool, benchmark: bool) -> int | None:
    """Return the bounded archive limit; complete restores are unbounded."""
    if full_restore:
        return None
    return 2 * 1024**3 if benchmark else 20 * 1024**2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def full_source_validation_contract(bundle: dict) -> tuple[str, str]:
    """Require and return the explicit user decision carried by a full bundle."""
    marker = bundle.get('source_validation')
    reason = bundle.get('source_validation_reason')
    if marker != FULL_SOURCE_VALIDATION_MARKER:
        raise ValueError('Full restore bundle must declare source_validation=DEFERRED_BY_USER')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Full restore bundle must declare source_validation_reason')
    return marker, reason


def run_full_restore_stages(*, phase, restore, flyway, validate_structure,
                            analyze_candidate, source_validation_reason: str) -> dict:
    """Run the full archive stages while deliberately omitting source scans/signatures."""
    phase('restore_full_archive', restore)
    phase('flyway_v2_to_v6', lambda: flyway('migrate', 'latest'))
    phase('flyway_validate', lambda: flyway('validate', 'latest'))
    phase('validate_partition_structure', validate_structure)
    phase('defer_source_validation', lambda: None)
    phase('analyze_candidate', analyze_candidate)
    return {
        'source_validation': FULL_SOURCE_VALIDATION_MARKER,
        'source_validation_deferred': True,
        'source_validation_deferred_reason': source_validation_reason,
        'status': 'RESTORED_UNVERIFIED',
        'ready_for_service': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--postgres-container', default='pickage-app-postgres-1')
    parser.add_argument('--service-db', default='pickage')
    parser.add_argument('--java-image', default='pickage-api:manual-01')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--benchmark', action='store_true', help='Allow bounded 2 GiB archive and streaming SQL signatures')
    mode.add_argument('--full-restore', action='store_true', help='Restore a complete verified archive into a new candidate without source signatures')
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if not work.is_relative_to(Path('/home/ubuntu/service-data-migration/341')):
        raise ValueError('Pilot output must stay under /home/ubuntu/service-data-migration/341')
    if not re.fullmatch(r'[a-zA-Z0-9_]+', args.service_db):
        raise ValueError('A plain service DB name is required')
    bundle = json.loads((work / 'bundle-manifest.json').read_text())
    scope = restore_scope(full_restore=args.full_restore, benchmark=args.benchmark)
    if bundle.get('scope') != scope:
        raise ValueError('Bundle scope does not match requested pilot mode')
    source_validation_marker = None
    source_validation_reason = None
    if args.full_restore:
        source_validation_marker, source_validation_reason = full_source_validation_contract(bundle)
    for item in bundle['files']:
        path = (work / item['path']).resolve()
        if not path.is_relative_to(work) or path.is_symlink() or digest(path) != item['sha256']:
            raise ValueError('Bundle checksum/path mismatch')
    archive_bytes = sum(p.stat().st_size for p in (work / 'archive').iterdir())
    size_limit = archive_size_limit(full_restore=args.full_restore, benchmark=args.benchmark)
    if size_limit is not None and archive_bytes > size_limit:
        raise ValueError('Archive exceeds the bounded pilot size limit')
    disk_before = shutil.disk_usage(work.parent)
    if args.benchmark and disk_before.free < 20 * 1024**3:
        raise ValueError('Benchmark requires at least 20 GiB free disk')
    if args.full_restore and disk_before.free < 220 * 1024**3:
        raise ValueError('Full restore requires at least 220 GiB free on the work filesystem')
    token = uuid.uuid4().hex[:12]
    candidate_prefix = 'pickage_import_341_full_restore_' if args.full_restore else 'pickage_import_341_server_pilot_'
    candidate = candidate_prefix + token
    helper = 'pickage-341-pgclient-' + token
    output = work / 'server-result.json'
    if output.exists():
        raise ValueError('This run already has a result; prepare a new run directory')
    report = {'candidate': candidate, 'status': 'RUNNING', 'ready_for_service': False,
              'full_transfer_ready': False, 'phases': [], 'pid': os.getpid(),
              'scope': scope, 'archive_bytes': archive_bytes,
              'started_at': utc_now(),
              'host_disk_free_before_bytes': disk_before.free}
    if args.full_restore:
        report['source_validation'] = source_validation_marker
        report['source_validation_deferred'] = True
        report['source_validation_deferred_reason'] = source_validation_reason
    started = time.monotonic()
    helper_created = False
    stop_monitor = threading.Event()
    samples = []
    disk_samples = []
    monitor = None
    config = json.loads(run(['docker','inspect',args.postgres_container]))[0]
    pg_env = dict(item.split('=',1) for item in config['Config'].get('Env',[]) if '=' in item)
    pg_user = pg_env.get('POSTGRES_USER','postgres')
    password = pg_env.get('POSTGRES_PASSWORD')
    if not password:
        raise RuntimeError('No usable postgres password in container environment; no candidate created')
    env = dict(os.environ, PGUSER=pg_user, PGPASSWORD=password, PICKAGE_341_CANDIDATE_DB=candidate)

    def save():
        report['elapsed_seconds'] = round(time.monotonic()-started,3)
        report['updated_at'] = utc_now()
        temp = output.with_suffix('.json.tmp')
        temp.write_text(json.dumps(report,indent=2),encoding='utf-8')
        temp.replace(output)

    def phase(name, action):
        report['current_phase'] = name
        save()
        at = time.monotonic()
        value = action()
        report['phases'].append({'name':name,'elapsed_seconds':round(time.monotonic()-at,3)})
        save()
        return value

    def sql(database, query):
        return run(['docker','exec','-i','--env','PGOPTIONS=-c DateStyle=ISO,YMD',args.postgres_container,'psql','-X','-U',pg_user,'-d',database,
                    '-v','ON_ERROR_STOP=1','-At'],data=query.encode()).decode('utf-8')

    def source_state():
        return {'history':sql(args.service_db,'SELECT row_to_json(h) FROM public.flyway_schema_history h ORDER BY installed_rank;'),
                'rows':{table:int(sql(args.service_db,f'SELECT count(*) FROM public.{table};')) for table in TABLES},
                'objects':sql(args.service_db,"SELECT c.oid,c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.oid;")}

    def flyway(action, target):
        command = ['docker','run','--rm','--label','pickage.task=341-flyway-pilot','--memory=512m',
                   '--network','container:'+args.postgres_container,'--read-only','--tmpfs','/tmp:rw,size=64m',
                   '--mount',f'type=bind,source={work},target=/work,readonly',
                   '--env','PGUSER','--env','PGPASSWORD','--env','PICKAGE_341_CANDIDATE_DB',
                   '--entrypoint','java',args.java_image,'-cp','/work/runtime/*:/work/classes','CandidateFlyway',
                   action,'/work/migrations',target]
        result = subprocess.run(command,env=env,capture_output=True)
        with (work/'flyway-stdout.log').open('ab') as log:
            log.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Flyway failed: '+result.stderr.decode('utf-8','replace')[-3000:])

    try:
        before = phase('service_preflight',source_state)
        if any(before['rows'].values()):
            raise RuntimeError('Service data changed: only the observed empty service DB is supported')
        histories = [json.loads(line) for line in before['history'].splitlines()]
        if len(histories)!=1 or histories[0].get('version')!='1' or not histories[0].get('success'):
            raise RuntimeError('Service migration state changed; expected genuine V1 only')
        report['service_before'] = before
        report['postgres_memory_limit_bytes'] = config['HostConfig']['Memory']
        # Sample the existing PostgreSQL cgroup without running polling queries.
        cgroup_lines = Path(f"/proc/{config['State']['Pid']}/cgroup").read_text().splitlines()
        relative = next(line.split(':',2)[2] for line in cgroup_lines if line.startswith('0::'))
        cgroup = Path('/sys/fs/cgroup') / relative.lstrip('/')
        def sample():
            while not stop_monitor.is_set() and len(samples) < MAX_MONITOR_SAMPLES:
                try:
                    samples.append(int((cgroup/'memory.current').read_text()))
                    disk_samples.append(shutil.disk_usage(work.parent).used)
                except OSError:
                    break
                stop_monitor.wait(MONITOR_INTERVAL_SECONDS)
            if len(samples) >= MAX_MONITOR_SAMPLES:
                report['monitor_sample_limit_reached'] = True
        monitor = threading.Thread(target=sample,daemon=True)
        monitor.start()
        report['wal_before'] = sql(args.service_db,'SELECT wal_bytes FROM pg_stat_wal;').strip()
        backup = work/'service-v1-backup.dump'
        if backup.exists():
            raise RuntimeError('Backup path already exists')
        def backup_service():
            with backup.open('xb') as destination:
                run(['docker','exec',args.postgres_container,'pg_dump','-U',pg_user,'-d',args.service_db,
                     '-Fc','--no-owner','--no-privileges'],stdout=destination)
        phase('backup_existing_service',backup_service)
        report['backup_bytes'] = backup.stat().st_size
        report['backup_sha256'] = digest(backup)
        phase('create_candidate',lambda: sql('postgres',f'CREATE DATABASE "{candidate}" OWNER "{pg_user}";'))
        report['candidate_created'] = True
        def bootstrap():
            with backup.open('rb') as stream:
                result = subprocess.run(['docker','exec','-i',args.postgres_container,'pg_restore','-U',pg_user,
                    '-d',candidate,'--no-owner','--no-privileges','--exit-on-error'],stdin=stream,capture_output=True)
                if result.returncode:
                    raise RuntimeError(result.stderr.decode('utf-8','replace')[-3000:])
        phase('restore_existing_v1_history',bootstrap)
        phase('validate_actual_v1_checksum',lambda:flyway('validate','1'))
        phase('prepare_empty_candidate',lambda:sql(candidate,(work/'prepare_candidate.sql').read_text()))
        phase('start_pg_client',lambda:run(['docker','run','-d','--name',helper,'--label','pickage.task=341-server-pilot',
             '--memory=256m','--network','container:'+args.postgres_container,
             '--mount',f'type=bind,source={work},target=/work,readonly',
             '--env','PGUSER','--env','PGPASSWORD','--env','PGHOST=127.0.0.1','--entrypoint','sleep',config['Config']['Image'],'infinity'],env=env))
        helper_created = True
        archive_meta = json.loads((work/'archive-manifest.json').read_text())
        def restore():
            with (work/'restore.log').open('wb') as log:
                result = subprocess.run([sys.executable,str(work/'transfer.py'),'restore','--archive-dir',str(work/'archive'),
                    '--container',helper,'--container-archive-dir','/work','--candidate-db',candidate,
                    '--source-db',archive_meta['source_db'],'--service-db',args.service_db,'--user',pg_user,'--jobs','2'],stdout=log,stderr=subprocess.STDOUT)
                if result.returncode:
                    raise RuntimeError('Restore failed; inspect restore.log')
            report['restore_sections'] = json.loads((work/(candidate+'.restore-status.json')).read_text())['phases']
        def validate_structure():
            return sql(candidate,(work/'validate_structure.sql').read_text())
        def analyze_candidate():
            return sql(candidate,';'.join('ANALYZE public.'+t for t in TABLES)+';')
        def compare_values():
            meta = json.loads((work/'sample.json').read_text())
            counts={}
            for table in TABLES:
                order = 'snapshot_at' if table=='snapshot' else 'package_id'
                if table in ('version','package_version_snapshot'): order+=',version'
                if table in ('package_snapshot','package_version_snapshot'): order+=',snapshot_at'
                actual = run(['docker','exec',args.postgres_container,'psql','-X','-U',pg_user,'-d',candidate,'-At','-c',
                    f'COPY (SELECT * FROM public.{table} ORDER BY {order}) TO STDOUT WITH (FORMAT csv, HEADER true);'])
                if csv_rows_by_key(actual,table) != csv_rows_by_key((work/(table+'.csv')).read_bytes(),table):
                    raise RuntimeError('Source and candidate values differ: '+table)
                counts[table]=int(sql(candidate,f'SELECT count(*) FROM public.{table};'))
            if counts!=meta['sample_rows']: raise RuntimeError('Candidate counts differ')
            return counts
        def compare_signatures():
            expected = json.loads((work/'expected-signatures.json').read_text())
            actual = {}
            report['signature_seconds_by_table'] = {}
            for table in TABLES:
                at = time.monotonic()
                actual[table] = json.loads(sql(candidate,signature_query(table)))
                report['signature_seconds_by_table'][table] = round(time.monotonic()-at,3)
            if actual != expected:
                report['actual_signatures'] = actual
                raise RuntimeError('Source and candidate row counts/value signatures differ')
            report['signature_validation'] = 'Counts and order-independent sums of both MD5 halves over every row; probabilistic integrity check'
            return {table:item['rows'] for table,item in actual.items()}
        if args.full_restore:
            report.update(run_full_restore_stages(
                phase=phase, restore=restore, flyway=flyway,
                validate_structure=validate_structure,
                analyze_candidate=analyze_candidate,
                source_validation_reason=source_validation_reason))
            report['status'] = 'RUNNING'  # Final status follows service postflight.
            report['candidate_rows'] = None
        else:
            phase('restore_sample_archive', restore)
            phase('flyway_v2_to_v6',lambda:flyway('migrate','latest'))
            phase('flyway_validate',lambda:flyway('validate','latest'))
            phase('validate_partition_structure', validate_structure)
            report['candidate_rows'] = phase('compare_value_signatures' if args.benchmark else 'compare_every_sample_value',
                                             compare_signatures if args.benchmark else compare_values)
            phase('analyze_candidate', analyze_candidate)
        report['candidate_bytes'] = int(sql(candidate,'SELECT pg_database_size(current_database());'))
        report['candidate_table_sizes'] = json.loads(sql(candidate,"""
            WITH sizes AS (
              SELECT root.relname table_name,
                     sum(pg_table_size(c.oid)) table_bytes, sum(pg_indexes_size(c.oid)) index_bytes
              FROM pg_class root JOIN pg_namespace n ON n.oid=root.relnamespace
              JOIN pg_class c ON c.oid=root.oid OR c.oid IN
                (SELECT relid FROM pg_partition_tree(root.oid) WHERE isleaf)
              WHERE n.nspname='public' AND root.relname IN
                ('package','version','snapshot','package_snapshot','package_version_snapshot')
              GROUP BY root.relname)
            SELECT json_agg(sizes) FROM sizes;"""))
        report['candidate_temp_bytes'] = int(sql(candidate,"SELECT temp_bytes FROM pg_stat_database WHERE datname=current_database();"))
        report['wal_after'] = sql(args.service_db,'SELECT wal_bytes FROM pg_stat_wal;').strip()
        after = phase('service_postflight',source_state)
        if before!=after: raise RuntimeError('Original service DB state changed during pilot')
        report['service_unchanged'] = True
        report['containers_after'] = run(['docker','ps','--format','{{.Names}} {{.Status}}']).decode()
        report['status']='RESTORED_UNVERIFIED' if args.full_restore else 'PASS'
        report['current_phase']='complete'
    except BaseException as exc:
        report['status']='FAIL'
        report['error']=str(exc)
        raise
    finally:
        stop_monitor.set()
        if monitor: monitor.join(timeout=2)
        if samples:
            report['postgres_cgroup_sampled_peak_bytes']=max(samples)
            report['postgres_cgroup_sample_count']=len(samples)
            report['memory_note']='Existing PostgreSQL cgroup incl page cache; shared load, sampled every 5 seconds with a bounded sample count'
        if disk_samples:
            report['host_disk_used_start_bytes'] = disk_samples[0]
            report['host_disk_sampled_peak_delta_bytes'] = max(disk_samples)-disk_samples[0]
            report['host_disk_used_end_delta_bytes'] = shutil.disk_usage(work.parent).used-disk_samples[0]
            report['disk_note'] = 'Shared host filesystem, sampled every 5 seconds; includes WAL and other activity'
        if helper_created:
            run(['docker','rm','-f',helper])
        save()
        print(json.dumps({'status':report['status'],'candidate':candidate,'result':str(output)}),flush=True)


if __name__=='__main__':
    main()
