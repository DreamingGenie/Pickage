from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import hashlib
import json
import subprocess
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from pipeline.preprocessing.requirements_resolution.policy import make_policy
from pipeline.preprocessing.version_dependents.diagnostic import build_diagnostic, verify_diagnostic


SNAPSHOT = date(2026, 8, 31)
STAMP = datetime(2026, 8, 31, 21, 1, 10, 517131, tzinfo=timezone.utc)
UPSTREAM_RUN = "requirements-20260831-v1"
INPUT_SHA = "1" * 64
CURATED_RUN = "curated-20260907-v2"
BRONZE_RUN = "bronze-20260907-v1"
EDGE_SCHEMA = [
    ["snapshot_at", "DATE"], ["source_package_id", "INTEGER"],
    ["source_version", "VARCHAR"], ["target_package_id", "INTEGER"],
    ["target_version", "VARCHAR"], ["dependency_kinds", "VARCHAR[]"],
    ["declaration_count", "BIGINT"], ["snapshot_timestamp", "TIMESTAMP WITH TIME ZONE"],
    ["run_id", "VARCHAR"], ["input_sha256", "VARCHAR"],
    ["curated_run_id", "VARCHAR"], ["bronze_run_id", "VARCHAR"],
    ["policy_sha256", "VARCHAR"],
]


def _policy() -> dict:
    return make_policy(
        kinds=["dependencies"],
        unknown_published_at="exclude",
        unresolved="partial",
        decision_reference="S15P21A506-193 diagnostic aggregation",
    )


