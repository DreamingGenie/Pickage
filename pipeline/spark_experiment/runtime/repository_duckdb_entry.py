"""Local-file repository engine trials, with pinned inputs and exact comparison."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify_manifest(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Frozen manifest SHA mismatch')
    manifest = json.loads(raw)
    if manifest.get('sample', {}).get('package_rows') != 1000 or manifest['stages']['repository']['counts']['package'] != 1000:
        raise ValueError('Expected frozen 1000-package input')
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
    watch_control(args.control)
    manifest = verify_manifest(args.manifest, args.manifest_sha256)
    args.output.mkdir(parents=True, exist_ok=False)
    from ..job import code_sha
    from ..telemetry import Sampler
    code = code_sha()
    report = {'status': 'RUNNING', 'engine': args.engine, 'input_identity': manifest['input_identity'],
              'manifest_sha256': args.manifest_sha256, 'code_sha256': code,
              'output': str(args.output / 'output'), 'threads': 2,
              'memory_setting': '4g JVM heap' if args.engine == 'spark' else '4GB DuckDB memory_limit',
              'db_loaded': False, 'production_publication': False}
    save(args.output / 'report.json', report)
    sampler = Sampler(interval=0.25).start()
    started = time.perf_counter()
    try:
        if args.engine == 'spark':
            from pipeline.repository_metrics.runtime import create_spark
            from pipeline.repository_metrics.transform import transform
            os.environ['PYSPARK_SUBMIT_ARGS'] = '--driver-memory 4g pyspark-shell'
            spark = create_spark(args.output / 'runtime', threads=2, driver_memory='4g', shuffle_partitions=16)
            report['spark_version'] = spark.version
            try:
                transform_start = time.perf_counter()
                result = transform(spark, manifest['stages']['repository'], args.output / 'output')
                report['transform_seconds'] = time.perf_counter() - transform_start
            finally:
                spark.stop()
        else:
            import duckdb
            from ..repository_duckdb import transform
            with duckdb.connect(config={'threads': 2, 'memory_limit': '4GB'}) as con:
                con.execute('SET temp_directory=?', [str(args.output / 'scratch')])
                transform_start = time.perf_counter()
                result = transform(con, manifest['stages']['repository'], args.output / 'output')
                report['transform_seconds'] = time.perf_counter() - transform_start
            report['duckdb_version'] = duckdb.__version__
        report.update(seconds=time.perf_counter() - started, result=result)
        verify_manifest(args.manifest, args.manifest_sha256)
        if code_sha() != code:
            raise ValueError('Code changed during trial')
        report['status'] = 'COMPUTED'
    except BaseException as error:
        report.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        save(args.output / 'telemetry.json', sampler.stop())
        save(args.output / 'report.json', report)
    return report


def compare(trials, output):
    import duckdb
    from .bounded_compare import _compare_group
    from ..job import GROUPS
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
            groups = {}
            for group in GROUPS['repository']:
                left = sorted(str(p) for p in (Path(oracle['output']) / group).rglob('*.parquet'))
                right = sorted(str(p) for p in (Path(row['output']) / group).rglob('*.parquet'))
                groups[group] = _compare_group(con, left, right, set())
            comparisons.append({'engine': row['engine'], 'output': row['output'], 'groups': groups,
                                'report_equal': row['result'] == oracle['result']})
    equal = all(c['report_equal'] and all(g['equal'] and g['logical_schema_equal'] for g in c['groups'].values()) for c in comparisons)
    result = {'status': 'VERIFIED' if equal else 'DIFFERENT', 'comparison': 'EXACT_CANONICAL_ROW_MULTISET',
              'trials': reports, 'comparisons': comparisons,
              'limits': ['local files; OS cache not flushed', 'heap and DuckDB limits have different meanings',
                         'memory peak covers cgroup lifetime; use fresh containers'],
              'db_loaded': False, 'production_publication': False}
    save(output, result)
    if not equal:
        raise ValueError('Repository outputs or reports differ')
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
