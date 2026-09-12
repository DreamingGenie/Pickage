"""Bounded H6 preparation from a completed historical run, without publishing to DB."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical_artifact import _path, _read_json, _publish_json
from . import historical_parallel as producer
from . import historical_parallel_input as inputs
from . import historical_parallel_writer as writer

MAX_ROWS = 100_000


def validate_scope(names, dates):
    if (not isinstance(names, list) or not 1 <= len(names) <= 32
            or any(not isinstance(n, str) or not n or n != n.strip() or '\x00' in n or len(n) > 300 for n in names)
            or len(set(names)) != len(names)):
        raise ValueError('Specify 1..32 unique package names')
    if (not isinstance(dates, list) or not 1 <= len(dates) <= 4
            or any(not isinstance(d, str) for d in dates) or len(set(dates)) != len(dates)):
        raise ValueError('Specify 1..4 unique snapshot dates')
    if any(date.fromisoformat(d).isoformat() != d for d in dates):
        raise ValueError('Use ISO snapshot dates')
    return sorted(names), sorted(dates)


def validate_catalog(identities, counts, catalog):
    """Require the same package identity, rather than guessing or silently remapping IDs."""
    expected = {(r['package_id'], r['name']) for r in identities}
    packages = catalog['packages']
    if (len(packages) != len(expected) or len({r['package_id'] for r in packages}) != len(packages)
            or len({r['name'] for r in packages}) != len(packages)
            or {(r['package_id'], r['name']) for r in packages} != expected):
        raise ValueError('DB package ID/name does not match the calculation input')
    versions = {(r['package_id'], r['version']) for r in catalog['versions']}
    snapshots = {r['snapshot_at'] for r in catalog['snapshots']}
    if any((r['package_id'], r['version']) not in versions for r in counts):
        raise ValueError('DB version composite key is missing')
    if any(r['snapshot_at'] not in snapshots for r in counts):
        raise ValueError('DB snapshot date is missing')


def _source(con, run_dir, digest):
    root = _path(run_dir)
    if file_sha256(root / 'run_manifest.json') != digest:
        raise ValueError('Completed run manifest SHA mismatch')
    run, plan = _read_json(root / 'run_manifest.json'), _read_json(root / 'run_plan.json')
    if (run.get('run_status') != 'COMPLETE' or run.get('full_selection_executed') is not True
            or run.get('scope') != 'FULL_SELECTED' or run.get('ready_for_load') is not False
            or run.get('upstream_resolution_status') != 'PARTIAL'
            or plan.get('generation_contract') != producer.contract()
            or run.get('plan_sha256') != sha256(plan) or plan.get('history_layout') != 'grouped'):
        raise ValueError('Expected the unchanged, completed FULL_SELECTED CPU grouped run')
    prepared = _path(_read_json(root / 'input_location.json')['prepared_dir'])
    im = inputs._manifest(prepared, plan['input_manifest_sha256'])
    if im['scope'] != 'FULL_SELECTED' or im['calendar'] != plan['calendar']:
        raise ValueError('Prepared input scope/calendar mismatch')
    cache = producer.old._within(root, run['cache']['directory']) / 'cache'
    history = _path(run['history']['run_dir'])
    if history != cache.parent / 'history' or run['history']['run_status'] != 'COMPLETE':
        raise ValueError('Unexpected history location or status')
    writer.open_counts(con, history, run['history']['run_manifest_sha256'])
    hm, hp = _read_json(history / 'run_manifest.json'), _read_json(history / 'run_plan.json')
    if (hp['calendar'] != plan['calendar'] or _path(hp['cache_dir']) != cache
            or hp['cache_manifest_sha256'] != run['cache']['cache_sha256']):
        raise ValueError('History lineage differs from completed run')
    con.read_parquet(str(writer._file(history, hm['quality']['name'])), hive_partitioning=False).create_view('source_quality')
    return prepared, im, {'run_dir': str(root), 'run_manifest_sha256': digest,
                         'input_manifest_sha256': plan['input_manifest_sha256'],
                         'history_manifest_sha256': run['history']['run_manifest_sha256']}


def _selected_inputs(con, prepared, manifest, names):
    files = {table: [] for table in ('target_names', 'target_population')}
    remaining = set(names)
    for key, part in manifest['partitions'].items():
        selected = remaining.intersection(part['names'])
        if not selected:
            continue
        if part['status'] != 'READY':
            raise ValueError('Selected package has no prepared partition')
        for table in files:
            record = part['files'][table]
            if record['name'] != f'partition={key}/{table}.parquet':
                raise ValueError('Unexpected input shard path')
            path = _path(prepared / record['name'])
            if {**inputs._record(path, con), 'name': record['name']} != record:
                raise ValueError('Selected input shard changed')
            files[table].append(str(path))
        remaining -= selected
    if remaining:
        raise ValueError('Package name is outside the pinned selection')
    con.read_parquet(files['target_names'], hive_partitioning=False).create_view('pilot_names_raw')
    con.read_parquet(files['target_population'], hive_partitioning=False).create_view('pilot_targets_raw')
    con.execute('CREATE TEMP TABLE chosen_names(name VARCHAR PRIMARY KEY)')
    con.executemany('INSERT INTO chosen_names VALUES (?)', [(n,) for n in names])
    con.execute('CREATE TEMP TABLE pilot_names AS SELECT r.package_id,r.name FROM pilot_names_raw r JOIN chosen_names USING(name)')
    con.execute('CREATE TEMP TABLE pilot_targets AS SELECT t.* FROM pilot_targets_raw t JOIN chosen_names USING(name)')
    rows = con.execute('SELECT package_id,name FROM pilot_names ORDER BY name').fetchall()
    if len(rows) != len(names) or any(r[0] is None for r in rows) or len({r[0] for r in rows}) != len(rows):
        raise ValueError('Selected package has no unique mapped input ID')
    return [{'package_id': i, 'name': n} for i, n in rows]


def restore_counts(con, calendar, dates):
    """Expand only the requested dates, from the verified eligible target population."""
    days = {r['snapshot_at']: (i, r['snapshot_timestamp']) for i, r in enumerate(calendar)}
    if not set(dates) <= days.keys():
        raise ValueError('Snapshot is outside the calculation calendar')
    con.execute('CREATE TEMP TABLE pilot_dates(snapshot_at DATE PRIMARY KEY,snapshot_index INTEGER,snapshot_timestamp TIMESTAMPTZ)')
    con.executemany('INSERT INTO pilot_dates VALUES (?,?,?)', [(d, *days[d]) for d in dates])
    n = con.execute('SELECT count(*) FROM pilot_targets t JOIN pilot_dates d ON t.birth_index<=d.snapshot_index').fetchone()[0]
    if not 1 <= n <= MAX_ROWS:
        raise ValueError('Pilot must contain 1..100000 eligible version/date rows')
    con.execute('CREATE TEMP TABLE pilot_positive AS SELECT c.* FROM counts c '
                'JOIN pilot_names p USING(package_id) JOIN pilot_dates d USING(snapshot_at)')
    if con.execute('SELECT EXISTS(SELECT 1 FROM pilot_positive p LEFT JOIN pilot_targets t '
                   'ON p.package_id=t.package_id AND p.version=t.version JOIN pilot_dates d USING(snapshot_at) '
                   'WHERE t.package_id IS NULL OR t.birth_index>d.snapshot_index OR p.dependents_count IS NULL '
                   'OR p.dependents_count<=0 OR p.dependents_count>2147483647 '
                   'OR p.snapshot_timestamp IS DISTINCT FROM d.snapshot_timestamp)').fetchone()[0]:
        raise ValueError('Positive count is not a valid eligible version/date row')
    if con.execute('SELECT EXISTS(SELECT 1 FROM pilot_positive GROUP BY package_id,version,snapshot_at HAVING count(*)>1)').fetchone()[0]:
        raise ValueError('Duplicate positive count key')
    con.execute('CREATE TEMP TABLE pilot_counts AS SELECT t.package_id,t.version,d.snapshot_at,'
                'coalesce(p.dependents_count,0)::INTEGER dependents_count FROM pilot_targets t '
                'JOIN pilot_dates d ON t.birth_index<=d.snapshot_index LEFT JOIN pilot_positive p '
                'ON p.package_id=t.package_id AND p.version=t.version AND p.snapshot_at=d.snapshot_at')
    records = con.execute('SELECT package_id,version,snapshot_at::VARCHAR,dependents_count FROM pilot_counts '
                          'ORDER BY package_id,version,snapshot_at').fetchall()
    if len(records) != n or len({r[:3] for r in records}) != n:
        raise ValueError('Eligible target coverage is not unique')
    return [dict(zip(('package_id', 'version', 'snapshot_at', 'dependents_count'), r)) for r in records]


def prepare_sample(*, run_dir, manifest_sha256, names, dates, db_command, output):
    from .historical_db_probe import read_catalog
    names, dates = validate_scope(names, dates)
    root = _path(output)
    if root.exists():
        raise ValueError('Sample output must be a new directory')
    generation = file_sha256(Path(__file__))
    with duckdb.connect(config={'threads': 2, 'memory_limit': '2GB'}) as con:
        con.execute("SET TimeZone='UTC'")
        prepared, manifest, source = _source(con, run_dir, manifest_sha256)
        for protected in (_path(run_dir).parent, prepared):
            if root.is_relative_to(protected) or protected.is_relative_to(root):
                raise ValueError('Sample output overlaps a preserved source directory')
        root.mkdir(parents=True, exist_ok=False)
        identities = _selected_inputs(con, prepared, manifest, names)
        counts = restore_counts(con, manifest['calendar'], dates)
        catalog = read_catalog(db_command, root, names, dates)
        validate_catalog(identities, counts, catalog)
        from .historical_db_probe import validate_rows
        validate_rows(counts, identities)
        con.execute("COPY pilot_counts TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(root / 'counts.parquet')])
        con.execute('COPY (SELECT q.* FROM source_quality q JOIN pilot_dates d USING(snapshot_at)) '
                    'TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(root / 'source_quality.parquet')])
        if con.execute('SELECT count(*) FROM read_parquet(?)', [str(root / 'source_quality.parquet')]).fetchone()[0] != len(dates):
            raise ValueError('Missing source quality date')
        quality_status = con.execute('SELECT DISTINCT calculation_status,resolution_status,ready_for_load '
                                     'FROM read_parquet(?)', [str(root / 'source_quality.parquet')]).fetchall()
        if any(r[0] != 'COMPLETE' or r[1] not in ('PARTIAL', 'COMPLETE') or r[2] is not False for r in quality_status):
            raise ValueError('Unexpected source resolution quality')
        if file_sha256(Path(__file__)) != generation:
            raise ValueError('Preparation generation changed')
        # Recheck the exact source metadata and used files before publishing the sample.
        _source(con, run_dir, manifest_sha256)
        for key, part in manifest['partitions'].items():
            if set(names).intersection(part['names']):
                for role in ('target_names', 'target_population'):
                    r = part['files'][role]
                    if file_sha256(prepared / r['name']) != r['sha256']:
                        raise ValueError('Selected source changed during preparation')
        result = {'format': 'historical-db-pilot-v1', 'status': 'PREPARED', 'source': source,
                  'names': names, 'dates': dates, 'identities': identities, 'rows': len(counts),
                  'positive_rows': sum(r['dependents_count'] > 0 for r in counts),
                  'zero_rows': sum(r['dependents_count'] == 0 for r in counts),
                  'catalog_sha256': sha256(catalog), 'catalog_check': 'EXACT_ID_NAME_VERSION_DATE',
                  'source_quality_scope': 'FULL_SELECTED_DATE_QUALITY_NOT_PILOT_ONLY',
                  'resolution_status': 'PARTIAL', 'ready_for_load': False,
                  'generation_sha256': generation,
                  'files': [inputs._record(root / f, con) for f in ('counts.parquet', 'source_quality.parquet')]}
    _publish_json(root / 'sample_manifest.json', result)
    return result
