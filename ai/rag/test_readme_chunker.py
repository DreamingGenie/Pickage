"""chunk_readme()/parse_data_team_envelope() 유닛테스트 (S15P21A506-178, unittest, stdlib).

실행: 저장소 루트에서
    python -m unittest ai.rag.test_readme_chunker -v
"""

from __future__ import annotations

import unittest

from ai.rag.readme_chunker import chunk_readme


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


if __name__ == "__main__":
    unittest.main()
