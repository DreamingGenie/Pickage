import tempfile
from pathlib import Path
import unittest

from pipeline.preprocessing.orchestration.workspace import claim, cleanup_stage


class WorkspaceTests(unittest.TestCase):
    def test_claim_rejects_unmarked_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "run"
            path.mkdir()
            (path / "foreign.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unmarked"):
                claim(path, "run-1")
            self.assertTrue((path / "foreign.txt").exists())

    def test_stage_cleanup_removes_only_owned_stage_scratch(self):
        with tempfile.TemporaryDirectory() as root:
            path = claim(Path(root) / "run", "run-1")
            (path / "repository").mkdir()
            (path / "repository" / "scratch.duckdb").write_bytes(b"x")
            (path / "snapshot").mkdir()
            (path / "snapshot" / "snapshot-candidate.json").write_bytes(b"keep")
            (path / "inputs" / "projects").mkdir(parents=True)
            (path / "inputs" / "projects" / "source.parquet").write_bytes(b"keep")
            self.assertEqual(cleanup_stage(path, "repository"), ["repository"])
            self.assertFalse((path / "repository").exists())
            self.assertTrue((path / "snapshot" / "snapshot-candidate.json").exists())
            self.assertTrue((path / "inputs" / "projects" / "source.parquet").exists())
            self.assertEqual(cleanup_stage(path, "package_snapshot"), ["inputs/projects", "snapshot"])

    def test_cleanup_requires_marker_and_never_follows_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "run"
            path.mkdir()
            (path / "repository").mkdir()
            with self.assertRaisesRegex(ValueError, "marker"):
                cleanup_stage(path, "repository")
            (path / "repository").rmdir()
            claim(path, "run-1")
            outside = Path(root) / "outside"
            outside.mkdir()
            try:
                (path / "repository").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "symlink ancestor"):
                cleanup_stage(path, "repository")
            self.assertTrue(outside.exists())

    def test_cleanup_rejects_unknown_stage_and_invalid_marker(self):
        with tempfile.TemporaryDirectory() as root:
            path = claim(Path(root) / "run", "run-1")
            with self.assertRaisesRegex(ValueError, "unknown"):
                cleanup_stage(path, "arbitrary")
            (path / ".pickage-run-workspace.json").write_text(
                '{"format": 99, "run_id": "run-1", "root": "' + str(path).replace('\\', '\\\\') + '"}',
                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "marker"):
                cleanup_stage(path, "repository")

    def test_claim_rejects_nonexistent_child_below_symlink_parent(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            outside = base / "outside"
            outside.mkdir()
            link = base / "link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "ancestor"):
                claim(link / "new-run", "run-1")
            self.assertFalse((outside / "new-run").exists())


if __name__ == "__main__":
    unittest.main()
