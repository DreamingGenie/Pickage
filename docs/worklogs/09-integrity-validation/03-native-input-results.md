# native 입력 연결 코드·작은 샘플 검증 결과

2026-09-12 승인된 병렬 준비 범위를 완료했다. 별도 worktree
`C:\Users\SSAFY\workspace\S15P21A506-09-integrity-validation`, 브랜치
`codex/09-integrity-validation`에서만 작업했다. Jira 연결은 사용자 결정에 따라 보류 중이다.

## 실제 변경

- `native_selection.py`: package/version·observed package_snapshot의 기존 metadata 선택 함수를 재사용한다.
  명시한 run·정확한 snapshot 시각·manifest pin·기대 건수·완료 표식·파일 목록을 대조한다.
- `local_bundle.py`: 요청한 로컬 metadata만 읽는다. 중복 JSON 키, 과도한 크기,
  경로 탈출·wildcard·symlink·Windows reparse point를 거부한다.
- `native_samples.py`: 명시적으로 선택한 작은 원본 shard의 크기·SHA·열 순서/타입·footer 건수를 검사한다.
  선택하지 않은 파일은 열지 않고, 실제 검사 범위를 역할별로 남긴다.
- `native_input.py`: 별도 CLI와 JSON/Markdown 보고서. 오류와 재실행에서 기존 결과를 보존한다.
- `native_fixture.py`, `test_native_selection.py`, `test_native_input.py`: 작은 native 형식 예제와 오류 주입 테스트.
- 기존 합성 검증 CLI·SQL 기능은 유지하고 [사용 안내](../../../pipeline/integrity_validation/NATIVE_INPUT.md)를 추가했다.

생성 코드 SHA와 검증 코드 SHA를 구분한다. producer contract는 원문 값으로만 보존하며,
현재 코드 hash로 과거 파일의 생성 계약을 채워 넣지 않는다.

## 실측 결과

최종 전체 unittest **63개 통과**: 기존 합성 검사 30개 + native 입력 검사 33개.
테스트 로그는 [native-tests.txt](evidence/native-tests.txt), 구조화된 확인 결과는
[native-verification.json](evidence/native-verification.json)에 남겼다.
수정 후 독립 재검토에서도 native 테스트 33개와 두 CLI 예제가 통과했고,
이번 제한된 입력 연결 범위에 남은 차단 결함이 없다는 판정을 받았다.

| 작은 합성 native 예제 | 읽은 metadata | 검사한 Parquet | 결과 |
| --- | ---: | ---: | --- |
| package/version | 2개 / 822 bytes | 2개 / 1,875 bytes / footer 합계 4행 | metadata MATCH, samples MATCH |
| observed package_snapshot | 3개 / 1,386 bytes | 2개 / 914 bytes / footer 합계 4행 | metadata MATCH, samples MATCH |

observed 예제의 quality 파일은 선택하지 않아 `0 / 1개 검사`로 보고한다. 일부러 quality 파일을
삭제해도 선택한 service·identity 검사만 진행하며, 이를 전체 quality 검증이라고 보고하지 않음을 확인했다.
예제의 quality 값은 스키마 시험용 NULL이고 실제 품질 계약을 충족하는 데이터가 아니다.

검토 수정이 반영된 최종 보고서:

- [package/version 보고서](../../../data/native-package-report-final/report.md)
- [observed package_snapshot 보고서](../../../data/native-snapshot-report-final/report.md)

이전 `data/native-*-report/` 보고서는 검토 수정 전 실행 기록으로 보존했다.
최종 결과는 위 `*-report-final/`을 기준으로 한다.

## 발견한 이슈와 해결

- 처음 오류 주입 테스트의 SQL 별칭 문법 때문에 샘플 생성 4건이 실패했다. 별칭에 `AS`를 명시한 뒤
  실제 schema·행 수 불일치 검출까지 실행해 통과했다.
- 독립 검토에서 `datetime.fromisoformat`이 소수점 7자리 이상을 잘라내는 문제를 발견했다.
  기존 snapshot 정책 parser로 요청과 원문 manifest 모두 검사하도록 수정했다. 초 단위 시간대 offset도 거부한다.
  native selector가 이미 시각을 잘라 반환한 경우에도 원문 검사에서 잡는다.
- 재사용하는 `snapshot/policy.py`를 이번 validator SHA에 포함했다.
- 같은 UTC 순간을 `+09:00`으로 표현한 정상 입력은 허용하고, microsecond가 다른 입력은 거부함을 확인했다.

## 기존 작업 보호

원래 worktree의 비교 대상 코드·문서 **623개 파일이 동일**하고 브랜치·HEAD·인덱스도 동일했다.
작업 기준선은 [native-parent-before.json](evidence/native-parent-before.json)이다.
8번의 변경 중인 historical 적재 코드, 실제 원천 데이터, DB/Docker, 원격 저장소를 사용하거나 변경하지 않았다.
이번 작업은 로컬 미커밋 상태로 남겼으며 커밋·push·MR·Jira 갱신은 수행하지 않았다.

## 후속 범위 — 미실행

historical package_snapshot·snapshot calendar·historical dependents 연결,
승인된 실제 원천의 생성 계약·upstream lineage·전체 파일 SHA·전체 모집단 대조,
행 값·PK/FK·품질 의미, 실제 PostgreSQL 정합성·장애 복구·성능 검증은 미실행이다.
요청 pin 자체의 외부 승인도 이 도구가 증명하지 않는다.

두 예제 모두 `synthetic_demo=true`, `ready_for_load=false`, `ready_for_publication=false`,
`task_09_complete=false`다. 이번 완료는 병렬 가능한 연결 준비 범위에 한정한다.
