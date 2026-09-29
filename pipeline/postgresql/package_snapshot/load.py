"""Load an explicitly pinned integrated Curated run into an explicit PostgreSQL DB."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import time
import uuid

import duckdb

from pipeline.preprocessing.curated.storage import json_bytes, read_optional
from pipeline.preprocessing.downloads_interval.input import _fetch, _verify_remote
from pipeline.minio.ingest_raw import client
from pipeline.postgresql.input import _sql_path, _sql_paths
from pipeline.postgresql.load import _write_report
from pipeline.postgresql.package_snapshot.postgres import PackageSnapshotLoader
from pipeline.preprocessing.package_snapshot.quality import normalize_quality, validate_quality
from pipeline.preprocessing.common.paths import REPO_ROOT, PREPROCESSING_ROOT

ROOT = REPO_ROOT
BUCKET = 'pickage-curated'
SAFE_ID = re.compile(r'[A-Za-z0-9_-]{1,100}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
SCHEMAS = {
    'package_snapshot': [('package_id', 'INTEGER'), ('snapshot_at', 'DATE'), ('downloads', 'BIGINT'),
                         ('stars', 'INTEGER'), ('open_issues', 'INTEGER')],
    'package_identity': [('package_id', 'INTEGER'), ('name', 'VARCHAR')],
}

# The package-snapshot loader depends on the tables and execution lineage
# introduced by V1-V3.  Later migrations may belong to an unrelated feature
# (for example an API index or a new table) and must not make an already
# published snapshot impossible to revalidate.
PACKAGE_SNAPSHOT_MIGRATIONS = (
    'V1__init.sql',
    'V2__add_curated_load_execution.sql',
    'V3__add_snapshot_reference_execution.sql',
)


def contract_sha256():
    digest = hashlib.sha256()
    paths = [Path(__file__), Path(__file__).with_name('postgres.py'),
             PREPROCESSING_ROOT / 'package_snapshot/quality.py',
             PREPROCESSING_ROOT / 'package_snapshot/quality_schema.py',
             ROOT / 'pipeline/postgresql/postgres.py', ROOT / 'pipeline/postgresql/input.py', PREPROCESSING_ROOT / 'common/curated_input.py',
             ROOT / 'pipeline/postgresql/load.py', ROOT / 'pipeline/preprocessing/downloads_interval/input.py',
             ROOT / 'pipeline/preprocessing/curated/storage.py']
    migration_dir = ROOT / 'backend/src/main/resources/db/migration'
    paths += [migration_dir / name for name in PACKAGE_SNAPSHOT_MIGRATIONS]
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0')
        digest.update(path.read_text(encoding='utf-8').encode() + b'\0')
    digest.update(json_bytes({'format': 'package-snapshot-postgres-v1', 'duckdb': duckdb.__version__}))
    return digest.hexdigest()


def _read(s3, key):
    item = read_optional(s3, BUCKET, key)
    if item is None:
        raise ValueError('required object missing: ' + key)
    return item[0]


def select_run(s3, snapshot, run_id, manifest_sha256):
    if date.fromisoformat(snapshot).isoformat() != snapshot or not SAFE_ID.fullmatch(run_id):
        raise ValueError('invalid snapshot or run ID')
    if not SHA.fullmatch(manifest_sha256):
        raise ValueError('explicit manifest SHA is required')
    prefix = f'depsdev/v1/package-snapshot/snapshot={snapshot}/run_id={run_id}'
    body = _read(s3, prefix + '/run_manifest.json')
    if hashlib.sha256(body).hexdigest() != manifest_sha256:
        raise ValueError('integrated manifest SHA mismatch')
    if _read(s3, prefix + '/_SUCCESS') != (manifest_sha256 + '\n').encode():
        raise ValueError('integrated completion marker mismatch')
    if json.loads(_read(s3, prefix + '/_INPUT.json')) != {'manifest_sha256': manifest_sha256}:
        raise ValueError('integrated input lock mismatch')
    m = json.loads(body)
    if any(m.get(k) != v for k, v in {'dataset': 'package-snapshot', 'status': 'PASSED',
            'format_version': 1, 'snapshot': snapshot, 'run_id': run_id,
            'required_remote_verification': 'GET_SHA256_ALL_FILES'}.items()):
        raise ValueError('integrated manifest contract mismatch')
    for field, sha_field in [('input_manifest', 'input_manifest_sha256'), ('policy', 'policy_sha256')]:
        if hashlib.sha256(json_bytes(m[field])).hexdigest() != m[sha_field]:
            raise ValueError('integrated ' + field + ' hash mismatch')
    if not SHA.fullmatch(str(m.get('contract_sha256', ''))):
        raise ValueError('missing integration code contract')
    timestamp = datetime.fromisoformat(m['snapshot_timestamp'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None or timestamp.astimezone(timezone.utc).date().isoformat() != snapshot:
        raise ValueError('snapshot requires an exact UTC instant')
    if (m['interval']['snapshot_at'] != snapshot or
            m['interval']['snapshot_timestamp'] != m['snapshot_timestamp'] or
            m['input_manifest']['interval'] != m['interval']):
        raise ValueError('integrated interval mismatch')
    count = m['counts']['package_snapshot']
    if type(count) is not int or count <= 0:
        raise ValueError('invalid population count')
    records, seen = {}, set()
    for rec in m['files']:
        path, role = rec['path'], rec['role']
        relative = PurePosixPath(path)
        if (not isinstance(path, str) or relative.is_absolute() or '..' in relative.parts or
                '\\' in path or ':' in path or '*' in path or '?' in path or '[' in path or
                relative.as_posix() != path or not path.endswith('.parquet') or path in seen):
            raise ValueError('unsafe or duplicate output path')
        if role not in ('package_snapshot', 'package_identity', 'quality'):
            raise ValueError('unexpected output role')
        if (type(rec['bytes']) is not int or rec['bytes'] <= 0 or not SHA.fullmatch(rec['sha256']) or
                type(rec['row_count']) is not int or rec['row_count'] != count):
            raise ValueError('invalid output file record')
        seen.add(path)
        records.setdefault(role, []).append({**rec, 'key': prefix + '/data/' + path})
    if set(records) != {'package_snapshot', 'package_identity', 'quality'}:
        raise ValueError('required output role missing')
    return {'dataset': 'package-snapshot', 'snapshot': snapshot,
            'snapshot_timestamp': timestamp.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
            'curated_run_id': run_id, 'run_prefix': prefix, 'manifest_sha256': manifest_sha256,
            'manifest': m, 'counts': {'package_snapshot': count}, '_records': records}


def prepare(s3, metadata, work_dir, *, memory='4GB', threads=2):
    files = {}
    for role, records in metadata['_records'].items():
        files[role] = [_fetch(s3, BUCKET, r['key'], r, work_dir / 'cache' / role / (r['sha256'] + '.parquet'))
                       for r in records]
    expected = metadata['counts']['package_snapshot']
    csv_files = {}
    with duckdb.connect() as con:
        con.execute('SET memory_limit=?', [memory])
        con.execute('SET threads=?', [threads])
        con.execute("SET TimeZone='UTC'")
        for role, paths in files.items():
            view = 'quality_raw' if role == 'quality' else role
            con.execute(f'CREATE VIEW {view} AS SELECT * FROM read_parquet({_sql_paths(paths)},hive_partitioning=false)')
            schema = [(r[0], r[1]) for r in con.execute('DESCRIBE ' + view).fetchall()]
            if role in SCHEMAS and schema != SCHEMAS[role]:
                raise ValueError(role + ' schema mismatch')
            if con.execute(f'SELECT count(*) FROM {view}').fetchone()[0] != expected:
                raise ValueError(role + ' count mismatch')
            if con.execute(f'SELECT count(*) FROM (SELECT package_id FROM {view} GROUP BY 1 HAVING count(*)<>1)').fetchone()[0]:
                raise ValueError(role + ' duplicate package ID')
        normalize_quality(con, metadata['manifest'], producer='observed')
        bad = con.execute('SELECT count(*) FROM package_snapshot WHERE package_id IS NULL OR snapshot_at IS NULL '
                          'OR snapshot_at<>?::date OR downloads<0 OR stars<0 OR open_issues<0',
                          [metadata['snapshot']]).fetchone()[0]
        if bad:
            raise ValueError('invalid service row')
        if con.execute('SELECT count(*) FROM package_identity WHERE package_id IS NULL OR name IS NULL '
                       "OR contains(name,chr(0)) OR name='' ").fetchone()[0]:
            raise ValueError('invalid package identity')
        if con.execute('SELECT count(*)-count(DISTINCT name) FROM package_identity').fetchone()[0]:
            raise ValueError('duplicate package name')
        for role in ('package_identity', 'quality'):
            if con.execute(f'SELECT count(*) FROM package_snapshot s FULL JOIN {role} q USING(package_id) '
                           'WHERE s.package_id IS NULL OR q.package_id IS NULL').fetchone()[0]:
                raise ValueError(role + ' key mismatch')
        validate_quality(con, metadata['manifest'], producer='observed')
        counts = con.execute('SELECT count(downloads),count(stars),count(open_issues),'
                             'cast(sum(downloads) AS VARCHAR),cast(sum(stars) AS VARCHAR),'
                             'cast(sum(open_issues) AS VARCHAR) FROM package_snapshot').fetchone()
        validation = {'rows': expected, 'nonnull': dict(zip(('downloads', 'stars', 'open_issues'), counts[:3])),
                      'sums': dict(zip(('downloads', 'stars', 'open_issues'), counts[3:])),
                      'verification': 'ALL_KEYS_SCHEMA_COUNTS_VALUES'}
        for role, schema in SCHEMAS.items():
            columns = []
            for column, kind in schema:
                value = f'CAST({column} AS VARCHAR)'
                for char, escaped in ((92, 92), (9, 't'), (10, 'n'), (13, 'r')):
                    suffix = f'chr({escaped})' if isinstance(escaped, int) else f"'{escaped}'"
                    value = f'replace({value},chr({char}),chr(92)||{suffix})'
                columns.append(value)
            path = work_dir / (role + '.copy.tsv')
            con.execute(f"COPY (SELECT {','.join(columns)} FROM {role}) TO {_sql_path(path)} "
                        "(FORMAT CSV, DELIMITER '\\t', QUOTE '', ESCAPE '', HEADER false, NULL '\\N')")
            csv_files[role] = [path]
    return {'csv_files': csv_files, 'validation': validation}


def revalidate(s3, metadata):
    selected = select_run(s3, metadata['snapshot'], metadata['curated_run_id'], metadata['manifest_sha256'])
    if selected != metadata:
        raise ValueError('integrated input changed before commit')
    for records in metadata['_records'].values():
        for rec in records:
            _verify_remote(s3, BUCKET, rec['key'], rec)
    # Recheck every predecessor completion marker and pinned manifest. Their quality
    # locations remain immutable references in the integrated manifest and DB history.
    for role, source in metadata['manifest']['input_manifest'].items():
        if role not in ('population', 'downloads', 'repository_metrics'):
            continue
        prefix, sha = source['run_prefix'], source['manifest_sha256']
        if hashlib.sha256(_read(s3, prefix + '/run_manifest.json')).hexdigest() != sha:
            raise ValueError(role + ' manifest changed before commit')
        marker = _read(s3, prefix + '/_SUCCESS')
        valid = marker == (sha + '\n').encode() if role == 'downloads' else json.loads(marker) == {'manifest_sha256': sha}
        if not valid:
            raise ValueError(role + ' completion marker changed before commit')
    for group in ('population_files', 'download_files', 'repository_files', 'selection_files', 'detail_files'):
        for record in metadata['manifest']['input_manifest'].get(group, []):
            _verify_remote(s3, BUCKET, record['key'], record)


def run(s3, snapshot, curated_run_id, manifest_sha256, execution_id, work_dir, command,
        *, memory='4GB', threads=2, failpoint=None):
    if not SAFE_ID.fullmatch(execution_id) or not command:
        raise ValueError('explicit execution ID and PostgreSQL command are required')
    attempt_id = uuid.uuid4().hex
    root = Path(work_dir).resolve() / execution_id / attempt_id
    root.mkdir(parents=True, exist_ok=False)
    report_path = root / 'execution_report.json'
    started = time.monotonic()
    report = {'execution_id': execution_id, 'attempt_id': attempt_id, 'status': 'PREPARING',
              'started_at': datetime.now(timezone.utc).isoformat(), 'phase': 'SELECT_INPUT',
              'contract_sha256': contract_sha256(), 'report_path': str(report_path)}
    try:
        metadata = select_run(s3, snapshot, curated_run_id, manifest_sha256)
        report['input'] = {k: v for k, v in metadata.items() if not k.startswith('_')}
        _write_report(report_path, report)
        with PackageSnapshotLoader(command, root) as database:
            try:
                database.start(metadata, execution_id, report['contract_sha256'], attempt_id)
                print('Validating integrated files and exporting COPY rows', flush=True)
                report['phase'] = 'VALIDATE_INPUT'
                prepared = prepare(s3, metadata, root, memory=memory, threads=threads)
                report['validation'] = prepared['validation']
                report['phase'] = 'PUBLISH'
                _write_report(report_path, report)
                print('Staging and comparing all service rows', flush=True)
                report.update(database.publish(prepared['csv_files'], failpoint=failpoint,
                                               before_commit=lambda: revalidate(s3, metadata)))
            except BaseException as error:
                report['database_phase'] = database.phase
                if database.phase == 'VERIFY_COMMIT':
                    report['status'] = 'COMMITTED_UNVERIFIED'
                try:
                    database.fail(error)
                except Exception as history_error:
                    report['failure_history_error'] = str(history_error)
                raise
        report['phase'] = 'COMPLETE'
    except BaseException as error:
        report.update(status=('COMMITTED_UNVERIFIED' if report['status'] == 'COMMITTED_UNVERIFIED' else 'FAILED'),
                      error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 3))
        _write_report(report_path, report)
        print(f"{report['status']}: {report_path}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'curated-run-id', 'manifest-sha256', 'execution-id', 'database'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'data/package_snapshot/postgresql')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--docker-container')
    target.add_argument('--psql')
    parser.add_argument('--db-user', default='postgres')
    parser.add_argument('--memory-limit', default='4GB')
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    if not SAFE_ID.fullmatch(args.database) or not SAFE_ID.fullmatch(args.db_user):
        parser.error('database and user must be simple names')
    if args.docker_container:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.docker_container):
            parser.error('invalid Docker container name')
        command = ['docker', 'exec', '-i', args.docker_container, 'psql']
    else:
        command = [args.psql]
    command += ['-U', args.db_user, '-d', args.database]
    run(client(), args.snapshot, args.curated_run_id, args.manifest_sha256, args.execution_id,
        args.work_dir, command, memory=args.memory_limit, threads=args.threads)


if __name__ == '__main__':
    main()
