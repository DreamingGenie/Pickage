# 07 계산 정책 확정

2026-09-09 사용자 결정 기록. 기존 구현은 이 조합을 지원하므로 이번에는 정책 파일과 문서만 갱신한다.

사용자 답변: “NULL제외하고 미해석은 PARTIAL로 보존하자. 그리고 다음 작업을 진행하기 전에 지금 한 작업들 결과를 좀 보고싶은데 어케해?”

| 항목 | 확정 선택 | 적용 의미 |
| --- | --- | --- |
| 의존성 종류 | 일반 `dependencies` | 이전 사용자 선택 유지. peer/optional은 계산에서 제외하고 원본 계보·제외 사유·개수 보존 |
| 배포일 NULL | `exclude` | 배포일을 모르는 버전을 source와 target 후보 양쪽에서 제외. 알려진 배포일은 정확한 snapshot 시점 이하 조건 적용 |
| 미해석 및 불완전 입력 | `partial` | 해석 결과와 미해석 사유를 로컬 PARTIAL로 보존. 정상 완료 게시와 08의 정상 집계로 사용하지 않음 |
| 다음 실행 | 현재 결과 검토 우선 | 실제 전체 계산·게시를 시작하지 않고 현재 산출물과 검증 기록을 보여줌 |

기존 `snapshot-time-v1`과 02 산출물은 변경하지 않는다. 07만 NULL 배포일 버전을 추가로 제외하여 source/target 집합을 좁힌다. 이 때문에 07의 실제 source 수는 Curated version 전체 행 수와 다를 수 있으며, 제외 수는 실제 계산 시 기록한다.

확정 정책 파일: [policy.json](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/data/requirements-resolution/policy.json).

정책 document의 SHA256: `721c9d968f75429497b5e30b86ba0137998ea6a6ab1766bfb274d5661da52ef8`.

`make_policy`로 생성하고 `validate_policy`로 정확한 계약과 해시를 검증했다. policy 파일 생성은 계산 실행을 시작하지 않는다.

기존 합성 데이터 통합 검증 `integration-dbf68cf2`는 당시 `include + partial` 정책으로 실행한 역사적 결과다. 원본 manifest와 결과를 수정하지 않는다. 기존 Spark 경계 테스트에는 NULL 제외 시 source·target이 함께 줄어드는 검증이 포함돼 있지만, 이번에 확정한 정책 파일로 실제 전체 데이터를 계산한 결과는 아직 없다.
