"""Measure largest-date preparation/publication and estimate a fresh full-calendar reload."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents.historical_artifact import _publish_json
from pipeline.postgresql.version_dependents.historical_db_keys import verify_keys
from pipeline.postgresql.version_dependents.historical_db_source import FullSource
from pipeline.postgresql.version_dependents.historical_db_partition_probe import COMMAND, run as probe


def fit_nonnegative(points):
    """Least squares seconds = fixed + seconds_per_million * rows_in_millions."""
    xs=[p[0]/1e6 for p in points];ys=[p[1] for p in points]
    xm,ym=sum(xs)/len(xs),sum(ys)/len(ys)
    variance=sum((x-xm)**2 for x in xs)
    slope=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/variance if variance else 0
    intercept=ym-slope*xm
    candidates=[(max(ym,0),0),(0,max(0,sum(x*y for x,y in zip(xs,ys))/sum(x*x for x in xs)))]
    if intercept>=0 and slope>=0:candidates.append((intercept,slope))
    intercept,slope=min(candidates,key=lambda c:sum((y-c[0]-c[1]*x)**2 for x,y in zip(xs,ys)))
    return {'fixed_seconds_per_date':intercept,'seconds_per_million_rows':slope,
            'rmse_seconds':(sum((y-intercept-slope*x)**2 for x,y in zip(xs,ys))/len(xs))**.5}


def estimate(trials, rows_by_date, startup_seconds):
    count=len(rows_by_date);total=sum(r['rows'] for r in rows_by_date)
    phases={}
    predictions=[]
    for name in ('input_seconds','probe_seconds'):
        points=[(r['rows'],r[name]) for r in trials]
        model=fit_nonnegative(points)
        projected=count*model['fixed_seconds_per_date']+total/1e6*model['seconds_per_million_rows']
        phases[name]={'model':model,'projected_seconds':projected}
    sizes=sorted({r['rows'] for r in trials})
    if len(sizes)!=2:raise ValueError('Expected exactly two measured date sizes')
    small=[r for r in trials if r['rows']==sizes[0]]
    large=[r for r in trials if r['rows']==sizes[1]]
    for s in small:
        for l in large:
            predicted=startup_seconds
            for name in phases:
                model=fit_nonnegative([(s['rows'],s[name]),(l['rows'],l[name])])
                predicted+=count*model['fixed_seconds_per_date']+total/1e6*model['seconds_per_million_rows']
            predictions.append(predicted)
    return {'scope':'ALL_DATES_FROM_EMPTY_TARGET_INCLUDING_PREVIOUSLY_LOADED_DATES',
            'dates':count,'rows':total,'startup_seconds':startup_seconds,'phases':phases,
            'central_seconds':startup_seconds+sum(p['projected_seconds'] for p in phases.values()),
            'pair_sensitivity_seconds':[min(predictions),max(predictions)],
            'each_date_at_slowest_observed_seconds':startup_seconds+count*max(r['input_seconds']+r['probe_seconds'] for r in trials),
            'observed_size_range':[sizes[0],sizes[1]],
            'dates_below_small_sample':sum(r['rows']<sizes[0] for r in rows_by_date),
            'notes':['Sensitivity range is not a statistical confidence interval or guaranteed bound.',
                     'Assumes one sequential loader, one source initialization/key preflight, and fixed reference dataset.',
                     'Per-date input includes FullSource.prepare_date recheck; probe includes extra experiment setup/reverification/cleanup.',
                     'Existing Parquet aggregation, production migration/cutover and unimplemented ETL integration are excluded.',
                     'Long-run WAL/checkpoints, accumulated partitions, cache and concurrent I/O may change throughput.']}


def run(output, run_dir, digest, small_day='2023-03-06'):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    began=time.perf_counter();samples=[];stop=threading.Event()
    def monitor():
        while not stop.is_set():
            try:
                result=subprocess.run(['docker','exec','pickage-267-validation','cat','/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory.max'],capture_output=True,text=True,timeout=8)
                values=result.stdout.splitlines()
                if result.returncode==0 and len(values)==2:
                    samples.append({'elapsed_seconds':time.perf_counter()-began,'container_memory_including_cache_bytes':int(values[0]),'container_limit_bytes':int(values[1])})
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
            stop.wait(5)
    watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
    def event(phase,**extra):
        item={'at':datetime.now(timezone.utc).isoformat(),'phase':phase,'elapsed_seconds':time.perf_counter()-began,**extra}
        with (output/'progress.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(item)+'\n')
        print(json.dumps(item),flush=True)
    paths=[Path(__file__),Path(__file__).with_name('historical_db_partition_probe.py'),Path(__file__).with_name('historical_db_source.py'),Path(__file__).with_name('historical_db_benchmark.py')]
    code={p.name:file_sha256(p) for p in paths}
    _publish_json(output/'plan.json',{'source_run_dir':str(Path(run_dir).resolve()),'source_sha256':digest,'code':code,'small_day':small_day})
    source=None
    try:
        event('SOURCE_INITIALIZATION')
        tick=time.perf_counter();source=FullSource(run_dir,digest,output/'source')
        init_seconds=time.perf_counter()-tick
        birth=dict(source.con.execute('SELECT birth_index,count(*) FROM targets GROUP BY birth_index').fetchall())
        rows_by_date=[];cumulative=0
        for i,day in enumerate(source.calendar):
            cumulative+=birth.get(i,0)
            if cumulative!=source.quality[day['snapshot_at']]['target_versions']:raise ValueError('Calendar population differs from quality')
            rows_by_date.append({'snapshot':day['snapshot_at'],'rows':cumulative})
        largest=max(rows_by_date,key=lambda r:(r['rows'],r['snapshot']))
        if small_day not in {r['snapshot'] for r in rows_by_date}:raise ValueError('Small date is not in calendar')
        _publish_json(output/'rows-by-date.json',rows_by_date)
        event('KEY_PREFLIGHT',largest=largest,dates=len(rows_by_date),total_rows=sum(r['rows'] for r in rows_by_date),source_init_seconds=init_seconds)
        tick=time.perf_counter()
        keys=verify_keys(COMMAND,output,source.identity_file,source.version_file,source.calendar,source.lineage,source.expected)
        source.recheck()
        key_seconds=time.perf_counter()-tick
        _publish_json(output/'key-verification.json',keys)
        trials=[]
        for index,day in enumerate((largest['snapshot'],small_day,small_day,largest['snapshot'])):
            case=output/f'trial-{index}-{day}';case.mkdir()
            saved=case/'input';saved.mkdir()
            event('PREPARE_DATE',trial=index,snapshot=day)
            tick=time.perf_counter();metadata,files=source.prepare_date(day)
            input_seconds=time.perf_counter()-tick
            tick=time.perf_counter()
            shutil.copyfile(files['counts'],saved/'counts.tsv')
            _publish_json(saved/'metadata.json',metadata)
            archive_seconds=time.perf_counter()-tick
            metadata_sha=file_sha256(saved/'metadata.json')
            event('DB_PROBE',trial=index,snapshot=day,rows=metadata['counts']['package_version_snapshot'],input_seconds=input_seconds)
            result=probe(case/'database',saved,metadata_sha)
            trial={'snapshot':day,'rows':metadata['counts']['package_version_snapshot'],
                   'input_seconds':input_seconds,'archive_copy_seconds':archive_seconds,'probe_seconds':result['total_seconds'],
                   'input_plus_probe_seconds':input_seconds+result['total_seconds'],
                   'prepared':result['prepared'],'publication':result['publication'],
                   'exact_match':result['published_exact_match'],'cleanup_complete':result['cleanup_complete'],
                   'counts_file_bytes':(saved/'counts.tsv').stat().st_size,'metadata_sha256':metadata_sha}
            if not trial['exact_match'] or not trial['cleanup_complete']:raise ValueError('Probe did not fully verify')
            _publish_json(case/'result.json',trial);trials.append(trial)
            event('TRIAL_COMPLETE',trial=index,**{k:trial[k] for k in ('snapshot','rows','input_seconds','probe_seconds','input_plus_probe_seconds')})
        if code!={p.name:file_sha256(p) for p in paths}:raise ValueError('Experiment code changed')
        source.recheck()
        report={'status':'COMPLETE','source_init_seconds':init_seconds,'key_preflight_seconds':key_seconds,
                'trials':trials,'largest':largest,'estimate':estimate(trials,rows_by_date,init_seconds+key_seconds),
                'sampled_container_peak_including_cache_bytes':max((s['container_memory_including_cache_bytes'] for s in samples),default=None),
                'container_memory_samples':samples,'total_experiment_seconds':time.perf_counter()-began,
                'actual_full_service_reload':False}
        _publish_json(output/'result.json',report);event('COMPLETE',estimate=report['estimate'])
        return report
    except BaseException as error:
        event('FAILED',error=str(error));raise
    finally:
        if source:source.close()
        stop.set();watcher.join(timeout=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--run-dir',required=True)
    parser.add_argument('--manifest-sha256',required=True)
    args=parser.parse_args();run(args.output,args.run_dir,args.manifest_sha256)


if __name__=='__main__':main()
