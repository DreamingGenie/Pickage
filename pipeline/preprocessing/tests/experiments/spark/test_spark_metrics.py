"""Focused Spark contract checks; skipped when the optional Spark runtime is absent."""
import tempfile
import unittest
from pathlib import Path

try:
    from pyspark.sql import SparkSession
except ModuleNotFoundError:  # Spark is supplied only by the experiment image.
    SparkSession = None

try:
    from pipeline.preprocessing.experiments.spark.downloads import aggregate
except ModuleNotFoundError:
    aggregate = None


@unittest.skipUnless(SparkSession is not None and aggregate is not None, "PySpark is available only in the Spark runtime")
class SparkMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (SparkSession.builder.master("local[2]").appName("spark-metrics-tests")
                     .config("spark.ui.enabled", "false")
                     .config("spark.sql.shuffle.partitions", "2").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_downloads_first_snapshot_preserves_population(self):
        spark = self.spark
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spark.createDataFrame([(1, "a", "https://example/a"), (2, "b", "https://example/b")],
                                  "package_id int, name string, repo_url string").write.mode("overwrite").parquet(str(root / "packages"))
            spark.createDataFrame([("a", "READY"), ("b", "READY")], "name string, status string").write.mode("overwrite").parquet(str(root / "status"))
            (root / "target.csv").write_text("name\na\nb\n", encoding="utf-8")
            prepared = {"package_files": [str(root / "packages")], "daily_files": [],
                        "target_file": str(root / "target.csv"), "status_file": str(root / "status"),
                        "interval": {"snapshot_at": "2026-08-31", "previous_snapshot_at": None},
                        "available_start": "2026-08-01", "available_end": "2026-08-30",
                        "lineage": {key: "a" * 64 for key in ("input_manifest_sha256", "policy_sha256", "aggregation_policy_sha256")}}
            result = aggregate(spark, prepared, str(root / "out"))
            rows = spark.read.parquet(str(root / "out" / "interval_downloads.parquet")).orderBy("package_id").collect()
            self.assertEqual(result["quality"]["package_rows"], 2)
            self.assertEqual([row.download_sum for row in rows], [None, None])
            self.assertEqual([row.data_status for row in rows], ["UNAVAILABLE", "UNAVAILABLE"])
