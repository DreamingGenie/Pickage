"""Pin ID parent inside the native writer lock, including an own-run retry."""
import tempfile
import json
from pathlib import Path
import unittest

from pipeline.preprocessing.curated import build
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import make_fixture


class PinnedParentTests(unittest.TestCase):
    def test_wrong_parent_rejected_inside_native_writer(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = make_fixture(Path(root) / "fixture")
            fixture.bootstrap_parent()
            with self.assertRaisesRegex(ValueError, "pinned pipeline"):
                build.run(fixture.s3, fixture.snapshot, fixture.request["bronze_run_id"], "current-test",
                          Path(root) / "run", workers=1, threads=1, memory="512MB", expected_parent=None)

    def test_same_run_retry_uses_original_pinned_parent(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = make_fixture(Path(root) / "fixture")
            fixture.bootstrap_parent()
            parent = fixture.request["parent"]
            first = build.run(fixture.s3, fixture.snapshot, fixture.request["bronze_run_id"], "current-test",
                             Path(root) / "run", workers=1, threads=1, memory="512MB", expected_parent=parent)
            second = build.run(fixture.s3, fixture.snapshot, fixture.request["bronze_run_id"], "current-test",
                              Path(root) / "run", workers=1, threads=1, memory="512MB", expected_parent=parent)
            self.assertEqual(first, second)

    def test_new_run_on_same_snapshot_preserves_ids(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = make_fixture(Path(root) / "fixture")
            fixture.bootstrap_parent()
            build.run(fixture.s3, fixture.snapshot, fixture.request["bronze_run_id"], "first",
                      Path(root) / "run", workers=1, threads=1, memory="512MB",
                      expected_parent=fixture.request["parent"])
            current = json.loads(fixture.s3.objects[(build.CURATED_BUCKET, build.CURRENT)])
            rerun = build.run(fixture.s3, fixture.snapshot, fixture.request["bronze_run_id"], "second",
                              Path(root) / "run", workers=1, threads=1, memory="512MB", expected_parent=current)
            self.assertEqual(rerun["report"]["new_packages"], 0)
            self.assertEqual(rerun["report"]["registry_packages"], 3)


if __name__ == "__main__":
    unittest.main()
