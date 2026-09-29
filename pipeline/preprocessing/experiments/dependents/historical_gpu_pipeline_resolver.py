"""CPU npm normalization and interval mapping around cached GPU package requests."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import sys
import time
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes
from pipeline.preprocessing.version_dependents.historical import _check_lookup
from pipeline.preprocessing.version_dependents.historical_gpu import intervals_from_ranks, validate_plan
from pipeline.preprocessing.version_dependents.historical_production_resolver import _insert, validate_options, MAX_FRAME_BYTES
from pipeline.preprocessing.experiments.dependents.historical_gpu_owner import MAX_FRAME

NORMALIZER=Path(__file__).with_name('historical_gpu_pipeline_normalize.cjs')


def _key(identity,partition_id,name):
    return json.dumps(dict(attempt=identity,partition_id=partition_id,package=name),sort_keys=True,separators=(',',':'))


def _runtime(value,metadata):
    for key,expected in (('node','node_version'),('semver','semver_version'),('package_arg','package_arg_version'),
                         ('options','options'),('tie','equal_precedence_tie')):
        if expected not in metadata or value.get(key)!=metadata[expected]:
            raise ValueError('Normalizer runtime differs: '+key)


def _base_matches(plan,message,metadata):
    if plan.get('accepted')!=message['candidates'] or plan.get('rejected')!=[] or plan.get('package_key')!=message['package_key']:
        raise ValueError('Normalizer candidate/package identity differs')
    births={c['version']:c['birth_index'] for c in message['candidates']}
    versions=plan.get('rank_to_version',[])
    if (len(births)!=len(message['candidates']) or len(versions)!=len(births) or set(versions)!=set(births)
            or plan.get('birth_by_rank')!=[births[v] for v in versions]
            or plan.get('known_package') is not message['known_package'] or plan.get('snapshot_count')!=message['snapshot_count']):
        raise ValueError('Normalizer rank/birth identity differs')
    _runtime(plan.get('runtime',{}),metadata)
    validate_plan(plan)


def _batches(cursor,key,lookup_batch):
    pending=[]
    base=len(canonical_bytes(dict(op='batch',package_key=key,requirements=[])))
    size=base
    while True:
        rows=cursor.fetchmany(lookup_batch)
        if not rows:
            break
        for row in rows:
            addition=len(canonical_bytes(row[1]))+bool(pending)
            if pending and (len(pending)>=lookup_batch or size+addition>=MAX_FRAME_BYTES):
                yield pending
                pending=[];size=base;addition=len(canonical_bytes(row[1]))
            if size+addition>=MAX_FRAME_BYTES:
                raise ValueError('One requirement exceeds Node frame limit')
            pending.append(row);size+=addition
    if pending:
        yield pending


def resolve_partition(con,node,metadata,partition_id,n,*,client,attempt_identity,lookup_batch=1024,workspace_mib=128,event=None):
    validate_options('gpu',lookup_batch,workspace_mib)
    if type(n) is not int or not 1<=n<=4096:
        raise ValueError('Invalid calendar')
    lookup_batch=min(lookup_batch,(MAX_FRAME-65536)//(n*8))
    started=time.perf_counter(); metrics=Counter()
    def request(message,normalize=True):
        if len(canonical_bytes(message))>=MAX_FRAME_BYTES:
            raise ValueError('Node request exceeds framing bound')
        tick=time.perf_counter()
        if normalize and event: event('NORMALIZE_BEGIN')
        try:
            result=node.request(message)
            if len(canonical_bytes(result))>=MAX_FRAME_BYTES:
                raise ValueError('Node response exceeds framing bound')
            return result
        finally:
            if normalize:
                metrics['normalize_seconds']+=time.perf_counter()-tick
                if event: event('NORMALIZE_END')
    def details(value):
        for key,number in (value or {}).items():
            if isinstance(number,(int,float)):
                if key.startswith('peak_') or key in ('candidate_cache_bytes','chunk_rows'):
                    metrics[key]=max(metrics[key],number)
                else:
                    metrics[key]+=number
    con.execute('''CREATE TEMP TABLE lookup_intervals(lookup_id BIGINT,start_index INTEGER,end_index INTEGER,
        status VARCHAR,normalized_range VARCHAR,target_package_id INTEGER,target_version VARCHAR)''')
    packages=con.execute('SELECT name,package_id,known_package FROM target_names WHERE partition_id=? ORDER BY name',[partition_id]).fetchall()
    for name,package_id,known in packages:
        if type(known) is not bool or known!=(package_id is not None):
            raise ValueError('Target identity differs')
        tick=time.perf_counter()
        candidates=[dict(version=v,birth_index=int(b)) for v,b in con.execute(
            'SELECT version,birth_index FROM target_population WHERE name=? ORDER BY birth_index,version',[name]).fetchall()]
        metrics['candidate_read_seconds']+=time.perf_counter()-tick
        key=_key(attempt_identity,partition_id,name)
        node_active=gpu_active=False; cursor=None; count=0
        try:
            message=dict(op='begin',package_key=key,name=name,known_package=known,candidates=candidates,snapshot_count=n)
            base=request(message);node_active=True
            _base_matches(base,message,metadata)
            details(client.begin(key,base));gpu_active=True
            metrics['packages']+=1;metrics['candidates']+=len(candidates)
            cursor=con.cursor()
            tick=time.perf_counter()
            cursor.execute('SELECT lookup_id,requirement FROM lookups WHERE declared_name=? ORDER BY lookup_id',[name])
            metrics['lookup_read_seconds']+=time.perf_counter()-tick
            for rows in _batches(cursor,key,lookup_batch):
                requirements=[r for _,r in rows]
                response=request(dict(op='batch',package_key=key,requirements=requirements))
                if response.get('package_key')!=key or [r.get('requirement') for r in response.get('lookups',[])]!=requirements:
                    raise ValueError('Normalizer changed lookup order, requirement or package')
                _runtime(response.get('runtime',{}),metadata)
                plan={**base,'lookups':response['lookups']};validate_plan(plan)
                tick=time.perf_counter();ranks,detail=client.ranks(key,plan)
                metrics['numeric_seconds']+=time.perf_counter()-tick;details(detail)
                tick=time.perf_counter();resolved=intervals_from_ranks(plan,ranks)
                metrics['interval_seconds']+=time.perf_counter()-tick
                if len(resolved)!=len(rows):
                    raise ValueError('Resolved lookup count differs')
                tick=time.perf_counter();output=[]
                for (lookup_id,requirement),item in zip(rows,resolved):
                    if item['requirement']!=requirement:
                        raise ValueError('Resolved requirement changed')
                    _check_lookup(item['intervals'],n)
                    for interval in item['intervals']:
                        output.append((lookup_id,interval['start_index'],interval['end_index'],interval['status'],
                            interval['normalized_range'],package_id if interval['status']=='RESOLVED' else None,interval['target_version']))
                metrics['mapping_seconds']+=time.perf_counter()-tick
                if output:
                    tick=time.perf_counter();_insert(con,output);metrics['insert_seconds']+=time.perf_counter()-tick
                metrics['lookup_intervals']+=len(output);metrics['resolved_lookups']+=len(rows)
                metrics['lookup_requests']+=1;count+=len(rows)
            if not count:
                metrics['zero_lookup_packages']+=1
        finally:
            prior_error=sys.exc_info()[0] is not None
            cleanup_error=None
            if cursor is not None: cursor.close()
            if node_active:
                try:
                    if request(dict(op='end',package_key=key),normalize=False).get('package_key')!=key:
                        raise ValueError('Node ended another package')
                except Exception as error:
                    cleanup_error=error
            if gpu_active:
                try: details(client.end(key))
                except Exception as error: cleanup_error=cleanup_error or error
            if cleanup_error is not None and not prior_error:
                raise cleanup_error
    return {**metrics,'seconds':time.perf_counter()-started,'backend':'gpu','partition_id':partition_id}
