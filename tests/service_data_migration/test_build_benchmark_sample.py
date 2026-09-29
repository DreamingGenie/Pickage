import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "service-data-migration" / "build_benchmark_sample.py"
SPEC = importlib.util.spec_from_file_location("build_benchmark_sample", MODULE_PATH)
sample = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sample)


class BenchmarkSampleTests(unittest.TestCase):
    def test_caps_and_output_path_are_bounded(self):
        args = type("Args", (), {
            "output": Path("data/service-data-migration/benchmark-900"),
            "pvs_cap": 1_000_000, "version_cap": 300_000,
            "package_snapshot_cap": 300_000, "package_cap": 50_000,
        })()
        output, _ = sample.validate_args(args)
        self.assertTrue(str(output).endswith("benchmark-900"))
        args.pvs_cap = 0
        with self.assertRaises(sample.SampleError):
            sample.validate_args(args)

    def test_source_sampling_is_read_only_and_preserves_version_column_order(self):
        parts = "\n".join(f"d20220{i:04d}|100000" for i in range(1, 5))
        captured = []
        signatures = "\n".join(f"{name}|1|0|0" for name in (
            "package", "version", "snapshot", "package_snapshot", "package_version_snapshot"))

        def fake_source(sql):
            if "FROM pg_inherits" in sql:
                return parts
            captured.append(sql)
            return signatures

        with tempfile.TemporaryDirectory() as raw, patch.object(sample, "source_psql", side_effect=fake_source):
            result = sample.prepare_source(Path(raw) / "benchmark-901", pvs_cap=100, version_cap=100,
                                           package_snapshot_cap=100, package_cap=100)
        sql = captured[0]
        self.assertIn("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY", sql)
        self.assertIn("SET LOCAL DateStyle = 'ISO, YMD'", sql)
        self.assertIn("CREATE TEMP TABLE sampled_version AS TABLE public.version WITH NO DATA", sql)
        self.assertIn("INSERT INTO sampled_version (version,package_id,published_at,ordinal,description,licenses,deprecated,dependency)", sql)
        self.assertEqual(result["signatures"]["version"]["rows"], 1)


if __name__ == "__main__":
    unittest.main()
