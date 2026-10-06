"""Validate and load a frozen Projects calendar with database execution history."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from pipeline.preprocessing.snapshot.input import read_candidate
from pipeline.postgresql.snapshot.postgres import SAFE_ID, SnapshotLoader
from pipeline.preprocessing.common.paths import REPO_ROOT


ROOT = REPO_ROOT


def logical_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_uri()


def contract_sha256() -> str:
    """The load contract is separate from the snapshot-time-v1 policy hash."""
    paths = [p for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')]
    paths += list((ROOT / 'pipeline/preprocessing/snapshot').glob('*.py'))
    paths += [ROOT / 'pipeline/postgresql/postgres.py']
    migrations = ROOT / 'backend/src/main/resources/db/migration'
    paths += [migrations / name for name in ('V1__init.sql', 'V2__add_curated_load_execution.sql',
                                            'V3__add_snapshot_reference_execution.sql')]
    digest = hashlib.sha256(b'snapshot-reference-load-v1\0')
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0')
        digest.update(path.read_text(encoding='utf-8').encode() + b'\0')
    return digest.hexdigest()


def prior_date_load(path: Path, prepared: dict) -> dict:
    raw = path.read_bytes()
    receipt = json.loads(raw)
    candidate = prepared['candidate']
    dates = [r['snapshot_at'] for r in prepared['calendar']]
    expected_sql_hash = next(f['sha256'] for f in candidate['files'] if f['path'] == 'snapshot-dates.sql')
    if (not isinstance(receipt, dict) or receipt.get('status') != 'COMMITTED_AND_VERIFIED'
            or receipt.get('candidate_sha256') != prepared['candidate_sha256']
            or receipt.get('policy_sha256') != candidate['policy_sha256']
            or receipt.get('source_sql_sha256') != expected_sql_hash
            or receipt.get('expected_dates') != dates or not receipt.get('database')):
        raise ValueError('prior date-load receipt does not match the frozen input')
    return {'path': logical_path(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'receipt': receipt}


def _write_report(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def run(candidate_path: Path, execution_id: str, work_dir: Path, command: list[str] | None,
        *, verify_only: bool = False, prior_receipt: Path | None = None, failpoint: str | None = None) -> dict:
    if not isinstance(execution_id, str) or not SAFE_ID.fullmatch(execution_id):
        raise ValueError('invalid execution ID')
    if not verify_only and not command:
        raise ValueError('an explicit PostgreSQL command is required')
    attempt_id = uuid.uuid4().hex
    attempt_dir = work_dir.resolve() / execution_id / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    report_path = attempt_dir / 'execution_report.json'
    started = time.monotonic()
    report = {'dataset': 'snapshot-reference', 'execution_id': execution_id, 'attempt_id': attempt_id,
              'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'PREPARING',
              'phase': 'VALIDATE_INPUT', 'mode': 'VERIFY_ONLY' if verify_only else 'LOAD',
              'candidate_path': logical_path(candidate_path), 'contract_sha256': contract_sha256(),
              'service_ready': False, 'report_path': str(report_path)}
    _write_report(report_path, report)
    try:
        prepared = read_candidate(candidate_path)
        candidate = prepared['candidate']
        manifest = {'candidate': candidate, 'inventory_sha256': prepared['inventory_sha256']}
        if prior_receipt is not None:
            manifest['prior_date_load'] = prior_date_load(prior_receipt, prepared)
        metadata = {'dataset': 'snapshot-reference', 'manifest_sha256': prepared['candidate_sha256'],
                    'run_prefix': logical_path(candidate_path.parent), 'manifest': manifest,
                    'counts': {'snapshot': len(prepared['calendar'])}}
        report.update(input=metadata, policy_sha256=candidate['policy_sha256'])
        if verify_only:
            report.update(status='VERIFIED', counts=metadata['counts'])
        else:
            report['phase'] = 'LOAD_DATABASE'
            _write_report(report_path, report)
            with SnapshotLoader(command, attempt_dir) as database:
                try:
                    if prior_receipt is not None:
                        expected_db = manifest['prior_date_load']['receipt']['database']
                        if database._send('SELECT current_database();') != [expected_db]:
                            raise ValueError('prior date-load receipt belongs to a different database')
                    database.start(metadata, execution_id, report['contract_sha256'], attempt_id)
                    report.update(database.publish(prepared['calendar'], failpoint=failpoint))
                except BaseException as error:
                    report['phase'] = database.phase
                    try:
                        database.fail(error)
                    except Exception as history_error:
                        report['failure_history_error'] = str(history_error)
                    raise
        report['phase'] = 'COMPLETE'
    except BaseException as error:
        report.update(status='FAILED', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic()-started, 3))
        _write_report(report_path, report)
        print(f"{report['status']}: {report_path}", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--execution-id', required=True)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'data/snapshot/executions')
    parser.add_argument('--prior-receipt', type=Path, help='optional receipt of an earlier date-only load')
    parser.add_argument('--verify-only', action='store_true')
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--docker-container')
    target.add_argument('--psql')
    parser.add_argument('--database')
    parser.add_argument('--db-user', default='postgres')
    args = parser.parse_args()
    command = None
    if not args.verify_only:
        if not args.database or not (args.docker_container or args.psql):
            parser.error('--database and either --docker-container or --psql are required')
        if not SAFE_ID.fullmatch(args.database) or not SAFE_ID.fullmatch(args.db_user):
            parser.error('database and user must be simple names; use libpq settings for authentication')
        if args.docker_container:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.docker_container):
                parser.error('invalid Docker container name')
            command = ['docker', 'exec', '-i', args.docker_container, 'psql']
        else:
            command = [args.psql]
        command += ['-U', args.db_user, '-d', args.database]
    try:
        run(args.candidate, args.execution_id, args.work_dir, command,
            verify_only=args.verify_only, prior_receipt=args.prior_receipt)
    except Exception as error:
        print(f'Load failed ({type(error).__name__}); see the execution report for details', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
