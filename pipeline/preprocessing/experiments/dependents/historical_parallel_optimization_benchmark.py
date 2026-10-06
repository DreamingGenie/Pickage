"""Isolated preparation profiling for archived and current generation code."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
import functools
import json
from pathlib import Path
import time
import os
import subprocess
import sys


def profile_prepare(source_plan, output):
    from pipeline.preprocessing.version_dependents import historical_parallel_input as module
    source = json.loads(Path(source_plan).read_bytes())
    rows, stack = {}, []
    def wrap(name, original):
        @functools.wraps(original)
        def call(*args, **kwargs):
            started = time.perf_counter()
            frame = {'children': 0.0}
            stack.append(frame)
            try:
                return original(*args, **kwargs)
            finally:
                seconds = time.perf_counter() - started
                stack.pop()
                if stack:
                    stack[-1]['children'] += seconds
                item = rows.setdefault(name, {'calls': 0, 'inclusive_seconds': 0.0, 'exclusive_seconds': 0.0})
                item['calls'] += 1
                item['inclusive_seconds'] += seconds
                item['exclusive_seconds'] += seconds - frame['children']
        return call
    originals = {}
    for name in ('selection', '_inputs', '_verify_profile', '_verify_used_raw', 'verify_historical_inputs',
                 'prepare_tables', '_write_shards', 'verify_inputs', 'verify_bytes', 'verify_partition', '_record'):
        if hasattr(module, name):
            originals[name] = getattr(module, name)
            setattr(module, name, wrap(name, originals[name]))
    selected = source['selection']
    started = time.perf_counter()
    try:
        result = module.prepare(h1_dir=source['h1_dir'], h1_manifest_sha256=source['h1_manifest_sha256'],
            profile_manifest=source['profile_manifest'], profile_manifest_sha256=source['profile_manifest_sha256'],
            selection_csv=selected['path'], selection_sha256=selected['sha256'], sample_names=selected['chosen_names'],
            partition_count=source['partition_count'], output=output)
    finally:
        for name, original in originals.items():
            setattr(module, name, original)
    return {'seconds': time.perf_counter() - started, 'result': result, 'profile': rows,
            'generation_contract': module.contract(), 'module_path': str(Path(module.__file__).resolve()),
            'profile_semantics': 'exclusive_seconds exclude time in other wrapped functions; inclusive values overlap'}


def measure(prepared, output, layout):
    from pipeline.preprocessing.version_dependents import historical_parallel as runner
    from pipeline.preprocessing.requirements_resolution.input import file_sha256
    from pipeline.preprocessing.experiments.dependents.historical_production_backend_benchmark import run_metrics
    options = {} if layout == 'archived' else {'history_layout': layout}
    start = time.perf_counter()
    result = runner.run(prepared_dir=prepared, manifest_sha256=file_sha256(Path(prepared) / 'input_manifest.json'),
                        output=output, workers=4, **options)
    computed = time.perf_counter()
    verified = runner.verify_run(run_dir=output, manifest_sha256=result['run_manifest_sha256'])
    end = time.perf_counter()
    return dict(result=result, verification=verified, run_seconds=computed-start, verify_seconds=end-computed,
                preprocessing_seconds=end-start, phases=run_metrics(output), module_path=runner.__file__)


def supervise(root, archive, old_input, new_input, repeats):
    from pipeline.preprocessing.experiments.dependents.historical_parallel_benchmark import compare_runs
    from pipeline.preprocessing.experiments.dependents.historical_throughput_benchmark import _resources, _disk
    root, archive = Path(root).resolve(), Path(archive).resolve()
    root.mkdir(parents=True, exist_ok=False)
    repo = REPO_ROOT
    records = []
    for repeat in range(1, repeats + 1):
        order = ('old', 'new') if repeat % 2 else ('new', 'old')
        for kind in order:
            label = f'{kind}-{repeat}'
            output, report = root / label, root / (label + '.json')
            source = archive if kind == 'old' else repo
            env = dict(os.environ, PYTHONPATH=str(source) + os.pathsep + str(repo / '.venv-bq/Lib/site-packages'))
            command = [sys.executable, str(Path(__file__).resolve()), '--mode', 'measure', '--prepared',
                       str(old_input if kind == 'old' else new_input), '--output', str(output), '--report', str(report),
                       '--layout', 'archived' if kind == 'old' else 'grouped']
            peak_rss = peak_scratch = 0
            with (root / (label + '.log')).open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    while process.poll() is None:
                        resource, disk = _resources(process.pid), _disk(output)
                        peak_rss = max(peak_rss, resource['tree_rss_bytes'])
                        peak_scratch = max(peak_scratch, disk['scratch_bytes'])
                        (root / 'progress.json').write_text(json.dumps(dict(trial=label, pid=process.pid, status='RUNNING')))
                        time.sleep(1)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=15)
                if process.returncode:
                    raise RuntimeError('Trial failed: ' + str(root / (label + '.log')))
            record = json.loads(report.read_bytes())
            record.update(kind=kind, repeat=repeat, peak_tree_rss_bytes=peak_rss, peak_run_scratch_bytes=peak_scratch)
            records.append(record)
        comparison = compare_runs(root / f'old-{repeat}', root / f'new-{repeat}')
        records[-1]['comparison'] = comparison
        (root / 'measurements.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    return dict(status='PASS', measurements=records, repeats=repeats, workers=4,
                resource_sampling='1 second; scratch inside trial directory only; disk IO bytes not measured',
                scope='32 targets, 229 dates; preparation measured separately once per implementation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('prepare', 'measure', 'supervise'), default='prepare')
    parser.add_argument('--source-plan')
    parser.add_argument('--prepared')
    parser.add_argument('--layout', choices=('archived', 'daily', 'grouped'), default='grouped')
    parser.add_argument('--archive')
    parser.add_argument('--old-input')
    parser.add_argument('--new-input')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        result = profile_prepare(args.source_plan, args.output)
    elif args.mode == 'measure':
        result = measure(args.prepared, args.output, args.layout)
    else:
        existed = Path(args.output).exists()
        try:
            result = supervise(args.output, args.archive, args.old_input, args.new_input, args.repeats)
        except Exception as error:
            root = Path(args.output)
            if not existed and root.is_dir():
                (root / 'progress.json').write_text(json.dumps(dict(status='FAILED', error=str(error))), encoding='utf-8')
            raise
    Path(args.report).write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
    if args.mode == 'supervise':
        (Path(args.output) / 'progress.json').write_text(json.dumps(dict(status='COMPLETE', trials=len(result['measurements']))), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
