"""get_or_build_evidence() 유닛테스트 (S15P21A506-176, unittest, stdlib).

2026-09-18 결정: PostgreSQL 캐시 없이 요청마다 그때그때 읽고 청킹한다
([[rag-176-no-db-cache]]) — 이 테스트는 그 경로(파일 읽기 → 175 청킹)만 검증한다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_pipeline -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ai.rag.pipeline import get_or_build_evidence
from ai.rag.readme_source import ReadmeSourceNotFoundError


def _write_readme(root: Path, package: str, version: str, body: str) -> None:
    shard = (package[1:] if package.startswith("@") else package)[0].lower()
    shard_dir = root / shard
    shard_dir.mkdir(parents=True, exist_ok=True)
    key = package.replace("/", "__") + "@" + version
    (shard_dir / f"{key}.md").write_text(
        f"# {package}@{version}\nsome desc\n\n## README 전문\n\n{body}\n",
        encoding="utf-8",
    )


class GetOrBuildEvidenceTests(unittest.TestCase):
    def test_reads_file_and_chunks_it_with_explicit_root(self):
        with tempfile.TemporaryDirectory() as root:
            _write_readme(Path(root), "express", "4.21.2", "Fast web framework.")

            chunks = get_or_build_evidence("express", "4.21.2", root=root)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].package, "express")
            self.assertEqual(chunks[0].version, "4.21.2")
            self.assertEqual(chunks[0].excerpt, "Fast web framework.")
            self.assertTrue(chunks[0].snapshot_id)

    def test_same_file_content_gives_same_snapshot_id(self):
        with tempfile.TemporaryDirectory() as root:
            _write_readme(Path(root), "express", "4.21.2", "Fast web framework.")

            chunks_first = get_or_build_evidence("express", "4.21.2", root=root)
            chunks_second = get_or_build_evidence("express", "4.21.2", root=root)

            self.assertEqual(chunks_first[0].snapshot_id, chunks_second[0].snapshot_id)

    def test_missing_file_raises_readme_source_not_found_error(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ReadmeSourceNotFoundError):
                get_or_build_evidence("does-not-exist", "1.0.0", root=root)

    def test_falls_back_to_readme_source_root_env_var(self):
        with tempfile.TemporaryDirectory() as root:
            _write_readme(Path(root), "express", "4.21.2", "Fast web framework.")
            old = os.environ.get("README_SOURCE_ROOT")
            os.environ["README_SOURCE_ROOT"] = root
            try:
                chunks = get_or_build_evidence("express", "4.21.2")
            finally:
                if old is None:
                    del os.environ["README_SOURCE_ROOT"]
                else:
                    os.environ["README_SOURCE_ROOT"] = old

            self.assertEqual(len(chunks), 1)


if __name__ == "__main__":
    unittest.main()
