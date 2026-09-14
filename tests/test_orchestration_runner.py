"""Failure-injection tests for orchestration, separate from real transform tests."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pipeline.curated.storage import json_bytes, put_immutable
from pipeline.downloads.test_bronze import FakeS3
from pipeline.orchestration import runner
from pipeline.orchestration.contracts import STAGES, validate_request
from pipeline.orchestration.storage import BUCKET, WaitingInput, StageClient, host_lock, sha


def request_fixture():
    snapshot, bronze = "2026-08-31", "raw-test"
    raw = {table: {"bucket": "pickage-raw", "key":
           f"depsdev/v1/{table}/snapshot={snapshot}/run_id={bronze}/run_manifest.json", "sha256": "a" * 64}
           for table in ("versions_full", "requirements", "projects")}
    raw["downloads"] = {"bucket": "pickage-raw", "run_id": "dl-test", "sha256": "b" * 64,
                         "key": "npm-downloads/v1/run_id=dl-test/run_manifest.json"}
    return {"format_version": 1, "run_id": "run-test", "snapshot": snapshot,
            "snapshot_timestamp": snapshot + "T21:00:00Z", "bronze_run_id": bronze,
            "raw_refs": raw, "calendar_refs": [{**raw["projects"], "snapshot": snapshot, "run_id": bronze}],
            "parent": None, "targets": {"dependents": {"bucket": "pickage-raw",
                "key": "targets/test.parquet", "sha256": "c" * 64}}, "options": {"workers": 1}}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s3, self.request, self.calls = FakeS3(), request_fixture(), []
        self.s3.meta = SimpleNamespace(endpoint_url="memory://" + self.temp.name)
        # Other independently edited modules must not change this test's synthetic contract.
        self.contract_patch = patch.object(runner, "code_contract", return_value={"test": "fixed"})
        self.contract_patch.start()
        self.addCleanup(self.contract_patch.stop)

    def execute(self, name, request, completed, s3, work_dir):
        self.calls.append(name)
        prefix = runner.run_prefix(request) + "/test-data/" + name
        content = (name + ": fixture output").encode()
        record = {"key": prefix + "/output.parquet", "bytes": len(content), "sha256": sha(content)}
        body = json_bytes({"status": "PASSED", "files": [record]})
        marker = json_bytes({"manifest_sha256": sha(body)})
        for suffix, value in (("/output.parquet", content), ("/run_manifest.json", body), ("/_SUCCESS", marker)):
            put_immutable(s3, BUCKET, prefix + suffix, value)
        return {"stage": name, "run_id": request["run_id"], "snapshot": request["snapshot"],
                "bucket": BUCKET, "prefix": prefix, "manifest_key": prefix + "/run_manifest.json",
                "manifest_sha256": sha(body), "marker_key": prefix + "/_SUCCESS", "marker_sha256": sha(marker),
                "files": [record], "quality": {"status": "PASSED"}}

    def run_pipeline(self, **kwargs):
        return runner.run(self.request, self.s3, self.temp.name, _executor=self.execute,
                          _preflight=lambda *args: None, **kwargs)

    def test_completed_run_reverifies_without_stage_execution(self):
        first = self.run_pipeline()
        self.assertEqual(self.calls, list(STAGES))
        self.calls.clear()
        self.assertEqual(self.run_pipeline(resume=True), first)
        self.assertEqual(self.calls, [])
        self.assertFalse(first["db_loaded"])

    def test_windows_long_output_path_rejected_before_execution(self):
        with patch.object(runner.sys, "platform", "win32"):
            runner._validate_work_path(Path("C:/w/r"), "r")
            with self.assertRaisesRegex(ValueError, "shorter --work-dir"):
                runner._validate_work_path(Path("C:/") / ("x" * 200), "r")

    def test_same_snapshot_id_parent_allows_new_run_after_code_change(self):
        request = copy.deepcopy(self.request)
        request["parent"] = {"run_prefix": "depsdev/v1/package-version/snapshot=2026-08-31/run_id=previous-attempt",
                             "snapshot": "2026-08-31", "manifest_sha256": "d" * 64}
        self.assertEqual(validate_request(request), request)
        request["parent"]["snapshot"] = "2026-09-01"
        with self.assertRaisesRegex(ValueError, "newer"):
            validate_request(request)

    def test_stage_failure_and_restart_skip_completed_stages(self):
        def fail(point):
            if point == "before_stage:repository":
                raise RuntimeError("injected interruption")
        with self.assertRaisesRegex(RuntimeError, "interruption"):
            self.run_pipeline(failpoint=fail)
        self.assertNotIn((BUCKET, runner.run_prefix(self.request) + "/_SUCCESS"), self.s3.objects)
        self.calls.clear()
        self.run_pipeline(resume=True)
        self.assertEqual(self.calls, ["repository", "package_snapshot", "dependents"])
        state = runner.status(self.request, self.s3)
        self.assertEqual(state["status"], "COMPLETE")
        self.assertEqual(state["stages"]["repository"]["attempt"], 2)

    def test_recovery_after_stage_published_before_checkpoint(self):
        def fail(point):
            if point == "after_stage:package_version":
                raise RuntimeError("stage published")
        with self.assertRaisesRegex(RuntimeError, "published"):
            self.run_pipeline(failpoint=fail)
        self.calls.clear()
        self.run_pipeline(resume=True)
        self.assertNotIn("snapshot", self.calls)
        self.assertEqual(self.calls[0], "package_version")

    def test_foreign_run_checkpoint_rejected_before_reuse(self):
        def fail(point):
            if point == "before_stage:package_version":
                raise RuntimeError("pause after snapshot")
        with self.assertRaisesRegex(RuntimeError, "pause"):
            self.run_pipeline(failpoint=fail)
        key = runner.run_prefix(self.request) + "/stages/snapshot.json"
        descriptor = json.loads(self.s3.objects[(BUCKET, key)])
        descriptor["run_id"] = "another-run"
        self.s3.objects[(BUCKET, key)] = json_bytes(descriptor)
        self.calls.clear()
        with self.assertRaisesRegex(ValueError, "checkpoint identity"):
            self.run_pipeline(resume=True)
        self.assertEqual(self.calls, [])

    def test_bundle_manifest_then_marker_crash_is_recoverable(self):
        def fail(point):
            if point == "before_bundle_marker":
                raise RuntimeError("marker interruption")
        with self.assertRaises(RuntimeError):
            self.run_pipeline(failpoint=fail)
        prefix = runner.run_prefix(self.request)
        self.assertIn((BUCKET, prefix + "/run_manifest.json"), self.s3.objects)
        self.assertNotIn((BUCKET, prefix + "/_SUCCESS"), self.s3.objects)
        self.calls.clear()
        self.run_pipeline(resume=True)
        self.assertEqual(self.calls, [])

    def test_marker_wins_over_stale_failed_state(self):
        def fail(point):
            if point == "after_bundle_marker":
                raise RuntimeError("status interruption")
        with self.assertRaises(RuntimeError):
            self.run_pipeline(failpoint=fail)
        self.assertEqual(runner.status(self.request, self.s3)["status"], "COMPLETE")
        self.run_pipeline(resume=True)

    def test_changed_inputs_and_code_cannot_reuse_run(self):
        self.run_pipeline()
        self.request["targets"]["dependents"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "different inputs"):
            self.run_pipeline(resume=True)
        self.request = request_fixture()
        with patch.object(runner, "code_contract", return_value={"test": "changed"}):
            with self.assertRaisesRegex(ValueError, "different inputs"):
                self.run_pipeline(resume=True)

    def test_corrupt_output_blocks_resume(self):
        bundle = self.run_pipeline()
        record = bundle["stages"]["downloads"]["files"][0]
        self.s3.objects[(BUCKET, record["key"])] = b"corrupt"
        with self.assertRaisesRegex(ValueError, "verification failed"):
            self.run_pipeline(resume=True)

    def test_completed_bundle_reverifies_without_requiring_old_parent_current(self):
        bundle = self.run_pipeline()
        def no_new_input_check(*args):
            self.fail("Completed historical bundle must not require its parent to remain current")
        self.assertEqual(runner.run(self.request, self.s3, self.temp.name, resume=True,
                                   _preflight=no_new_input_check), bundle)

    def test_missing_input_gets_waiting_state(self):
        def missing(*args):
            raise WaitingInput("required marker missing")
        with self.assertRaises(WaitingInput):
            runner.run(self.request, self.s3, self.temp.name, _preflight=missing)
        self.assertEqual(runner.status(self.request, self.s3)["status"], "WAITING_INPUT")

    def test_unknown_resume_does_not_create_request(self):
        with self.assertRaisesRegex(ValueError, "unknown run"):
            self.run_pipeline(resume=True)
        self.assertEqual(self.s3.objects, {})

    def test_other_work_directory_is_rejected(self):
        self.run_pipeline()
        with self.assertRaisesRegex(ValueError, "work directory"):
            runner.run(self.request, self.s3, Path(self.temp.name) / "elsewhere", resume=True)

    def test_same_host_writer_lock_is_exclusive(self):
        with host_lock(self.s3):
            with self.assertRaisesRegex(ValueError, "Another Curated"):
                with host_lock(self.s3):
                    self.fail("second writer entered")
        with host_lock(self.s3):
            pass


class ContractTests(unittest.TestCase):
    def test_mixed_calendar_and_identity_rejected(self):
        request = request_fixture()
        request["calendar_refs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "same pinned"):
            validate_request(request)

    def test_unknown_field_rejected(self):
        request = request_fixture()
        request["db_password"] = "unexpected"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_request(request)

    def test_wrong_snapshot_timestamp_rejected(self):
        request = request_fixture()
        request["snapshot_timestamp"] = "2026-08-30T23:00:00Z"
        with self.assertRaises(ValueError):
            validate_request(request)


class AbandonedLockTests(unittest.TestCase):
    def test_only_this_runs_exact_native_lock_is_recovered(self):
        from tests.orchestration_fixture import FakeS3 as ConditionalS3
        with tempfile.TemporaryDirectory() as root:
            s3 = ConditionalS3()
            s3.meta = SimpleNamespace(endpoint_url="memory://" + root)
            client = StageClient(s3, root, request_fixture())
            key = "depsdev/v1/package-version/_writer.lock"
            body = json_bytes({"owner": "this-run", "token": "old-process"})
            client.put_object(Bucket=BUCKET, Key=key, Body=body, IfNoneMatch="*")
            # Simulate a killed process: its context manager never released this token.
            with host_lock(s3):
                self.assertEqual(StageClient(s3, root, request_fixture()).recover(), [key])
            foreign = json_bytes({"owner": "another-run", "token": "different"})
            s3.put_object(Bucket=BUCKET, Key=key, Body=foreign, IfNoneMatch="*")
            with host_lock(s3):
                self.assertEqual(client.recover(), [])
            self.assertEqual(s3.objects[(BUCKET, key)], foreign)


if __name__ == "__main__":
    unittest.main()
