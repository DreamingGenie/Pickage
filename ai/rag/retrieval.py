"""근거 검색 (S15P21A506-177).

"해석 B + LLM 단일 호출" 결정(readme-valiant-feather 계획 문서 참고)에 따라,
특정 기능 질문별로 미리 검색하지 않는다 — 비교 축 자체를 178이 그 순간 정하므로
"이 기능에 대한" 검색을 177이 미리 할 수 없다. 대신 패키지별로 판정에 쓸 만한
근거를 폭넓게 추려 178에 한 번에 넘긴다.
"""

from __future__ import annotations

from ai.rag.types import EvidenceChunk, PackageRef


def retrieve(
    packages: list[PackageRef],
    evidence_pool: list[EvidenceChunk],
    top_k_per_package: int = 15,
) -> list[EvidenceChunk]:
    """비교 대상 패키지별로 178에 넘길 근거를 추린다.

    규칙:
        - 다른 package/version의 근거가 섞이지 않게 범위를 고정한다(§7 근거 추적 원칙).
        - verificationLevel=SUPPLEMENTARY는 후순위로 밀어 top_k에서 우선순위를 낮춘다
          (완전히 제외하지는 않음 — SEARCH_TRACE류 질문에 쓰일 수 있음).
        - 임베딩 기반 의미 검색을 쓸지, section 이름 기반 휴리스틱으로 충분할지는
          147의 POC 결정 사안. 이 함수 시그니처는 어느 쪽이든 그대로 유지된다.

    Args:
        top_k_per_package: 패키지 하나당 178에 넘길 최대 근거 개수.

    Returns:
        evidence_pool의 부분집합 (원본 EvidenceChunk 객체 그대로, 변형하지 않음).
    """
    raise NotImplementedError
