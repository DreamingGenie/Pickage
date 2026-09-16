"""Cleanup failure behavior for the experiment driver."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.spark_experiment import job


def measured():
    snapshot = {"timestamp": 1, "cpu": {"usage_usec": 10},
                "memory": {"current": 100, "peak": 120, "events": {}},
                "io": {}, "network": {}, "limitations": {"network_scope": "host"}}
    return {"sample_count": 1, "samples": [snapshot], "delta": None}


class FakeSampler:
    def __init__(self, fail_stop=False):
        self.fail_stop = fail_stop
        self.stop_called = False

    def start(self):
        return self

    def stop(self):
        self.stop_called = True
        if self.fail_stop:
            raise OSError("sampler stop failed")
        return measured()

    def summary(self):
        return measured()


class FakeSpark:
    version = "3.5.3"
    class Context:
        master = "local[2]"
        applicationId = "app-test"
        def setJobGroup(self, *_):
            pass
    class Catalog:
        def clearCache(self):
            pass
    sparkContext = Context()
    catalog = Catalog()
    def __init__(self, fail_stop=False):
        self.fail_stop = fail_stop
        self.stop_called = False
    def stop(self):
        self.stop_called = True
        if self.fail_stop:
            raise OSError("spark stop failed")


def manifest():
    return {"format_version": 1, "input_files": [{"sha256": "x", "bytes": 1}],
            "source_request": {}, "stages": {"package_version": {}, "repository": {}}}


class JobTelemetryCleanupTests(unittest.TestCase):
    def _patch_common(self, sampler, spark, *, stage_error=None, remote_write_error=False):
        stack = [
            patch.object(job, "code_sha", return_value="codehash"),
            patch.object(job, "spark_session", return_value=spark),
            patch.object(job, "read_json", return_value=manifest()),
            patch.object(job, "verify_manifest"),
            patch("pipeline.spark_experiment.telemetry.read_snapshot", return_value=measured()["samples"][0]),
            patch("pipeline.spark_experiment.telemetry.snapshot_delta", return_value={"cpu": {"usage_usec": 10}}),
            patch.object(job, "spark_stage", side_effect=stage_error) if stage_error else
                patch.object(job, "spark_stage", return_value={"ok": True}),
            patch("pipeline.spark_experiment.telemetry.Sampler", return_value=sampler),
        ]
        captured = []
        def write_json(_location, value, _spark=None):
            captured.append(json.loads(json.dumps(value, default=str)))
            if remote_write_error:
                raise OSError("remote report write failed")
        stack.append(patch.object(job, "write_json", side_effect=write_json))
        return stack, captured

    def test_spark_stop_failure_does_not_skip_sampler_or_local_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = Path(tmp) / "telemetry"
            sampler = FakeSampler()
            spark = FakeSpark(fail_stop=True)
            patches, captured = self._patch_common(sampler, spark)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
                with self.assertRaisesRegex(RuntimeError, "spark_stop"):
                    job.main(["--manifest", "manifest.json", "--engine", "spark", "--output", str(Path(tmp)/"out"),
                              "--stages", "package_version", "--telemetry-dir", str(telemetry)])
            self.assertTrue(spark.stop_called)
            self.assertTrue(sampler.stop_called)
            self.assertTrue((telemetry / "samples.json").exists())
            companion = json.loads((telemetry / "report-with-telemetry.json").read_text(encoding="utf-8"))
            self.assertEqual(companion["cleanup_errors"][0]["step"], "spark_stop")

    def test_remote_write_and_sampler_stop_failures_preserve_stage_error_and_restore_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = Path(tmp) / "telemetry"
            sampler = FakeSampler(fail_stop=True)
            spark = FakeSpark()
            original = os.environ.get("PYSPARK_SUBMIT_ARGS")
            os.environ["PYSPARK_SUBMIT_ARGS"] = "original-submit-args"
            patches, _ = self._patch_common(sampler, spark, stage_error=ValueError("stage failed"),
                                             remote_write_error=True)
            try:
                with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
                    with self.assertRaisesRegex(ValueError, "stage failed"):
                        job.main(["--manifest", "manifest.json", "--engine", "spark",
                                  "--output", "s3a://pickage-curated/experiments/run-test",
                                  "--stages", "package_version", "--telemetry-dir", str(telemetry)])
                self.assertEqual(os.environ["PYSPARK_SUBMIT_ARGS"], "original-submit-args")
            finally:
                if original is None:
                    os.environ.pop("PYSPARK_SUBMIT_ARGS", None)
                else:
                    os.environ["PYSPARK_SUBMIT_ARGS"] = original
            self.assertTrue(sampler.stop_called)
            self.assertTrue(spark.stop_called)
            self.assertTrue((telemetry / "samples.json").exists())
            companion = json.loads((telemetry / "report-with-telemetry.json").read_text(encoding="utf-8"))
            self.assertEqual(companion["status"], "FAILED")
            self.assertEqual({e["step"] for e in companion["cleanup_errors"]},
                             {"provisional_remote_report", "sampler_stop"})

    def test_s3a_output_requires_telemetry_directory(self):
        with self.assertRaises(SystemExit) as error:
            job.main(["--manifest", "manifest.json", "--engine", "spark",
                      "--output", "s3a://pickage-curated/experiments/run-test"])
        self.assertEqual(error.exception.code, 2)

    def test_baseline_failure_restores_modified_submit_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = Path(tmp) / "telemetry"
            sampler = FakeSampler(fail_stop=True)
            original = os.environ.get("PYSPARK_SUBMIT_ARGS")
            os.environ["PYSPARK_SUBMIT_ARGS"] = "original-submit-args"
            try:
                with patch.object(job, "code_sha", return_value="codehash"), \
                     patch("pipeline.spark_experiment.telemetry.Sampler", return_value=sampler), \
                     patch("pipeline.spark_experiment.telemetry.read_snapshot", return_value=measured()["samples"][0]), \
                     patch("pipeline.spark_experiment.telemetry.snapshot_delta", return_value=None), \
                     patch.object(job, "read_json", return_value=manifest()), \
                     patch.object(job, "verify_manifest"), \
                     patch.object(job, "baseline", side_effect=ValueError("baseline stage failed")), \
                     patch.object(job, "write_json"):
                    with self.assertRaisesRegex(ValueError, "baseline stage failed"):
                        job.main(["--manifest", "manifest.json", "--engine", "baseline",
                                  "--output", str(Path(tmp)/"out"), "--stages", "repository",
                                  "--telemetry-dir", str(telemetry)])
                self.assertEqual(os.environ["PYSPARK_SUBMIT_ARGS"], "original-submit-args")
                self.assertTrue(sampler.stop_called)
                self.assertTrue((telemetry / "samples.json").exists())
            finally:
                if original is None:
                    os.environ.pop("PYSPARK_SUBMIT_ARGS", None)
                else:
                    os.environ["PYSPARK_SUBMIT_ARGS"] = original


if __name__ == "__main__":
    unittest.main()
