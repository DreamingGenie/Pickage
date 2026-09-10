"""Contract tests for immutable interval input preparation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.downloads_interval import input as loader


class _Body:
    def __init__(self, body: bytes): self.body, self.pos = body, 0
    def read(self, size=-1):
        if size < 0: size = len(self.body) - self.pos
        value = self.body[self.pos:self.pos + size]; self.pos += len(value); return value
    def close(self): pass


class _S3:
    def __init__(self): self.objects = {}
    def get_object(self, Bucket, Key): return {"Body": _Body(self.objects[(Bucket, Key)])}
    def head_object(self, Bucket, Key): return {"ContentLength": len(self.objects[(Bucket, Key)])}


def _sha(body): return hashlib.sha256(body).hexdigest()
def _put(s3, bucket, key, body): s3.objects[(bucket, key)] = body


class InputFixture:
    """Build a valid tiny Bronze input and a real two-table Curated run."""
    snapshot = "2026-08-31"; curated_run_id = "curated-test-1"; bronze_run_id = "bronze-test-1"

    def __init__(self, root: Path, *, first_snapshot=False, bronze_run_id=None, curated_run_id=None):
        self.root, self.s3 = root, _S3()
        if bronze_run_id is not None: self.bronze_run_id = bronze_run_id
        if curated_run_id is not None: self.curated_run_id = curated_run_id
        self.bronze_prefix = f"npm-downloads/v1/run_id={self.bronze_run_id}"
        self.curated_prefix = f"depsdev/v1/package-version/snapshot={self.snapshot}/run_id={self.curated_run_id}"
        self.candidate = {"candidate_sha256": "c" * 64, "calendar": [{
            "snapshot_at": self.snapshot, "snapshot_timestamp": "2026-08-31T00:00:00Z",
            "previous_snapshot_at": None if first_snapshot else "2026-08-24",
            "download_start_inclusive": None if first_snapshot else "2026-08-24",
            "download_end_exclusive": self.snapshot}]}
        self._build_curated(); self._build_bronze(first_snapshot=first_snapshot)

    def _parquet(self, name, sql):
        path = self.root / name
        with duckdb.connect() as con:
            con.execute(sql); con.execute("COPY (SELECT * FROM source) TO ? (FORMAT PARQUET)", [str(path)])
        return path.read_bytes()

    def _record(self, key, body): return {"key": key, "bytes": len(body), "sha256": _sha(body)}

    def _build_curated(self):
        package = self._parquet("package.parquet", "CREATE TABLE source(package_id INTEGER, name VARCHAR, repo_url VARCHAR); INSERT INTO source VALUES (1, 'alpha', NULL)")
        version = self._parquet("version.parquet", "CREATE TABLE source(version VARCHAR, package_id INTEGER, published_at TIMESTAMP, ordinal BIGINT, description VARCHAR, licenses JSON, deprecated VARCHAR, dependency JSON); INSERT INTO source VALUES ('1.0.0', 1, TIMESTAMP '2026-08-01 00:00:00', 0, NULL, NULL, NULL, NULL)")
        self.package_record = self._record(self.curated_prefix + "/attempts/a1/package/data/part-0.parquet", package)
        self.version_record = self._record(self.curated_prefix + "/attempts/a1/version/data/part-0.parquet", version)
        _put(self.s3, "pickage-curated", self.package_record["key"], package); _put(self.s3, "pickage-curated", self.version_record["key"], version)
        manifest = {"contract_version": 1, "status": "PASSED", "verification": "GET_SHA256_ALL_FILES", "request": {"snapshot": self.snapshot, "run_id": self.curated_run_id}, "report": {"output_counts": {"package/data": 1, "version/data": 1}, "snapshot_timestamp": "2026-08-31T00:00:00"}, "files": [self.package_record, self.version_record]}
        self.curated_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); self.curated_sha = _sha(self.curated_body)
        _put(self.s3, "pickage-curated", self.curated_prefix + "/run_manifest.json", self.curated_body)
        _put(self.s3, "pickage-curated", self.curated_prefix + "/_SUCCESS", json.dumps({"manifest_sha256": self.curated_sha}).encode())

    def _build_bronze(self, *, first_snapshot):
        target_body = b"name\nalpha\n"
        status_path = self.root / "status.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE source(name VARCHAR, status VARCHAR)")
            con.execute("INSERT INTO source VALUES ('alpha', 'READY')")
            con.execute("COPY source TO ? (FORMAT PARQUET)", [str(status_path)])
        values = {"target.csv": target_body, "status.parquet": status_path.read_bytes(), "source/metadata.json": b"{}", "raw/response.json": b"{}"}
        roles = {"target.csv": "target_csv", "status.parquet": "status_parquet", "source/metadata.json": "source_metadata", "raw/response.json": "raw_response"}
        files = [{"path": path, "role": roles[path], "bytes": len(body), "sha256": _sha(body), "row_count": 1}
                 for path, body in values.items()]
        if not first_snapshot:
            path = "parquet/downloads/date=2026-08-24/part.parquet"
            daily = self._parquet("daily.parquet", "CREATE TABLE source(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN); INSERT INTO source VALUES ('alpha', 10, false)")
            values[path] = daily; files.append({"path": path, "role": "daily_parquet", "bytes": len(daily), "sha256": _sha(daily)})
        else:
            path = "parquet/downloads/date=2026-08-31/part.parquet"
            daily = self._parquet("daily-first.parquet", "CREATE TABLE source(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN); INSERT INTO source VALUES ('alpha', 10, false)")
            values[path] = daily; files.append({"path": path, "role": "daily_parquet", "bytes": len(daily), "sha256": _sha(daily)})
        for row in files:
            if row["role"] == "daily_parquet":
                day = row["path"].split("date=")[1].split("/")[0]
                row.update(min_date=day, max_date=day, row_count=1)
        manifest = {"format_version": 1, "dataset": "npm-downloads", "run_id": self.bronze_run_id, "status": "REVERIFIED", "required_remote_verification": "GET_SHA256_ALL_FILES", "quality": {"consistency_checks": {"all_files": True}}, "files": files}
        self.bronze_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); self.bronze_sha = _sha(self.bronze_body)
        _put(self.s3, "pickage-raw", self.bronze_prefix + "/run_manifest.json", self.bronze_body); _put(self.s3, "pickage-raw", self.bronze_prefix + "/_SUCCESS", (self.bronze_sha + "\n").encode()); _put(self.s3, "pickage-raw", self.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": self.bronze_sha}).encode())
        for row in files: _put(self.s3, "pickage-raw", self.bronze_prefix + "/data/" + row["path"], values[row["path"]])

    def prepare(self, **kwargs):
        args = dict(snapshot=self.snapshot, bronze_run_id=self.bronze_run_id, bronze_manifest_sha256=self.bronze_sha, curated_run_id=self.curated_run_id, curated_manifest_sha256=self.curated_sha, candidate_path=self.root / "candidate.json", candidate_sha256="c" * 64, cache_dir=self.root / "cache", workers=2); args.update(kwargs)
        with patch.object(loader, "read_candidate", return_value=self.candidate): return loader.prepare(self.s3, **args)


class InputTests(unittest.TestCase):
    def fixture(self, **kwargs):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return InputFixture(Path(self.tmp.name), **kwargs)

    def test_valid_run_selects_half_open_daily_and_both_curated_tables(self):
        f = self.fixture(); result = f.prepare(); self.assertEqual(len(result["daily_files"]), 1); self.assertEqual(len(result["package_files"]), 1); self.assertEqual(result["interval"]["previous_snapshot_at"], "2026-08-24")
        self.assertNotIn("path", result["input_manifest"]["candidate"])
        self.assertEqual(result["input_manifest"]["verification"]["unconsumed_curated_files"], "APPROVED_MANIFEST_ONLY_NO_BYTE_RESCAN")

    def test_first_snapshot_has_no_selected_daily_files(self): self.assertEqual(self.fixture(first_snapshot=True).prepare()["daily_files"], [])
    def test_revalidate_accepts_same_input(self):
        f = self.fixture(); result = f.prepare()
        with patch.object(loader, "read_candidate", return_value=f.candidate): loader.revalidate(f.s3, result)

    def test_rejects_wrong_bronze_manifest_digest(self):
        with self.assertRaisesRegex(ValueError, "manifest or completion"): self.fixture().prepare(bronze_manifest_sha256="a" * 64)

    def test_rejects_wrong_bronze_completion_marker(self):
        f = self.fixture(); _put(f.s3, "pickage-raw", f.bronze_prefix + "/_SUCCESS", b"f" * 64 + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest or completion"): f.prepare()

    def test_rejects_wrong_bronze_input_digest(self):
        f = self.fixture(); _put(f.s3, "pickage-raw", f.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": "a" * 64}).encode())
        with self.assertRaisesRegex(ValueError, "_INPUT manifest"): f.prepare()

    def test_rejects_wrong_curated_manifest_digest(self):
        with self.assertRaisesRegex(ValueError, "Curated manifest hash"): self.fixture().prepare(curated_manifest_sha256="a" * 64)

    def test_select_run_rejects_wrong_curated_marker(self):
        f = self.fixture(); _put(f.s3, "pickage-curated", f.curated_prefix + "/_SUCCESS", b"{}")
        with self.assertRaisesRegex(ValueError, "completion marker hash"): f.prepare()

    def test_accepts_timestamp_with_different_fraction_format_for_same_instant(self):
        f = self.fixture(); self._replace_curated_report(f, "2026-08-31T00:00:00.000000"); f.prepare()

    def test_rejects_changed_curated_snapshot_instant(self):
        f = self.fixture(); self._replace_curated_report(f, "2026-08-31T00:00:01")
        with self.assertRaisesRegex(ValueError, "timestamp mismatch"): f.prepare()

    @staticmethod
    def _replace_curated_report(f, timestamp):
        manifest = json.loads(f.curated_body); manifest["report"]["snapshot_timestamp"] = timestamp; body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.curated_sha = _sha(body)
        _put(f.s3, "pickage-curated", f.curated_prefix + "/run_manifest.json", body); _put(f.s3, "pickage-curated", f.curated_prefix + "/_SUCCESS", json.dumps({"manifest_sha256": f.curated_sha}).encode())

    def test_rejects_unsafe_duplicate_or_unknown_bronze_records(self):
        for mutation in (lambda rows: rows.append(rows[0].copy()), lambda rows: rows[0].update(path="../escape"), lambda rows: rows[0].update(path="C:/escape"), lambda rows: rows[0].update(role="unknown")):
            f = self.fixture(); manifest = json.loads(f.bronze_body); mutation(manifest["files"]); body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.bronze_sha = _sha(body)
            _put(f.s3, "pickage-raw", f.bronze_prefix + "/run_manifest.json", body); _put(f.s3, "pickage-raw", f.bronze_prefix + "/_SUCCESS", (f.bronze_sha + "\n").encode()); _put(f.s3, "pickage-raw", f.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": f.bronze_sha}).encode())
            with self.assertRaises(ValueError): f.prepare(bronze_manifest_sha256=f.bronze_sha)

    def test_rejects_daily_record_without_date_partition(self):
        f = self.fixture(); manifest = json.loads(f.bronze_body); manifest["files"][-1]["path"] = "parquet/downloads/part.parquet"; body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.bronze_sha = _sha(body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/run_manifest.json", body); _put(f.s3, "pickage-raw", f.bronze_prefix + "/_SUCCESS", (f.bronze_sha + "\n").encode()); _put(f.s3, "pickage-raw", f.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": f.bronze_sha}).encode())
        with self.assertRaises(ValueError): f.prepare(bronze_manifest_sha256=f.bronze_sha)

    def test_rejects_daily_footer_row_count_mismatch(self):
        f = self.fixture(); manifest = json.loads(f.bronze_body); manifest["files"][-1]["row_count"] = 2
        body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.bronze_sha = _sha(body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/run_manifest.json", body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/_SUCCESS", (f.bronze_sha + "\n").encode())
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": f.bronze_sha}).encode())
        with self.assertRaisesRegex(ValueError, "footer row count mismatch"):
            f.prepare(bronze_manifest_sha256=f.bronze_sha)

    def test_rejects_target_csv_row_count_mismatch(self):
        f = self.fixture(); manifest = json.loads(f.bronze_body)
        target = next(row for row in manifest["files"] if row["role"] == "target_csv")
        target["row_count"] = 2
        body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.bronze_sha = _sha(body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/run_manifest.json", body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/_SUCCESS", (f.bronze_sha + "\n").encode())
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": f.bronze_sha}).encode())
        with self.assertRaisesRegex(ValueError, "target CSV row count mismatch"):
            f.prepare(bronze_manifest_sha256=f.bronze_sha)

    def test_rejects_missing_target_csv_row_count(self):
        f = self.fixture(); manifest = json.loads(f.bronze_body)
        target = next(row for row in manifest["files"] if row["role"] == "target_csv")
        del target["row_count"]
        body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.bronze_sha = _sha(body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/run_manifest.json", body)
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/_SUCCESS", (f.bronze_sha + "\n").encode())
        _put(f.s3, "pickage-raw", f.bronze_prefix + "/_INPUT.json", json.dumps({"manifest_sha256": f.bronze_sha}).encode())
        with self.assertRaises(ValueError):
            f.prepare(bronze_manifest_sha256=f.bronze_sha)

    def test_rejects_missing_selected_daily_object(self):
        f = self.fixture(); f.s3.objects.pop(("pickage-raw", f.bronze_prefix + "/data/parquet/downloads/date=2026-08-24/part.parquet"))
        with self.assertRaises(KeyError): f.prepare()

    def test_revalidate_rejects_same_size_remote_tamper(self):
        f = self.fixture(); result = f.prepare(); _put(f.s3, "pickage-raw", f.bronze_prefix + "/data/target.csv", b"name\nbeta\n")
        with patch.object(loader, "read_candidate", return_value=f.candidate), self.assertRaisesRegex(ValueError, "remote object"): loader.revalidate(f.s3, result)

    def test_revalidate_rejects_local_tamper_before_commit(self):
        f = self.fixture(); result = f.prepare(); Path(result["target_file"]).write_bytes(b"tampered!!")
        with patch.object(loader, "read_candidate", return_value=f.candidate), self.assertRaisesRegex(ValueError, "local consumed"): loader.revalidate(f.s3, result)

    def test_rejects_curated_package_schema_mismatch(self):
        f = self.fixture(); bad = f.root / "bad.parquet"
        with duckdb.connect() as con: con.execute("CREATE TABLE source(package_id INTEGER, name VARCHAR)"); con.execute("INSERT INTO source VALUES (1, 'alpha')"); con.execute("COPY source TO ? (FORMAT PARQUET)", [str(bad)])
        body = bad.read_bytes(); _put(f.s3, "pickage-curated", f.package_record["key"], body)
        manifest = json.loads(f.curated_body)
        manifest["files"][0] = f.package_record | {"bytes": len(body), "sha256": _sha(body)}
        manifest_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        f.curated_sha = _sha(manifest_body)
        _put(f.s3, "pickage-curated", f.curated_prefix + "/run_manifest.json", manifest_body)
        _put(f.s3, "pickage-curated", f.curated_prefix + "/_SUCCESS", json.dumps({"manifest_sha256": f.curated_sha}).encode())
        with self.assertRaisesRegex(ValueError, "schema mismatch"): f.prepare()

    def test_rejects_curated_package_footer_count_mismatch(self):
        f = self.fixture(); manifest = json.loads(f.curated_body)
        manifest["report"]["output_counts"]["package/data"] = 2
        body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(); f.curated_sha = _sha(body)
        _put(f.s3, "pickage-curated", f.curated_prefix + "/run_manifest.json", body)
        _put(f.s3, "pickage-curated", f.curated_prefix + "/_SUCCESS", json.dumps({"manifest_sha256": f.curated_sha}).encode())
        with self.assertRaisesRegex(ValueError, "counts disagree|footer row count"): f.prepare()

    def test_prepare_accepts_parallel_workers(self): self.assertEqual(self.fixture().prepare(workers=4)["expected_package_rows"], 1)


if __name__ == "__main__": unittest.main()
