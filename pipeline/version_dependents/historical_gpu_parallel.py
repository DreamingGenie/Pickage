"""Opt-in CPU preparation/aggregation with a single contained CUDA owner."""
from __future__ import annotations
import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import shutil
import time
import uuid
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from . import historical_parallel as cpu
from . import historical_gpu_parallel_worker as worker
from .historical_gpu_owner import Owner,OwnerError,PROTOCOL,MAX_FRAME
from .historical_parallel_pool import Pool
from .historical_artifact import _path,_publish_json,_read_json,_run_lock
from .historical_production_input import connection,event
from .historical_production_resolver import validate_options
from .historical_throughput_benchmark import _resources,_disk
from .historical_parallel_writer import build_history
from .historical_parallel_verify import verify_history

FORMAT='historical-parallel-cpu-gpu-v1'
FILES=cpu.FILES


def contract():
    names=('historical_gpu_parallel.py','historical_gpu_parallel_worker.py','historical_gpu_owner.py',
           'historical_gpu_cached.py','historical_gpu_pipeline_resolver.py','historical_gpu_pipeline_normalize.cjs')
    return dict(format=FORMAT,protocol=PROTOCOL,cpu=cpu.contract(),code={n:file_sha256(Path(__file__).with_name(n)) for n in names})


def _candidate(root,plan,part,attempt,expected_sha=None):
    result=cpu._candidate(root,plan,part,attempt,expected_sha)
    directory=cpu.old._within(root,attempt)
    assignment=_read_json(directory/'assignment.json');receipt=_read_json(directory/'receipt.json')
    if (assignment.get('gpu_settings')!=plan['resolver_settings'] or receipt.get('gpu_runtime')!=plan['resolver_runtime']):
        raise ValueError('Candidate GPU settings or runtime differ')
    return result


def _accepted(root,plan,part):
    result=cpu._accepted(root,plan,part)
    return None if result is None else _candidate(root,plan,part,result['attempt'],result['receipt_sha256'])


def _recover(root,plan,part,settings):
    prior=_accepted(root,plan,part)
    if prior:
        return prior
    parent=root/'partitions'/f'{part:03d}'/'attempts'
    candidates=[]
    for path in sorted(parent.iterdir()) if parent.exists() else []:
        if not (path/'receipt.json').exists():
            continue
        try:
            _read_json(path/'receipt.json')
        except (json.JSONDecodeError,UnicodeDecodeError):
            continue
        candidates.append(_candidate(root,plan,part,path.relative_to(root).as_posix()))
    if not candidates:
        return None
    if any(not cpu._same_candidates(root,candidates[0],other,settings) for other in candidates[1:]):
        raise ValueError('Multiple candidate attempts contain different results')
    return cpu._accept(root,plan,candidates[0])


def _checkpoint(root,phase,**values):
    event(root,phase,**values)


