"""Semantic comparison and isolated 1/2/4 CPU worker measurements."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.experiments.dependents.historical_production_backend_benchmark import inventory as legacy_inventory, run_metrics, _write
from pipeline.preprocessing.version_dependents.historical_production_input import TABLES
from pipeline.preprocessing.experiments.dependents.historical_throughput_benchmark import _resources, _disk
from pipeline.preprocessing.version_dependents import historical_parallel as runner


def read(path):
    return json.loads(Path(path).read_bytes())


def inventory(directory):
    root = Path(directory)
    plan = read(root / 'run_plan.json')
    if not plan['format'].startswith('historical-parallel-cpu-'):
        return legacy_inventory(root)
    manifest = read(root / 'run_manifest.json')
    prepared = Path(read(root / 'input_location.json')['prepared_dir'])
    input_manifest = read(prepared / 'input_manifest.json')
    result = {f'input/{t}': ([str(prepared / p['files'][t]['name'])
                             for p in input_manifest['partitions'].values() if t in p['files']], []) for t in TABLES}
    for table in runner.FILES:
        result['partition/' + table] = ([str(root / p['attempt'] / (table + '.parquet'))
                                         for p in manifest['partitions']], [])
    finalization = root / manifest['cache']['directory']
    for table in ('target_population', 'count_intervals', 'quality'):
        result['cache/' + table] = ([str(finalization / 'cache' / (table + '.parquet'))], [])
    for table in ('counts', 'quality'):
        files = []
        if plan.get('history_layout', 'daily') == 'grouped':
            grouped = read(finalization / 'history' / 'run_manifest.json')
            if table == 'quality':
                files = [str(finalization / 'history' / grouped['quality']['name'])]
            else:
                files = [str(finalization / 'history' / p['file']['name'])
                         for p in grouped['partitions'].values() if p.get('file') is not None]
        else:
            for day in manifest['history']['completed_dates']:
                parent = finalization / 'history' / ('snapshot=' + day)
                pointer = read(parent / 'complete.json')
                files.append(str(parent / 'attempts' / pointer['attempt_id'] / (table + '.parquet')))
        result['daily/' + table] = (files, ['run_plan_sha256'] if table == 'quality' else [])
    return result


def compare_runs(left, right):
    a, b = inventory(left), inventory(right)
    if set(a) != set(b) or len(a) != 13:
        raise ValueError('Expected exactly 13 semantic table groups')
    with runner.connection(Path(right) / ('comparison-' + uuid.uuid4().hex + '.duckdb')) as con:
        result = {}
        for label, (files, excluded) in a.items():
            if b[label][1] != excluded:
                raise ValueError('Unexpected comparison exclusions')
            for side, paths in (('left', files), ('right', b[label][0])):
                if paths:
                    con.read_parquet(paths, hive_partitioning=False).create_view(side + '_values', replace=True)
                elif label == 'daily/counts':
                    con.execute('CREATE OR REPLACE TEMP VIEW ' + side + '_values AS SELECT '
                                'NULL::INTEGER package_id,NULL::VARCHAR version,NULL::DATE snapshot_at,'
                                'NULL::TIMESTAMPTZ snapshot_timestamp,NULL::INTEGER dependents_count WHERE false')
                else:
                    raise ValueError('Unexpected empty comparison input: ' + label)
            columns = '*' + (' EXCLUDE (' + ','.join(excluded) + ')' if excluded else '')
            lquery, rquery = ('SELECT ' + columns + ' FROM ' + s + '_values' for s in ('left', 'right'))
            if con.execute('DESCRIBE ' + lquery).fetchall() != con.execute('DESCRIBE ' + rquery).fetchall():
                raise ValueError('Comparison schema differs: ' + label)
            if con.execute(f'SELECT EXISTS (({lquery} EXCEPT ALL {rquery}) UNION ALL '
                           f'({rquery} EXCEPT ALL {lquery}))').fetchone()[0]:
                raise ValueError('Comparison values differ: ' + label)
            result[label] = {'equal': True, 'rows': con.execute('SELECT count(*) FROM left_values').fetchone()[0],
                             'left_files': len(files), 'right_files': len(b[label][0])}
    return result


def measure(output, prepared, reference, workers):
    started = time.perf_counter()
    result = runner.run(prepared_dir=prepared, manifest_sha256=file_sha256(Path(prepared) / 'input_manifest.json'),
                        output=output, workers=workers)
    computed = time.perf_counter()
    verification = runner.verify_run(run_dir=output, manifest_sha256=result['run_manifest_sha256'])
    verified = time.perf_counter()
    compared = compare_runs(reference, output)
    return {'workers': workers, 'result': result, 'verification': verification, 'comparison': compared,
            'run_seconds': computed - started, 'verify_seconds': verified - computed,
            'preprocessing_seconds': verified - started, 'comparison_seconds': time.perf_counter() - verified,
            'phases': run_metrics(output)}


def supervise(root, prepared, reference, repeats=1):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    generation = runner.contract()
    measurements = []
    for repeat in range(1, repeats + 1):
        for workers in (1, 2, 4):
            label = f'w{workers}-r{repeat}'
            with (root / (label + '.log')).open('w', encoding='utf-8') as log:
                process = subprocess.Popen([sys.executable, '-m',
                    'pipeline.preprocessing.experiments.dependents.historical_parallel_benchmark', 'measure',
                    '--output', str(root / label), '--prepared', str(prepared),
                    '--reference', str(reference), '--workers', str(workers)], stdout=log, stderr=subprocess.STDOUT)
                peak_rss = peak_scratch = 0
                cpu = {}
                try:
                    while process.poll() is None:
                        resource, disk = _resources(process.pid), _disk(root / label)
                        peak_rss = max(peak_rss, resource['tree_rss_bytes'])
                        peak_scratch = max(peak_scratch, disk['scratch_bytes'])
                        cpu.update(resource['cpu_seconds_by_pid'])
                        _write(root / 'progress.json', {'status': 'RUNNING', 'trial': label,
                            'pid': process.pid, 'peak_tree_rss_bytes': peak_rss, 'peak_scratch_bytes': peak_scratch})
                        time.sleep(1)
                finally:
                    if process.poll() is None:
                        process.terminate()  # Coordinator's job handles clean up the worker tree.
                        process.wait(timeout=15)
                if process.returncode:
                    raise RuntimeError(f'{label} failed; see {root / (label + ".log")}')
            result = read(root / (label + '.json'))
            result['resources'] = {'peak_tree_rss_bytes': peak_rss, 'peak_scratch_bytes': peak_scratch,
                                   'cpu_seconds': sum(cpu.values())}
            measurements.append(result)
            if runner.contract() != generation:
                raise ValueError('Generation changed during benchmark')
    result = {'status': 'PASS', 'generation_contract': generation, 'measurements': measurements,
              'repeats': repeats, 'input_preparation_shared': True,
              'scope': '32-target sample; no full-population ETA'}
    _write(root / 'results.json', result)
    _write(root / 'progress.json', {'status': 'COMPLETE', 'trials': len(measurements)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('measure', 'supervise'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--prepared', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args()
    if args.command == 'measure':
        result = measure(args.output, args.prepared, args.reference, args.workers)
        _write(Path(args.output).with_suffix('.json'), result)
    else:
        result = supervise(args.output, args.prepared, args.reference, args.repeats)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
