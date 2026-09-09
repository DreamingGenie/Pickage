# 07. MR 리뷰 대응 — package/version 재실행 시각 비교

## 변경 범위

- 대상: `pipeline/postgresql/postgres.py`의 동일 실행 입력 판정과 해당 회귀 테스트.
- PostgreSQL `row_to_json`의 `.5`와 Python `datetime.isoformat()`의 `.500000`을 같은 시간 값으로 판정한다.
- `snapshot_timestamp`는 실행 identity에 유지한다. 실제 시각, 다른 입력, 허용되지 않은 계약 변경의 거부 조건을 보존한다.
- 리뷰 1번의 TIMESTAMP/TIMESTAMPTZ 설계, V2/V3 마이그레이션, 입력의 naive 시간 계약은 변경하지 않는다.
- 기존 적재 DB와 외부 서버의 데이터는 변경하지 않는다. PostgreSQL 검증은 테스트별로 생성한 격리 DB에서 수행한다.

## 작업 계획

1. 실제 PostgreSQL을 사용하는 회귀 테스트를 추가하고 수정 전 실패를 확인한다.
2. `snapshot_timestamp`만 양쪽 값을 `datetime.fromisoformat()`으로 파싱해 비교한다.
3. 게시 완료 재검증·실패 후 재시도·실제 마이크로초 차이 거부 및 기존 계약 검사를 실행한다.
4. 관련 package/version·snapshot 테스트, 정적 검사, 독립 코드 검토 후 실측 결과를 기록한다.

## 이슈와 해결 방법

| 항목 | 근거 / 조치 |
| --- | --- |
| 문자열 표현 차이 | DB JSON은 소수부 끝의 0을 생략하고 입력은 마이크로초 6자리를 보존해, 같은 값이 다른 입력으로 거부된다. 해당 필드만 시간 값으로 비교한다. |
| 기존 테스트 누락 | 기존 통합 fixture의 `.517131`은 양쪽 표현이 같아 버그를 드러내지 못했다. 끝의 0이 있는 입력과 실제 시각 차이를 추가한다. |
| 계약 해시 변경 | loader 코드가 계약 해시에 포함된다. 기존 PUBLISHED 실행은 동일 입력에 한해 새 해시 재검증을 허용하고, FAILED 실행의 계약 변경 거부는 유지한다. 이번 수정은 그 정책을 바꾸지 않는다. |

## 실제 진행 및 검증 결과

- 작업 시작: 현재 브랜치 `feat/S15P21A506-269-snapshot-contract-load`, 기준 HEAD `e3a8a62` 확인. 기존 추적 파일 변경 없음.
- 수정: 기존 문자열 identity 필드를 먼저 확인하고, 같은 경우 `snapshot_timestamp` 양쪽을 파싱해 비교한다. 다른 dataset의 실행처럼 시각이 NULL인 행은 기존 identity 불일치로 먼저 거부한다.
- 테스트 추가: 게시 완료 입력의 `.500000` 재검증과 새 계약 해시 기록, 실패 입력의 `.123450` 재시도, `.000010`에서 `.000011`로 실제 시각이 바뀌면 실행 상태·attempt 수를 보존하며 거부하는 3건.

| 검증 | 실제 결과 | 증거 |
| --- | --- | --- |
| 수정 전 회귀 테스트 | 2026-09-09 10:49:06 +09:00, 3건 중 정상 재시도 2건에서 기존 `different input or contract` 오류 재현, 시각 변경 거부 1건 통과. skip 0, 7.094초 | [수정 전 결과](evidence/timestamp-retry-before.json) |
| 수정 후 동일 테스트 | 2026-09-09 10:49:42 +09:00, 3건 통과, 실패·오류·skip 0, 7.640초 | [수정 후 결과](evidence/timestamp-retry-after.json) |
| 관련 전체 테스트 | PostgreSQL 16.14에서 package/version·snapshot의 11개 테스트 모듈 실행. 대상 76건 중 75건 통과, 실패·오류 0, 원천 후보 경로 미지정으로 1건 skip, 110.047초 | [전체 실행 결과](evidence/timestamp-retry-suites.json) |
| 누락된 원천 후보 테스트 | 로컬 `projects-v1/snapshot-candidate.json` 경로를 지정해 skip된 1건만 별도 실행, 통과. 기존 통과 75건과 합쳐 대상 76건 모두 검증 완료. 후보 파일/정책 해시·날짜 목록·재실행 검증 포함 | [추가 실행 결과](evidence/timestamp-retry-candidate.json) |
| 정적 검사 | `compileall -q pipeline/postgresql pipeline/snapshot` 및 `git diff --check` 통과. 대상 모듈에는 별도 lint/typecheck 설정이 없어 해당 도구 통과로 기록하지 않는다. | 2026-09-09 10:50:54 +09:00 실행 출력 |
| 독립 코드 검토 | 2번 수정과 테스트에 대해 APPROVE. 추가 조치가 필요한 지적이나 중대한 테스트 누락 없음. MR 전체 승인을 의미하지 않는다. | 별도 code-reviewer 검토 |

- 테스트 종료 후 `pickage_267_test_*`, `pickage_269_test_*`, `pickage_269_history_test_*` 데이터베이스 잔여 수 0을 조회해 정리를 확인했다.
- 검증 결과 JSON에는 실행 로그·실측 시간과 수정 파일 SHA-256을 보존했다. 원천 후보 추가 검증은 후보 경로와 SHA-256을 기록했다.
- 결과: 같은 시각의 문자열 표현 차이는 허용하고, 실제 시각 차이·다른 입력·허용되지 않은 계약 변경은 계속 거부한다. 1번 설계와 스키마는 수정하지 않았다.

## 미실행 범위

- 외부 서버 반영, 기존 대용량 적재 DB 재실행, Spring/Flyway 기동 검증, 커밋·푸시는 이 수정 작업에서 실행하지 않는다.
