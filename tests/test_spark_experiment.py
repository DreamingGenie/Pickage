"""Pure contract tests for the Spark experiment infrastructure (no Docker/Spark)."""
import io
import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from pipeline.spark_experiment.benchmark import remap
from pipeline.spark_experiment.compare import canonicalize, compare
from pipeline.spark_experiment.job import GROUPS
from pipeline.spark_experiment.overlay import OverlayS3
from pipeline.spark_experiment.prepare import digest, verify_inputs
from pipeline.curated.build import CURRENT


class Source:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, *, Bucket, Key):
        body = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body), "ContentLength": len(body)}


class SparkExperimentInfrastructureTests(unittest.TestCase):
    def test_overlay_reads_raw_and_pinned_parent_but_keeps_current_local(self):
        parent = {"run_prefix": "depsdev/v1/curated/run-parent"}
        source = Source({
            ("pickage-raw", "raw/key"): b"raw",
            ("pickage-curated", parent["run_prefix"] + "/data.parquet"): b"parent",
            ("pickage-curated", CURRENT): b"production-current",
        })
        with tempfile.TemporaryDirectory() as tmp:
            overlay = OverlayS3(source, Path(tmp) / "objects", parent)
            self.assertEqual(overlay.get_object(Bucket="pickage-raw", Key="raw/key")["Body"].read(), b"raw")
            self.assertEqual(overlay.get_object(Bucket="pickage-curated", Key=parent["run_prefix"] + "/data.parquet")["Body"].read(), b"parent")
            self.assertEqual(json.loads(overlay.get_object(Bucket="pickage-curated", Key=CURRENT)["Body"].read()), parent)
            with self.assertRaises(ValueError):
                overlay.put_object(Bucket="pickage-raw", Key="raw/new", Body=b"x")
            with self.assertRaises(ValueError):
                overlay.delete_object(Bucket="pickage-raw", Key="raw/key")
            with self.assertRaises(Exception):
                overlay.get_object(Bucket="pickage-curated", Key="other-run/data")

    def test_verify_inputs_detects_frozen_file_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.parquet"
            path.write_bytes(b"frozen")
            manifest = {"input_files": [{"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}]}
            verify_inputs(manifest)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Frozen experiment input changed"):
                verify_inputs(manifest)

    def test_canonicalize_compares_null_zero_duplicate_and_json_logically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left, right = root / "left.parquet", root / "right.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE l(package_id INTEGER, downloads BIGINT, dependency VARCHAR)")
                con.executemany("INSERT INTO l VALUES (?, ?, ?)", [(1, 0, '{"a":1,"b":[2]}'), (1, None, None)])
                con.execute("COPY l TO ? (FORMAT PARQUET)", [str(left)])
                con.execute("CREATE TABLE r(dependency VARCHAR, downloads BIGINT, package_id INTEGER)")
                con.executemany("INSERT INTO r VALUES (?, ?, ?)", [('{"b":[2],"a":1}', 0, 1), (None, None, 1)])
                con.execute("COPY r TO ? (FORMAT PARQUET)", [str(right)])
                left_lines = root / "left.jsonl"
                right_lines = root / "right.jsonl"
                left_schema, left_logical, left_count = canonicalize(con, [str(left)], left_lines, {"dependency"})
                right_schema, right_logical, right_count = canonicalize(con, [str(right)], right_lines, {"dependency"})
            self.assertEqual(left_schema, right_schema)
            self.assertEqual(left_logical, right_logical)
            self.assertEqual(left_count, right_count, 2)
            self.assertEqual(sorted(left_lines.read_text().splitlines()), sorted(right_lines.read_text().splitlines()))
            self.assertNotEqual(left_lines.read_text().splitlines()[0], left_lines.read_text().splitlines()[1])

    def test_benchmark_remap_is_recursive_and_only_rewrites_source_prefix(self):
        value = {"path": "/host/input/file", "nested": ["/host/input/x", "/host/input2/keep"], "other": 3}
        self.assertEqual(remap(value, "/host/input", "/experiment"), {"path": "/experiment/file", "nested": ["/experiment/x", "/host/input2/keep"], "other": 3})

    def test_comparison_rejects_duplicate_loss_and_changed_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with duckdb.connect() as con:
                for engine in ("baseline", "spark"):
                    folder = root / engine
                    folder.mkdir()
                    for group in GROUPS["downloads"]:
                        query = "SELECT 0::BIGINT AS downloads"
                        if engine == "baseline":
                            query += " UNION ALL SELECT 0::BIGINT"
                        con.execute("COPY (" + query + ") TO ? (FORMAT PARQUET)", [str(folder / group)])
            def report(engine):
                return {"status": "COMPUTED", "input_identity": "same", "code_sha256": "same",
                        "stages": {"downloads": {"output": str(root / engine)}}}
            a, b = report("baseline"), report("spark")
            checked = compare(a, b, root / "compare")
            self.assertEqual(checked["status"], "DIFFERENT")
            self.assertTrue(all(r["baseline_only_rows"] == 1 for r in checked["groups"].values()))
            b["code_sha256"] = "changed"
            with self.assertRaisesRegex(ValueError, "Source code changed"):
                compare(a, b, root / "changed")


if __name__ == "__main__":
    unittest.main()
