"""Publish explicitly reconstructed historical rows without changing observed loaders."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

import duckdb

from pipeline.downloads.bronze import _file_hash, _read, _verify_remote
from pipeline.postgresql.input import _sql_path
from .history_policy import policy_document, policy_sha256
from .policy import canonical_bytes
from .postgres import PackageSnapshotLoader
from .quality import normalize_quality, validate_quality


class HistorySnapshotLoader(PackageSnapshotLoader):
    def _send(self, sql):
        if sql.strip() == 'COMMIT;':
            self.phase = 'COMMIT_SENT'
        return super()._send(sql)

    def _lineage(self):
        m, q = self._metadata, self._literal
        manifest = m['manifest']
        if (manifest.get('history_policy') != policy_document() or
                manifest.get('history_policy_sha256') != policy_sha256()):
            raise ValueError('history reconstruction policy is not approved')
        sources = manifest['input_manifest']
        base, interval = sources['population'], manifest['interval']
        self._require(
            "EXISTS(SELECT 1 FROM public.etl_dataset_current c JOIN public.etl_load_execution e "
            "ON e.execution_id=c.execution_id WHERE c.dataset='package-version' AND e.status='PUBLISHED' "
            f"AND c.manifest_sha256={q(base['manifest_sha256'])} "
            f"AND e.manifest_sha256={q(base['manifest_sha256'])} "
            f"AND e.curated_run_id={q(base['run_id'])} AND c.snapshot_at={q(base['snapshot'])}::date "
            f"AND e.snapshot_at={q(base['snapshot'])}::date "
            f"AND e.snapshot_timestamp={q(base['snapshot_timestamp'])}::timestamp)",
            'history base population differs from approved package-version current input')
        if m['snapshot'] >= base['snapshot']:
            raise ValueError('history loader accepts dates before the preserved base snapshot only')
        previous = interval['previous_snapshot_at']
        previous_check = '' if previous is None else (
            ' AND EXISTS(SELECT 1 FROM public.etl_snapshot_reference p WHERE p.execution_id=r.execution_id '
            f"AND p.snapshot_at={q(previous)}::date "
            f"AND p.snapshot_timestamp={q(interval['previous_snapshot_timestamp'])}::timestamptz)")
        self._require(
            "EXISTS(SELECT 1 FROM public.etl_snapshot_reference r JOIN public.etl_load_execution e "
            "ON e.execution_id=r.execution_id WHERE e.dataset='snapshot-reference' AND e.status='PUBLISHED' "
            f"AND e.manifest_sha256={q(sources['candidate']['sha256'])} "
            f"AND r.snapshot_at={q(m['snapshot'])}::date "
            f"AND r.snapshot_timestamp={q(interval['snapshot_timestamp'])}::timestamptz "
            f"AND r.previous_snapshot_at IS NOT DISTINCT FROM {q(previous)}::date{previous_check})",
            'history calendar or exact source observation time differs from approved reference')


def prepare_copy(files, manifest, work_dir, *, memory='8GB', threads=4):
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    rows = manifest['counts']['package_snapshot']
    day, instant = manifest['snapshot'], manifest['interval']['snapshot_timestamp']
    csv_files = {}
    with duckdb.connect(config={'memory_limit': memory, 'threads': threads}) as con:
        con.execute("SET TimeZone='UTC'")
        for role in ('package_snapshot', 'package_identity', 'quality'):
            path = Path(files[role])
            view = 'quality_raw' if role == 'quality' else role
            con.execute(f'CREATE VIEW {view} AS SELECT * FROM read_parquet({_sql_path(path)},hive_partitioning=false)')
            if con.execute(f'SELECT count(*) FROM {view}').fetchone()[0] != rows:
                raise ValueError('history output row count mismatch: ' + role)
            if con.execute(f'SELECT EXISTS(SELECT package_id FROM {view} GROUP BY 1 HAVING count(*)<>1)').fetchone()[0]:
                raise ValueError('duplicate history package key: ' + role)
        normalize_quality(con, manifest, producer='history')
        validate_quality(con, manifest, producer='history')
        expected_schema = [('package_id', 'INTEGER'), ('snapshot_at', 'DATE'), ('downloads', 'BIGINT'),
                           ('stars', 'INTEGER'), ('open_issues', 'INTEGER')]
        schema = [(r[0], r[1]) for r in con.execute('DESCRIBE package_snapshot').fetchall()]
        if schema != expected_schema:
            raise ValueError('history service schema differs from DDL')
        if con.execute('SELECT EXISTS(SELECT 1 FROM package_snapshot s FULL JOIN package_identity p USING(package_id) '
                       'WHERE s.package_id IS NULL OR p.package_id IS NULL OR p.package_id<=0 OR p.name IS NULL '
                       "OR p.name='' OR contains(p.name,chr(0)))").fetchone()[0]:
            raise ValueError('history output identity mismatch')
        if con.execute('SELECT EXISTS(SELECT name FROM package_identity GROUP BY 1 HAVING count(*)<>1)').fetchone()[0]:
            raise ValueError('duplicate history name')
        if con.execute('SELECT EXISTS(SELECT 1 FROM package_snapshot s FULL JOIN quality q USING(package_id) '
                       'WHERE s.package_id IS NULL OR q.package_id IS NULL '
                       'OR s.snapshot_at IS DISTINCT FROM ?::DATE OR q.snapshot_at IS DISTINCT FROM ?::DATE '
                       'OR ROW(s.downloads,s.stars,s.open_issues) IS DISTINCT FROM ROW(q.download_sum,q.stars,q.open_issues) '
                       'OR s.downloads<0 OR s.stars<0 OR s.open_issues<0 '
                       'OR q.first_published_at IS NULL OR q.first_published_at>?::TIMESTAMPTZ '
                       'OR q.selected_published_at>?::TIMESTAMPTZ '
                       'OR (q.repository_observed_timestamp IS NOT NULL AND q.repository_observed_timestamp<>?::TIMESTAMPTZ) '
                       'OR (q.repository_repo_url IS NOT NULL AND q.selected_published_at IS NULL) '
                       'OR q.valid_days IS NULL OR q.observed_days IS NULL OR q.valid_days<0 '
                       'OR q.expected_days IS DISTINCT FROM ?::INTEGER '
                       'OR q.valid_days>q.observed_days OR q.observed_days>q.expected_days '
                       'OR (q.download_sum IS NULL) IS DISTINCT FROM (q.valid_days=0) '
                       'OR (q.null_reason IS NOT NULL) IS DISTINCT FROM (q.valid_days=0) '
                       "OR q.data_status IS DISTINCT FROM CASE WHEN q.valid_days=0 THEN 'UNAVAILABLE' "
                       "WHEN q.valid_days=q.expected_days THEN 'COMPLETE' ELSE 'PARTIAL' END)",
                       [day, day, instant, instant, instant, manifest['interval']['interval_days']]).fetchone()[0]:
            raise ValueError('history service, eligibility, coverage or quality mismatch')
        values = con.execute('SELECT count(downloads),count(stars),count(open_issues),'
                             'cast(sum(downloads) AS VARCHAR),cast(sum(stars) AS VARCHAR),'
                             'cast(sum(open_issues) AS VARCHAR) FROM package_snapshot').fetchone()
        validation = {'rows': rows, 'nonnull': dict(zip(('downloads', 'stars', 'open_issues'), values[:3])),
                      'sums': dict(zip(('downloads', 'stars', 'open_issues'), values[3:])),
                      'verification': 'ALL_KEYS_VALUES_ELIGIBILITY_COVERAGE_AND_QUALITY'}
        for role, columns in (('package_snapshot', [r[0] for r in expected_schema]),
                              ('package_identity', ['package_id', 'name'])):
            expressions = []
            for column in columns:
                value = f'CAST({column} AS VARCHAR)'
                for char, escaped in ((92, 92), (9, 't'), (10, 'n'), (13, 'r')):
                    suffix = f'chr({escaped})' if isinstance(escaped, int) else f"'{escaped}'"
                    value = f'replace({value},chr({char}),chr(92)||{suffix})'
                expressions.append(value)
            path = work_dir / (role + '.copy.tsv')
            con.execute(f"COPY (SELECT {','.join(expressions)} FROM {role}) TO {_sql_path(path)} "
                        "(FORMAT CSV, DELIMITER '\\t', QUOTE '', ESCAPE '', HEADER false, NULL '\\N')")
            csv_files[role] = [path]
    return {'csv_files': csv_files, 'validation': validation}


def verify_publication(s3, prefix, manifest):
    digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    if (_read(s3, 'pickage-curated', prefix + '/run_manifest.json') != canonical_bytes(manifest) or
            _read(s3, 'pickage-curated', prefix + '/_SUCCESS') != (digest + '\n').encode()):
        raise ValueError('history output approval changed')
    for record in manifest['files']:
        _verify_remote(s3, 'pickage-curated', prefix + '/data/' + record['path'], record['bytes'], record['sha256'])
    return digest


def load_snapshot(s3, *, prefix, manifest, files, work_dir, command, contract_hash, execution_id, copy_input=None):
    started = time.monotonic()
    work_dir = Path(work_dir) / uuid.uuid4().hex
    work_dir.mkdir(parents=True)
    for record in manifest['files']:
        size, sha = _file_hash(Path(files[record['role']]))
        if (size, sha) != (record['bytes'], record['sha256']):
            raise ValueError('local output SHA mismatch before COPY')
    digest = verify_publication(s3, prefix, manifest)
    prepared = copy_input or prepare_copy(files, manifest, work_dir)
    instant = datetime.fromisoformat(manifest['interval']['snapshot_timestamp'].replace('Z', '+00:00'))
    metadata = {'dataset': 'package-snapshot', 'snapshot': manifest['snapshot'],
                'snapshot_timestamp': instant.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
                'curated_run_id': manifest['run_id'], 'run_prefix': prefix, 'manifest_sha256': digest,
                'counts': manifest['counts'], 'manifest': manifest}
    attempt_id = work_dir.name
    with HistorySnapshotLoader(command, work_dir) as loader:
        loader.start(metadata, execution_id, contract_hash, attempt_id)
        try:
            result = loader.publish(prepared['csv_files'], before_commit=lambda: verify_publication(s3, prefix, manifest))
        except BaseException as exc:
            uncertain = loader.phase in ('COMMIT_SENT', 'VERIFY_COMMIT', 'COMPLETE')
            failure = {'snapshot': manifest['snapshot'], 'execution_id': execution_id, 'attempt_id': attempt_id,
                       'status': 'COMMITTED_UNVERIFIED' if uncertain else 'FAILED', 'phase': loader.phase,
                       'error_type': type(exc).__name__, 'error': str(exc),
                       'manifest_sha256': digest, 'elapsed_seconds': round(time.monotonic() - started, 3),
                       'recovery': 'Retry the same execution and immutable input to reconcile actual DB rows'}
            (work_dir / 'execution-report.json').write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding='utf-8')
            if not uncertain:
                loader.fail(exc)
            raise
    report = {'snapshot': manifest['snapshot'], 'execution_id': execution_id, 'attempt_id': attempt_id,
              'elapsed_seconds': round(time.monotonic() - started, 3), 'result': result,
              'validation': prepared['validation'], 'manifest_sha256': digest,
              'history_kind': policy_document()['history_kind']}
    (work_dir / 'execution-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
