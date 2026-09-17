"""Backend integration checks for the production resolver switch."""
import builtins
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents.historical_production import WEIGHTED_ALGORITHM, run, verify_run
from pipeline.preprocessing.experiments.dependents.historical_production_backend_benchmark import compare_runs
from pipeline.preprocessing.tests.version_dependents.test_historical_production import prepared_fixture


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Optional CPU/GPU backend requires NumPy')
class ProductionBackendTests(unittest.TestCase):
    def _run(self, root, backend, **kwargs):
        inputs = root / "inputs"
        root.mkdir(parents=True, exist_ok=True)
        digest = prepared_fixture(inputs)
        args = {"prepared_dir": inputs, "manifest_sha256": digest,
                "output": root / backend, "min_free_bytes": 0,
                "resolver_backend": backend, "algorithm": WEIGHTED_ALGORITHM, **kwargs}
        result = run(**args)
        self.assertEqual(result["run_status"], "COMPLETE")
        verified = verify_run(run_dir=args["output"], manifest_sha256=result["run_manifest_sha256"])
        self.assertEqual(verified["snapshots"], 3)
        return result

    def _counts(self, result):
        with duckdb.connect() as con:
            return con.execute(
                "SELECT package_id,version,start_index,end_index,dependents_count "
                "FROM read_parquet(?) ORDER BY 1,2,3",
                [str(Path(result["cache_dir"]) / "count_intervals.parquet")]).fetchall()

    def _artifact_rows(self, result, relative):
        path = Path(result["cache_dir"]).parent / relative
        with duckdb.connect() as con:
            return con.execute("SELECT * FROM read_parquet(?) ORDER BY ALL", [str(path)]).fetchall()

    def _daily_rows(self, result, filename):
        history = Path(result["cache_dir"]).parent / "history"
        values = []
        for marker in sorted(history.glob("snapshot=*/complete.json")):
            anchor = json.loads(marker.read_text(encoding="utf-8"))
            path = marker.parent / "attempts" / anchor["attempt_id"] / filename
            with duckdb.connect() as con:
                if filename == "quality.parquet":
                    values.extend(con.execute("SELECT * EXCLUDE (run_plan_sha256) FROM read_parquet(?) ORDER BY ALL", [str(path)]).fetchall())
                else:
                    values.extend(con.execute("SELECT * FROM read_parquet(?) ORDER BY ALL", [str(path)]).fetchall())
        return values

    def test_npm_and_cpu_have_identical_complete_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            npm = self._run(root / "npm", "npm")
            cpu = self._run(root / "cpu", "cpu")
            self.assertEqual(self._counts(npm), self._counts(cpu))
            self.assertEqual(self._artifact_rows(npm, "cache/quality.parquet"), self._artifact_rows(cpu, "cache/quality.parquet"))
            self.assertEqual(self._daily_rows(npm, "counts.parquet"), self._daily_rows(cpu, "counts.parquet"))
            self.assertEqual(self._daily_rows(npm, "quality.parquet"), self._daily_rows(cpu, "quality.parquet"))
            self.assertEqual(len(compare_runs(npm["run_dir"], cpu["run_dir"])), 13)

    def test_cpu_partial_partition_then_complete_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = root / "inputs"; digest = prepared_fixture(inputs)
            args = {"prepared_dir": inputs, "manifest_sha256": digest, "output": root / "run",
                    "min_free_bytes": 0, "resolver_backend": "cpu", "algorithm": WEIGHTED_ALGORITHM}
            first = run(**args, max_partitions=1, max_snapshots=1)
            self.assertEqual(first["run_status"], "INCOMPLETE")
            partial = run(**args, resume=True, max_snapshots=1)
            self.assertEqual(partial["run_status"], "INCOMPLETE")
            complete = run(**args, resume=True)
            self.assertEqual(complete["run_status"], "COMPLETE")
            verify_run(run_dir=args["output"], manifest_sha256=complete["run_manifest_sha256"])
            again = run(**args, resume=True)
            self.assertEqual(again["run_manifest_sha256"], complete["run_manifest_sha256"])
            self.assertEqual(again["written_partitions"], [])

    def test_resume_rejects_backend_batch_workspace_runtime_and_generation_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = root / "inputs"; digest = prepared_fixture(inputs)
            args = {"prepared_dir": inputs, "manifest_sha256": digest, "output": root / "run",
                    "min_free_bytes": 0, "resolver_backend": "cpu", "algorithm": WEIGHTED_ALGORITHM}
            run(**args, max_partitions=1)
            for key, value in (("resolver_backend", "npm"), ("resolver_lookup_batch", 2),
                               ("gpu_workspace_mib", 64)):
                changed = dict(args); changed[key] = value
                with self.assertRaises(ValueError): run(**changed, resume=True)
            with patch("pipeline.preprocessing.version_dependents.historical_production.ranked_resolver.runtime_identity",
                       return_value={"backend": "cpu", "numpy": "changed"}):
                with self.assertRaises(ValueError): run(**args, resume=True)
            with patch("pipeline.preprocessing.version_dependents.historical_production.ranked_resolver.generation_contract", return_value={"changed": True}):
                with self.assertRaises(ValueError): run(**args, resume=True)

    def test_cpu_does_not_import_torch(self):
        with tempfile.TemporaryDirectory() as directory:
            original = builtins.__import__
            def blocked(name, *args, **kwargs):
                if name == "torch":
                    raise AssertionError("CPU resolver imported torch")
                return original(name, *args, **kwargs)
            with patch("builtins.__import__", side_effect=blocked):
                self._run(Path(directory), "cpu")

    def test_gpu_unavailable_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = root / "inputs"; digest = prepared_fixture(inputs)
            output = root / "gpu"
            with patch("pipeline.preprocessing.version_dependents.historical_production.ranked_resolver.runtime_identity",
                       side_effect=RuntimeError("GPU backend requested but CUDA is unavailable")):
                with self.assertRaisesRegex(RuntimeError, "CUDA"):
                    run(prepared_dir=inputs, manifest_sha256=digest, output=output,
                        min_free_bytes=0, resolver_backend="gpu")
            self.assertFalse(output.exists())

    @unittest.skipUnless(os.environ.get("VD_GPU_TESTS") == "1", "Set VD_GPU_TESTS=1 for real CUDA checks")
    def test_gpu_matches_npm_and_can_complete_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            npm = self._run(root / "npm", "npm")
            gpu_root = root / "gpu"; gpu_root.mkdir(parents=True); inputs = gpu_root / "inputs"; digest = prepared_fixture(inputs)
            args = {"prepared_dir": inputs, "manifest_sha256": digest, "output": gpu_root / "run",
                    "min_free_bytes": 0, "resolver_backend": "gpu", "algorithm": WEIGHTED_ALGORITHM}
            partial = run(**args, max_partitions=1)
            self.assertEqual(partial["run_status"], "INCOMPLETE")
            result = run(**args, resume=True)
            self.assertEqual(result["run_status"], "COMPLETE")
            self.assertEqual(self._counts(npm), self._counts(result))
            verify_run(run_dir=args["output"], manifest_sha256=result["run_manifest_sha256"])
            self.assertEqual(len(compare_runs(npm["run_dir"], result["run_dir"])), 13)
            again = run(**args, resume=True)
            self.assertEqual(again["run_manifest_sha256"], result["run_manifest_sha256"])
            self.assertEqual(again["written_partitions"], [])
            target = next(args["output"].glob("partitions/*/attempts/*/lookup_intervals.parquet"))
            with target.open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaises(ValueError):
                verify_run(run_dir=args["output"], manifest_sha256=result["run_manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
