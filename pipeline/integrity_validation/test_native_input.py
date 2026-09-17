"""Small real Parquet integration tests for read boundaries and honest coverage."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.preprocessing.curated.storage import json_bytes
from .local_bundle import LocalMetadataStore, MAX_FILE_BYTES, relative_file
from .native_fixture import create_demo
from .native_input import inspect_bundle, main


class NativeInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = create_demo(Path(self.temp.name) / "bundle")
        self.request_path = self.root / "request.json"
        self.request = json.loads(self.request_path.read_bytes())

    def save_request(self):
        self.request_path.write_bytes(json_bytes(self.request))

    def repin(self, manifest):
        body = json_bytes(manifest)
        (self.root / "run_manifest.json").write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        self.request["manifest_sha256"] = digest
        (self.root / "_SUCCESS").write_bytes(json_bytes({"manifest_sha256": digest}))
        self.save_request()

    def change_sample(self, sql):
        record = json.loads((self.root / "run_manifest.json").read_bytes())
        path = self.root / "files/package.parquet"
        path.unlink()
        with duckdb.connect(":memory:", config={"threads": 1, "memory_limit": "128MB",
                                               "max_temp_directory_size": "0B"}) as con:
            con.execute("COPY (" + sql + ") TO ? (FORMAT PARQUET)", [str(path)])
        row = record["files"][0]
        row.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.repin(record)

    def test_complete_small_bundle_has_honest_scope_and_preserves_inputs(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file()}
        report = inspect_bundle(self.request_path)
        self.assertEqual(report["metadata_status"], "MATCH")
        self.assertTrue(report["synthetic_demo"])
        self.assertEqual(report["samples"]["status"], "MATCH")
        self.assertEqual(report["samples"]["rows"], 4)
        self.assertFalse(report["samples"]["row_values_checked"])
        self.assertFalse(report["ready_for_load"])
        self.assertFalse(report["task_09_complete"])
        self.assertFalse(report["producer_generation_contract_verified"])
        self.assertEqual(len(report["metadata_reads"]), 2)
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in self.root.rglob("*") if p.is_file()})

    def test_observed_unselected_quality_file_is_never_opened(self):
        root = create_demo(Path(self.temp.name) / "observed", "package-snapshot-observed")
        # Removing an unselected file demonstrates it is neither opened nor required.
        (root / "files/quality.parquet").unlink()
        report = inspect_bundle(root / "request.json")
        self.assertEqual(len(report["metadata_reads"]), 3)
        self.assertEqual(report["samples"]["coverage"]["quality"]["checked_files"], 0)
        self.assertFalse(report["samples"]["coverage"]["quality"]["all_role_files_selected"])

    def test_metadata_only_does_not_open_any_parquet(self):
        self.request["samples"] = []
        self.save_request()
        with patch("pipeline.integrity_validation.native_samples.read_bounded",
                   side_effect=AssertionError("must not read Parquet")):
            report = inspect_bundle(self.request_path)
        self.assertEqual(report["samples"]["status"], "NOT_RUN")

    def test_same_size_sample_tampering_rejected(self):
        path = self.root / "files/package.parquet"
        body = bytearray(path.read_bytes())
        body[12] ^= 1
        path.write_bytes(body)
        with self.assertRaisesRegex(ValueError, "SHA/size"):
            inspect_bundle(self.request_path)

    def test_wrong_schema_even_after_repinning_rejected(self):
        self.change_sample("SELECT i::BIGINT AS package_id, 'name'::VARCHAR AS name, NULL::VARCHAR AS repo_url FROM range(2) r(i)")
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            inspect_bundle(self.request_path)

    def test_wrong_footer_rows_even_after_repinning_rejected(self):
        self.change_sample("SELECT i::INTEGER AS package_id, 'name'::VARCHAR AS name, NULL::VARCHAR AS repo_url FROM range(3) r(i)")
        with self.assertRaisesRegex(ValueError, "row count"):
            inspect_bundle(self.request_path)

    def test_rows_without_per_file_count_still_match_full_role_total(self):
        self.change_sample("SELECT i::INTEGER AS package_id, 'name'::VARCHAR AS name, NULL::VARCHAR AS repo_url FROM range(3) r(i)")
        manifest = json.loads((self.root / "run_manifest.json").read_bytes())
        manifest["files"][0].pop("row_count")
        self.repin(manifest)
        with self.assertRaisesRegex(ValueError, "manifest total"):
            inspect_bundle(self.request_path)

    def test_compressed_file_exceeding_row_budget_rejected(self):
        self.change_sample("SELECT 1::INTEGER AS package_id, 'name'::VARCHAR AS name, NULL::VARCHAR AS repo_url FROM range(5001)")
        with self.assertRaisesRegex(ValueError, "5,000-row"):
            inspect_bundle(self.request_path)

    def test_oversize_sample_rejected_before_read(self):
        manifest = json.loads((self.root / "run_manifest.json").read_bytes())
        manifest["files"][0]["bytes"] = MAX_FILE_BYTES + 1
        self.repin(manifest)
        with patch("pipeline.integrity_validation.native_samples.read_bounded",
                   side_effect=AssertionError("must reject before body read")):
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                inspect_bundle(self.request_path)

    def test_local_oversize_metadata_rejected_before_open(self):
        path = self.root / "huge.json"
        with path.open("wb") as stream:
            stream.truncate(MAX_FILE_BYTES + 1)
        key = next(key for key in self.request["objects"] if key.endswith("run_manifest.json"))
        store = LocalMetadataStore(self.root, {key: "huge.json"})
        with patch.object(Path, "open", side_effect=AssertionError("must reject before open")):
            with self.assertRaisesRegex(ValueError, "size limit"):
                store.get_object(Bucket="pickage-curated", Key=key)

    def test_unsafe_local_paths_rejected(self):
        for path in ("../request.json", "C:/request.json", "//host/a", "files/*.parquet",
                     "files\\package.parquet", "files/CON", "files/package.parquet:stream"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                relative_file(self.root, path)

    def test_sample_missing_or_not_in_manifest_rejected(self):
        self.request["samples"][0]["path"] = "files/missing.parquet"
        self.save_request()
        with self.assertRaises(FileNotFoundError):
            inspect_bundle(self.request_path)
        self.request["samples"][0]["key"] += ".unknown"
        self.save_request()
        with self.assertRaisesRegex(ValueError, "native file record"):
            inspect_bundle(self.request_path)

    def test_duplicate_json_request_and_manifest_rejected(self):
        body = self.request_path.read_bytes()
        self.request_path.write_bytes(b'{"format_version":1,' + body[1:])
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            inspect_bundle(self.request_path)
        self.save_request()
        path = self.root / "run_manifest.json"
        path.write_bytes(b'{"status":"PASSED",' + path.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            inspect_bundle(self.request_path)

    def test_unknown_history_format_rejected(self):
        self.request["dataset"] = "package-snapshot-historical"
        self.save_request()
        with self.assertRaisesRegex(ValueError, "unsupported native dataset"):
            inspect_bundle(self.request_path)

    def test_request_timestamp_precision_and_second_offsets_are_rejected(self):
        for value in ("2026-08-31T12:34:56.1234567Z", "2026-08-31T12:34:56.123456+00:00:30"):
            with self.subTest(value=value):
                self.request["snapshot_timestamp"] = value
                self.save_request()
                with self.assertRaisesRegex(ValueError, "timestamp policy"):
                    inspect_bundle(self.request_path)

    def test_original_manifest_time_cannot_be_silently_truncated(self):
        manifest = json.loads((self.root / "run_manifest.json").read_bytes())
        manifest["report"]["snapshot_timestamp"] = "2026-08-31T12:34:56.1234567"
        self.repin(manifest)
        with self.assertRaisesRegex(ValueError, "source snapshot_timestamp"):
            inspect_bundle(self.request_path)

    def test_equivalent_utc_instant_with_minute_offset_matches(self):
        self.request["snapshot_timestamp"] = "2026-08-31T21:34:56.123456+09:00"
        self.save_request()
        self.assertEqual(inspect_bundle(self.request_path)["metadata_status"], "MATCH")

    def test_cli_writes_fresh_report_and_preserves_it_on_retry(self):
        out = Path(self.temp.name) / "report"
        args = ["--request", str(self.request_path), "--output", str(out)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
            previous = (out / "report.json").read_bytes()
            self.assertEqual(main(args), 2)
            self.assertEqual((out / "report.json").read_bytes(), previous)

    def test_cli_failure_produces_no_success_report(self):
        self.request["manifest_sha256"] = "0" * 64
        self.save_request()
        out = Path(self.temp.name) / "report"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--request", str(self.request_path), "--output", str(out)]), 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
