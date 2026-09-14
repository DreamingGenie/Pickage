"""Compare all lookups of an explicit prepared sample, never production counts."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import uuid

from pipeline.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes, sha256
from .historical import WORKER, _check_lookup
from .historical_artifact import _path, _publish_json
from .historical_gpu import NORMALIZER, cpu_ranks, gpu_ranks, intervals_from_ranks
from .historical_gpu_suite_input import load_suite


def messages(package, snapshot_count, batch_size):
    """Preserve every lookup in id order; never mix package candidates."""
    if type(batch_size) is not int or not 1 <= batch_size <= 1024:
        raise ValueError('lookup_batch must be 1..1024')
    for offset in range(0, len(package['lookups']), batch_size):
        items = package['lookups'][offset:offset + batch_size]
        yield items, {'op': 'package', 'name': package['name'],
                      'known_package': package['known_package'], 'snapshot_count': snapshot_count,
                      'candidates': package['candidates'], 'requirements': [r for _, r in items]}


def result_hash(package, items, actual, snapshot_count):
    """Check every field, including the original target package identity."""
    if len(actual) != len(items):
        raise ValueError('Result lookup cardinality differs')
    canonical = []
    for (lookup_id, requirement), result in zip(items, actual):
        if result['requirement'] != requirement:
            raise ValueError('Result requirement identity differs')
        _check_lookup(result['intervals'], snapshot_count)
        mapped = [{**row, 'target_package_id': package['package_id']
                   if row['status'] == 'RESOLVED' else None} for row in result['intervals']]
        if mapped != package['oracle'][lookup_id]:
            raise ValueError(f'Oracle mismatch in {package["name"]}, lookup {lookup_id}')
        canonical.append({'lookup_id': lookup_id, 'requirement': requirement, 'intervals': mapped})
    return sha256(canonical)


def plan_hash(plan):
    return sha256({k: v for k, v in plan.items() if k != 'metrics'})


def checked_plan(node, payload, runtime, verify_spans=False):
    plan = node.request({**payload, 'verify_spans': verify_spans})
    if plan['accepted'] != payload['candidates'] or plan['rejected']:
        raise ValueError('Normalizer candidate population differs from prepared input')
    if [item['requirement'] for item in plan['lookups']] != payload['requirements']:
        raise ValueError('Normalizer omitted or reordered requirements')
    if (plan['runtime']['node'] != runtime['node_version'] or
            plan['runtime']['semver'] != runtime['semver_version'] or
            plan['runtime']['package_arg'] != runtime['package_arg_version'] or
            plan['runtime']['options'] != runtime['options'] or
            plan['runtime']['tie'] != runtime['equal_precedence_tie']):
        raise ValueError('Normalizer runtime differs from stored oracle')
    return plan


def _numeric_summary(values):
    return {'median_seconds': statistics.median(values), 'min_seconds': min(values),
            'max_seconds': max(values), 'repetitions': len(values)}


def summarize_rounds(rounds):
    """Sum each complete round first; do not average per-package speedups."""
    result = {'repetitions': len(rounds)}
    for route in ('cpu', 'gpu'):
        result[route] = {key: _numeric_summary([r[route][key] for r in rounds]) for key in
                         ('numeric_seconds', 'normalization_plus_numeric_seconds', 'path_seconds')}
    result['cpu_over_gpu_speedup'] = {}
    for key in ('numeric_seconds', 'normalization_plus_numeric_seconds', 'path_seconds'):
        numerator = result['cpu'][key]['median_seconds']
        denominator = result['gpu'][key]['median_seconds']
        result['cpu_over_gpu_speedup'][key] = numerator / denominator if denominator else None
    return result


def _route(values, normalizing):
    return {**values, 'normalization_plus_numeric_seconds': normalizing + values['numeric_seconds'],
            'path_seconds': normalizing + values['numeric_seconds'] + values['interval_seconds']}


def sum_routes(rows, kind):
    keys = set().union(*(row[kind].keys() for row in rows))
    return {key: sum(row[kind].get(key, 0.0) for row in rows) for key in sorted(keys)}


def run_suite(*, prepared_dir, oracle_run_dir, oracle_manifest_sha256, output,
              repetitions=5, lookup_batch=1024, workspace_mib=128):
    if type(repetitions) is not int or not 3 <= repetitions <= 7:
        raise ValueError('repetitions must be 3..7')
    if type(lookup_batch) is not int or not 1 <= lookup_batch <= 1024:
        raise ValueError('lookup_batch must be 1..1024')
    if type(workspace_mib) is not int or not 1 <= workspace_mib <= 512:
        raise ValueError('workspace_mib must be 1..512')
    output = _path(output)
    if output.exists() or any(output.is_relative_to(_path(p)) or _path(p).is_relative_to(output)
                              for p in (prepared_dir, oracle_run_dir)):
        raise ValueError('Use a new output directory separate from inputs and oracle')
    output.mkdir(parents=True, exist_ok=False)
    total_start = time.perf_counter()

    def status(phase, **values):
        # Progress is mutable; completed reports remain write-once artifacts.
        temporary = output / f'.status-{uuid.uuid4().hex}.tmp'
        temporary.write_bytes(canonical_bytes({'status': phase, 'at_unix': time.time(), **values}))
        os.replace(temporary, output / 'status.json')

    try:
        status('PREPARING_INPUTS')
        tick = time.perf_counter()
        suite = load_suite(prepared_dir=prepared_dir, oracle_run_dir=oracle_run_dir,
                           oracle_manifest_sha256=oracle_manifest_sha256)
        input_seconds = time.perf_counter() - tick
        packages, n = suite['packages'], len(suite['calendar'])
        protected = dict(suite['provenance']['protected_files_sha256'])
        code_paths = [Path(__file__), NORMALIZER, WORKER,
                      Path(__file__).with_name('historical_gpu.py'),
                      Path(__file__).with_name('historical_gpu_suite_input.py')]
        code_hashes = {str(p.resolve()): file_sha256(p) for p in code_paths}
        tick = time.perf_counter()
        import numpy as np
        import torch
        import_seconds = time.perf_counter() - tick
        tick = time.perf_counter()
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA required; GPU experiment has no CPU fallback')
        torch.cuda.synchronize()
        gpu_properties = torch.cuda.get_device_properties(0)
        cuda_init_seconds = time.perf_counter() - tick
        runtime = discover_runtime()
        tick = time.perf_counter()
        with NodeSession(runtime, output / 'oracle-runtime.log', worker=WORKER) as original:
            runtime_metadata = original.request({'op': 'metadata'})
        if runtime_metadata != suite['provenance']['stored_runtime']:
            raise ValueError('Current npm runtime differs from the stored production run')
        runtime_check_seconds = time.perf_counter() - tick
        report = {'format': 'historical-gpu-suite-experiment-v1', 'status': 'RUNNING',
                  'scope': 'all lookups in explicit prepared sample; resolver only',
                  'ready_for_load': False, 'production_integration': False,
                  'production_speedup_measured': False, 'full_selected_execution': False,
                  'input_rows': suite['input_rows'], 'snapshot_count': n,
                  'calendar_sha256': sha256(suite['calendar']), 'provenance': suite['provenance'],
                  'code_sha256': code_hashes, 'lookup_batch': lookup_batch,
                  'workspace_mib': workspace_mib, 'runtime': runtime_metadata,
                  'startup': {'common_input_read_and_verification_seconds': input_seconds,
                              'numpy_torch_import_seconds': import_seconds,
                              'cuda_context_initialization_seconds': cuda_init_seconds,
                              'oracle_runtime_check_seconds': runtime_check_seconds},
                  'gpu': {'name': gpu_properties.name, 'total_memory_bytes': gpu_properties.total_memory,
                          'torch': torch.__version__, 'cuda': torch.version.cuda, 'numpy': np.__version__},
                  'method': {'repetitions': repetitions, 'common_normalization': 'once per batch; identical time added to both paths',
                             'backend_order': 'alternates by round and batch',
                             'package_order': 'ascending name on even rounds, descending on odd rounds',
                             'comparison_and_hashing': 'outside backend performance timers',
                             'input_preparation': 'read existing prepared files once, not Bronze regeneration'},
                  'packages': [{'name': p['name'], 'package_id': p['package_id'],
                                'known_package': p['known_package'],
                                'candidate_count': len(p['candidates']), 'lookup_count': len(p['lookups']),
                                'q_times_v': len(p['candidates']) * len(p['lookups']),
                                'expected_declarations': p['expected_declarations']} for p in packages],
                  'preflight': [], 'rounds': []}
        tick = time.perf_counter()
        with NodeSession(runtime, output / 'normalizer.log', worker=NORMALIZER) as node:
            warmup = {'op': 'package', 'name': 'gpu-suite-warmup', 'known_package': True,
                      'snapshot_count': 1, 'candidates': [{'version': '1.0.0', 'birth_index': 0}],
                      'requirements': ['^1']}
            warm_plan = checked_plan(node, warmup, runtime_metadata)
            report['startup']['normalizer_start_and_first_request_seconds'] = time.perf_counter() - tick
            tick = time.perf_counter()
            cpu_ranks(warm_plan)
            gpu_ranks(warm_plan, workspace_mib=workspace_mib)
            report['startup']['cpu_gpu_warmup_seconds'] = time.perf_counter() - tick
            fingerprints = {}
            for index, package in enumerate(packages):
                status('PREFLIGHT', package=package['name'], package_index=index + 1,
                       packages=len(packages))
                tick = time.perf_counter()
                checks, chunks = 0, 0
                package_hash = hashlib.sha256()
                if not package['lookups']:
                    # Retain and validate zero-lookup candidate populations without timing fake work.
                    checked_plan(node, {'op': 'package', 'name': package['name'],
                                 'known_package': package['known_package'], 'snapshot_count': n,
                                 'candidates': package['candidates'], 'requirements': []}, runtime_metadata)
                for chunk_index, (items, payload) in enumerate(messages(package, n, lookup_batch)):
                    plan = checked_plan(node, payload, runtime_metadata, verify_spans=True)
                    fingerprints[(package['name'], chunk_index)] = plan_hash(plan)
                    checks += plan['metrics']['span_membership_comparisons']
                    cpu, _ = cpu_ranks(plan)
                    gpu, memory = gpu_ranks(plan, workspace_mib=workspace_mib)
                    np.testing.assert_array_equal(cpu, gpu)
                    left = result_hash(package, items, intervals_from_ranks(plan, cpu), n)
                    right = result_hash(package, items, intervals_from_ranks(plan, gpu), n)
                    if left != right or memory['peak_allocated_bytes'] >= 6 * 1024 ** 3:
                        raise ValueError('GPU equality or 6 GiB memory guard failed')
                    package_hash.update(bytes.fromhex(left))
                    chunks += 1
                report['preflight'].append({'name': package['name'], 'lookup_count': len(package['lookups']),
                    'chunk_count': chunks, 'span_membership_comparisons': checks,
                    'all_date_mismatches': 0, 'result_sha256': package_hash.hexdigest(),
                    'seconds': time.perf_counter() - tick})
            expected_hashes = {p['name']: p['result_sha256'] for p in report['preflight']}
            _publish_json(output / 'preflight.json', report)

            for round_index in range(repetitions):
                round_started = time.perf_counter()
                rows = []
                sequence = packages if round_index % 2 == 0 else list(reversed(packages))
                for package_index, package in enumerate(sequence):
                    status('MEASURING', round=round_index + 1, repetitions=repetitions,
                           package=package['name'], package_index=package_index + 1, packages=len(packages))
                    shared, verification = 0.0, 0.0
                    totals = {kind: Counter({'numeric_seconds': 0.0, 'interval_seconds': 0.0})
                              for kind in ('cpu', 'gpu')}
                    digests = {kind: hashlib.sha256() for kind in ('cpu', 'gpu')}
                    peak_allocated, peak_reserved, chunks, max_chunk = 0, 0, 0, 0
                    for chunk_index, (items, payload) in enumerate(messages(package, n, lookup_batch)):
                        tick = time.perf_counter()
                        plan = checked_plan(node, payload, runtime_metadata)
                        shared += time.perf_counter() - tick
                        tick = time.perf_counter()
                        if plan_hash(plan) != fingerprints[(package['name'], chunk_index)]:
                            raise ValueError('Repeated normalization changed')
                        verification += time.perf_counter() - tick
                        order = ('cpu', 'gpu') if (round_index + chunk_index) % 2 == 0 else ('gpu', 'cpu')
                        for kind in order:
                            values, detail = (cpu_ranks(plan) if kind == 'cpu' else
                                              gpu_ranks(plan, workspace_mib=workspace_mib))
                            totals[kind]['numeric_seconds'] += detail['seconds']
                            if kind == 'gpu':
                                for key in ('host_preparation_seconds', 'h2d_seconds', 'compute_seconds', 'd2h_seconds'):
                                    totals[kind][key] += detail[key]
                                peak_allocated = max(peak_allocated, detail['peak_allocated_bytes'])
                                peak_reserved = max(peak_reserved, detail['peak_reserved_bytes'])
                                max_chunk = max(max_chunk, detail['chunk_rows'])
                            tick = time.perf_counter()
                            restored = intervals_from_ranks(plan, values)
                            totals[kind]['interval_seconds'] += time.perf_counter() - tick
                            tick = time.perf_counter()
                            digests[kind].update(bytes.fromhex(result_hash(package, items, restored, n)))
                            verification += time.perf_counter() - tick
                        chunks += 1
                    if peak_allocated >= 6 * 1024 ** 3:
                        raise ValueError('GPU memory guard failed')
                    if any(d.hexdigest() != expected_hashes[package['name']] for d in digests.values()):
                        raise ValueError('Repeated result hash changed')
                    rows.append({'name': package['name'], 'lookup_count': len(package['lookups']),
                                 'chunk_count': chunks, 'normalization_seconds': shared,
                                 'cpu': _route(dict(totals['cpu']), shared),
                                 'gpu': _route(dict(totals['gpu']), shared),
                                 'peak_allocated_bytes': peak_allocated, 'peak_reserved_bytes': peak_reserved,
                                 'gpu_max_chunk_rows': max_chunk, 'verification_seconds': verification,
                                 'result_sha256': digests['cpu'].hexdigest(),
                                 'zero_lookup_no_computation': not package['lookups']})
                rows.sort(key=lambda p: p['name'])
                if ([r['name'] for r in rows] != [p['name'] for p in packages] or
                        sum(r['lookup_count'] for r in rows) != suite['input_rows']['lookups']):
                    raise ValueError('Round did not process all selected packages and lookups')
                routes = {kind: sum_routes(rows, kind) for kind in ('cpu', 'gpu')}
                record = {'round': round_index + 1, **routes, 'packages': rows,
                          'normalization_seconds': sum(r['normalization_seconds'] for r in rows),
                          'verification_seconds': sum(r['verification_seconds'] for r in rows),
                          'elapsed_seconds': time.perf_counter() - round_started,
                          'result_sha256': sha256([(r['name'], r['result_sha256']) for r in rows])}
                report['rounds'].append(record)
                _publish_json(output / f'round-{round_index + 1}.json', record)

        status('FINAL_VERIFICATION')
        tick = time.perf_counter()
        for path, expected in {**protected, **code_hashes}.items():
            if file_sha256(Path(path)) != expected:
                raise ValueError('Input, oracle or experiment code changed: ' + str(path))
        with NodeSession(runtime, output / 'oracle-runtime-final.log', worker=WORKER) as original:
            if original.request({'op': 'metadata'}) != runtime_metadata:
                raise ValueError('npm runtime changed during experiment')
        report['final_fingerprint_check_seconds'] = time.perf_counter() - tick
        if len({r['result_sha256'] for r in report['rounds']}) != 1:
            raise ValueError('Round result hash differs')
        report['summary'] = summarize_rounds(report['rounds'])
        report['all_date_mismatches'] = 0
        report['compared_lookup_dates'] = suite['input_rows']['lookups'] * n
        report['repeated_result_hashes_equal'] = True
        report['elapsed_seconds'] = time.perf_counter() - total_start
        report['status'] = 'COMPLETE'
        _publish_json(output / 'report.json', report)
        status('COMPLETE', report_sha256=file_sha256(output / 'report.json'),
               elapsed_seconds=report['elapsed_seconds'])
        return report
    except BaseException as error:
        status('FAILED', error_type=type(error).__name__, error=str(error)[:1000])
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir', type=Path, required=True)
    parser.add_argument('--oracle-run-dir', type=Path, required=True)
    parser.add_argument('--oracle-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--lookup-batch', type=int, default=1024)
    parser.add_argument('--workspace-mib', type=int, default=128)
    report = run_suite(**vars(parser.parse_args()))
    print(json.dumps({'status': report['status'], 'input_rows': report['input_rows'],
                      'summary': report['summary'], 'elapsed_seconds': report['elapsed_seconds']}, indent=2))


if __name__ == '__main__':
    main()
