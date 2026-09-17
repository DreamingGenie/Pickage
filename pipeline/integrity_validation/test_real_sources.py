import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from .real_sources import bind_sources, _safe_path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class RealSourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        source = self.root / "source/run/run_manifest.json"; source.parent.mkdir(parents=True)
        source.write_text('{"run_status":"COMPLETE","full_selection_executed":true}\n')
        cdir = self.root / "data/snapshot/ref"; cdir.mkdir(parents=True)
        inv, sql = b'{"rows":1}\n', b"SELECT snapshot_at FROM projects;\n"
        (cdir / "projects-inventory.json").write_bytes(inv); (cdir / "snapshot-dates.sql").write_bytes(sql)
        candidate = {"files": [{"path": "projects-inventory.json", "sha256": hashlib.sha256(inv).hexdigest()}, {"path": "snapshot-dates.sql", "sha256": hashlib.sha256(sql).hexdigest()}], "calendar": ["2022-05-08", "2026-08-31"]}
        (cdir / "snapshot-candidate.json").write_text(json.dumps(candidate, indent=2) + "\n")
        candidate_sha = hashlib.sha256((cdir / "snapshot-candidate.json").read_bytes()).hexdigest()
        self.base_meta = {"dataset": "package-snapshot", "snapshot": "2026-08-31", "files": [{"path": "package_snapshot.parquet"}], "counts": {"package_snapshot": 1}}
        self.history_meta = {"dataset": "package-snapshot", "snapshot": "2022-05-08", "files": [{"path": "package_snapshot.parquet"}], "counts": {"package_snapshot": 1}}
        bdir = self.root / "data/package_snapshot/curated/base"; (bdir / "output").mkdir(parents=True)
        bmanifest = bdir / "run_manifest.json"; bmanifest.write_text(json.dumps(self.base_meta, indent=2) + "\n")
        bsha = hashlib.sha256(bmanifest.read_bytes()).hexdigest()
        receipt_dir = self.root / "data/package_snapshot/S15P21A506-288"; receipt_dir.mkdir(parents=True)
        (receipt_dir / "build-result.json").write_text(json.dumps({"result": {"manifest_path": str(bmanifest), "manifest_sha256": bsha}}))
        (receipt_dir / "first-load-result.json").write_text(json.dumps({"input": {"manifest_sha256": bsha, "manifest": self.base_meta}}))
        hdir = self.root / "data/package_snapshot/history/full-history-288-20260909-v1/2022-05-08"; hdir.mkdir(parents=True)
        hmanifest = hdir / "run_manifest.json"; hmanifest.write_text(json.dumps(self.history_meta, indent=2) + "\n")
        hsha = hashlib.sha256(canonical(self.history_meta)).hexdigest()
        (hdir / "result.json").write_text(json.dumps({"publication": {"manifest_sha256": hsha}, "database": {"manifest_sha256": hsha, "execution_id": "hist-e"}}))
        self.metadata = {"executions": [
            {"dataset": "snapshot-reference", "status": "PUBLISHED", "run_prefix": "data/snapshot/ref", "manifest_sha256": candidate_sha, "input_metadata": {"candidate": candidate}},
            {"dataset": "package-snapshot", "status": "PUBLISHED", "snapshot_at": "2026-08-31", "execution_id": "base-e", "manifest_sha256": bsha, "input_metadata": self.base_meta},
            {"dataset": "package-snapshot", "status": "PUBLISHED", "snapshot_at": "2022-05-08", "execution_id": "hist-e", "manifest_sha256": hsha, "input_metadata": self.history_meta},]}
        self.plan = {"dates": ["2022-05-08", "2026-08-31"], "generation": {"x.py": "abc"}, "source_run_dir": "source/run", "source_run_manifest_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}

    def tearDown(self): self.tmp.cleanup()

    def _bind(self):
        policy = types.ModuleType("pipeline.preprocessing.package_snapshot.policy"); policy.canonical_bytes = canonical
        reload_mod = types.ModuleType("pipeline.postgresql.version_dependents.historical_db_reload"); reload_mod.validate_generation = lambda value: None; reload_mod.contract = lambda: self.plan["generation"]
        with patch.dict(sys.modules, {"pipeline.preprocessing.package_snapshot.policy": policy, "pipeline.postgresql.version_dependents.historical_db_reload": reload_mod}):
            return bind_sources(self.root, self.metadata, self.plan)

    def test_all_bindings_pass_and_return_two_results(self):
        result = self._bind(); self.assertEqual(result["status"], "BOUND_WITH_DEFERRED"); self.assertEqual(len(result["package_snapshot_results"]), 2); self.assertTrue(all(c["status"] == "PASS" for c in result["checks"]))

    def test_canonical_manifest_tamper_fails(self):
        p = self.root / "data/package_snapshot/history/full-history-288-20260909-v1/2022-05-08/run_manifest.json"; p.write_text(json.dumps({**self.history_meta, "counts": {"package_snapshot": 2}}, indent=2) + "\n")
        self.assertEqual(self._bind()["status"], "FAILED")

    def test_incomplete_source_with_matching_sha_fails(self):
        path = self.root / "source/run/run_manifest.json"
        path.write_text('{"run_status":"FAILED","full_selection_executed":false}')
        self.plan["source_run_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        result = self._bind()
        check = next(c for c in result["checks"] if c["name"] == "pinned_source_run_manifest")
        self.assertEqual(check["status"], "FAIL")

    def test_input_metadata_mismatch_fails(self):
        self.metadata["executions"][2]["input_metadata"] = {"different": True}; self.assertEqual(self._bind()["status"], "FAILED")

    def test_receipt_sha_fails(self):
        p = self.root / "data/package_snapshot/history/full-history-288-20260909-v1/2022-05-08/result.json"; p.write_text(json.dumps({"publication": {"manifest_sha256": "bad"}, "database": {"manifest_sha256": "bad", "execution_id": "hist-e"}})); self.assertEqual(self._bind()["status"], "FAILED")

    def test_candidate_file_tamper_and_missing_pin_fail(self):
        (self.root / "data/snapshot/ref/projects-inventory.json").write_bytes(b"tampered"); self.assertEqual(self._bind()["status"], "FAILED")
        self.tearDown(); self.setUp(); del self.metadata["executions"][0]["input_metadata"]["candidate"]; self.assertEqual(self._bind()["status"], "FAILED")

    def test_base_manifest_and_source_anchor_fail(self):
        (self.root / "data/package_snapshot/curated/base/run_manifest.json").write_text('{"tampered":true}'); self.assertEqual(self._bind()["status"], "FAILED")
        self.tearDown(); self.setUp(); self.plan.pop("source_run_dir"); self.assertEqual(self._bind()["status"], "FAILED")

    def test_traversal_and_symlink_are_rejected(self):
        with self.assertRaises(ValueError): _safe_path(self.root, "../outside.json")
        link = self.root / "link.json"
        try: link.symlink_to(self.root / "source/run/run_manifest.json")
        except (OSError, NotImplementedError): self.skipTest("symlink unavailable")
        with self.assertRaises(ValueError): _safe_path(self.root, "link.json")


if __name__ == "__main__": unittest.main()
