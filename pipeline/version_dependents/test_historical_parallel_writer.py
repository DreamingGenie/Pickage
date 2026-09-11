"""Synthetic contract tests for partition-oriented history output."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import duckdb
from .historical_cache import create_fixture_cache
from .historical_parallel_writer import build_history, open_counts, open_quality
from .historical_parallel_verify import verify_history
from .historical_artifact import _run_lock
from . import historical_parallel_writer as writer

class ParallelHistoryWriterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Path(__file__).parent / "fixtures" / "historical_reference.json"
        if not self.fixture.exists(): self.skipTest("fixture unavailable")
    def _make(self, root):
        cache = create_fixture_cache(self.fixture, root / "cache")
        with duckdb.connect() as con:
            ids = [r[0] for r in con.execute("SELECT DISTINCT package_id FROM read_parquet(?) ORDER BY 1", [str(Path(cache["cache_dir"]) / "target_population.parquet")]).fetchall()]
        groups = {"000": ids[:1], "001": ids[1:]}
        result = build_history(cache_dir=cache["cache_dir"], cache_sha256=cache["manifest_sha256"], output=root / "history", partitions=groups)
        return cache, groups, result
    def test_sparse_output_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache, groups, result=self._make(root)
            self.assertEqual(result["run_status"], "COMPLETE")
            self.assertEqual(verify_history(run_dir=root/"history", cache_dir=cache["cache_dir"], cache_sha256=cache["manifest_sha256"], run_manifest_sha256=result["run_manifest_sha256"])["partitions_verified"], 2)
            with duckdb.connect() as con:
                open_counts(con, root/"history", result["run_manifest_sha256"])
                self.assertEqual([r[0] for r in con.execute("DESCRIBE counts").fetchall()], ["package_id","version","snapshot_at","snapshot_timestamp","dependents_count"])
    def test_include_zero_matches_oracle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache, _, result=self._make(root)
            with duckdb.connect() as con:
                calendar = json.loads((Path(cache['cache_dir']) / 'cache_manifest.json').read_bytes())['calendar']
                con.read_parquet(str(Path(cache['cache_dir']) / 'target_population.parquet')).create_view('oracle_targets')
                con.read_parquet(str(Path(cache['cache_dir']) / 'count_intervals.parquet')).create_view('oracle_intervals')
                zero_rows = 0
                for index, row in enumerate(calendar):
                    open_counts(con, root/'history', result['run_manifest_sha256'], snapshot_at=row['snapshot_at'], include_zero=True)
                    con.execute('CREATE OR REPLACE TEMP TABLE oracle AS SELECT t.package_id,t.version,?::DATE snapshot_at,'
                                '?::TIMESTAMPTZ snapshot_timestamp,coalesce(i.dependents_count,0)::INTEGER dependents_count '
                                'FROM oracle_targets t LEFT JOIN oracle_intervals i ON t.package_id=i.package_id '
                                'AND t.version=i.version AND i.start_index<=? AND ?<i.end_index WHERE t.birth_index<=?',
                                [row['snapshot_at'], row['snapshot_timestamp'], index, index, index])
                    self.assertFalse(con.execute('SELECT EXISTS ((SELECT * FROM oracle EXCEPT ALL SELECT * FROM counts) '
                                                 'UNION ALL (SELECT * FROM counts EXCEPT ALL SELECT * FROM oracle))').fetchone()[0])
                    zero_rows += con.execute('SELECT count(*) FROM counts WHERE dependents_count=0').fetchone()[0]
                self.assertGreater(zero_rows, 0)
                with self.assertRaises(ValueError):
                    open_counts(con, root/'history', result['run_manifest_sha256'], snapshot_at='1900-01-01')
    def test_partial_and_completed_resume_are_stable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache=create_fixture_cache(self.fixture, root/"cache")
            with duckdb.connect() as con: ids=[r[0] for r in con.execute("SELECT DISTINCT package_id FROM read_parquet(?) ORDER BY 1", [str(Path(cache["cache_dir"])/"target_population.parquet")]).fetchall()]
            groups={"000":ids[:1],"001":ids[1:]}; first=build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=root/"history",partitions=groups,max_partitions=1); self.assertEqual(first["run_status"],"INCOMPLETE")
            second=build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=root/"history",partitions=groups,resume=True); before=(root/"history"/"run_manifest.json").read_bytes(); third=build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=root/"history",partitions=groups,resume=True); self.assertEqual(second["run_manifest_sha256"],third["run_manifest_sha256"]); self.assertEqual(before,(root/"history"/"run_manifest.json").read_bytes())
    def test_count_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache,_,result=self._make(root); m=json.loads((root/"history"/"run_manifest.json").read_text()); key=next(k for k,v in m["partitions"].items() if v["file"] is not None); p=root/"history"/m["partitions"][key]["file"]["name"]; p.write_bytes(p.read_bytes()+b"x")
            with self.assertRaises(ValueError): verify_history(run_dir=root/"history",cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],run_manifest_sha256=result["run_manifest_sha256"])
    def test_duplicate_or_omitted_targets_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache=create_fixture_cache(self.fixture,root/"cache")
            with duckdb.connect() as con: ids=[r[0] for r in con.execute("SELECT DISTINCT package_id FROM read_parquet(?) ORDER BY 1",[str(Path(cache["cache_dir"])/"target_population.parquet")]).fetchall()]
            with self.assertRaises(ValueError): build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=root/"omitted",partitions={"000":ids[:-1]})
            with self.assertRaises(ValueError): build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=root/"duplicate",partitions={"000":ids,"001":ids[:1]})
    def test_quality_open_api(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); _,_,result=self._make(root)
            with duckdb.connect() as con: open_quality(con,root/"history",result["run_manifest_sha256"]); self.assertEqual(con.execute("SELECT count(*) FROM quality").fetchone()[0],3)

    def test_quality_and_receipt_tamper_rejected(self):
        for target in ("quality", "receipt"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as d:
                root=Path(d); cache,_,result=self._make(root); m=json.loads((root/"history"/"run_manifest.json").read_text())
                if target == "quality":
                    p=root/"history"/m["quality"]["name"]
                else:
                    key=next(iter(m["partitions"])); p=root/"history"/m["partitions"][key]["attempt"]/"receipt.json"
                p.write_bytes(p.read_bytes()+b"x")
                with self.assertRaises(ValueError): verify_history(run_dir=root/"history",cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],run_manifest_sha256=result["run_manifest_sha256"])

    def test_concurrent_run_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache=create_fixture_cache(self.fixture,root/"cache")
            with duckdb.connect() as con: ids=[r[0] for r in con.execute("SELECT DISTINCT package_id FROM read_parquet(?)",[str(Path(cache["cache_dir"])/"target_population.parquet")]).fetchall()]
            output=root/"history"; output.mkdir()
            with _run_lock(output):
                with self.assertRaises(RuntimeError): build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=output,partitions={"000":ids},resume=True)

    def test_empty_partition_has_no_count_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache,groups,_=self._make(root); groups["002"]=[]
            result=build_history(cache_dir=cache["cache_dir"],cache_sha256=cache["manifest_sha256"],output=root/"empty",partitions=groups)
            manifest=json.loads((root/"empty"/"run_manifest.json").read_text())
            self.assertIsNone(manifest["partitions"]["002"]["file"])

    def test_orphan_receipt_after_checkpoint_crash_is_recovered(self):
        for phase in ('PART_RECEIPT', 'QUALITY_RECEIPT'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d:
                root=Path(d); cache,groups,_=self._make(root)
                output=root/'crash'
                def crash(_root, reached):
                    if reached == phase:
                        raise RuntimeError('injected')
                with patch.object(writer, '_checkpoint', side_effect=crash):
                    with self.assertRaisesRegex(RuntimeError, 'injected'):
                        build_history(cache_dir=cache['cache_dir'], cache_sha256=cache['manifest_sha256'], output=output, partitions=groups)
                before = {p:p.read_bytes() for p in output.rglob('*') if p.is_file() and p.suffix in ('.json', '.parquet')}
                resumed=build_history(cache_dir=cache['cache_dir'],cache_sha256=cache['manifest_sha256'],output=output,partitions=groups,resume=True)
                self.assertEqual(resumed['run_status'], 'COMPLETE')
                verify_history(run_dir=output, cache_dir=cache['cache_dir'], cache_sha256=cache['manifest_sha256'], run_manifest_sha256=resumed['run_manifest_sha256'])
                for p, raw in before.items():
                    self.assertEqual(raw, p.read_bytes())

if __name__ == "__main__": unittest.main()
