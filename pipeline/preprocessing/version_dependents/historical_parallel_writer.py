"""Immutable partition files containing all dates, with independently checked receipts."""
from __future__ import annotations
import json
from pathlib import Path
import re
import uuid
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.preprocessing.version_dependents.historical_artifact import _path, _publish_json, _read_json, _run_lock, METRIC, MODE
from pipeline.preprocessing.version_dependents.historical_parallel_input import _record
from pipeline.preprocessing.version_dependents.historical_production_input import connection
from pipeline.preprocessing.version_dependents.historical_production_cache import verify_cache, verify_cache_bytes
from pipeline.preprocessing.version_dependents import historical_production_daily as daily

FORMAT = 'historical-parallel-history-v1'
COUNT_SCHEMA = [['package_id', 'INTEGER'], ['version', 'VARCHAR'], ['snapshot_at', 'DATE'],
                ['snapshot_timestamp', 'TIMESTAMP WITH TIME ZONE'], ['dependents_count', 'INTEGER']]


def _contract():
    return {name: file_sha256(Path(__file__).with_name(name + '.py')) for name in (
        'historical_parallel_writer', 'historical_parallel_verify', 'historical_parallel_input',
        'historical_production_daily', 'historical_production_cache', 'historical_artifact')}


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _normalize(partitions):
    if not isinstance(partitions, dict) or not partitions:
        raise ValueError('Partitions must be a nonempty mapping')
    result, owned = {}, set()
    for key, ids in partitions.items():
        if not re.fullmatch(r'\d{1,3}', str(key)) or int(key) > 255:
            raise ValueError('Invalid partition identity')
        key = f'{int(key):03d}'
        if key in result or not isinstance(ids, list):
            raise ValueError('Duplicate partition or invalid package list')
        if any(type(i) is not int or not 0 < i <= 2147483647 for i in ids):
            raise ValueError('Invalid package identity')
        if len(set(ids)) != len(ids) or owned.intersection(ids):
            raise ValueError('Duplicate package ownership')
        owned.update(ids)
        result[key] = sorted(ids)
    return dict(sorted(result.items()))


def _plan(cache_dir, digest, cache, partitions):
    return dict(format=FORMAT, cache_dir=str(cache_dir), cache_manifest_sha256=digest,
                calendar=cache['calendar'], partitions=_normalize(partitions), generation_contract=_contract(),
                lineage=cache['lineage'], observed_snapshot_timestamp=cache['observed_snapshot_timestamp'],
                metric_definition=METRIC, calculation_mode=MODE, ready_for_load=False)


def _load(con, cache_dir, cache, plan):
    daily._load_views(con, cache_dir, cache)
    rows = [dict(snapshot_index=i, **r) for i, r in enumerate(plan['calendar'])]
    con.execute('CREATE TEMP TABLE grouped_calendar AS SELECT unnest(from_json(?,?),recursive:=true)',
                [json.dumps(rows), json.dumps([dict(snapshot_index='INTEGER', snapshot_at='DATE', snapshot_timestamp='TIMESTAMPTZ')])])
    owners = [dict(partition_id=k, package_id=i) for k, ids in plan['partitions'].items() for i in ids]
    con.execute('CREATE TEMP TABLE grouped_owners AS SELECT unnest(from_json(?,?),recursive:=true)',
                [json.dumps(owners), json.dumps([dict(partition_id='VARCHAR', package_id='INTEGER')])])
    if con.execute('SELECT EXISTS(SELECT 1 FROM cache_targets t LEFT JOIN grouped_owners o USING(package_id) WHERE o.package_id IS NULL)').fetchone()[0]:
        raise ValueError('Partition ownership does not cover cache targets')


def _quality_expected(con, cache, plan):
    for index in range(len(plan['calendar'])):
        daily._expected_tables(con, cache, plan, index)
        statement = 'CREATE TEMP TABLE grouped_expected_quality AS' if index == 0 else 'INSERT INTO grouped_expected_quality'
        con.execute(statement + ' SELECT * FROM expected_quality')


def _file(root, relative):
    path = _path(root / relative)
    if not path.is_relative_to(root):
        raise ValueError('Output path escapes run')
    return path