def _compute(root,prepared,manifest,plan,settings,workers,runtime,request_timeout,rpc_timeout,
             max_partitions,min_free_bytes,rss_limit_bytes,scratch_limit_bytes,owner):
    groups=cpu._groups(manifest)
    receipts={p:r for p in sorted(groups) if (r:=_recover(root,plan,p,settings))}
    reused=sorted(receipts)
    pending=sorted(set(groups)-set(receipts),key=lambda p:(-manifest['partitions'][f'{p:03d}']['rows']['declarations'],p))
    if max_partitions is not None: pending=pending[:max_partitions]
    epoch=uuid.uuid4().hex
    _publish_json(root/('execution-'+epoch+'.json'),dict(epoch=epoch,workers=workers,worker_settings=settings,
        coordinator_pid=os.getpid(),gpu_owner_pid=owner.pid,plan_sha256=sha256(plan),prepared_dir=str(prepared),
        request_timeout=request_timeout,gpu_rpc_timeout=rpc_timeout,timeout_scope='single Node request or GPU RPC including queue wait',
        max_inflight_requests=workers,max_frame_bytes=MAX_FRAME,max_wire_request_response_bytes=2*workers*MAX_FRAME))
    peak_rss=peak_scratch=0;sample_at=0;retries={}
    if pending:
        with Pool(workers,worker.execute,initializer=worker.initialize,initargs=(str(root),runtime,plan['runtime'],
                    request_timeout,owner.address,owner.authkey,owner.runtime,rpc_timeout)) as pool:
            init_deadline=time.monotonic()+max(180,request_timeout*2+rpc_timeout)
            ready=set()
            while pending or pool.active:
                owner.check()
                if len(ready)<workers and time.monotonic()>init_deadline:
                    raise RuntimeError('CPU worker initialization timed out')
                if time.monotonic()>=sample_at:
                    resources,disk=_resources(os.getpid()),_disk(root)
                    peak_rss=max(peak_rss,resources['tree_rss_bytes']);peak_scratch=max(peak_scratch,disk['scratch_bytes'])
                    if peak_rss>rss_limit_bytes or peak_scratch>scratch_limit_bytes or shutil.disk_usage(root).free<min_free_bytes:
                        raise RuntimeError('GPU pipeline resource guard exceeded; accepted partitions remain resumable')
                    sample_at=time.monotonic()+1
                for slot in pool.idle:
                    if not pending: break
                    part=pending.pop(0)
                    attempt=root/'partitions'/f'{part:03d}'/'attempts'/uuid.uuid4().hex
                    attempt.mkdir(parents=True)
                    task=dict(partition_id=part,attempt=attempt.relative_to(root).as_posix(),epoch=epoch,plan_sha256=sha256(plan),
                        input_sha256=plan['input_manifest_sha256'],generation=plan['generation_contract'],run_root=str(root),
                        prepared_dir=str(prepared),settings=settings,lookup_batch=plan['resolver_settings']['lookup_batch'],
                        gpu_settings=plan['resolver_settings'])
                    _publish_json(attempt/'assignment.json',task)
                    _checkpoint(root,'RUNNING',partition_id=part,attempt=task['attempt'])
                    pool.submit(slot,task)
                for result in pool.events():
                    kind,task,slot=result['kind'],result.get('task'),result['slot']
                    if kind=='READY':
                        ready.add(slot);continue
                    owner.check()
                    if kind=='RESULT':
                        value=result['value']
                        if not task or task['epoch']!=epoch or task['partition_id'] in receipts:
                            _checkpoint(root,'IGNORED_LATE_RESPONSE',slot=slot);continue
                        if value['attempt']!=task['attempt']:
                            raise ValueError('Worker returned another assignment')
                        candidate=_candidate(root,plan,task['partition_id'],value['attempt'],value['receipt_sha256'])
                        _checkpoint(root,'CANDIDATE',partition_id=task['partition_id'],attempt=value['attempt'])
                        receipts[task['partition_id']]=cpu._accept(root,plan,candidate)
                        _checkpoint(root,'ACCEPTED',partition_id=task['partition_id'])
                    elif kind in ('ERROR','DEAD'):
                        _checkpoint(root,'FAILED',slot=slot,detail={k:v for k,v in result.items() if k!='task'})
                        # An owner/RPC/CUDA error is never retried as a CPU success.
                        transient=kind=='DEAD' or result.get('error','') in (
                            'Node bridge failed or exceeded request timeout','Node bridge ended before a valid response')
                        if not task or not transient or retries.get(task['partition_id'],0)>=1:
                            raise RuntimeError('GPU pipeline worker failed: '+str({k:v for k,v in result.items() if k!='task'}))
                        part=task['partition_id'];recovered=_recover(root,plan,part,settings)
                        if recovered: receipts[part]=recovered
                        else: pending.insert(0,part)
                        retries[part]=retries.get(part,0)+1
                        ready.discard(slot);init_deadline=time.monotonic()+max(180,request_timeout*2+rpc_timeout)
                        pool.replace(slot)
                    else:
                        raise RuntimeError('Worker initialization failed: '+str(result))
    owner.check()
    return [receipts[p] for p in sorted(receipts)],reused,dict(peak_tree_rss_bytes=peak_rss,
        peak_scratch_bytes=peak_scratch,epoch=epoch,gpu_owner_pid=owner.pid)



@contextmanager
def _locked_owner(root,resume,workers,workspace_mib):
    with ExitStack() as stack:
        if resume:
            stack.enter_context(_run_lock(root))
        owner=stack.enter_context(Owner(workers,workspace_mib,trace_path=str(root/'gpu-overlap.jsonl')))
        if not resume:
            root.mkdir(parents=True)
            stack.enter_context(_run_lock(root))
        yield owner

