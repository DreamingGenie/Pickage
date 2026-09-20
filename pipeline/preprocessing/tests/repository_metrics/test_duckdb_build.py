"""Real DuckDB outputs through the immutable repository publication boundary."""
import builtins
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.preprocessing.repository_metrics.build import run, verify_completed
from pipeline.preprocessing.tests.repository_metrics import test_duckdb_transform as fixture
from pipeline.preprocessing.tests.repository_metrics.test_build import MemoryS3


class DuckDBBuildContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.RepositoryDuckDBTransformTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.kwargs = dict(snapshot=fixture.SNAPSHOT, curated_run_id="curated-v2",
            curated_outputs=self.fixture.temp / "curated", versions_dir=self.fixture.temp / "versions",
            projects_dir=self.fixture.temp / "projects", candidate_path=self.fixture.temp / "calendar/candidate.json",
            run_id="duckdb-run", work_dir=root / "runs", threads=1, memory_limit="256MB")
        ts = fixture.TS
        self.prepared = self.fixture._inputs([(1, "alpha")], [(1, "1.0.0", ts, 1)],
            [(ts, "alpha", "1.0.0", True, ts, 1, "https://github.com/acme/repo")],
            [(ts, "GITHUB", "acme/repo", 7, 2)])
        self.s3 = MemoryS3()

    def execute(self, **kwargs):
        with patch("pipeline.preprocessing.repository_metrics.input.prepare_inputs", return_value=self.prepared), \
             patch("pipeline.preprocessing.repository_metrics.input.reverify_inputs"):
            return run(self.s3, **{**self.kwargs, **kwargs})

    def test_default_build_publish_and_reverify_without_spark(self):
        original = builtins.__import__
        def no_spark(name, *args, **kwargs):
            if name == "pyspark" or name.startswith("pyspark."):
                raise AssertionError("DuckDB must not import PySpark")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=no_spark):
            result = self.execute(publish=True)
            self.assertEqual(result["status"], "PASSED")
            directory = self.kwargs["work_dir"] / self.kwargs["run_id"]
            manifest, before = verify_completed(directory)
            self.assertEqual(manifest["runtime"]["engine"], "duckdb")
            self.assertEqual(manifest["request"]["execution"]["memory_limit"], "256MB")
            self.assertEqual(manifest["request"]["execution"]["max_temp_directory_size"], "100GB")
            self.assertEqual(set(manifest["report"]["output_counts"]), fixture.GROUPS)
            self.assertEqual(result["publication"]["status"], "PUBLISHED")
            with patch("pipeline.preprocessing.repository_metrics.duckdb_transform.transform", side_effect=AssertionError("must reuse")):
                second = self.execute(publish=True)
            self.assertEqual(second["status"], "REVERIFIED")
            self.assertEqual(second["publication"]["action"], "REVERIFIED")
            self.assertEqual(verify_completed(directory)[1], before)

    def test_engine_and_memory_change_cannot_reuse_run_id(self):
        self.execute()
        for settings in ({"engine": "native"}, {"memory_limit": "512MB"},
                         {"max_temp_directory_size": "200GB"}):
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, "different input or contract"):
                self.execute(**settings)

    def test_invalid_spill_limit_is_rejected(self):
        for value in ("10", "0GB", "10gb", "10 GB"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "explicit MB or GB"):
                self.execute(max_temp_directory_size=value)

    def test_publish_failure_does_not_publish_success_marker(self):
        self.s3.fail_output = True
        with self.assertRaisesRegex(RuntimeError, "upload failure"):
            self.execute(publish=True)
        self.assertFalse(any(key.endswith("/_SUCCESS") for bucket, key in self.s3.objects))
        self.s3.fail_output = False
        self.assertEqual(self.execute(publish=True)["status"], "REVERIFIED")

    def test_injected_spark_requires_explicit_native_engine(self):
        with self.assertRaisesRegex(ValueError, "engine=native"):
            run(self.s3, spark=SimpleNamespace(version="fixture"), **self.kwargs)
