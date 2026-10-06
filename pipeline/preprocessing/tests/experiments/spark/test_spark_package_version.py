import tempfile
import unittest
from datetime import datetime
from pathlib import Path

try:
    import duckdb
    from pipeline.preprocessing.curated.transform import transform as baseline_transform
    from pipeline.preprocessing.experiments.spark.compare import compare
except ImportError:
    duckdb = None
    baseline_transform = compare = None
from pipeline.preprocessing.experiments.spark.package_version import _json_dependencies, _paths


class SparkPackageVersionHelperTests(unittest.TestCase):
    def test_uri_join_preserves_s3a_scheme(self):
        self.assertEqual(_paths("s3a://bucket/run", "package/data"), "s3a://bucket/run/package/data")
        self.assertEqual(_paths("C:/tmp/run/", "version/data"), "C:/tmp/run/version/data")

    def test_dependency_json_matches_curated_shape_and_order(self):
        item = {"Name": "z", "Requirement": "^1"}
        result = _json_dependencies([item, item], [], [])
        self.assertEqual(result, '{"dependencies":{"z":"^1"},"peerDependencies":{},"optionalDependencies":{}}')

    def test_dependency_json_rejects_conflicts_and_null_arrays(self):
        self.assertIsNone(_json_dependencies(
            [{"Name": "dep", "Requirement": "^1"}, {"Name": "dep", "Requirement": "^2"}], [], []))
        self.assertIsNone(_json_dependencies(None, [], []))


try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None


@unittest.skipUnless(SparkSession is not None and duckdb is not None, "pyspark and duckdb are required")
class SparkPackageVersionTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.preprocessing.experiments.spark.job import spark_session
        cls.spark = SparkSession.builder.master("local[2]").getOrCreate()
        cls.spark = spark_session(2)

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    @staticmethod
    def _write_inputs(root):
        snapshot = datetime(2026, 8, 31, 21, 1, 10)
        versions = [
            ("app", "1.0.0", snapshot, True, 1, "description", ["MIT"], None, "https://github.com/a/old", snapshot),
            ("app", "2.0.0", snapshot, True, 2, "description", ["MIT"], None, "https://github.com/a/new", snapshot),
            ("nul", "1.0.0", snapshot, True, 1, "before\x00after", ["MIT"], None, None, snapshot),
            ("future", "1.0.0", datetime(2026, 9, 1), True, 1, "future", ["MIT"], None, None, snapshot),
            ("nonrelease", "1.0.0", snapshot, False, 1, "excluded", ["MIT"], None, None, snapshot),
            ("invalid", "1.0.0", snapshot, True, 1, "invalid", ["MIT"], None, None, snapshot),
        ]
        dep = [{"Name": "dep", "Requirement": "^1"}]
        requirements = [
            ("app", "1.0.0", dep, [], [], snapshot),
            ("app", "2.0.0", dep + dep, [], [], snapshot),
            ("nul", "1.0.0", [], [], [], snapshot),
            ("invalid", "1.0.0", dep + [{"Name": "dep", "Requirement": "^2"}], [], [], snapshot),
        ]
        con = duckdb.connect()
        try:
            con.execute("CREATE TABLE versions (Name VARCHAR, Version VARCHAR, published_at TIMESTAMP, is_release BOOLEAN, ordinal BIGINT, Description VARCHAR, Licenses VARCHAR[], Deprecated VARCHAR, source_repo VARCHAR, SnapshotAt TIMESTAMP)")
            con.executemany("INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", versions)
            con.execute("CREATE TABLE requirements (Name VARCHAR, Version VARCHAR, Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], PeerDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], OptionalDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], SnapshotAt TIMESTAMP)")
            con.executemany("INSERT INTO requirements VALUES (?, ?, ?, ?, ?, ?)", requirements)
            con.execute(f"COPY versions TO '{(root / 'versions.parquet').as_posix()}' (FORMAT PARQUET)")
            con.execute(f"COPY requirements TO '{(root / 'requirements.parquet').as_posix()}' (FORMAT PARQUET)")
            con.execute("CREATE TABLE ids (package_id INTEGER, name VARCHAR)")
            con.execute("INSERT INTO ids VALUES (7, 'legacy'), (11, 'app')")
            con.execute(f"COPY ids TO '{(root / 'ids.parquet').as_posix()}' (FORMAT PARQUET)")
        finally:
            con.close()
        return root / "versions.parquet", root / "requirements.parquet", root / "ids.parquet"

    def test_transform_matches_duckdb_baseline_for_all_output_groups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            versions, requirements, previous = self._write_inputs(root)
            baseline_output = root / "baseline"
            spark_output = root / "spark"
            with duckdb.connect() as con:
                baseline_report = baseline_transform(
                    con, [versions], [requirements], [previous], "2026-08-31", baseline_output)
            spark_report = __import__(
                "pipeline.preprocessing.experiments.spark.package_version", fromlist=["transform"]
            ).transform(self.spark, [str(versions)], [str(requirements)], [str(previous)], "2026-08-31", str(spark_output))
            self.assertEqual(baseline_report["output_counts"], spark_report["output_counts"])
            checked = compare(
                {"status": "COMPUTED", "input_identity": "fixture", "code_sha256": "fixture",
                 "stages": {"package_version": {"output": str(baseline_output)}}},
                {"status": "COMPUTED", "input_identity": "fixture", "code_sha256": "fixture",
                 "stages": {"package_version": {"output": str(spark_output)}}},
                root / "comparison",
            )
            self.assertEqual(checked["status"], "EQUAL")
            self.assertEqual(set(checked["groups"]), {
                "package_version/package/data", "package_version/version/data", "package_version/package_ids/data",
                "package_version/quality/repository_selection", "package_version/quality/excluded_versions",
                "package_version/quality/dependency_issues", "package_version/quality/metadata_issues",
            })


if __name__ == "__main__":
    unittest.main()
