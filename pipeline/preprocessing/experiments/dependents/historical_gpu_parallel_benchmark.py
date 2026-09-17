"""Bounded single-GPU pipeline sample comparison; never extrapolates a full ETA."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.experiments.dependents import historical_gpu_parallel as gpu
from pipeline.preprocessing.version_dependents import historical_parallel as cpu
from pipeline.preprocessing.experiments.dependents.historical_parallel_benchmark import compare_runs, read
from pipeline.preprocessing.experiments.dependents.historical_production_backend_benchmark import run_metrics, _write
from pipeline.preprocessing.experiments.dependents.historical_throughput_benchmark import _resources, _disk


def _intervals(path, name):
    if not path.exists(): return []
    active = None
    result = []
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['phase'] == name + '_BEGIN': active = row['at_ns']
        elif row['phase'] == name + '_END' and active is not None:
            result.append((active, row['at_ns']))
            active = None
    return result


def _union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]: merged[-1][1] = max(end, merged[-1][1])
        else: merged.append([start, end])
    return merged


def overlap(root):
    root = Path(root)
    gpu_intervals = _intervals(root / 'gpu-overlap.jsonl', 'GPU_CALCULATE')
    cpu_intervals = [span for path in root.glob('partitions/*/attempts/*/overlap.jsonl')
                     for phase in ('NORMALIZE', 'AGGREGATE') for span in _intervals(path, phase)]
    intersections = [(max(a, c), min(b, d)) for a, b in gpu_intervals for c, d in cpu_intervals
                     if max(a, c) < min(b, d)]
    return {'gpu_request_intervals': len(gpu_intervals),
            'gpu_request_wall_seconds': sum(b-a for a,b in _union(gpu_intervals))/1e9,
            'cpu_normalize_or_aggregate_overlap_seconds': sum(b-a for a,b in _union(intersections))/1e9,
            'meaning': 'wall overlap of GPU rank requests with CPU Node normalization or DuckDB aggregation; not CUDA kernel utilization'}


def gpu_metrics(output):
    manifest = read(Path(output)/'run_manifest.json')
    receipts = [read(Path(output)/p['attempt']/'receipt.json') for p in manifest['partitions']]
    return {key:sum(r['metrics'].get(key,0) for r in receipts)
            for key in ('queue_wait_seconds','rpc_seconds','ipc_encode_seconds','request_bytes','response_bytes')}


def measure(output, prepared, reference, workers, backend):
    runner = gpu if backend == 'gpu' else cpu
    kwargs = {} if backend == 'gpu' else {'history_layout': 'grouped'}
    started = time.perf_counter()
    result = runner.run(prepared_dir=prepared, manifest_sha256=file_sha256(Path(prepared)/'input_manifest.json'),
                        output=output, workers=workers, **kwargs)
    computed = time.perf_counter()
    verification = runner.verify_run(run_dir=output, manifest_sha256=result['run_manifest_sha256'])
    verified = time.perf_counter()
    comparison = compare_runs(reference, output)
    phases = run_metrics(output)
    if backend == 'gpu':
        phases.update(gpu_metrics(output))
    return dict(backend=backend, workers=workers, result=result, verification=verification, comparison=comparison,
                run_seconds=computed-started, verify_seconds=verified-computed, preprocessing_seconds=verified-started,
                comparison_seconds=time.perf_counter()-verified, phases=phases,
                overlap=overlap(output) if backend=='gpu' else None)


def supervise(output, prepared, reference, repeats=3):
    if type(repeats) is not int or not 1 <= repeats <= 5: raise ValueError('repeats must be 1..5')
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    generation = gpu.contract()
    measurements = []
    def trial(label, backend, workers):
        with (root/(label+'.log')).open('w',encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable,'-m',__name__ if __name__!='__main__' else
                'pipeline.preprocessing.experiments.dependents.historical_gpu_parallel_benchmark','measure','--output',str(root/label),
                '--prepared',str(prepared),'--reference',str(reference),'--workers',str(workers),'--backend',backend],
                stdout=log,stderr=subprocess.STDOUT)
            peak_rss=peak_scratch=0
            cpu_times={}
            try:
                while process.poll() is None:
                    resource,disk=_resources(process.pid),_disk(root/label)
                    peak_rss=max(peak_rss,resource['tree_rss_bytes']);peak_scratch=max(peak_scratch,disk['scratch_bytes'])
                    cpu_times.update(resource['cpu_seconds_by_pid'])
                    _write(root/'progress.json',dict(status='RUNNING',trial=label,pid=process.pid,
                        completed_trials=len(measurements),peak_tree_rss_bytes=peak_rss,peak_scratch_bytes=peak_scratch))
                    time.sleep(1)
            finally:
                if process.poll() is None:
                    process.terminate();process.wait(timeout=15)
            if process.returncode: raise RuntimeError(f'{label} failed; inspect {root/(label+".log")}')
        value=read(root/(label+'.json'))
        value.update(label=label,resources=dict(peak_tree_rss_bytes=peak_rss,peak_scratch_bytes=peak_scratch,
                                               cpu_seconds=sum(cpu_times.values())))
        measurements.append(value)
        if gpu.contract()!=generation: raise ValueError('Generation changed during benchmark')
        _write(root/'measurements.json',measurements)
        return value
    try:
        probes=[trial('probe-gpu'+str(w),'gpu',w) for w in (1,2,4)]
        best=min(probes,key=lambda row:row['preprocessing_seconds'])['workers']
        repeated=[]
        for i in range(1,repeats+1):
            order=(('cpu',4),('gpu',best)) if i%2 else (('gpu',best),('cpu',4))
            for backend,workers in order: repeated.append(trial(f'{backend}-r{i}',backend,workers))
        medians={backend:{key:statistics.median(r[key] for r in repeated if r['backend']==backend)
                         for key in ('run_seconds','verify_seconds','preprocessing_seconds')}
                 for backend in ('cpu','gpu')}
        improvement=1-medians['gpu']['preprocessing_seconds']/medians['cpu']['preprocessing_seconds']
        result=dict(status='PASS',generation_contract=generation,selected_gpu_cpu_workers=best,repeats=repeats,
                    measurements=measurements,medians=medians,improvement_fraction=improvement,
                    meets_ten_percent_sample_guideline=improvement>=.1,input_preparation_shared=True,
                    scope='same prepared 32-target sample; preparation excluded; no full-population ETA')
        _write(root/'results.json',result)
        _write(root/'progress.json',dict(status='COMPLETE',trials=len(measurements)))
        return result
    except BaseException as error:
        _write(root/'progress.json',dict(status='FAILED',error=str(error),completed_trials=len(measurements)))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('measure','supervise'))
    for name in ('output','prepared','reference'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--workers',type=int,choices=(1,2,4),default=4)
    parser.add_argument('--backend',choices=('cpu','gpu'),default='gpu')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.command=='measure':
        result=measure(args.output,args.prepared,args.reference,args.workers,args.backend)
        _write(Path(args.output).with_suffix('.json'),result)
    else: result=supervise(args.output,args.prepared,args.reference,args.repeats)
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__': main()
