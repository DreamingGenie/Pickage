"""Recompute [P,S) downloads for published package_snapshot dates and UPDATE only changed rows.

Production package_snapshot rows arrived by pg_dump (S15P21A506-341) without etl provenance, and
the inputs of the publication-date reconstruction (S15P21A506-288) no longer exist. The published
rows are therefore the authority for population, stars and open_issues; this module never assigns
those. It recomputes downloads from a wider daily Bronze run with the same [P,S) rule as
pipeline/downloads_interval/aggregate.py and updates only rows whose value changes (S15P21A506-453).
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

import duckdb

from pipeline.downloads.bronze import _file_hash
from pipeline.downloads_interval.aggregate import DATE_PART, MAX_BIGINT, quote, reject, require_schema
from .history_contract import _contract
from .policy import canonical_bytes
from .postgres import PackageSnapshotLoader

ROOT = Path(__file__).resolve().parents[2]
SAFE_ID = re.compile(r'[A-Za-z0-9_-]{1,60}')
PSQL_OPTIONS = ['-X', '-q', '-A', '-t', '-w', '-v', 'ON_ERROR_STOP=1', '-P', 'pager=off']
CONTRACT_FILES = ('pipeline/package_snapshot/downloads_reload.py', 'pipeline/downloads_interval/aggregate.py')
STAGING_COLUMNS = 'name,downloads,observed_days,valid_days'
# Verbatim from pipeline/downloads_interval/aggregate.py: the published values were produced by
# this rule, and the acceptance check below proves it against every existing non-NULL value.
DAILY_AGGREGATE_SQL = """CREATE TEMP TABLE daily_aggregate AS
            SELECT name,count(*)::INTEGER AS observed_days,
                   count(*) FILTER(WHERE downloads IS NOT NULL AND NOT imputed_gap)::INTEGER AS valid_days,
                   count(*) FILTER(WHERE downloads IS NULL)::INTEGER AS null_days,
                   count(*) FILTER(WHERE imputed_gap)::INTEGER AS gap_days,
                   sum(downloads::DECIMAL(38,0)) FILTER(WHERE downloads IS NOT NULL AND NOT imputed_gap) AS total
            FROM daily GROUP BY name"""


def policy_document():
    return {
        'policy_version': 'package-snapshot-downloads-reload-v1',
        'approval': 'Control tower approved a downloads-only UPDATE reload on 2026-09-22 (S15P21A506-453)',
        'population': 'The existing published rows of the target date are the population; no row is added or removed',
        'invariants': 'stars and open_issues are never assigned; row count and the (package_id,stars,open_issues) '
                      'fingerprint must be identical before and after',
        'interval': 'P is LAG(snapshot_at) over public.snapshot, the definition used by the backend DOWNLOADS_TREND_SQL',
        'downloads': 'Same [P,S) rule as pipeline/downloads_interval/aggregate.py: sum of valid daily values '
                     '(not NULL, not imputed_gap); NULL when valid_days=0; an actual zero stays zero',
        'acceptance': 'Every existing non-NULL downloads value must equal its recomputed value before any UPDATE; '
                      'one difference stops the date without changes',
        'update': 'UPDATE ... SET downloads only where the stored value IS DISTINCT FROM the recomputed value',
    }


def policy_sha256():
    return hashlib.sha256(canonical_bytes(policy_document())).hexdigest()


def contract_sha256():
    return _contract(CONTRACT_FILES, {'format': 'package-snapshot-downloads-reload-v1',
                                      'policy': policy_document(), 'duckdb': duckdb.__version__})


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
    result = subprocess.run(command + PSQL_OPTIONS, input=sql.encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-2500:])
    return json.loads(result.stdout.decode().strip() or 'null')


def calendar(command):
    """{snapshot_at: previous_at} with P = LAG(snapshot_at), exactly as the backend reads it."""
    rows = sql_json(command, "SELECT coalesce(json_agg(json_build_object('snapshot_at',snapshot_at,"
                             "'previous_at',previous_at) ORDER BY snapshot_at),'[]') FROM (SELECT snapshot_at,"
                             'LAG(snapshot_at) OVER (ORDER BY snapshot_at) previous_at FROM public.snapshot) c;')
    return {r['snapshot_at']: r['previous_at'] for r in rows}


def daily_partitions(daily_root, start, end):
    """Existing Hive partitions inside [start,end). Missing days make the sum PARTIAL, never fail."""
    root = Path(daily_root).resolve() / 'downloads'
    if not root.is_dir():
        raise ValueError('daily root has no downloads/ partition directory: ' + str(root))
    found = {}
    for entry in sorted(root.iterdir()):
        match = DATE_PART.search(entry.as_posix())
        if not entry.is_dir() or not match:
            continue
        day = date.fromisoformat(match.group(1))
        if start <= day < end:
            files = sorted(p for p in entry.iterdir() if p.is_file() and p.suffix == '.parquet')
            if not files:
                raise ValueError('daily partition without parquet files: ' + str(entry))
            found[day.isoformat()] = files
    return found


def recompute(daily_root, interval, out_dir, *, memory='4GB', threads=4):
    """Write a COPY staging file (name, downloads, observed_days, valid_days) for one date."""
    end = date.fromisoformat(interval['snapshot_at'])
    start = date.fromisoformat(interval['previous_snapshot_at'])
    if start >= end:
        raise ValueError('snapshot interval must be positive')
    status_path = Path(daily_root).resolve() / 'downloads_status.parquet'
    if not status_path.is_file():
        raise ValueError('missing downloads_status.parquet under daily root')
    partitions = daily_partitions(daily_root, start, end)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = out_dir / 'downloads_input.copy.tsv'
    with duckdb.connect(config={'memory_limit': memory, 'threads': threads}) as con:
        con.execute(f"SET temp_directory={quote(out_dir / 'tmp')}")
        con.execute(f'CREATE TEMP TABLE statuses AS SELECT * FROM read_parquet({quote(status_path)}, hive_partitioning=false)')
        require_schema(con, 'statuses', {'name': 'VARCHAR', 'status': 'VARCHAR'})
        reject(con, "SELECT 1 FROM statuses WHERE name IS NULL OR name='' OR status IS NULL OR status NOT IN ('READY','NOT_FOUND')", 'invalid status row')
        reject(con, 'SELECT name FROM statuses GROUP BY name HAVING count(*)>1', 'duplicate status name')
        daily_selects = []
        for day, files in partitions.items():
            for path in files:
                con.execute(f'CREATE OR REPLACE TEMP VIEW one_daily AS SELECT * FROM read_parquet({quote(path)}, hive_partitioning=false)')
                columns = require_schema(con, 'one_daily', {'name': 'VARCHAR', 'downloads': 'BIGINT', 'imputed_gap': 'BOOLEAN'})
                if 'date' in columns:
                    require_schema(con, 'one_daily', {'date': 'DATE'})
                    reject(con, f"SELECT 1 FROM one_daily WHERE date IS NULL OR date<>DATE '{day}'", 'physical daily date differs from Hive date')
                daily_selects.append(f"SELECT name,downloads,imputed_gap,DATE '{day}' AS date FROM read_parquet({quote(path)}, hive_partitioning=false)")
        if daily_selects:
            con.execute('CREATE TEMP TABLE daily AS ' + ' UNION ALL '.join(daily_selects))
        else:
            con.execute('CREATE TEMP TABLE daily(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN,date DATE)')
        reject(con, "SELECT 1 FROM daily WHERE name IS NULL OR name='' OR imputed_gap IS NULL OR downloads<0", 'invalid daily name, negative value, or NULL imputed_gap')
        reject(con, 'SELECT name,date FROM daily GROUP BY name,date HAVING count(*)>1', 'duplicate daily (name,date)')
        reject(con, "SELECT d.name FROM daily d LEFT JOIN statuses s USING(name) WHERE s.name IS NULL OR s.status<>'READY'", 'daily name has no READY status (unknown or NOT_FOUND)')
        con.execute(DAILY_AGGREGATE_SQL)
        reject(con, f'SELECT name FROM daily_aggregate WHERE total>{MAX_BIGINT}', 'BIGINT sum overflow')
        expected_days = (end - start).days
        counts = con.execute(f"""SELECT count(*),count(total),
            count(*) FILTER(WHERE valid_days={expected_days}),
            count(*) FILTER(WHERE valid_days>0 AND valid_days<{expected_days}),
            count(*) FILTER(WHERE valid_days=0) FROM daily_aggregate""").fetchone()
        name = 'CAST(name AS VARCHAR)'
        for char, escaped in ((92, 92), (9, 't'), (10, 'n'), (13, 'r')):
            suffix = f'chr({escaped})' if isinstance(escaped, int) else f"'{escaped}'"
            name = f'replace({name},chr({char}),chr(92)||{suffix})'
        con.execute(f"COPY (SELECT {name},total::BIGINT,observed_days,valid_days FROM daily_aggregate ORDER BY name) "
                    f"TO {quote(staging)} (FORMAT CSV, DELIMITER '\\t', QUOTE '', ESCAPE '', HEADER false, NULL '\\N')")
    size, digest = _file_hash(staging)
    return {'file': str(staging), 'bytes': size, 'sha256': digest, 'rows': counts[0], 'nonnull': counts[1],
            'complete': counts[2], 'partial': counts[3], 'unavailable': counts[4],
            'expected_days': expected_days, 'daily_dates': sorted(partitions),
            'daily_files': [{'date': day, 'path': str(p), **dict(zip(('bytes', 'sha256'), _file_hash(p)))}
                            for day, files in partitions.items() for p in files]}


class DownloadsReloadLoader(PackageSnapshotLoader):
    """Registers like every package-snapshot execution, but publishes an UPDATE of downloads only."""

    def _send(self, sql):
        if sql.strip() == 'COMMIT;':
            self.phase = 'COMMIT_SENT'
        return super()._send(sql)

    def _copy_staging(self, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or not path.name.endswith('.copy.tsv'):
            raise ValueError('expected regular COPY text file')
        process = self._process
        with path.open('rb') as source:
            process.stdin.write((f'COPY pg_temp.downloads_input ({STAGING_COLUMNS}) '
                                 "FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');\n").encode())
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                process.stdin.write(chunk)
            process.stdin.write(b'\\.\n')
            process.stdin.flush()
        self._send('SELECT 1;')

    def _measure(self, snapshot):
        return json.loads(self._send(
            "SELECT json_build_object('rows',count(*),'nonnull',count(downloads),'fingerprint',"
            "coalesce(sum(('x'||substr(md5(package_id::text||'|'||coalesce(stars::text,'NULL')||'|'||"
            "coalesce(open_issues::text,'NULL')),1,16))::bit(64)::bigint::numeric),0)::text) "
            f'FROM public.package_snapshot WHERE snapshot_at={snapshot}::date;')[0])

    def _sizes(self):
        heap, index = self._send("SELECT pg_relation_size('public.package_snapshot'),"
                                 "pg_indexes_size('public.package_snapshot');")[0].split('|')
        return {'heap_bytes': int(heap), 'index_bytes': int(index)}

    def reload(self, staging, *, interval, verify_only=False, vacuum=True, failpoint=None):
        if not self._registered:
            raise RuntimeError('start() must be called before reload()')
        if failpoint not in (None, 'after_update'):
            raise ValueError('unknown failpoint')
        m, q = self._metadata, self._literal
        expected, snapshot = m['counts']['package_snapshot'], q(m['snapshot'])
        previous = interval['previous_snapshot_at']
        reverify = self._already_published
        self._phase('COPY')
        self._send('CREATE TEMP TABLE downloads_input (name text NOT NULL,downloads bigint CHECK(downloads>=0),'
                   'observed_days int NOT NULL,valid_days int NOT NULL CHECK(valid_days>=0));')
        self._copy_staging(staging['file'])
        self._phase('VALIDATE_STAGING')
        self._send('CREATE UNIQUE INDEX ON downloads_input(name); ANALYZE downloads_input;')
        self._require(f"(SELECT count(*) FROM pg_temp.downloads_input)={staging['rows']}", 'staging count mismatch')
        self._require('NOT EXISTS (SELECT 1 FROM pg_temp.downloads_input WHERE (downloads IS NULL)<>(valid_days=0) '
                      'OR valid_days>observed_days)', 'staging coverage mismatch')
        self._phase('PUBLISH')
        sizes_before = self._sizes()
        self._send('BEGIN; LOCK TABLE public.package IN SHARE MODE; LOCK TABLE public.snapshot IN SHARE MODE; '
                   'LOCK TABLE public.package_snapshot,public.etl_load_execution,public.etl_load_attempt,'
                   'public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;')
        self._require("(SELECT count(*) FROM (VALUES ('package_id','integer',true),"
                      "('snapshot_at','date',true),('downloads','bigint',false),"
                      "('stars','integer',false),('open_issues','integer',false)) "
                      "AS expected(name,type_name,not_null) JOIN pg_attribute a "
                      "ON a.attrelid='public.package_snapshot'::regclass AND a.attname=expected.name "
                      "WHERE a.attnum>0 AND NOT a.attisdropped "
                      "AND format_type(a.atttypid,a.atttypmod)=expected.type_name "
                      "AND a.attnotnull=expected.not_null)=5",
                      'service schema differs from package-snapshot contract')
        self._require('(SELECT previous_at FROM (SELECT snapshot_at,LAG(snapshot_at) OVER (ORDER BY snapshot_at) '
                      f'previous_at FROM public.snapshot) c WHERE snapshot_at={snapshot}::date) '
                      f'IS NOT DISTINCT FROM {q(previous)}::date', 'snapshot calendar changed: previous date differs')
        before = self._measure(snapshot)
        if before['rows'] != expected:
            raise ValueError('published row count differs from registered population')
        acceptance = json.loads(self._send(
            "SELECT json_build_object('matched',count(*),"
            "'mismatched',count(*) FILTER (WHERE s.downloads IS NOT NULL AND s.downloads IS DISTINCT FROM i.downloads),"
            "'to_update',count(*) FILTER (WHERE s.downloads IS DISTINCT FROM i.downloads),"
            "'newly_filled',count(*) FILTER (WHERE s.downloads IS NULL AND i.downloads IS NOT NULL),"
            "'kept_equal',count(*) FILTER (WHERE s.downloads IS NOT NULL AND s.downloads=i.downloads)) "
            'FROM pg_temp.downloads_input i JOIN public.package p ON p.name=i.name '
            f'JOIN public.package_snapshot s ON s.package_id=p.package_id AND s.snapshot_at={snapshot}::date;')[0])
        missing = int(self._send(
            f'SELECT count(*) FROM public.package_snapshot s WHERE s.snapshot_at={snapshot}::date '
            'AND s.downloads IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.package p '
            'JOIN pg_temp.downloads_input i ON i.name=p.name WHERE p.package_id=s.package_id);')[0])
        acceptance.update(existing_nonnull=before['nonnull'], existing_nonnull_missing_from_staging=missing,
                          staging_rows=staging['rows'], staging_unmatched=staging['rows'] - acceptance['matched'])
        # Acceptance: the values the service already shows are the answer key for the shared rule.
        if missing or acceptance['mismatched']:
            raise ValueError('recomputed downloads differ from published values: '
                             f"mismatched={acceptance['mismatched']} missing_from_staging={missing}")
        if reverify and acceptance['to_update']:
            raise ValueError('published reload values differ from recomputation: '
                             f"to_update={acceptance['to_update']}")
        updated = 0
        if not reverify and acceptance['to_update']:
            updated = int(self._send(
                'WITH u AS (UPDATE public.package_snapshot s SET downloads=i.downloads '
                'FROM public.package p,pg_temp.downloads_input i WHERE p.name=i.name AND s.package_id=p.package_id '
                f'AND s.snapshot_at={snapshot}::date AND s.downloads IS DISTINCT FROM i.downloads RETURNING 1) '
                'SELECT count(*) FROM u;')[0])
            if updated != acceptance['to_update']:
                raise ValueError('UPDATE row count differs from planned changes')
        if failpoint == 'after_update':
            raise RuntimeError('injected failure after_update')
        after = self._measure(snapshot)
        if after['rows'] != before['rows'] or after['fingerprint'] != before['fingerprint']:
            raise ValueError('row count or stars/open_issues changed during reload')
        if after['nonnull'] != before['nonnull'] + (0 if reverify else acceptance['newly_filled']):
            raise ValueError('downloads fill count differs from planned changes')
        self._counts = {'package_snapshot': expected, 'updated': updated, 'verified_rows': after['rows']}
        quality = {'policy': policy_document()['policy_version'], 'acceptance': acceptance,
                   'downloads_nonnull_before': before['nonnull'], 'downloads_nonnull_after': after['nonnull'],
                   'changed_rows': updated, 'rows_identical': True, 'stars_open_issues_identical': True,
                   'fingerprint': after['fingerprint'],
                   'staging': {k: staging[k] for k in ('rows', 'nonnull', 'complete', 'partial', 'unavailable',
                                                       'expected_days', 'daily_dates', 'sha256')},
                   'verification_scope': 'ALL_ROWS_OF_DATE_FINGERPRINT_AND_ALL_EXISTING_NONNULL_VALUES'}
        if verify_only:
            self._send('ROLLBACK;')
            self.phase = 'VERIFY_ONLY'
            self.record_quality(quality)
            self.fail(RuntimeError('verify-only: all checks passed; transaction rolled back'))
            self.phase = 'COMPLETE'
            return {'status': 'VERIFIED_ROLLED_BACK', 'action': 'VERIFY_ONLY', 'counts': self._counts,
                    'quality': quality, 'execution_id': self._execution_id, 'attempt_id': self._attempt_id}
        state = 'REVERIFIED' if reverify else 'PUBLISHED'
        first_counts = '' if self._already_published else f',actual_counts={q(self._counts)}'
        self._send("UPDATE public.etl_load_attempt SET "
                   f"status={q(state)},phase='COMMIT',actual_counts={q(self._counts)},quality_report={q(quality)},"
                   f"completed_at=clock_timestamp() WHERE attempt_id={q(self._attempt_id)} AND status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='PUBLISHED',error_message=NULL,"
                   f"updated_at=clock_timestamp(){first_counts} WHERE execution_id={q(self._execution_id)} "
                   f"AND active_attempt_id={q(self._attempt_id)};")
        if not self._already_published:
            self._send('INSERT INTO public.etl_dataset_current '
                       '(dataset,execution_id,snapshot_at,manifest_sha256,manifest) VALUES (' +
                       ','.join(q(v) for v in ('package-snapshot', self._execution_id, m['snapshot'],
                                              m['manifest_sha256'], m['manifest'])) +
                       ') ON CONFLICT(dataset) DO UPDATE SET execution_id=EXCLUDED.execution_id,'
                       'snapshot_at=EXCLUDED.snapshot_at,manifest_sha256=EXCLUDED.manifest_sha256,'
                       'manifest=EXCLUDED.manifest,published_at=clock_timestamp() '
                       'WHERE etl_dataset_current.snapshot_at<=EXCLUDED.snapshot_at;')
        self._send('COMMIT;')
        self.phase = 'VERIFY_COMMIT'
        proof = json.loads(self._one_shot("SELECT json_build_object('database',current_database(),"
            "'status',e.status,'attempt_status',a.status,'actual_counts',a.actual_counts) "
            'FROM public.etl_load_execution e JOIN public.etl_load_attempt a '
            f'ON a.attempt_id=e.active_attempt_id WHERE e.execution_id={q(self._execution_id)};'))
        if proof['status'] != 'PUBLISHED' or proof['attempt_status'] != state:
            raise RuntimeError('post-commit execution verification failed')
        maintenance = {'vacuum': False, 'sizes_before': sizes_before, 'sizes_after_commit': self._sizes()}
        if vacuum and updated:
            self.phase = 'VACUUM'
            started = time.monotonic()
            self._send('VACUUM public.package_snapshot;')
            maintenance.update(vacuum=True, vacuum_seconds=round(time.monotonic() - started, 3),
                               sizes_after_vacuum=self._sizes())
        self.phase = 'COMPLETE'
        return {'status': 'PUBLISHED', 'action': state if reverify else 'UPDATED', 'counts': self._counts,
                'quality': quality, 'maintenance': maintenance, 'execution_id': self._execution_id,
                'attempt_id': self._attempt_id, 'db_verification': proof}


def reload_snapshot(*, snapshot, previous, rows, staging, bronze, run_id, work_dir, command, verify_only=False,
                    vacuum=True, failpoint=None):
    started = time.monotonic()
    work_dir = Path(work_dir)
    attempt_id = uuid.uuid4().hex
    (work_dir / 'postgresql').mkdir(parents=True, exist_ok=True)
    manifest = {'dataset': 'package-snapshot', 'format_version': 1, 'mode': 'DOWNLOADS_RELOAD',
                'policy': policy_document(), 'policy_sha256': policy_sha256(), 'reload_run_id': run_id,
                'snapshot': snapshot,
                'interval': {'previous_snapshot_at': previous, 'snapshot_at': snapshot,
                             'expected_days': staging['expected_days'], 'daily_dates': staging['daily_dates']},
                'bronze': bronze,
                'daily_files': [{k: r[k] for k in ('date', 'bytes', 'sha256')} for r in staging['daily_files']],
                'snapshot_timestamp_note': 'No source observation time exists for a reload; midnight UTC of S is recorded',
                'counts': {'package_snapshot': rows, 'staging': staging['rows']}}
    metadata = {'dataset': 'package-snapshot', 'snapshot': snapshot, 'snapshot_timestamp': snapshot + 'T00:00:00',
                'curated_run_id': bronze['run_id'], 'run_prefix': bronze['prefix'],
                'manifest_sha256': bronze['manifest_sha256'], 'counts': {'package_snapshot': rows},
                'manifest': manifest}
    execution_id = f'reload-453-{run_id}-{snapshot}'
    with DownloadsReloadLoader(command, work_dir / 'postgresql') as loader:
        loader.start(metadata, execution_id, contract_sha256(), attempt_id)
        try:
            result = loader.reload(staging, interval={'previous_snapshot_at': previous, 'snapshot_at': snapshot},
                                   verify_only=verify_only, vacuum=vacuum, failpoint=failpoint)
        except BaseException as exc:
            uncertain = loader.phase in ('COMMIT_SENT', 'VERIFY_COMMIT', 'VACUUM', 'COMPLETE')
            # VACUUM runs after the verified COMMIT: the date is published even if maintenance failed.
            status = ('PUBLISHED_MAINTENANCE_FAILED' if loader.phase in ('VACUUM', 'COMPLETE')
                      else 'COMMITTED_UNVERIFIED' if uncertain else 'FAILED')
            failure = {'snapshot': snapshot, 'execution_id': execution_id, 'attempt_id': attempt_id,
                       'status': status, 'phase': loader.phase,
                       'error_type': type(exc).__name__, 'error': str(exc),
                       'elapsed_seconds': round(time.monotonic() - started, 3)}
            write_json(work_dir / 'report.json', failure)
            if not uncertain:
                loader.fail(exc)
            raise
    report = {'snapshot': snapshot, 'previous_snapshot_at': previous, 'rows': rows, 'execution_id': execution_id,
              'attempt_id': attempt_id, 'elapsed_seconds': round(time.monotonic() - started, 3), 'result': result}
    write_json(work_dir / 'report.json', report)
    return report


def run(*, daily_root, bronze, run_id, work_dir, command, snapshots=None, start=None, end=None,
        verify_only=False, vacuum=True, skip_published=False, memory='4GB', threads=4):
    if not SAFE_ID.fullmatch(run_id):
        raise ValueError('invalid reload run ID')
    if not re.fullmatch(r'[0-9a-f]{64}', bronze['manifest_sha256']):
        raise ValueError('bronze manifest SHA-256 must be 64 hex characters')
    began = time.monotonic()
    root = Path(work_dir).resolve() / run_id
    root.mkdir(parents=True, exist_ok=True)
    days = calendar(command)
    if snapshots:
        chosen = list(snapshots)
    else:
        chosen = [d for d in days if (start is None or d >= start) and (end is None or d <= end)]
    unknown = [d for d in chosen if d not in days]
    if unknown or not chosen:
        raise ValueError('requested dates are not in the snapshot calendar: ' + ','.join(unknown or ['(none)']))
    if any(days[d] is None for d in chosen):
        raise ValueError('the first calendar date has no [P,S) interval and cannot be reloaded')
    chosen = sorted(set(chosen), reverse=True)  # most recent first: an interruption keeps the recent trend
    published = set()
    if skip_published:
        published = set(sql_json(command, "SELECT coalesce(json_agg(snapshot_at),'[]') FROM public.etl_load_execution "
                                          "WHERE dataset='package-snapshot' AND status='PUBLISHED' AND execution_id LIKE "
                                          f"{quote('reload-453-' + run_id + '-%')};"))
    event('RELOAD_START', run_id=run_id, dates=len(chosen), verify_only=verify_only,
          skipping=len(published & set(chosen)))
    write_json(root / 'plan.json', {'run_id': run_id, 'bronze': bronze, 'daily_root': str(Path(daily_root).resolve()),
                                    'dates': chosen, 'verify_only': verify_only, 'contract_sha256': contract_sha256(),
                                    'policy_sha256': policy_sha256()})
    reports = []
    for day in chosen:
        if day in published:
            event('SNAPSHOT_SKIPPED_PUBLISHED', snapshot=day)
            continue
        previous = days[day]
        day_root = root / day
        event('SNAPSHOT_START', snapshot=day, previous=previous, completed=len(reports))
        rows = sql_json(command, f"SELECT count(*) FROM public.package_snapshot WHERE snapshot_at={quote(day)}::date;")
        if not rows:
            raise ValueError(f'{day} has no published rows to reload')
        recomputed = time.monotonic()
        staging = recompute(daily_root, {'previous_snapshot_at': previous, 'snapshot_at': day}, day_root / 'staging',
                            memory=memory, threads=threads)
        event('STAGING_READY', snapshot=day, staging_rows=staging['rows'], nonnull=staging['nonnull'],
              daily_dates=len(staging['daily_dates']), seconds=round(time.monotonic() - recomputed, 3))
        report = reload_snapshot(snapshot=day, previous=previous, rows=rows, staging=staging, bronze=bronze,
                                 run_id=run_id, work_dir=day_root, command=command, verify_only=verify_only,
                                 vacuum=vacuum)
        reports.append(report)
        result = report['result']
        event('SNAPSHOT_COMPLETE', snapshot=day, action=result['action'], rows=rows,
              changed_rows=result['counts']['updated'], nonnull_before=result['quality']['downloads_nonnull_before'],
              nonnull_after=result['quality']['downloads_nonnull_after'],
              maintenance=result.get('maintenance'), seconds=report['elapsed_seconds'])
    summary = {'status': 'VERIFIED_ROLLED_BACK' if verify_only else 'RELOADED', 'run_id': run_id,
               'dates': [r['snapshot'] for r in reports], 'rows': sum(r['rows'] for r in reports),
               'changed_rows': sum(r['result']['counts']['updated'] for r in reports),
               'elapsed_seconds': round(time.monotonic() - began, 3)}
    write_json(root / 'result.json', summary)
    event('RELOAD_COMPLETE', **summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daily-root', type=Path, required=True,
                        help='directory holding downloads/date=*/ partitions and downloads_status.parquet')
    parser.add_argument('--bronze-run-id', required=True, help='npm-downloads Bronze run that published --daily-root')
    parser.add_argument('--bronze-manifest-sha256', required=True)
    parser.add_argument('--run-id', required=True, help='identifier of this reload; part of every execution_id')
    parser.add_argument('--snapshots', nargs='+', help='explicit dates; default is the --from/--to range')
    parser.add_argument('--from', dest='start')
    parser.add_argument('--to', dest='end')
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'data/package_snapshot/downloads_reload')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--docker-container')
    target.add_argument('--psql')
    parser.add_argument('--database', required=True)
    parser.add_argument('--db-user', default='postgres')
    parser.add_argument('--memory', default='4GB')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--verify-only', action='store_true', help='run every check and the UPDATE, then ROLLBACK')
    parser.add_argument('--no-vacuum', action='store_true')
    parser.add_argument('--skip-published', action='store_true', help='resume: skip dates this run already published')
    args = parser.parse_args()
    if not SAFE_ID.fullmatch(args.database) or not SAFE_ID.fullmatch(args.db_user):
        parser.error('database and user must be simple names')
    if not SAFE_ID.fullmatch(args.bronze_run_id):
        parser.error('invalid Bronze run ID')
    if args.docker_container:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.docker_container):
            parser.error('invalid Docker container name')
        command = ['docker', 'exec', '-i', args.docker_container, 'psql']
    else:
        command = [args.psql]
    command += ['-U', args.db_user, '-d', args.database]
    bronze = {'run_id': args.bronze_run_id, 'prefix': 'npm-downloads/v1/run_id=' + args.bronze_run_id,
              'manifest_sha256': args.bronze_manifest_sha256}
    run(daily_root=args.daily_root, bronze=bronze, run_id=args.run_id, work_dir=args.work_dir, command=command,
        snapshots=args.snapshots, start=args.start, end=args.end, verify_only=args.verify_only,
        vacuum=not args.no_vacuum, skip_published=args.skip_published, memory=args.memory, threads=args.threads)


if __name__ == '__main__':
    main()
