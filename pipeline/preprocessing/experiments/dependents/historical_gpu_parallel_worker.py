"""CPU preparation and aggregation around requests to a single CUDA owner."""
from __future__ import annotations
from contextlib import ExitStack
import os
from pathlib import Path
import time
import uuid
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents.historical_artifact import _read_json, _publish_json
from pipeline.preprocessing.version_dependents.historical_cache import _record
from pipeline.preprocessing.version_dependents.historical_production_input import connection
from pipeline.preprocessing.version_dependents.historical_production_events import aggregate_partition_weighted
from pipeline.preprocessing.version_dependents import historical_parallel_input as inputs
from pipeline.preprocessing.version_dependents import historical_production as production
from pipeline.preprocessing.experiments.dependents.historical_gpu_owner import Client, _trace
from pipeline.preprocessing.experiments.dependents.historical_gpu_pipeline_resolver import resolve_partition

NORMALIZER=Path(__file__).with_name('historical_gpu_pipeline_normalize.cjs')


class Context:
    def __init__(self,run_root,runtime,metadata,request_timeout,address,authkey,gpu_runtime,rpc_timeout):
        self.stack=ExitStack()
        try:
            root=Path(run_root)
            with production.MeasuredNode(runtime,root/('gpu-metadata-'+uuid.uuid4().hex+'.log'),
                                         worker=production.WORKER,timeout=request_timeout) as node:
                if node.request({'op':'metadata'})!=metadata:
                    raise ValueError('Worker Node metadata differs')
            self.node=self.stack.enter_context(production.MeasuredNode(runtime,
                root/('gpu-normalizer-'+uuid.uuid4().hex+'.log'),worker=NORMALIZER,timeout=request_timeout))
            self.client=Client(address,authkey,gpu_runtime,timeout=rpc_timeout)
            self.stack.callback(self.client.close)
            self.metadata,self.gpu_runtime=metadata,gpu_runtime
        except BaseException:
            self.stack.close()
            raise

    def close(self):
        self.stack.close()


def initialize(*args):
    return Context(*args)


def execute(task,context):
    from pipeline.preprocessing.experiments.dependents.historical_gpu_parallel import contract
    started=time.perf_counter()
    if task['generation']!=contract():
        raise ValueError('GPU parallel generation changed')
    root=Path(task['run_root']); attempt=production._within(root,task['attempt'])
    plan=_read_json(root/'run_plan.json')
    if (_read_json(attempt/'assignment.json')!=task or task['gpu_settings']!=plan['resolver_settings']
            or context.gpu_runtime!=plan['resolver_runtime']):
        raise ValueError('GPU assignment or runtime differs from durable plan')
    manifest_path=Path(task['prepared_dir'])/'input_manifest.json'
    if file_sha256(manifest_path)!=task['input_sha256']:
        raise ValueError('Input manifest changed')
    manifest=_read_json(manifest_path); part=task['partition_id']
    identity=dict(run_plan_sha256=task['plan_sha256'],epoch=task['epoch'],attempt=task['attempt'],partition_id=part)
    context.client.bind(identity)
    checked=time.perf_counter()
    inputs.verify_partition(task['prepared_dir'],manifest,part,bytes_only=True)
    verified=time.perf_counter()
    trace_path=attempt/'overlap.jsonl'
    def trace(phase,*args):
        _trace(trace_path,phase,identity=identity)
    with connection(attempt/'working.duckdb',**task['settings']) as con:
        paths=inputs.open_partition(con,task['prepared_dir'],manifest,part,materialize=True)
        opened=time.perf_counter()
        metrics=resolve_partition(con,context.node,context.metadata,part,len(manifest['calendar']),
            client=context.client,attempt_identity=identity,lookup_batch=task['lookup_batch'],
            workspace_mib=task['gpu_settings']['workspace_mib'],event=trace)
        resolved=time.perf_counter(); metrics['resolution_seconds']=resolved-opened
        trace('AGGREGATE_BEGIN')
        try:
            metrics['aggregation']=aggregate_partition_weighted(con,len(manifest['calendar']),part,global_validated=True)
        finally:
            trace('AGGREGATE_END')
        aggregated=time.perf_counter()
        for name,table in production._part_files(production.WEIGHTED_ALGORITHM).items():
            con.execute(f'COPY {table} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(attempt/(name+'.parquet'))])
    saved=time.perf_counter()
    inputs.verify_partition(task['prepared_dir'],manifest,part,bytes_only=True)
    if file_sha256(manifest_path)!=task['input_sha256'] or contract()!=task['generation']:
        raise ValueError('Input or GPU code changed during task')
    metrics.update(input_verify_seconds=verified-checked,input_open_seconds=opened-verified,
        partition_save_seconds=saved-aggregated,opened_input_paths=paths,gpu_owner_pid=context.client.owner_pid)
    receipt=dict(status='COMPLETE',partition_id=part,names=manifest['partitions'][f'{part:03d}']['names'],
        attempt_id=attempt.name,epoch=task['epoch'],input_sha256=task['input_sha256'],plan_sha256=task['plan_sha256'],
        assignment_sha256=file_sha256(attempt/'assignment.json'),metrics=metrics,worker_pid=os.getpid(),
        node_pid=context.node.process.pid,gpu_runtime=context.gpu_runtime,
        files=[_record(attempt/(name+'.parquet')) for name in production._part_files(production.WEIGHTED_ALGORITHM)],
        seconds=time.perf_counter()-started,memory=production.current_memory())
    _publish_json(attempt/'receipt.json',receipt)
    return dict(attempt=task['attempt'],receipt_sha256=file_sha256(attempt/'receipt.json'))
