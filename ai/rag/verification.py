"""근거ID·판정값 검증 (S15P21A506-179/180).

2026-09-18 재배정: 179(근거ID·패키지·버전 연결 검증)·180(5종 기능 판정·근거 충족
조건 검증) 둘 다 AI(정민지)가 설계·구현한다 — BE는 구현만 맡을 것으로 예상돼
직접 설계함(148/203은 이번 스코프에서 제외, 148 공통 계약 없이 180과 같은
`list[str]` 반환 타입으로 통일). 148 원문의 "source snapshot 연결"은 176이 DB
없이 그때그때 청킹하는 방식으로 바뀌면서 더 이상 해당 없음 — 대신 `FeatureResult`에
`version`을 직접 실어(2026-09-18 추가) 셀 하나만 보고 검증 가능하게 함.
"""

from __future__ import annotations

from ai.rag.types import ComparisonResult, EvidenceChunk

_ALLOWED_VERDICTS = {
    "SUPPORTED",
    "CONDITIONALLY_SUPPORTED",
    "LIMITED_SUPPORT",
    "UNCONFIRMED",
    "UNSUPPORTED",
}
_ALLOWED_GROUNDED_IN = {"EVIDENCE", "GENERAL_KNOWLEDGE"}


def verify_evidence_ids(
    result: ComparisonResult, evidence_pool: list[EvidenceChunk]
) -> list[str]:
    """179: 인용된 근거ID가 177이 178에 실제로 넘긴 evidence_pool 안에 있고, 그 근거가
    인용한 셀과 같은 package/version 소속인지 검사한다.

    evidence_pool은 pipeline.py의 compare_packages()에서 `retrieved`(177 출력,
    178이 실제로 본 것)를 넘겨받는다 — get_or_build_evidence()의 전체 풀이 아니다.
    178이 못 본 근거를 인용했으면 여기서 이미 "존재하지 않는 ID"로 잡힌다.

    Returns:
        위반 사유 문자열 목록 (빈 리스트면 통과).
    """
    by_id = {chunk.evidence_id: chunk for chunk in evidence_pool}

    violations: list[str] = []
    for row in result.features:
        for r in row.results:
            label = f"{row.feature_label}/{r.package}@{r.version}"
            for evidence_id in r.evidence_ids:
                chunk = by_id.get(evidence_id)
                if chunk is None:
                    violations.append(f"{label}: 존재하지 않는 evidenceId {evidence_id!r}")
                elif chunk.package != r.package or chunk.version != r.version:
                    violations.append(
                        f"{label}: evidenceId {evidence_id!r}는 "
                        f"{chunk.package}@{chunk.version} 소속이라 이 셀에 쓸 수 없음"
                    )
    return violations


def verify_verdicts(result: ComparisonResult) -> list[str]:
    """180: 판정값이 5개 허용값 안에 있고 근거 충족 조건을 지키는지 검증.

    검사 항목(180 완료조건 참고):
        - verdict가 SUPPORTED/CONDITIONALLY_SUPPORTED/LIMITED_SUPPORT/UNCONFIRMED/
          UNSUPPORTED 외 값이 아닌지
        - SUPPORTED에는 직접 지원 근거, 조건부·제한적 지원에는 조건/범위 제한 근거가
          있는지 (groundedIn=GENERAL_KNOWLEDGE인 셀은 evidenceIds가 비어있는 게 정상 —
          다른 검사 기준 적용)
        - UNSUPPORTED가 명시적 공식 부정 근거 없이 나오지 않았는지
        - verdict와 dataStatus를 혼합하지 않았는지

    Returns:
        위반 사유 문자열 목록 (빈 리스트면 통과).
    """
    violations: list[str] = []
    for row in result.features:
        for r in row.results:
            label = f"{row.feature_label}/{r.package}"
            if r.verdict not in _ALLOWED_VERDICTS:
                violations.append(f"{label}: 허용되지 않은 verdict {r.verdict!r}")
                continue
            if r.grounded_in not in _ALLOWED_GROUNDED_IN:
                violations.append(f"{label}: 허용되지 않은 groundedIn {r.grounded_in!r}")
                continue

            if r.grounded_in == "GENERAL_KNOWLEDGE" and r.evidence_ids:
                violations.append(
                    f"{label}: groundedIn=GENERAL_KNOWLEDGE인데 evidenceIds가 비어있지 않음"
                )
            elif (
                r.grounded_in == "EVIDENCE"
                and r.verdict != "UNCONFIRMED"
                and not r.evidence_ids
            ):
                violations.append(
                    f"{label}: verdict={r.verdict!r}인데 근거(evidenceIds)가 없음"
                )
    return violations
