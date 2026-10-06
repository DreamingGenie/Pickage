import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.preprocessing.repository_metrics.input import _file_record, _json_bytes, _safe_rel, prepare_inputs, reverify_inputs
from pipeline.preprocessing.snapshot.projects import _footer_sha256, inspect_projects


class RepositoryMetricsInputTests(unittest.TestCase):
    def test_safe_rel_rejects_traversal_absolute_and_windows_paths(self):
        for value in ("../x.parquet", "/x.parquet", "C:/x.parquet", "a\\b.parquet", "a/./b.parquet"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _safe_rel(value)

    def test_file_record_keeps_full_sha_and_row_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "part-0.parquet"
            with duckdb.connect() as con:
                con.execute("COPY (SELECT * FROM range(3)) TO ? (FORMAT PARQUET)", [str(path)])
                record = _file_record(path, root, con)
            self.assertEqual(record["rows"], 3)
            self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_reverify_detects_changed_input_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot, curated, versions, projects, candidate, metadata, bronze, bronze_ref = self._fixture(root)
            candidate_path = root / "calendar/candidate.json"
            candidate_path.parent.mkdir()
            candidate_path.write_bytes(b"{}")
            candidate["candidate_sha256"] = hashlib.sha256(b"{}").hexdigest()
            with patch("pipeline.preprocessing.repository_metrics.input.select_run", return_value=metadata), \
                 patch("pipeline.preprocessing.repository_metrics.input.load_bronze", return_value=(bronze, bronze_ref)), \
                 patch("pipeline.preprocessing.repository_metrics.input.read_candidate", return_value=candidate):
                prepared = prepare_inputs(object(), snapshot=snapshot, curated_run_id="curated-1", curated_outputs=curated,
                                          versions_dir=versions, projects_dir=projects, candidate_path=candidate_path,
                                          output=root / "prepared/input.json")
                reverify_inputs(prepared)
                extra = projects / f"snapshot={snapshot}/extra.parquet"
                extra.write_bytes(b"extra")
                with self.assertRaisesRegex(ValueError, "file set changed"):
                    reverify_inputs(prepared)
                extra.unlink()
                Path(prepared["file_records"][0]["path"]).write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "input file changed"):
                    reverify_inputs(prepared)

    def test_manifest_serialization_is_deterministic(self):
        value = {"b": 1, "a": {"z": 2, "y": 3}}
        self.assertEqual(_json_bytes(value), _json_bytes(json.loads(_json_bytes(value))))

    def _fixture(self, root: Path):
        snapshot = "2026-08-31"
        timestamp = "2026-08-31T21:01:10.517131"
        curated = root / "curated"
        for rel in ("package/data/package.parquet", "version/data/version.parquet", "package_ids/data/ids.parquet"):
            (curated / Path(rel).parent).mkdir(parents=True, exist_ok=True)
        with duckdb.connect() as con:
            con.execute("CREATE TABLE p(package_id INTEGER,name VARCHAR,repo_url VARCHAR)")
            con.execute("INSERT INTO p VALUES (1,'demo','https://github.com/example/demo')")
            con.execute("COPY p TO ? (FORMAT PARQUET)", [str(curated / "package/data/package.parquet")])
            con.execute("CREATE TABLE v(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON)")
            con.execute("INSERT INTO v VALUES ('1.0.0',1,NULL,1,NULL,NULL,NULL,NULL)")
            con.execute("COPY v TO ? (FORMAT PARQUET)", [str(curated / "version/data/version.parquet")])
            con.execute("COPY (SELECT 1::INTEGER AS package_id, 'demo' AS name) TO ? (FORMAT PARQUET)", [str(curated / "package_ids/data/ids.parquet")])
        versions = root / "versions"
        versions.mkdir()
        with duckdb.connect() as con:
            con.execute("COPY (SELECT TIMESTAMP '2026-08-31 21:01:10.517131' AS SnapshotAt, 'demo' AS Name, '1.0.0' AS Version, true AS is_release, 1::BIGINT AS ordinal, NULL::TIMESTAMP AS published_at, 'https://github.com/example/demo' AS source_repo) TO ? (FORMAT PARQUET)", [str(versions / "part-0.parquet")])
        local_manifest = {"status": "done", "verify": "ok", "table": "versions_full", "snapshot": snapshot,
                          "rows": 1, "gcs_files": 1, "gcs_bytes": (versions / "part-0.parquet").stat().st_size}
        local_bytes = json.dumps(local_manifest, sort_keys=True).encode()
        (versions / "_MANIFEST.json").write_bytes(local_bytes)
        projects = root / "projects"; partition = projects / f"snapshot={snapshot}"; partition.mkdir(parents=True)
        with duckdb.connect() as con:
            con.execute("COPY (SELECT TIMESTAMP '2026-08-31 21:01:10.517131' AS SnapshotAt, 4::INTEGER AS stars, 2::INTEGER AS open_issues) TO ? (FORMAT PARQUET)", [str(partition / "part-0.parquet")])
        (partition / "_MANIFEST.json").write_text(json.dumps({"status":"done","verify":"ok","table":"projects","snapshot":snapshot,"rows":1}), encoding="utf-8")
        inventory = inspect_projects(projects)
        candidate = {"candidate_sha256": "candidate-sha", "inventory_sha256": "inventory-sha",
                     "candidate": {"source": {"root": str(projects), "inventory_file": "projects-inventory.json"},
                                   "policy_version": "snapshot-time-v1", "policy_sha256": "policy"},
                     "inventory": inventory,
                     "calendar": [{"snapshot_at": snapshot, "snapshot_timestamp": timestamp + "Z"}]}
        prefix = f"depsdev/v1/package-version/snapshot={snapshot}/run_id=curated-1"
        def rec(rel, path):
            body = path.read_bytes(); return {"key": prefix + "/attempts/a1/" + rel, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        records = [rec("package/data/package.parquet", curated / "package/data/package.parquet"), rec("version/data/version.parquet", curated / "version/data/version.parquet"), rec("package_ids/data/ids.parquet", curated / "package_ids/data/ids.parquet")]
        bronze_records = [{"key": "depsdev/v1/versions_full/data/part-0.parquet", "bytes": (versions / "part-0.parquet").stat().st_size, "sha256": hashlib.sha256((versions / "part-0.parquet").read_bytes()).hexdigest()}]
        bronze = {"source_manifest_sha256": hashlib.sha256(local_bytes).hexdigest(), "row_count": 1, "files": bronze_records}
        curated_meta = {"run_prefix": prefix, "manifest_sha256": "curated-sha", "counts": {"package":1,"version":1},
                        "snapshot_timestamp": timestamp, "_service_records": {"package":[records[0]],"version":[records[1]]},
                        "manifest": {"files": records, "request": {"bronze_run_id":"bronze-1", "sources": {"versions_full": {"key":"depsdev/v1/versions_full/run_manifest.json","sha256":"bronze-sha"}}}}}
        return snapshot, curated, versions, projects, candidate, curated_meta, bronze, {"key":"depsdev/v1/versions_full/run_manifest.json","sha256":"bronze-sha"}

    def test_prepare_inputs_happy_path_and_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); snapshot, curated, versions, projects, candidate, metadata, bronze, bronze_ref = self._fixture(root)
            output = root / "prepared" / "input-manifest.json"
            candidate_path = root / "candidate" / "candidate.json"
            candidate_path.parent.mkdir()
            candidate_path.write_text("{}")
            with patch("pipeline.preprocessing.repository_metrics.input.select_run", return_value=metadata), \
                 patch("pipeline.preprocessing.repository_metrics.input.load_bronze", return_value=(bronze, bronze_ref)), \
                 patch("pipeline.preprocessing.repository_metrics.input.read_candidate", return_value=candidate):
                prepared = prepare_inputs(object(), snapshot=snapshot, curated_run_id="curated-1", curated_outputs=curated,
                                          versions_dir=versions, projects_dir=projects, candidate_path=candidate_path, output=output)
            self.assertEqual(prepared["counts"], {"package":1,"version":1,"versions_full":1,"projects":1})
            (curated / "extra.txt").write_text("bad")
            with patch("pipeline.preprocessing.repository_metrics.input.select_run", return_value=metadata), \
                 patch("pipeline.preprocessing.repository_metrics.input.load_bronze", return_value=(bronze, bronze_ref)), \
                 patch("pipeline.preprocessing.repository_metrics.input.read_candidate", return_value=candidate), self.assertRaisesRegex(ValueError, "output files"):
                prepare_inputs(object(), snapshot=snapshot, curated_run_id="curated-1", curated_outputs=curated,
                               versions_dir=versions, projects_dir=projects, candidate_path=candidate_path, output=root/"other.json")

    def test_prepare_rejects_checksum_lineage_and_timestamp_mismatch(self):
        for kind in ("checksum", "lineage", "timestamp"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); snapshot, curated, versions, projects, candidate, metadata, bronze, bronze_ref = self._fixture(root)
                candidate_path = root / "candidate" / "candidate.json"; candidate_path.parent.mkdir(); candidate_path.write_text("{}")
                if kind == "checksum":
                    (curated / "package/data/package.parquet").write_bytes(b"corrupt")
                elif kind == "lineage":
                    bronze_ref = {"key": bronze_ref["key"], "sha256": "different"}
                else:
                    metadata["snapshot_timestamp"] = "2026-08-31T21:01:11.517131"
                with patch("pipeline.preprocessing.repository_metrics.input.select_run", return_value=metadata), \
                     patch("pipeline.preprocessing.repository_metrics.input.load_bronze", return_value=(bronze, bronze_ref)), \
                     patch("pipeline.preprocessing.repository_metrics.input.read_candidate", return_value=candidate), self.assertRaises(ValueError):
                    prepare_inputs(object(), snapshot=snapshot, curated_run_id="curated-1", curated_outputs=curated,
                                   versions_dir=versions, projects_dir=projects, candidate_path=candidate_path,
                                   output=root / "prepared" / "input-manifest.json")


if __name__ == "__main__":
    unittest.main()
