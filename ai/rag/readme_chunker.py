"""README → EvidenceChunk 청킹 (S15P21A506-175).

설계 근거: readme-valiant-feather 계획 문서.
무거운 의존성 없이 stdlib만으로 테스트 가능하게 유지한다
(ai/similarity/similarity_batch_pipeline.py의 지연 import 관례와 같은 이유).

175는 순수 함수다 — 같은 (package, version, README 원문, 분석 로직 버전) 입력이면
항상 같은 EvidenceChunk 목록을 반환한다. 언제/얼마나 자주 호출할지(캐시 관리)는
호출부(pipeline.py의 get_or_build_evidence)의 책임이지 이 모듈의 책임이 아니다.
"""

from __future__ import annotations

import re

from ai.rag.types import DataTeamEnvelope, EvidenceChunk, PackageSource

_ATX_HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*\n?$")
_FENCE_LINE_RE = re.compile(r"^(```+|~~~+)")


def _split_into_paragraphs(text: str) -> list[str]:
    """빈 줄로 문단을 나누되, 코드펜스(``` / ~~~) 안의 빈 줄은 경계로 보지 않는다.

    펜스 하나 전체(여는 줄~닫는 줄)는 항상 하나의 문단으로 묶여서 나온다.
    """
    paragraphs: list[str] = []
    current_lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if _FENCE_LINE_RE.match(stripped):
            in_fence = not in_fence
            current_lines.append(line)
            continue
        if not stripped and not in_fence:
            if current_lines:
                paragraphs.append("\n".join(current_lines).strip())
                current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        paragraphs.append("\n".join(current_lines).strip())
    return [p for p in paragraphs if p]


def _split_oversized_body(body: str, max_chars: int) -> list[str]:
    """본문이 max_chars를 넘으면 문단(빈 줄) 경계로 여러 조각으로 나눈다.

    코드펜스는 통째로 한 문단 취급되어 절대 안에서 안 잘린다(`_split_into_paragraphs`).
    문단 자체가 max_chars를 넘는 경우(예: 거대한 코드펜스 하나)의 겹침 슬라이딩
    윈도우는 아직 없음 — 그 경우 문단을 그대로(상한 초과 허용) 반환한다.
    """
    if len(body) <= max_chars:
        return [body]

    parts: list[str] = []
    current = ""
    for para in _split_into_paragraphs(body):
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= max_chars:
            current = f"{current}\n\n{para}"
        else:
            parts.append(current)
            current = para
    if current:
        parts.append(current)
    return parts


def _find_headings(text: str) -> list[tuple[int, int, str]]:
    """코드펜스(``` / ~~~) 안의 `#` 줄은 헤딩으로 인식하지 않는다.

    Returns:
        (heading_line_start, heading_line_end, heading_text) 튜플 목록.
        heading_line_end는 그 헤딩 줄 바로 다음 오프셋 — 본문 시작점으로 쓴다.
    """
    headings: list[tuple[int, int, str]] = []
    in_fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if _FENCE_LINE_RE.match(stripped):
            in_fence = not in_fence
        elif not in_fence:
            m = _ATX_HEADING_LINE_RE.match(line)
            if m:
                headings.append((offset, offset + len(line), m.group(2).strip()))
        offset += len(line)
    return headings

# 잡음 필터링 deny-list — 시작점일 뿐, 127 실제 수집물로 튜닝 필요 (계획 문서 참고)
_NOISE_HEADINGS = {
    "license",
    "contributors",
    "sponsors",
    "backers",
    "changelog",
    "code of conduct",
    "authors",
}


# `---` 한 줄 + 다음 줄이 `근거:` 로 시작하는 꼬리 구분선. CRLF 도 받는다.
_FOOTER_SEPARATOR_RE = re.compile(r"^---[ \t]*\r?\n(?=근거:)", re.MULTILINE)

# 인계 파일이 설명이 비었을 때 넣는 자리표시(백엔드 DocAssembler). 근거로 쓰지 않는다.
_NO_DESCRIPTION = "(설명 없음)"


class EnvelopeParseError(Exception):
    """데이터팀 인계 포맷(봉투)이 예상과 다를 때 명확히 실패시키기 위한 예외.

    앵커 텍스트(`## README 전문` 등)가 안 맞으면 조용히 잘못 파싱하지 않고 여기서 멈춘다.
    """


