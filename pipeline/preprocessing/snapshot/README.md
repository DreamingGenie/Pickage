# Projects snapshot 기준과 시간 정책

사용자가 지정한 `Projects`에 실제로 존재하는 스냅샷에서 날짜 목록을 만든다.
`package`·`version` 적재와 독립적으로 실행하며 정책 버전은 `snapshot-time-v1`이다.
작업 기록은 [S15P21A506-269](../../../docs/worklogs/S15P21A506-269/README.md)에 있다.

## 입력과 실행

기존 `.venv-bq`의 DuckDB와 Python 표준 라이브러리를 사용한다. 새 패키지 설치는 없다.
저장 위치는 실행마다 새 디렉터리를 사용한다. 아래 명령은 원본을 읽고 로컬 파일만 생성한다.

```powershell
.\.venv-bq\Scripts\python.exe -m pipeline.preprocessing.snapshot.build --projects-root data/raw/projects --output-dir data/snapshot/S15P21A506-269/projects-v1
```

입력은 `snapshot=YYYY-MM-DD/_MANIFEST.json`과 같은 디렉터리의 `part-*.parquet`다.
manifest의 `table=projects`, `snapshot`, `status=done`, `verify=ok`, 기대 행 수를 확인한다.
모든 파일의 scalar `SnapshotAt` 타입·row group min/max·NULL 수·행 수를 검사하여 하나의
정확한 원천 시각인지 확인한다. partition 날짜와 UTC 날짜가 다르거나 한 날짜에 서로 다른
시각이 있으면 실패한다. 폴더 이름만 읽어 자정 timestamp를 만들지 않는다.

검사는 Parquet 메타데이터에 한정한다. 파일 길이·mtime·footer SHA 및 manifest SHA를 기록하며
**footer SHA는 전체 파일 SHA가 아니다**. `started_at`·`finished_at`은 수집 실행 시각이다.

| 산출물 | 내용 |
| --- | --- |
| `projects-inventory.json` | 날짜별 원천 시각, 파일 목록, manifest·footer 해시, 행 수 검사 |
| `snapshot-candidate.json` | 고정 목록, 직전 P, 시간 정책 버전·해시, 입력 계보·범위 |
| `snapshot-dates.sql` | 명시적 DATE INSERT와 트랜잭션, `ON CONFLICT DO NOTHING` |

출력 상태 `LOCAL_VALIDATED`는 후보 생성 완료다. SQL은 `snapshot` 기준 날짜만 추가하며,
DB 실행 이력이나 지표의 PUBLISHED·서비스 준비 완료를 자동으로 선언하지 않는다.
SQL 실행 여부·대상 DB·실행 이력 연결은 별도 적재 절차의 책임이다. 검증용 SQL 실행은 아래 테스트로 수행한다.

## `snapshot-reference` 실행 이력 적재

`pipeline.postgresql.snapshot.load`는 candidate가 고정한 calendar 전체를 하나의 실행으로 등록한다.
부모 실행의 `snapshot_at`, `snapshot_timestamp`, `curated_run_id`는 NULL이며,
각 날짜·원천 시각·직전 날짜는 `etl_snapshot_reference`에 기록한다. 부모 `manifest_sha256`은
candidate 파일의 SHA-256이다. 입력 metadata에는 candidate 원문과 Projects inventory SHA-256을 포함하고, 선택한
`--prior-receipt`가 있으면 원래 date-only 적재 receipt 원문과 SHA-256도 함께 보존한다.

candidate와 `projects-inventory.json`은 매 실행 다시 읽는다. source footer의 전체 파일 목록,
크기·mtime·footer 통계·해시·행 수와 inventory를 재검증하고, calendar와 생성 가능한 SQL의
바이트·SHA가 동일해야 한다. SQL 파일을 실행해 날짜를 추론하지 않으며, 검증된 calendar로만
SQL을 생성한다. candidate와 source 원본은 변경하지 않는다.

실행 등록과 날짜 적재의 경계는 다음과 같다.

- `PREPARING` 등록은 별도 commit으로 남긴다.
- 날짜·실행별 날짜 연결 행·execution 및 attempt의 성공 기록을 하나의 트랜잭션으로 확정한다.
- 실패한 attempt는 `FAILED`가 된다. 처음 적재하다 실패한 execution도 `FAILED`가 되지만,
  이미 `PUBLISHED`인 실행의 재검증 실패는 최초 성공 상태를 보존한다. 누락된 행을 자동 복구하지 않는다.
