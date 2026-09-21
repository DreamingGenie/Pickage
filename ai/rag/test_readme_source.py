"""README 인계 파일 경로 해석 유닛테스트 (S15P21A506-176, unittest, stdlib).

2026-09-18 데이터팀 전달 규칙 기준 — 예시 4개(express/@babel/core/lodash.get/
@types/node)를 그대로 회귀 테스트로 고정한다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_readme_source -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.rag.readme_source import (
    ReadmeSourceNotFoundError,
    read_readme_envelope,
    resolve_readme_path,
)


class ResolveReadmePathTests(unittest.TestCase):
    def test_unscoped_package(self):
        path = resolve_readme_path("express", "4.21.2", "/root")
        self.assertEqual(path, Path("/root/e/express@4.21.2.md"))

    def test_scoped_package_slash_becomes_double_underscore(self):
        path = resolve_readme_path("@babel/core", "7.28.4", "/root")
        self.assertEqual(path, Path("/root/b/@babel__core@7.28.4.md"))

    def test_name_with_dot_is_preserved_and_split_on_last_at(self):
        path = resolve_readme_path("lodash.get", "4.4.2", "/root")
        self.assertEqual(path, Path("/root/l/lodash.get@4.4.2.md"))

    def test_scoped_types_package(self):
        path = resolve_readme_path("@types/node", "22.10.2", "/root")
        self.assertEqual(path, Path("/root/t/@types__node@22.10.2.md"))

    def test_uppercase_in_name_is_preserved_only_shard_letter_lowercased(self):
        path = resolve_readme_path("Foo", "1.0.0", "/root")
        self.assertEqual(path, Path("/root/f/Foo@1.0.0.md"))


class ReadReadmeEnvelopeTests(unittest.TestCase):
    def test_reads_and_parses_the_file_at_the_resolved_path(self):
        with tempfile.TemporaryDirectory() as root:
            shard_dir = Path(root) / "e"
            shard_dir.mkdir()
            (shard_dir / "express@4.21.2.md").write_text(
                "# express@4.21.2\n"
                "Fast web framework.\n\n"
                "## README 전문\n\n"
                "Hello express\n",
                encoding="utf-8",
            )

            envelope = read_readme_envelope("express", "4.21.2", root)

            self.assertEqual(envelope.package, "express")
            self.assertEqual(envelope.version, "4.21.2")
            self.assertEqual(envelope.readme_body, "Hello express")

    def test_missing_file_raises_readme_source_not_found_error(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ReadmeSourceNotFoundError):
                read_readme_envelope("does-not-exist", "1.0.0", root)


if __name__ == "__main__":
    unittest.main()
