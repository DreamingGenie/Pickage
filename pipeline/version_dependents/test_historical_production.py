"""Integration checks for the production path using explicitly synthetic input."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical_artifact import _publish_json
from .historical_cache import _record
from .historical_production import _check_cache_derivation, _check_output_path, batches, run, verify_run
from .historical_production_input import (FORMAT, POLICY, TABLES, contract, partition_for,
                                         prepare_tables, selection, verify_inputs)


def fixture_tables(con):
    con.execute("""CREATE TABLE source_population AS SELECT * FROM (VALUES
      (10,'source-a','1.0.0',0,false),(10,'source-a','2.0.0',1,false),
      (30,'source-c','1.0.0',0,false),(40,'outside-list','1.0.0',2,false))
      s(source_package_id,source_name,source_version,birth_index,dependency_error)""")
    rows = [
        {"Name": "source-a", "Version": "1.0.0", "Dependencies": [
            {"Name": "b", "Requirement": "^1.0.0"}, {"Name": "b", "Requirement": ">=1.0.0"},
            {"Name": "c", "Requirement": "^2.0.0"}]},
        {"Name": "source-a", "Version": "2.0.0", "Dependencies": [{"Name": "b", "Requirement": "^1.0.0"}]},
        {"Name": "source-c", "Version": "1.0.0", "Dependencies": [{"Name": "b", "Requirement": "1.0.0"}]},
        {"Name": "outside-list", "Version": "1.0.0", "Dependencies": [
            {"Name": "b", "Requirement": "workspace:*"}, {"Name": "b", "Requirement": None},
            {"Name": "ghost", "Requirement": "1.0.0"}]},
    ]
    con.execute("CREATE TABLE input_requirements AS SELECT unnest(from_json(?,?),recursive:=true)",
                [json.dumps(rows), '[{"Name":"VARCHAR","Version":"VARCHAR",'
                                  '"Dependencies":[{"Name":"VARCHAR","Requirement":"VARCHAR"}]}]'])
    con.execute("""CREATE TABLE h1_targets AS SELECT * FROM (VALUES
        (20,'b','1.0.0',0),(20,'b','1.2.0',2),(21,'c','2.0.0',0),(22,'empty','1.0.0',1))
        t(package_id,name,version,birth_index)""")
    con.execute("CREATE TABLE input_package AS SELECT * FROM (VALUES (20,'b'),(21,'c'),(22,'empty'),(23,'gone')) p(package_id,name)")
    con.execute("""CREATE TABLE lookup_workload AS WITH expanded AS (
        SELECT item.Name AS declared_name,item.Requirement AS requirement,s.birth_index
        FROM input_requirements r JOIN source_population s
          ON r.Name=s.source_name AND r.Version=s.source_version,
        UNNEST(r.Dependencies) AS u(item)
      ) SELECT row_number() OVER (ORDER BY declared_name,requirement NULLS FIRST)::BIGINT AS lookup_id,
          declared_name,requirement,count(*)::BIGINT AS declaration_count,
          min(birth_index)::INTEGER AS first_source_birth
        FROM expanded GROUP BY declared_name,requirement""")
    con.execute("""CREATE TABLE package_workload AS
        WITH names AS (SELECT name FROM input_package UNION SELECT declared_name FROM lookup_workload),
        c AS (SELECT name,count(*)::BIGINT candidate_count FROM h1_targets GROUP BY name),
        l AS (SELECT declared_name AS name,count(*)::BIGINT lookup_count,
                     sum(declaration_count)::BIGINT declaration_count FROM lookup_workload GROUP BY 1)
        SELECT n.name,coalesce(c.candidate_count,0)::BIGINT candidate_count,
               coalesce(l.lookup_count,0)::BIGINT lookup_count,
               coalesce(l.declaration_count,0)::BIGINT declaration_count
        FROM names n LEFT JOIN c USING(name) LEFT JOIN l USING(name)""")


def prepared_fixture(root, *, scope="SAMPLE"):
    root.mkdir()
    names = ["b", "c", "empty", "ghost", "gone"]
    with duckdb.connect() as con:
        fixture_tables(con)
        rows = prepare_tables(con, names, partition_count=4)
        for table in TABLES:
            con.execute(f"COPY {table} TO ? (FORMAT PARQUET)", [str(root / (table + ".parquet"))])
    calendar = [{"snapshot_at": f"2026-0{m}-01", "snapshot_timestamp": f"2026-0{m}-01T00:00:00.000000Z"}
                for m in (1, 2, 3)]
    plan = {"format": FORMAT, "scope": scope, "policy": POLICY,
            "generation_contract": contract(), "selection": {"chosen_count": len(names),
                "chosen_names": names, "chosen_names_sha256": sha256(names)},
            "partition_count": 4, "ready_for_load": False, "test_fixture": True}
    _publish_json(root / "input_plan.json", plan)
    manifest = {**plan, "preparation_status": "COMPLETE", "count_status": "NOT_COMPUTED",
                "calendar": calendar, "observed_snapshot_timestamp": calendar[-1]["snapshot_timestamp"],
                "input_plan_sha256": file_sha256(root / "input_plan.json"), "rows": rows,
                "files": [_record(root / (name + ".parquet")) for name in TABLES]}
    _publish_json(root / "input_manifest.json", manifest)
    return file_sha256(root / "input_manifest.json")


class ProductionTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows filename limit")
    def test_rejects_long_output_before_writing(self):
        with self.assertRaisesRegex(ValueError, "short run path"):
            _check_output_path(Path("C:/") / ("a" * 100))
        _check_output_path(Path("C:/vd/run"))

    def test_selection_deduplicates_and_rejects_implicit_full(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected.csv"
            path.write_text("name\nb\nb\nc\n", encoding="utf-8")
            digest = file_sha256(path)
            names, record = selection(path, digest, sample_names=["b"])
            self.assertEqual(names, ["b"])
            self.assertEqual((record["csv_rows"], record["unique_names"]), (3, 2))
            with self.assertRaises(ValueError): selection(path, digest)
            with self.assertRaises(ValueError): selection(path, digest, sample_names=[])
            with self.assertRaises(ValueError): selection(path, digest, sample_names=["outside"])
            self.assertEqual(selection(path, digest, full_selected=True)[0], ["b", "c"])

    def test_input_adapter_conserves_original_declarations(self):
        with duckdb.connect() as con:
            fixture_tables(con)
            counts = prepare_tables(con, ["b", "c", "empty", "ghost", "gone"], partition_count=4)
            self.assertEqual(counts["declarations"], 8)
            self.assertEqual(con.execute("SELECT count(DISTINCT source_package_id) FROM declarations").fetchone()[0], 3)
            self.assertEqual(con.execute("SELECT known_package FROM target_names WHERE name='gone'").fetchone()[0], True)
            self.assertEqual(con.execute("SELECT known_package FROM target_names WHERE name='ghost'").fetchone()[0], False)
            self.assertEqual(con.execute("SELECT max(original_declaration_index) FROM declarations WHERE source_package_id=10").fetchone()[0], 2)
        with duckdb.connect() as con:
            fixture_tables(con)
            con.execute("UPDATE lookup_workload SET declaration_count=declaration_count+1")
            with self.assertRaisesRegex(ValueError, "conserve"):
                prepare_tables(con, ["b"], partition_count=2)

    def test_run_partition_and_date_resume_then_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); inputs = root / "inputs"; digest = prepared_fixture(inputs)
            args = dict(prepared_dir=inputs, manifest_sha256=digest, output=root / "run", min_free_bytes=0)
            first = run(**args, max_partitions=1)
            self.assertEqual(first["run_status"], "INCOMPLETE")
            self.assertFalse(first["full_selection_executed"])
            pointer = next((root / "run" / "partitions").glob("*/complete.json"))
            pointer_bytes = pointer.read_bytes()
            second = run(**args, resume=True, max_snapshots=1)
            self.assertEqual(second["run_status"], "INCOMPLETE")
            self.assertFalse(second["full_selection_executed"])
            self.assertTrue(second["reused_partitions"])
            self.assertEqual(pointer.read_bytes(), pointer_bytes)
            result = run(**args, resume=True)
            self.assertEqual(result["run_status"], "COMPLETE")
            self.assertFalse(result["full_selection_executed"])
            verified = verify_run(run_dir=root / "run", manifest_sha256=result["run_manifest_sha256"])
            self.assertEqual(verified["snapshots"], 3)
            with duckdb.connect() as con:
                counts = con.execute("SELECT package_id,version,dependents_count FROM read_parquet(?) WHERE start_index<=2 AND 2<end_index ORDER BY 1,2",
                                     [str(Path(result["cache_dir"]) / "count_intervals.parquet")]).fetchall()
                self.assertEqual(counts, [(20, "1.0.0", 1), (20, "1.2.0", 2), (21, "2.0.0", 1)])
            again = run(**args, resume=True)
            self.assertEqual(again["run_manifest_sha256"], result["run_manifest_sha256"])
            self.assertEqual(again["written_partitions"], [])
            pointer = root / "run" / "cache_complete.json"
            saved = json.loads(pointer.read_bytes())
            pointer.write_text(json.dumps({**saved, "cache_sha256": "0" * 64}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "completion pointer"):
                verify_run(run_dir=root / "run", manifest_sha256=result["run_manifest_sha256"])

    def test_cache_values_must_equal_partition_values(self):
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            con.execute("CREATE TABLE history_count_intervals AS SELECT 1::INTEGER AS package_id,'1.0.0' AS version,0::INTEGER AS start_index,1::INTEGER AS end_index,2::BIGINT AS dependents_count")
            con.execute("CREATE TABLE history_target_population AS SELECT 1::INTEGER AS package_id,'1.0.0' AS version,0::INTEGER AS birth_index")
            con.execute("CREATE TABLE history_quality AS SELECT 0::INTEGER snapshot_index,'{}' quality_json")
            for name in ("count_intervals", "target_population", "quality"):
                con.execute(f"COPY history_{name} TO ? (FORMAT PARQUET)", [str(root / (name + '.parquet'))])
            _check_cache_derivation(con, root)
            con.execute("UPDATE history_count_intervals SET dependents_count=3")
            with self.assertRaisesRegex(ValueError, "partition-derived count_intervals"):
                _check_cache_derivation(con, root)

    def test_full_scope_needs_explicit_option(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); digest = prepared_fixture(root / "inputs", scope="FULL_SELECTED")
            with self.assertRaisesRegex(ValueError, "explicit"):
                run(prepared_dir=root / "inputs", manifest_sha256=digest, output=root / "run")
            self.assertFalse((root / "run").exists())

    def test_input_and_checkpoint_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); digest = prepared_fixture(root / "inputs")
            args = dict(prepared_dir=root / "inputs", manifest_sha256=digest, output=root / "run", min_free_bytes=0)
            run(**args, max_partitions=1)
            pointer = next((root / "run" / "partitions").glob("*/complete.json"))
            record = json.loads(pointer.read_bytes())
            receipt = pointer.parent / record["attempt"] / "receipt.json"
            receipt.write_bytes(receipt.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "receipt SHA"):
                run(**args, resume=True)
            file = root / "inputs" / "declarations.parquet"
            file.write_bytes(file.read_bytes() + b"changed")
            with self.assertRaises(ValueError): verify_inputs(root / "inputs", digest)

    def test_worker_batch_respects_heavy_package_bounds(self):
        bounds = {"max_candidates": 100000, "max_snapshots": 4096, "max_unique_requirements": 512,
                  "max_candidate_requirement_work": 2000000, "max_result_intervals": 20000,
                  "max_frame_bytes": 7 * 1024 * 1024}
        candidates = [{"version": f"1.0.{i}", "birth_index": 0} for i in range(33966)]
        messages = list(batches("b", candidates, [(i, f">=1.0.{i}") for i in range(59)],
                               known_package=True, snapshot_count=229, bounds=bounds))
        self.assertGreater(len(messages), 1)
        self.assertEqual(sum(len(items) for items, _ in messages), 59)
        for items, message in messages:
            self.assertLessEqual(len(items) * len(candidates), 2000000)
            self.assertLessEqual(len(items) * 229, 20000)
            self.assertEqual(message["candidates"], candidates)


if __name__ == "__main__":
    unittest.main()