- 같은 execution ID는 동일 input으로 이미 `PUBLISHED`인 경우에만 DB 내용 재검증 후
  attempt가 `REVERIFIED`가 된다. 신규 ID가 이미 존재하는 날짜만 가리키면 날짜 추가는 0건이고,
  새 실행의 날짜 연결 행을 생성한다. DB 상태는 `PUBLISHED`, 보고서 action은 `LINKED_EXISTING`이다.
- `active_attempt_id`는 최신 시도다. 최초 성공 attempt의 완료 시각과 부모의 최초
  `actual_counts`·`contract_sha256`은 보존하며, 현재 검증 계약은 새 attempt에 기록한다.
- 현재 포인터는 갱신하지 않는다. 날짜가 준비되었다는 사실은 서비스 준비 완료를 뜻하지 않는다.

V3 스키마는 Flyway가 관리한다. 이 CLI는 자동 migration을 수행하지 않으며, 기존 V1/V2
migration 파일을 수정하지 않는다.

검증만 수행하려면 PostgreSQL 옵션 없이 다음처럼 실행한다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.postgresql.snapshot.load `
  --candidate data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json `
  --execution-id verify-calendar-20260908 `
  --verify-only
```

DB에 적재할 때는 대상 database와 Docker container 또는 host `psql`을 명시한다. 이전
date-only 적재 receipt를 연결할 때만 `--prior-receipt`를 추가한다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.postgresql.snapshot.load `
  --candidate data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json `
  --execution-id calendar-20260908 `
  --docker-container <postgres-container> `
  --database <validation-database> `
  --prior-receipt data/snapshot/date-load/receipt.json
```

전용 advisory lock과 reference table `SHARE ROW EXCLUSIVE` lock을 사용하며,
트랜잭션의 `lock_timeout`은 2초, `statement_timeout`은 30초다. 후속 서비스 준비 상태와
공통 readiness 판정은 아직 구현 범위가 아니다.

## 확정한 269 v1 정책

| 항목 | 적용 규칙 / 의미 |
| --- | --- |
| 기준 목록 | 선택 Projects 디렉터리에서 검증한 실제 SnapshotAt 목록. deps.dev 전체 역사라는 주장은 하지 않음 |
| 원천 시각 | `snapshot_timestamp`: UTC microseconds 보존. BigQuery에서 내보낸 timezone 없는 TIMESTAMP는 입력 어댑터에서만 UTC로 해석 |
| DB 기준 날짜 | 기존 `snapshot_at DATE` 이름 유지, 원천 시각의 UTC 날짜. 날짜당 다른 시각이 둘이면 현재 DATE 키로 표현할 수 없어 거부 |
| 직전 P | 같은 고정 목록에서 S 직전 항목. DB 마지막 성공일·수집일·임의 7일을 사용하지 않음 |
| 다운로드 | UTC 날짜 `[P,S)`. 2026-08-24→31은 24~30일. 시간 단위 두 SnapshotAt 사이의 정확한 합계와 구분 |
| 불규칙 간격 | 실제 DATE 차이. 14일 간격이면 14일 |
| 최초 | 선택 목록의 이전 항목 없음: NULL / `NO_PREVIOUS_SNAPSHOT` |
| 원본 범위 밖 | NULL / `OUTSIDE_AVAILABLE_RANGE`. 부분 합계로 대체하지 않음 |
| 일별 누락·NULL | NULL / `MISSING_DAILY_VALUES`. 실제 관측 0은 누락이 아님 |
| Projects 관측 선택 | 동일한 정확한 시각만 허용. 미래 및 과거 값 자동 대체 없음. 불일치는 NULL / `NO_EXACT_OBSERVATION` |
| 버전 대상 | 동일 snapshot에서 관측한 릴리스. 미래 published_at은 제외, published_at NULL은 포함하되 `PUBLISHED_AT_UNKNOWN` 기록 |
| 과거 대상 집합 | 현재 snapshot의 목록만으로 과거 전체 집합을 확정하지 않음. 관측 snapshot 불일치는 eligible 미확인 / `OBSERVED_SNAPSHOT_MISMATCH` |

이 표의 `[P,S)`·정확한 Projects 시각 선택·NULL 사유는 **이 작업의 구현 결정**이다.
공급자 공식 계약과 구분한다. 이전 Projects 값 재사용이 필요하면 최대 간격·원천 관측 시각을
포함하는 새 정책 버전으로 변경한다. 과거 실행의 P나 정책을 조용히 다시 해석하지 않는다.

