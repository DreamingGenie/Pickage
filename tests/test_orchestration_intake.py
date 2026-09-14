import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tests.orchestration_fixture import make_fixture
from pipeline.orchestration.intake import hydrate_bronze, preflight
from pipeline.orchestration.storage import WaitingInput


class IntakeTests(unittest.TestCase):
    def test_preflight_hydrates_native_inputs_and_target(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            result = preflight(fixture.s3, fixture.request, Path(directory) / "run")
            self.assertEqual(result["status"], "INPUT_READY")
            self.assertTrue((Path(result["projects_root"]) / ("snapshot=" + fixture.snapshot)).exists())
            self.assertTrue(Path(result["target_path"]).is_file())

    def test_hydrate_projects_preserves_source_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            ref = fixture.request["raw_refs"]["projects"]
            root = Path(directory) / "projects"
            manifest = hydrate_bronze(fixture.s3, ref, root, table="projects",
                                      snapshot=fixture.snapshot, run_id=ref["run_id"])
            self.assertEqual(manifest["status"], "PASSED")
            self.assertTrue((root / ("snapshot=" + fixture.snapshot) / "_MANIFEST.json").is_file())
            self.assertTrue(list((root / ("snapshot=" + fixture.snapshot)).glob("*.parquet")))

    def test_preflight_rejects_malformed_parent_before_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            request = deepcopy(fixture.request)
            request["parent"] = {"run_prefix": "bad", "manifest_sha256": "a" * 64,
                                  "snapshot": fixture.prior_snapshot}
            with self.assertRaises(ValueError):
                preflight(fixture.s3, request, Path(directory) / "run")

    def test_preflight_rejects_exact_timestamp_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            request = deepcopy(fixture.request)
            request["snapshot_timestamp"] = fixture.snapshot + "T21:01:11Z"
            with self.assertRaises(ValueError):
                preflight(fixture.s3, request, Path(directory) / "run")

    def test_missing_raw_marker_is_waiting_input(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            ref = fixture.request["raw_refs"]["versions_full"]
            marker = (ref["bucket"], ref["key"].rsplit("/", 1)[0] + "/_SUCCESS")
            del fixture.s3.objects[marker]
            with self.assertRaises(WaitingInput):
                preflight(fixture.s3, fixture.request, Path(directory) / "run")


if __name__ == "__main__":
    unittest.main()
