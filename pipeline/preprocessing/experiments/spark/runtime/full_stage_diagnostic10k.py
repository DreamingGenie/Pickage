"""Separate diagnostic trial; cProfile timings are not ABBA benchmark timings."""
import cProfile
import json
from pathlib import Path
import pstats
import sys
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime.repository_duckdb10k_entry import save

RUN = 'full-stage-diagnostic10000-20260917-a2'
REFERENCE = 'repository-duckdb10000-20260917-a1'


def profiled_call(function, output, *args, **kwargs):
    profiler = cProfile.Profile()
    try:
        return profiler.runcall(function, *args, **kwargs)
    finally:
        profiler.dump_stats(str(output) + '.pstats')
        rows = []
        for (file, line, name), (primitive, calls, own, cumulative, callers) in pstats.Stats(profiler).stats.items():
            rows.append(dict(file=file, line=line, function=name, calls=calls,
                             primitive_calls=primitive, self_seconds=own, cumulative_seconds=cumulative))
        save(str(output) + '.json', {'scope': 'Python parent thread; subprocess work appears as wait',
             'warning': 'Cumulative times overlap; do not sum nested functions. Profiling adds overhead.',
             'functions': sorted(rows, key=lambda r: r['cumulative_seconds'], reverse=True)})


def compare(trials, output):
    import duckdb
    from pipeline.preprocessing.experiments.spark.job import GROUPS
    from pipeline.preprocessing.experiments.spark.compare import files_for
    from pipeline.preprocessing.experiments.spark.runtime.bounded_compare import _compare_group
    if len(trials) != 1:
        raise ValueError('Exactly one diagnostic trial required')
    current = json.loads((trials[0] / 'report.json').read_bytes())
    reference = json.loads((Path('/reference') / 'output/spark-1/report.json').read_bytes())
    completed = json.loads((Path('/reference') / 'result.json').read_bytes())
    trial_names = ('spark-1', 'duckdb-1', 'duckdb-2', 'spark-2')
    if current['status'] != 'COMPUTED' or any(
            completed['phases'][name]['state']['ExitCode'] != 0 or
            completed['phases'][name]['state']['OOMKilled'] for name in trial_names):
        raise ValueError('Reference or diagnostic trial incomplete')
    for key in ('input_identity', 'manifest_sha256'):
        if current[key] != reference[key]:
            raise ValueError('Diagnostic input mismatch')
    # A separate code hash is intentional: diagnostic wrapper is added after ABBA.
    groups = {}
    references = [json.loads((Path('/reference/output') / name / 'report.json').read_bytes()) for name in trial_names]
    if any(r['status'] != 'COMPUTED' or r['input_identity'] != reference['input_identity'] or
           r['manifest_sha256'] != reference['manifest_sha256'] or r['code_sha256'] != reference['code_sha256'] for r in references):
        raise ValueError('ABBA reference identity or completion mismatch')
    with duckdb.connect(config={'threads': 2, 'memory_limit': '4GB'}) as con:
        con.execute("SET TimeZone='UTC'")
        con.execute('SET temp_directory=?', [str(output.parent / 'compare-scratch')])
        for label, report in [*zip(trial_names, references), ('diagnostic', current)]:
            groups[label] = {}
            for stage, names in GROUPS.items():
                groups[label][stage] = {}
                original = Path(reference['stages'][stage]['output'])
                left_root = Path('/reference/output') / original.relative_to('/experiment/' + REFERENCE)
                right_root = Path(report['stages'][stage]['output'])
                if label != 'diagnostic':
                    right_root = Path('/reference/output') / right_root.relative_to('/experiment/' + REFERENCE)
                for name in names:
                    left = files_for(str(left_root), 'baseline', stage, name)
                    right = files_for(str(right_root), 'baseline', stage, name)
                    value = _compare_group(con, left, right, set())
                    # All version outputs use the same baseline transform. Exact
                    # JSON-string equality is stronger than normalized equality.
                    if not value['equal'] and stage == 'package_version' and name == 'version/data':
                        value = _compare_group(con, left, right, {'licenses', 'dependency'})
                    groups[label][stage][name] = value
                    print('EXACT_GROUP', label, stage, name, value['equal'], flush=True)
    equal = all(g['equal'] and g['logical_schema_equal'] for t in groups.values() for s in t.values() for g in s.values())
    save(output, {'status': 'VERIFIED' if equal else 'DIFFERENT', 'groups': groups,
                 'reference_code_sha256': reference['code_sha256'],
                 'diagnostic_code_sha256': current['code_sha256'], 'trial': current})
    if not equal:
        raise ValueError('Diagnostic output changed')


def main():
    if '--host' in sys.argv:
        from pipeline.preprocessing.experiments.spark.runtime import repository_duckdb10k_host as host
        host.RUN = RUN
        host.ROOT = host.ROOT.parent / RUN
        host.DEST = '/experiment/' + RUN
        host.TRIALS = ('duckdb-1',)
        host.ENTRY_MODULE = __spec__.name
        original = host.WeeklyPrioritySupervisor.phase
        def phase(self, name, entry, extra=()):
            return original(self, name, entry, [*extra, '--mount',
                f'type=bind,source={host.ROOT.parent / REFERENCE},target=/reference,readonly'])
        with patch.object(host.WeeklyPrioritySupervisor, 'phase', phase):
            if '--check' in sys.argv:
                print(json.dumps(host.preflight())); return 0
            return host.run()
    from pipeline.preprocessing.experiments.spark import job
    from pipeline.preprocessing.experiments.spark.runtime import repository_duckdb10k_entry as entry
    original = job.baseline
    def baseline(name, inputs, output, threads, memory):
        return profiled_call(original, Path(output).parent / (name + '-python-profile'),
                             name, inputs, output, threads, memory)
    with patch.object(job, 'baseline', baseline), patch.object(entry, 'compare', compare):
        return entry.main()


if __name__ == '__main__':
    raise SystemExit(main())