def run(*,prepared_dir,manifest_sha256,output,resume=False,workers=4,allow_full_selected=False,max_partitions=None,
        threads=4,memory_limit='4GB',max_temp_size='40GB',min_free_bytes=20_000_000_000,request_timeout=60,
        rpc_timeout=120,lookup_batch=1024,workspace_mib=128,rss_limit_bytes=12*1024**3,scratch_limit_bytes=64*1024**3):
    started=time.perf_counter()
    validate_options('gpu',lookup_batch,workspace_mib)
    settings=dict(threads=threads,memory_limit=memory_limit,max_temp_size=max_temp_size)
    per_worker=cpu._settings(workers,threads,memory_limit,max_temp_size)
    if max_partitions is not None and (type(max_partitions) is not int or max_partitions<1):
        raise ValueError('Invalid max_partitions')
    if any(type(v) is not int or v<0 for v in (min_free_bytes,rss_limit_bytes,scratch_limit_bytes)):
        raise ValueError('Invalid resource guard')
    if any(type(v) is not int or not 1<=v<=3600 for v in (request_timeout,rpc_timeout)):
        raise ValueError('Request timeouts must be 1..3600 seconds')
    prepared,root=_path(prepared_dir),_path(output)
    cpu.old._check_output_path(root)
    if root.is_relative_to(prepared) or prepared.is_relative_to(root):
        raise ValueError('Output overlaps prepared input')
    if (resume and not root.is_dir()) or (not resume and root.exists()):
        raise ValueError('Resume requires existing output; new run requires a fresh output')
    manifest=cpu.inputs.verify_inputs(prepared,manifest_sha256)
    if manifest['scope']=='FULL_SELECTED' and not allow_full_selected:
        raise ValueError('Full selected execution requires explicit allow_full_selected')
    initialized=time.perf_counter()
    with _locked_owner(root,resume,workers,workspace_mib) as owner:
        owner_started=time.perf_counter()
        runtime=cpu.old.discover_runtime()
        with cpu.old.MeasuredNode(runtime,root/('metadata-'+uuid.uuid4().hex+'.log'),
                                  worker=cpu.old.WORKER,timeout=request_timeout) as node:
            metadata=node.request({'op':'metadata'})
        options=dict(lookup_batch=lookup_batch,workspace_mib=workspace_mib,protocol=PROTOCOL,
                     frame_limit=MAX_FRAME,candidate_cache_bytes=64*1024**2,allocation_guard=6*1024**3)
        plan=dict(format=FORMAT,algorithm=cpu.old.WEIGHTED_ALGORITHM,input_manifest_sha256=manifest_sha256,
            scope=manifest['scope'],calendar=manifest['calendar'],partitions={str(p):v for p,v in cpu._groups(manifest).items()},
            policy=manifest['policy'],runtime=metadata,resolver_backend='gpu',resolver_runtime=owner.runtime,
            resolver_settings=options,history_layout='grouped',generation_contract=contract(),ready_for_load=False)
        path=root/'run_plan.json'
        if path.exists():
            if _read_json(path)!=plan or file_sha256(path)!=sha256(plan):
                raise ValueError('GPU resume plan differs')
        else:
            _publish_json(path,plan);_publish_json(root/'input_location.json',dict(prepared_dir=str(prepared)))
        event(root,'COMPUTE_PARTITIONS',workers=workers,owner_startup_seconds=owner_started-initialized,
              input_validation_seconds=initialized-started)
        receipts,reused,metrics=_compute(root,prepared,manifest,plan,per_worker,workers,runtime,request_timeout,rpc_timeout,
            max_partitions,min_free_bytes,rss_limit_bytes,scratch_limit_bytes,owner)
        written=[r['partition_id'] for r in receipts if r['partition_id'] not in reused]
        if len(receipts)<len(plan['partitions']):
            return dict(run_status='INCOMPLETE',written_partitions=written,reused_partitions=reused,ready_for_load=False)
        event(root,'FINALIZE_INTERVAL_CACHE')
        cached=cpu._finalize(root,prepared,manifest,plan,receipts,settings)
        directory=cpu.old._within(root,cached['directory'])
        event(root,'WRITE_SNAPSHOT_PARQUETS')
        with connection(root/('history-ownership-'+uuid.uuid4().hex+'.duckdb'),**settings) as con:
            cpu.inputs.open_all(con,prepared,manifest)
            groups={str(p):[] for p in cpu._groups(manifest)}
            for p,pid in con.execute('SELECT partition_id,package_id FROM target_names WHERE package_id IS NOT NULL ORDER BY partition_id,package_id').fetchall():
                groups[str(p)].append(pid)
        history=build_history(cache_dir=directory/'cache',cache_sha256=cached['cache_sha256'],output=directory/'history',
                              partitions=groups,resume=(directory/'history').exists())
        cpu.inputs.verify_bytes(prepared,manifest_sha256);owner.check()
        if contract()!=plan['generation_contract']:
            raise ValueError('GPU generation changed during run')
        stable={k:v for k,v in history.items() if k not in ('written_partitions','reused_partitions')}
        result=dict(format=FORMAT,run_status='COMPLETE',plan_sha256=sha256(plan),partitions=receipts,cache=cached,
                    history=stable,scope=manifest['scope'],full_selection_executed=manifest['scope']=='FULL_SELECTED',
                    upstream_resolution_status='PARTIAL',ready_for_load=False)
        path=root/'run_manifest.json'
        if path.exists():
            if _read_json(path)!=result: raise ValueError('Published GPU result differs')
        else: _publish_json(path,result)
        event(root,'RUN_COMPLETE',seconds=time.perf_counter()-started)
        return dict(run_dir=str(root),run_status='COMPLETE',run_manifest_sha256=file_sha256(path),
                    written_partitions=written,reused_partitions=reused,resources=metrics,
                    elapsed_seconds=time.perf_counter()-started,ready_for_load=False)


