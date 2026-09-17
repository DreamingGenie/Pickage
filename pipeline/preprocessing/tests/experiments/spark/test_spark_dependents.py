"""Small local Spark oracle for the experimental dependents stage."""
from pathlib import Path
import tempfile
import unittest

from pipeline.preprocessing.experiments.spark.dependents import calculate

@unittest.skipUnless(__import__("importlib").util.find_spec("pyspark") and __import__("importlib").util.find_spec("duckdb"), "Spark test dependencies are not installed")
class SparkDependentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyspark.sql import SparkSession
        cls.spark = (SparkSession.builder.master("local[2]").appName("spark-dependents-test")
                     .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2")
                     .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_stable_target_counts_and_untargeted_null(self):
        from datetime import datetime
        from pipeline.preprocessing.experiments.spark.job import node_runtime
        from pyspark.sql import functions as F
        import duckdb
        from pipeline.preprocessing.orchestration.dependents import calculate as baseline_calculate
        from pipeline.preprocessing.experiments.spark.compare import compare
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            self.spark.createDataFrame([(10, "app"), (20, "lib"), (30, "zero")], "package_id int,name string").write.parquet(str(root / "package"))
            version_rows = [(10, "1.0.0", datetime(2021, 1, 1)), (10, "2.0.0-beta.1", datetime(2021, 1, 1)),
                            (20, "1.0.0", datetime(2021, 1, 1)), (20, "2.0.0-beta.1", datetime(2021, 1, 1)),
                            (30, "1.0.0", datetime(2021, 1, 1))]
            self.spark.createDataFrame(version_rows, "package_id int,version string,published_at timestamp").write.parquet(str(root / "version"))
            req_rows = [("app", "1.0.0", [{"Name": "lib", "Requirement": "^1"},
                        {"Name": "lib", "Requirement": None},
                        {"Name": "lib", "Requirement": "npm:lib@^1"},
                        {"Name": "missing", "Requirement": "^1"}]),
                        ("app", "2.0.0-beta.1", [{"Name": "lib", "Requirement": "^1"}, {"Name": "lib", "Requirement": "^1"}])]
            req = self.spark.createDataFrame(req_rows, "Name string,Version string,Dependencies array<struct<Name:string,Requirement:string>>")
            req = req.withColumn("PeerDependencies", F.array().cast("array<struct<Name:string,Requirement:string>>"))
            req = req.withColumn("OptionalDependencies", F.col("PeerDependencies"))
            req.withColumn("SnapshotAt", F.lit(datetime(2026, 8, 31, 21))).write.parquet(str(root / "requirements"))
            raw_rows = [(name, ver, published, True, False) for (pid, ver, published), (name, _) in zip(version_rows, [("app", 0), ("app", 0), ("lib", 0), ("lib", 0), ("zero", 0)])]
            self.spark.createDataFrame(raw_rows, "Name string,Version string,published_at timestamp,is_release boolean,dependency_error boolean").withColumn("SnapshotAt", F.lit(datetime(2026, 8, 31, 21))).write.parquet(str(root / "versions_full"))
            self.spark.createDataFrame([("lib",), ("missing",), ("zero",)], "name string").coalesce(1).write.parquet(str(root / "targets"))
            for key in ("package", "version", "requirements", "versions_full"):
                paths[key] = str(root / key)
            paths["targets"] = str(root / "targets")
            runtime = node_runtime()
            result = calculate(self.spark, files=paths, snapshot="2026-08-31", snapshot_timestamp="2026-08-31T21:00:00Z", output=str(root / "out"), runtime=runtime)
            rows = {(r.package_id, r.version): r.dependents_count for r in self.spark.read.parquet(result["outputs"]["version_dependents"]).collect()}
            self.assertEqual(rows[(20, "1.0.0")], 2)
            self.assertIsNone(rows[(20, "2.0.0-beta.1")])
            self.assertIsNone(rows[(10, "1.0.0")])
            self.assertEqual(rows[(30, "1.0.0")], 0)
            self.assertEqual(result["quality"]["rows"], 5)
            self.assertEqual(result["resolution_lookup"]["rows"], 4)
            baseline_files = {key: [str(p) for p in Path(value).glob("*.parquet")]
                              for key, value in paths.items() if key != "targets"}
            baseline_files["targets"] = str(next(Path(paths["targets"]).glob("*.parquet")))
            with duckdb.connect() as con:
                _, _, baseline_quality = baseline_calculate(con, files=baseline_files,
                    snapshot="2026-08-31", snapshot_timestamp="2026-08-31T21:00:00Z",
                    output=root / "baseline", runtime=runtime)
            for field in ("resolution_status", "source_gaps", "unresolved_declarations", "rows", "zero_rows", "null_rows"):
                self.assertEqual(result["quality"][field], baseline_quality[field], field)
            def report(output):
                return {"status": "COMPUTED", "input_identity": "oracle", "code_sha256": "oracle",
                        "stages": {"dependents": {"output": str(output)}}}
            compared = compare(report(root / "baseline"), report(root / "out"), root / "compare")
            self.assertEqual(compared["status"], "EQUAL", compared)


if __name__ == "__main__":
    unittest.main()
