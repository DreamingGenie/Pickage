"""전체 흐름 오케스트레이션: 175 청킹 → 177 검색 → 178 생성 → 179/180 검증.

2026-09-18 결정으로 DEC-FEATURE-CACHE-20260917-01(PostgreSQL 영속화)은 폐기됐다 —
SourceSnapshot·EvidenceChunk를 DB에 저장해 재사용하지 않고, 비교 요청이 올 때마다
README를 그때그때 읽어서 청킹한다([[rag-176-no-db-cache]] 메모 참고). 176 담당도
정민지로 이관됨. ComparisonResult(판정 결과)를 영속화하지 않고 매 요청 새로
계산한다는 부분은 그대로다.

순수 순차 파이프라인이다 — 루프/조건부 재시도 없음(readme-valiant-feather 계획 문서
"구현은 LangGraph 없이 순수 Python 함수로" 결정 참고). 179/180이 실패해도 자동
재시도하지 않고 예외로 실패를 알린다.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ai.rag.generation import generate
from ai.rag.readme_chunker import chunk_readme, parse_data_team_envelope
from ai.rag.readme_source import ReadmeSourceNotFoundError, resolve_readme_path
from ai.rag.retrieval import retrieve
from ai.rag.types import ComparisonResult, EvidenceChunk, PackageRef
from ai.rag.verification import verify_evidence_ids, verify_verdicts


class VerificationFailedError(Exception):
    """179/180 검증 실패 시. 위반 사유 목록을 담는다."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__(f"검증 실패: {violations}")
        self.violations = violations


def get_or_build_evidence(
    package: str, version: str, root: str | Path | None = None
) -> list[EvidenceChunk]:
    """(package, version)의 README 인계 파일을 읽어 즉시 청킹한다 (176).

    2026-09-18 결정: DB 캐시 없음 — 매 요청 파일을 읽고 chunk_readme()를 그대로
    돌린다([[rag-176-no-db-cache]]). snapshot_id는 파일 원문의 sha256 앞 16자로
    잡는다 — 내용이 같으면 항상 같은 id가 나와서(순수 함수 성질 유지), DB 없이도
    "이 근거가 어느 원문 스냅샷에서 나왔는지"를 재현 가능하게 식별할 수 있다.

    Args:
        root: README 인계 파일 루트. 생략하면 `README_SOURCE_ROOT` 환경변수를 쓴다
            (app 노드 실 경로: `/srv/pickage/docs`, 2026-09-18 데이터팀 전달).

    Raises:
        ReadmeSourceNotFoundError: 이 (package, version) 파일이 없을 때.
    """
    root = root if root is not None else os.environ["README_SOURCE_ROOT"]
    path = resolve_readme_path(package, version, root)
    try:
        doc_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReadmeSourceNotFoundError(str(path)) from exc

    envelope = parse_data_team_envelope(doc_text)
    snapshot_id = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()[:16]
    return chunk_readme(envelope.readme_body, package, version, snapshot_id=snapshot_id)


def compare_packages(
    packages: list[PackageRef],
    max_chars_per_package: int = 12000,
) -> ComparisonResult:
    """175~180 전체 흐름을 순서대로 실행한다.

    Args:
        max_chars_per_package: 177(retrieve)에 그대로 전달하는 패키지당 근거
            글자수 예산 (2026-09-18 결정, [[retrieve]] docstring 참고).

    Raises:
        VerificationFailedError: 179/180 중 하나라도 위반이 있으면.
    """
    evidence_pool: list[EvidenceChunk] = []
    for pkg in packages:
        evidence_pool.extend(get_or_build_evidence(pkg.name, pkg.version))

    retrieved = retrieve(packages, evidence_pool, max_chars_per_package=max_chars_per_package)
    result = generate(packages, retrieved)

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
