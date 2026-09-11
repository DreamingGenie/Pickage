"""Check grouped stored rows with independent interval expansion and pinned cache totals."""
from __future__ import annotations
import uuid
from .historical_artifact import _path
from .historical_production_input import connection
from .historical_production_cache import verify_cache, verify_cache_bytes
from . import historical_parallel_writer as writer


def _compare(con, expected, actual):
    if con.execute('DESCRIBE ' + expected).fetchall() != con.execute('DESCRIBE ' + actual).fetchall():
        raise ValueError('Output schema differs')
    if con.execute(f'SELECT EXISTS ((SELECT * FROM {expected} EXCEPT ALL SELECT * FROM {actual}) UNION ALL '
                   f'(SELECT * FROM {actual} EXCEPT ALL SELECT * FROM {expected}))').fetchone()[0]:
        raise ValueError('Output values differ from pinned cache')


def check_counts(con, root, key, record):
    con.execute(f'''CREATE OR REPLACE TEMP VIEW grouped_expected_counts AS
        SELECT i.package_id,i.version,c.snapshot_at,c.snapshot_timestamp,i.dependents_count::INTEGER AS dependents_count
        FROM cache_counts i JOIN grouped_owners o USING(package_id)
        JOIN LATERAL UNNEST(range(i.start_index,i.end_index)) x(snapshot_index) ON true
        JOIN grouped_calendar c ON c.snapshot_index=x.snapshot_index
        WHERE o.partition_id={writer._literal(key)}''')
    if record is None:
        if con.execute('SELECT EXISTS(SELECT 1 FROM grouped_expected_counts)').fetchone()[0]:
            raise ValueError('Nonempty partition has no count file')
    else:
        con.read_parquet(str(writer._file(root, record['name'])), hive_partitioning=False).create_view('grouped_actual_counts', replace=True)
        _compare(con, 'grouped_expected_counts', 'grouped_actual_counts')


def check_quality(con, root, record):
    con.read_parquet(str(writer._file(root, record['name'])), hive_partitioning=False).create_view('grouped_actual_quality', replace=True)
    _compare(con, 'grouped_expected_quality', 'grouped_actual_quality')


def verify_history(*, run_dir, cache_dir, cache_sha256, run_manifest_sha256):
    root, cache_dir = _path(run_dir), _path(cache_dir)
    cache = verify_cache(cache_dir, cache_sha256)
    with connection(root / ('verify-' + uuid.uuid4().hex + '.duckdb')) as con:
        manifest, plan = writer._read_manifest(con, root, run_manifest_sha256)
        if plan != writer._plan(cache_dir, cache_sha256, cache, plan['partitions']):
            raise ValueError('History input identity differs')
        writer._load(con, cache_dir, cache, plan)
        for key, part in manifest['partitions'].items():
            check_counts(con, root, key, part['file'])
        writer._quality_expected(con, cache, plan)
        check_quality(con, root, manifest['quality'])
    verify_cache_bytes(cache_dir, cache_sha256, cache)
    if writer._contract() != plan['generation_contract']:
        raise ValueError('Generation changed during verification')
    return dict(run_status='COMPLETE', partitions_verified=len(manifest['partitions']),
                snapshots_verified=len(plan['calendar']), ready_for_load=False)
