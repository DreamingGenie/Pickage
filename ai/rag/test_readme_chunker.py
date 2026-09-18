"""chunk_readme()/parse_data_team_envelope() 유닛테스트 (S15P21A506-178, unittest, stdlib).

실행: 저장소 루트에서
    python -m unittest ai.rag.test_readme_chunker -v
"""

from __future__ import annotations

import unittest

from ai.rag.readme_chunker import (
    EnvelopeParseError,
    chunk_readme,
    parse_data_team_envelope,
)


class ChunkReadmeNoHeadingsTests(unittest.TestCase):
    def test_no_headings_becomes_single_intro_chunk(self):
        readme_text = "Just a short readme with no headings at all."

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
        )

        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk.section, "(intro)")
        self.assertEqual(chunk.excerpt, readme_text)
        self.assertEqual(chunk.package, "foo")
        self.assertEqual(chunk.version, "1.0.0")
        self.assertEqual(chunk.snapshot_id, "snap-1")
        self.assertEqual(chunk.source_type, "TARBALL_README")
        self.assertEqual(chunk.verification_level, "DISTRIBUTED_ARTIFACT")


class ChunkReadmeHeadingSplitTests(unittest.TestCase):
    def test_atx_heading_splits_intro_from_section(self):
        readme_text = "Intro line.\n\n## Usage\n\nDo the thing.\n"

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].section, "(intro)")
        self.assertEqual(chunks[0].excerpt, "Intro line.")
        self.assertEqual(chunks[1].section, "Usage")
        self.assertEqual(chunks[1].excerpt, "Do the thing.")


class ChunkReadmeCodeFenceTests(unittest.TestCase):
    def test_hash_comment_inside_code_fence_is_not_a_heading(self):
        readme_text = (
            "Intro.\n\n"
            "```bash\n# not a heading\necho hi\n```\n\n"
            "## Real Section\n\nBody.\n"
        )

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].section, "(intro)")
        self.assertIn("```bash\n# not a heading\necho hi\n```", chunks[0].excerpt)
        self.assertEqual(chunks[1].section, "Real Section")
        self.assertEqual(chunks[1].excerpt, "Body.")


class ChunkReadmeNoiseHeadingTests(unittest.TestCase):
    def test_noise_heading_is_downgraded_not_dropped(self):
        readme_text = "Intro.\n\n## License\n\nMIT.\n\n## Usage\n\nDo it.\n"

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
        )

        by_section = {c.section: c for c in chunks}
        self.assertIn("License", by_section)
        self.assertEqual(by_section["License"].verification_level, "SUPPLEMENTARY")
        self.assertEqual(by_section["Usage"].verification_level, "DISTRIBUTED_ARTIFACT")

    def test_noise_heading_match_is_case_insensitive(self):
        readme_text = "Intro.\n\n## LICENSE\n\nMIT.\n"

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
        )

        by_section = {c.section: c for c in chunks}
        self.assertEqual(by_section["LICENSE"].verification_level, "SUPPLEMENTARY")


class ParseDataTeamEnvelopeTests(unittest.TestCase):
    def test_extracts_package_version_and_readme_body(self):
        doc_text = (
            "# debug@4.4.3\n"
            "Debug utility.\n\n"
            "## README 전문\n\n"
            "Hello world\n\n"
            "---\n"
            "근거: S1 README 상태 OK\n"
        )

        envelope = parse_data_team_envelope(doc_text)

        self.assertEqual(envelope.package, "debug")
        self.assertEqual(envelope.version, "4.4.3")
        self.assertEqual(envelope.readme_body, "Hello world")
        self.assertEqual(envelope.source_footer, "근거: S1 README 상태 OK")

    def test_scoped_package_name_keeps_its_own_at_sign(self):
        doc_text = (
            "# @scope/pkg@1.0.0\n"
            "Scoped package.\n\n"
            "## README 전문\n\n"
            "Body text\n"
        )

        envelope = parse_data_team_envelope(doc_text)

        self.assertEqual(envelope.package, "@scope/pkg")
        self.assertEqual(envelope.version, "1.0.0")

    def test_missing_readme_anchor_raises_envelope_parse_error(self):
        doc_text = "# debug@4.4.3\nNo README section here.\n"

        with self.assertRaises(EnvelopeParseError):
            parse_data_team_envelope(doc_text)

    def test_extracts_structured_facts_sections(self):
        doc_text = (
            "# debug@4.4.3\n"
            "Debug utility.\n\n"
            "## 소비 형태 · 진입점\n"
            "- CommonJS\n"
            "- 진입점: index.js\n\n"
            "## 설치 조건\n"
            "- Node >= 14\n\n"
            "## README 전문\n\n"
            "Hello world\n"
        )

        envelope = parse_data_team_envelope(doc_text)

        self.assertEqual(
            envelope.structured_facts,
            {
                "소비 형태 · 진입점": "- CommonJS\n- 진입점: index.js",
                "설치 조건": "- Node >= 14",
            },
        )


if __name__ == "__main__":
    unittest.main()
