"""Execute these tests in the pinned Spark container (no mocked Spark)."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from pyspark.sql import SparkSession, functions as F

from pipeline.preprocessing.requirements_resolution.policy import make_policy
from pipeline.preprocessing.requirements_resolution.transform import prepare, finalize

STAMP = datetime(2026, 8, 31, 21, 1, 10, 123456)
BEFORE = datetime(2026, 8, 30)
AFTER = datetime(2026, 9, 1)


class TransformSparkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (SparkSession.builder.master("local[2]").appName("requirements-transform-tests")
                     .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2")
                     .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def _inputs(self, root, *, duplicate=False, bad_date=False):
        package = self.spark.createDataFrame([(1, "a", None), (2, "@scope/b", None),
                     (3, "missing", None), (4, "null-list", None), (5, "error", None), (6, "unknown", None)],
                     "package_id INT,name STRING,repo_url STRING")
        values = [(1, "a", "1.0.0", BEFORE, False), (1, "a", "2.0.0", None, False),
                  (2, "@scope/b", "1.2.1", BEFORE, False), (2, "@scope/b", "1.3.0", BEFORE, False),
                  (2, "@scope/b", "2.0.0", AFTER, False), (3, "missing", "1.0.0", BEFORE, False),
                  (4, "null-list", "1.0.0", BEFORE, False), (5, "error", "1.0.0", BEFORE, True),
                  (6, "unknown", "1.0.0", BEFORE, None)]
        version = self.spark.createDataFrame([(v, i, published) for i, _, v, published, _ in values],
                                             "version STRING,package_id INT,published_at TIMESTAMP")
        raw_rows = [(STAMP, name, v, True, 0, published, None, error, None, [], None)
                    for _, name, v, published, error in values]
        if duplicate:
            raw_rows.append(raw_rows[0])
        if bad_date:
            row = list(raw_rows[0]); row[5] = AFTER; raw_rows[0] = tuple(row)
        raw = self.spark.createDataFrame(raw_rows,
                    "SnapshotAt TIMESTAMP,Name STRING,Version STRING,is_release BOOLEAN,ordinal BIGINT,"
                    "published_at TIMESTAMP,Deprecated STRING,dependency_error BOOLEAN,Description STRING,"
                    "Licenses ARRAY<STRING>,source_repo STRING")
        req_rows = [(STAMP, "a", "1.0.0", [("@scope/b", "^1"), ("@scope/b", "^1"), None], [], []),
                    (STAMP, "a", "2.0.0", [("@scope/b", "1.2.1")], [("@scope/b", "^2")], []),
                    (STAMP, "@scope/b", "1.2.1", [], [], []), (STAMP, "@scope/b", "1.3.0", [], [], []),
                    (STAMP, "null-list", "1.0.0", None, [], []), (STAMP, "error", "1.0.0", [], [], []),
                    (STAMP, "unknown", "1.0.0", [], [], [])]
        req = self.spark.createDataFrame(req_rows,
                  "SnapshotAt TIMESTAMP,Name STRING,Version STRING,Dependencies ARRAY<STRUCT<Name:STRING,Requirement:STRING>>,"
                  "PeerDependencies ARRAY<STRUCT<Name:STRING,Requirement:STRING>>,OptionalDependencies ARRAY<STRUCT<Name:STRING,Requirement:STRING>>")
        paths = {}
        for key, frame in (("package", package), ("version", version), ("versions_full", raw), ("requirements", req)):
            path = Path(root) / key
            frame.write.mode("errorifexists").parquet(str(path))
            paths[key] = [str(path)]
        return {"files": paths, "snapshot": "2026-08-31", "snapshot_timestamp": STAMP.isoformat() + "Z",
                "input_sha256": "fixture", "curated_run_id": "curated-fixture", "bronze_run_id": "bronze-fixture"}

    def _policy(self, null="include", unresolved="partial"):
        return make_policy(kinds=["dependencies"], unknown_published_at=null,
                           unresolved=unresolved, decision_reference="synthetic test fixture")

    def _bridge(self, prepared, output, *, extra=False, bad_target=False):
        rows = []
        for row in self.spark.read.parquet(str(prepared / "declarations")).select("lookup_id", "declared_name", "requirement").distinct().collect():
            target = "1.3.0" if row.requirement == "^1" else "1.2.1" if row.requirement == "1.2.1" else None
            if bad_target and target:
                target = "999.0.0"
            rows.append((row.lookup_id, row.declared_name, row.requirement, row.requirement, target,
                         "RESOLVED" if target else "INVALID_PACKAGE_NAME"))
        if extra:
            rows.append(("unexpected", "@scope/b", "*", "*", None, "NO_ELIGIBLE_TARGET"))
        mapping = self.spark.createDataFrame(rows,
                       "lookup_id STRING,declared_name STRING,requirement STRING,normalized_range STRING,target_version STRING,status STRING")
        mapping.write.parquet(str(output / "mappings"))
        self.spark.createDataFrame([], "name STRING,version STRING,reason STRING").write.parquet(str(output / "target_quality"))

    def test_all_sources_null_items_and_partial_finalization(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = self._inputs(root)
            report = prepare(self.spark, inputs, self._policy(), root / "prepared")
            self.assertEqual(report["counts"], {"sources": 8, "declarations": 4, "candidates": 8})
            self.assertEqual(report["excluded_kind_counts"]["peerDependencies"], 1)
            self._bridge(root / "prepared", root / "bridge")
            final = finalize(self.spark, root / "prepared", root / "bridge", inputs,
                             self._policy(), root / "final", "fixture")
            self.assertEqual(final["output_counts"]["edges"], 2)
            self.assertEqual(final["resolved_declarations"], 3)
            self.assertEqual(final["unresolved_declarations"], 1)
            self.assertEqual(final["resolution_status"], "PARTIAL")
            self.assertFalse(final["ready_for_dependents"])
            counts = final["source_status_counts"]
            for status in ("MISSING_REQUIREMENTS", "NULL_DEPENDENCY_LIST", "DEPENDENCY_EXTRACTION_ERROR", "DEPENDENCY_EXTRACTION_UNKNOWN"):
                self.assertEqual(counts[status], 1)
            outcomes = self.spark.read.parquet(str(root / "final/declaration_outcomes"))
            self.assertEqual(outcomes.where("declared_name IS NULL AND requirement IS NULL").count(), 1)
            self.assertTrue({"snapshot_at", "snapshot_timestamp", "input_sha256", "run_id", "bronze_run_id"}.issubset(outcomes.columns))
            self._bridge(root / "prepared", root / "extra", extra=True)
            with self.assertRaisesRegex(ValueError, "Unexpected bridge lookup"):
                finalize(self.spark, root / "prepared", root / "extra", inputs, self._policy(), root / "bad-final", "fixture")
            self._bridge(root / "prepared", root / "bad-target", bad_target=True)
            with self.assertRaisesRegex(ValueError, "absent from eligible"):
                finalize(self.spark, root / "prepared", root / "bad-target", inputs, self._policy(), root / "bad-target-final", "fixture")

    def test_duplicate_and_provenance_mismatch_fail(self):
        for variant in ("duplicate", "bad_date"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); inputs = self._inputs(root, **{variant: True})
                with self.assertRaisesRegex(ValueError, "Duplicate raw version|release/date provenance"):
                    prepare(self.spark, inputs, self._policy(), root / "prepared")

    def test_null_publication_policy_filters_source_and_target_together(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = self._inputs(root)
            report = prepare(self.spark, inputs, self._policy(null="exclude"), root / "prepared")
            self.assertEqual(report["counts"]["sources"], 7)
            self.assertEqual(report["excluded_unknown_publication_versions"], 1)
            self.assertEqual(self.spark.read.parquet(str(root / "prepared/candidates")).where("published_at IS NULL").count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
