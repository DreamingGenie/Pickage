"""Actual full -> weekly Curated stages behind a dispatcher tick, no network."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.preprocessing.orchestration import dispatcher, runner
from pipeline.preprocessing.orchestration.weekly_request import build_request
from pipeline.preprocessing.tests.fixtures.weekly_fixture import make_weekly_fixture
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import BRONZE_RUN, DOWNLOAD_RUN, SNAPSHOT


class DispatcherIntegrationTests(unittest.TestCase):
    def test_real_weekly_pipeline_and_completed_tick(self):
        with tempfile.TemporaryDirectory(prefix="dispatch-") as directory:
            root = Path(directory)
            fixture, baseline = make_weekly_fixture(root)
            work = root / "w"
            runner.run(baseline, fixture.s3, work)

            def request(s3, snapshot, run_id, work_dir, **kwargs):
                return build_request(s3, snapshot, run_id, work_dir,
                    bronze_run_id=BRONZE_RUN, download_run_id=DOWNLOAD_RUN, **kwargs)

            with patch.object(dispatcher, "_documents", return_value={SNAPSHOT: {"status": "SUCCEEDED"}}), \
                 patch.object(dispatcher, "build_request", side_effect=request) as build:
                self.assertEqual(dispatcher.dispatch(fixture.s3, work), 0)
                with patch.object(runner, "run", side_effect=AssertionError("completed tick reran stages")):
                    self.assertEqual(dispatcher.dispatch(fixture.s3, work), 0)
                build.assert_called_once()
            state = json.loads((work / "dispatch" / SNAPSHOT / "status.json").read_bytes())
            self.assertEqual(state["status"], "COMPLETE")
            self.assertEqual(state["attempt"], 1)


if __name__ == "__main__":
    unittest.main()
