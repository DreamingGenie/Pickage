"""로컬 인계 파일 생성기(scripts/make_local_docs.py) 유닛테스트 (S15P21A506-419, unittest, stdlib).

이 도구가 만든 문서를 rag 파서가 그대로 읽는지(서식 계약), 그리고 백엔드 DocAssembler 에서
옮긴 판정 규칙이 어긋나지 않는지만 본다. npm 은 부르지 않는다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_make_local_docs -v
"""

from __future__ import annotations

import unittest

from ai.rag.readme_chunker import parse_data_team_envelope, parse_source_footer
from ai.rag.scripts.make_local_docs import (
    _doc_status,
    _lstrip_dot_slash,
    _manifest,
    assemble,
    prose,
)


def _document(pkg: dict, body: str, status: str = "LIMITED") -> str:
    return assemble(
        "foo", "1.0.0", pkg, count=3, unpacked=1234, dts=["dist/index.d.ts"],
        body=body, kind="TYPES", status=status, readme_bytes=len(body.encode()), prose_chars=len(prose(body)),
    )


class GeneratedDocumentContractTests(unittest.TestCase):
    """만든 문서는 운영 인계 파일과 같은 서식이라 rag 파서가 그대로 읽어야 한다."""

    def test_round_trips_through_the_envelope_parser(self):
        doc = _document({"description": "A parser", "license": "MIT"}, "# foo\n\nBody text.")

        envelope = parse_data_team_envelope(doc)

        self.assertEqual((envelope.package, envelope.version), ("foo", "1.0.0"))
        self.assertEqual(envelope.description, "A parser")
        self.assertEqual(envelope.readme_body, "# foo\n\nBody text.")
        self.assertIn("소비 형태 · 진입점", envelope.structured_facts)  # 공백 있는 제목이 실제 서식
        self.assertIn("설치 조건", envelope.structured_facts)

    def test_footer_status_is_readable_by_the_footer_parser(self):
        doc = _document({"description": "A parser"}, "Body", status="OK")

        source = parse_source_footer(parse_data_team_envelope(doc).source_footer, "foo", "1.0.0")

        self.assertEqual(source.status, "OK")
        self.assertEqual(source.readme_bytes, 4)

    def test_missing_description_uses_the_placeholder_and_is_read_back_as_empty(self):
        envelope = parse_data_team_envelope(_document({}, "Body"))

        self.assertEqual(envelope.description, "")

    def test_a_readme_with_a_horizontal_rule_survives_the_round_trip(self):
        body = "Intro\n\n---\n\n## API\n\nloadAll"

        envelope = parse_data_team_envelope(_document({"description": "d"}, body))

        self.assertEqual(envelope.readme_body, body)


class DocAssemblerRulesTests(unittest.TestCase):
    """백엔드 DocAssembler 판정 규칙을 그대로 옮겼는지."""

    def test_status_thresholds(self):
        manifest = _manifest({"description": "d"}, "foo")
        empty = _manifest({}, "foo")

        self.assertEqual(_doc_status(1000, manifest, []), "OK")
        self.assertEqual(_doc_status(999, manifest, []), "LIMITED")  # 설명만 있어도 LIMITED
        self.assertEqual(_doc_status(0, empty, ["a.d.ts"]), "LIMITED")
        self.assertEqual(_doc_status(0, empty, []), "NONE")

    def test_prose_drops_code_fences_links_badges_and_headings(self):
        text = "# Title\n\n![badge](x.svg)\n\nSee [docs](https://x).\n\n```js\ncode()\n```\n"

        self.assertEqual(prose(text), "Title See docs.")

    def test_root_entry_becomes_an_empty_string_like_the_real_documents(self):
        # 운영 파일에서 실제로 `진입점 2개: , browser` 로 보인다 — "." 에서 "./" 문자 집합을 벗기기 때문.
        self.assertEqual(_lstrip_dot_slash("."), "")
        self.assertEqual(_lstrip_dot_slash("./browser"), "browser")
        subs = _manifest({"exports": {".": {}, "./browser": {}, "./package.json": {}, "./x/*": {}}}, "foo")

        self.assertEqual(subs["subpaths"], ["", "browser"])
        self.assertEqual(subs["subpath_count"], 2)


if __name__ == "__main__":
    unittest.main()
