"""Regression checks for repository-relative execution resources."""
import importlib
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pipeline.preprocessing.common.paths import REPO_ROOT


class LayoutTests(unittest.TestCase):
    def test_code_contract_resources_exist(self):
        functions = {
            "curated.build": "_code_hash",
            "downloads_interval.load": "contract_sha256",
            "package_snapshot.policy": "contract_sha256",
            "package_snapshot.history_contract": "build_contract_sha256",
            "repository_metrics.build": "code_sha256",
            "requirements_resolution.build": "_code_fingerprint",
            "version_dependents.historical_profile": "_contract",
            "version_dependents.historical_artifact": "_contract",
            "version_dependents.historical_parallel": "contract",
            "version_dependents.historical_production": "contract",
        }
        for module, name in functions.items():
            with self.subTest(module=module):
                value = getattr(importlib.import_module("pipeline.preprocessing." + module), name)()
                self.assertTrue(value)

    def test_node_workers_exist(self):
        from pipeline.preprocessing.experiments.spark.job import node_runtime
        for key in ("worker", "classifier_worker"):
            self.assertTrue(Path(node_runtime()[key]).is_file())

    def test_shared_helpers_preserve_db_interface(self):
        from pipeline.postgresql import input as db
        from pipeline.preprocessing.common import curated_input as shared
        self.assertEqual(db._SCHEMAS, shared.SCHEMAS)
        path = Path("quoted'input.parquet")
        self.assertEqual(db._sql_path(path), shared.sql_path(path))
        self.assertEqual(db._sql_paths([path]), shared.sql_paths([path]))

    def test_legacy_cli_delegates(self):
        from pipeline.orchestration.__main__ import main as old
        from pipeline.preprocessing.orchestration.__main__ import main as new
        self.assertIs(old, new)

    def test_spark_container_mounts_match_job_paths(self):
        from pipeline.preprocessing.requirements_resolution import runtime
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "stage"
            def complete(command, **kwargs):
                (output / "result.json").write_text("{}")
                mounts = [command[i + 1] for i, item in enumerate(command) if item == "--mount"]
                for area in ("requirements_resolution", "snapshot"):
                    source = REPO_ROOT / "pipeline" / "preprocessing" / area
                    self.assertTrue(source.is_dir())
                    self.assertIn(f"type=bind,source={source},target=/workspace/pipeline/preprocessing/{area},readonly", mounts)
                self.assertIn("/workspace/pipeline/preprocessing/requirements_resolution/spark_job.py", command)
                return SimpleNamespace(returncode=0)
            with patch.object(runtime.subprocess, "run", side_effect=complete):
                runtime.run_stage("prepare", {"sources": {}, "files": {}}, {}, output, run_id="layout")
