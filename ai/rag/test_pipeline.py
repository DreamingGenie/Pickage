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

from ai.rag.pipeline import get_or_build_evidence, load_document
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





def _write_doc(root: Path, package: str, version: str, text: str) -> None:
    shard = (package[1:] if package.startswith("@") else package)[0].lower()
    (root / shard).mkdir(parents=True, exist_ok=True)
    key = package.replace("/", "__") + "@" + version
    (root / shard / f"{key}.md").write_text(text, encoding="utf-8")


_FOOTER = "근거: S1 README 917 B / 산문 214자 · S2 manifest · S3 spec · 상태 LIMITED"


class LoadDocumentTests(unittest.TestCase):
    """load_document(): 청크와 함께 문헌 상태를 돌려준다 (S15P21A506-419)."""

    def test_returns_chunks_and_the_document_status_from_the_footer(self):
        with tempfile.TemporaryDirectory() as root:
            _write_doc(
                Path(root), "js-yaml", "5.4.1",
                "# js-yaml@5.4.1\n\n## README 전문\n\nParser.\n\n---\n" + _FOOTER,
            )

            loaded = load_document("js-yaml", "5.4.1", root=root)

            self.assertEqual([c.excerpt for c in loaded.chunks], ["Parser."])
            self.assertEqual(loaded.source.package, "js-yaml")
            self.assertEqual(loaded.source.version, "5.4.1")
            self.assertEqual(loaded.source.status, "LIMITED")
            self.assertEqual(loaded.source.prose_chars, 214)

    def test_readme_after_a_horizontal_rule_becomes_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            _write_doc(
                Path(root), "foo", "1.0.0",
                "# foo@1.0.0\n\n## README 전문\n\nIntro.\n\n---\n\n## API\n\nloadAll reads many.\n\n---\n" + _FOOTER,
            )

            chunks = load_document("foo", "1.0.0", root=root).chunks

            self.assertTrue(any("loadAll" in c.excerpt for c in chunks))

    def test_document_without_a_footer_has_an_unknown_status(self):
        with tempfile.TemporaryDirectory() as root:
            _write_readme(Path(root), "foo", "1.0.0", "Body.")

            self.assertIsNone(load_document("foo", "1.0.0", root=root).source.status)

    def test_get_or_build_evidence_still_returns_only_the_chunks(self):
        with tempfile.TemporaryDirectory() as root:
            _write_readme(Path(root), "foo", "1.0.0", "Body.")

            chunks = get_or_build_evidence("foo", "1.0.0", root=root)

            self.assertEqual([c.excerpt for c in chunks], ["Body."])

    def test_missing_file_error_carries_package_and_version(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ReadmeSourceNotFoundError) as ctx:
                load_document("ghost", "9.9.9", root=root)

            self.assertEqual(ctx.exception.package, "ghost")
            self.assertEqual(ctx.exception.version, "9.9.9")


if __name__ == "__main__":
    unittest.main()