def verify_run(*,run_dir,manifest_sha256):
    root=_path(run_dir)
    if file_sha256(root/'run_manifest.json')!=manifest_sha256:
        raise ValueError('GPU run manifest SHA mismatch')
    result,plan=_read_json(root/'run_manifest.json'),_read_json(root/'run_plan.json')
    if (result['format']!=FORMAT or plan['format']!=FORMAT or result['plan_sha256']!=sha256(plan)
            or file_sha256(root/'run_plan.json')!=sha256(plan) or plan['generation_contract']!=contract()
            or plan['resolver_backend']!='gpu' or plan['history_layout']!='grouped'
            or plan['resolver_runtime'].get('backend')!='gpu' or result['run_status']!='COMPLETE'
            or result['ready_for_load'] is not False or result['upstream_resolution_status']!='PARTIAL'):
        raise ValueError('GPU run contract differs')
    prepared=_path(_read_json(root/'input_location.json')['prepared_dir'])
    manifest=cpu.inputs.verify_inputs(prepared,plan['input_manifest_sha256'])
    if (plan['partitions']!={str(p):v for p,v in cpu._groups(manifest).items()} or plan['scope']!=manifest['scope']
            or result['scope']!=manifest['scope'] or result['full_selection_executed']!=(manifest['scope']=='FULL_SELECTED')
            or plan['calendar']!=manifest['calendar'] or plan['policy']!=manifest['policy']):
        raise ValueError('GPU input coverage differs')
    receipts=[_accepted(root,plan,p) for p in sorted(cpu._groups(manifest))]
    if any(r is None for r in receipts) or receipts!=result['partitions']:
        raise ValueError('GPU receipt coverage differs')
    cached=_read_json(root/'cache_complete.json')
    if cached!=result['cache']: raise ValueError('GPU cache pointer differs')
    directory=cpu.old._verify_cache_chain(root,cached,manifest,plan,receipts)
    with connection(root/('verify-'+uuid.uuid4().hex+'.duckdb')) as con:
        cpu._merge(con,root,prepared,manifest,receipts)
        cpu.old._check_cache_derivation(con,directory/'cache')
    verify_history(run_dir=directory/'history',cache_dir=directory/'cache',cache_sha256=cached['cache_sha256'],
                   run_manifest_sha256=result['history']['run_manifest_sha256'])
    return dict(verified=True,scope=manifest['scope'],partitions=len(receipts),snapshots=len(manifest['calendar']),ready_for_load=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('run')
    for name in ('prepared-dir','manifest-sha256','output'): p.add_argument('--'+name,required=True)
    p.add_argument('--workers',type=int,choices=(1,2,4),default=4)
    p.add_argument('--lookup-batch',type=int,default=1024);p.add_argument('--workspace-mib',type=int,default=128)
    p.add_argument('--rpc-timeout',type=int,default=120);p.add_argument('--max-partitions',type=int)
    p.add_argument('--resume',action='store_true');p.add_argument('--allow-full-selected',action='store_true')
    p=sub.add_parser('verify');p.add_argument('--run-dir',required=True);p.add_argument('--manifest-sha256',required=True)
    args=vars(parser.parse_args());command=args.pop('command')
    print(json.dumps({'run':run,'verify':verify_run}[command](**args),ensure_ascii=True,indent=2))


if __name__=='__main__': main()
