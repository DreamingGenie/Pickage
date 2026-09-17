"""Run the unchanged 1,000-package baseline with repository-only diagnostics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from .repository_profile import Recorder, summarize_actions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--previous-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--control', type=Path)
    args = parser.parse_args(argv)
    raw = args.manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.manifest_sha256:
        raise ValueError('Pinned sample manifest changed')
    manifest = json.loads(raw)
    if manifest.get('sample', {}).get('package_rows') != 1000 or manifest['stages']['repository']['counts']['package'] != 1000:
        raise ValueError('Expected the frozen 1,000-package sample')
    args.output.mkdir(parents=True, exist_ok=False)
    if args.control:
        import threading
        import time
        from .repository_retry_entry import wait_for_start, fresh_control
        wait_for_start(args.control)
        def watch():
            while True:
                try:
                    if not fresh_control(args.control):
                        raise RuntimeError('stale supervisor')
                except Exception:
                    os._exit(70)
                time.sleep(3)
        threading.Thread(target=watch, daemon=True).start()
    from ..job import main as job
    old = os.environ.get('PYSPARK_SUBMIT_ARGS')
    os.environ['PYSPARK_SUBMIT_ARGS'] = '--driver-memory 4g pyspark-shell'
    action_file = args.output / 'repository-actions.jsonl'
    try:
        with Recorder(action_file).install():
            job(['--manifest', str(args.manifest), '--engine', 'baseline',
                        '--output', str(args.output / 'baseline'),
                        '--telemetry-dir', str(args.output / 'telemetry'),
                        '--threads', '2', '--memory', '4GB', '--partitions', '16'])
    finally:
        active_error = sys.exc_info()[1]
        if old is None:
            os.environ.pop('PYSPARK_SUBMIT_ARGS', None)
        else:
            os.environ['PYSPARK_SUBMIT_ARGS'] = old
        diagnostics_errors = []
        if action_file.exists():
            try:
                (args.output / 'repository-actions-summary.json').write_text(
                    json.dumps(summarize_actions(action_file), indent=2), encoding='utf-8')
            except Exception as error:
                diagnostics_errors.append('action summary: ' + str(error))
        events = args.output / 'telemetry/events'
        if events.exists():
            try:
                from .repository_profile_summary import write_summary
                write_summary(events, args.output / 'repository-spark-summary.json')
            except Exception as error:
                diagnostics_errors.append('event summary: ' + str(error))
        if diagnostics_errors:
            print('REPOSITORY_DIAGNOSTICS_ERRORS', json.dumps(diagnostics_errors), flush=True)
            if active_error is None:
                raise RuntimeError('Repository diagnostics incomplete: ' + '; '.join(diagnostics_errors))
    # Compare values despite intentionally different diagnostic code hashes.
    # Never rewrite old reports to satisfy the engine comparison hash gate.
    import duckdb
    from .bounded_compare import _compare_group
    from ..compare import files_for
    from ..job import GROUPS
    previous = json.loads(args.previous_report.read_bytes())
    current = json.loads((args.output / 'baseline/report.json').read_bytes())
    if previous['status'] != 'COMPUTED' or current['status'] != 'COMPUTED' or previous['input_identity'] != current['input_identity']:
        raise ValueError('Reference/current run is incomplete or has different inputs')
    groups = {}
    with duckdb.connect(config={'memory_limit': '1GB', 'threads': 2}) as con:
        con.execute('SET temp_directory=?', [str(args.output / 'compare-scratch')])
        for group in GROUPS['repository']:
            left = files_for(previous['stages']['repository']['output'], 'baseline', 'repository', group)
            right = files_for(current['stages']['repository']['output'], 'baseline', 'repository', group)
            groups[group] = _compare_group(con, left, right, set())
    result = {'status': 'EQUAL' if all(x['equal'] for x in groups.values()) else 'DIFFERENT',
              'comparison': 'EXACT_CANONICAL_ROW_MULTISET', 'groups': groups,
              'previous_code_sha256': previous['code_sha256'], 'current_code_sha256': current['code_sha256'],
              'input_identity': current['input_identity'], 'manifest_sha256': args.manifest_sha256,
              'scope': 'REPOSITORY_OUTPUTS_ONLY', 'db_loaded': False, 'production_publication': False}
    (args.output / 'repository-comparison.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if result['status'] != 'EQUAL':
        raise ValueError('Repository output differs from frozen reference')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
