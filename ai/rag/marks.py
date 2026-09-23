"""차이점 문단 강조 계산 (S15P21A506-470).

커뮤니티 요약 강조(백엔드 `CommunitySummaryValidator.marks`)와 같은 규칙이다 — 모델이 고른 핵심
문장·핵심어를 그대로 믿지 않고, `body` 안에서 **글자 그대로** 찾아 위치를 서버가 계산한다. 찾지
못했거나 규칙(길이·겹침)에 어긋나면 그 구간만 버린다 — 강조는 읽기 보조라 문단 자체를 실패시키지
않는다.

위치는 UTF-16 코드 단위 오프셋(`[start, end)`)으로 낸다 — 소비하는 쪽(TypeScript `String.slice`)과
같은 단위여야 한다. Python 문자열은 코드 포인트 단위라 서로게이트 쌍(이모지 등 BMP 밖 문자)이 본문에
있으면 둘이 어긋난다 — `_to_utf16_offset` 이 그 변환을 한다.
"""

from __future__ import annotations

from ai.rag.types import Mark, MarkKind

MAX_KEY_TERMS = 3
MAX_KEY_TERM_LENGTH = 30
MAX_KEY_SENTENCE_LENGTH = 220
# 핵심 문장 하나가 본문의 이 비율보다 길면 "전부 강조"와 다르지 않아 버린다.
MAX_KEY_SENTENCE_SHARE = 0.6


def compute_marks(
    body: str, key_sentence: str | None, key_terms: list[str] | None
) -> list[Mark]:
    """`body` 로 부터 핵심 문장 1개(있으면)·핵심어 최대 3개의 강조 구간을 계산한다.

    규칙: 핵심어는 서로 겹치면 먼저 온 것만 남기고, 핵심 문장 경계에 걸치면(부분만 겹치면) 버린다 —
    핵심 문장 안에 통째로 들어가는 것만 함께 둔다. 결과는 시작 위치 순으로 정렬된다.
    """
    if not body:
        return []

    sentence = _locate(body, key_sentence, MAX_KEY_SENTENCE_LENGTH)
    if sentence is not None and (sentence[1] - sentence[0]) > len(body) * MAX_KEY_SENTENCE_SHARE:
        sentence = None

    terms: list[tuple[int, int]] = []
    for raw in key_terms or []:
        if len(terms) >= MAX_KEY_TERMS:
            break
        term = _locate(body, raw, MAX_KEY_TERM_LENGTH)
        if term is None:
            continue
        if any(_overlaps(existing, term) for existing in terms):
            continue
        if sentence is not None and _overlaps(sentence, term) and not _contains(sentence, term):
            continue
        terms.append(term)

    spans: list[tuple[int, int, MarkKind]] = [(s, e, "KEY_SENTENCE") for s, e in ([sentence] if sentence else [])]
    spans += [(s, e, "KEY_TERM") for s, e in terms]
    spans.sort(key=lambda span: (span[0], span[1], span[2]))

    return [
        Mark(start=_to_utf16_offset(body, start), end=_to_utf16_offset(body, end), kind=kind)
        for start, end, kind in spans
    ]


def _locate(text: str, value: str | None, max_length: int) -> tuple[int, int] | None:
    """`value` 가 `text` 안에 코드 포인트 단위로 글자 그대로 있는 첫 구간. 없거나 길이 상한을 넘으면 None.

    위치는 아직 코드 포인트 인덱스다 — `compute_marks` 가 마지막에 한 번만 UTF-16 으로 변환한다.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > max_length:
        return None
    start = text.find(stripped)
    if start < 0:
        return None
    return start, start + len(stripped)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _contains(outer: tuple[int, int], inner: tuple[int, int]) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def _to_utf16_offset(text: str, codepoint_index: int) -> int:
    """코드 포인트 인덱스를 UTF-16 코드 단위 오프셋으로 바꾼다 — BMP 밖 문자(이모지 등)는 서로게이트
    쌍이라 UTF-16 에서 2 단위를 차지하므로 둘이 다를 수 있다."""
    return len(text[:codepoint_index].encode("utf-16-le")) // 2
