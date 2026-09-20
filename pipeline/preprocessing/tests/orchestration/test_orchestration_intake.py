import tempfile
import unittest
from copy import deepcopy
import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from pipeline.preprocessing.tests.fixtures.orchestration_fixture import make_fixture
from pipeline.preprocessing.orchestration.intake import _materialize_verified, hydrate_bronze, preflight
from pipeline.preprocessing.orchestration.storage import WaitingInput


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

    def test_hydrate_reuses_verified_target_without_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            root = Path(directory) / "projects"
            ref = fixture.request["raw_refs"]["projects"]
            hydrate_bronze(fixture.s3, ref, root, table="projects",
                           snapshot=fixture.snapshot, run_id=ref["run_id"])
            with patch("pipeline.preprocessing.curated.storage.download_files",
                       side_effect=AssertionError("verified target should be reused")):
                hydrate_bronze(fixture.s3, ref, root, table="projects",
                               snapshot=fixture.snapshot, run_id=ref["run_id"])

    def test_hydrate_rejects_corrupt_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = make_fixture(Path(directory) / "fixture")
            root = Path(directory) / "projects"
            ref = fixture.request["raw_refs"]["projects"]
            hydrate_bronze(fixture.s3, ref, root, table="projects",
                           snapshot=fixture.snapshot, run_id=ref["run_id"])
            target = next((root / ("snapshot=" + fixture.snapshot)).glob("*.parquet"))
            target.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "Hydrated file differs"):
                hydrate_bronze(fixture.s3, ref, root, table="projects",
                               snapshot=fixture.snapshot, run_id=ref["run_id"])

    def test_materialize_uses_hardlink_and_copy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cached = root / "cache.parquet"
            cached.write_bytes(b"cached")
            linked = root / "linked.parquet"
            checksum = hashlib.sha256(b"cached").hexdigest()
            _materialize_verified(cached, linked, 6, checksum)
            self.assertEqual(os.stat(cached).st_ino, os.stat(linked).st_ino)
            copied = root / "copied.parquet"
            with patch("pipeline.preprocessing.orchestration.intake.os.link", side_effect=OSError("cross-device")):
                _materialize_verified(cached, copied, 6, checksum)
            self.assertEqual(copied.read_bytes(), b"cached")
            self.assertNotEqual(os.stat(cached).st_ino, os.stat(copied).st_ino)

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
