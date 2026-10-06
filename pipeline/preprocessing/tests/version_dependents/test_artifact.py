"""File lifecycle checks with synthetic, single-snapshot populations only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import duckdb

from pipeline.preprocessing.version_dependents.artifact import save_artifact, verify_artifact
from pipeline.preprocessing.tests.version_dependents.test_aggregate import setup, SNAPSHOT, STAMP


LINEAGE = [
    {"role": role, "run_id": "synthetic-v1", "manifest_sha256": "a" * 64,
     "policy_sha256": "b" * 64}
    for role in ("requirements_edges", "approved_sources", "approved_targets")
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dependents-'한글-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def connection(self, *, snapshot=SNAPSHOT, stamp=STAMP, empty=False):
        published = datetime(2020, 1, 1, tzinfo=timezone.utc)
        edges = [] if empty else [(1, "1.0.0", 10, "3.0.0"),
                                 (1, "2.0.0", 10, "3.0.0"),
                                 (1, "2.0.0", 10, "3.0.0"),
                                 (2, "1.0.0", 10, "3.0.0")]
        con = setup(edges, [(1, "1.0.0", published), (1, "2.0.0", published),
                            (2, "1.0.0", published)],
                    [(10, "3.0.0", published), (20, "1.0.0", published)])
        for table in ("requirements_edges", "approved_sources", "approved_targets"):
            con.execute(f"UPDATE {table} SET snapshot_at=?, snapshot_timestamp=?", [snapshot, stamp])
        self.addCleanup(con.close)
        return con

    def save(self, con=None, **overrides):
        args = dict(output_root=self.root, run_id="fixture-v1", expected_snapshot_at=SNAPSHOT,
                    snapshot_timestamp=STAMP, resolution_status="COMPLETE",
                    ready_for_dependents=True, input_lineage=LINEAGE)
        args.update(overrides)
        return save_artifact(con if con is not None else self.connection(), **args)

    def verify(self, result, **overrides):
        args = {"manifest_sha256": result["manifest_sha256"]}
        args.update(overrides)
        return verify_artifact(Path(result["run_dir"]), **args)

    def repin_manifest(self, result, mutate):
        path = Path(result["run_dir"]) / "run_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        mutate(manifest)
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return {**result, "manifest_sha256": digest(path)}

    def rewrite_parquet(self, result, filename, query):
        path = Path(result["run_dir"]) / filename
        with duckdb.connect() as con:
            con.execute("CREATE TABLE saved AS SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(path)])
            con.execute(query)
            new = path.with_suffix(".replacement")
            escaped = str(new).replace("'", "''")
            con.execute(f"COPY saved TO '{escaped}' (FORMAT PARQUET)")
            new.replace(path)
            schema = [list(row[:2]) for row in con.execute("DESCRIBE saved").fetchall()]
            rows = con.execute("SELECT count(*) FROM saved").fetchone()[0]

        def refresh(manifest):
            record = next(row for row in manifest["files"] if row["path"] == filename)
            record.update(bytes=path.stat().st_size, sha256=digest(path), rows=rows, schema=schema)
            record["schema_sha256"] = hashlib.sha256(
                json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        return self.repin_manifest(result, refresh)

    def test_round_trip_without_original_connection(self):
        con = self.connection()
        result = self.save(con)
        con.close()
        manifest = self.verify(result, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP)
        self.assertEqual(manifest["quality"], {
            "source_versions": 3, "input_edges": 4, "distinct_edges": 3,
            "duplicate_edges": 1, "target_versions": 2, "zero_target_versions": 1,
            "max_dependents_count": 3, "total_direct_dependents": 3,
        })
        self.assertFalse(manifest["ready_for_load"])
        self.assertEqual(manifest["input_verification"], "NOT_PERFORMED")
        self.assertEqual(manifest["verification_scope"], "LOCAL_ARTIFACT_ONLY")
        run = Path(result["run_dir"])
        self.assertFalse((run / "_SUCCESS").exists())
        self.assertEqual({r["path"] for r in manifest["files"]},
                         {"counts.parquet", "quality.parquet", "lineage.parquet"})
        with duckdb.connect() as saved:
            rows = saved.execute("SELECT package_id, version, dependents_count FROM read_parquet(?, hive_partitioning=false) ORDER BY package_id", [str(run / "counts.parquet")]).fetchall()
        self.assertEqual(rows, [(10, "3.0.0", 3), (20, "1.0.0", 0)])

    def test_different_snapshots_keep_different_counts(self):
        first = self.save()
        later_date = SNAPSHOT + timedelta(days=7)
        later_stamp = STAMP + timedelta(days=7)
        second = self.save(self.connection(snapshot=later_date, stamp=later_stamp, empty=True),
                           expected_snapshot_at=later_date, snapshot_timestamp=later_stamp)
        self.assertNotEqual(first["run_dir"], second["run_dir"])
        self.assertEqual(self.verify(first)["quality"]["total_direct_dependents"], 3)
        self.assertEqual(self.verify(second)["quality"]["total_direct_dependents"], 0)
        self.assertEqual(self.verify(second)["quality"]["zero_target_versions"], 2)
        with self.assertRaises(ValueError):
            self.verify(first, expected_snapshot_at=later_date)
        with self.assertRaises(ValueError):
            self.verify(first, snapshot_timestamp=STAMP + timedelta(microseconds=1))

    def test_partial_and_not_ready_create_no_artifact(self):
        for status, ready in (("PARTIAL", True), ("COMPLETE", False), ("COMPLETE", 1)):
            with self.subTest(status=status, ready=ready), self.assertRaises(ValueError):
                self.save(resolution_status=status, ready_for_dependents=ready)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_snapshot_mismatch_rejected(self):
        con = self.connection()
        con.execute("UPDATE requirements_edges SET snapshot_timestamp=snapshot_timestamp + INTERVAL 1 MICROSECOND")
        with self.assertRaises(ValueError):
            self.save(con)
        self.assertEqual(list(self.root.rglob("run_manifest.json")), [])

    def test_bigint_input_ids_are_saved_as_service_integers(self):
        con = self.connection()
        con.execute("ALTER TABLE approved_targets ALTER package_id TYPE BIGINT")
        result = self.save(con)
        manifest = self.verify(result)
        counts = next(row for row in manifest["files"] if row["path"] == "counts.parquet")
        self.assertIn(["package_id", "INTEGER"], counts["schema"])

    def test_microseconds_do_not_use_floating_point_epoch(self):
        stamp = datetime(2500, 8, 31, 12, 0, 0, 517131, tzinfo=timezone.utc)
        result = self.save(self.connection(snapshot=stamp.date(), stamp=stamp),
                           expected_snapshot_at=stamp.date(), snapshot_timestamp=stamp)
        self.verify(result, snapshot_timestamp=stamp)
        with self.assertRaises(ValueError):
            self.verify(result, snapshot_timestamp=stamp + timedelta(microseconds=1))

    def test_unsafe_run_id_and_incomplete_lineage_rejected(self):
        for run in ("../escape", "a/b", "a\\b", "", ".", "..", "a ", "a.", "CON"):
            with self.subTest(run=run), self.assertRaises(ValueError):
                self.save(run_id=run)
        for lineage in ([], LINEAGE[:2], [LINEAGE[0]] * 3,
                        [{**r, "manifest_sha256": "not-a-hash"} for r in LINEAGE]):
            with self.subTest(lineage=lineage), self.assertRaises(ValueError):
                self.save(input_lineage=lineage)

    def test_lineage_order_is_canonicalized(self):
        result = self.save(input_lineage=list(reversed(LINEAGE)))
        self.assertEqual(self.verify(result)["input_lineage"], LINEAGE)

    def test_existing_run_is_unchanged_and_reverification_is_read_only(self):
        first = self.save()
        run = Path(first["run_dir"])
        before = {p.name: (digest(p), p.stat().st_mtime_ns) for p in run.iterdir()}
        for attempt in ({}, {"input_lineage": [{**r, "run_id": "changed-v2"} for r in LINEAGE]}):
            with self.assertRaises((FileExistsError, ValueError)):
                self.save(**attempt)
        self.verify(first)
        self.verify(first)
        after = {p.name: (digest(p), p.stat().st_mtime_ns) for p in run.iterdir()}
        self.assertEqual(before, after)

    def test_manifest_sha_is_required_and_tampering_rejected(self):
        result = self.save()
        with self.assertRaises(ValueError):
            self.verify(result, manifest_sha256="0" * 64)
        path = Path(result["run_dir"]) / "run_manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.verify(result)

    def test_file_tamper_missing_and_extra_rejected(self):
        for mode in ("tamper", "missing", "extra"):
            result = self.save(run_id=mode)
            run = Path(result["run_dir"])
            if mode == "tamper":
                with (run / "counts.parquet").open("ab") as stream:
                    stream.write(b"changed")
            elif mode == "missing":
                (run / "lineage.parquet").unlink()
            else:
                shutil.copyfile(run / "counts.parquet", run / "unlisted.parquet")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.verify(result)

    def test_manifest_contract_cannot_claim_load_readiness(self):
        for key, value in (("ready_for_load", True), ("input_verification", "VERIFIED"),
                           ("resolution_status", "PARTIAL"), ("quality", {})):
            result = self.save(run_id=f"edit-{key}")
            result = self.repin_manifest(result, lambda m: m.update({key: value}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(result)

    def test_invalid_json_shapes_and_file_record_types_rejected(self):
        for index, value in enumerate(([], None, "wrong", {"files": [None]})):
            result = self.save(run_id=f"shape-{index}")
            path = Path(result["run_dir"]) / "run_manifest.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.verify(result, manifest_sha256=digest(path))
        result = self.save(run_id="row-bool")
        result = self.repin_manifest(result, lambda m: m["files"][2].update(rows=True))
        with self.assertRaises(ValueError):
            self.verify(result)

    def test_rehashed_bad_counts_still_rejected(self):
        for name, sql in (
            ("negative", "UPDATE saved SET dependents_count=-1"),
            ("null", "UPDATE saved SET dependents_count=NULL"),
            ("snapshot", "UPDATE saved SET snapshot_at=snapshot_at + 1"),
            ("instant", "UPDATE saved SET snapshot_timestamp=snapshot_timestamp + INTERVAL 1 MICROSECOND"),
            ("null-instant", "UPDATE saved SET snapshot_timestamp=NULL"),
            ("empty-version", "UPDATE saved SET version=''"),
            ("duplicate", "INSERT INTO saved SELECT * FROM saved LIMIT 1"),
            ("wrong-count", "UPDATE saved SET dependents_count=dependents_count+1"),
        ):
            result = self.save(run_id=name)
            result = self.rewrite_parquet(result, "counts.parquet", sql)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify(result)

    def test_rehashed_lineage_and_quality_disagreement_rejected(self):
        for file, sql in (
            ("lineage.parquet", "UPDATE saved SET upstream_run_id='invented-v1'"),
            ("quality.parquet", "UPDATE saved SET source_versions=source_versions+1"),
        ):
            result = self.save(run_id=file.split(".")[0])
            result = self.rewrite_parquet(result, file, sql)
            with self.subTest(file=file), self.assertRaises(ValueError):
                self.verify(result)

    def test_failure_during_copy_never_completes_artifact(self):
        con = self.connection()

        class FailSecondCopy:
            copies = 0

            def __getattr__(self, name):
                return getattr(con, name)

            def execute(self, sql, *args, **kwargs):
                if sql.lstrip().upper().startswith("COPY"):
                    self.copies += 1
                    if self.copies == 2:
                        raise RuntimeError("injected disk failure")
                return con.execute(sql, *args, **kwargs)

        with self.assertRaisesRegex(RuntimeError, "injected disk failure"):
            self.save(FailSecondCopy())
        self.assertFalse(list(self.root.rglob("run_manifest.json")))
        self.assertFalse(list(self.root.rglob("_SUCCESS")))
        self.assertEqual(con.execute("SELECT count(*) FROM requirements_edges").fetchone()[0], 4)
        with self.assertRaises((FileExistsError, ValueError)):
            self.save()
        self.verify(self.save(run_id="retry-v2"))

    def test_saved_content_is_checked_before_manifest_completion(self):
        con = self.connection()

        class CorruptResultBeforeCopy:
            def __getattr__(self, name):
                return getattr(con, name)

            def execute(self, sql, *args, **kwargs):
                if sql.lstrip().upper().startswith("COPY"):
                    con.execute("UPDATE version_dependents SET dependents_count=-1")
                return con.execute(sql, *args, **kwargs)

        with self.assertRaisesRegex(ValueError, "invalid counts rows"):
            self.save(CorruptResultBeforeCopy())
        self.assertFalse(list(self.root.rglob("run_manifest.json")))

    def test_manifest_rejects_invalid_snapshot_types_and_precision(self):
        for name, changes in (
            ("null-date", {"snapshot_at": None}),
            ("null-stamp", {"snapshot_timestamp": None}),
            ("submicrosecond", {"snapshot_timestamp": "2026-08-31T12:00:00.0000001Z"}),
            ("unlisted-field", {"published": True}),
        ):
            result = self.save(run_id=name)
            result = self.repin_manifest(result, lambda m: m.update(changes))
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify(result)

    def test_same_run_concurrent_writers_have_one_winner(self):
        def attempt(_):
            con = setup([], [(1, "1", date(2020, 1, 1))], [(10, "1", date(2020, 1, 1))])
            try:
                return self.save(con)
            except (FileExistsError, ValueError):
                return None
            finally:
                con.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        self.verify(winners[0])


if __name__ == "__main__":
    unittest.main()
