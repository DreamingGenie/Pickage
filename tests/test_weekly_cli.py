import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.orchestration.__main__ import main
from tests.test_orchestration_runner import request_fixture


class WeeklyCliTests(unittest.TestCase):
    def test_one_command_generates_pins_and_reuses_request(self):
        with tempfile.TemporaryDirectory() as directory:
            request = request_fixture()
            request["run_id"] = "weekly"
            args = ["weekly", "--snapshot", request["snapshot"], "--run-id", "weekly",
                    "--work-dir", directory]
            with patch("pipeline.minio.ingest_raw.client") as client, \
                 patch("pipeline.orchestration.weekly_request.build_request", return_value=request) as build, \
                 patch("pipeline.orchestration.runner.run", return_value={"status": "COMPLETE"}) as run:
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args), 0)
                build.assert_called_once()
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args.args[0], request)
                saved = Path(directory) / "requests" / "weekly.json"
                self.assertEqual(json.loads(saved.read_bytes()), request)
                changed = args + ["--bronze-run-id", "other-input"]
                self.assertEqual(main(changed), 1)
                self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