def _info(con, root, path):
    return {**_record(path, con), 'name': path.relative_to(root).as_posix()}


def _read_receipt(root, parent, plan):
    marker = parent / 'complete.json'
    if not marker.exists():
        return None
    pointer = _read_json(marker)
    if (set(pointer) != {'attempt_id', 'receipt_sha256', 'run_plan_sha256'}
            or pointer['run_plan_sha256'] != sha256(plan)
            or not isinstance(pointer['attempt_id'], str)
            or not re.fullmatch('[0-9a-f]{32}', pointer['attempt_id'])):
        raise ValueError('Completion pointer identity mismatch')
    attempt = _file(root, (parent / 'attempts' / pointer['attempt_id']).relative_to(root))
    if file_sha256(attempt / 'receipt.json') != pointer['receipt_sha256']:
        raise ValueError('Receipt changed')
    return attempt, pointer, _read_json(attempt / 'receipt.json')


def _read_part(con, root, plan, key, *, values=True):
    found = _read_receipt(root, root / ('partition=' + key), plan)
    if found is None:
        return None
    attempt, pointer, receipt = found
    required = dict(status='COMPLETE', partition_id=key, attempt_id=attempt.name,
                    package_ids=plan['partitions'][key], run_plan_sha256=sha256(plan))
    if set(receipt) != set(required) | {'file', 'rows'} or any(receipt.get(k) != v for k, v in required.items()):
        raise ValueError('Partition receipt identity mismatch')
    record = receipt['file']
    if record is None:
        if receipt['rows'] != 0:
            raise ValueError('Empty partition has nonzero rows')
    elif (record.get('name') != (attempt / 'counts.parquet').relative_to(root).as_posix()
          or _info(con, root, attempt / 'counts.parquet') != record
          or record['rows'] <= 0 or receipt['rows'] != record['rows'] or record['schema'] != COUNT_SCHEMA):
        raise ValueError('Count file SHA/schema/rows mismatch')
    result = dict(package_ids=plan['partitions'][key], file=record,
                  attempt=attempt.relative_to(root).as_posix(), receipt_sha256=pointer['receipt_sha256'])
    if values:
        from pipeline.preprocessing.version_dependents.historical_parallel_verify import check_counts
        check_counts(con, root, key, record)
    return result


def _read_quality(con, root, plan, *, values=True):
    found = _read_receipt(root, root / 'quality', plan)
    if found is None:
        return None
    attempt, pointer, receipt = found
    if (set(receipt) != {'run_plan_sha256', 'file'} or receipt['run_plan_sha256'] != sha256(plan)
            or receipt['file'].get('name') != (attempt / 'quality.parquet').relative_to(root).as_posix()
            or _info(con, root, attempt / 'quality.parquet') != receipt['file']):
        raise ValueError('Quality receipt or file mismatch')
    if values:
        from pipeline.preprocessing.version_dependents.historical_parallel_verify import check_quality
        check_quality(con, root, receipt['file'])
    return dict(file=receipt['file'], attempt=attempt.relative_to(root).as_posix(), receipt_sha256=pointer['receipt_sha256'])


def _completed(plan, parts, quality):
    return dict(format=FORMAT, status='COMPLETE', run_plan_sha256=sha256(plan),
                cache_manifest_sha256=plan['cache_manifest_sha256'], calendar=plan['calendar'],
                partitions=parts, quality=quality['file'], quality_receipt=quality, ready_for_load=False)


def _checkpoint(root, phase):
    """Crash injection seam, before an immutable receipt becomes accepted."""


def _accept(root, parent, attempt, plan, receipt, phase):
    _publish_json(attempt / 'receipt.json', receipt)
    _checkpoint(root, phase)
    _publish_json(parent / 'complete.json', dict(attempt_id=attempt.name,
                  receipt_sha256=file_sha256(attempt / 'receipt.json'), run_plan_sha256=sha256(plan)))


