import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.preprocessing.runtime import recover_dependents as recovery
from pipeline.preprocessing.runtime import recover_repository as repository_recovery
from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import make_fixture


class DependentsRecoveryTests(unittest.TestCase):
    def test_contract_allows_only_dependents_generators(self):
        old = {"runtime": {"python": [3, 12]}, "files": {
            "pipeline/preprocessing/orchestration/dependents_parallel.py": "a",
            "pipeline/preprocessing/version_dependents/historical_input.py": "a",
        }}
        new = copy.deepcopy(old)
        new["files"]["pipeline/preprocessing/orchestration/dependents_parallel.py"] = "b"
        self.assertEqual(recovery._changed_files(old, new),
                         ["pipeline/preprocessing/orchestration/dependents_parallel.py"])
        for path in ("pipeline/preprocessing/version_dependents/historical_production_events.py",
                     "pipeline/preprocessing/version_dependents/historical_parallel_input.py"):
            old["files"][path] = "a"
            new["files"][path] = "b"
        self.assertEqual(len(recovery._changed_files(old, new)), 3)
        new["files"]["pipeline/preprocessing/curated/transform.py"] = "x"
        with self.assertRaisesRegex(ValueError, "unapproved"):
            recovery._changed_files(old, new)

    def test_receipt_pins_predecessor_and_all_retained_checkpoints(self):
        request = {"run_id": "run", "snapshot": "2026-08-31"}
        old = {"runtime": {}, "files": {}}
        new = {"runtime": {}, "files": {}}
        hashes = {name: name * 64 for name in recovery.RETAINED_STAGES}
        with patch.object(recovery, "file_sha256", return_value="f" * 64):
            key, body = recovery._receipt(request, b"envelope", b'{"recovery_id":"repository-bounded-v1"}',
                                           "a" * 64, old, new, hashes)
        self.assertTrue(key.endswith("dependents-bounded-v2.json"))
        receipt = json.loads(body)
        self.assertEqual(receipt["predecessor_receipt_sha256"], "a" * 64)
        self.assertEqual(receipt["retained_checkpoints"], hashes)

    def test_real_predecessor_failure_retry_publication_and_replay(self):
        with tempfile.TemporaryDirectory(prefix="dr-", dir="C:/" if os.name == "nt" else None) as folder:
            fixture = make_fixture(Path(folder) / "fixture")
            s3, request = fixture.s3, fixture.request
            request["options"].update(work_cleanup="stage", repository_engine="duckdb",
                repository_max_temp_directory_size="128MB", dependents_max_temp_size="128MB")
            work = Path(folder) / "w"
            original_executor = runner._default_executor
            contract = recovery.code_contract()
            initial = copy.deepcopy(contract)
            initial["files"][repository_recovery.ALLOWED_GENERATOR] = "0" * 64
            def first_failure(point):
                if point == "before_stage:repository": raise RuntimeError("first repository failure")
            with patch.object(runner, "code_contract", return_value=initial):
                with self.assertRaisesRegex(RuntimeError, "first repository failure"):
                    runner.run(request, s3, work, failpoint=first_failure)
            def predecessor_executor(name, *args):
                if name == "dependents": raise RuntimeError("original dependents failure")
                return original_executor(name, *args)
            with self.assertRaisesRegex(RuntimeError, "original dependents failure"):
                repository_recovery.recover(request, s3, work, _executor=predecessor_executor)
            prefix = runner.run_prefix(request)
            keys = [prefix + "/request.json", prefix + "/recoveries/repository-bounded-v1.json"]
            keys += [prefix + "/stages/" + name + ".json" for name in recovery.RETAINED_STAGES]
            retained = {key: s3.objects[("pickage-curated", key)] for key in keys}
            current = copy.deepcopy(contract)
            current["files"]["pipeline/preprocessing/orchestration/dependents_parallel.py"] = "1" * 64
            calls = []
            def failed_executor(name, *args):
                calls.append(name)
                raise RuntimeError("tail failure")
            def tracked_executor(name, *args):
                calls.append(name)
                return original_executor(name, *args)
            with patch.object(recovery, "code_contract", return_value=current):
                with self.assertRaisesRegex(RuntimeError, "tail failure"):
                    recovery.recover(request, s3, work, _executor=failed_executor)
                failed = json.loads(s3.objects[("pickage-curated", prefix + "/status.json")])
                self.assertEqual(failed["stages"]["dependents"]["status"], "FAILED")
                self.assertEqual(failed["stages"]["repository"]["status"], "COMPLETE")
                self.assertNotIn(("pickage-curated", prefix + "/_SUCCESS"), s3.objects)
                calls.clear()
                downloads = json.loads(retained[prefix + "/stages/downloads.json"])
                manifest_key = (downloads["bucket"], downloads["manifest_key"])
                original_manifest = s3.objects[manifest_key]
                def changed_retained_executor(name, *args):
                    result = tracked_executor(name, *args)
                    s3.objects[manifest_key] = b'{"status":"COMPLETE","changed":true}'
                    return result
                with self.assertRaisesRegex(ValueError, "Stage manifest changed"):
                    recovery.recover(request, s3, work, _executor=changed_retained_executor)
                self.assertEqual(calls, ["dependents"])
                self.assertNotIn(("pickage-curated", prefix + "/_SUCCESS"), s3.objects)
                s3.objects[manifest_key] = original_manifest
                calls.clear()
                with patch.object(recovery, "publish_current", side_effect=RuntimeError("publication interrupted")):
                    with self.assertRaisesRegex(RuntimeError, "publication interrupted"):
                        recovery.recover(request, s3, work, _executor=tracked_executor)
                self.assertEqual(calls, [])
                self.assertIn(("pickage-curated", prefix + "/_SUCCESS"), s3.objects)
                failed = json.loads(s3.objects[("pickage-curated", prefix + "/status.json")])
                self.assertEqual(failed["status"], "FAILED")
                result = recovery.recover(request, s3, work,
                    _executor=lambda *args: (_ for _ in ()).throw(AssertionError("tail executed again")))
                self.assertEqual(result["status"], "COMPLETE")
                status = json.loads(s3.objects[("pickage-curated", prefix + "/status.json")])
                self.assertEqual(status["status"], "COMPLETE")
                self.assertEqual(status["stages"]["dependents"]["status"], "COMPLETE")
                pointer = json.loads(s3.objects[("pickage-curated", "depsdev/v1/curated-bundle/_current.json")])
                self.assertEqual(pointer["run_prefix"], prefix)
                for key, body in retained.items(): self.assertEqual(s3.objects[("pickage-curated", key)], body)
                replay = recovery.recover(request, s3, work,
                    _executor=lambda *args: (_ for _ in ()).throw(AssertionError("tail executed again")))
                self.assertEqual(replay, result)
                checkpoint_key = ("pickage-curated", prefix + "/stages/dependents.json")
                changed = json.loads(s3.objects[checkpoint_key])
                changed["metadata"]["unexpected"] = True
                s3.objects[checkpoint_key] = recovery.json_bytes(changed)
                with self.assertRaisesRegex(ValueError, "checkpoint differs from bundle"):
                    recovery.recover(request, s3, work)

    def test_recover_executes_only_dependents_and_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = make_fixture(Path(folder) / "fixture")
            request = fixture.request
            prefix = runner.run_prefix(request)
            local = Path(folder) / "work" / request["run_id"]
            envelope = {"request": request, "code_contract": {"runtime": {}, "files": {}},
                        "work_dir": str(local.resolve())}
            fixture.s3.put_object(Bucket="pickage-curated", Key=prefix + "/request.json",
                                  Body=recovery.json_bytes(envelope))
            predecessor_key = prefix + "/recoveries/repository-bounded-v1.json"
            predecessor = {"recovery_id": "repository-bounded-v1", "request": request,
                           "original_envelope_sha256": recovery.sha(recovery.json_bytes(envelope)),
                           "original_code_contract": envelope["code_contract"],
                           "new_code_contract": {"runtime": {}, "files": {}},
                           "helper_sha256": "h" * 64,
                           "checkpoints": {name: "x" * 64 for name in ("snapshot", "package_version", "downloads")}}
            predecessor_body = recovery.json_bytes(predecessor)
            fixture.s3.put_object(Bucket="pickage-curated", Key=predecessor_key, Body=predecessor_body)
            descriptors = {}
            bodies = {}
            for name in recovery.RETAINED_STAGES:
                descriptor = {"stage": name, "run_id": request["run_id"], "snapshot": request["snapshot"],
                              "recovery": {"key": predecessor_key, "sha256": recovery.sha(predecessor_body)} if name in ("repository", "package_snapshot") else None}
                body = recovery.json_bytes(descriptor)
                descriptors[name], bodies[name] = descriptor, body
            hashes = {name: recovery.sha(body) for name, body in bodies.items()}
            predecessor["checkpoints"] = {name: hashes[name] for name in ("snapshot", "package_version", "downloads")}
            predecessor_body = recovery.json_bytes(predecessor)
            fixture.s3.objects[("pickage-curated", predecessor_key)] = predecessor_body
            predecessor_ref = {"key": predecessor_key, "sha256": recovery.sha(predecessor_body)}
            for name in ("repository", "package_snapshot"):
                descriptors[name]["recovery"] = predecessor_ref
                bodies[name] = recovery.json_bytes(descriptors[name])
            for name, body in bodies.items():
                fixture.s3.put_object(Bucket="pickage-curated", Key=f"{prefix}/stages/{name}.json", Body=body)
            calls = []
            def checkpoint(_s3, _prefix, name, _request, _workers):
                return bodies[name], descriptors[name]
            def executor(name, *_args):
                calls.append(name)
                return {"stage": "dependents", "run_id": request["run_id"], "snapshot": request["snapshot"],
                        "bucket": "pickage-curated", "manifest_key": "dependents", "manifest_sha256": "a" * 64,
                        "marker_key": "dependents/_SUCCESS", "marker_sha256": "b" * 64,
                        "files": [{"key": "dependents/file", "bytes": 1, "sha256": "c" * 64}]}
            with patch.object(recovery, "_checkpoint", side_effect=checkpoint), \
                 patch.object(recovery, "verify_descriptor"), \
                 patch.object(recovery, "pinned"), \
                 patch.object(recovery, "file_sha256", side_effect=lambda _path: "h" * 64), \
                 patch.object(recovery, "code_contract", return_value={"runtime": {}, "files": {}}), \
                 patch.object(recovery, "publish_current"):
                result = recovery.recover(request, fixture.s3, Path(folder) / "work", _executor=executor)
            self.assertEqual(calls, ["dependents"])
            self.assertEqual(result["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
