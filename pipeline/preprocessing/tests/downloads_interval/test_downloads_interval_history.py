import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from pipeline.preprocessing.downloads_interval.input import _selected_daily
from pipeline.preprocessing.downloads_interval import input as loader
from pipeline.preprocessing.downloads_interval.aggregate import aggregate
from pipeline.preprocessing.tests.downloads_interval.test_input import InputFixture, _put, _sha


class DownloadHistorySelectionTests(unittest.TestCase):
    @staticmethod
    def _args(fixture, root):
        return dict(snapshot=fixture.snapshot, bronze_run_id=fixture.bronze_run_id,
                    bronze_manifest_sha256=fixture.bronze_sha,
                    curated_run_id=fixture.curated_run_id,
                    curated_manifest_sha256=fixture.curated_sha,
                    candidate_path=root / "candidate.json", candidate_sha256="c" * 64,
                    cache_dir=root / "cache", workers=2)
    def test_same_date_files_are_retained_for_row_level_resolution(self):
        rows = [
            {"role": "daily_parquet", "path": "parquet/downloads/date=2026-08-24/primary.parquet"},
            {"role": "daily_parquet", "path": "parquet/downloads/date=2026-08-24/history.parquet"},
            {"role": "daily_parquet", "path": "parquet/downloads/date=2026-08-25/outside.parquet"},
        ]
        selected = _selected_daily(rows, {"download_start_inclusive": "2026-08-24", "download_end_exclusive": "2026-08-25"})
        self.assertEqual([row["path"] for row in selected], [
            "parquet/downloads/date=2026-08-24/history.parquet",
            "parquet/downloads/date=2026-08-24/primary.parquet",
        ])

    def test_prepare_aggregate_revalidate_resolves_history_rows_and_derived_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "primary").mkdir()
            (root / "history").mkdir()
            primary = InputFixture(root / "primary")
            history = InputFixture(root / "history", bronze_run_id="bronze-history")

            # Add a history-only name to the primary status/target population.
            target = b"name\nalpha\nbeta\n"
            status_path = root / "status.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE s(name VARCHAR, status VARCHAR)")
                con.execute("INSERT INTO s VALUES ('alpha','READY'), ('beta','READY')")
                con.execute("COPY s TO ? (FORMAT PARQUET)", [str(status_path)])
            manifest = json.loads(primary.bronze_body)
            target_row = next(row for row in manifest["files"] if row["role"] == "target_csv")
            target_row.update(bytes=len(target), sha256=_sha(target), row_count=2)
            status_row = next(row for row in manifest["files"] if row["role"] == "status_parquet")
            status_body = status_path.read_bytes()
            status_row.update(bytes=len(status_body), sha256=_sha(status_body), row_count=2)
            _put(primary.s3, "pickage-raw", primary.bronze_prefix + "/data/target.csv", target)
            _put(primary.s3, "pickage-raw", primary.bronze_prefix + "/data/status.parquet", status_body)
            primary.bronze_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            primary.bronze_sha = _sha(primary.bronze_body)
            _put(primary.s3, "pickage-raw", primary.bronze_prefix + "/run_manifest.json", primary.bronze_body)
            _put(primary.s3, "pickage-raw", primary.bronze_prefix + "/_SUCCESS", (primary.bronze_sha + "\n").encode())
            _put(primary.s3, "pickage-raw", primary.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": primary.bronze_sha}).encode())

            # History has the same name/date with a conflicting value and beta only.
            hmanifest = json.loads(history.bronze_body)
            daily = next(row for row in hmanifest["files"] if row["role"] == "daily_parquet")
            daily["path"] = "parquet/downloads/date=2026-08-24/aaa.parquet"
            history_file = root / "history-daily.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE d(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN)")
                con.execute("INSERT INTO d VALUES ('alpha',99,false),('beta',7,false)")
                con.execute("COPY d TO ? (FORMAT PARQUET)", [str(history_file)])
            history_body = history_file.read_bytes()
            daily.update(bytes=len(history_body), sha256=_sha(history_body), row_count=2,
                         min_date="2026-08-24", max_date="2026-08-24")
            old_path = "parquet/downloads/date=2026-08-24/part.parquet"
            history.s3.objects.pop(("pickage-raw", history.bronze_prefix + "/data/" + old_path))
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/data/" + daily["path"], history_body)
            hmanifest["files"] = [daily if row["role"] == "daily_parquet" else row for row in hmanifest["files"]]
            history.bronze_body = json.dumps(hmanifest, sort_keys=True, separators=(",", ":")).encode()
            history.bronze_sha = _sha(history.bronze_body)
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/run_manifest.json", history.bronze_body)
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/_SUCCESS", (history.bronze_sha + "\n").encode())
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": history.bronze_sha}).encode())

            # Share the history receipt with the primary fake S3 namespace.
            for (bucket, key), body in history.s3.objects.items():
                if bucket == "pickage-raw": _put(primary.s3, bucket, key, body)
            args = dict(snapshot=primary.snapshot, bronze_run_id=primary.bronze_run_id,
                        bronze_manifest_sha256=primary.bronze_sha,
                        curated_run_id=primary.curated_run_id,
                        curated_manifest_sha256=primary.curated_sha,
                        candidate_path=root / "candidate.json", candidate_sha256="c" * 64,
                        cache_dir=root / "cache", workers=2)
            with patch.object(loader, "read_candidate", return_value=primary.candidate):
                prepared = loader.prepare(primary.s3, **args, additional_bronze_refs=[
                    {"run_id": history.bronze_run_id, "manifest_sha256": history.bronze_sha}])
            prepared["lineage"]["aggregation_policy_sha256"] = "a" * 64
            result = aggregate(prepared, root / "aggregate")
            self.assertIn("duplicate_rows", prepared["input_manifest"]["history"])
            self.assertEqual(prepared["input_manifest"]["history"]["conflicts"][0]["reason"], "VALUE_CONFLICT")
            self.assertEqual(result["files"][0]["row_count"], 1)
            with patch.object(loader, "read_candidate", return_value=primary.candidate):
                loader.revalidate(primary.s3, prepared)
            derived = Path(prepared["_cache_dir"]) / "bronze" / "derived/parquet/downloads/date=2026-08-24/merged.parquet"
            derived.write_bytes(derived.read_bytes() + b"x")
            with patch.object(loader, "read_candidate", return_value=primary.candidate), self.assertRaisesRegex(ValueError, "derived daily"):
                loader.revalidate(primary.s3, prepared)

    def test_history_only_target_is_silently_omitted_from_primary_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "primary").mkdir(); (root / "history").mkdir()
            primary = InputFixture(root / "primary")
            history = InputFixture(root / "history", bronze_run_id="bronze-history")
            hmanifest = json.loads(history.bronze_body)
            target = next(row for row in hmanifest["files"] if row["role"] == "target_csv")
            body = b"name\nhistory-only\n"
            target.update(bytes=len(body), sha256=_sha(body), row_count=1)
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/data/target.csv", body)
            history.bronze_body = json.dumps(hmanifest, sort_keys=True, separators=(",", ":")).encode(); history.bronze_sha = _sha(history.bronze_body)
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/run_manifest.json", history.bronze_body)
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/_SUCCESS", (history.bronze_sha + "\n").encode())
            _put(history.s3, "pickage-raw", history.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": history.bronze_sha}).encode())
            for (bucket, key), value in history.s3.objects.items():
                if bucket == "pickage-raw": _put(primary.s3, bucket, key, value)
            with patch.object(loader, "read_candidate", return_value=primary.candidate):
                prepared = loader.prepare(primary.s3, **self._args(primary, root), additional_bronze_refs=[{"run_id": history.bronze_run_id, "manifest_sha256": history.bronze_sha}])
            # History target/status receipts are not consumed at all; this is
            # current behavior and documents the missing validation boundary.
            self.assertEqual(Path(prepared["target_file"]).read_text(), "name\nalpha\n")
            self.assertEqual(prepared["input_manifest"]["history"]["unconsumed_history_target_csv_rows"], 1)

    def test_same_bronze_source_duplicate_name_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); root.mkdir(exist_ok=True)
            fixture = InputFixture(root)
            manifest = json.loads(fixture.bronze_body)
            daily = next(row for row in manifest["files"] if row["role"] == "daily_parquet")
            duplicate = daily | {"path": "parquet/downloads/date=2026-08-24/duplicate.parquet"}
            manifest["files"].append(duplicate)
            duplicate_body = fixture.s3.objects[("pickage-raw", fixture.bronze_prefix + "/data/" + daily["path"])]
            duplicate.update(bytes=len(duplicate_body), sha256=_sha(duplicate_body))
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/data/" + duplicate["path"], duplicate_body)
            fixture.bronze_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); fixture.bronze_sha = _sha(fixture.bronze_body)
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/run_manifest.json", fixture.bronze_body)
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/_SUCCESS", (fixture.bronze_sha + "\n").encode())
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": fixture.bronze_sha}).encode())
            with patch.object(loader, "read_candidate", return_value=fixture.candidate), self.assertRaisesRegex(ValueError, "duplicate daily"):
                loader.prepare(fixture.s3, **self._args(fixture, root))

    def test_physical_date_mismatch_is_rejected_before_merge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fixture = InputFixture(root)
            daily = next(row for row in json.loads(fixture.bronze_body)["files"] if row["role"] == "daily_parquet")
            bad = root / "bad.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE d(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN, date DATE)")
                con.execute("INSERT INTO d VALUES ('alpha',10,false,DATE '2026-08-25')")
                con.execute("COPY d TO ? (FORMAT PARQUET)", [str(bad)])
            body = bad.read_bytes(); daily.update(bytes=len(body), sha256=_sha(body))
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/data/" + daily["path"], body)
            manifest = json.loads(fixture.bronze_body); manifest["files"] = [daily if row["role"] == "daily_parquet" else row for row in manifest["files"]]
            fixture.bronze_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); fixture.bronze_sha = _sha(fixture.bronze_body)
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/run_manifest.json", fixture.bronze_body)
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/_SUCCESS", (fixture.bronze_sha + "\n").encode())
            _put(fixture.s3, "pickage-raw", fixture.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": fixture.bronze_sha}).encode())
            with patch.object(loader, "read_candidate", return_value=fixture.candidate), self.assertRaisesRegex(ValueError, "physical date"):
                loader.prepare(fixture.s3, **self._args(fixture, root))


if __name__ == "__main__":
    unittest.main()
