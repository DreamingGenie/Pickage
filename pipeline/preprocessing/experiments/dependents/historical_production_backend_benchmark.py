"""Sequential 32-target production CPU/GPU comparison, including common preparation.

The reference must already have been verified by its original generating code.
This tool never relaxes the current production verifier for legacy artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import duckdb

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents.historical_production import contract, run, verify_run, WEIGHTED_ALGORITHM
from pipeline.preprocessing.version_dependents.historical_production_input import prepare, TABLES
from pipeline.preprocessing.experiments.dependents.historical_throughput_benchmark import _selection, _resources, _disk, _write as _atomic_write


def _write(path, body):
    # Windows readers/scanners can briefly hold the old progress file open.
    for attempt in range(10):
        try:
            return _atomic_write(path, body)
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05)


def read(path):
    return json.loads(Path(path).read_bytes())


def protected(reference):
    if reference['status'] != 'PASS' or reference['verification']['verified'] is not True:
        raise ValueError('Reference was not verified with its generating code')
    if reference['verification']['scope'] != 'SAMPLE' or reference['verification']['snapshots'] != 229:
        raise ValueError('Reference must be the 229-date sample')
    paths = reference['protected_files_sha256']
    manifest = str(Path(reference['run_dir']) / 'run_manifest.json')
    if paths.get(manifest) != reference['run_manifest_sha256']:
        raise ValueError('Reference manifest is not protected')
    for name, digest in paths.items():
        if file_sha256(name) != digest:
            raise ValueError('Reference file changed: ' + name)
    return len(paths)


def inventory(directory):
    directory = Path(directory)
    manifest = read(directory / 'run_manifest.json')
    plan = read(directory / 'run_plan.json')
    cache = directory / manifest['cache']['directory'] / 'cache'
    result = {f'input/{table}': ([str(Path(plan['prepared_dir']) / (table + '.parquet'))], [])
              for table in TABLES}
    for table in ('lookup_intervals', 'counts', 'source_summary', 'status_deltas'):
        result['partition/' + table] = ([str(directory / p['attempt'] / (table + '.parquet'))
                                         for p in manifest['partitions']], [])
    for table in ('target_population', 'count_intervals', 'quality'):
        result['cache/' + table] = ([str(cache / (table + '.parquet'))], [])
    history = directory / manifest['cache']['directory'] / 'history'
    for table in ('counts', 'quality'):
        paths = []
        for day in manifest['history']['completed_dates']:
            parent = history / ('snapshot=' + day)
            marker = read(parent / 'complete.json')
            paths.append(str(parent / 'attempts' / marker['attempt_id'] / (table + '.parquet')))
        # Each output's own verifier checks these plan identities, which differ by backend.
        result['daily/' + table] = (paths, ['run_plan_sha256'] if table == 'quality' else [])
    return result


def compare_runs(left, right):
    a, b = inventory(left), inventory(right)
    if set(a) != set(b):
        raise ValueError('Comparison table coverage differs')
    result = {}
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        con.execute("SET memory_limit='4GB'")
        con.execute("SET temp_directory=?", [str(Path(right) / ('comparison-scratch-' + uuid.uuid4().hex))])
        con.execute("SET max_temp_directory_size='40GB'")
        for label in a:
            lpaths, exclude = a[label]
            rpaths, rexclude = b[label]
            if exclude != rexclude or len(lpaths) != len(rpaths):
                raise ValueError('Comparison file coverage differs: ' + label)
            con.read_parquet(lpaths, hive_partitioning=False).create_view('left_values', replace=True)
            con.read_parquet(rpaths, hive_partitioning=False).create_view('right_values', replace=True)
            columns = '*' + (' EXCLUDE (' + ','.join(exclude) + ')' if exclude else '')
            lquery, rquery = ('SELECT ' + columns + ' FROM ' + side + '_values' for side in ('left', 'right'))
            if con.execute('DESCRIBE ' + lquery).fetchall() != con.execute('DESCRIBE ' + rquery).fetchall():
                raise ValueError('Comparison schema differs: ' + label)
            mismatch = con.execute(f'SELECT EXISTS (({lquery} EXCEPT ALL {rquery}) UNION ALL ({rquery} EXCEPT ALL {lquery}))').fetchone()[0]
            if mismatch:
                raise ValueError('Production values differ: ' + label)
            result[label] = {'rows': con.execute('SELECT count(*) FROM left_values').fetchone()[0],
                             'left_files': len(lpaths), 'right_files': len(rpaths), 'equal': True}
    return result


def run_metrics(directory):
    directory = Path(directory)
    manifest = read(directory / 'run_manifest.json')
    receipts = [read(directory / p['attempt'] / 'receipt.json') for p in manifest['partitions']]
    phases = [read_line for line in (directory / 'progress.jsonl').read_text(encoding='utf-8').splitlines()
              if (read_line := json.loads(line))]
    first = {}
    for row in phases:
        first.setdefault(row['phase'], row['at_unix'])
    result = {'partitions': len(receipts), 'partition_total_seconds': sum(r['seconds'] for r in receipts),
              'aggregation_seconds': sum(r['metrics']['aggregation']['seconds'] for r in receipts),
              'finalize_cache_seconds': first['WRITE_SNAPSHOT_PARQUETS'] - first['FINALIZE_INTERVAL_CACHE'],
              'write_dates_and_final_checks_seconds': first['RUN_COMPLETE'] - first['WRITE_SNAPSHOT_PARQUETS']}
    for key in ('resolution_seconds', 'normalize_seconds', 'numeric_seconds', 'interval_seconds',
                'mapping_seconds', 'insert_seconds', 'candidate_read_seconds', 'lookup_read_seconds',
                'host_preparation_seconds', 'h2d_seconds', 'compute_seconds', 'd2h_seconds',
                'resolved_lookups', 'lookup_intervals', 'zero_lookup_packages'):
        result[key] = sum(r['metrics'].get(key, 0) for r in receipts)
    for key in ('peak_allocated_bytes', 'peak_reserved_bytes'):
        result[key] = max((r['metrics'].get(key, 0) for r in receipts), default=0)
    return result


def worker(args):
    root = Path(args.output).resolve()
    started = time.perf_counter()
    generations = {b: contract(WEIGHTED_ALGORITHM, b) for b in ('cpu', 'gpu')}
    selection, samples = _selection(args.selection, args.selection_sha)
    if args.stage == 'prepare':
        pins = selection['pinned_inputs']
        h1, profile, csv = (pins[k] for k in ('h1_input_manifest', 'h5_a_profile_manifest', 'selection_csv'))
        result = prepare(h1_dir=Path(h1['path']).parent, h1_manifest_sha256=h1['sha256'],
                         profile_manifest=profile['path'], profile_manifest_sha256=profile['sha256'],
                         selection_csv=csv['path'], selection_sha256=csv['sha256'],
                         sample_names=[r['name'] for r in samples[32]], output=root / 'input',
                         partition_count=128, threads=4, memory_limit='4GB', max_temp_size='40GB')
        expected = dict(target_names=32, target_population=sum(r['V'] for r in samples[32]),
                        lookups=sum(r['Q'] for r in samples[32]), declarations=sum(r['D'] for r in samples[32]))
        if result['rows'] != expected:
            raise ValueError('Prepared rows differ from selected full-source profile')
    elif args.stage == 'compare':
        if file_sha256(args.reference) != args.reference_sha:
            raise ValueError('Reference verification record changed')
        reference = read(args.reference)
        count = protected(reference)
        result = {'baseline_cpu': compare_runs(reference['run_dir'], root / 'cpu'),
                  'cpu_gpu': compare_runs(root / 'cpu', root / 'gpu'),
                  'protected_files_unchanged': count, 'baseline_commit': reference['commit'],
                  'baseline_manifest_sha256': reference['run_manifest_sha256']}
        protected(reference)
    else:
        backend, action = args.stage.split('-')
        prepared = read(root / 'prepare.json')['result']
        if action == 'run':
            result = run(prepared_dir=prepared['prepared_dir'], manifest_sha256=prepared['manifest_sha256'],
                         output=root / backend, resolver_backend=backend, algorithm=WEIGHTED_ALGORITHM,
                         threads=4, memory_limit='4GB', max_temp_size='40GB')
            if result['run_status'] != 'COMPLETE' or result['scope'] != 'SAMPLE':
                raise ValueError('Sample run did not complete')
            result['phase_metrics'] = run_metrics(root / backend)
        else:
            computed = read(root / (backend + '-run.json'))['result']
            result = verify_run(run_dir=root / backend, manifest_sha256=computed['run_manifest_sha256'])
    if generations != {b: contract(WEIGHTED_ALGORITHM, b) for b in ('cpu', 'gpu')}:
        raise ValueError('Generation changed during measurement')
    if file_sha256(__file__) != args.harness_sha:
        raise ValueError('Measurement code changed during stage')
    _write(root / (args.stage + '.json'), {'stage': args.stage, 'elapsed_seconds': time.perf_counter() - started,
                                         'result': result, 'generation': generations})


def benchmark(args):
    if os.name != 'nt':
        raise RuntimeError('Local resource observer requires Windows')
    root = Path(args.output).resolve()
    if len(str(root)) > 83:
        raise ValueError('Use a short benchmark output path')
    if file_sha256(args.reference) != args.reference_sha:
        raise ValueError('Reference verification record changed')
    protected(read(args.reference))
    _selection(args.selection, args.selection_sha)
    generations = {b: contract(WEIGHTED_ALGORITHM, b) for b in ('cpu', 'gpu')}
    root.mkdir(parents=True, exist_ok=False)
    harness_sha = file_sha256(__file__)
    observations = []
    for stage in ('prepare', 'cpu-run', 'cpu-verify', 'gpu-run', 'gpu-verify', 'compare'):
        if generations != {b: contract(WEIGHTED_ALGORITHM, b) for b in ('cpu', 'gpu')}:
            raise ValueError('Generation changed between measurement stages')
        command = [sys.executable, '-B', '-m', 'pipeline.preprocessing.experiments.dependents.historical_production_backend_benchmark', '--output', str(root),
                   '--selection', str(Path(args.selection).resolve()), '--selection-sha', args.selection_sha,
                   '--reference', str(Path(args.reference).resolve()), '--reference-sha', args.reference_sha,
                   '--stage', stage, '--harness-sha', harness_sha]
        started = time.perf_counter()
        peak = dict(tree_rss_bytes=0, scratch_bytes=0, working_database_bytes=0, output_bytes=0)
        samples = 0
        with (root / (stage + '.log')).open('wb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            while process.poll() is None:
                resource, disk = _resources(process.pid), _disk(root)
                for key in peak:
                    peak[key] = max(peak[key], resource.get(key, disk.get(key, 0)))
                samples += 1
                _write(root / 'status.json', {'status': 'RUNNING', 'stage': stage, 'pid': process.pid,
                                             'elapsed_seconds': time.perf_counter() - started, 'peak': peak})
                time.sleep(1)
            exit_code = process.wait()
        observation = {'stage': stage, 'exit_code': exit_code, 'peak': peak, 'samples': samples,
                       'observed_seconds': time.perf_counter() - started}
        observations.append(observation)
        _write(root / (stage + '-resources.json'), observation)
        if exit_code:
            _write(root / 'status.json', {'status': 'FAILED', **observation})
            raise RuntimeError('Benchmark failed: ' + stage + '; see stage log')
        print(json.dumps(observation), flush=True)
    if file_sha256(__file__) != harness_sha:
        raise ValueError('Measurement code changed')
    stages = {o['stage']: read(root / (o['stage'] + '.json')) for o in observations}
    totals = {b: sum(stages[s]['elapsed_seconds'] for s in ('prepare', b + '-run', b + '-verify'))
              for b in ('cpu', 'gpu')}
    report = {'status': 'PASS', 'targets': 32, 'snapshots': 229,
              'shared_preparation_count': 1, 'total_seconds_with_shared_preparation': totals,
              'stages': stages, 'resources': observations, 'harness_sha256': harness_sha,
              'selection_sha256': args.selection_sha, 'reference_sha256': args.reference_sha,
              'full_selection_executed': False, 'db_load_executed': False, 'ready_for_load': False,
              'limits': 'One sequential run per backend; startup included; shared input prepared once. '
                        'RSS and cumulative task-directory disk are 1-second samples. Comparison excluded from totals. '
                        'This 32-target sample excludes the three extreme packages and does not establish full-population throughput.'}
    _write(root / 'report.json', report)
    _write(root / 'status.json', {'status': 'COMPLETE', 'report': str(root / 'report.json')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'selection', 'selection-sha', 'reference', 'reference-sha'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--stage', choices=('prepare', 'cpu-run', 'cpu-verify', 'gpu-run', 'gpu-verify', 'compare'))
    parser.add_argument('--harness-sha')
    args = parser.parse_args()
    if args.stage:
        worker(args)
    else:
        benchmark(args)


if __name__ == '__main__':
    main()
