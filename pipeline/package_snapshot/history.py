"""Resumable full-calendar reconstruction and local PostgreSQL publication."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from pipeline.downloads.bronze import _file_hash, _same_or_put, publish
from pipeline.minio.ingest_raw import client
from .history_build import prepare_state, build_snapshot
from .history_inputs import prepare, revalidate_files
from .history_load import load_snapshot, prepare_copy
from .history_contract import build_contract_sha256, validator_contract_sha256
from .history_policy import policy_document, policy_sha256
from .policy import canonical_bytes
from .quality_schema import QUALITY_SCHEMA_ID


def event(phase, **values):
    print(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'phase': phase, **values},
                     ensure_ascii=False), flush=True)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def sql_json(command, sql):
    result = subprocess.run(command + ['-X', '-q', '-A', '-t', '-w', '-v', 'ON_ERROR_STOP=1'],
                            input=sql.encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return json.loads(result.stdout.decode().strip())


def database_state(command, base_date):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', base_date):
        raise ValueError('invalid base date')
    return sql_json(command, f"""SELECT json_build_object(
        'dates',(SELECT json_agg(x ORDER BY snapshot_at) FROM
          (SELECT snapshot_at,count(*) AS rows FROM package_snapshot GROUP BY 1)x),
        'current',(SELECT json_agg(c ORDER BY dataset) FROM etl_dataset_current c),
        'base_values',(SELECT json_build_object('rows',count(*),'downloads',sum(downloads),
          'stars',sum(stars),'issues',sum(open_issues),
          'hash_sum',sum(('x'||substr(md5(package_id::text||'|'||snapshot_at::text||'|'||
             coalesce(downloads::text,'NULL')||'|'||coalesce(stars::text,'NULL')||'|'||
             coalesce(open_issues::text,'NULL')),1,16))::bit(64)::bigint))
          FROM package_snapshot WHERE snapshot_at=DATE '{base_date}'),
        'reference_rows',(SELECT count(*) FROM etl_snapshot_reference),
        'snapshot_rows',(SELECT count(*) FROM snapshot));""")


def state_cache(prepared, directory, contract, memory, threads):
    directory = Path(directory)
    saved = directory / 'state.json'
    if saved.exists():
        document = json.loads(saved.read_text(encoding='utf-8'))
        if (document['input_sha256'] != prepared['input_sha256'] or
                document.get('build_contract_sha256') != contract):
            raise ValueError('history state belongs to different input or code; use a new run directory')
        for rec in document['file_records']:
            if _file_hash(Path(rec['path'])) != (rec['bytes'], rec['sha256']):
                raise ValueError('history state cache changed')
        return document['state']
    event('PREPARE_ASOF_STATE')
    state = prepare_state(prepared, directory, memory=memory, threads=threads)
    file_records = []
    for role, path in state['files'].items():
        size, sha = _file_hash(Path(path))
        file_records.append({'role': role, 'path': str(path), 'bytes': size, 'sha256': sha})
    write_json(saved, {'input_sha256': prepared['input_sha256'], 'build_contract_sha256': contract,
                       'file_records': file_records, 'state': state})
    event('ASOF_STATE_READY', counts=state.get('counts'))
    return state


def validate_saved_manifest(manifest, prepared, interval, run_id, *, build_contract=None):
    """Reuse only a proven matching build; a validator hash alone is insufficient."""
    saved_build = manifest.get('build_contract_sha256')
    if not re.fullmatch(r'[0-9a-f]{64}', str(saved_build or '')):
        raise ValueError('saved history output has no valid build contract; '
                         'legacy provenance must be established separately; do not stamp the current hash')
    current_build = build_contract if build_contract is not None else build_contract_sha256()
    if saved_build != current_build:
        raise ValueError('saved history output build contract differs; '
                         'preserve the old run and use a new run ID to rebuild')
    sources = prepared['input_manifest']
    expected = {'dataset': 'package-snapshot', 'format_version': 1, 'status': 'PASSED',
                'run_id': run_id, 'snapshot': interval['snapshot_at'],
                'snapshot_timestamp': interval['snapshot_timestamp'], 'interval': interval,
                'input_manifest_sha256': prepared['input_sha256'],
                'input_manifest': {k: sources[k] for k in ('population', 'candidate', 'repository', 'downloads')},
                'history_policy': policy_document(), 'history_policy_sha256': policy_sha256(),
                'projects_input': sources['projects'][interval['snapshot_at']],
                'required_remote_verification': 'GET_SHA256_ALL_FILES'}
    if (any(manifest.get(key) != value for key, value in expected.items()) or
            manifest.get('quality_schema') != QUALITY_SCHEMA_ID or
            not re.fullmatch(r'[0-9a-f]{64}', str(manifest.get('contract_sha256', '')))):
        raise ValueError('saved history output belongs to different input, date, policy or schema')
    records = manifest.get('files', [])
    if (len(records) != 3 or {r.get('role') for r in records} !=
            {'package_snapshot', 'package_identity', 'quality'} or
            any(r.get('path') != r['role'] + '.parquet' for r in records)):
        raise ValueError('saved history output file roles or paths differ')


def run(config, *, run_id, work_dir, command, s3, memory='8GB', threads=4, snapshots=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', run_id):
        raise ValueError('invalid history run ID')
    started = time.monotonic()
    root = Path(work_dir).resolve() / run_id
    root.mkdir(parents=True, exist_ok=True)
    build_contract = build_contract_sha256()
    validator_contract = validator_contract_sha256()
    event('INPUT_PREFLIGHT', run_id=run_id)
    prepared = prepare(config, root / 'inputs', s3)
    expected_counts = config.get('expected_date_counts', {})
    base_date = prepared['input_manifest']['population']['snapshot']
    days = {r['snapshot_at'] for r in prepared['calendar']}
    if snapshots and not set(snapshots).issubset(days - {base_date}):
        raise ValueError('requested history dates must belong to the calendar before the preserved base')
    # Reject unproven/mismatched saved builds before scanning the large DB or
    # writing any remote objects. Keep the original manifests immutable.
    saved_outputs = {}
    for interval in prepared['calendar']:
        day = interval['snapshot_at']
        if day == base_date or (snapshots and day not in snapshots):
            continue
        saved = root / day / 'run_manifest.json'
        if saved.exists():
            manifest = json.loads(saved.read_text(encoding='utf-8'))
            validate_saved_manifest(manifest, prepared, interval, run_id + '-' + day.replace('-', ''),
                                    build_contract=build_contract)
            saved_outputs[day] = manifest
    before = database_state(command, base_date)
    baseline_path = root / 'database-before.json'
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        if before['base_values'] != baseline['base_values'] or before['current'] != baseline['current']:
            raise ValueError('preserved base values or current pointers changed since the history run began')
    else:
        baseline = before
        write_json(baseline_path, baseline)
    if baseline['base_values']['rows'] != prepared['input_manifest']['population']['counts']['package']:
        raise ValueError('preserved observed base snapshot is incomplete')
    input_key = f'depsdev/v1/package-snapshot-history-input/run_id={run_id}/input-manifest.json'
    _same_or_put(s3, 'pickage-curated', input_key, canonical_bytes(prepared['input_manifest']))
    _same_or_put(s3, 'pickage-curated', input_key.rsplit('/', 1)[0] + '/_SUCCESS',
                 (prepared['input_sha256'] + '\n').encode())
    # Revalidating saved outputs needs no population-state rebuild. New dates get
    # a cache tied to generation code, leaving older caches and artifacts intact.
    state = None
    reports = []
    for interval in prepared['calendar']:
        day = interval['snapshot_at']
        if day == base_date or (snapshots and day not in snapshots):
            continue
        day_root = root / day
        saved_manifest = day_root / 'run_manifest.json'
        day_run = run_id + '-' + day.replace('-', '')
        prefix = f'depsdev/v1/package-snapshot-history/snapshot={day}/run_id={day_run}'
        execution_id = 'load-' + day_run
        event('SNAPSHOT_START', snapshot=day, completed_in_this_invocation=len(reports))
        if day in saved_outputs:
            manifest = saved_outputs[day]
            files = {r['role']: str(day_root / 'output' / r['path']) for r in manifest['files']}
        else:
            if state is None:
                state = state_cache(prepared, root / 'state' / build_contract, build_contract, memory, threads)
            # Check consumed raw partitions immediately before building this date.
            paths = set(prepared['project_files'][day])
            for date, items in prepared['daily_files'].items():
                if interval['previous_snapshot_at'] and interval['previous_snapshot_at'] <= date < day:
                    paths.update(items)
            revalidate_files([r for r in prepared['verified_files'] if r['local_path'] in paths])
            built = build_snapshot(prepared, state, interval, day_root / 'output', memory=memory, threads=threads)
            files = {role: str(path) for role, path in built['files'].items()}
            records = []
            for role, path in files.items():
                if role not in ('package_snapshot', 'package_identity', 'quality'):
                    raise ValueError('unexpected history output role')
                size, sha = _file_hash(Path(path))
                records.append({'role': role, 'path': Path(path).name, 'bytes': size, 'sha256': sha,
                                'row_count': built['rows']})
            if len(records) != 3:
                raise ValueError('history output role missing')
            inputs = prepared['input_manifest']
            manifest = {'dataset': 'package-snapshot', 'format_version': 1, 'status': 'PASSED',
                        'quality_schema': built['quality_schema'],
                        'run_id': day_run, 'snapshot': day, 'snapshot_timestamp': interval['snapshot_timestamp'],
                        'interval': interval, 'history_policy': policy_document(),
                        'history_policy_sha256': policy_sha256(),
                        'build_contract_sha256': build_contract,
                        'contract_sha256': validator_contract,
                        'input_manifest_sha256': prepared['input_sha256'],
                        'input_manifest': {k: inputs[k] for k in ('population', 'candidate', 'repository', 'downloads')},
                        'history_input': {'key': input_key, 'sha256': prepared['input_sha256']},
                        'projects_input': inputs['projects'][day], 'counts': {'package_snapshot': built['rows']},
                        'quality': built['quality'], 'files': records,
                        'required_remote_verification': 'GET_SHA256_ALL_FILES'}
            write_json(saved_manifest, manifest)
        if expected_counts and manifest['counts']['package_snapshot'] != expected_counts.get(day):
            raise ValueError('history population differs from independently planned per-date count')
        # Validate service/quality/eligibility before publishing a PASSED Curated marker.
        copy_input = prepare_copy(files, manifest, day_root / 'validated-copy', memory=memory, threads=threads)
        publication = publish(s3, bucket='pickage-curated', prefix=prefix,
                              root=day_root / 'output', manifest=manifest)
        event('SNAPSHOT_CURATED', snapshot=day, rows=manifest['counts']['package_snapshot'])
        db_report = load_snapshot(s3, prefix=prefix, manifest=manifest, files=files,
                                  work_dir=day_root / 'postgresql', command=command,
                                  contract_hash=validator_contract, execution_id=execution_id, copy_input=copy_input)
        report = {'snapshot': day, 'rows': manifest['counts']['package_snapshot'],
                  'publication': publication, 'database': db_report}
        write_json(day_root / 'result.json', report)
        reports.append(report)
        event('SNAPSHOT_COMPLETE', snapshot=day, rows=report['rows'],
              action=db_report['result']['action'], seconds=db_report['elapsed_seconds'])
    event('FINAL_DB_RECONCILIATION')
    after = database_state(command, base_date)
    write_json(root / 'database-after.json', after)
    if (after['base_values'] != baseline['base_values'] or after['current'] != baseline['current'] or
            after['reference_rows'] != baseline['reference_rows'] or after['snapshot_rows'] != baseline['snapshot_rows']):
        raise ValueError('preserved observed base or predecessor history changed')
    actual = {r['snapshot_at']: r['rows'] for r in after['dates']}
    for report in reports:
        if actual.get(report['snapshot']) != report['rows']:
            raise ValueError('final per-date DB count differs from publication')
    if not snapshots and set(actual) != days:
        raise ValueError('full history calendar has missing or unexpected DB dates')
    revalidate_files(prepared['verified_files'])
    result = {'status': 'PUBLISHED' if not snapshots else 'SELECTED_DATES_PUBLISHED', 'run_id': run_id,
              'input_sha256': prepared['input_sha256'], 'contract_sha256': validator_contract,
              'build_contract_sha256': build_contract, 'validator_contract_sha256': validator_contract,
              'calendar_dates': len(days), 'loaded_dates': len(actual), 'rows': sum(actual.values()),
              'preserved_observed_base': base_date, 'reconstructed_dates': len(actual) - 1,
              'elapsed_seconds': round(time.monotonic() - started, 3), 'dates': after['dates'],
              'base_values_and_current_pointers_preserved': True}
    write_json(root / 'result.json', result)
    event('HISTORY_COMPLETE', **result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--docker-container', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--memory', default='8GB')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--snapshots', nargs='+')
    args = parser.parse_args()
    command = ['docker', 'exec', '-i', args.docker_container, 'psql', '-U', 'postgres', '-d', args.database]
    run(json.loads(args.config.read_text(encoding='utf-8')), run_id=args.run_id,
        work_dir=args.work_dir, command=command, s3=client(), memory=args.memory,
        threads=args.threads, snapshots=args.snapshots)


if __name__ == '__main__':
    main()
