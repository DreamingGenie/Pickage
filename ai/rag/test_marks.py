"""compute_marks() 유닛테스트 (S15P21A506-470, unittest, stdlib).

백엔드 `CommunitySummaryMarksTest`(S15P21A506-408)와 같은 규칙을 검증한다 — 모델이 고른 핵심
문장·핵심어를 그대로 믿지 않고 `body` 안에서 글자 그대로 찾아 위치를 서버가 계산한다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_marks -v
"""

from __future__ import annotations

import unittest

from ai.rag.marks import compute_marks
from ai.rag.types import Mark

BODY = (
    "axios 는 브라우저와 Node.js를 함께 대상으로 하는 Promise 기반 HTTP 클라이언트예요. "
    "일반적으로 fetch 보다 더 높은 수준의 추상화를 기대하는 상황에서 많이 써요."
)
KEY_SENTENCE = "일반적으로 fetch 보다 더 높은 수준의 추상화를 기대하는 상황에서 많이 써요."


def _cut(body: str, mark: Mark) -> str:
    return body[mark.start : mark.end]


class LocateTests(unittest.TestCase):
    def test_body_에_글자_그대로_있는_핵심어와_핵심_문장만_구간으로_바꾼다(self):
        result = compute_marks(BODY, KEY_SENTENCE, ["Promise 기반", "HTTP 클라이언트"])

        # 결과는 시작 위치 순 — 핵심어 둘이 핵심 문장보다 앞에 나온다.
        self.assertEqual([m.kind for m in result], ["KEY_TERM", "KEY_TERM", "KEY_SENTENCE"])
        self.assertEqual(
            [_cut(BODY, m) for m in result],
            ["Promise 기반", "HTTP 클라이언트", KEY_SENTENCE],
        )

    def test_body에_없는_말은_버리고_문단을_실패시키지_않는다(self):
        result = compute_marks(BODY, "본문에 전혀 없는 문장이다.", ["없는 말", "Promise 기반"])

        self.assertEqual([_cut(BODY, m) for m in result], ["Promise 기반"])

    def test_위치는_서버가_계산한다(self):
        result = compute_marks(BODY, None, ["HTTP"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].start, BODY.index("HTTP"))
        self.assertEqual(result[0].end, BODY.index("HTTP") + 4)

    def test_None이거나_빈_입력은_빈_목록이다(self):
        self.assertEqual(compute_marks(BODY, None, None), [])
        self.assertEqual(compute_marks(BODY, "", []), [])
        self.assertEqual(compute_marks("", "a", ["b"]), [])


class OverlapTests(unittest.TestCase):
    def test_핵심어끼리_겹치면_먼저_온_것만_남긴다(self):
        result = compute_marks(BODY, None, ["Promise 기반 HTTP", "HTTP 클라이언트"])

        self.assertEqual([_cut(BODY, m) for m in result], ["Promise 기반 HTTP"])

    def test_핵심어가_핵심_문장_안에_통째로_들어가면_함께_둔다(self):
        result = compute_marks(BODY, KEY_SENTENCE, ["fetch"])

        self.assertEqual([m.kind for m in result], ["KEY_SENTENCE", "KEY_TERM"])

    def test_핵심어가_핵심_문장_경계에_걸치면_버린다(self):
        # 핵심 문장 시작 직전부터 시작 직후까지 넘나드는 구간
        straddling = BODY[BODY.index(KEY_SENTENCE) - 4 : BODY.index(KEY_SENTENCE) + 5]
        result = compute_marks(BODY, KEY_SENTENCE, [straddling])

        self.assertEqual([m.kind for m in result], ["KEY_SENTENCE"])

    def test_결과는_시작_위치_순으로_정렬된다(self):
        result = compute_marks(BODY, KEY_SENTENCE, ["fetch", "추상화"])

        starts = [m.start for m in result]
        self.assertEqual(starts, sorted(starts))


class LengthLimitTests(unittest.TestCase):
    def test_body_대부분을_덮는_핵심_문장은_강조가_아니라서_버린다(self):
        result = compute_marks(BODY, BODY, [])

        self.assertEqual(result, [])

    def test_개수와_길이_상한을_지킨다(self):
        result = compute_marks(BODY, None, ["axios", "브라우저", "Node.js", "Promise", "HTTP"])

        self.assertLessEqual(len(result), 3)
        too_long = "x" * 31
        self.assertEqual(compute_marks(too_long + BODY, None, [too_long]), [])


class Utf16OffsetTests(unittest.TestCase):
    """서로게이트 쌍(이모지)이 낀 본문에서도 오프셋이 UTF-16 코드 단위여야 프런트(JS)와 맞는다."""

    def test_이모지가_핵심어_앞에_있어도_오프셋은_utf16_기준이다(self):
        text = "가나다 🔥 라마바"
        # 🔥 는 서로게이트 쌍(2 코드 유닛)이라 codepoint 인덱스와 UTF-16 오프셋이 여기서부터 어긋난다.
        result = compute_marks(text, None, ["라마바"])

        self.assertEqual(len(result), 1)
        utf16_units = text.encode("utf-16-le")
        marked = utf16_units[result[0].start * 2 : result[0].end * 2].decode("utf-16-le")
        self.assertEqual(marked, "라마바")


if __name__ == "__main__":
    unittest.main()
