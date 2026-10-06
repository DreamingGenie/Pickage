"""Finish an ordered candidate restore without switching the service database.

Runs detached on the server. Preparation and each following phase have durable
status; unexpected benchmark plans stop before starting the full FK scan.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import transfer


def benchmark_gate(document):
    """Require an observed sort-free, heap-free reference index scan."""
    plans = []

    def visit(value):
        if isinstance(value, dict):
            if 'Node Type' in value:
                plans.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    if not plans:
        raise ValueError('No actual benchmark plan was recorded')
    if any(p['Node Type'] in ('Sort', 'Incremental Sort') for p in plans):
        raise ValueError('Benchmark still sorts; review before restarting the full FK')
    scans = [p for p in plans if p.get('Relation Name')]
    reference = [p for p in scans if p.get('Relation Name') == 'version']
    leaves = [p for p in scans if p.get('Relation Name', '').startswith('d')]
    if not reference or not leaves or any(p['Node Type'] != 'Index Only Scan' or
                            p.get('Heap Fetches') != 0 or 'Actual Rows' not in p
                            for p in scans):
        raise ValueError('Benchmark inputs are not observed heap-free index-only scans')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--candidate-db', required=True)
    parser.add_argument('--reference-db', required=True)
    parser.add_argument('--client-container', required=True)
    parser.add_argument('--postgres-container', default='pickage-app-postgres-1')
    parser.add_argument('--user', default='pickage')
    parser.add_argument('--service-db', default='pickage')
    parser.add_argument('--java-image', default='eclipse-temurin:21-jdk')
    args = parser.parse_args()
    work, output = args.work_dir.resolve(), args.output_dir.resolve()
    if not transfer.CANDIDATE_PATTERN.fullmatch(args.candidate_db) or args.candidate_db == args.service_db:
        raise ValueError('Only an isolated 341 candidate is allowed')
    output.mkdir(parents=True, exist_ok=True)
    claim = output / 'finish.claim'
    # O_EXCL prevents two orchestrators from starting work concurrently.
    with claim.open('x') as stream:
        stream.write(str(os.getpid()))
    started = time.monotonic()
    report = {'status': 'RUNNING', 'candidate': args.candidate_db, 'pid': os.getpid(),
              'started_at': transfer.utc_now(), 'ready_for_service': False,
              'full_transfer_ready': False, 'source_validation': 'DEFERRED_BY_USER', 'phases': []}

    def save():
        report['updated_at'] = transfer.utc_now()
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        transfer.write_json(output / 'server-result.json', report)

    def run(command, *, data=None, env=None):
        result = subprocess.run(command, input=data, capture_output=True, env=env)
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', 'replace')[-4000:])
        return result.stdout

    def sql(db, statement):
        return run(['docker', 'exec', '-i', args.postgres_container, 'psql', '-X', '-U', args.user,
                    '-d', db, '-v', 'ON_ERROR_STOP=1', '-At'], data=statement.encode()).decode()

    def phase(name, action):
        report['current_phase'] = name
        save()
        at = time.monotonic()
        value = action()
        report['phases'].append({'name': name, 'elapsed_seconds': round(time.monotonic()-at, 3)})
        save()
        return value

    def service_state():
        return {
            'history': sql(args.service_db, 'SELECT row_to_json(h) FROM public.flyway_schema_history h ORDER BY installed_rank;'),
            'rows': {t: int(sql(args.service_db, f'SELECT count(*) FROM public.{t};')) for t in transfer.ROOT_TABLES},
            'objects': sql(args.service_db, "SELECT c.oid,c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.oid;")}

    try:
        bundle = json.loads((work / 'bundle-manifest.json').read_text())
        if bundle.get('source_validation') != 'DEFERRED_BY_USER':
            raise ValueError('Missing explicit deferred source validation contract')
        # Frozen migration/runtime inputs must still match the uploaded bundle.
        for entry in bundle['files']:
            if entry['path'].startswith('archive/'):
                continue  # resume_postdata validates the archive.
            path = (work / entry['path']).resolve()
            if not path.is_relative_to(work) or transfer.sha256_file(path) != entry['sha256']:
                raise ValueError('Frozen bundle file differs: ' + entry['path'])
        original = json.loads((work / 'server-result.json').read_text())
        if original['candidate'] != args.candidate_db:
            raise ValueError('Candidate differs from original restore')
        stop = json.loads((output / 'stop-receipt.json').read_text())
        if (stop.get('candidate') != args.candidate_db or stop.get('status') != 'STOPPED'
                or not stop.get('old_processes_exited') or stop.get('sessions_after') != []):
            raise ValueError('Old restore termination is not confirmed')
        before = phase('service_preflight', service_state)
        if before != original['service_before']:
            raise ValueError('Service state changed since original restore; review required')
        base = [sys.executable, str(Path(__file__).with_name('resume_postdata.py')),
                '--work-dir', str(work), '--output-dir', str(output / 'postdata'),
                '--archive-dir', str(work / 'archive'),
                '--source-db', json.loads((work / 'archive-manifest.json').read_text())['source_db'],
                '--candidate-db', args.candidate_db, '--reference-db', args.reference_db,
                '--client-container', args.client_container, '--postgres-container', args.postgres_container,
                '--user', args.user, '--benchmark-timeout-seconds', '120']

        def resume(through):
            with (output / ('resume-' + through + '.log')).open('ab') as log:
                result = subprocess.run(base + ['--through', through], stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('Ordered restore stopped; inspect resume-' + through + '.log')
            state = json.loads((output / 'postdata' / 'resume-status.json').read_text())
            if state.get('status') != ('PREPARED' if through == 'prepare' else 'COMPLETE'):
                raise ValueError('Post-data phase did not reach the required completion state')

        phase('indexes_vacuum_benchmark', lambda: resume('prepare'))
        # Written by the preparation runner; only actual execution is accepted.
        benchmark = json.loads((output / 'postdata' / 'benchmark.json').read_text())
        phase('benchmark_gate', lambda: benchmark_gate(benchmark))
        phase('remaining_foreign_keys', lambda: resume('all'))
        config = json.loads(run(['docker', 'inspect', args.postgres_container]))[0]
        pg_env = dict(item.split('=', 1) for item in config['Config']['Env'] if '=' in item)
        password = pg_env.get('POSTGRES_PASSWORD')
        if not password:
            raise ValueError('PostgreSQL password unavailable for candidate Flyway')
        env = dict(os.environ, PGUSER=args.user, PGPASSWORD=password,
                   PICKAGE_341_CANDIDATE_DB=args.candidate_db)

        def flyway(action):
            command = ['docker', 'run', '--rm', '--memory=512m',
                       '--network', 'container:' + args.postgres_container, '--read-only',
                       '--tmpfs', '/tmp:rw,size=64m', '--mount', f'type=bind,source={work},target=/work,readonly',
                       '--env', 'PGUSER', '--env', 'PGPASSWORD', '--env', 'PICKAGE_341_CANDIDATE_DB',
                       '--entrypoint', 'java', args.java_image, '-cp', '/work/runtime/*:/work/classes',
                       'CandidateFlyway', action, '/work/migrations', 'latest']
            with (output / 'flyway.log').open('ab') as log:
                result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('Candidate Flyway failed; inspect flyway.log')

        phase('flyway_migrate', lambda: flyway('migrate'))
        phase('flyway_validate', lambda: flyway('validate'))
        report['structure'] = phase('validate_structure', lambda: sql(args.candidate_db, (work / 'validate_structure.sql').read_text()))
        phase('analyze', lambda: sql(args.candidate_db, ';'.join('ANALYZE public.'+t for t in transfer.ROOT_TABLES)+';'))
        after = phase('service_postflight', service_state)
        if before != after:
            raise ValueError('Service changed during candidate restore')
        report['service_unchanged'] = True
        report['candidate_bytes'] = int(sql(args.candidate_db, 'SELECT pg_database_size(current_database());'))
        report['status'] = 'RESTORED_UNVERIFIED'
        report['current_phase'] = 'complete'
        report['completed_at'] = transfer.utc_now()
        origin = datetime.fromisoformat(original['started_at'].replace('Z', '+00:00'))
        report['wall_seconds_since_original_start'] = (datetime.now(timezone.utc)-origin).total_seconds()
    except BaseException as exc:
        report['status'] = 'NEEDS_REVIEW'
        report['error'] = str(exc)
        raise
    finally:
        save()
        # Preserve helper and reference DB as evidence/recovery inputs.


if __name__ == '__main__':
    main()
