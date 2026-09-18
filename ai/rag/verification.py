"""근거ID·판정값 검증 (S15P21A506-179/180).

179(근거ID·패키지·버전·판정 연결 검증)는 BE(정보경) 담당이고, 180(5종 기능 판정·근거
충족 조건 검증)은 AI(정민지) 담당이다. verify_evidence_ids()는 로컬에서 전체 흐름을
끝까지 테스트하기 위한 스텁일 뿐, 실제 구현은 BE와 별도 합의가 필요하다.
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
    """179(BE 담당 — 로컬 테스트용 스텁).

    검사 항목(179 완료조건 참고):
        - 근거 ID 존재와 package/version/source snapshot 연결
        - 공개 근거 ID가 해당 셀의 기능·판정·원문 위치를 정확히 가리키는지
        - 식별자 오염·없는 ID·다른 package/version의 ID를 구조화 실패로 반환

    Returns:
        위반 사유 문자열 목록 (빈 리스트면 통과).
    """
    raise NotImplementedError


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
