import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.runtime import recover_repository as recovery
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import FakeS3, make_fixture


class RepositoryRecoveryTests(unittest.TestCase):
    def test_snapshot_metadata_must_stay_inside_claimed_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "run"
            workspace.mkdir()
            snapshot = {"metadata": {
                "candidate_path": str(workspace / "candidate.json"),
                "projects_dir": str(Path(folder) / "outside"),
            }}
            with self.assertRaisesRegex(ValueError, "escapes recovery workspace"):
                recovery._validate_snapshot_metadata(snapshot, workspace)

    def test_dangling_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            link = workspace / "linked"
            try:
                link.symlink_to(workspace / "missing", target_is_directory=True)
            except OSError as error:
                self.skipTest(str(error))
            with self.assertRaisesRegex(ValueError, "symlink"):
                recovery._workspace_path(link / "candidate.json", workspace, "candidate")

    def test_footer_mismatch_does_not_restore_mtime(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "run"
            projects = workspace / "projects"
            projects.mkdir(parents=True)
            candidate = workspace / "snapshot-candidate.json"
            candidate.write_text("{}")
            project = projects / "part.parquet"
            con = duckdb.connect()
            try:
                con.execute("CREATE TABLE t AS SELECT 1 AS package_id")
                con.execute("COPY t TO ? (FORMAT PARQUET)", [str(project)])
            finally:
                con.close()
            inventory = {"snapshots": [{"files": [{"path": "part.parquet", "bytes": project.stat().st_size,
                                                       "mtime_ns": 123456789, "parquet_footer_sha256": "0" * 64}]}]}
            (workspace / "projects-inventory.json").write_text(json.dumps(inventory))
            snapshot = {"metadata": {"candidate_path": str(candidate), "projects_dir": str(projects)}}
            with patch.object(recovery.os, "utime") as utime:
                recovery._restore_project_mtimes(snapshot, workspace)
            utime.assert_not_called()
            inventory["snapshots"][0]["files"][0]["path"] = "../outside.parquet"
            (workspace / "projects-inventory.json").write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "escapes projects directory"):
                recovery._restore_project_mtimes(snapshot, workspace)

    def test_contract_gate_rejects_runtime_and_unrelated_changes(self):
        old = {"runtime": {"python": [3, 12, 0]}, "files": {recovery.ALLOWED_GENERATOR: "a", "other.py": "a"}}
        with self.assertRaisesRegex(ValueError, "runtime differs"):
            recovery._contract_changes(old, {"runtime": {"python": [3, 12, 1]}, "files": old["files"]})
        with self.assertRaisesRegex(ValueError, "reviewed repository"):
            recovery._contract_changes(
                {"runtime": old["runtime"], "files": {"other.py": "a"}},
                {"runtime": old["runtime"], "files": {"other.py": "b"}},
            )

    def test_recovery_pins_three_checkpoints_and_replays_without_executor(self):
        self._run_mock_recovery()

    def test_checkpoint_mutated_during_execution_prevents_publication(self):
        self._run_mock_recovery(mutate=True)

    def _run_mock_recovery(self, mutate=False):
        with tempfile.TemporaryDirectory(prefix="repository-recovery-") as folder:
            fixture = make_fixture(Path(folder) / "fixture")
            request = fixture.request
            s3 = fixture.s3
            local = Path(folder) / "work" / request["run_id"]
            prefix = runner.run_prefix(request)
            old_contract = {"runtime": {"python": [3, 12, 0]}, "files": {recovery.ALLOWED_GENERATOR: "old"}}
            new_contract = {"runtime": old_contract["runtime"], "files": {recovery.ALLOWED_GENERATOR: "new"}}
            envelope = {"request": request, "code_contract": old_contract, "work_dir": str(local.resolve())}
            s3.put_object(Bucket="pickage-curated", Key=prefix + "/request.json",
                          Body=json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode())
            descriptors = {}
            for name in recovery.RETAINED_STAGES:
                descriptor = {"stage": name, "run_id": request["run_id"], "snapshot": request["snapshot"],
                              "bucket": "pickage-curated", "manifest_key": name, "manifest_sha256": "a" * 64,
                              "marker_key": name + "/_SUCCESS", "marker_sha256": "b" * 64, "files": [{"key": name, "bytes": 1, "sha256": "c" * 64}]}
                descriptors[name] = descriptor

            calls = []
            def executor(name, req, completed, client, work):
                calls.append(name)
                if name == "snapshot":
                    return descriptors[name]
                if name == "dependents" and mutate:
                    key = ("pickage-curated", prefix + "/stages/snapshot.json")
                    s3.objects[key] += b" "
                return {"stage": name, "run_id": req["run_id"], "snapshot": req["snapshot"],
                        "bucket": "pickage-curated", "manifest_key": name, "manifest_sha256": "a" * 64,
                        "marker_key": name + "/_SUCCESS", "marker_sha256": "b" * 64,
                        "files": [{"key": name, "bytes": 1, "sha256": "c" * 64}]}

            def checkpoint(_s3, _prefix, name, _request, _workers):
                body = json.dumps(descriptors[name], sort_keys=True, separators=(",", ":")).encode()
                _s3.put_object(Bucket="pickage-curated", Key=_prefix + "/stages/" + name + ".json", Body=body)
                return body, copy.deepcopy(descriptors[name])

            with patch.object(recovery, "code_contract", return_value=new_contract), \
                 patch.object(recovery, "file_sha256", return_value="d" * 64), \
                 patch.object(recovery, "_checkpoint", side_effect=checkpoint), \
                 patch.object(recovery, "verify_descriptor"), \
                 patch.object(recovery, "_receipt", wraps=recovery._receipt), \
                 patch.object(recovery, "publish_current", wraps=recovery.publish_current) as publish_current_mock:
                if mutate:
                    with self.assertRaisesRegex(ValueError, "changed during recovery"):
                        recovery.recover(request, s3, Path(folder) / "work",
                                         _executor=executor, _preflight=lambda *_: None)
                    self.assertNotIn(("pickage-curated", prefix + "/_SUCCESS"), s3.objects)
                    self.assertNotIn(("pickage-curated", prefix + "/run_manifest.json"), s3.objects)
                    publish_current_mock.assert_not_called()
                    return
                result = recovery.recover(request, s3, Path(folder) / "work",
                                          _executor=executor, _preflight=lambda *_: None)
                self.assertEqual(calls, ["snapshot", "repository", "package_snapshot", "dependents"])
                original = s3.objects[("pickage-curated", prefix + "/request.json")]
                receipt_key = prefix + "/recoveries/" + recovery.RECOVERY_ID + ".json"
                receipt = json.loads(s3.objects[("pickage-curated", receipt_key)])
                self.assertEqual(receipt["checkpoints"].keys(), set(recovery.RETAINED_STAGES))
                self.assertEqual(s3.objects[("pickage-curated", prefix + "/request.json")], original)

                calls.clear()
                replay = recovery.recover(request, s3, Path(folder) / "work",
                                          _executor=lambda *args: (_ for _ in ()).throw(AssertionError("replayed")),
                                          _preflight=lambda *_: (_ for _ in ()).throw(AssertionError("replayed")))
                self.assertEqual(replay["status"], "COMPLETE")
                self.assertEqual(calls, [])
                self.assertEqual(publish_current_mock.call_count, 2)

                incomplete = copy.deepcopy(replay)
                incomplete["stages"].pop("dependents")
                incomplete_body = recovery.json_bytes(incomplete)
                s3.objects[("pickage-curated", prefix + "/run_manifest.json")] = incomplete_body
                s3.objects[("pickage-curated", prefix + "/_SUCCESS")] = recovery.json_bytes(
                    {"manifest_sha256": recovery.sha(incomplete_body)})
                with self.assertRaisesRegex(ValueError, "differs from pinned recovery"):
                    recovery.recover(request, s3, Path(folder) / "work",
                                     _executor=lambda *args: (_ for _ in ()).throw(AssertionError("replayed")),
                                     _preflight=lambda *_: (_ for _ in ()).throw(AssertionError("replayed")))

    def test_checkpoint_tamper_changes_pinned_receipt_bytes(self):
        request = {"format_version": 1, "run_id": "run", "snapshot": "2026-08-31",
                   "snapshot_timestamp": "2026-08-31T00:00:00Z", "bronze_run_id": "bronze",
                   "raw_refs": {}, "calendar_refs": [], "parent": None, "targets": {}}
        old = {"runtime": {"python": [3, 12, 0]}, "files": {recovery.ALLOWED_GENERATOR: "a"}}
        new = copy.deepcopy(old)
        with patch.object(recovery, "_contract_changes", return_value=[]):
            _key, first = recovery._receipt(request, b"envelope", {"code_contract": old}, new, {"snapshot": "a"})
            _key, tampered = recovery._receipt(request, b"envelope", {"code_contract": old}, new, {"snapshot": "b"})
        self.assertNotEqual(first, tampered)

    def test_real_fixture_recovery_reuses_first_three_remote_checkpoints(self):
        with tempfile.TemporaryDirectory(prefix="rr-", dir="C:/" if os.name == "nt" else None) as folder:
            fixture = make_fixture(Path(folder) / "fixture")
            request = fixture.request
            request["options"].update({"work_cleanup": "stage", "repository_engine": "duckdb",
                                       "repository_max_temp_directory_size": "1GB",
                                       "dependents_max_temp_size": "1GB"})
            s3 = fixture.s3
            work = Path(folder) / "w"
            actual_contract = recovery.code_contract()
            original_contract = copy.deepcopy(actual_contract)
            original_contract["files"] = dict(original_contract["files"])
            original_contract["files"][recovery.ALLOWED_GENERATOR] = "0" * 64
            original_executor = runner._default_executor

            def fail_before_repository(point):
                if point == "before_stage:repository":
                    raise RuntimeError("repository fixture failure")

            with patch.object(runner, "code_contract", return_value=original_contract), \
                 patch.object(recovery, "code_contract", return_value=actual_contract):
                with self.assertRaisesRegex(RuntimeError, "repository fixture failure"):
                    runner.run(request, s3, work, failpoint=fail_before_repository)

            prefix = runner.run_prefix(request)
            original_envelope = s3.objects[("pickage-curated", prefix + "/request.json")]
            original_checkpoints = {
                name: s3.objects[("pickage-curated", prefix + "/stages/" + name + ".json")]
                for name in recovery.RETAINED_STAGES
            }
            calls = []

            def tracked_executor(name, *args):
                calls.append(name)
                return original_executor(name, *args)

            failed_once = {"value": False}
            def fail_once_executor(name, *args):
                calls.append(name)
                if name == "repository" and not failed_once["value"]:
                    failed_once["value"] = True
                    raise RuntimeError("bounded repository retry")
                return original_executor(name, *args)

            with patch.object(runner, "_default_executor", side_effect=fail_once_executor):
                with self.assertRaisesRegex(RuntimeError, "bounded repository retry"):
                    recovery.recover(request, s3, work)
            calls.clear()
            with patch.object(runner, "_default_executor", side_effect=tracked_executor):
                bundle = recovery.recover(request, s3, work)
            self.assertEqual(set(bundle["stages"]), set(runner.STAGES))
            self.assertEqual(calls[0], "snapshot")
            self.assertNotIn("package_version", calls)
            self.assertNotIn("downloads", calls)
            self.assertEqual(s3.objects[("pickage-curated", prefix + "/request.json")], original_envelope)
            for name, body in original_checkpoints.items():
                self.assertEqual(s3.objects[("pickage-curated", prefix + "/stages/" + name + ".json")], body)
            self.assertIn("repository", calls)
            self.assertIn("package_snapshot", calls)
            self.assertIn("dependents", calls)

            changed_checkpoint = recovery.json_bytes({"tampered": True})
            s3.objects[("pickage-curated", prefix + "/stages/snapshot.json")] = changed_checkpoint
            with self.assertRaisesRegex(ValueError, "differs"):
                recovery.recover(request, s3, work,
                                 _executor=lambda *args: (_ for _ in ()).throw(AssertionError("replayed")))
            s3.objects[("pickage-curated", prefix + "/stages/snapshot.json")] = original_checkpoints["snapshot"]

            with patch.object(runner, "_default_executor", side_effect=AssertionError("recovery replayed")):
                replay = recovery.recover(request, s3, work)
            self.assertEqual(replay["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
