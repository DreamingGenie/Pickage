"""Opt-in, process-local action instrumentation; never changes Spark's plan."""
from contextlib import contextmanager
import inspect
import json
import linecache
from pathlib import Path
import time
from unittest.mock import patch


def repository_callsite():
    """Keep source lines as evidence; do not pretend lazy expressions ran here."""
    frames = []
    frame = inspect.currentframe()
    try:
        frame = frame.f_back
        while frame:
            if frame.f_globals.get('__name__') in ('pipeline.preprocessing.repository_metrics.transform',
                                                   'pipeline.preprocessing.experiments.spark.repository'):
                frames.append({'function': frame.f_code.co_name, 'line': frame.f_lineno,
                               'source': linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip(),
                               'dataset': frame.f_locals.get('name') if frame.f_code.co_name in ('_read', '_write') else None})
            frame = frame.f_back
    finally:
        del frame
    return frames


class Recorder:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None
        self.sequence = 0

    def emit(self, row):
        self.stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.stream.flush()

    @contextmanager
    def action(self, label, context=None, callsite=None):
        self.sequence += 1
        group = f'repository-profile:{self.sequence:04d}:{label}'
        keys = ('spark.jobGroup.id', 'spark.job.description', 'spark.job.interruptOnCancel')
        old = {k: context.getLocalProperty(k) for k in keys} if context else {}
        if context:
            context.setJobGroup(group, label)
        started = time.perf_counter()
        row = {'group_id': group, 'label': label, 'callsite': callsite or [], 'time': time.time()}
        self.emit(dict(row, event='START'))
        status = 'COMPLETE'
        try:
            yield
        except BaseException:
            status = 'FAILED'
            raise
        finally:
            elapsed = time.perf_counter() - started
            if context:
                for key, value in old.items():
                    context.setLocalProperty(key, value)
            self.emit(dict(row, event='END', status=status, seconds=elapsed))
            print('REPOSITORY_PROFILE', group, status, round(elapsed, 6), flush=True)

    def wrap_action(self, original, action):
        def wrapped(obj, *args, **kwargs):
            site = repository_callsite()
            if not site:
                return original(obj, *args, **kwargs)
            nearest = site[0]
            label = f"{nearest['function']}:{nearest['dataset'] or nearest['line']}:{action}"
            spark = obj._spark if action == 'parquet' else obj.sparkSession
            with self.action(label, spark.sparkContext, site):
                return original(obj, *args, **kwargs)
        return wrapped

    @contextmanager
    def install(self):
        from pyspark.sql import DataFrame
        from pyspark.sql.readwriter import DataFrameWriter
        from pipeline.preprocessing.repository_metrics import runtime
        original_create = runtime.create_spark

        def create(*args, **kwargs):
            with self.action('spark.startup'):
                spark = original_create(*args, **kwargs)
            original_stop = spark.stop

            def stop():
                with self.action('spark.shutdown'):
                    return original_stop()
            spark.stop = stop
            return spark

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('x', encoding='utf-8') as self.stream:
            with patch.object(DataFrame, 'count', self.wrap_action(DataFrame.count, 'count')), \
                 patch.object(DataFrame, 'collect', self.wrap_action(DataFrame.collect, 'collect')), \
                 patch.object(DataFrameWriter, 'parquet', self.wrap_action(DataFrameWriter.parquet, 'parquet')), \
                 patch.object(runtime, 'create_spark', create):
                yield self


def summarize_actions(path):
    starts, ends = {}, {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        (starts if row['event'] == 'START' else ends)[row['group_id']] = row
    return {'actions': sorted(ends.values(), key=lambda x: x['seconds'], reverse=True),
            'unfinished_actions': [v for k, v in starts.items() if k not in ends],
            'interpretation': 'Wall time of existing actions, including upstream lazy evaluation; not isolated operator timings. Startup/shutdown are separate. No extra materialization.'}
