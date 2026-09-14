"""Small integration contracts for the independent production verifier."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.requirements_resolution.bridge import NodeSession, discover_runtime
from .historical_production_verify import verify_sample


class HistoricalProductionVerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.runtime = discover_runtime()
            probe = Path(tempfile.mkdtemp(prefix="production-verify-runtime-")) / "node.log"
            with NodeSession(cls.runtime, probe) as node:
                cls.node_meta = node.request({"op": "metadata"})
        except ValueError as exc:
            raise unittest.SkipTest(str(exc))

    def _case(self, *, wrong_cache=False, wrong_lookup=False, diagnostic=None,
              empty_lookup=False, diagnostic_date="2026-08-31"):
        root = Path(tempfile.mkdtemp(prefix="production-verify-"))
        prepared = root / "prepared"; cache = root / "cache"
        prepared.mkdir(); cache.mkdir()
        manifest = {"scope": "SAMPLE", "calendar": [
            {"snapshot_at": "2026-08-30", "snapshot_timestamp": "2026-08-30T00:00:00.000000Z"},
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T00:00:00.000000Z"}],
            "observed_snapshot_timestamp": "2026-08-31T00:00:00.000000Z"}
        def open_inputs(con, _prepared, _manifest):
            con.execute("CREATE TABLE target_names(name VARCHAR, package_id INTEGER, known_package BOOLEAN)")
            con.execute("INSERT INTO target_names VALUES ('dep', 2, true)")
            con.execute("CREATE TABLE target_population(package_id INTEGER, name VARCHAR, version VARCHAR, birth_index INTEGER)")
            con.execute("INSERT INTO target_population VALUES (2,'dep','1.0.0',0),(2,'dep','2.0.0',1)")
            con.execute("CREATE TABLE lookups(lookup_id BIGINT, declared_name VARCHAR, requirement VARCHAR)")
            if not empty_lookup:
                con.execute("INSERT INTO lookups VALUES (1,'dep','^1.0.0')")
            con.execute("CREATE TABLE declarations(source_package_id INTEGER, source_version VARCHAR, birth_index INTEGER, declared_name VARCHAR, requirement VARCHAR, lookup_id BIGINT)")
            if not empty_lookup:
                con.execute("INSERT INTO declarations VALUES (1,'1.0.0',0,'dep','^1.0.0',1),(1,'2.0.0',1,'dep','^1.0.0',1)")
        with duckdb.connect() as out:
            out.execute("COPY (SELECT * FROM (VALUES (2,'dep','1.0.0',0),(2,'dep','2.0.0',1)) v(package_id,name,version,birth_index)) TO ? (FORMAT PARQUET)", [str(prepared / "target_population.parquet")])
            values = "(2,'1.0.0',0,1,1),(2,'1.0.0',1,2,2)" if not wrong_cache else "(2,'1.0.0',0,1,9),(2,'1.0.0',1,2,2)"
            if empty_lookup:
                values = "(2,'1.0.0',0,2,0)"
            out.execute(f"COPY (SELECT * FROM (VALUES {values}) v(package_id,version,start_index,end_index,dependents_count)) TO ? (FORMAT PARQUET)", [str(cache / "count_intervals.parquet")])
            target1 = "'2.0.0'" if wrong_lookup else "'1.0.0'"
            lookup_query = "SELECT * FROM (VALUES (1,0,2,'RESOLVED','>=1.0.0 <2.0.0-0',2," + target1 + ")) v(lookup_id,start_index,end_index,status,normalized_range,target_package_id,target_version)" if not empty_lookup else "SELECT NULL::BIGINT lookup_id,NULL::INTEGER start_index,NULL::INTEGER end_index,NULL::VARCHAR status,NULL::VARCHAR normalized_range,NULL::INTEGER target_package_id,NULL::VARCHAR target_version WHERE false"
            out.execute(f"COPY ({lookup_query}) TO ? (FORMAT PARQUET)", [str(root / "lookup.parquet")])
            if diagnostic is not None:
                out.execute(f"COPY (SELECT * FROM (VALUES (2,'1.0.0',DATE '{diagnostic_date}',TIMESTAMPTZ '{diagnostic_date}T00:00:00Z',{int(diagnostic)}::INTEGER,'PARTIAL')) v(package_id,version,snapshot_at,snapshot_timestamp,resolved_dependents_count,dataset_status)) TO ? (FORMAT PARQUET)", [str(root / "diagnostic.parquet")])
        patches = [patch("pipeline.version_dependents.historical_production_input.verify_inputs", return_value=manifest),
                   patch("pipeline.version_dependents.historical_production_input.open_inputs", side_effect=open_inputs),
                   patch("pipeline.version_dependents.historical_production_verify.verify_cache", return_value={"calendar": manifest["calendar"], "runtime": self.node_meta})]
        for item in patches: item.start()
        self.addCleanup(lambda: [item.stop() for item in patches])
        return root, prepared, cache

    def _run(self, root, prepared, cache, **kwargs):
        return verify_sample(prepared_dir=prepared, manifest_sha256="a" * 64,
                             cache_dir=cache, cache_sha256="b" * 64,
                             lookup_interval_paths=[root / "lookup.parquet"],
                             output=root / "report", runtime=self.runtime, **kwargs)

    def test_real_node_and_duckdb_sample_matches_cache_and_lookup_intervals(self):
        root, prepared, cache = self._case()
        report = self._run(root, prepared, cache)
        self.assertEqual(report["mismatch_count"], 0)
        self.assertEqual(report["total_resolved_lookups"], 2)
        self.assertTrue((root / "report" / "report.json").is_file())

    def test_count_mismatch_is_rejected(self):
        root, prepared, cache = self._case(wrong_cache=True)
        with self.assertRaisesRegex(ValueError, "sample verification mismatch"):
            self._run(root, prepared, cache)

    def test_diagnostic_physical_schema_without_partition_columns(self):
        root, prepared, cache = self._case(diagnostic=2)
        report = self._run(root, prepared, cache, diagnostic_counts=root / "diagnostic.parquet")
        self.assertEqual(report["diagnostic_mismatch_count"], 0)

    def test_lookup_status_or_target_mismatch_is_rejected(self):
        root, prepared, cache = self._case(wrong_lookup=True)
        with self.assertRaisesRegex(ValueError, "sample verification mismatch"):
            self._run(root, prepared, cache)

    def test_latest_diagnostic_mismatch_is_rejected(self):
        root, prepared, cache = self._case(diagnostic=99)
        with self.assertRaisesRegex(ValueError, "latest diagnostic count mismatch"):
            self._run(root, prepared, cache, diagnostic_counts=root / "diagnostic.parquet")

    def test_empty_lookup_sample_completes_without_executemany(self):
        root, prepared, cache = self._case(empty_lookup=True)
        report = self._run(root, prepared, cache)
        self.assertEqual(report["lookup_count"], 0)
        self.assertEqual(report["mismatch_count"], 0)

    def test_diagnostic_wrong_snapshot_is_rejected(self):
        root, prepared, cache = self._case(diagnostic=1, diagnostic_date="2026-08-30")
        with self.assertRaisesRegex(ValueError, "snapshot does not match"):
            self._run(root, prepared, cache, diagnostic_counts=root / "diagnostic.parquet")


if __name__ == "__main__":
    unittest.main()
