"""Orchestration-facing checks for the bounded CPU dependents runner.

These tests deliberately execute real spawned worker processes.  The
orchestration adapter must preserve the weighted production result while
keeping the configured memory and worker budgets total, rather than applying
the budget once per worker.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import duckdb
from pipeline.preprocessing.experiments.dependents.historical_parallel_benchmark import compare_runs
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.orchestration.dependents import calculate as sequential_calculate
from pipeline.preprocessing.orchestration.dependents_parallel import (
    _load_weekly_views, _prepare_tables, calculate as parallel_calculate)
from pipeline.preprocessing.version_dependents import historical_parallel as parallel
from pipeline.preprocessing.version_dependents.historical_parallel_input import from_prepared
from pipeline.preprocessing.tests.version_dependents.test_historical_production import prepared_fixture


def _short_temp_dir(prefix):
    return tempfile.mkdtemp(prefix=prefix, dir="C:/" if os.name == "nt" else None)


def _parquet(path, schema, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE fixture ({schema})")
        if rows:
            con.executemany("INSERT INTO fixture VALUES (" + ",".join("?" for _ in rows[0]) + ")", rows)
        con.execute("COPY fixture TO ? (FORMAT PARQUET)", [str(path)])
    return path


def _weekly_files(root):
    root = Path(root)
    snapshot = "2026-08-31"
    stamp = snapshot + "T21:00:00Z"
    packages = [(10, "app"), (20, "lib"), (30, "zero")]
    versions = [(10, "0.9.0", "2020-01-01"), (10, "1.0.0", "2021-01-01"),
                (20, "1.0.0", "2020-01-01"), (30, "1.0.0", "2020-01-01")]
    names = dict(packages)
    files = {
        "package": [_parquet(root / "package.parquet", "package_id INTEGER,name VARCHAR", packages)],
        "version": [_parquet(root / "version.parquet", "package_id INTEGER,version VARCHAR,published_at TIMESTAMP", versions)],
        "versions_full": [_parquet(root / "versions_full.parquet",
            "Name VARCHAR,Version VARCHAR,published_at TIMESTAMP,is_release BOOLEAN,SnapshotAt TIMESTAMP",
            [(names[pid], version, published, True, stamp) for pid, version, published in versions])],
        "requirements": [_parquet(root / "requirements.parquet",
            "Name VARCHAR,Version VARCHAR,Dependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],PeerDependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],OptionalDependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],SnapshotAt TIMESTAMP",
            [(names[pid], version,
              None if pid == 10 and version == "0.9.0" else
              ([{"Name": "ghost", "Requirement": "*"}, {"Name": "lib", "Requirement": "^1"},
                {"Name": "lib", "Requirement": "^1"}, {"Name": "lib", "Requirement": "workspace:*"}] if pid == 10 else []),
              [], [], stamp)
             for pid, version, _ in versions])],
        "targets": _parquet(root / "targets.parquet", "name VARCHAR", [("lib",), ("zero",)]),
    }
    return files, snapshot, stamp


def _empty_weekly_files(root):
    files, snapshot, stamp = _weekly_files(root)
    names = {10: "app", 20: "lib", 30: "zero"}
    versions = [(10, "0.9.0", "2020-01-01"), (10, "1.0.0", "2021-01-01"),
                (20, "1.0.0", "2020-01-01"), (30, "1.0.0", "2020-01-01")]
    _parquet(root / "versions_full.parquet",
             "Name VARCHAR,Version VARCHAR,published_at TIMESTAMP,is_release BOOLEAN,SnapshotAt TIMESTAMP",
             [(names[pid], version, published, True, stamp) for pid, version, published in versions])
    _parquet(root / "requirements.parquet",
             "Name VARCHAR,Version VARCHAR,Dependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],PeerDependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],OptionalDependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],SnapshotAt TIMESTAMP",
             [(names[pid], version, [], [], [], stamp) for pid, version, _ in versions])
    _parquet(root / "targets.parquet", "name VARCHAR", [("ghost",)])
    return files, snapshot, stamp


class ParallelDependentsOrchestrationTests(unittest.TestCase):
    """Use a small prepared fixture as the exact legacy oracle."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="orchestration-parallel-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source_sha = prepared_fixture(self.source)
        self.shards = self.root / "shards"
        self.sharded = from_prepared(
            prepared_dir=self.source,
            manifest_sha256=self.source_sha,
            output=self.shards,
            threads=2,
            memory_limit="512MB",
            max_temp_size="2GB",
            min_free_bytes=0,
        )
        self.oracle = self.root / "oracle"
        parallel.old.run(
            prepared_dir=self.source,
            manifest_sha256=self.source_sha,
            output=self.oracle,
            algorithm=parallel.old.WEIGHTED_ALGORITHM,
            resolver_backend="cpu",
            threads=1,
            memory_limit="512MB",
            max_temp_size="2GB",
            min_free_bytes=0,
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_parallel(self, name, **options):
        return parallel.run(
            prepared_dir=self.shards,
            manifest_sha256=self.sharded["manifest_sha256"],
            output=self.root / name,
            workers=2,
            threads=2,
            memory_limit="4GB",
            max_temp_size="8GB",
            min_free_bytes=0,
            rss_limit_bytes=8 * 1024**3,
            scratch_limit_bytes=4 * 1024**3,
            **options,
        )

    def assert_exact_oracle(self, name, result):
        self.assertEqual(result["run_status"], "COMPLETE")
        self.assertFalse(result["ready_for_load"])
        verified = parallel.verify_run(
            run_dir=self.root / name,
            manifest_sha256=result["run_manifest_sha256"],
        )
        self.assertTrue(verified["verified"])
        groups = compare_runs(self.oracle, self.root / name)
        self.assertEqual(len(groups), 13)
        self.assertTrue(all(group["equal"] for group in groups.values()))

    def test_parallel_path_matches_oracle_with_total_four_gb_budget(self):
        result = self.run_parallel("complete")
        self.assert_exact_oracle("complete", result)
        execution = next((self.root / "complete").glob("execution-*.json"))
        execution_body = json.loads(execution.read_bytes())
        self.assertEqual(execution_body["workers"], 2)
        self.assertEqual(execution_body["worker_settings"]["threads"], 1)
        self.assertEqual(execution_body["worker_settings"]["memory_limit"], "2000MB")
        self.assertEqual(execution_body["worker_settings"]["max_temp_size"], "4000MB")

    def test_resume_reuses_receipt_and_rejects_corrupted_reference(self):
        partial = self.run_parallel("resume", max_partitions=1)
        self.assertEqual(partial["run_status"], "INCOMPLETE")
        self.assertEqual(len(partial["written_partitions"]), 1)
        pointer = next((self.root / "resume" / "partitions").glob("*/complete.json"))
        pointer_bytes = pointer.read_bytes()

        completed = self.run_parallel("resume", resume=True)
        self.assertIn(partial["written_partitions"][0], completed["reused_partitions"])
        self.assertEqual(pointer.read_bytes(), pointer_bytes)
        self.assert_exact_oracle("resume", completed)

        receipt = next((self.root / "resume").glob("partitions/*/attempts/*/receipt.json"))
        receipt.write_bytes(receipt.read_bytes() + b" tampered")
        with self.assertRaisesRegex(ValueError, "receipt SHA"):
            self.run_parallel("resume", resume=True)

    def test_weekly_adapter_matches_sequential_three_outputs_with_two_threads(self):
        files, snapshot, stamp = _weekly_files(self.root / "weekly")
        sequential_dir = self.root / "sequential"
        with duckdb.connect(str(self.root / "sequential.duckdb"), config={"threads": 1, "memory_limit": "512MB"}) as con:
            sequential_output, _, sequential_quality = sequential_calculate(
                con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                output=sequential_dir,
            )
        # The production runner intentionally rejects deep Windows paths.  Use
        # a short, disposable root here just as the real short work-dir does.
        parallel_dir = Path(_short_temp_dir("pd-"))
        try:
            with duckdb.connect(str(parallel_dir / "parallel.duckdb"), config={"threads": 2, "memory_limit": "2GB"}) as con:
                parallel_output, _, quality = parallel_calculate(
                    con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                    output=parallel_dir, workers=2, threads=2,
                    memory_limit="2GB", max_temp_size="4GB",
                )
            parallel_values = {}
            for name in ("version_dependents.parquet", "quality.parquet", "resolution_lookup.parquet"):
                with duckdb.connect() as con:
                    parallel_values[name] = (
                        con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(parallel_output / name)]).fetchall(),
                        con.execute("SELECT * FROM read_parquet(?)", [str(parallel_output / name)]).fetchall(),
                    )
        finally:
            shutil.rmtree(parallel_dir, ignore_errors=True)
        self.assertEqual(quality["engine"], "historical_parallel_cpu_weighted")
        for key in ("resolution_status", "source_gaps", "unresolved_declarations"):
            self.assertEqual(quality[key], sequential_quality[key], key)
        for name in ("version_dependents.parquet", "quality.parquet", "resolution_lookup.parquet"):
            with duckdb.connect() as con:
                left = con.execute("SELECT * FROM read_parquet(?)", [str(sequential_output / name)]).fetchall()
                self.assertEqual(
                    con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(sequential_output / name)]).fetchall(),
                    parallel_values[name][0],
                    name,
                )
                self.assertEqual(sorted(left, key=repr), sorted(parallel_values[name][1], key=repr), name)

    def test_adapter_reuses_durable_partition_after_interruption_and_rejects_changed_input(self):
        files, snapshot, stamp = _weekly_files(self.root / "retry-weekly")
        output = Path(_short_temp_dir("pd-retry-"))
        try:
            original_checkpoint = parallel._checkpoint
            raised = {"value": False}

            def interrupt_after_first_accept(root, phase, **values):
                original_checkpoint(root, phase, **values)
                if phase == "ACCEPTED" and not raised["value"]:
                    raised["value"] = True
                    raise RuntimeError("injected adapter interruption")

            with patch.object(parallel, "_checkpoint", interrupt_after_first_accept):
                with self.assertRaisesRegex(RuntimeError, "injected adapter interruption"):
                    with duckdb.connect(config={"threads": 2, "memory_limit": "2GB"}) as con:
                        parallel_calculate(con, files=files, snapshot=snapshot,
                                           snapshot_timestamp=stamp, output=output,
                                           workers=2, threads=2, memory_limit="2GB",
                                           max_temp_size="4GB")

            pointers = list((output / "parallel-run" / "partitions").glob("*/complete.json"))
            self.assertGreaterEqual(len(pointers), 1)
            pointer_bytes = {path: path.read_bytes() for path in pointers}

            with duckdb.connect(config={"threads": 2, "memory_limit": "2GB"}) as con:
                _, _, quality = parallel_calculate(
                    con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                    output=output, workers=2, threads=2, memory_limit="2GB",
                    max_temp_size="4GB",
                )
            self.assertEqual(quality["engine"], "historical_parallel_cpu_weighted")
            for path, body in pointer_bytes.items():
                self.assertEqual(path.read_bytes(), body)

            changed = dict(files)
            changed_targets = self.root / "retry-weekly" / "targets-changed.parquet"
            _parquet(changed_targets, "name VARCHAR", [("lib",), ("app",)])
            changed["targets"] = changed_targets
            with self.assertRaisesRegex(ValueError, "identity"):
                with duckdb.connect(config={"threads": 2, "memory_limit": "2GB"}) as con:
                    parallel_calculate(
                        con, files=changed, snapshot=snapshot,
                        snapshot_timestamp=stamp, output=output,
                        workers=2, threads=2, memory_limit="2GB",
                        max_temp_size="4GB",
                    )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_adapter_matches_empty_release_and_dependency_population(self):
        files, snapshot, stamp = _empty_weekly_files(self.root / "empty-weekly")
        sequential_dir = self.root / "empty-sequential"
        with duckdb.connect(str(self.root / "empty-sequential.duckdb"), config={"threads": 1, "memory_limit": "512MB"}) as con:
            sequential_output, _, sequential_quality = sequential_calculate(
                con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                output=sequential_dir,
            )
        output = Path(_short_temp_dir("pd-empty-"))
        try:
            with duckdb.connect(config={"threads": 2, "memory_limit": "2GB"}) as con:
                parallel_output, _, parallel_quality = parallel_calculate(
                    con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                    output=output, workers=2, threads=2, memory_limit="2GB",
                    max_temp_size="4GB",
                )
            self.assertEqual(parallel_quality["engine"], "historical_parallel_cpu_weighted")
            self.assertEqual(parallel_quality["resolution_status"], sequential_quality["resolution_status"])
            self.assertEqual(parallel_quality["source_gaps"], sequential_quality["source_gaps"])
            self.assertEqual(parallel_quality["unresolved_declarations"], sequential_quality["unresolved_declarations"])
            for name in ("version_dependents.parquet", "quality.parquet", "resolution_lookup.parquet"):
                with duckdb.connect() as con:
                    left_schema = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(sequential_output / name)]).fetchall()
                    right_schema = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(parallel_output / name)]).fetchall()
                    left_rows = con.execute("SELECT * FROM read_parquet(?)", [str(sequential_output / name)]).fetchall()
                    right_rows = con.execute("SELECT * FROM read_parquet(?)", [str(parallel_output / name)]).fetchall()
                self.assertEqual(left_schema, right_schema, name)
                self.assertEqual(sorted(left_rows, key=repr), sorted(right_rows, key=repr), name)
            with duckdb.connect() as con:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM read_parquet(?) WHERE dependents_count IS NULL",
                                [str(parallel_output / "version_dependents.parquet")]).fetchone()[0],
                    4,
                )
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_weekly_adapter_preserves_oracle_under_constrained_duckdb_budget(self):
        files, snapshot, stamp = _weekly_files(self.root / "constrained-weekly")
        oracle_dir = self.root / "constrained-oracle"
        with duckdb.connect(config={"threads": 1, "memory_limit": "128MB"}) as con:
            oracle_output, _, oracle_quality = sequential_calculate(
                con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                output=oracle_dir)
        output = Path(_short_temp_dir("pd-constrained-"))
        try:
            with duckdb.connect(config={"threads": 2, "memory_limit": "128MB"}) as con:
                actual_output, _, actual_quality = parallel_calculate(
                    con, files=files, snapshot=snapshot, snapshot_timestamp=stamp,
                    output=output, workers=2, threads=2, memory_limit="128MB",
                    max_temp_size="256MB")
            self.assertEqual(actual_quality["resolution_status"], oracle_quality["resolution_status"])
            for name in ("version_dependents.parquet", "quality.parquet", "resolution_lookup.parquet"):
                with duckdb.connect() as con:
                    self.assertEqual(
                        sorted(con.execute("SELECT * FROM read_parquet(?)", [str(oracle_output / name)]).fetchall(), key=repr),
                        sorted(con.execute("SELECT * FROM read_parquet(?)", [str(actual_output / name)]).fetchall(), key=repr),
                        name)
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_selected_declaration_indices_preserve_original_positions(self):
        files, snapshot, stamp = _weekly_files(self.root / "index-contract")
        with duckdb.connect(config={"threads": 1, "memory_limit": "128MB"}) as con:
            _load_weekly_views(con, files)
            _prepare_tables(con, snapshot=snapshot, snapshot_timestamp=stamp,
                            output=self.root / "index-contract-out")
            rows = con.execute(
                "SELECT declared_name,original_declaration_index,requirement "
                "FROM declarations WHERE declared_name='lib' ORDER BY original_declaration_index,requirement"
            ).fetchall()
        self.assertEqual(rows, [("lib", 1, "^1"), ("lib", 2, "^1"), ("lib", 3, "workspace:*")])

    def test_non_release_raw_provenance_is_rejected_before_empty_publication(self):
        files, snapshot, stamp = _empty_weekly_files(self.root / "invalid-release")
        versions = [("app", "0.9.0", "2020-01-01", False, stamp),
                    ("app", "1.0.0", "2021-01-01", False, stamp),
                    ("lib", "1.0.0", "2020-01-01", False, stamp),
                    ("zero", "1.0.0", "2020-01-01", False, stamp)]
        _parquet(self.root / "invalid-release" / "versions_full.parquet",
                 "Name VARCHAR,Version VARCHAR,published_at TIMESTAMP,is_release BOOLEAN,SnapshotAt TIMESTAMP",
                 versions)
        with duckdb.connect(config={"threads": 1, "memory_limit": "512MB"}) as con:
            with self.assertRaisesRegex(ValueError, "lacks matching raw release"):
                sequential_calculate(con, files=files, snapshot=snapshot,
                                     snapshot_timestamp=stamp, output=self.root / "invalid-sequential")
        output = Path(_short_temp_dir("pd-invalid-"))
        try:
            with duckdb.connect(config={"threads": 2, "memory_limit": "2GB"}) as con:
                with self.assertRaisesRegex(ValueError, "lacks matching raw release"):
                    parallel_calculate(con, files=files, snapshot=snapshot,
                                       snapshot_timestamp=stamp, output=output,
                                       workers=2, threads=2, memory_limit="2GB",
                                       max_temp_size="4GB")
        finally:
            shutil.rmtree(output, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
