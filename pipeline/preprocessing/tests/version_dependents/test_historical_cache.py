"""Contract tests for the compact H4 historical cache."""
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import duckdb

from pipeline.preprocessing.version_dependents import historical_cache as cache
from pipeline.preprocessing.version_dependents.historical_cache import create_cache, verify_cache

RUNTIME = {"node_version": "v24.18.0", "semver_version": "7.8.1", "package_arg_version": "13.0.2",
           "semver_sha256": "c" * 64, "package_arg_sha256": "d" * 64, "dependency_closure_sha256": "e" * 64,
           "options": {"loose": False, "includePrerelease": False}, "equal_precedence_tie": "original_version_utf16_ascending",
           "interval_end": "exclusive", "bounds": {"max_snapshots": 4096, "max_candidates": 100000,
           "max_unique_requirements": 512, "max_candidate_requirement_work": 2000000, "max_result_intervals": 20000, "max_frame_bytes": 7340032}}


class HistoricalCacheTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("CREATE TABLE history_count_intervals(package_id INTEGER, version VARCHAR, start_index INTEGER, end_index INTEGER, dependents_count BIGINT)")
        self.con.execute("CREATE TABLE history_target_population(package_id INTEGER, version VARCHAR, birth_index INTEGER)")
        self.con.execute("CREATE TABLE history_quality(snapshot_index INTEGER, quality_json VARCHAR)")
        quality = {"source_versions": 1, "target_versions": 1, "selected_declarations": 1,
                   "resolved_declarations": 1, "unresolved_declarations": 0, "distinct_edges": 1,
                   "duplicate_resolved_declarations": 0, "resolution_status": "COMPLETE",
                   "source_status_counts": {"RESOLVED": 1}, "declaration_status_counts": {"RESOLVED": 1},
                   "excluded_kind_declarations": {"peer_dependencies": 0, "optional_dependencies": 0},
                   "source_null_publication_excluded": 0, "source_future_excluded": 0, "target_rejections": {}}
        self.con.execute("INSERT INTO history_target_population VALUES (2,'1.0.0',0)")
        self.con.execute("INSERT INTO history_count_intervals VALUES (2,'1.0.0',0,2,1)")
        self.con.executemany("INSERT INTO history_quality VALUES (?,?)", [(i, json.dumps(quality)) for i in range(2)])
        self.calendar = [{"snapshot_at": "2026-08-30", "snapshot_timestamp": "2026-08-30T12:00:00Z"},
                         {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T12:00:00.000000Z"}]
        self.lineage = {"source_kind": "SYNTHETIC_FIXTURE", "input_manifest_sha256": "a" * 64, "policy_sha256": "b" * 64}

    def tearDown(self): self.con.close()

    def _save(self, path):
        return create_cache(self.con, output=path, calendar=self.calendar,
                            observed_snapshot_timestamp="2026-08-31T12:00:00Z",
                            lineage=self.lineage, runtime=RUNTIME)

    def _mutate_quality(self, **changes):
        rows = self.con.execute("SELECT snapshot_index, quality_json FROM history_quality ORDER BY snapshot_index").fetchall()
        self.con.execute("DELETE FROM history_quality")
        for index, raw in rows:
            value = json.loads(raw); value.update(changes)
            self.con.execute("INSERT INTO history_quality VALUES (?,?)", [index, json.dumps(value)])

    def test_save_verify_and_sparse_contract(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"; receipt = self._save(out)
            self.assertEqual(receipt["manifest"]["format"], "historical-count-cache-v1")
            self.assertEqual(verify_cache(out, receipt["manifest_sha256"])["files"][0]["rows"], 1)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"; receipt = self._save(out)
            with self.assertRaises(ValueError): self._save(out)

    def test_manifest_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"; receipt = self._save(out)
            p = out / "cache_manifest.json"; p.write_text(p.read_text() + " ", encoding="utf-8")
            with self.assertRaises(ValueError): verify_cache(out, receipt["manifest_sha256"])

    def test_parquet_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"; receipt = self._save(out)
            p = out / "quality.parquet"; p.write_bytes(p.read_bytes() + b"x")
            with self.assertRaises(ValueError): verify_cache(out, receipt["manifest_sha256"])

    def test_overlap_rejected(self):
        self.con.execute("INSERT INTO history_count_intervals VALUES (2,'1.0.0',1,2,2)")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_quality_conservation_rejected(self):
        self.con.execute("DELETE FROM history_quality")
        bad = {"source_versions": 1, "target_versions": 1, "selected_declarations": 2,
               "resolved_declarations": 1, "unresolved_declarations": 0, "distinct_edges": 1,
               "duplicate_resolved_declarations": 0, "resolution_status": "PARTIAL",
               "source_status_counts": {"RESOLVED": 1}, "declaration_status_counts": {"RESOLVED": 1},
               "excluded_kind_declarations": {"peer_dependencies": 0, "optional_dependencies": 0},
               "source_null_publication_excluded": 0, "source_future_excluded": 0, "target_rejections": {}}
        self.con.executemany("INSERT INTO history_quality VALUES (?,?)", [(i, json.dumps(bad)) for i in range(2)])
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_calendar_subset_before_observed_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = create_cache(self.con, output=Path(d) / "cache", calendar=self.calendar,
                                   observed_snapshot_timestamp="2026-09-01T00:00:00Z", lineage=self.lineage, runtime=RUNTIME)
            self.assertEqual(verify_cache(Path(receipt["cache_dir"]), receipt["manifest_sha256"])["calendar"], self.calendar)

    def test_zero_count_rows_are_rejected(self):
        self.con.execute("INSERT INTO history_count_intervals VALUES (2,'1.0.0',0,1,0)")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_quality_must_match_actual_edge_sum(self):
        self.con.execute("UPDATE history_count_intervals SET dependents_count = 2")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_quality_must_match_actual_target_births(self):
        self.con.execute("INSERT INTO history_target_population VALUES (3,'1.0.0',0)")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_detailed_status_counts_and_status_types_are_strict(self):
        self._mutate_quality(source_status_counts={"RESOLVED": 2})
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_unknown_negative_and_partial_statuses_are_rejected(self):
        self._mutate_quality(source_status_counts={"BOGUS": 1})
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")
        self._mutate_quality(source_status_counts={"RESOLVED": -1})
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")
        self._mutate_quality(source_status_counts={"RESOLVED": 1}, resolution_status="PARTIAL")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")
        self._mutate_quality(resolution_status="COMPLETE", source_status_counts={"RESOLVED": True})
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_runtime_requires_pinned_metadata(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            create_cache(self.con, output=Path(d) / "cache", calendar=self.calendar,
                         observed_snapshot_timestamp="2026-08-31T12:00:00Z", lineage=self.lineage, runtime={"node": "test"})

    def test_pinned_manifest_sha_is_required_for_verification(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"; self._save(out)
            with self.assertRaises(ValueError): verify_cache(out, None)

    def test_calendar_date_and_precision_are_validated(self):
        bad = [dict(self.calendar[0], snapshot_at="2026-08-29"), self.calendar[1]]
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            create_cache(self.con, output=Path(d) / "cache", calendar=bad,
                         observed_snapshot_timestamp="2026-08-31T12:00:00Z", lineage=self.lineage, runtime=RUNTIME)
        bad = [self.calendar[0], dict(self.calendar[1], snapshot_timestamp="2026-08-31T12:00:00.123456789Z")]
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            create_cache(self.con, output=Path(d) / "cache", calendar=bad,
                         observed_snapshot_timestamp="2026-08-31T12:00:00Z", lineage=self.lineage, runtime=RUNTIME)

    def test_empty_target_and_count_tables_are_allowed(self):
        self.con.execute("DELETE FROM history_count_intervals"); self.con.execute("DELETE FROM history_target_population")
        self._mutate_quality(target_versions=0, selected_declarations=0, resolved_declarations=0,
                             unresolved_declarations=0, distinct_edges=0, duplicate_resolved_declarations=0,
                             source_versions=0, source_status_counts={}, declaration_status_counts={},
                             resolution_status="COMPLETE")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"; receipt = self._save(out)
            self.assertEqual(verify_cache(out, receipt["manifest_sha256"])["files"][1]["rows"], 0)

    def test_generation_fingerprint_change_prevents_manifest_publication(self):
        original = cache.generation_contract(); changed = dict(original)
        changed[next(iter(changed))] = "f" * 64
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cache, "generation_contract", side_effect=[original, changed]):
            with self.assertRaises(ValueError): self._save(Path(d) / "cache")
            self.assertFalse((Path(d) / "cache" / "cache_manifest.json").exists())

    def test_required_path_reparse_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cache, "_reject_reparse_ancestors", side_effect=ValueError("reparse")):
            with self.assertRaises(ValueError): self._save(Path(d) / "cache")

    def test_required_file_reparse_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cache"
            receipt = self._save(out)
            with mock.patch.object(cache, "_reparse", side_effect=lambda path: path.name == "quality.parquet"):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    verify_cache(out, receipt["manifest_sha256"])

    def test_resolved_status_total_must_match_quality(self):
        self._mutate_quality(declaration_status_counts={"INVALID_SPEC": 1})
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError, "resolved declaration status"):
            self._save(Path(d) / "cache")

    def test_calendar_after_observed_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError, "exceeds observed"):
            create_cache(self.con, output=Path(d) / "cache", calendar=self.calendar,
                         observed_snapshot_timestamp="2026-08-31T11:59:59Z", lineage=self.lineage, runtime=RUNTIME)

    def test_fixture_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = Path(d) / "oversize.json"; fixture.write_bytes(b"{" + b"x" * (4 * 1024 * 1024) + b"}")
            with self.assertRaises(ValueError): cache.create_fixture_cache(fixture, Path(d) / "cache")


if __name__ == "__main__": unittest.main()