def _write_edges(path: Path, *, rows: list[tuple] | None = None) -> None:
    rows = [
        (SNAPSHOT, 1, "1.0.0", 10, "2.0.0", ["dependencies"], 1, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
        # The same source package-version declaration is repeated in the input.
        (SNAPSHOT, 1, "1.0.0", 10, "2.0.0", ["dependencies"], 1, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
        (SNAPSHOT, 1, "1.1.0", 10, "2.0.0", ["dependencies"], 2, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
        (SNAPSHOT, 2, "1.0.0", 10, "2.0.0", ["dependencies"], 1, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
        (SNAPSHOT, 1, "1.0.0", 10, "3.0.0", ["dependencies"], 1, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
        (SNAPSHOT, 10, "2.0.0", 20, "1.0.0", ["dependencies"], 1, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
        # A self edge is retained as a direct resolved relationship.
        (SNAPSHOT, 20, "1.0.0", 20, "1.0.0", ["dependencies"], 1, STAMP,
         UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"]),
    ] if rows is None else rows
    con = duckdb.connect()
    try:
        con.execute(
            """CREATE TABLE edges(
              snapshot_at DATE, source_package_id INTEGER, source_version VARCHAR,
              target_package_id INTEGER, target_version VARCHAR, dependency_kinds VARCHAR[],
              declaration_count BIGINT, snapshot_timestamp TIMESTAMPTZ, run_id VARCHAR,
              input_sha256 VARCHAR, curated_run_id VARCHAR, bronze_run_id VARCHAR,
              policy_sha256 VARCHAR)"""
        )
        if rows:
            con.executemany("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        con.execute("COPY edges TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)])
    finally:
        con.close()


def _candidate(source_run: Path, *, rows: list[tuple] | None = None) -> tuple[Path, str, bytes]:
    output = source_run / "attempts" / "test" / "finalize" / "outputs"
    (output / "edges").mkdir(parents=True)
    edge_path = output / "edges" / "part-000.parquet"
    _write_edges(edge_path, rows=rows)
    policy = _policy()
    candidate = {
        "status": "RECOVERY_CANDIDATE",
        "resolution_status": "PARTIAL",
        "ready_for_dependents": False,
        "final_output": "attempts/test/finalize/outputs",
        "request": {"run_id": UPSTREAM_RUN},
        "input": {
            "snapshot": SNAPSHOT.isoformat(),
            "snapshot_timestamp": STAMP.isoformat().replace("+00:00", "Z"),
            "input_sha256": INPUT_SHA,
            "curated_run_id": CURATED_RUN,
            "bronze_run_id": BRONZE_RUN,
        },
        "files": [],
        "finalize_report": {
            "run_id": UPSTREAM_RUN,
            "snapshot": SNAPSHOT.isoformat(),
            "snapshot_timestamp": STAMP.isoformat().replace("+00:00", "Z"),
            "resolution_status": "PARTIAL",
            "ready_for_dependents": False,
            "input_sha256": INPUT_SHA,
            "policy_sha256": policy["sha256"],
            "curated_run_id": CURATED_RUN,
            "bronze_run_id": BRONZE_RUN,
            "selected_declarations": 9,
            "resolved_declarations": 8,
            "unresolved_declarations": 1,
            "source_status_counts": {"PARTIAL": 3},
            "declaration_status_counts": {"RESOLVED": 8, "UNSUPPORTED_TAG": 1},
            "output_counts": {"edges": 7},
        },
        "prepare_report": {
            "snapshot": SNAPSHOT.isoformat(),
            "snapshot_timestamp": STAMP.isoformat().replace("+00:00", "Z"),
            "input_sha256": INPUT_SHA,
            "policy_sha256": policy["sha256"],
            "excluded_kind_counts": {},
            "excluded_unknown_publication_versions": 0,
        },
        "recovery": {"gaps": [], "output_hash_semantics": "sha256 of each parquet file"},
        "policy": policy,
    }
    con = duckdb.connect()
    try:
        record = con.execute(
            "SELECT count(*) AS rows FROM read_parquet(?)", [str(edge_path)]
        ).fetchone()[0]
        size = edge_path.stat().st_size
    finally:
        con.close()
    digest = hashlib.sha256(edge_path.read_bytes()).hexdigest()
    candidate["files"] = [{"path": "edges/part-000.parquet", "bytes": size, "sha256": digest,
                            "rows": record}]
    manifest = source_run / "candidate.json"
    raw = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    manifest.write_bytes(raw)
    return manifest, hashlib.sha256(raw).hexdigest(), raw


class DiagnosticArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="version-dependents-diagnostic-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source-run"
        self.source.mkdir()
        self.manifest, self.manifest_sha256, self.manifest_bytes = _candidate(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, **kwargs):
        params = dict(
            source_run=self.source,
            candidate_manifest=self.manifest,
            candidate_sha256=self.manifest_sha256,
            expected_snapshot_at=SNAPSHOT,
            output_root=self.root / "artifacts",
            run_id="diagnostic-test-1",
            threads=2,
            memory_limit="1GB",
        )
        params.update(kwargs)
        return build_diagnostic(**params)

    def rewrite_candidate(self, mutate):
        candidate = json.loads(self.manifest.read_text(encoding="utf-8"))
        mutate(candidate)
        raw = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.manifest.write_bytes(raw)
        self.manifest_sha256 = hashlib.sha256(raw).hexdigest()

    def replace_edges(self, rows):
        edge = self.source / "attempts" / "test" / "finalize" / "outputs" / "edges" / "part-000.parquet"
        _write_edges(edge, rows=rows)
        size = edge.stat().st_size
        digest = hashlib.sha256(edge.read_bytes()).hexdigest()
        self.rewrite_candidate(lambda value: value["files"][0].update(bytes=size, sha256=digest, rows=len(rows)))

    def rehash_output_manifest(self, output: Path, name: str):
        manifest_path = output / "diagnostic_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        path = output / name
        con = duckdb.connect()
        try:
            rows = con.execute("SELECT count(*) FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchone()[0]
            schema = [[str(row[0]), str(row[1]).upper()] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchall()]
        finally:
            con.close()
        record = {"path": name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": rows, "schema": schema,
                  "schema_sha256": hashlib.sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        manifest["files"] = [record if item["path"] == name else item for item in manifest["files"]]
        raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        manifest_path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_counts_distinct_source_versions_per_target_and_preserves_partial(self):
        result = self.build()
        self.assertEqual(result["manifest"]["dataset_status"], "PARTIAL")
        self.assertFalse(result["manifest"]["ready_for_load"])
        self.assertEqual(result["manifest"]["statistics"]["distinct_edges"], 6)
        self.assertEqual(result["manifest"]["statistics"]["duplicate_edges"], 1)
        with duckdb.connect() as con:
            rows = con.execute(
                "SELECT package_id, version, resolved_dependents_count FROM read_parquet(?, hive_partitioning=false) ORDER BY package_id, version",
                [str(Path(result["output_dir"]) / "resolved_counts.parquet")],
            ).fetchall()
        self.assertEqual(rows, [(10, "2.0.0", 3), (10, "3.0.0", 1), (20, "1.0.0", 2)])

    def test_fresh_connection_verification_returns_partial_manifest(self):
        result = self.build()
        verified = verify_diagnostic(Path(result["output_dir"]), manifest_sha256=result["manifest_sha256"])
        self.assertEqual(verified["artifact_status"], "COMPLETE")
        self.assertEqual(verified["dataset_status"], "PARTIAL")
        self.assertFalse(verified["ready_for_load"])

    def test_input_manifest_sha_mismatch_is_rejected_before_output(self):
        with self.assertRaises(ValueError):
            self.build(candidate_sha256="0" * 64)
        run_dir = self.root / "artifacts" / f"snapshot={SNAPSHOT}" / "run_id=diagnostic-test-1"
        self.assertFalse((run_dir / "outputs" / "diagnostic_manifest.json").exists())

    def test_source_edge_mutation_is_rejected(self):
        edge = self.source / "attempts" / "test" / "finalize" / "outputs" / "edges" / "part-000.parquet"
        edge.write_bytes(edge.read_bytes() + b"tampered")
        with self.assertRaises((ValueError, duckdb.Error)):
            self.build()

    def test_candidate_requires_request_run_id(self):
        self.rewrite_candidate(lambda value: value.pop("request"))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_snapshot_microsecond_mismatch(self):
        self.rewrite_candidate(lambda value: value["input"].update(snapshot_timestamp="2026-08-31T21:01:10.517132Z"))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_non_dependency_kind(self):
        edge = self.source / "attempts" / "test" / "finalize" / "outputs" / "edges" / "part-000.parquet"
        bad = edge.with_name("bad.parquet")
        con = duckdb.connect()
        try:
            con.execute("""CREATE TABLE bad_edges AS SELECT snapshot_at, source_package_id, source_version,
                target_package_id, target_version, ['optionalDependencies']::VARCHAR[] AS dependency_kinds,
                declaration_count, snapshot_timestamp, run_id, input_sha256, curated_run_id,
                bronze_run_id, policy_sha256 FROM read_parquet(?, hive_partitioning=false)""", [str(edge)])
            con.execute("COPY bad_edges TO ? (FORMAT PARQUET)", [str(bad)])
        finally:
            con.close()
        edge.unlink()
        # The input contract is tested through the manifest's declared edge schema;
        # a malformed file must fail before aggregation.
        self.rewrite_candidate(lambda value: value["files"][0].update(path="edges/bad.parquet", bytes=bad.stat().st_size, sha256=hashlib.sha256(bad.read_bytes()).hexdigest(), rows=7))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_declaration_count_reconciliation_mismatch(self):
        self.rewrite_candidate(lambda value: value["finalize_report"].update(resolved_declarations=7))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_unsafe_final_output_path(self):
        self.rewrite_candidate(lambda value: value.update(final_output="../outside"))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_null_source_id(self):
        self.replace_edges([(SNAPSHOT, None, "1.0.0", 10, "2.0.0", ["dependencies"], 1, STAMP,
                             UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"])])
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_null_target_id(self):
        self.replace_edges([(SNAPSHOT, 1, "1.0.0", None, "2.0.0", ["dependencies"], 1, STAMP,
                             UPSTREAM_RUN, INPUT_SHA, CURATED_RUN, BRONZE_RUN, _policy()["sha256"])])
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_more_than_six_timestamp_fraction_digits(self):
        self.rewrite_candidate(lambda value: value["input"].update(snapshot_timestamp="2026-08-31T21:01:10.5171311Z"))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_input_report_lineage_mismatch(self):
        self.rewrite_candidate(lambda value: value["finalize_report"].update(input_sha256="2" * 64))
        with self.assertRaises(ValueError):
            self.build()

    def test_candidate_rejects_complete_ready_upstream_state(self):
        self.rewrite_candidate(lambda value: value.update(resolution_status="COMPLETE", ready_for_dependents=True))
        with self.assertRaises(ValueError):
            self.build()

    def test_empty_resolved_edge_file_is_accepted_as_partial(self):
        self.replace_edges([])
        self.rewrite_candidate(lambda value: value["finalize_report"].update(
            selected_declarations=1, resolved_declarations=0, unresolved_declarations=1,
            output_counts={"edges": 0}, source_status_counts={"PARTIAL": 1},
            declaration_status_counts={"RESOLVED": 0, "UNSUPPORTED_TAG": 1}))
        # The artifact remains diagnostic-only even when no resolved edges exist.
        result = self.build()
        self.assertEqual(result["manifest"]["statistics"]["target_versions"], 0)

    def test_verify_cli_reads_manifest_in_a_new_process(self):
        result = self.build()
        completed = subprocess.run(
            [sys.executable, "-m", "pipeline.preprocessing.version_dependents.diagnostic", "verify",
             "--output-dir", result["output_dir"], "--manifest-sha256", result["manifest_sha256"]],
            cwd=REPO_ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_build_cli_emits_machine_readable_json_without_progress_prefix(self):
        output_root = self.root / "cli-artifacts"
        completed = subprocess.run(
            [sys.executable, "-m", "pipeline.preprocessing.version_dependents.diagnostic", "build",
             "--source-run", str(self.source), "--candidate-manifest", str(self.manifest),
             "--candidate-sha256", self.manifest_sha256, "--snapshot-at", SNAPSHOT.isoformat(),
             "--output-root", str(output_root), "--run-id", "diagnostic-cli-build-1",
             "--threads", "2", "--memory-limit", "1GB"],
            cwd=REPO_ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["dataset_status"], "PARTIAL")
        self.assertFalse(payload["ready_for_load"])
        self.assertTrue(Path(payload["output_dir"]).is_dir())

    def test_rehashed_wrong_count_content_is_rejected(self):
        result = self.build()
        output = Path(result["output_dir"])
        counts = output / "resolved_counts.parquet"
        con = duckdb.connect()
        try:
            con.execute("CREATE TEMP TABLE wrong_counts AS SELECT package_id, version, snapshot_at, snapshot_timestamp, resolved_dependents_count + 1 AS resolved_dependents_count, dataset_status FROM read_parquet(?, hive_partitioning=false)", [str(counts)])
            con.execute("COPY wrong_counts TO ? (FORMAT PARQUET)", [str(counts.with_suffix(".next.parquet"))])
        finally:
            con.close()
        counts.with_suffix(".next.parquet").replace(counts)
        sha = self.rehash_output_manifest(output, "resolved_counts.parquet")
        with self.assertRaises(ValueError):
            verify_diagnostic(output, manifest_sha256=sha)

    def test_rehashed_wrong_quality_content_is_rejected(self):
        result = self.build()
        output = Path(result["output_dir"])
        quality = output / "quality.parquet"
        con = duckdb.connect()
        try:
            con.execute("CREATE TEMP TABLE wrong_quality AS SELECT run_id, snapshot_at, snapshot_timestamp, dataset_status, ready_for_load, input_edge_rows + 1 AS input_edge_rows, distinct_edges, duplicate_edges, target_versions, max_resolved_dependents_count, upstream_quality_json, full_source_target_population_verified FROM read_parquet(?, hive_partitioning=false)", [str(quality)])
            con.execute("COPY wrong_quality TO ? (FORMAT PARQUET)", [str(quality.with_suffix(".next.parquet"))])
        finally:
            con.close()
        quality.with_suffix(".next.parquet").replace(quality)
        sha = self.rehash_output_manifest(output, "quality.parquet")
        with self.assertRaises(ValueError):
            verify_diagnostic(output, manifest_sha256=sha)

    def test_candidate_input_bytes_are_unchanged(self):
        self.build()
        self.assertEqual(self.manifest.read_bytes(), self.manifest_bytes)

    def test_duplicate_run_does_not_overwrite_existing_artifact(self):
        first = self.build()
        manifest_path = Path(first["output_dir"]) / "diagnostic_manifest.json"
        before = manifest_path.read_bytes()
        with self.assertRaises((FileExistsError, ValueError)):
            self.build()
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_output_mutation_is_detected_by_independent_verifier(self):
        result = self.build()
        output = Path(result["output_dir"])
        counts = output / "resolved_counts.parquet"
        counts.write_bytes(counts.read_bytes() + b"tampered")
        with self.assertRaises((ValueError, duckdb.Error)):
            verify_diagnostic(output, manifest_sha256=result["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
