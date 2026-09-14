"""One persistent Node normalizer per contained CPU worker; isolated task files."""
from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
import time
import uuid

from pipeline.requirements_resolution.input import file_sha256
from .historical_artifact import _publish_json, _read_json
from .historical_cache import _record
from . import historical_parallel_input as inputs
from . import historical_production as production
from .historical_production_events import aggregate_partition_weighted
from .historical_production_input import connection
from .historical_production_resolver import resolve_partition, NORMALIZER


class Context:
    def __init__(self, run_root, runtime, expected_metadata, request_timeout):
        self.stack = ExitStack()
        root = Path(run_root)
        try:
            with production.MeasuredNode(runtime, root / ('metadata-' + uuid.uuid4().hex + '.log'),
                                         worker=production.WORKER, timeout=request_timeout) as node:
                metadata = node.request({'op': 'metadata'})
            if metadata != expected_metadata:
                raise ValueError('Worker Node runtime differs from plan')
            self.metadata = metadata
            self.node = self.stack.enter_context(production.MeasuredNode(runtime,
                root / ('normalizer-' + uuid.uuid4().hex + '.log'), worker=NORMALIZER, timeout=request_timeout))
        except BaseException:
            self.stack.close()
            raise

    def close(self):
        self.stack.close()


def initialize(run_root, runtime, metadata, request_timeout):
    return Context(run_root, runtime, metadata, request_timeout)


def execute(task, context):
    from .historical_parallel import contract
    started = time.perf_counter()
    if task['generation'] != contract():
        raise ValueError('Parallel generation changed before task')
    root = Path(task['run_root'])
    attempt = production._within(root, task['attempt'])
    assignment = _read_json(attempt / 'assignment.json')
    if assignment != task:
        raise ValueError('Task differs from durable assignment')
    part = task['partition_id']
    manifest_path = Path(task['prepared_dir']) / 'input_manifest.json'
    if file_sha256(manifest_path) != task['input_sha256']:
        raise ValueError('Input manifest changed before task')
    manifest = _read_json(manifest_path)
    checked = time.perf_counter()
    inputs.verify_partition(task['prepared_dir'], manifest, part, bytes_only=True)
    verified = time.perf_counter()
    with connection(attempt / 'working.duckdb', **task['settings']) as con:
        paths = inputs.open_partition(con, task['prepared_dir'], manifest, part, materialize=True)
        opened = time.perf_counter()
        metrics = resolve_partition(con, context.node, context.metadata, part, len(manifest['calendar']),
                                    backend='cpu', lookup_batch=task['lookup_batch'])
        resolved = time.perf_counter()
        metrics['resolution_seconds'] = resolved - opened
        metrics['aggregation'] = aggregate_partition_weighted(con, len(manifest['calendar']), part,
                                                             global_validated=True)
        aggregated = time.perf_counter()
        for name, table in production._part_files(production.WEIGHTED_ALGORITHM).items():
            con.execute(f'COPY {table} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',
                        [str(attempt / (name + '.parquet'))])
    saved = time.perf_counter()
    inputs.verify_partition(task['prepared_dir'], manifest, part, bytes_only=True)
    if file_sha256(manifest_path) != task['input_sha256'] or contract() != task['generation']:
        raise ValueError('Input or generation changed during task')
    metrics.update(input_verify_seconds=verified-checked, input_open_seconds=opened-verified,
                   partition_save_seconds=saved-aggregated, opened_input_paths=paths)
    receipt = {'status': 'COMPLETE', 'partition_id': part,
               'names': manifest['partitions'][f'{part:03d}']['names'],
               'attempt_id': attempt.name, 'epoch': task['epoch'], 'input_sha256': task['input_sha256'],
               'plan_sha256': task['plan_sha256'], 'assignment_sha256': file_sha256(attempt / 'assignment.json'),
               'metrics': metrics, 'worker_pid': os.getpid(), 'node_pid': context.node.process.pid,
               'files': [_record(attempt / (name + '.parquet'))
                         for name in production._part_files(production.WEIGHTED_ALGORITHM)],
               'seconds': time.perf_counter()-started, 'memory': production.current_memory()}
    _publish_json(attempt / 'receipt.json', receipt)
    return {'attempt': task['attempt'], 'receipt_sha256': file_sha256(attempt / 'receipt.json')}
