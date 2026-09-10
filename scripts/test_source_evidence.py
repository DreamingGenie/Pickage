import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.source_evidence import (
    file_sha256,
    git_sha256,
    index_sha256,
    normalized_sha256,
    normalized_utf8_bytes,
    HASH_BASIS,
    verify_evidence,
)


class SourceEvidenceTests(unittest.TestCase):
    def test_line_endings_have_one_hash(self):
        source = "이름 = '값'\nreturn 1\n".encode()
        self.assertEqual(normalized_utf8_bytes(source), normalized_utf8_bytes(source.replace(b"\n", b"\r\n")))
        self.assertEqual(normalized_sha256(source), normalized_sha256(source.replace(b"\n", b"\r\n")))
        self.assertEqual(normalized_sha256(source), normalized_sha256(source.replace(b"\n", b"\r")))

    def test_content_change_changes_hash(self):
        self.assertNotEqual(normalized_sha256(b"value = 1\n"), normalized_sha256(b"value = 2\n"))

    def test_mixed_line_endings_and_non_ascii_are_supported(self):
        mixed = "한글\r\n두번째\n세번째\r".encode()
        expected = "한글\n두번째\n세번째\n".encode()
        self.assertEqual(normalized_utf8_bytes(mixed), expected)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "source.py"
            path.write_bytes(mixed)
            self.assertEqual(file_sha256(path), normalized_sha256(expected))

    def test_git_revision_hash_does_not_depend_on_checkout(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            source = repo / "sample.py"
            source.write_bytes(b"print('x')\n")
            subprocess.run(["git", "add", "sample.py"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial"],
                cwd=repo,
                check=True,
            )
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            source.write_bytes(b"print('working tree')\r\n")
            self.assertEqual(git_sha256(repo, revision, "sample.py"), normalized_sha256(b"print('x')\n"))
            self.assertEqual(index_sha256(repo, "sample.py"), normalized_sha256(b"print('x')\n"))

    def test_verify_evidence_uses_historical_revision_after_worktree_changes(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            source = repo / "sample.py"
            source.write_bytes(b"print('historical')\n")
            subprocess.run(["git", "add", "sample.py"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial"],
                cwd=repo,
                check=True,
            )
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            evidence = repo / "evidence.json"
            evidence.write_text(json.dumps({"source_hash_basis": HASH_BASIS, "source_revision": revision, "source_sha256": {"sample.py": normalized_sha256(b"print('historical')\n")}}), encoding="utf-8")
            source.write_bytes(b"print('current')\r\n")
            verify_evidence(repo, evidence)
            evidence.write_text(json.dumps({"source_hash_basis": HASH_BASIS, "source_revision": revision, "source_sha256": {"sample.py": "0" * 64}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_evidence(repo, evidence)

    def test_worktree_verification_detects_missing_or_changed_source(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            source = repo / "sample.py"
            source.write_bytes(b"value = 1\n")
            evidence = repo / "evidence.json"
            evidence.write_text(json.dumps({"source_hash_basis": HASH_BASIS, "source_sha256": {"sample.py": file_sha256(source)}}), encoding="utf-8")
            source.write_bytes(b"value = 2\n")
            with self.assertRaises(ValueError):
                verify_evidence(repo, evidence, source="worktree")
            source.unlink()
            with self.assertRaises(FileNotFoundError):
                verify_evidence(repo, evidence, source="worktree")

    def test_verify_rejects_unknown_hash_basis(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            source = repo / "sample.py"
            source.write_bytes(b"value = 1\n")
            evidence = repo / "evidence.json"
            evidence.write_text(json.dumps({"source_hash_basis": "raw bytes", "source_sha256": {"sample.py": file_sha256(source)}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_evidence(repo, evidence, source="worktree")

    def test_verify_cli_returns_nonzero_for_mismatch(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            source = repo / "sample.py"
            source.write_bytes(b"value = 1\n")
            evidence = repo / "evidence.json"
            evidence.write_text(json.dumps({"source_hash_basis": HASH_BASIS, "source_sha256": {"sample.py": file_sha256(source)}}), encoding="utf-8")
            source.write_bytes(b"value = 2\n")
            result = subprocess.run(
                ["python", "scripts/source_evidence.py", "--repo", str(repo), "--verify", str(evidence), "--worktree"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main()
import json
