from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import time
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime import cluster_benchmark_entry as entry


class _Context:
    master = "spark://experiment-master:7077"

    def __init__(self):
        self.stopped = False
        self._jsc = object()
        self._jvm = types.SimpleNamespace(
            java=types.SimpleNamespace(
                lang=types.SimpleNamespace(
                    Runtime=types.SimpleNamespace(
                        getRuntime=lambda: types.SimpleNamespace(maxMemory=lambda: 1024)
                    )
                )
            )
        )

    @property
    def applicationId(self):
        if self.stopped:
            raise RuntimeError("SparkContext has been stopped")
        return "app-regression-1"

    def setLogLevel(self, _level):
        pass

    def getConf(self):
        return {"spark.driver.memory": "1g", "spark.executor.memory": "2g",
                "spark.executor.cores": "1", "spark.cores.max": "2"}

    def parallelize(self, _values, _partitions):
        return _BarrierProbe()


class _BarrierProbe:
    def barrier(self):
        return self

    def mapPartitions(self, _function):
        return self

    def collect(self):
        return [{"private_ip": ip} for ip in sorted(entry.EXPECTED_WORKERS)]


class _Spark:
    version = "3.5.3"

    def __init__(self):
        self.sparkContext = _Context()
        self.catalog = types.SimpleNamespace(clearCache=lambda: None)

    def stop(self):
        self.sparkContext.stopped = True


class _Builder:
    def __init__(self, spark):
        self.spark = spark

    def appName(self, _value):
        return self

    def master(self, _value):
        return self

    def config(self, *_args):
        return self

    def getOrCreate(self):
        return self.spark


class ClusterBenchmarkLifecycleTests(unittest.TestCase):
    def test_summary_uses_application_id_captured_before_job_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = root / "events"
            telemetry = root / "telemetry"
            summary = root / "summary.json"
            spark = _Spark()
            control = root / "control"
            control.mkdir()
            (control / "supervisor-heartbeat.json").write_text(
                json.dumps({"time": time.time()}), encoding="utf-8"
            )

            sql = types.ModuleType("pyspark.sql")
            sql.SparkSession = types.SimpleNamespace(
                builder=_Builder(spark)
            )
            pyspark = types.ModuleType("pyspark")
            pyspark.sql = sql

            def run_job(_argv):
                (events / "app.inprogress").write_text("event", encoding="utf-8")
                spark.stop()
                return 0

            parsed_event = {
                "completed": True,
                "malformed_line_count": 0,
                "executors": [{"executor_id": "1", "host": ip}
                              for ip in sorted(entry.EXPECTED_WORKERS)],
                "stages": [{"job_group_id": stage, "task_count": 1,
                             "executors": ["1", "2"]} for stage in entry.STAGES],
            }
            args = types.SimpleNamespace(
                run_id="regression",
                manifest="s3a://pickage-curated/experiments/regression/input.json",
                output="s3a://pickage-curated/experiments/regression/output",
                telemetry_dir=telemetry,
                events_dir=events,
                summary=summary,
                control_dir=control,
                start_timeout=1,
                partitions=2,
                stages=list(entry.STAGES),
            )
            with patch.dict(sys.modules, {"pyspark": pyspark, "pyspark.sql": sql}), \
                 patch.dict(entry.os.environ, {"SPARK_MASTER_URL": "spark://experiment-master:7077"}), \
                 patch.object(entry, "validate_paths"), \
                 patch.object(entry, "wait_for_start"), \
                 patch.object(entry.threading, "Thread"), \
                 patch("pipeline.preprocessing.experiments.spark.job.main", side_effect=run_job), \
                 patch("pipeline.preprocessing.experiments.spark.telemetry.parse_event_log", return_value=parsed_event):
                result = entry.run(args)

            self.assertEqual(result["status"], "COMPUTED")
            self.assertEqual(result["application_id"], "app-regression-1")
            self.assertEqual(json.loads(summary.read_text(encoding="utf-8"))["application_id"],
                             "app-regression-1")


if __name__ == "__main__":
    unittest.main()
