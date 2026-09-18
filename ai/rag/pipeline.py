"""전체 흐름 오케스트레이션: 175 캐시 조회 → 177 검색 → 178 생성 → 179/180 검증.

DEC-FEATURE-CACHE-20260917-01 (docs/Pickage_기능별_개발_구상안_0917.md §7.1·§14.5):
    - SourceSnapshot·EvidenceChunk(EvidenceRecord)는 (package, version) 단위로
      PostgreSQL에 영속화해 재사용한다.
    - ComparisonResult(FeatureAssessment 등 판정 결과)는 영속화하지 않고 매 요청
      새로 계산한다.

순수 순차 파이프라인이다 — 루프/조건부 재시도 없음(readme-valiant-feather 계획 문서
"구현은 LangGraph 없이 순수 Python 함수로" 결정 참고). 179/180이 실패해도 자동
재시도하지 않고 예외로 실패를 알린다.
"""

from __future__ import annotations

from ai.rag.generation import generate
from ai.rag.readme_chunker import chunk_readme
from ai.rag.retrieval import retrieve
from ai.rag.types import ComparisonResult, EvidenceChunk, PackageRef
from ai.rag.verification import verify_evidence_ids, verify_verdicts


class VerificationFailedError(Exception):
    """179/180 검증 실패 시. 위반 사유 목록을 담는다."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__(f"검증 실패: {violations}")
        self.violations = violations


def get_or_build_evidence(package: str, version: str) -> list[EvidenceChunk]:
    """(package, version)의 EvidenceChunk를 조회하고, 없으면 새로 만든다.

    흐름(계획 문서 "공식 결정" 절 참고):
        1. PostgreSQL에서 이 (package, version)의 EvidenceChunk가 이미 있는지 조회
           — 176(정보경) 스키마/영속화 계층. 있으면 그대로 반환 (175 재실행 없음).
        2. 없으면 `app` 노드 로컬 파일(README 원본, 데이터팀 LRU 캐시)을 읽는다.
           파일이 evict돼서 없으면 청킹 실패와 구분되는 "재수집 필요" 상태를
           호출자에게 알려야 한다(아직 TODO).
        3. chunk_readme()로 청킹하고, 결과를 PostgreSQL에 저장한 뒤 반환한다
           (저장은 176 책임 — 여기서는 자리만 잡아둔다).

    TODO(176 연동 전): 지금은 DB 조회/저장이 없어 매번 2~3단계로 간다. 176 스키마가
    정해지면 이 함수 안에 캐시 조회 로직을 채운다.
    """
    raise NotImplementedError


def compare_packages(
    packages: list[PackageRef],
    variant: str = "A",
    top_k_per_package: int = 15,
) -> ComparisonResult:
    """175~180 전체 흐름을 순서대로 실행한다.

    Args:
        variant: 178에 쓸 프롬프트. "A"(근거 전용, 기본) 또는 "B"(실험용).

    Raises:
        VerificationFailedError: 179/180 중 하나라도 위반이 있으면.
    """
    evidence_pool: list[EvidenceChunk] = []
    for pkg in packages:
        evidence_pool.extend(get_or_build_evidence(pkg.name, pkg.version))

    retrieved = retrieve(packages, evidence_pool, top_k_per_package=top_k_per_package)
    result = generate(packages, retrieved, variant=variant)

    violations = verify_evidence_ids(result, retrieved) + verify_verdicts(result)
    if violations:
        raise VerificationFailedError(violations)

    return result


__all__ = [
    "VerificationFailedError",
    "chunk_readme",
    "compare_packages",
    "get_or_build_evidence",
]
