"""Recovery reuses the five completed baseline stages and prepared inputs."""
import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.preprocessing.experiments import real_snapshot_recover as recovery
from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.orchestration.contracts import STAGES, code_contract
from pipeline.preprocessing.tests.fixtures.weekly_fixture import make_weekly_fixture


class _Experiment:
    def __init__(self, root, local, request):
        self.root = Path(root)
        self.local = local
        self._request = request

    def request(self, label):
        self.assert_label = label
        return self._request

    @contextmanager
    def phase(self, _name):
        yield


class RealSnapshotRecoveryTests(unittest.TestCase):
    def test_recovery_reuses_completed_stages_and_prepared_input(self):
        # Keep the path short because the production output layout is nested.
        with tempfile.TemporaryDirectory(dir="C:/", prefix="rc-") as folder:
            root = Path(folder)
            fixture, request = make_weekly_fixture(root / "fixture", population=3)
            # Recovery currently uses two verification workers; keep the
            # synthetic request's total thread budget valid for that path.
            request["options"]["threads"] = 2
            s3 = fixture.s3
            work = root / "w"
            source_inventory = root / "source-files.json"
            source_inventory.write_bytes(b"{}")

            with patch(
                "pipeline.preprocessing.orchestration.dependents_parallel.parallel.run",
                side_effect=RuntimeError("stop before dependents compute"),
            ):
                with self.assertRaisesRegex(RuntimeError, "stop before dependents compute"):
                    runner.run(request, s3, work)

            local = work / request["run_id"]
            prefix = runner.run_prefix(request)
            checkpoint_bytes = {
                name: s3.objects[("pickage-curated", prefix + "/stages/" + name + ".json")]
                for name in STAGES
                if name != "dependents"
            }
            request_bytes = s3.objects[("pickage-curated", prefix + "/request.json")]
            prepared = list((local / "dependents" / "parallel-attempt").glob("prep-*/input/input_manifest.json"))
            self.assertEqual(len(prepared), 1)

            experiment = _Experiment(root, s3, request)
            result = recovery.recover_baseline(experiment, request)

            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["recovery"]["key"], prefix + "/recoveries/" + recovery.RECOVERY_ID + ".json")
            self.assertTrue((local / "bundle.json").is_file())
            self.assertTrue(s3.objects[("pickage-curated", prefix + "/_SUCCESS")])
            for name, body in checkpoint_bytes.items():
                self.assertEqual(s3.objects[("pickage-curated", prefix + "/stages/" + name + ".json")], body)
            self.assertEqual(s3.objects[("pickage-curated", prefix + "/request.json")], request_bytes)
            self.assertEqual(json.loads((local / "status.json").read_bytes())["status"], "COMPLETE")

            # A completed recovery is idempotent and must not execute any stage.
            with patch.object(recovery, "recover_baseline", side_effect=AssertionError("recovery replayed")):
                replay = runner.run(request, s3, work, resume=True)
            self.assertEqual(replay["status"], "COMPLETE")

    def test_contract_change_rejects_unreviewed_generator_file(self):
        old = {"runtime": {"python": [3, 12, 0]}, "files": {"other.py": "a"}}
        new = {"runtime": {"python": [3, 12, 0]}, "files": {"other.py": "b"}}
        with self.assertRaisesRegex(ValueError, "reviewed reader/input validation"):
            recovery.contract_changes(old, new)

    def test_contract_change_rejects_runtime_change(self):
        old = {"runtime": {"python": [3, 12, 0]}, "files": {recovery.READER: "a"}}
        new = {"runtime": {"python": [3, 12, 1]}, "files": {recovery.READER: "b"}}
        with self.assertRaisesRegex(ValueError, "runtime differs"):
            recovery.contract_changes(old, new)


if __name__ == "__main__":
    unittest.main()
