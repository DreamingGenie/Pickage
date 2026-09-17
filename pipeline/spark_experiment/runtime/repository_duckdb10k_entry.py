"""Isolated 10,000-package full-pipeline trial with phase diagnostics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import traceback
import sys


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify_manifest(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Frozen manifest SHA mismatch')
    manifest = json.loads(raw)
    if manifest.get('sample', {}).get('package_rows') != 10000 or manifest['stages']['repository']['counts']['package'] != 10000:
        raise ValueError('Expected frozen 10000-package input')
    if not manifest.get('input_identity') or not manifest.get('input_files'):
        raise ValueError('Missing input identity or inventory')
    inventory = set()
    for row in manifest['input_files']:
        source = Path(row['path']).resolve()
        if not source.is_relative_to(Path(path).resolve().parent):
            raise ValueError('Input outside frozen manifest directory')
        digest = hashlib.sha256()
        with source.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if source.stat().st_size != row['bytes'] or digest.hexdigest() != row['sha256']:
            raise ValueError('Frozen input changed: ' + str(source))
        inventory.add(str(source))
    for paths in manifest['stages']['repository']['files'].values():
        for source in paths:
            if str(Path(source).resolve()) not in inventory:
                raise ValueError('Repository input not covered by hash inventory')
    return manifest


def watch_control(control):
    if control is None:
        return
    from .repository_retry_entry import wait_for_start, fresh_control
    wait_for_start(control)
    def watch():
        while True:
            try:
                if not fresh_control(control):
                    os._exit(70)
            except Exception:
                os._exit(70)
            time.sleep(3)
    threading.Thread(target=watch, daemon=True).start()


def run(args):
    from contextlib import contextmanager
    from unittest.mock import patch
    from ..job import STAGES, baseline, code_sha
    from ..telemetry import Sampler, read_snapshot, snapshot_delta
    from .repository_profile import Recorder, summarize_actions
    from .repository_profile_summary import write_summary
    watch_control(args.control)
    verified_at = time.perf_counter()
    manifest = verify_manifest(args.manifest, args.manifest_sha256)
    verified_seconds = time.perf_counter() - verified_at
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'RUNNING', 'engine': args.engine, 'sample_packages': 10000,
              'input_identity': manifest['input_identity'], 'manifest_sha256': args.manifest_sha256,
              'code_sha256': code_sha(), 'stages': {}, 'input_verification_seconds': verified_seconds,
              'scope': 'FIXED_STAGE_INPUTS_ALL_STAGES_REPOSITORY_ENGINE_VARIANT',
              'threads': 2, 'db_loaded': False, 'production_publication': False}
    sampler = Sampler(interval=0.25).start()
    action_counters = []
    class MeasuredRecorder(Recorder):
        @contextmanager
        def action(self, label, context=None, callsite=None):
            before = read_snapshot()
            try:
                with super().action(label, context, callsite):
                    group = self.sequence
                    yield
            finally:
                action_counters.append({'sequence': self.sequence, 'label': label,
                                        'counters': snapshot_delta(before, read_snapshot())})
    started = time.perf_counter()
    try:
        for name in STAGES:
            output = args.output / name
            before = read_snapshot()
            stage_start = time.perf_counter()
            phase = {'status': 'RUNNING', 'started_at': time.time(), 'output': str(output)}
            report['stages'][name] = phase
            save(args.output / 'report.json', report)
            print('EXPERIMENT_STAGE_START', name, flush=True)
            if name != 'repository':
                value = baseline(name, manifest['stages'][name], str(output), 2, '4GB')
            elif args.engine == 'spark':
                events = args.output / 'events'
                events.mkdir()
                actions = args.output / 'repository-actions.jsonl'
                old = os.environ.get('PYSPARK_SUBMIT_ARGS')
                os.environ['PYSPARK_SUBMIT_ARGS'] = ('--driver-memory 4g --conf spark.eventLog.enabled=true '
                    '--conf spark.eventLog.compress=false --conf spark.eventLog.rolling.enabled=false '
                    '--conf spark.eventLog.dir=' + events.resolve().as_uri() + ' pyspark-shell')
                try:
                    with MeasuredRecorder(actions).install():
                        from pipeline.repository_metrics import runtime
                        from pipeline.repository_metrics.transform import transform
                        spark = runtime.create_spark(args.output / 'repository-runtime', threads=2,
                                                     driver_memory='4g', shuffle_partitions=16)
                        report['spark_version'] = spark.version
                        try:
                            transform_start = time.perf_counter()
                            value = transform(spark, manifest['stages'][name], output)
                            phase['transform_seconds'] = time.perf_counter() - transform_start
                        finally:
                            spark.stop()
                finally:
                    if old is None: os.environ.pop('PYSPARK_SUBMIT_ARGS', None)
                    else: os.environ['PYSPARK_SUBMIT_ARGS'] = old
                    save(args.output / 'spark-action-counters.json', action_counters)
                    if actions.exists():
                        save(args.output / 'spark-actions-summary.json', summarize_actions(actions))
                phase['engine_seconds'] = time.perf_counter() - stage_start
                event_summary = write_summary(events, args.output / 'spark-events-summary.json')
                if event_summary['incomplete_log']:
                    raise ValueError('Incomplete Spark event log')
                action_summary = summarize_actions(actions)
                if action_summary['unfinished_actions'] or any(x['status'] != 'COMPLETE' for x in action_summary['actions']):
                    raise ValueError('Incomplete Spark action diagnostics')
                phase['action_seconds'] = sum(x['seconds'] for x in action_summary['actions'])
                phase['unattributed_seconds'] = max(0, phase['engine_seconds'] - phase['action_seconds'])
            else:
                import duckdb
                from .. import repository_duckdb
                from .repository_duckdb_profile import DuckDBProfiler
                normalize_stats = {'calls': 0, 'seconds': 0.0}
                original = repository_duckdb.normalize_repository_url
                def normalize(url):
                    tick = time.perf_counter()
                    try: return original(url)
                    finally:
                        normalize_stats['calls'] += 1
                        normalize_stats['seconds'] += time.perf_counter() - tick
                with duckdb.connect(config={'threads': 2, 'memory_limit': '4GB'}) as raw_con:
                    raw_con.execute('SET temp_directory=?', [str(args.output / 'repository-scratch')])
                    with DuckDBProfiler(args.output / 'repository-duckdb.jsonl') as profiler, \
                         patch.object(repository_duckdb, 'normalize_repository_url', normalize):
                        tick = time.perf_counter()
                        value = repository_duckdb.transform(profiler.connection(raw_con), manifest['stages'][name], output)
                        phase['transform_seconds'] = time.perf_counter() - tick
                report['duckdb_version'] = duckdb.__version__
                phase['engine_seconds'] = time.perf_counter() - stage_start
                phase['python_url_normalization'] = normalize_stats
                phase['query_seconds'] = sum(e['wall_seconds'] for e in profiler.events)
                phase['unattributed_seconds'] = max(0, phase['transform_seconds'] - phase['query_seconds'] - normalize_stats['seconds'])
            phase.update(status='COMPLETE', seconds=time.perf_counter() - stage_start,
                         finished_at=time.time(), result=value,
                         container_counters=snapshot_delta(before, read_snapshot()))
            phase['sampled_memory_current_max_bytes'] = max(
                (s['memory']['current'] or 0 for s in sampler.samples
                 if phase['started_at'] <= s['timestamp'] <= phase['finished_at']), default=None)
            save(args.output / 'report.json', report)
            print('EXPERIMENT_STAGE_COMPLETE', name, phase['seconds'], flush=True)
        report['seconds'] = time.perf_counter() - started
        verify_manifest(args.manifest, args.manifest_sha256)
        if code_sha() != report['code_sha256']:
            raise ValueError('Code changed during trial')
        report['status'] = 'COMPUTED'
    except BaseException as error:
        report.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error),
                                            'traceback': traceback.format_exc()})
        raise
    finally:
        save(args.output / 'telemetry.json', sampler.stop())
        save(args.output / 'report.json', report)
    return report


def compare(trials, output):
    import duckdb
    from .bounded_compare import _compare_group
    from ..job import GROUPS
    from ..compare import files_for
    reports = [json.loads((path / 'report.json').read_text(encoding='utf-8')) for path in trials]
    if len(reports) < 2 or {r['engine'] for r in reports} != {'spark', 'duckdb'}:
        raise ValueError('Both engines required')
    for key in ('input_identity', 'manifest_sha256', 'code_sha256'):
        if len({r[key] for r in reports}) != 1:
            raise ValueError('Comparison mismatch: ' + key)
    if any(r['status'] != 'COMPUTED' for r in reports):
        raise ValueError('Incomplete trial')
    if output.exists():
        raise FileExistsError(output)
    oracle = next(r for r in reports if r['engine'] == 'spark')
    comparisons = []
    with duckdb.connect(config={'threads': 2, 'memory_limit': '4GB'}) as con:
        con.execute("SET TimeZone='UTC'")
        con.execute('SET temp_directory=?', [str(output.parent / 'compare-scratch')])
        for row in reports:
            stages = {}
            for stage in GROUPS:
                stage_groups = {}
                for group in GROUPS[stage]:
                    left = files_for(oracle['stages'][stage]['output'], 'baseline', stage, group)
                    right = files_for(row['stages'][stage]['output'], 'baseline', stage, group)
                    value = _compare_group(con, left, right, set())
                    if not value['equal'] and stage == 'package_version' and group == 'version/data':
                        value = _compare_group(con, left, right, {'licenses', 'dependency'})
                    stage_groups[group] = value
                    print('EXACT_GROUP', row['engine'], stage, group, value['equal'], flush=True)
                stages[stage] = stage_groups
            comparisons.append({'engine': row['engine'], 'stages': stages})
    equal = all(all(g['equal'] and g['logical_schema_equal']
                    for groups in c['stages'].values() for g in groups.values()) for c in comparisons)
    result = {'status': 'VERIFIED' if equal else 'DIFFERENT', 'comparison': 'EXACT_CANONICAL_ROW_MULTISET',
              'trials': reports, 'comparisons': comparisons,
              'limits': ['local files; OS cache not flushed', 'heap and DuckDB limits have different meanings',
                         'memory peak covers cgroup lifetime; use fresh containers',
                         'non-repository stages are held constant; only repository engine varies'],
              'db_loaded': False, 'production_publication': False}
    save(output, result)
    if not equal:
        raise ValueError('Pipeline outputs differ')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    rp = sub.add_parser('run')
    rp.add_argument('--engine', choices=('spark', 'duckdb'), required=True)
    rp.add_argument('--manifest', type=Path, required=True)
    rp.add_argument('--manifest-sha256', required=True)
    rp.add_argument('--output', type=Path, required=True)
    rp.add_argument('--control', type=Path)
    cp = sub.add_parser('compare')
    cp.add_argument('--trials', nargs='+', type=Path, required=True)
    cp.add_argument('--output', type=Path, required=True)
    cp.add_argument('--control', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'run':
        run(args)
    else:
        watch_control(args.control)
        compare(args.trials, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
