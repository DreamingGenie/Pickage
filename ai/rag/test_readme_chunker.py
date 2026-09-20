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
    parse_source_footer,
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


class ChunkReadmeOversizedSectionTests(unittest.TestCase):
    def test_paragraphs_that_together_exceed_max_chars_split_into_multiple_chunks(self):
        para_a = "A" * 30
        para_b = "B" * 30
        readme_text = f"## Notes\n\n{para_a}\n\n{para_b}\n"

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
            max_chunk_chars=40,
        )

        notes_chunks = [c for c in chunks if c.section == "Notes"]
        self.assertEqual(len(notes_chunks), 2)
        self.assertEqual(notes_chunks[0].excerpt, para_a)
        self.assertEqual(notes_chunks[1].excerpt, para_b)

    def test_blank_line_inside_code_fence_does_not_split_the_fence(self):
        code_block = "```js\nline1\n\nline2\n```"
        readme_text = f"## Example\n\nIntro para.\n\n{code_block}\n\nTrailing para.\n"

        chunks = chunk_readme(
            readme_text,
            package="foo",
            version="1.0.0",
            snapshot_id="snap-1",
            max_chunk_chars=25,
        )

        example_chunks = [c for c in chunks if c.section == "Example"]
        self.assertTrue(
            any(code_block in c.excerpt for c in example_chunks),
            f"code_block이 온전히 한 청크 안에 있어야 함: {[c.excerpt for c in example_chunks]!r}",
        )



_FOOTER_LIMITED = "근거: S1 README 917 B / 산문 214자 · S2 manifest · S3 spec · 상태 LIMITED"


def _doc(readme_body: str, footer: str | None = _FOOTER_LIMITED, description: str = "설명입니다") -> str:
    """운영 노드 인계 파일과 같은 서식(백엔드 DocAssembler)의 문서를 만든다."""
    text = (
        "# foo@1.0.0\n\n"
        f"{description}\n\n"
        "## 소비 형태 · 진입점\n\n- 명령: 없음\n\n"
        "## 설치 조건\n\n- 파일 수: 3\n\n"
        "## README 전문\n\n"
        f"{readme_body}\n"
    )
    if footer is not None:
        text += f"\n---\n{footer}"
    return text


class EnvelopeFooterSplitTests(unittest.TestCase):
    """README 안의 수평선(---)이 본문을 잘라 먹던 문제 (S15P21A506-419).

    운영 노드 실측(/srv/pickage/docs/j, 4,061건): 5.4%(218건)의 문서에 꼬리 말고도 `---` 줄이
    있다. 예전에는 첫 `---` 를 꼬리의 시작으로 봐서 그 뒤 README 전체가 근거에서 사라졌다.
    """

    def test_horizontal_rule_inside_readme_does_not_truncate_the_body(self):
        readme = "# foo\nIntro.\n\n---\n\n## API\n`loadAll()` reads many documents."

        envelope = parse_data_team_envelope(_doc(readme))

        self.assertIn("loadAll", envelope.readme_body)
        self.assertTrue(envelope.readme_body.startswith("# foo"))

    def test_footer_is_only_the_trailing_evidence_line(self):
        envelope = parse_data_team_envelope(_doc("A\n\n---\n\nB"))

        self.assertEqual(envelope.source_footer, _FOOTER_LIMITED)

    def test_several_rules_and_a_rule_right_before_the_footer_keep_everything(self):
        readme = "A\n\n---\n\nB\n\n---\n\nC\n\n---"

        envelope = parse_data_team_envelope(_doc(readme))

        self.assertEqual(envelope.readme_body, readme)
        self.assertEqual(envelope.source_footer, _FOOTER_LIMITED)

    def test_without_a_footer_the_whole_remainder_is_the_readme(self):
        readme = "A\n\n---\n\nB"

        envelope = parse_data_team_envelope(_doc(readme, footer=None))

        self.assertEqual(envelope.readme_body, readme)
        self.assertEqual(envelope.source_footer, "")

    def test_crlf_line_endings_are_handled(self):
        envelope = parse_data_team_envelope(_doc("A\n\n---\n\nB").replace("\n", "\r\n"))

        self.assertIn("B", envelope.readme_body)
        self.assertIn("상태 LIMITED", envelope.source_footer)


class EnvelopeDescriptionTests(unittest.TestCase):
    def test_description_line_between_title_and_first_section_is_kept(self):
        envelope = parse_data_team_envelope(_doc("Body"))

        self.assertEqual(envelope.description, "설명입니다")

    def test_placeholder_description_means_no_description(self):
        envelope = parse_data_team_envelope(_doc("Body", description="(설명 없음)"))

        self.assertEqual(envelope.description, "")

    def test_old_format_without_header_sections_still_parses(self):
        doc = "# foo@1.0.0\nsome desc\n\n## README 전문\n\nBody\n"

        envelope = parse_data_team_envelope(doc)

        self.assertEqual(envelope.readme_body, "Body")
        self.assertEqual(envelope.description, "some desc")


class ParseSourceFooterTests(unittest.TestCase):
    def test_reads_status_readme_bytes_and_prose_chars(self):
        source = parse_source_footer(_FOOTER_LIMITED, "js-yaml", "5.4.1")

        self.assertEqual(source.package, "js-yaml")
        self.assertEqual(source.version, "5.4.1")
        self.assertEqual(source.status, "LIMITED")
        self.assertEqual(source.readme_bytes, 917)
        self.assertEqual(source.prose_chars, 214)

    def test_thousands_separators_are_understood(self):
        footer = "근거: S1 README 12,345 B / 산문 1,204자 · S2 manifest · S3 spec · 상태 OK"

        source = parse_source_footer(footer, "foo", "1.0.0")

        self.assertEqual((source.status, source.readme_bytes, source.prose_chars), ("OK", 12345, 1204))

    def test_none_status(self):
        footer = "근거: S1 README 0 B / 산문 0자 · S2 manifest · S3 spec · 상태 NONE"

        self.assertEqual(parse_source_footer(footer, "foo", "1.0.0").status, "NONE")

    def test_unreadable_footer_gives_none_instead_of_a_guess(self):
        for footer in ("", "근거: S1 README 상태 ???", "no footer at all"):
            with self.subTest(footer=footer):
                self.assertIsNone(parse_source_footer(footer, "foo", "1.0.0").status)

    def test_a_missing_number_does_not_hide_the_status(self):
        source = parse_source_footer("근거: S1 README 상태 OK", "foo", "1.0.0")

        self.assertEqual(source.status, "OK")
        self.assertIsNone(source.readme_bytes)
        self.assertIsNone(source.prose_chars)


if __name__ == "__main__":
    unittest.main()