def build_history(*, cache_dir, cache_sha256, output, partitions, resume=False, max_partitions=None):
    from pipeline.preprocessing.version_dependents.historical_parallel_verify import check_counts, check_quality
    cache_dir, root = _path(cache_dir), _path(output)
    if root == cache_dir or root.is_relative_to(cache_dir) or cache_dir.is_relative_to(root):
        raise ValueError('Cache and output must not overlap')
    if max_partitions is not None and (type(max_partitions) is not int or max_partitions < 1):
        raise ValueError('Invalid partition limit')
    cache = verify_cache(cache_dir, cache_sha256)
    plan = _plan(cache_dir, cache_sha256, cache, partitions)
    if resume:
        if not root.is_dir():
            raise ValueError('Missing resume directory')
    else:
        root.mkdir(parents=True, exist_ok=False)
    written = []
    with _run_lock(root), connection(root / ('working-' + uuid.uuid4().hex + '.duckdb'), memory_limit='16GB', max_temp_size='256GB') as con:
        plan_path = root / 'run_plan.json'
        if plan_path.exists():
            if _read_json(plan_path) != plan or file_sha256(plan_path) != sha256(plan):
                raise ValueError('Run plan differs')
        else:
            _publish_json(plan_path, plan)
        _load(con, cache_dir, cache, plan)
        parts = {k: _read_part(con, root, plan, k) for k in plan['partitions']}
        parts = {k: v for k, v in parts.items() if v is not None}
        reused = list(parts)
        pending = [k for k in plan['partitions'] if k not in parts]
        final_path = root / 'run_manifest.json'
        if final_path.exists() and pending:
            raise ValueError('Completed run lost partition receipts')
        for key in pending[:max_partitions]:
            parent = root / ('partition=' + key)
            attempt = parent / 'attempts' / uuid.uuid4().hex
            attempt.mkdir(parents=True)
            con.execute(f'''CREATE OR REPLACE TEMP VIEW grouped_write_counts AS
                SELECT i.package_id,i.version,c.snapshot_at,c.snapshot_timestamp,i.dependents_count::INTEGER AS dependents_count
                FROM cache_counts i JOIN grouped_owners o USING(package_id)
                JOIN grouped_calendar c ON i.start_index<=c.snapshot_index AND c.snapshot_index<i.end_index
                WHERE o.partition_id={_literal(key)}''')
            rows = con.execute('SELECT count(*) FROM grouped_write_counts').fetchone()[0]
            record = None
            if rows:
                destination = attempt / 'counts.parquet'
                con.execute(f'COPY grouped_write_counts TO {_literal(destination)} (FORMAT PARQUET, COMPRESSION ZSTD)')
                record = _info(con, root, destination)
            check_counts(con, root, key, record)
            receipt = dict(status='COMPLETE', partition_id=key, attempt_id=attempt.name,
                           package_ids=plan['partitions'][key], run_plan_sha256=sha256(plan), file=record, rows=rows)
            _accept(root, parent, attempt, plan, receipt, 'PART_RECEIPT')
            parts[key] = dict(package_ids=plan['partitions'][key], file=record,
                              attempt=attempt.relative_to(root).as_posix(), receipt_sha256=file_sha256(attempt / 'receipt.json'))
            written.append(key)
        if len(parts) != len(plan['partitions']):
            return dict(run_dir=str(root), run_status='INCOMPLETE', written_partitions=written,
                        reused_partitions=reused, ready_for_load=False)
        _quality_expected(con, cache, plan)
        quality = _read_quality(con, root, plan)
        if quality is None:
            if final_path.exists():
                raise ValueError('Completed run lost quality receipt')
            parent = root / 'quality'
            attempt = parent / 'attempts' / uuid.uuid4().hex
            attempt.mkdir(parents=True)
            destination = attempt / 'quality.parquet'
            con.execute(f'COPY grouped_expected_quality TO {_literal(destination)} (FORMAT PARQUET, COMPRESSION ZSTD)')
            record = _info(con, root, destination)
            check_quality(con, root, record)
            _accept(root, parent, attempt, plan, dict(run_plan_sha256=sha256(plan), file=record), 'QUALITY_RECEIPT')
            quality = dict(file=record, attempt=attempt.relative_to(root).as_posix(), receipt_sha256=file_sha256(attempt / 'receipt.json'))
        verify_cache_bytes(cache_dir, cache_sha256, cache)
        for record in [p['file'] for p in parts.values()] + [quality['file']]:
            if record and file_sha256(_file(root, record['name'])) != record['sha256']:
                raise ValueError('Output changed before publication')
        if _contract() != plan['generation_contract']:
            raise ValueError('Generation changed')
        result = _completed(plan, parts, quality)
        if final_path.exists():
            if _read_json(final_path) != result:
                raise ValueError('Published manifest differs')
        else:
            _publish_json(final_path, result)
        return dict(run_dir=str(root), run_status='COMPLETE', run_manifest_sha256=file_sha256(final_path),
                    completed_dates=[r['snapshot_at'] for r in plan['calendar']], written_partitions=written,
                    reused_partitions=reused, ready_for_load=False)


