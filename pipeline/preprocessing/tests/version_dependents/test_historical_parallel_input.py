"""Checks for immutable physical input shards."""
import tempfile
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pipeline.preprocessing.tests.version_dependents.test_historical_production import prepared_fixture
from pipeline.preprocessing.version_dependents.historical_parallel_input import from_prepared, prepare, verify_inputs, verify_partition, open_partition, open_all
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256
import duckdb
from pipeline.preprocessing.tests.version_dependents.test_historical_production import fixture_tables


class ParallelInputTests(unittest.TestCase):
    def test_direct_prepare_reads_pinned_tables_and_matches_reference_rows(self):
        """Exercise direct H1/profile/raw views; no legacy prepare call is allowed."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); h1dir = root / "h1"; profiledir = root / "profile"; rawdir = root / "raw"
            h1dir.mkdir(); profiledir.mkdir(); rawdir.mkdir()
            with duckdb.connect() as con:
                fixture_tables(con)
                for table in ("source_population", "h1_targets"):
                    source = "source_population" if table == "source_population" else "h1_targets"
                    con.execute(f"COPY {source} TO ? (FORMAT PARQUET)", [str(h1dir / ("source_population.parquet" if table == "source_population" else "target_population.parquet"))])
                con.execute("COPY (SELECT * FROM (VALUES (0,'2026-01-01'::DATE,'2026-01-01T00:00:00Z'::TIMESTAMPTZ),(1,'2026-02-01'::DATE,'2026-02-01T00:00:00Z'::TIMESTAMPTZ),(2,'2026-03-01'::DATE,'2026-03-01T00:00:00Z'::TIMESTAMPTZ)) t(snapshot_index,snapshot_at,snapshot_timestamp)) TO ? (FORMAT PARQUET)", [str(h1dir / "calendar.parquet")])
                con.execute("COPY input_requirements TO ? (FORMAT PARQUET)", [str(rawdir / "requirements.parquet")])
                con.execute("COPY input_package TO ? (FORMAT PARQUET)", [str(rawdir / "package.parquet")])
                con.execute("COPY lookup_workload TO ? (FORMAT PARQUET)", [str(profiledir / "lookup_workload.parquet")])
                con.execute("COPY package_workload TO ? (FORMAT PARQUET)", [str(profiledir / "package_workload.parquet")])
            selection_csv = root / "selection.csv"; selection_csv.write_text("name\nb\nc\nempty\nghost\ngone\n", encoding="utf-8")
            selection_sha = file_sha256(selection_csv)
            h1 = {"observed_snapshot_timestamp": "2026-03-01T00:00:00Z"}
            raw = {"sources": {"requirements": str(rawdir / "requirements.parquet"), "package": str(rawdir / "package.parquet")},
                   "files": {"requirements": str(rawdir / "requirements.parquet"), "package": str(rawdir / "package.parquet")}}
            profile = {"profile_status": "COMPLETE"}
            with patch("pipeline.preprocessing.version_dependents.historical_parallel_input._inputs", return_value=(h1, raw)), \
                 patch("pipeline.preprocessing.version_dependents.historical_parallel_input._verify_profile", return_value=profile), \
                 patch("pipeline.preprocessing.version_dependents.historical_parallel_input._verify_used_raw", return_value=2), \
                 patch("pipeline.preprocessing.version_dependents.historical_parallel_input.verify_historical_inputs") as verify_h1:
                result = prepare(h1_dir=h1dir, h1_manifest_sha256="a" * 64,
                                 profile_manifest=profiledir / "profile.json", profile_manifest_sha256="b" * 64,
                                 selection_csv=selection_csv, selection_sha256=selection_sha,
                                 output=root / "direct", partition_count=4, full_selected=True, min_free_bytes=0)
            direct = verify_inputs(result["prepared_dir"], result["manifest_sha256"])
            self.assertIsNone(direct["selection"]["chosen_names"])
            self.assertEqual(direct["selection"]["chosen_count"], 5)
            self.assertEqual(direct["selection"]["unique_names_sha256"], sha256(sorted(["b", "c", "empty", "ghost", "gone"])))
            reference_dir = root / "reference"; reference_sha = prepared_fixture(reference_dir)
            with duckdb.connect() as con:
                open_all(con, root / "direct", direct)
                for table in ("target_names", "target_population", "lookups", "declarations"):
                    reference = con.execute("SELECT * FROM read_parquet(?) ORDER BY ALL", [str(reference_dir / (table + ".parquet"))]).fetchall()
                    actual = con.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()
                    self.assertEqual(actual, reference)
                    self.assertEqual(con.execute(f"SELECT count(*) FROM (SELECT * FROM {table} EXCEPT ALL SELECT * FROM read_parquet(?))", [str(reference_dir / (table + ".parquet"))]).fetchone()[0], 0)
                    self.assertEqual(con.execute(f"SELECT count(*) FROM (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM {table})", [str(reference_dir / (table + ".parquet"))]).fetchone()[0], 0)
            with duckdb.connect() as worker_con:
                open_partition(worker_con, root / "direct", direct, 0)
                self.assertEqual(worker_con.cursor().execute("SELECT count(*) FROM lookups").fetchone()[0], direct["partitions"]["000"]["rows"]["lookups"])

    def test_manifest_metadata_tamper_is_rejected_even_with_new_manifest_sha(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "source"; digest = prepared_fixture(source)
            result = from_prepared(prepared_dir=source, manifest_sha256=digest,
                                   output=root / "shards", min_free_bytes=0)
            path = root / "shards" / "input_manifest.json"
            original = json.loads(path.read_text(encoding="utf-8"))
            for mutation in ("names", "status", "path"):
                manifest = json.loads(json.dumps(original))
                part = manifest["partitions"]["000"]
                if mutation == "names":
                    part["names"] = part["names"] + ["forged"]
                elif mutation == "status":
                    part["status"] = "EMPTY" if part["status"] == "READY" else "READY"
                else:
                    part["files"]["target_names"]["name"] = "partition=000/../forged.parquet"
                manifest["files"] = {r["name"]: r for p in manifest["partitions"].values() for r in p["files"].values()}
                path.write_text(json.dumps(manifest), encoding="utf-8")
                forged_sha = file_sha256(path)
                with self.assertRaises(ValueError): verify_inputs(root / "shards", forged_sha)
            path.write_bytes(json.dumps(original).encode("utf-8"))
    def test_conversion_preserves_rows_and_partition_views(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "source"; digest = prepared_fixture(source)
            result = from_prepared(prepared_dir=source, manifest_sha256=digest,
                                   output=root / "shards", min_free_bytes=0)
            manifest = verify_inputs(result["prepared_dir"], result["manifest_sha256"])
            self.assertEqual(set(manifest["partitions"]), {"000", "001", "002", "003"})
            with duckdb.connect() as con:
                open_all(con, root / "shards", manifest)
                for table in ("target_names", "target_population", "lookups", "declarations"):
                    self.assertEqual(con.execute(f"select count(*) from {table}").fetchone()[0], manifest["rows"][table])
            with duckdb.connect() as worker_con:
                open_partition(worker_con, root / "shards", manifest, 0)
                self.assertTrue(worker_con.execute("select count(*) from target_names where partition_id<>0").fetchone()[0] == 0)

    def test_empty_partition_is_explicit_and_tamper_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "source"; digest = prepared_fixture(source)
            result = from_prepared(prepared_dir=source, manifest_sha256=digest,
                                   output=root / "shards", min_free_bytes=0)
            manifest = verify_inputs(result["prepared_dir"], result["manifest_sha256"])
            self.assertIn("EMPTY", [p["status"] for p in manifest["partitions"].values()])
            path = root / "shards" / "partition=000" / "target_names.parquet"
            path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaises(ValueError): verify_inputs(root / "shards", result["manifest_sha256"])

    def test_partition_manifest_uses_root_relative_file_names(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "source"; digest = prepared_fixture(source)
            result = from_prepared(prepared_dir=source, manifest_sha256=digest,
                                   output=root / "shards", min_free_bytes=0)
            manifest = verify_inputs(result["prepared_dir"], result["manifest_sha256"])
            for part in manifest["partitions"].values():
                for record in part["files"].values():
                    self.assertTrue(record["name"].startswith("partition="))
            verify_partition(root / "shards", manifest, 0)


if __name__ == "__main__":
    unittest.main()
