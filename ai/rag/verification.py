"""생성 결과 검증 (S15P21A506-179/180).

2026-09-22 출력 형식 전환(판정표 → 공통점·차이점 서술)으로 근거ID 검증(179)과 판정값 검증(180)은
대상이 없어져 없앴다. 남은 계약은 "비교한 패키지마다 차이점 문단이 정확히 하나 있다" 이다 —
모델이 패키지를 빠뜨리거나, 요청에 없는 패키지를 지어내거나, 버전을 바꿔 쓰면 화면이 엉뚱한 글을
보여주게 된다.
"""

from __future__ import annotations

from ai.rag.types import ComparisonResult, PackageRef


def verify_result(result: ComparisonResult, packages: list[PackageRef]) -> list[str]:
    """공통점이 비어 있지 않고, 요청한 패키지마다 차이점 문단이 한 개씩 있는지 검사한다.

    Returns:
        위반 사유 문자열 목록 (빈 리스트면 통과).
    """
    violations: list[str] = []
    if not result.common.strip():
        violations.append("common 이 비어 있음")

    expected = {p.name: p.version for p in packages}
    seen: set[str] = set()
    for note in result.differences:
        label = f"{note.package}@{note.version}"
        if note.package not in expected:
            violations.append(f"{label}: 요청하지 않은 패키지")
            continue
        if note.version != expected[note.package]:
            violations.append(f"{label}: 요청한 버전은 {expected[note.package]}")
        if note.package in seen:
            violations.append(f"{label}: 차이점 문단이 두 번 나옴")
        seen.add(note.package)
        if not note.body.strip():
            violations.append(f"{label}: 차이점 문단이 비어 있음")

    for name in expected:
        if name not in seen:
            violations.append(f"{name}: 차이점 문단이 없음")
    return violations