def _read_manifest(con, root, digest):
    if file_sha256(root / 'run_manifest.json') != digest:
        raise ValueError('Run manifest SHA mismatch')
    manifest, plan = _read_json(root / 'run_manifest.json'), _read_json(root / 'run_plan.json')
    if (plan['format'] != FORMAT or plan['generation_contract'] != _contract()
            or file_sha256(root / 'run_plan.json') != sha256(plan) or _normalize(plan['partitions']) != plan['partitions']):
        raise ValueError('History generation or plan mismatch')
    parts = {k: _read_part(con, root, plan, k, values=False) for k in plan['partitions']}
    quality = _read_quality(con, root, plan, values=False)
    if quality is None or any(p is None for p in parts.values()) or manifest != _completed(plan, parts, quality):
        raise ValueError('History receipt coverage mismatch')
    return manifest, plan


def open_counts(con, run_dir, manifest_sha256, snapshot_at=None, include_zero=False):
    root = _path(run_dir)
    manifest, plan = _read_manifest(con, root, manifest_sha256)
    if snapshot_at is not None and snapshot_at not in [r['snapshot_at'] for r in plan['calendar']]:
        raise ValueError('Snapshot not in run calendar')
    files = [str(_file(root, p['file']['name'])) for p in manifest['partitions'].values() if p['file']]
    if files:
        con.read_parquet(files, hive_partitioning=False).create_view('grouped_positive', replace=True)
    else:
        con.execute('CREATE OR REPLACE TEMP VIEW grouped_positive AS SELECT NULL::INTEGER package_id,NULL::VARCHAR version,NULL::DATE snapshot_at,NULL::TIMESTAMPTZ snapshot_timestamp,NULL::INTEGER dependents_count WHERE false')
    predicate = '' if snapshot_at is None else ' WHERE snapshot_at=DATE ' + _literal(snapshot_at)
    if not include_zero:
        con.execute('CREATE OR REPLACE TEMP VIEW counts AS SELECT * FROM grouped_positive' + predicate)
    else:
        cache_dir = _path(plan['cache_dir'])
        cache = verify_cache(cache_dir, plan['cache_manifest_sha256'])
        if cache['calendar'] != plan['calendar']:
            raise ValueError('Cache calendar changed')
        con.read_parquet(str(cache_dir / 'target_population.parquet'), hive_partitioning=False).create_view('grouped_read_targets', replace=True)
        rows = [dict(snapshot_index=i, **r) for i, r in enumerate(plan['calendar'])]
        con.execute('CREATE OR REPLACE TEMP TABLE grouped_read_calendar AS SELECT unnest(from_json(?,?),recursive:=true)',
                    [json.dumps(rows), json.dumps([dict(snapshot_index='INTEGER', snapshot_at='DATE', snapshot_timestamp='TIMESTAMPTZ')])])
        con.execute('''CREATE OR REPLACE TEMP VIEW counts AS SELECT * FROM (
            SELECT t.package_id,t.version,c.snapshot_at,c.snapshot_timestamp,coalesce(p.dependents_count,0)::INTEGER dependents_count
            FROM grouped_read_targets t JOIN grouped_read_calendar c ON t.birth_index<=c.snapshot_index
            LEFT JOIN grouped_positive p ON p.package_id=t.package_id AND p.version=t.version AND p.snapshot_at=c.snapshot_at)''' + predicate)


def open_quality(con, run_dir, manifest_sha256):
    root = _path(run_dir)
    manifest, _ = _read_manifest(con, root, manifest_sha256)
    con.read_parquet(str(_file(root, manifest['quality']['name'])), hive_partitioning=False).create_view('quality', replace=True)
