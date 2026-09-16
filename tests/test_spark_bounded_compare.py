"""Tiny-Parquet tests for the SQL-backed bounded comparator."""
import tempfile
import unittest
from pathlib import Path

import duckdb

from pipeline.spark_experiment.compare import compare as old_compare
from pipeline.spark_experiment.job import GROUPS
from pipeline.spark_experiment.runtime.bounded_compare import compare


def write_parquet(path, schema, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    names = [name for name, _ in schema]
    columns = ",".join(f'"{name}" {kind}' for name, kind in schema)
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE source ({columns})")
        if rows:
            con.executemany("INSERT INTO source VALUES (" + ",".join("?" for _ in names) + ")", rows)
        con.execute("COPY source TO ? (FORMAT PARQUET)", [str(path)])


def make_reports(root, *, scenario="equal"):
    baseline_root, spark_root = root / "baseline", root / "spark"
    baseline_root.mkdir(); spark_root.mkdir()
    common_schema = [("item", "VARCHAR"), ("value", "BIGINT")]
    for index, group in enumerate(GROUPS["package_version"]):
        if group == "version/data":
            schema = [("Name", "VARCHAR"), ("Version", "VARCHAR"), ("licenses", "VARCHAR"), ("dependency", "VARCHAR")]
            left_schema = schema
            right_schema = schema
            left_rows = [("pkg", "1.0.0", '{"z":1,"a":["x","y"]}', '{"requires":{"b":"^1","a":"*"}}')]
            right_rows = [("pkg", "1.0.0", '{"a":["x","y"],"z":1}', '{"requires":{"a":"*","b":"^1"}}')]
            if scenario == "array_difference":
                right_rows = [("pkg", "1.0.0", '{"a":["y","x"],"z":1}', '{"requires":{"a":"*","b":"^1"}}')]
        else:
            schema = common_schema
            left_schema = schema
            right_schema = schema
            left_rows = [("x", 0), ("x", None)]
            right_rows = [("x", 0), ("x", None)]
            if scenario == "null_zero" and group == "package/data":
                right_rows = [("x", 0), ("x", 0)]
            elif scenario == "duplicate" and group == "package/data":
                right_rows = [("x", 0)]
            elif scenario == "column_order" and group == "package/data":
                right_schema = [("value", "BIGINT"), ("item", "VARCHAR")]
                right_rows = [(None, "x"), (0, "x")]
            elif scenario == "schema_difference" and group == "package/data":
                right_schema = [("item", "VARCHAR"), ("other", "BIGINT")]
            elif scenario == "timestamp_equivalent" and group == "package/data":
                left_schema = [("item", "VARCHAR"), ("at", "TIMESTAMP")]
                right_schema = [("item", "VARCHAR"), ("at", "TIMESTAMP WITH TIME ZONE")]
                left_rows = [("x", "2026-01-02 03:04:05")]
                right_rows = [("x", "2026-01-02 03:04:05+00:00")]
        write_parquet(baseline_root / group / "part.parquet", left_schema, left_rows)
        write_parquet(spark_root / group / "part.parquet", right_schema, right_rows)
    base = {"status": "COMPUTED", "input_identity": "same-input", "code_sha256": "same-code",
            "stages": {"package_version": {"output": str(baseline_root)}}}
    candidate = {**base, "stages": {"package_version": {"output": str(spark_root)}}}
    return base, candidate


class BoundedComparatorTests(unittest.TestCase):
    def run_comparison(self, scenario):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        base, spark = make_reports(root, scenario=scenario)
        bounded = compare(base, spark, root / "bounded")
        legacy = old_compare(base, spark, root / "legacy")
        self.assertEqual(bounded["status"], legacy["status"])
        self.assertEqual({key: value["equal"] for key, value in bounded["groups"].items()},
                         {key: value["equal"] for key, value in legacy["groups"].items()})
        return bounded

    def test_object_key_order_and_column_order_are_normalized(self):
        result = self.run_comparison("column_order")
        self.assertEqual(result["status"], "EQUAL")
        self.assertTrue(result["bounded_group_processing"])

    def test_null_zero_and_duplicate_multiplicity_are_preserved(self):
        null_zero = self.run_comparison("null_zero")
        duplicate = self.run_comparison("duplicate")
        self.assertEqual(null_zero["status"], "DIFFERENT")
        self.assertEqual(duplicate["groups"]["package_version/package/data"]["baseline_only_rows"], 1)

    def test_json_array_order_remains_significant(self):
        result = self.run_comparison("array_difference")
        self.assertEqual(result["status"], "DIFFERENT")
        self.assertEqual(result["groups"]["package_version/version/data"]["baseline_only_rows"], 1)

    def test_schema_difference_is_reported_with_both_raw_row_counts(self):
        result = self.run_comparison("schema_difference")
        group = result["groups"]["package_version/package/data"]
        self.assertFalse(group["logical_schema_equal"])
        self.assertEqual([record["rows"] for record in group["outputs"]], [2, 2])

    def test_utc_timestamp_type_and_representation_are_normalized(self):
        self.assertEqual(self.run_comparison("timestamp_equivalent")["status"], "EQUAL")

    def test_status_input_code_and_stage_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, spark = make_reports(root)
            for patch, message in (({"status": "FAILED"}, "Both engines"),
                                   ({"input_identity": "different"}, "inputs differ"),
                                   ({"code_sha256": "different"}, "Source code changed"),
                                   ({"stages": {}}, "stage sets differ")):
                candidate = dict(spark, **patch)
                with self.assertRaisesRegex(ValueError, message):
                    compare(base, candidate, root / ("blocked-" + str(len(list(root.glob("blocked-*"))))))


if __name__ == "__main__":
    unittest.main()
