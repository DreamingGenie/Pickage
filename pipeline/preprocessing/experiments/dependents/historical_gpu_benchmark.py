"""Bounded, explicit CPU/GPU resolver comparison; no full counts or DB writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time

from pipeline.preprocessing.common.paths import REPO_ROOT
from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.preprocessing.version_dependents.historical_gpu import NORMALIZER, cpu_ranks, gpu_ranks, intervals_from_ranks
from pipeline.preprocessing.version_dependents.historical_production import MeasuredNode, batches


def _code_paths() -> list[Path]:
    """Return the exact local experiment and production adapter sources."""
    production = REPO_ROOT / "pipeline" / "preprocessing" / "version_dependents"
    return [Path(__file__), NORMALIZER,
            production / "historical_gpu.py",
            production / "historical_semver_worker.cjs"]


def legacy_result(node, payload, bounds):
    started = time.perf_counter()
    lookups = []
    for items, message in batches(payload['name'], payload['candidates'],
                                  list(enumerate(payload['requirements'])),
                                  known_package=payload['known_package'],
                                  snapshot_count=payload['snapshot_count'], bounds=bounds):
        result = node.request(message)
        if result['accepted'] != payload['candidates'] or result['rejected']:
            raise ValueError('Real benchmark candidate population was not already eligible')
        if [r['requirement'] for r in result['lookups']] != [r for _, r in items]:
            raise ValueError('Oracle changed request order')
        lookups.extend(result['lookups'])
    return lookups, time.perf_counter() - started


def summarize(rows, field):
    values = sorted(row[field] for row in rows)
    return {'median_seconds': statistics.median(values), 'min_seconds': values[0],
            'max_seconds': values[-1], 'repetitions': len(values)}


def benchmark(*, candidates_parquet, lookups_parquet, snapshot_count, name, limits,
              output, repetitions=5, workspace_mib=128):
    import duckdb
    import numpy as np
    import torch

    if not limits or any(type(k) is not int or not 1 <= k <= 2048 for k in limits):
        raise ValueError('Explicit lookup limits must be between 1 and 2048')
    if not 3 <= repetitions <= 10 or not 1 <= snapshot_count <= 4096:
        raise ValueError('Invalid repetitions/calendar bound')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; experiment cannot silently fall back to CPU')
    output = Path(output).resolve()
    paths = [Path(candidates_parquet).resolve(), Path(lookups_parquet).resolve()]
    if output.exists() or any(p == output or p.is_relative_to(output) for p in paths):
        raise ValueError('Use a new output directory separate from inputs')
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    input_hashes = {str(p): file_sha256(p) for p in paths}
    with duckdb.connect(config={'threads': 4, 'memory_limit': '4GB'}) as con:
        candidate_rows = con.execute('SELECT version,birth_index FROM read_parquet(?) '
                                     'WHERE name=? ORDER BY birth_index,version',
                                     [str(paths[0]), name]).fetchall()
        requirement_rows = con.execute('SELECT DISTINCT requirement FROM read_parquet(?) '
                                       'WHERE declared_name=? ORDER BY sha256(requirement) NULLS FIRST,requirement LIMIT ?',
                                       [str(paths[1]), name, max(limits)]).fetchall()
    if not candidate_rows or len(requirement_rows) < max(limits):
        raise ValueError('Real input does not contain enough candidates or lookups')
    candidates = [{'version': v, 'birth_index': int(b)} for v, b in candidate_rows]
    requirements = [r[0] for r in requirement_rows]
    extraction_seconds = time.perf_counter() - started
    runtime = discover_runtime()
    report = {'format': 'historical-gpu-resolver-experiment-v1', 'status': 'RUNNING',
              'ready_for_load': False, 'full_selected_execution': False, 'db_load_executed': False,
              'package_name': name, 'candidate_count': len(candidates), 'snapshot_count': snapshot_count,
              'input_read_and_hash_seconds': extraction_seconds, 'input_sha256': input_hashes,
              'selection': 'DISTINCT requirement ordered by sha256 NULLS FIRST, then original; first N',
              'scope': 'resolver only; input extraction once; no count aggregation or Parquet publication',
              'code_sha256': {str(p.name): file_sha256(p)
                              for p in _code_paths()},
              'gpu': {'name': torch.cuda.get_device_name(0),
                      'total_memory_bytes': torch.cuda.get_device_properties(0).total_memory,
                      'torch': torch.__version__, 'cuda': torch.version.cuda}, 'cases': []}
    torch.cuda.synchronize()
    tick = time.perf_counter()
    warm = torch.tensor([0, 1], device='cuda', dtype=torch.int64)
    torch.cummax(warm, dim=0)
    torch.cuda.synchronize()
    report['cuda_basic_warmup_seconds'] = time.perf_counter() - tick
    del warm
    for count in limits:
        payload = {'op': 'package', 'name': name, 'known_package': True,
                   'snapshot_count': snapshot_count, 'candidates': candidates,
                   'requirements': requirements[:count]}
        output.joinpath(f'input-{count}.json').write_bytes(canonical_bytes(payload))
        case_started = time.perf_counter()
        with MeasuredNode(runtime, output / f'oracle-{count}.log', worker=NORMALIZER.with_name('historical_semver_worker.cjs')) as node:
            metadata = node.request({'op': 'metadata'})
            oracle, legacy_seconds = legacy_result(node, payload, metadata['bounds'])
            oracle_metrics = dict(node.metrics)
        legacy_cold = time.perf_counter() - case_started
        trials = []
        with NodeSession(runtime, output / f'normalize-{count}.log', worker=NORMALIZER) as node:
            tick = time.perf_counter()
            verified_plan = node.request({**payload, 'verify_spans': True})
            span_verification_wall = time.perf_counter() - tick
            if verified_plan['runtime']['semver'] != metadata['semver_version'] or \
                    verified_plan['runtime']['package_arg'] != metadata['package_arg_version'] or \
                    verified_plan['runtime']['options'] != metadata['options']:
                raise ValueError('Normalizer and oracle npm runtimes differ')
            # Record the first complete GPU path separately from warm repetitions.
            cold_gpu, cold_gpu_metrics = gpu_ranks(verified_plan, workspace_mib=workspace_mib)
            if intervals_from_ranks(verified_plan, cold_gpu) != oracle:
                raise ValueError('Cold GPU result differs from all-date npm oracle')
            for index in range(repetitions):
                tick = time.perf_counter()
                plan = node.request(payload)
                normalization_wall = time.perf_counter() - tick
                if {k: v for k, v in plan.items() if k != 'metrics'} != \
                        {k: v for k, v in verified_plan.items() if k != 'metrics'}:
                    raise ValueError('Repeated normalization changed')
                outputs, metrics = {}, {}
                # Alternate order so neither optimized path is always measured first.
                for kind in (['cpu', 'gpu'] if index % 2 == 0 else ['gpu', 'cpu']):
                    values, detail = (cpu_ranks(plan) if kind == 'cpu' else
                                      gpu_ranks(plan, workspace_mib=workspace_mib))
                    tick = time.perf_counter()
                    outputs[kind] = intervals_from_ranks(plan, values)
                    detail['interval_conversion_seconds'] = time.perf_counter() - tick
                    detail['normalization_plus_resolve_seconds'] = normalization_wall + detail['seconds']
                    detail['normalization_resolve_and_intervals_seconds'] = (
                        normalization_wall + detail['seconds'] + detail['interval_conversion_seconds'])
                    metrics[kind] = detail
                tick = time.perf_counter()
                if outputs['cpu'] != oracle or outputs['gpu'] != oracle:
                    raise ValueError('CPU/GPU intervals differ from all-date npm oracle')
                verification_wall = time.perf_counter() - tick
                if metrics['gpu']['peak_allocated_bytes'] >= 6 * 1024 ** 3:
                    raise ValueError('GPU experiment exceeded 6 GiB tensor allocation')
                trials.append({'normalization_wall_seconds': normalization_wall,
                               'normalizer_metrics': plan['metrics'],
                               'cpu': metrics['cpu'], 'gpu': metrics['gpu'],
                               'verification_seconds': verification_wall,
                               'result_sha256': sha256(outputs['gpu'])})
        case = {'lookup_count': count, 'payload_sha256': sha256(payload),
                'legacy_active_worker_seconds': legacy_seconds, 'legacy_cold_seconds': legacy_cold,
                'legacy_repetitions': 1, 'legacy_metrics': oracle_metrics, 'runtime': metadata,
                'span_verification_wall_seconds': span_verification_wall,
                'span_verification_metrics': verified_plan['metrics'],
                'cold_gpu': cold_gpu_metrics, 'trials': trials, 'all_date_mismatches': 0,
                'compared_lookup_dates': count * snapshot_count,
                'repeated_result_hashes_equal': len({t['result_sha256'] for t in trials}) == 1,
                'cpu_summary': summarize([t['cpu'] for t in trials], 'normalization_resolve_and_intervals_seconds'),
                'gpu_summary': summarize([t['gpu'] for t in trials], 'normalization_resolve_and_intervals_seconds')}
        case['optimized_cpu_over_gpu_speedup'] = (case['cpu_summary']['median_seconds'] /
                                                  case['gpu_summary']['median_seconds'])
        report['cases'].append(case)
        output.joinpath('progress.json').write_bytes(canonical_bytes(report))
    if any(file_sha256(p) != input_hashes[str(p)] for p in paths):
        raise ValueError('Input Parquet changed during experiment')
    report['elapsed_seconds'] = time.perf_counter() - started
    report['status'] = 'COMPLETE'
    output.joinpath('report.json').write_bytes(canonical_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates-parquet', type=Path, required=True)
    parser.add_argument('--lookups-parquet', type=Path, required=True)
    parser.add_argument('--snapshot-count', type=int, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--limits', type=int, nargs='+', default=[59, 256, 1024])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--workspace-mib', type=int, default=128)
    args = parser.parse_args()
    result = benchmark(**vars(args))
    print(json.dumps({'status': result['status'], 'package': result['package_name'],
                      'elapsed_seconds': result['elapsed_seconds'],
                      'cases': [{k: c[k] for k in ['lookup_count', 'legacy_active_worker_seconds',
                                  'cpu_summary', 'gpu_summary', 'optimized_cpu_over_gpu_speedup',
                                  'all_date_mismatches']} for c in result['cases']]}, indent=2))


if __name__ == '__main__':
    main()
