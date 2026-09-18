"""State-machine tests for the weekly raw-to-Curated dispatcher."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from botocore.exceptions import ClientError

from pipeline.preprocessing.orchestration import dispatcher
from pipeline.preprocessing.orchestration.storage import BUCKET, PipelineBusy, WaitingInput, sha


class _Pages:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        return iter(self.pages)


class MemoryS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        try:
            body = self.objects[(Bucket, Key)]
        except KeyError:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(body), "ETag": '"etag"'}

    def put_object(self, Bucket, Key, Body, **kwargs):
        body = Body if isinstance(Body, bytes) else Body.read()
        if kwargs.get("IfNoneMatch") == "*" and (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[(Bucket, Key)] = body

    def get_paginator(self, name):
        contents = [{"Key": key} for bucket, key in self.objects if bucket == "pickage-raw"]
        return _Pages([{"Contents": contents}])

    def put_json(self, bucket, key, value):
        self.objects[(bucket, key)] = json.dumps(value, sort_keys=True).encode()

    def json(self, bucket, key):
        return json.loads(self.objects[(bucket, key)])


class PagedMemoryS3(MemoryS3):
    def get_paginator(self, name):
        contents = [{"Key": key} for bucket, key in self.objects if bucket == "pickage-raw"]
        return _Pages([{"Contents": contents[:1]}, {"Contents": contents[1:]}])


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dispatcher-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.s3 = MemoryS3()
        self.now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        self.base = "2026-09-07"
        self.week = "2026-09-14"
        self.history = {self.base: {"snapshot": self.base, "raw_refs": {}}}
        self.raw = {self.week: {"status": "SUCCEEDED"}}
        self.request = {"snapshot": self.week, "run_id": "curated-weekly-20260914", "raw_refs": {}}

    def _dispatch(self, *, history=None, weeks=None, request=None, **patches):
        values = {
            "_history": lambda s3: history if history is not None else self.history,
            "_documents": lambda s3: weeks if weeks is not None else self.raw,
            "_verify_raw": lambda s3, request: None,
            "build_request": lambda *args, **kwargs: request or self.request,
        }
        values.update(patches)
        with patch.multiple(dispatcher, **values):
            return dispatcher.dispatch(self.s3, self.root, now=self.now)

    def test_raw_incomplete_waits_without_counting_failure(self):
        result = self._dispatch(weeks={self.week: {"status": "RUNNING"}})
        self.assertEqual(result, 2)
        state = self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")
        self.assertEqual(state["status"], "WAITING_INPUT")
        self.assertEqual(state["consecutive_failures"], 0)

    def test_completed_history_is_skipped_and_reconciles_state(self):
        history = {self.base: {"raw_refs": {}}, self.week: {"raw_refs": {}}}
        runner_run = unittest.mock.Mock()
        result = self._dispatch(history=history, runner=unittest.mock.Mock(run=runner_run))
        self.assertEqual(result, 0)
        self.assertFalse(runner_run.called)
        state = self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")
        self.assertEqual(state["status"], "COMPLETE")

    def test_raw_drift_in_completed_history_is_blocked(self):
        history = {self.base: {"raw_refs": {}}, self.week: {"raw_refs": {"input": {"bucket": "raw", "key": "x", "sha256": "a" * 64}}}}
        result = self._dispatch(history=history, _verify_raw=lambda s3, request: (_ for _ in ()).throw(ValueError("drift")))
        self.assertEqual(result, 1)
        state = self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")
        self.assertEqual(state["status"], "BLOCKED")

    def test_failure_retries_saved_request_without_repinning(self):
        builds = unittest.mock.Mock(return_value=self.request)
        runs = [RuntimeError("temporary"), None]
        def run(*args):
            error = runs.pop(0)
            if error:
                raise error
        with patch.multiple(dispatcher, _history=lambda s: self.history,
                            _documents=lambda s: self.raw, _verify_raw=lambda s, r: None,
                            build_request=builds, **{"runner": unittest.mock.Mock(run=run)}):
            self.assertEqual(dispatcher.dispatch(self.s3, self.root, now=self.now), 1)
            self.assertEqual(dispatcher.dispatch(self.s3, self.root, now=self.now + timedelta(hours=2)), 0)
        self.assertEqual(builds.call_count, 1)

    def test_blocked_requires_explicit_manual_retry(self):
        prefix = dispatcher.OPS + "/" + self.week
        self.s3.put_json(BUCKET, prefix + "/status.json", {"status": "BLOCKED", "consecutive_failures": 10})
        run = unittest.mock.Mock()
        with patch.multiple(dispatcher, _history=lambda s: self.history, _documents=lambda s: self.raw,
                            _verify_raw=lambda s, r: None, runner=unittest.mock.Mock(run=run)):
            self.assertEqual(dispatcher.dispatch(self.s3, self.root, now=self.now), 1)
            self.assertFalse(run.called)

    def test_manual_retry_resets_blocked_snapshot_and_runs(self):
        prefix = dispatcher.OPS + "/" + self.week
        self.s3.put_json(BUCKET, prefix + "/status.json", {"status": "BLOCKED", "consecutive_failures": 10})
        run = unittest.mock.Mock()
        with patch.multiple(dispatcher, _history=lambda s: self.history, _documents=lambda s: self.raw,
                            _verify_raw=lambda s, r: None, build_request=lambda *a, **k: self.request,
                            runner=unittest.mock.Mock(run=run)):
            result = dispatcher.dispatch(self.s3, self.root, retry_snapshot=self.week, now=self.now)
        self.assertEqual(result, 0)
        self.assertTrue(run.called)
        state = self.s3.json(BUCKET, prefix + "/status.json")
        self.assertEqual(state["status"], "COMPLETE")
        self.assertEqual(state["consecutive_failures"], 0)

    def test_waiting_input_does_not_consume_failure_budget(self):
        result = self._dispatch(_verify_raw=lambda s, r: (_ for _ in ()).throw(WaitingInput("not ready")))
        self.assertEqual(result, 2)
        state = self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")
        self.assertEqual(state["consecutive_failures"], 0)

    def test_pipeline_lock_contention_waits_without_failure_budget(self):
        result = self._dispatch(_verify_raw=lambda s, r: (_ for _ in ()).throw(PipelineBusy("busy")))
        self.assertEqual(result, 2)
        state = self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")
        self.assertEqual(state["status"], "WAITING_INPUT")
        self.assertEqual(state["consecutive_failures"], 0)

    def test_main_persists_discovery_failure_and_success_tick(self):
        with patch("pipeline.minio.ingest_raw.client", return_value=self.s3), \
             patch.object(dispatcher, "_history", side_effect=ValueError("malformed raw state")):
            self.assertEqual(dispatcher.main(["--work-dir", str(self.root)]), 1)
        global_key = BUCKET, dispatcher.OPS + "/_dispatcher/status.json"
        self.assertEqual(self.s3.json(*global_key)["status"], "FAILED")
        local = self.root / "dispatch" / "_dispatcher" / "status.json"
        self.assertEqual(json.loads(local.read_bytes())["status"], "FAILED")

        with patch("pipeline.minio.ingest_raw.client", return_value=self.s3), \
             patch.object(dispatcher, "dispatch", return_value=0):
            self.assertEqual(dispatcher.main(["--work-dir", str(self.root)]), 0)
        self.assertEqual(self.s3.json(*global_key), {"status": "TICK_FINISHED", "exit_code": 0,
                                                     "updated_at": self.s3.json(*global_key)["updated_at"]})
        self.assertEqual(json.loads(local.read_bytes())["status"], "TICK_FINISHED")

    def test_local_newer_failure_wins_when_remote_status_is_stale(self):
        local = self.root / "dispatch" / self.week
        local.mkdir(parents=True)
        (local / "status.json").write_text(json.dumps({"status": "FAILED", "consecutive_failures": 3,
            "updated_at": "2026-09-18T02:00:00+00:00", "next_retry_at": None}), encoding="utf-8")
        self.s3.put_json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json",
                         {"status": "FAILED", "consecutive_failures": 1, "updated_at": "2026-09-17T02:00:00+00:00"})
        result = self._dispatch(_verify_raw=lambda s, r: (_ for _ in ()).throw(ValueError("bad")))
        self.assertEqual(result, 1)
        self.assertEqual(self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")["consecutive_failures"], 4)

    def test_paginated_raw_run_discovery_includes_all_documents(self):
        s3 = PagedMemoryS3()
        s3.put_json("pickage-raw", "_ops/weekly/2026-09-14/run.json", {"status": "SUCCEEDED"})
        s3.put_json("pickage-raw", "_ops/weekly/2026-09-21/run.json", {"status": "FAILED"})
        self.assertEqual(set(dispatcher._documents(s3)), {"2026-09-14", "2026-09-21"})

    def test_missing_baseline_is_waiting_input(self):
        with patch.object(dispatcher, "_history", side_effect=WaitingInput("baseline missing")):
            with self.assertRaises(WaitingInput):
                dispatcher.dispatch(self.s3, self.root, now=self.now)

    def test_interrupted_running_attempt_is_retried(self):
        prefix = dispatcher.OPS + "/" + self.week
        self.s3.put_json(BUCKET, prefix + "/status.json", {"status": "RUNNING", "attempt": 1,
                         "consecutive_failures": 0, "updated_at": "2026-09-17T00:00:00+00:00"})
        run = unittest.mock.Mock()
        with patch.multiple(dispatcher, _history=lambda s: self.history, _documents=lambda s: self.raw,
                            _verify_raw=lambda s, r: None, build_request=lambda *a, **k: self.request,
                            runner=unittest.mock.Mock(run=run)):
            self.assertEqual(dispatcher.dispatch(self.s3, self.root, now=self.now), 0)
        state = self.s3.json(BUCKET, prefix + "/status.json")
        self.assertEqual(state["status"], "COMPLETE")
        self.assertEqual(state["attempt"], 2)
        self.assertEqual(state["consecutive_failures"], 0)

    def test_completion_reconciles_after_state_write_crash(self):
        history = {self.base: {"raw_refs": {}}, self.week: {"raw_refs": {}}}
        result = self._dispatch(history=history)
        self.assertEqual(result, 0)
        self.assertEqual(self.s3.json(BUCKET, dispatcher.OPS + "/" + self.week + "/status.json")["status"], "COMPLETE")

    def test_verify_raw_checks_pinned_bytes_and_success_marker(self):
        s3 = MemoryS3()
        body = b"manifest"
        ref = {"bucket": "pickage-raw", "key": "deps/run_manifest.json", "sha256": sha(body)}
        s3.objects[("pickage-raw", ref["key"])] = body
        s3.objects[("pickage-raw", "deps/_SUCCESS")] = json.dumps({"manifest_sha256": sha(body)}).encode()
        dispatcher._verify_raw(s3, {"raw_refs": {"versions": ref}})
        s3.objects[("pickage-raw", ref["key"])] = b"changed"
        with self.assertRaisesRegex(ValueError, "Pinned object SHA mismatch"):
            dispatcher._verify_raw(s3, {"raw_refs": {"versions": ref}})

    def test_tenth_failure_blocks_and_backoff_does_not_run(self):
        prefix = dispatcher.OPS + "/" + self.week
        self.s3.put_json(BUCKET, prefix + "/status.json", {"status": "FAILED", "consecutive_failures": 9})
        result = self._dispatch(runner=unittest.mock.Mock(run=unittest.mock.Mock(side_effect=OSError("network"))))
        self.assertEqual(result, 1)
        state = self.s3.json(BUCKET, prefix + "/status.json")
        self.assertEqual((state["status"], state["consecutive_failures"]), ("BLOCKED", 10))
        state.update(status="FAILED", next_retry_at=(self.now + timedelta(hours=1)).isoformat())
        dispatcher.atomic_json(self.root / "dispatch" / self.week / "status.json", state)
        self.s3.put_json(BUCKET, prefix + "/status.json", state)
        run = unittest.mock.Mock()
        self.assertEqual(self._dispatch(runner=unittest.mock.Mock(run=run)), 0)
        run.assert_not_called()

    def test_tenth_interruption_blocks_without_an_eleventh_attempt(self):
        prefix = dispatcher.OPS + "/" + self.week
        self.s3.put_json(BUCKET, prefix + "/status.json", {"status": "RUNNING", "attempt": 10, "consecutive_failures": 9})
        run = unittest.mock.Mock()
        self.assertEqual(self._dispatch(runner=unittest.mock.Mock(run=run)), 1)
        run.assert_not_called()
        state = self.s3.json(BUCKET, prefix + "/status.json")
        self.assertEqual((state["status"], state["consecutive_failures"]), ("BLOCKED", 10))

    def test_older_incomplete_raw_blocks_newer_completed_raw(self):
        run = unittest.mock.Mock()
        weeks = {"2026-09-21": {"status": "SUCCEEDED"}, self.week: {"status": "FAILED"}}
        self.assertEqual(self._dispatch(weeks=weeks, runner=unittest.mock.Mock(run=run)), 2)
        run.assert_not_called()
        self.assertNotIn((BUCKET, dispatcher.OPS + "/2026-09-21/status.json"), self.s3.objects)


if __name__ == "__main__":
    unittest.main()
