"""Coordinator-owned CPU partition execution and durable candidate publication.

Worker concurrency is execution metadata. It never changes partition identity.
Only this process holds the run lock and publishes accepted/final pointers.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical_artifact import _path, _publish_json, _read_json, _run_lock
from .historical_cache import _record
from .historical_production_input import connection, event
from .historical_production_quality import finalize_quality_weighted
from .historical_parallel_pool import Pool
from . import historical_parallel_input as inputs
from . import historical_parallel_worker as worker
from . import historical_production as old
from .historical_throughput_benchmark import _resources, _disk

FORMAT = 'historical-parallel-cpu-v2'
FILES = old.WEIGHTED_PART_FILES


def contract():
    return {'format': FORMAT, 'input': inputs.contract(),
            'production': old.contract(old.WEIGHTED_ALGORITHM, 'cpu'),
            'code': {name: file_sha256(Path(__file__).with_name(name + '.py')) for name in
                     ('historical_parallel', 'historical_parallel_worker', 'historical_parallel_pool',
                      'historical_parallel_writer', 'historical_parallel_verify')}}


def _checkpoint(root, phase, **values):
    """Durable observation boundary, also injectable by crash tests."""
    event(root, phase, **values)


def _groups(manifest):
    return {int(p): v['names'] for p, v in manifest['partitions'].items() if v['status'] == 'READY'}


def _candidate(root, plan, part, attempt, expected_sha=None):
    directory = old._within(root, attempt)
    if directory.parent != root / 'partitions' / f'{part:03d}' / 'attempts':
        raise ValueError('Candidate belongs to another partition')
    receipt_path = directory / 'receipt.json'
    if expected_sha and file_sha256(receipt_path) != expected_sha:
        raise ValueError('Candidate receipt SHA mismatch')
    receipt = _read_json(receipt_path)
    assignment = _read_json(directory / 'assignment.json')
    if (receipt.get('plan_sha256') != sha256(plan) or receipt.get('partition_id') != part
            or receipt.get('names') != plan['partitions'][str(part)] or receipt.get('status') != 'COMPLETE'
            or receipt.get('attempt_id') != directory.name or receipt.get('epoch') != assignment.get('epoch')
            or receipt.get('input_sha256') != plan['input_manifest_sha256']
            or receipt.get('assignment_sha256') != file_sha256(directory / 'assignment.json')
            or assignment.get('attempt') != attempt or assignment.get('partition_id') != part
            or assignment.get('plan_sha256') != sha256(plan) or assignment.get('generation') != plan['generation_contract']
            or assignment.get('input_sha256') != plan['input_manifest_sha256']
            or assignment.get('lookup_batch') != plan['resolver_settings']['lookup_batch']
            or assignment.get('run_root') != str(root)):
        raise ValueError('Candidate assignment or receipt contract mismatch')
    records = receipt.get('files', [])
    if len(records) != len(FILES) or {r['name'] for r in records} != {f + '.parquet' for f in FILES}:
        raise ValueError('Candidate file coverage mismatch')
    for record in records:
        if _record(old._within(directory, record['name'])) != record:
            raise ValueError('Candidate output changed')
    return {'partition_id': part, 'attempt': attempt,
            'receipt_sha256': file_sha256(receipt_path), 'names': plan['partitions'][str(part)]}


def _accepted(root, plan, part):
    parent = root / 'partitions' / f'{part:03d}'
    pointer = parent / 'complete.json'
    if not pointer.exists():
        return None
    ref = _read_json(pointer)
    if set(ref) != {'attempt', 'receipt_sha256'}:
        raise ValueError('Invalid accepted pointer')
    attempt = old._within(parent, ref['attempt']).relative_to(root).as_posix()
    return _candidate(root, plan, part, attempt, ref['receipt_sha256'])


def _accept(root, plan, candidate):
    part = candidate['partition_id']
    prior = _accepted(root, plan, part)
    if prior:
        _checkpoint(root, 'IGNORED_ALREADY_ACCEPTED', partition_id=part)
        return prior
    parent = root / 'partitions' / f'{part:03d}'
    _checkpoint(root, 'CANDIDATE', partition_id=part, attempt=candidate['attempt'])
    _publish_json(parent / 'complete.json', {
        'attempt': old._within(root, candidate['attempt']).relative_to(parent).as_posix(),
        'receipt_sha256': candidate['receipt_sha256']})
    _checkpoint(root, 'POINTER_PUBLISHED', partition_id=part)
    _checkpoint(root, 'ACCEPTED', partition_id=part, attempt=candidate['attempt'])
    return candidate


def _same_candidates(root, left, right, settings):
    with connection(root / ('compare-candidates-' + uuid.uuid4().hex + '.duckdb'), **settings) as con:
        for name in FILES:
            for side, value in (('a', left), ('b', right)):
                con.read_parquet(str(old._within(root, value['attempt']) / (name + '.parquet')),
                                 hive_partitioning=False).create_view(side, replace=True)
            if con.execute('DESCRIBE a').fetchall() != con.execute('DESCRIBE b').fetchall():
                return False
            if con.execute('SELECT EXISTS ((SELECT * FROM a EXCEPT ALL SELECT * FROM b) '
                           'UNION ALL (SELECT * FROM b EXCEPT ALL SELECT * FROM a))').fetchone()[0]:
                return False
    return True


def _recover(root, plan, part, settings):
    accepted = _accepted(root, plan, part)
    if accepted:
        _checkpoint(root, 'REUSED_ACCEPTED', partition_id=part)
        return accepted
    parent = root / 'partitions' / f'{part:03d}' / 'attempts'
    candidates = []
    for directory in sorted(parent.iterdir()) if parent.exists() else []:
        receipt = directory / 'receipt.json'
        if not receipt.exists():
            _checkpoint(root, 'ORPHANED', partition_id=part, attempt=directory.name)
            continue
        try:
            _read_json(receipt)
        except (json.JSONDecodeError, UnicodeDecodeError):
            _checkpoint(root, 'ORPHANED_TRUNCATED_RECEIPT', partition_id=part, attempt=directory.name)
            continue
        candidates.append(_candidate(root, plan, part, directory.relative_to(root).as_posix()))
    if not candidates:
        return None
    if any(not _same_candidates(root, candidates[0], other, settings) for other in candidates[1:]):
        raise ValueError('Multiple candidate attempts contain different results')
    return _accept(root, plan, candidates[0])


def _merge(con, root, prepared, manifest, receipts):
    inputs.open_all(con, prepared, manifest)
    for suffix, name in (('counts', 'all_counts'), ('source_summary', 'all_source_summary'),
                         ('status_deltas', 'all_status_deltas')):
        con.read_parquet([str(old._within(root, r['attempt']) / (suffix + '.parquet')) for r in receipts],
                         hive_partitioning=False).create_view(name)
    finalize_quality_weighted(con, len(manifest['calendar']))


def _finalize(root, prepared, manifest, plan, receipts, settings):
    pointer = root / 'cache_complete.json'
    if pointer.exists():
        saved = _read_json(pointer)
        directory = old._verify_cache_chain(root, saved, manifest, plan, receipts)
        with connection(root / ('verify-cache-' + uuid.uuid4().hex + '.duckdb'), **settings) as con:
            _merge(con, root, prepared, manifest, receipts)
            old._check_cache_derivation(con, directory / 'cache')
        return saved
    directory = root / 'finalizations' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    _publish_json(directory / 'provenance.json', old._provenance(plan, receipts))
    with connection(directory / 'working.duckdb', **settings) as con:
        _merge(con, root, prepared, manifest, receipts)
        cached = old.create_cache(con, output=directory / 'cache', calendar=manifest['calendar'],
            observed_snapshot_timestamp=manifest['observed_snapshot_timestamp'], runtime=plan['runtime'],
            lineage={'source_kind': 'NORMALIZED_HISTORY_TABLES',
                     'input_manifest_sha256': file_sha256(directory / 'provenance.json'),
                     'policy_sha256': sha256(manifest['policy'])})
    saved = {'directory': directory.relative_to(root).as_posix(),
             'provenance_sha256': file_sha256(directory / 'provenance.json'),
             'cache_sha256': cached['manifest_sha256']}
    _publish_json(pointer, saved)
    return saved


def _settings(workers, threads, memory_limit, max_temp_size):
    def split(value):
        match = re.fullmatch(r'([1-9][0-9]*)(MB|GB)', value)
        if not match:
            raise ValueError('Resource limits require positive integer MB or GB')
        amount = int(match[1]) * (1000 if match[2] == 'GB' else 1)
        if amount < workers:
            raise ValueError('Resource limit is smaller than worker count')
        return str(amount // workers) + 'MB'
    if workers not in (1, 2, 4) or type(workers) is not int or type(threads) is not int or not workers <= threads <= 8:
        raise ValueError('Use 1, 2 or 4 workers and a total thread budget between workers and 8')
    return {'threads': threads // workers, 'memory_limit': split(memory_limit),
            'max_temp_size': split(max_temp_size)}


def _compute(root, prepared, manifest, plan, settings, workers, runtime, request_timeout,
             max_partitions, min_free_bytes, rss_limit_bytes, scratch_limit_bytes):
    groups = _groups(manifest)
    receipts = {part: r for part in sorted(groups) if (r := _recover(root, plan, part, settings))}
    reused = sorted(receipts)
    pending = sorted(set(groups) - set(receipts), key=lambda p: (
        -manifest['partitions'][f'{p:03d}']['rows']['declarations'], p))
    if max_partitions is not None:
        pending = pending[:max_partitions]
    epoch = uuid.uuid4().hex
    _publish_json(root / ('execution-' + epoch + '.json'), {
        'epoch': epoch, 'workers': workers, 'worker_settings': settings, 'coordinator_pid': os.getpid(),
        'plan_sha256': sha256(plan), 'prepared_dir': str(prepared), 'timeout_scope': 'single Node request only',
        'request_timeout': request_timeout})
    retries = {}
    peak_rss = peak_scratch = 0
    sample_at = 0
    if pending:
        with Pool(workers, worker.execute, initializer=worker.initialize,
                  initargs=(str(root), runtime, plan['runtime'], request_timeout)) as pool:
            while pending or pool.active:
                if time.monotonic() >= sample_at:
                    resources, disk = _resources(os.getpid()), _disk(root)
                    peak_rss = max(peak_rss, resources['tree_rss_bytes'])
                    peak_scratch = max(peak_scratch, disk['scratch_bytes'])
                    if (peak_rss > rss_limit_bytes or disk['scratch_bytes'] > scratch_limit_bytes
                            or shutil.disk_usage(root).free < min_free_bytes):
                        raise RuntimeError('Parallel resource guard exceeded; accepted partitions remain resumable')
                    sample_at = time.monotonic() + 1
                for slot in pool.idle:
                    if not pending:
                        break
                    part = pending.pop(0)
                    attempt = root / 'partitions' / f'{part:03d}' / 'attempts' / uuid.uuid4().hex
                    attempt.mkdir(parents=True)
                    task = {'partition_id': part, 'attempt': attempt.relative_to(root).as_posix(),
                            'epoch': epoch, 'plan_sha256': sha256(plan), 'input_sha256': plan['input_manifest_sha256'],
                            'generation': plan['generation_contract'], 'run_root': str(root),
                            'prepared_dir': str(prepared), 'settings': settings,
                            'lookup_batch': plan['resolver_settings']['lookup_batch']}
                    _publish_json(attempt / 'assignment.json', task)
                    _checkpoint(root, 'RUNNING', partition_id=part, attempt=task['attempt'], epoch=epoch)
                    pool.submit(slot, task)
                for result in pool.events():
                    kind, task, slot = result['kind'], result.get('task'), result['slot']
                    if kind == 'READY':
                        continue
                    if kind == 'RESULT':
                        value = result['value']
                        if not task or task['epoch'] != epoch or task['partition_id'] in receipts:
                            _checkpoint(root, 'IGNORED_LATE_RESPONSE', slot=slot)
                            continue
                        if value['attempt'] != task['attempt']:
                            raise ValueError('Worker returned another assignment')
                        candidate = _candidate(root, plan, task['partition_id'], value['attempt'], value['receipt_sha256'])
                        receipts[task['partition_id']] = _accept(root, plan, candidate)
                    elif kind in ('ERROR', 'DEAD'):
                        transient = kind == 'DEAD' or result.get('error', '') in (
                            'Node bridge failed or exceeded request timeout', 'Node bridge ended before a valid response')
                        if not task:
                            if pending:
                                raise RuntimeError('Idle worker failed before assignment: ' + str(result))
                            continue
                        part = task['partition_id']
                        detail = {k: v for k, v in result.items() if k != 'task'}
                        _checkpoint(root, 'FAILED', partition_id=part, detail=detail)
                        if not transient or retries.get(part, 0) >= 1:
                            raise RuntimeError('Partition worker failed: ' + str(detail))
                        recovered = _recover(root, plan, part, settings)
                        if recovered:
                            receipts[part] = recovered
                        else:
                            pending.insert(0, part)
                        retries[part] = retries.get(part, 0) + 1
                        pool.replace(slot)
                    else:
                        raise RuntimeError('Worker initialization failed: ' + str(result))
    return [receipts[p] for p in sorted(receipts)], reused, {
        'peak_tree_rss_bytes': peak_rss, 'peak_scratch_bytes': peak_scratch, 'epoch': epoch}


def run(*, prepared_dir, manifest_sha256, output, resume=False, workers=1,
        allow_full_selected=False, max_partitions=None, max_snapshots=None,
        threads=4, memory_limit='4GB', max_temp_size='40GB', min_free_bytes=20_000_000_000,
        request_timeout=60, lookup_batch=1024, rss_limit_bytes=12 * 1024**3,
        scratch_limit_bytes=64 * 1024**3, history_layout='daily'):
    started = time.perf_counter()
    settings = {'threads': threads, 'memory_limit': memory_limit, 'max_temp_size': max_temp_size}
    per_worker = _settings(workers, threads, memory_limit, max_temp_size)
    if history_layout not in ('daily', 'grouped'):
        raise ValueError('Unknown history layout')
    if history_layout == 'grouped' and max_snapshots is not None:
        raise ValueError('Grouped history checkpoints by partition, not snapshot')
    if os.name != 'nt':
        raise ValueError('This local parallel implementation has only validated Windows containment')
    old.ranked_resolver.validate_options('cpu', lookup_batch, 128)
    if max_partitions is not None and (type(max_partitions) is not int or max_partitions < 1):
        raise ValueError('max_partitions must be positive')
    for value in (min_free_bytes, rss_limit_bytes, scratch_limit_bytes):
        if type(value) is not int or value < 0:
            raise ValueError('Resource guards must be nonnegative integers')
    prepared, root = _path(prepared_dir), _path(output)
    old._check_output_path(root)
    if root.is_relative_to(prepared) or prepared.is_relative_to(root):
        raise ValueError('Run output overlaps prepared input')
    manifest = inputs.verify_inputs(prepared, manifest_sha256)
    if manifest['scope'] == 'FULL_SELECTED' and not allow_full_selected:
        raise ValueError('Full selected execution requires explicit allow_full_selected=True')
    if resume:
        if not root.is_dir():
            raise ValueError('Resume requires existing output')
    else:
        root.mkdir(parents=True, exist_ok=False)
    with _run_lock(root):
        runtime = old.discover_runtime()
        with old.MeasuredNode(runtime, root / ('metadata-' + uuid.uuid4().hex + '.log'),
                              worker=old.WORKER, timeout=request_timeout) as node:
            metadata = node.request({'op': 'metadata'})
        plan = {'format': FORMAT, 'algorithm': old.WEIGHTED_ALGORITHM,
                'input_manifest_sha256': manifest_sha256, 'scope': manifest['scope'],
                'calendar': manifest['calendar'], 'partitions': {str(p): n for p, n in _groups(manifest).items()},
                'policy': manifest['policy'], 'runtime': metadata, 'resolver_backend': 'cpu',
                'resolver_runtime': old.ranked_resolver.runtime_identity('cpu'),
                'resolver_settings': {'lookup_batch': lookup_batch, 'workspace_mib': 128},
                'history_layout': history_layout, 'generation_contract': contract(), 'ready_for_load': False}
        plan_path = root / 'run_plan.json'
        if plan_path.exists():
            if _read_json(plan_path) != plan:
                raise ValueError('Resume plan differs from original generation, input or policy')
        else:
            _publish_json(plan_path, plan)
            _publish_json(root / 'input_location.json', {'prepared_dir': str(prepared)})
        event(root, 'COMPUTE_PARTITIONS', workers=workers)
        receipts, reused, metrics = _compute(root, prepared, manifest, plan, per_worker, workers, runtime,
            request_timeout, max_partitions, min_free_bytes, rss_limit_bytes, scratch_limit_bytes)
        written = [r['partition_id'] for r in receipts if r['partition_id'] not in reused]
        if len(receipts) < len(plan['partitions']):
            return {'run_status': 'INCOMPLETE', 'written_partitions': written, 'reused_partitions': reused,
                    'remaining_partitions': len(plan['partitions']) - len(receipts), 'ready_for_load': False}
        event(root, 'FINALIZE_INTERVAL_CACHE')
        cached = _finalize(root, prepared, manifest, plan, receipts, settings)
        directory = old._within(root, cached['directory'])
        event(root, 'WRITE_SNAPSHOT_PARQUETS')
        if history_layout == 'grouped':
            from .historical_parallel_writer import build_history
            with connection(root / ('history-ownership-' + uuid.uuid4().hex + '.duckdb'), **settings) as con:
                inputs.open_all(con, prepared, manifest)
                groups = {str(part): [] for part in _groups(manifest)}
                for part, package_id in con.execute('SELECT partition_id,package_id FROM target_names '
                                                    'WHERE package_id IS NOT NULL ORDER BY partition_id,package_id').fetchall():
                    groups[str(part)].append(package_id)
            history = build_history(cache_dir=directory / 'cache', cache_sha256=cached['cache_sha256'],
                output=directory / 'history', partitions=groups, resume=(directory / 'history').exists())
        else:
            history = old.build_history(cache_dir=directory / 'cache', cache_sha256=cached['cache_sha256'],
                output=directory / 'history', resume=(directory / 'history').exists(), max_snapshots=max_snapshots)
        inputs.verify_bytes(prepared, manifest_sha256)
        if contract() != plan['generation_contract'] or old.ranked_resolver.runtime_identity('cpu') != plan['resolver_runtime']:
            raise ValueError('Generation or runtime changed during run')
        stable_history = {k: v for k, v in history.items()
                          if k not in ('written_dates', 'reused_dates', 'written_partitions', 'reused_partitions')}
        result = {'format': FORMAT, 'run_status': history['run_status'], 'plan_sha256': sha256(plan),
                  'partitions': receipts, 'cache': cached, 'history': stable_history, 'scope': manifest['scope'],
                  'full_selection_executed': manifest['scope'] == 'FULL_SELECTED' and history['run_status'] == 'COMPLETE',
                  'upstream_resolution_status': 'PARTIAL', 'ready_for_load': False}
        if history['run_status'] == 'COMPLETE':
            path = root / 'run_manifest.json'
            if path.exists():
                if _read_json(path) != result:
                    raise ValueError('Published result differs')
            else:
                _publish_json(path, result)
        event(root, 'RUN_' + history['run_status'], seconds=time.perf_counter() - started)
        return {'run_dir': str(root), 'run_status': history['run_status'],
                'run_manifest_sha256': file_sha256(root / 'run_manifest.json') if history['run_status'] == 'COMPLETE' else None,
                'written_partitions': written, 'reused_partitions': reused, 'resources': metrics,
                'elapsed_seconds': time.perf_counter() - started, 'ready_for_load': False}


def verify_run(*, run_dir, manifest_sha256):
    root = _path(run_dir)
    if file_sha256(root / 'run_manifest.json') != manifest_sha256:
        raise ValueError('Run manifest SHA mismatch')
    result, plan = _read_json(root / 'run_manifest.json'), _read_json(root / 'run_plan.json')
    if (plan['format'] != FORMAT or result['format'] != FORMAT or sha256(plan) != result['plan_sha256']
            or plan['generation_contract'] != contract() or result['run_status'] != 'COMPLETE'
            or result['ready_for_load'] is not False or result['upstream_resolution_status'] != 'PARTIAL'):
        raise ValueError('Parallel run contract mismatch')
    prepared = _path(_read_json(root / 'input_location.json')['prepared_dir'])
    manifest = inputs.verify_inputs(prepared, plan['input_manifest_sha256'])
    if ({str(p): n for p, n in _groups(manifest).items()} != plan['partitions']
            or plan['scope'] != manifest['scope'] or result['scope'] != manifest['scope']
            or result['full_selection_executed'] != (manifest['scope'] == 'FULL_SELECTED')
            or plan['calendar'] != manifest['calendar'] or plan['policy'] != manifest['policy']):
        raise ValueError('Parallel input scope or coverage mismatch')
    receipts = [_accepted(root, plan, p) for p in sorted(_groups(manifest))]
    if receipts != result['partitions'] or any(r is None for r in receipts):
        raise ValueError('Accepted partition coverage mismatch')
    cached = _read_json(root / 'cache_complete.json')
    if cached != result['cache']:
        raise ValueError('Cache pointer mismatch')
    directory = old._verify_cache_chain(root, cached, manifest, plan, receipts)
    with connection(root / ('verify-' + uuid.uuid4().hex + '.duckdb')) as con:
        _merge(con, root, prepared, manifest, receipts)
        old._check_cache_derivation(con, directory / 'cache')
    if plan['history_layout'] == 'grouped':
        from .historical_parallel_verify import verify_history
    elif plan['history_layout'] == 'daily':
        verify_history = old.verify_history
    else:
        raise ValueError('Unknown history layout')
    verify_history(run_dir=directory / 'history', cache_dir=directory / 'cache',
        cache_sha256=cached['cache_sha256'], run_manifest_sha256=result['history']['run_manifest_sha256'])
    return {'verified': True, 'scope': manifest['scope'], 'partitions': len(receipts),
            'snapshots': len(manifest['calendar']), 'ready_for_load': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('convert', 'run'):
        p = sub.add_parser(command)
        for name in ('prepared-dir', 'manifest-sha256', 'output'):
            p.add_argument('--' + name, required=True)
        if command == 'run':
            p.add_argument('--workers', type=int, default=1, choices=(1, 2, 4))
            p.add_argument('--resume', action='store_true')
            p.add_argument('--max-partitions', type=int)
            p.add_argument('--max-snapshots', type=int)
            p.add_argument('--allow-full-selected', action='store_true')
            p.add_argument('--history-layout', choices=('daily', 'grouped'), default='daily')
    p = sub.add_parser('verify')
    p.add_argument('--run-dir', required=True)
    p.add_argument('--manifest-sha256', required=True)
    args = vars(parser.parse_args())
    command = args.pop('command')
    result = {'convert': inputs.from_prepared, 'run': run, 'verify': verify_run}[command](**args)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
