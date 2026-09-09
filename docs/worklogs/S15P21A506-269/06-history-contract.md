# 269 snapshot-reference 실행 이력 계약

## 범위

이 문서는 frozen Projects calendar 전체를 `snapshot-reference` execution으로 등록하고,
기존 날짜 적재 이력과 안전하게 연결하는 V3 설계 결정을 기록한다. 구현 대상은 V3 Flyway
스키마, `pipeline.snapshot.load`/`input.py`/`postgres.py`의 실행 경계와 검증 규칙이다.
V1/V2 migration과 package-version 서비스 테이블은 이 범위에서 수정하지 않는다.

한 execution은 단일 날짜가 아니라 candidate가 고정한 calendar 전체다. 부모 계보는 단일
snapshot을 재해석하지 않으며 `curated_run_id=NULL`인 snapshot-reference 입력으로 보존한다.
입력 metadata에는 frozen candidate와 Projects inventory SHA를 포함하고, 부모 `manifest_sha256`에 candidate 파일의 SHA를 기록한다.
`--prior-receipt`가 지정되면 원래 date-only receipt 본문과 그 SHA도 함께 보존하고, receipt의
database가 현재 연결 대상과 일치하는지 확인한다.

## 상태와 원자성

- `PREPARING` 등록은 별도 commit이다.
- 날짜 행, 실행별 날짜/원천 시각/직전 날짜/구간 길이, execution과 attempt의 성공 기록은 하나의
  원자적 commit이다.
- 실패 attempt는 `FAILED`로 남긴다. 처음 실패한 execution도 `FAILED`가 되지만,
  이전에 성공한 실행은 `PUBLISHED`를 유지한다. 재검증 중 누락된 행을 자동 복구하지 않는다.
- 동일 ID는 동일 input의 기존 `PUBLISHED`일 때만 DB 내용 재검증으로 `REVERIFIED`를 만든다.
- 신규 ID가 이미 존재하는 날짜만 가리키면 날짜 삽입은 0건이고 실행별 날짜 연결 행을 새로 만든다.
  DB 상태는 `PUBLISHED`, 실행 보고서의 action은 `LINKED_EXISTING`이다.
- `active_attempt_id`는 최신 시도이며 마지막 성공 attempt를 의미하지 않는다. 부모의
  최초 `actual_counts`와 `contract_sha256`, 최초 성공 attempt의 완료 시각은 보존한다.
- 현재 포인터는 갱신하지 않는다. 날짜 준비 상태와 서비스 준비 상태는 별도이며 후속
  readiness 계약은 아직 구현하지 않는다.

## 불변 입력 검증

candidate/build 원본 상태는 불변으로 취급한다. 매 실행 candidate, inventory, source footer의
전체 파일 목록과 stat/hash/row-group 통계를 다시 검사하고 inventory가 같아야 한다. calendar는
검증된 inventory에서 다시 구성하며 `snapshot-dates.sql`은 SQL 파일을 실행해 확인하지 않고
그 calendar로 생성한 결과와 바이트/SHA를 비교한다. 검증된 calendar만 SQL 생성의 입력이다.

V3는 Flyway가 스키마를 관리한다. CLI는 자동 migration하지 않으며 이미 적용된 V1/V2 파일을
수정하지 않는다. DB 트랜잭션은 전용 advisory lock과 reference table
`SHARE ROW EXCLUSIVE` lock을 사용하고 `lock_timeout=2s`, `statement_timeout=30s`를 적용한다.

## CLI 계약

검증 전용 실행은 DB에 연결하지 않는다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.snapshot.load `
  --candidate data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json `
  --execution-id verify-calendar-20260908 `
  --verify-only
```

DB 적재에는 `--docker-container` 또는 `--psql`와 `--database`를 명시한다. 이전 날짜 적재를
연결할 때만 `--prior-receipt`를 사용한다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.snapshot.load `
  --candidate data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json `
  --execution-id calendar-20260908 `
  --docker-container <postgres-container> `
  --database <validation-database> `
  --prior-receipt data/snapshot/date-load/receipt.json
```

## package-version V3 호환성

package-version의 contract 해시는 loader/migration 등 실행 계약의 역사값이다. 동일
execution ID, 동일 dataset·snapshot·snapshot timestamp·curated run/prefix·manifest SHA·
input metadata·expected counts인 기존 PUBLISHED 입력만 새 contract로 `INPUT_ONLY`
재검증할 수 있다. 이때 새 attempt의 `validation_contract_sha256`에 현재 hash를 기록하고
부모 `contract_sha256`는 바꾸지 않는다. 입력이 달라지거나 FAILED/PREPARING 이력이거나,
신규 ID로 이미 게시된 manifest의 다른 contract를 우회하려는 경우는 거부한다.

## 검증 결과

검증은 candidate 재검증, 상태 전이, 중복 날짜 LINKED_EXISTING, 동일 ID REVERIFIED,
실패 원자성, lock/timeout, 부모 역사 보존, 현재 포인터 비갱신, package-version contract
호환 회귀를 각각 확인했다. [테스트 요약](evidence/history-tests.json)과
[실제 DB 반영 기록](evidence/history-db-load.json)에 결과를 보존한다.

| 항목 | 최종 실행 결과 |
| --- | --- |
| 검증 시각/환경 | 2026-09-08 22:02:23 +09:00, 로컬 `pickage_267_full_defaulted` |
| frozen calendar / 날짜 수 | 기준일 229개 유지, 실행별 날짜 연결 229행, timestamp/P/구간 길이 전체 일치 |
| 최초 이력 연결·재실행 | `snapshot-history-269-projects-v1`: `LINKED_EXISTING` → `REVERIFIED`, 날짜 추가 각각 0건 |
| 실패/원자성/lock 검증 | 단위 29개 + 실제 PostgreSQL 34개 통과, failures/errors/skips 0 |
| package-version V3 contract 호환 | 격리 DB에서 검증. 실제 전체 DB의 기존 실행·attempt·current 및 서비스 컬럼 계약은 전후 동일 |

로컬 전체 데이터 DB에는 Flyway 이력 테이블이 없으므로 V3 SQL을 `psql -X`,
`ON_ERROR_STOP=1`, `--single-transaction`으로 직접 적용했다. 애플리케이션 Flyway 기동은
검증하지 않았다. 실제 전체 package/version 입력 재검증을 다시 실행하지는 않았으며,
기존 실행의 계약 해시를 수정하지 않았다. 서비스 준비 상태 연결은 다음 범위다.

## DB에서 실행과 날짜 확인

```sql
SELECT e.execution_id, e.status,
       e.manifest_sha256 AS candidate_sha256,
       e.contract_sha256 AS original_load_contract_sha256,
       e.input_metadata->'candidate'->>'policy_version' AS policy_version,
       e.input_metadata->'candidate'->>'policy_sha256' AS policy_sha256,
       r.snapshot_at, r.snapshot_timestamp, r.previous_snapshot_at, r.interval_days
FROM public.etl_load_execution e
JOIN public.etl_snapshot_reference r USING (execution_id)
WHERE e.execution_id = 'snapshot-history-269-projects-v1'
ORDER BY r.snapshot_at;
```

최신 시도의 검증 계약과 성공 여부는 `etl_load_attempt.validation_contract_sha256`과
`status`를 확인한다. 부모의 PUBLISHED와 최신 attempt의 FAILED가 함께 있을 수 있다.