def parse_data_team_envelope(doc_text: str) -> DataTeamEnvelope:
    """0단계: `소비 형태·진입점`/`설치 조건`(구조화 데이터) / README 전문 / 꼬리 출처메타 3분리.

    파일 구조 (debug@4.4.3.md 실물 기준):
        # {package}@{version}
        {한 줄 설명}

        ## 소비 형태 · 진입점
        - ...

        ## 설치 조건
        - ...

        ## README 전문
        {원본 README 마크다운 전체}

        ---
        근거: S1 README ... 상태 OK

    Raises:
        EnvelopeParseError: `## README 전문` 헤딩을 찾을 수 없을 때.
    """
    anchor = "## README 전문"
    anchor_idx = doc_text.find(anchor)
    if anchor_idx == -1:
        raise EnvelopeParseError(f"'{anchor}' 헤딩을 찾을 수 없습니다.")

    header_region = doc_text[:anchor_idx]
    after_anchor = doc_text[anchor_idx + len(anchor):]

    title_match = re.search(r"^#[ \t]+(.+?)[ \t]*$", header_region, re.MULTILINE)
    if not title_match:
        raise EnvelopeParseError("제목 줄('# {package}@{version}')을 찾을 수 없습니다.")

    package, sep, version = title_match.group(1).rpartition("@")
    if not sep:
        raise EnvelopeParseError(f"제목 줄 형식이 올바르지 않습니다: {title_match.group(1)!r}")

    # 꼬리는 `---` 다음 줄이 `근거:` 로 시작하는 **마지막** 자리다. 예전에는 첫 `---` 를 꼬리로
    # 봐서, README 중간에 수평선이 있으면 그 뒤 본문이 통째로 근거에서 사라졌다(운영 노드
    # 실측 5.4%, S15P21A506-419). 꼬리가 없으면 남은 전체를 README 로 본다.
    footer_matches = list(_FOOTER_SEPARATOR_RE.finditer(after_anchor))
    if footer_matches:
        footer_match = footer_matches[-1]
        readme_body = after_anchor[: footer_match.start()].strip()
        source_footer = after_anchor[footer_match.end():].strip()
    else:
        readme_body = after_anchor.strip()
        source_footer = ""

    fact_headings = _find_headings(header_region)[1:]  # [0]은 제목(# {package}@{version}) 자신
    description_end = fact_headings[0][0] if fact_headings else len(header_region)
    description = header_region[title_match.end():description_end].strip()
    if description == _NO_DESCRIPTION:
        description = ""
    structured_facts: dict[str, str] = {}
    for i, (_, body_start, heading_text) in enumerate(fact_headings):
        body_end = fact_headings[i + 1][0] if i + 1 < len(fact_headings) else len(header_region)
        body = header_region[body_start:body_end].strip()
        if body:
            structured_facts[heading_text] = body

    return DataTeamEnvelope(
        package=package,
        version=version,
        structured_facts=structured_facts,
        readme_body=readme_body,
        source_footer=source_footer,
        description=description,
    )


_STATUS_RE = re.compile(r"상태\s+(OK|LIMITED|NONE)\b")
_README_BYTES_RE = re.compile(r"README\s+([\d,]+)\s*B\b")
_PROSE_CHARS_RE = re.compile(r"산문\s+([\d,]+)\s*자")


def _to_int(match: re.Match[str] | None) -> int | None:
    return int(match.group(1).replace(",", "")) if match else None


def parse_source_footer(footer: str, package: str, version: str) -> PackageSource:
    """인계 파일 꼬리(`근거: S1 README 917 B / 산문 214자 · … · 상태 LIMITED`)를 읽는다.

    각 값은 따로 읽는다 — 숫자 형식이 달라져도 상태는 살린다. **읽지 못한 값은 None** 이고
    추측해서 채우지 않는다(S15P21A506-419).
    """
    status_match = _STATUS_RE.search(footer)
    return PackageSource(
        package=package,
        version=version,
        status=status_match.group(1) if status_match else None,  # type: ignore[arg-type]
        readme_bytes=_to_int(_README_BYTES_RE.search(footer)),
        prose_chars=_to_int(_PROSE_CHARS_RE.search(footer)),
    )


def chunk_readme(
    readme_text: str,
    package: str,
    version: str,
    snapshot_id: str,
    max_chunk_chars: int = 1800,
) -> list[EvidenceChunk]:
    """1~3단계: README 전문 텍스트 → EvidenceChunk 목록.

    규칙 (계획 문서 "처리 파이프라인" 절 참고):
        - 헤딩(ATX `#`~`######`, Setext `===`/`---`) 아무 레벨이나 분리 기준. 레벨은
          section 경로 표기(`"A > B"`)에만 쓰고 분리 여부 판단엔 안 씀.
        - 문서 최상단 제목~첫 헤딩 사이는 `section: "(intro)"` 청크로 묶음 — 헤딩 없는
          짧은 README일수록 여기에 핵심 정보가 있는 경우가 많음.
        - 헤딩이 없거나 부족하면 문단(빈 줄) 분리 → 그래도 크면 겹침 있는 슬라이딩 윈도우.
        - 코드블록(```)·표는 절대 안에서 안 자름 (경계 보존).
        - 몸통이 빈 헤딩은 청크를 만들지 않고 드롭 (SUPPLEMENTARY 격하 대상과 다른 케이스).
        - _NOISE_HEADINGS 매칭 섹션은 삭제 대신 verificationLevel=SUPPLEMENTARY로 격하.
        - README의 지시문(install/build/postinstall 등)은 절대 실행하지 않음 — 텍스트로만 취급.

    Args:
        max_chunk_chars: 청크당 문자 상한(기본 1800 ≈ 450토큰). §8 "전체 문서를 무제한
            AI 입력으로 전달하지 않음" 기준. bge-small 512토큰 한도와는 독립적으로 잡은
            값 — 147이 검색/생성 임베딩 모델을 확정하면 재검토 필요.

    Returns:
        section/excerpt/verificationLevel이 채워진 EvidenceChunk 리스트.
        sourceType은 항상 "TARBALL_README".
    """
    chunks: list[EvidenceChunk] = []

    def _add(section: str, body: str) -> None:
        if not body:
            return
        verification_level = (
            "SUPPLEMENTARY" if section.strip().lower() in _NOISE_HEADINGS else "DISTRIBUTED_ARTIFACT"
        )
        for part in _split_oversized_body(body, max_chunk_chars):
            chunks.append(
                EvidenceChunk(
                    evidence_id=f"{package}@{version}#{len(chunks)}",
                    snapshot_id=snapshot_id,
                    package=package,
                    version=version,
                    section=section,
                    excerpt=part,
                    confirmed_content=part,
                    verification_level=verification_level,
                )
            )

    headings = _find_headings(readme_text)

    intro_end = headings[0][0] if headings else len(readme_text)
    _add("(intro)", readme_text[:intro_end].strip())

    for i, (_, body_start, section) in enumerate(headings):
        body_end = headings[i + 1][0] if i + 1 < len(headings) else len(readme_text)
        _add(section, readme_text[body_start:body_end].strip())

    return chunks