`assess_download_coverage`에 전달하는 available_start/end는 **해당 패키지**의 실제 보유 기간이다.
호출자는 `[P,S)`의 누락된 행과 NULL/imputed_gap 날짜를 모두 `missing_dates`에 전달해야 한다.
이 함수는 다운로드 값을 읽거나 더하지 않는다. 후속 다운로드 구간 집계에서 패키지별
보유 기간과 누락 날짜를 검사해 입력 coverage를 완성한다.
대상 목록 밖 패키지는 후속 LEFT JOIN에서 downloads NULL을 유지한다.

## 267 및 후속 작업 연결

- 267의 단일 스냅샷 실행과 같은 UTC 기준일 의미를 사용하되, calendar 실행의 날짜는 연결 테이블에 저장한다.
- `etl_snapshot_reference.snapshot_timestamp TIMESTAMPTZ`에 원천 시각과 microseconds를 보존한다.
- 입력 목록 해시·정책 버전/해시·snapshot별 이전 P·지표별 실제 원천 시각·NULL 사유를 후속 manifest에 전달한다.
- DB `snapshot` 행 존재와 지표 준비 완료는 별도다. 서비스 완료 판정은 필수 dataset의 동일 snapshot·호환 정책·승인 입력과 PUBLISHED를 확인해야 한다.
- 공통 실행 이력 연결과 package/version의 계약 변경 재검증 호환 처리를 구현했다. 지표별 준비 상태와 서비스 공개 판정은 후속이다.
- 후속 다운로드 구간 집계·저장소 지표 생성·requirements 대상 버전 해석·버전별 dependents 집계는 같은 candidate의 목록과 `snapshot-time-v1` 정책 버전·해시를 참조하도록 통합해야 한다.
- V1/V2 및 서비스 테이블 DDL은 유지한다. V3는 공통 실행 이력과 날짜 연결 구조를 추가하며, 실제 반영 기록은 [269 결과](../../../docs/worklogs/S15P21A506-269/05-results.md)에 있다.

## 검증

```powershell
.\.venv-bq\Scripts\python.exe -m unittest pipeline.preprocessing.tests.snapshot.test_policy pipeline.preprocessing.tests.snapshot.test_projects pipeline.preprocessing.tests.snapshot.test_build pipeline.preprocessing.tests.snapshot.test_input pipeline.postgresql.snapshot.tests.test_load -v
```

실제 PostgreSQL 테스트는 기존 **검증용** 컨테이너 안에 테스트마다 `pickage_269_test_<uuid>` 또는
`pickage_269_history_test_<uuid>` DB를 새로 만들고 삭제한다. 날짜 전용 테스트는 V1·V2,
실행 이력 테스트는 V3까지 적용하며 기존 DB·seed·267 적재 프로세스는 사용하지 않는다.
원천 후보 파일을 지정하면 실제 날짜 전체의 최초 적재·재실행 후 정확한 날짜 집합을 대조한다.

```powershell
$env:PICKAGE_SNAPSHOT_TEST_CONTAINER = 'pickage-267-validation'
$env:PICKAGE_SNAPSHOT_CANDIDATE = (Resolve-Path data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json).Path
.\.venv-bq\Scripts\python.exe -m unittest pipeline.preprocessing.tests.snapshot.test_integration pipeline.preprocessing.tests.snapshot.test_history -v
```

컨테이너 또는 실제 candidate를 지정하지 않은 테스트는 skip이며 통과로 합산하지 않는다.
267의 전체 적재 테스트 결과를 이 작업의 테스트 수에 포함하지 않는다.

## 공식 근거와 확인 범위

- [deps.dev BigQuery schema](https://docs.deps.dev/bigquery/v1/): Projects.SnapshotAt은 해당 행의 export 시각이다. 공급자 고정 주기를 가정하지 않는다.
- [BigQuery DATE](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/date_functions#date): TIMESTAMP→DATE 기본 타임존은 UTC다. 이 구현은 UTC를 명시한다.
- [BigQuery TIMESTAMP](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/data-types#timestamp_type): 절대 시각과 calendar DATE는 다른 의미다.
- [npm download counts](https://github.com/npm/registry/blob/main/docs/download-counts.md): 일별 집계는 UTC 기준 운영이며 API start/end는 포함 경계다. `[P,S)` 요청은 `P:S-1일`로 변환한다. 이번 작업은 API를 호출하지 않는다.
- [DuckDB Parquet metadata](https://duckdb.org/docs/stable/data/parquet/metadata): row group 통계 조회 필드.
- [Apache Parquet Statistics](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift): min/max 경계와 optional null_count/exactness 필드. min=max 상·하한, 명시적 NULL 0을 검증하며 없는 null_count를 0으로 해석하지 않는다.

공식 문서는 2026-09-08 조회했다. 실행별 실제 입력·검증 결과는 269 작업 기록에 남긴다.
