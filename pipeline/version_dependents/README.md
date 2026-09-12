# 버전별 직접 의존자 수 집계

`aggregate`는 7번 작업이 만든 선언된 버전 간 관계를 이용해 승인된 대상
패키지 버전별 `dependents_count`를 계산합니다. 계산 범위는 직접 간선 하나이며,
연쇄 의존자와 자기 자신 제거는 수행하지 않습니다.

## 입력 계약

호출자가 소유한 DuckDB 연결에 다음 세 테이블을 **정확한 이름과 열 타입**으로
정규화해 준비해야 합니다. ID는 `INTEGER` 또는 `BIGINT`, 버전은 `VARCHAR`,
`snapshot_at`은 `DATE`, `published_at`과 `snapshot_timestamp`는 `TIMESTAMP WITH TIME ZONE`이어야
합니다. 암묵적인 형 변환은 하지 않습니다.

| 테이블 | 열 |
| --- | --- |
| `requirements_edges` | `source_package_id`, `source_version`, `target_package_id`, `target_version`, `snapshot_at`, `snapshot_timestamp` |
| `approved_sources` | `package_id`, `version`, `published_at`, `snapshot_at`, `snapshot_timestamp` |
| `approved_targets` | `package_id`, `version`, `published_at`, `snapshot_at`, `snapshot_timestamp` |

모든 행의 snapshot 값은 호출 인자와 정확히 같아야 합니다. `snapshot_timestamp`는 UTC로
정규화했을 때 `expected_snapshot_at`과 같은 날짜여야 합니다. 모집단은 비어 있지
않고 `(package_id, version)`이 유일해야 하며, ID는 양수이고 INT 범위 안이어야
합니다. 버전은 1~100자이고 공백만으로 구성되거나 NUL을 포함할 수 없습니다.
`published_at`은 NULL일 수 없으며 정확한 `snapshot_timestamp` 이후일 수도 없습니다.
간선은 양쪽 승인 모집단에 모두 존재해야 합니다.
안정 버전 선별은 이 커널의 역할이 아니며, upstream 승인 모집단에서 완료해야 합니다.

호출은 `expected_snapshot_at`(date), `snapshot_timestamp`(timezone-aware datetime),
`resolution_status="COMPLETE"`, `ready_for_dependents=True`를 요구합니다. 두 readiness
값은 upstream guard일 뿐, 운영 manifest·전체 대상 모집단·출력 파일 검증을 증명하지
않습니다. `PARTIAL` 또는 미완료 입력은 0건 결과도 만들지 않고 거부합니다.

## 결과

검증이 모두 끝난 뒤에만 새 `version_dependents` 테이블을 한 번 생성합니다. 기존 결과
또는 내부 scratch 테이블이 이미 있으면 덮어쓰지 않고 거부합니다. 결과 열은
`package_id`, `version`, `snapshot_at`, `snapshot_timestamp`, `dependents_count`이며,
모든 승인 대상 버전을 유지합니다. 간선은 네 개의 복합 키로 중복 제거한 뒤 대상별
서로 다른 source `(package_id, version)` 수를 세므로, 같은 source의 중복 선언은 한 번만
셉니다. 간선이 없어도 유효한 대상 모집단에는 `0`을 기록합니다.

로컬 Parquet 저장·재검증은 아래 `artifact` 계층에서 수행합니다. 실제 운영 입력
어댑터, 검증된 전체 대상 모집단 연결, PostgreSQL 적재기는 후속 작업입니다.
이 모듈은 `_SUCCESS`를 만들거나 생산 결과를 publish-ready로 표시하지 않습니다.
집계 실패 시 새 결과 테이블을 만들거나 기존 결과를
덮어쓰지 않습니다. 각 집계 시도는 결과·임시 테이블이 없는 별도 연결에서 실행합니다.

## 검증

기존 Python 환경에서 다음 전용 테스트를 실행합니다. 실제 7번 파일·DB에 접근하지 않고
합성 데이터만 사용합니다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m unittest pipeline.version_dependents.test_aggregate pipeline.version_dependents.test_artifact -v
```

실제 실행 결과와 입력 조사 범위는 [8번 작업 기록](../../docs/worklogs/S15P21A506-193/05-results.md)에 있습니다.

## 스냅샷별 Parquet 저장

`artifact.save_artifact`는 위 세 입력 테이블을 검사·집계한 뒤 다음 새 경로에 저장합니다.
호출할 때마다 입력·날짜·정확한 시각을 명시합니다. 같은 날짜 안에서도 원천 시각이
다르면 별도 run이며, DB에 같은 날짜의 두 시각을 동시에 게시할 수 있다는 뜻은 아닙니다.

```text
<output_root>/snapshot=2026-08-31/run_id=<run_id>/
  counts.parquet
  lineage.parquet
  quality.parquet
  run_manifest.json
```

| 파일 | 행 단위와 내용 |
| --- | --- |
| `counts.parquet` | target 패키지·버전·snapshot별 count. 정확한 `snapshot_timestamp`도 보존 |
| `lineage.parquet` | 입력 종류별 1행, 총 3행. 관계·source·target 모집단의 run ID, manifest SHA, policy SHA, 검증 상태 |
| `quality.parquet` | 출력 run별 1행. 입력 source/edge 수, 고유/중복 edge 수, target 수, 0인 target 수, 최대 count, count 합계, 입력 승인 상태 |
| `run_manifest.json` | 같은 이력·품질·시간 정보, 코드 해시, 파일별 행 수·스키마와 스키마 해시·크기·SHA |

`save_artifact(con, ...)`는 `aggregate`와 같은 시간·준비 상태 인자에 더해
`output_root`, `run_id`, `input_lineage`를 받습니다. `input_lineage`는 아래 형식의
딕셔너리 3개이며 `role`은 `requirements_edges`, `approved_sources`, `approved_targets`입니다.

```python
{"role": "requirements_edges", "run_id": "requirements-example-v1",
 "manifest_sha256": "<64자리 소문자 SHA256>", "policy_sha256": "<64자리 소문자 SHA256>"}
```

반환값은 `run_dir`, `manifest_sha256`, `manifest`입니다. 이후 검증에서 사용할
`manifest_sha256`는 이 최초 반환값을 보관하여 전달합니다. 검증 직전에 변경된 manifest에서
해시를 새로 계산하면 원래 파일과 같은지 확인하는 기준을 잃습니다.

기존 run 폴더는 덮어쓰지 않습니다. 성공한 run은 재검증하고, 실패한 새 run 폴더는
증거로 보존한 채 새 run ID로 재시도합니다. 동일한 경로에 동시에 저장하면 한 시도만
폴더를 확보합니다. 파일 저장 실패가 이미 끝난 다른 run에 영향을 주지 않습니다.

### 파일 검증과 입력 승인의 구분

`verify_artifact(run_dir, manifest_sha256=...)`는 저장 파일만 읽습니다. SHA·크기·스키마·행 수,
키/값/날짜·정확한 시각, count와 품질·이력의 일치를 검사합니다. 원본 관계를 다시 집계하거나
전체 target의 stable-semver 정책·coverage를 검증하는 기능은 아닙니다.

현재 저장 계층은 호출자가 제공한 입력 이력을 보존하며 원본 manifest를 직접 검증하지
않습니다. 따라서 `input_verification=NOT_PERFORMED`, `verification_scope=LOCAL_ARTIFACT_ONLY`,
`ready_for_load=false`를 항상 기록합니다. `artifact_status=COMPLETE`는 로컬 저장 완료만
뜻합니다. 정상 게시용 `_SUCCESS`를 만들지 않으며, 이 결과만으로 DB 적재를 승인하면 안 됩니다.
`PARTIAL` 또는 준비되지 않은 입력은 저장 전에 거부합니다.

품질 수치는 **검사한 정규화 입력과 집계 결과의 범위**입니다. upstream의 미해석·peer/optional
제외 건수 등을 새로 조사한 것이 아니며, 이런 정보는 기록된 원본 이력에서 후속 어댑터가
검증·연결해야 합니다. 누락된 원본 품질 수치를 임의의 0으로 저장하지 않습니다.

### 직접 확인하기

다음 예제는 실제 패키지 데이터를 사용하지 않고 `2026-08-31`, `2026-09-07`의 합성 입력으로
서로 다른 count를 저장합니다. `--output-root`에는 아직 없는 경로를 지정합니다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents demo --output-root 'data/version-dependents/my-demo'
```

반환된 run 경로와 manifest SHA로 DB 없이 재검증합니다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents verify --run-dir '<반환된 run_dir>' --manifest-sha256 '<반환된 manifest_sha256>' --snapshot-at '2026-08-31'
```

DuckDB 등에서 해당 `counts.parquet`를 열면 실제 저장 행을 볼 수 있습니다.

```sql
SELECT package_id, version, snapshot_at, snapshot_timestamp, dependents_count
FROM read_parquet('<run_dir>/counts.parquet', hive_partitioning=false)
ORDER BY package_id, version;
```

서로 다른 날짜는 해당 날짜의 관계와 source·target 모집단으로 각각 계산합니다. 최신 관계의
날짜만 바꿔 과거 결과로 저장하지 않습니다. 현재 로컬에서 확인된 실제 `requirements`와
`versions_full` 입력 폴더는 `2026-08-31` 한 날짜이며, 예제의 `2026-09-07`은 합성 날짜입니다.

## PARTIAL 입력의 성공 관계 진단 집계

사용자가 승인한 진단 범위는 별도 `pipeline.version_dependents.diagnostic` 모듈에서 실행한다.
고정한 recovery candidate와 그 안의 모든 edge 파일을 검증하고, 성공한 관계의 서로 다른
source 패키지·버전 쌍을 target 버전별로 센다. 계산 엔진은 로컬 DuckDB이며 기본 설정은
8스레드·8GB다. 스냅샷 날짜뿐 아니라 원본의 마이크로초 시각과 계보도 대조한다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.diagnostic build --source-run '<원본 run>' --candidate-manifest '<고정한 recovery candidate>' --candidate-sha256 '<고정 SHA256>' --snapshot-at '2026-08-31' --output-root 'data/version-dependents/diagnostic-runs' --run-id '<새 실행 ID>' --threads 8 --memory-limit '8GB'
```

`snapshot=<날짜>/run_id=<실행 ID>/outputs/`에 다음 파일을 저장한다.

| 파일 | 내용 |
| --- | --- |
| `resolved_counts.parquet` | 성공 관계에 등장한 target 버전의 `resolved_dependents_count`. 전체 target에 0을 채우지 않음 |
| `lineage.parquet` | 스냅샷·원본 실행·입력/정책/candidate 해시·복구 이력의 검증 공백 |
| `quality.parquet` | 실제 읽은 관계 수·중복 제거 결과·상위 보고서의 미해석/제외 정보 |
| `diagnostic_manifest.json` | 파일별 해시/스키마/행 수, 입력 검증 범위, 실행 설정과 시간. 검증 후 마지막에 생성 |

모든 결과는 `PARTIAL`, `ready_for_load=false`다. 전체 source/target 모집단 및 미해석 원본은
이번 진단 검증의 범위 밖이며, `_SUCCESS`는 생성하지 않는다. 기존 정상 집계의 입력 승인
조건도 유지한다. 원본은 읽기 전용으로 사용하고 집계 후 SHA를 다시 비교한다.

최초 실행에서 반환한 manifest SHA로 별도 프로세스 검증이 가능하다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.diagnostic verify --output-dir '<반환된 output_dir>' --manifest-sha256 '<반환된 manifest_sha256>'
```

실제 실행 기록은 [진단 집계 결과](../../docs/worklogs/S15P21A506-193/09-diagnostic-run.md)에 남긴다.

## 과거 스냅샷의 입력 모집단 준비

`historical_input.py`는 최신 관측 원본과 과거 계산 시각을 분리하여, 각 버전이 처음 포함되는
calendar index와 스냅샷별 전체 대상 수를 만든다. `dependents_count` 해석·집계는 하지 않는다.
source는 모든 Curated release 버전을 유지하고 배포일 NULL/마지막 기준일 이후만 제외한다.
target은 같은 집합에서 기존 npm worker의 valid stable semver 판정까지 통과한 버전이다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.historical_input --input-manifest '<7번 원본 input-manifest.json>' --input-manifest-sha256 '<파일 SHA256>' --calendar '<snapshot-candidate.json>' --calendar-sha256 '<파일 SHA256>' --expected-snapshot-count 229 --output '<새 실행 디렉터리>'
```

원본 manifest의 로컬 파일 집합·SHA를 시작/종료 시 검증하고 schema·행 수·UTC 관측 시각·
Curated/raw 키와 release/배포일 일치를 확인한다. `published_at_raw`는 원본 TIMESTAMP를
보존하고, 명시적 BigQuery UTC adapter로 TIMESTAMPTZ와 정수 microseconds를 함께 저장한다.
원본/정책/Node 모듈 지문은 출력 manifest에 연결하며 원격 게시 상태는 재검증하지 않는다.
기준일 개수는 명시한 기대값(기본 229)과 일치해야 하고 마지막 기준 시각은 원본 관측 시각과
같아야 한다. 날짜 목록 자체와 고정 SHA를 정본으로 쓰며 별도 요약 메타데이터로 날짜를 생성하지 않는다.

| 파일 | 내용 |
| --- | --- |
| `calendar.parquet` | 정확한 UTC 시각, 날짜, 0부터 시작하는 snapshot index |
| `source_population.parquet` | source 버전·최초 포함 index, 원본/정규화 배포일, 선언 수와 원본 오류·누락 flags |
| `target_population.parquet` | valid stable target 버전·최초 포함 index |
| `snapshot_population.parquet` | 날짜별 source/target 수와 선언 수·누락/오류 source 수. 오류 항목은 독립 flags이며 상호 배타적 source 상태 수가 아님 |
| `semver_classification.parquet` | 원문 버전 문자열별 기존 npm 판정. 정규화된 버전으로 키를 교체하지 않음 |
| `input_manifest.json` | 입력·코드·runtime 계보, 출력 파일 SHA/행 수, 대상 규모, 준비 완료 상태 |

manifest는 `count_status=NOT_COMPUTED`, `ready_for_load=false`를 유지한다. population 행에
count가 없다는 사실을 0으로 해석해서는 안 된다. `verify_historical_inputs(output, manifest_sha256)`는
별도 연결에서 파일 해시·schema와 배포 시각 경계를 확인하고, birth index별 건수로 모든 날짜의
누적 대상 수를 독립 대조한다. 완료 검증 후 `working.duckdb`와 `scratch`, 임시 JSONL은 실행 소유
중간 자료로 정리할 수 있다. 원본 데이터와 기존 7번 산출물은 정리 대상이 아니다.

실패한 실행 디렉터리는 진단을 위해 보존하며 완료 manifest가 없으면 입력 준비 완료로 취급하지
않는다. 같은 디렉터리에 덮어쓰지 않고 새로운 실행 ID로 재시도한다. source population에는
prerelease/invalid 버전도 있으므로 `source_population.source_version = semver_classification.version`
으로 연결하면 패키지 ID·이름·버전별 target 제외 이유를 추적할 수 있다. NULL/미래 배포일로
source 밖에 있는 버전은 manifest가 보존한 원본 Curated 파일 목록으로 추적한다.

실제 규모와 실행 기록은 [과거 입력 준비 결과](../../docs/worklogs/S15P21A506-193/11-historical-input-results.md)에 남긴다.

## 작은 데이터의 날짜별 집계 기준

`historical_reference.py`는 최적화 구현과 비교할 작은 정답 계산기다. 매 날짜·선언마다 기존
npm worker에 당시 배포된 후보를 넣어 다시 해석하고, source/target 버전 쌍을 중복 제거한다.
구간 캐시나 delta 로직은 사용하지 않는다. 결과는 target별 count(0 포함), 선언/source별
상태, 품질 보존식이며 `SMALL_REFERENCE_ONLY`, `ready_for_load=false`로 기록한다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.historical_reference --fixture 'pipeline/version_dependents/fixtures/historical_reference.json' --output 'data/version-dependents/reference-examples/run_id=my-example'
```

입력 JSON은 관측 시각, calendar, ID/이름 package 목록, ID가 연결된 release 버전과 원본 선언을
담는다. 버전의 `published_at`, `dependency_error`는 NULL도 명시한다. requirements 행 누락과
행이 있지만 `dependencies=null`인 경우를 구분하며, 일반 dependencies만 해석한다.
날짜의 시각은 timezone이 있는 UTC 변환 가능 값이어야 한다. 모든 계산 시각은 관측 시각
이하여야 하며, **소형 비교에서는 과거 날짜 일부만 calendar로 전달할 수 있다.** 생략한 날짜는
계산하지 않는다. 실제 H1의 전체 calendar·마지막 관측 시각 일치 검증을 대체하지 않는다.

상한은 fixture 4MiB, 버전 512개, 일반 선언 2,048개, 날짜 32개,
`날짜 수 × 버전 수 × max(선언 수, 1)` 2,000,000이다. 실제 H1 전체 자료를 넣는 실행 경로가
아니다. 새 output 폴더에 `reference_result.json`, 입력/코드/결과 SHA와 실행 시간을 담은
`reference_manifest.json`, Node 로그를 저장한다. 기존 output을 덮어쓰지 않는다.

합성 예제와 검증 범위는 [날짜별 기준 구현 결과](../../docs/worklogs/S15P21A506-193/12-historical-reference-results.md)를 참조한다.

## 과거 날짜별 구간 집계 핵심

`historical_semver_worker.cjs`는 고유 원문 요구조건마다 npm Range를 준비하고 새 후보의
birth index에서만 최대 만족 버전·미해석 상태를 갱신한다. 결과는 `[start_index, end_index)`
구간이다. 새 후보의 semver가 같으면 원문 UTF-16 순서를 비교한다. 기존 alias·prerelease·
미지원 프로토콜 정책과 Node/npm 지문을 유지한다.

`historical.py`의 `aggregate_interval_tables(con, snapshot_count)`는 로컬 DuckDB의
`sources`와 `declaration_intervals`를 받아 동일 source-target 구간을 합친다. 겹친 구간의
누적 최대 끝을 사용하고 원본 declaration index로 정렬 동률을 해소한다. 시작/종료 증감을
누적한 `counts`에는 양수 target/date만 생성한다. 원본 선언 상태와 source 품질은 중복
제거 전에 계산하여 `source_intervals`와 날짜별 품질에 보존한다.

두 입력 테이블의 정확한 컬럼·타입은 `_create_tables`를 따른다. 선언 구간은 해당 source의
최초 포함일부터 마지막 날짜 뒤 경계까지 빈틈·중첩 없이 존재해야 한다. 원본 source당 선언
수가 맞아야 하며, 범위 밖 index·미매핑 source·잘못된 상태/target·INT 초과를 거부한다.
연결·임시 디스크·메모리 제한·파일 계보와 실제 입력의 완전성은 호출자가 책임진다.

`compute_optimized(fixture, log_path=..., partition_count=1)`는 H2 크기 제한을 따르는 작은
fixture adapter다. count·상태 구간·품질·후보 검사 횟수를 반환하며 항상
`scope=BOUNDED_H3_FIXTURE`, `ready_for_load=false`다. partition_count는 패키지 그룹의
처리 순서를 바꾸어 결과 불변성을 확인하는 매개변수이며 여러 프로세스를 실행하지 않는다.

H4 정규화 cache의 날짜별 Parquet 출력·재개는 아래에 구현했다. 실제 H1 원본 선언 공급과 H5 전체 실행은 아직 연결하지 않았다.
[H3 측정 결과와 재현 방법](../../docs/worklogs/S15P21A506-193/13-historical-optimization-results.md)에서
합성 예제 비교를 확인할 수 있다. 실제 DB에서 누락을 0으로 처리하는 계약은 별도 결정이다.


## H4 정규화 계산 결과 저장과 날짜별 재개

`historical_cache.create_cache`는 호출자 DuckDB 연결의 세 테이블을 받아 공통 Parquet와
최초 manifest SHA를 반환한다. 관계를 날짜마다 파일로 확장하지 않고 양수 count 유지 구간과
전체 target birth를 한 번 저장한다. 전체 원본의 계산 연결은 H5, 아래 fixture adapter는 작은 예제 전용이다.

```sql
CREATE TABLE history_count_intervals (
    package_id INTEGER, version VARCHAR, start_index INTEGER,
    end_index INTEGER, dependents_count BIGINT
);
CREATE TABLE history_target_population (
    package_id INTEGER, version VARCHAR, birth_index INTEGER
);
CREATE TABLE history_quality (snapshot_index INTEGER, quality_json VARCHAR);
```

구간은 `[start_index,end_index)`이고 count는 1..2,147,483,647이다. 같은 target 구간은 겹칠 수
없으며 target birth 이전 count를 거부한다. quality는 H3 결과 JSON의 수·상태·제외 상세를 유지한다.
calendar, observed_snapshot_timestamp, lineage(source_kind/input_manifest_sha256/policy_sha256),
H3 runtime metadata를 인자로 넘긴다. `source_kind`는 `SYNTHETIC_FIXTURE` 또는
`NORMALIZED_HISTORY_TABLES`다. cache 생성 연결의 자원 상한은 호출자가 설정해야 한다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.historical_artifact demo `
  --fixture pipeline/version_dependents/fixtures/historical_reference.json `
  --output data/version-dependents/historical-artifact-examples/my-new-example
```

`demo`는 새 출력 위치에 cache를 만들고 첫 날짜만 저장한 뒤 나머지를 재개·검증한다.
입력 파일은 4MiB·512버전·2,048선언·32일 및 H2 비교량 상한을 지킨다. 실제 H1 파일을 이
adapter에 넣지 않는다. 일반 cache의 calendar 상한은 4,096이다.

`build --cache-dir <경로> --cache-sha256 <최초 SHA> --output <새 run>`으로 날짜별
counts/quality/lineage Parquet를 쓴다. `--max-snapshots 1`로 완료할 날짜 수를 제한할 수 있다.
같은 cache·최초 SHA·output에 `--resume`을 추가하면 완료 날짜는 값·SHA·입력/코드를 검증한
후 재사용하고 미완료 날짜만 새 attempt로 처리한다. 손상된 완료 날짜를 자동 덮어쓰지 않는다.
전체 날짜가 끝나야 `run_manifest.json`을 생성한다.

`verify --run-dir <run> --cache-dir <cache> --cache-sha256 <최초 cache SHA>
--run-manifest-sha256 <최초 run SHA>`는 별도 프로세스에서 결과를 다시 확인한다. 캐시 자체와
날짜별 모든 행을 대조하므로 최초 SHA를 출력 파일의 현재 SHA로 바꾸면 안 된다.

파일 검증은 2스레드·메모리 1GB·임시 디스크 4GB 상한과 Parquet VIEW를 사용한다.
OS 잠금은 프로세스 종료 시 해제된다. `.writer.lock` 파일 존재 자체는 실행 중을 뜻하지 않는다.

`quality_origin=UPSTREAM_H3_METADATA_WITH_CONSERVATION_CHECKS`는 source/선언 품질이
상위 메타데이터임을 뜻한다. H4는 원본 선언을 재해석하거나 모집단 완전성을 승인하지 않는다.
계산 날짜의 COMPLETE와 원본 resolution_status=PARTIAL을 분리하고 ready_for_load=false를
유지한다. DB의 sparse 저장·0 조회·게시 계약은 별도다.

[H4 결과·파일 구조·157개 회귀 테스트·3일 예제](../../docs/worklogs/S15P21A506-193/14-historical-artifact-results.md)


## H5-A 실제 입력 workload 프로필

`historical_profile`은 H1의 고정 manifest 및 원본 파일을 전후 검증하고,
고유 대상 이름/요구조건별 선언 수와 패키지별 후보 규모를 두 Parquet로 만든다.
일반 dependencies만 다루며 원본 배열과 날짜별 관계를 Python 리스트로 가져오지 않는다.
`profile_status=COMPLETE`여도 `count_status=NOT_COMPUTED`, `ready_for_load=false`다.

`historical_job --config <파일> --config-sha256 <최초 SHA>`가 프로필을 별도 프로세스로
실행하고 주기적으로 RSS·scratch·출력·여유 공간·시간을 검사한다. 5초 간격의 soft guard이며
DuckDB 설정과 예산도 교차검사한다. 완료/실패는 status.json과 immutable job_receipt.json에
기록된다. 완료되거나 문제가 생길 때까지 모델의 반복 조회를 필요로 하지 않는다.

Windows에서는 venv redirector의 PID와 실제 Python PID가 다를 수 있어 실제 인터프리터를
직접 실행하면서 기존 module path를 전달한다. supervisor가 강제 종료되면 worker도 이를
감지해 실패 기록 후 종료한다. 기존 job은 자동 덮어쓰지 않으며 새 job ID로 실행한다.

고유 조건마다 계산된 target 버전이나 dependents_count를 저장하는 단계는 아니다.
이 단계의 후속 계산기는 아래 H5-B 모듈이다.
[H5-A 입력·파일·자원·실행 계약](../../docs/worklogs/S15P21A506-193/15-historical-production-run.md)

## H5-B 선정 target의 전체 날짜 계산

`historical_production_input`은 고정 H1/H5-A/선정 CSV에서 target 후보와 고유 요구조건,
원본 source ID·버전·선언 순서를 연결한다. 선정 목록은 target에만 적용한다. 같은 target을
참조하는 전체 적격 source 버전을 포함하고 선언 수·후보 수를 H5-A와 대조한다.

`historical_production`은 target 이름별 파티션을 만들고 후보/요구조건/응답 크기를 제한해
기존 npm worker에 요청한다. `historical_production_sql`에서 source별 겹친 구간을 합쳐
count 변화량을 계산하므로 날짜별 전체 관계 파일을 만들지 않는다. 최종 count는 양수인
버전·날짜만 Parquet로 저장한다. 0을 복원할 대상은 공통 target population에 별도로 보존한다.

실행 진입점은 `python -m pipeline.version_dependents.historical_production`이다.

- `prepare`: `--h1-dir`, `--h1-manifest-sha256`, `--profile-manifest`,
  `--profile-manifest-sha256`, `--selection-csv`, `--selection-sha256`, `--output`을 받는다.
  표본은 `--sample-name <이름>`을 반복한다. 전체 선정 입력은 명시적 `--full-selected`가 필요하다.
- `run`: `--prepared-dir`, `--manifest-sha256`, `--output`을 받는다. 전체 선정 입력 실행은
  추가로 `--allow-full-selected`가 필요하다. 기본값으로 전체 실행을 시작하지 않는다.
- `--resume`: 완료 파티션과 날짜의 최초 지문·코드·값을 검증해 재사용한다.
  `--max-partitions`와 `--max-snapshots`는 완료 단위 수를 제한하는 검증용 옵션이다.
- `verify`: `--run-dir`, `--manifest-sha256`으로 파티션→공통 cache→날짜별 결과를 대조한다.

실행 전체의 시간 제한은 없다. 개별 Node 요청 제한은 60초다. DuckDB 기본 자원은 4스레드,
메모리 4GB, 임시 디스크 40GB이며 파티션 시작 전 여유 공간 20GB를 확인한다. 이 수치는
프로세스 전체 RSS의 강제 상한이 아니다. 작업용 DuckDB·scratch·로그는 진단용으로 남기고
완료 영수증에 명시된 파일만 계산 결과로 소비한다.

새 production manifest가 입력/선정 목록/생성 코드/runtime/파티션/cache/날짜별 결과를
연결한다. H4의 기존 `quality_origin`은 저장 어댑터의 기존 라벨이며, 실제 계산 출처는
바깥 provenance의 `H5_PRODUCTION_INTERVAL_SQL`이다. 계산 완료 후에도 상위 품질은 PARTIAL,
`ready_for_load=false`를 유지한다. DB 적재·게시를 수행하는 모듈은 아니다.

`historical_production_verify.verify_sample`은 작은 실제 표본을 매 날짜 기존 해석기로 다시
계산하고 DISTINCT source 버전 수와 lookup 상태를 비교한다. 최신 진단 Parquet와의 대조도
지원한다. `historical_production_benchmark`는 후보가 많은 한 패키지의 59개 실제 요구조건만
측정하는 별도 도구다. [검증 범위와 실측 기록](../../docs/worklogs/S15P21A506-193/16-historical-production-code.md)

production 날짜별 저장은 `historical_production_writer`를 사용한다. 새 날짜는 전수 값 검증을
한 번 수행하고 완료 표시 직전 SHA·크기를 다시 확인한다. 이전 날짜의 재개 및 `verify`는
전수 검증을 유지한다. 새 writer SHA를 daily plan에도 기록하므로 기존 H4 파일을 변경하거나
기존 run의 지문을 바꾸지 않는다. 같은 cache의 229일 저장 비교는 29.297초→23.078초였고,
count 파일 229개와 품질·이력 값이 일치했다. 전체 선정 패키지의 속도 개선률은 미측정이다.
[저장 최적화 결과](../../docs/worklogs/S15P21A506-193/17-historical-write-optimization.md)

### 가중치 이벤트 집계 옵션

`run --algorithm weighted-events-v2`는 단일 조건의 source/target 쌍을 조건·birth별 가중치로
묶고 버전 교체 사건에서 count를 이동한다. 다중 조건의 쌍은 source/target/version 구간
합집합으로 처리한다. 원본 중복 선언 수와 미해석 상태는 품질 계산에 별도로 보존한다.
source 품질은 파티션별 최초/마지막 해석·never 요약을 전역으로 합친 뒤 정한다.

기본 알고리즘은 `interval-sql-v1`이다. 새 방식은 `historical-production-run-v2`와 새 코드
지문을 사용하므로 새 출력 폴더가 필요하다. v2 파티션의 완료 파일은 `lookup_intervals.parquet`,
`counts.parquet`, `source_summary.parquet`, `status_deltas.parquet`이며 v1의 source delta를
읽어 혼합 재개하지 않는다. 최종 H4 relation 스키마는 같다. v2의 계산 출처는 provenance의
`H5_PRODUCTION_WEIGHTED_EVENTS`다. PARTIAL·`ready_for_load=false`는 유지한다.

같은 lodash 전체 source·229일 표본의 집계/전역 품질 3회 중간값은 11.652초→4.831초였다.
작은 6개 target은 0.501초→1.043초로 느려져 기본값 전환·자동 선택을 하지 않았다.
이 시간은 입력 준비·해석·날짜별 저장·DB 적재를 포함하지 않는다.
`historical_weighted_benchmark`는 검증된 legacy SAMPLE lookup 구간으로 두 집계 방식을
새 프로세스에서 교대 실행하고 모든 날짜 count·품질·모집단을 대조하는 제한된 측정 도구다.
[구현·실측·재현 기록](../../docs/worklogs/S15P21A506-193/19-weighted-event-aggregation.md)

### 날짜별 검증 합계와 처리량 측정

production cache·날짜 writer는 target 등장 시점과 count 구간의 시작/끝 변화량으로 모든
스냅샷의 기대 합계를 한 번에 계산한다. 날짜별 최댓값은 범위 최댓값 갱신으로 처리한다.
날짜마다 대형 테이블을 다시 합산하는 비용을 줄이고 실제 Parquet 모든 값의 양방향 비교,
스키마·SHA·품질·재개 검사는 유지한다. 이 합계 준비는 각 cache 검증/날짜 writer 단계에서
한 번 수행한다. 실제 날짜별 파일 읽기·쓰기는 계속 필요하다.

`historical_production_cache`와 `historical_production_daily`의 SHA를 새 cache/run plan에
포함한다. H4 원본은 그대로이며 이전 run의 지문을 고쳐 재개하지 않는다.
`historical_daily_benchmark`는 같은 검증된 cache로 변경 전후 writer의 파일 값과 시간을
비교한다. `historical_throughput_benchmark`는 고정한 중첩 8·16·32개 목록을 사용해
입력 준비→계산·저장→별도 검증을 순차 실행하는 로컬 Windows 측정 도구다.
모든 source 선언을 포함하며 자식 프로세스 RSS/CPU와 작업 디스크를 1초 표본으로 기록한다.
순간 최고값은 놓칠 수 있고, 디스크 최고값은 이전 단계 파일까지 포함한 누적 크기다.
시작 대비 증가량도 별도 기록한다. 시간 경과에 따른 종료 제한은 없다.

[변경 범위·측정 결과·전체 시간 추정 한계](../../docs/worklogs/S15P21A506-193/20-daily-verification-throughput.md)

## GPU 버전 해석 실험

`historical_gpu_benchmark`는 선택한 패키지의 최대 2048개 요구조건에 대해 기존 npm worker,
rank 구간을 사용하는 CPU 범위 인덱스, PyTorch CUDA 계산을 비교하는 별도 도구다.
production 실행기의 기본 해석기로 연결하지 않았으며 count 집계·Parquet 게시·DB 적재를 하지 않는다.
NumPy/PyTorch는 해당 실험 또는 아래의 선택형 CPU/GPU 경로에서 필요하다.
CUDA가 없으면 GPU 실행을 CPU로 대체하지 않는다.

`historical_gpu_normalize.cjs`가 기존 stable/npm 정책과 원문 동률을 rank 구간으로 정규화한다.
CPU는 min-birth segment tree를 조회하고 GPU는 조건 묶음별 birth 최대값과 날짜 누적 최대값을
계산한다. 실제 표본의 모든 날짜 interval과 상태를 기존 worker와 비교한다.

[RTX 4070 실제 결과·실행 방법·생산 적용 경계](../../docs/worklogs/S15P21A506-193/21-gpu-resolver-experiment.md)

`historical_gpu_suite_benchmark`는 기존 32개 prepared 표본과 완료 production run의 지문을
고정해 **전체 요구조건**을 비교한다. 패키지별로 최대 1024개씩 나누어 모두 처리하며 후보를
공유하지 않는다. 기존 정답의 target key·상태·날짜 구간을 매번 대조하고, 5회 전체 합계의
중간값을 계산한다. 공통 파일 읽기·입력 검사와 정규화, 숫자 계산, interval 변환을 구분한다.
생산 집계와 저장 시간은 포함하지 않는다. [32개 실험 기록](../../docs/worklogs/S15P21A506-193/22-gpu-32-package-comparison.md)

### 실제 집계에서 CPU/GPU 선택

`historical_production run --algorithm weighted-events-v2 --resolver-backend cpu` 또는
`--resolver-backend gpu`로 개선한 버전 선택을 실제 count 집계·Parquet 저장에 연결한다.
기본값 `npm`은 기존 해석 경로다. CPU에는 NumPy, GPU에는 NumPy와 CUDA 지원 PyTorch가
필요하며 CPU 경로는 PyTorch를 불러오지 않는다. 별도의 Arrow/pandas 의존성은 없다.

`--resolver-lookup-batch`는 한 요청의 요구조건 수(1~1024, 기본 1024),
`--gpu-workspace-mib`는 GPU 숫자 계산의 묶음 예산(1~512 MiB, 기본 128)이다.
요구조건을 생략하지 않고 나눠 처리한다. 후보·전송 크기 상한을 넘으면 실패하므로
모든 크기의 패키지를 처리할 수 있다는 의미는 아니다. 숫자 계산 결과는 기존과 같은
lookup 구간으로 변환하고, DuckDB에 타입을 지정한 열 묶음으로 전달한다.

backend·설정·실행 라이브러리와 장치 정보·생성 코드 지문을 run plan에 기록한다.
`--resume`에는 처음과 같은 값이 필요하다. 코드나 backend를 바꾸려면 새 출력 폴더를
사용하며, 이전 결과에 현재 지문을 덮어쓰지 않는다. GPU 요청 시 CUDA가 없으면 출력
폴더를 만들기 전에 실패한다. 결과 파일의 독립 `verify`에는 GPU가 필요하지 않다.

`historical_production_backend_benchmark`는 고정한 32개 목록의 입력을 한 번 준비하고
CPU/GPU를 각각 새 프로세스로 실행·검증한다. 기존 결과는 그 생성 코드로 미리 검증해
파일 지문을 보존한 reference를 사용한다. 요구조건 구간·count·품질의 모든 행을 비교하며
날짜별 품질의 실행 plan ID만 제외한다. 각 실행의 이력 연결은 자체 `verify`로 검사한다.
측정 단계와 결과는 [실제 집계 연결 기록](../../docs/worklogs/S15P21A506-193/24-cpu-gpu-production-integration.md)에 남긴다.

### 선택형 CPU 병렬 실행과 날짜 묶음 저장

`historical_parallel_input.prepare`는 고정 원본에서 입력을 한 번 준비하고 네 테이블을 물리적으로
분할한다. 이미 검증한 단일 prepared 입력은 `historical_parallel convert`로 새 분할 입력에 옮길 수 있다.
빈 묶음은 metadata만 남긴다. 이전 생성 계약의 분할 입력을 새 코드로 덮어쓰지 않는다.

`python -m pipeline.version_dependents.historical_parallel run --prepared-dir <분할입력>
--manifest-sha256 <입력SHA> --output <새결과폴더> --workers 4 --history-layout grouped`로 실행한다.
Windows에서 작업자 1/2/4개와 전체 DuckDB 기본 예산 4 threads·4GB를 사용한다.
`--resume`은 승인된 묶음 결과를 재사용하고 worker 수 변경을 허용한다. 전체 선정 실행에는
별도 `--allow-full-selected`가 필요하며, 이번 검증 범위는 실제 32개 표본이다.

`history-layout` 기본값은 기존 `daily`다. `grouped`는 묶음마다 여러 날짜의 양수 count를 한
Parquet에, 날짜별 품질을 한 Parquet에 저장한다. 이력과 cache·calendar·코드 지문은 run plan에 남긴다.
묶음 단위로 재개하므로 `grouped`와 `--max-snapshots`를 함께 사용할 수 없다.

최종 `run_manifest.json`의 `cache.directory` 아래 `history`가 저장 결과다.
`historical_parallel_writer.open_counts(con, history_dir, history_manifest_sha256, snapshot_at=날짜)`로
해당 날짜를 조회한다. `include_zero=True`를 명시하면 cache의 버전별 최초 포함 날짜를 사용해 0을 복원한다.
`open_quality`는 날짜별 품질 view를 제공한다. 모든 조회는 완료 pointer·receipt·파일 지문을 확인하며,
`historical_parallel verify --run-dir <결과폴더> --manifest-sha256 <최종SHA>`는 입력부터 실제 출력값까지 검사한다.

[병렬 실행·재개 검증](../../docs/worklogs/S15P21A506-193/26-parallel-input-cpu-execution.md) ·
[입력·검증·저장 개선과 반복 실측](../../docs/worklogs/S15P21A506-193/27-input-verification-storage-optimization.md)

### 선택형 CPU·GPU 작업 중첩

`historical_gpu_parallel`은 CPU 작업자 1/2/4개가 후보 준비·npm 조건 해석·집계·저장을 맡고,
한 GPU 프로세스가 숫자로 바꾼 버전 범위를 계산한다. 한 패키지의 후보는 여러 요청에서 재사용한다.
이 경로는 Windows와 CUDA 지원 PyTorch가 필요하며 기존 CPU 실행의 기본값을 바꾸지 않는다.

```powershell
python -m pipeline.version_dependents.historical_gpu_parallel run --prepared-dir <분할입력> --manifest-sha256 <입력SHA> --output <새결과폴더> --workers 4
python -m pipeline.version_dependents.historical_gpu_parallel verify --run-dir <결과폴더> --manifest-sha256 <최종SHA>
```

출력은 앞 절의 `grouped` 형식이고 같은 `open_counts`/`open_quality`로 조회한다.
작업자당 요청 하나, 송수신 16MiB, 후보 GPU cache 전체 64MiB, 계산 workspace 기본 128MiB로 제한한다.
`--rpc-timeout` 기본 120초는 요청 하나의 대기·송수신 제한이다. 전체 계산 시간 제한은 아니다.
GPU 장애는 실행 실패로 기록하며 자동 CPU 대체를 하지 않는다. 같은 입력·코드·장치 설정과
`--resume`으로 완료한 묶음을 재사용할 수 있고 CPU 작업자 수는 바꿀 수 있다. 독립 검증은 GPU가 없어도 된다.

`historical_gpu_parallel_benchmark supervise`는 같은 prepared 표본에 GPU+CPU 1/2/4를 측정한 뒤
선택한 GPU 구성과 CPU 4개를 교대 반복한다. 계산·저장·검증·비교 시간을 나누고 13개 데이터 그룹의
실제 값을 비교한다. 공통 입력 준비 시간은 제외하며 전체 패키지 처리 시간으로 환산하지 않는다.
[구현·장애 검증·실측 기록](../../docs/worklogs/S15P21A506-193/28-cpu-gpu-overlap.md)

2026-09-12 로컬 CPU 전체 집계는 선정 99,996개 패키지·229개 날짜의 준비부터 최종 검증까지
5,215.125초에 완료했다. 양수 count 296,325,102행을 128개 Parquet로 저장했다.
현재 CPU 기본 자원은 메모리 16GB·임시 디스크 256GB·개별 요청 180초이며 4개 작업자가 나눠 쓴다.
PARTIAL과 `ready_for_load=false`를 유지하며 DB 적재는 별도 작업이다.
[전체 실행 결과와 생성 지문](../../docs/worklogs/S15P21A506-193/30-full-selected-run.md)

## H6 DB 준비 소규모 검증

`historical_db_prepare.prepare_sample`은 완료된 FULL_SELECTED CPU grouped 실행의 지문과
선택한 입력/출력 파일을 검사한 뒤 요청한 패키지·날짜의 적격 버전만 펼친다.
양수 값이 없는 적격 버전은 0으로 보완하며, DB의 ID/이름·버전 복합키·날짜를 읽기 전용으로 확인한다.
기본 PostgreSQL 세션 유틸리티를 재사용하며 새 드라이버는 필요하지 않다.
최대 32개 이름·4개 날짜·100,000행의 pilot 전용이다.

`historical_db_probe.apply_sample`은 새로 만든 `pickage_193_probe_<32자리 hex>` DB에서만
COPY/키 검증/UPSERT를 허용한다. 변경 컬럼은 dependents_count뿐이며 동일 값은 갱신하지 않는다.
서비스 DB 전체 적재기나 공통 ETL 게시기를 대신하지 않는다. PARTIAL과 `ready_for_load=false`를 보존한다.

실제 PostgreSQL 검사는 기존 격리 컨테이너를 지정해 실행한다. 테스트마다 새 검증 DB를 소유하고 정리한다.

```powershell
$env:PICKAGE_TEST_CONTAINER = 'pickage-267-validation'
python -m unittest pipeline.version_dependents.test_historical_db_prepare pipeline.version_dependents.test_historical_db_probe
```

[실제 78행 적재·재실행 결과와 남은 범위](../../docs/worklogs/S15P21A506-193/31-db-preparation-pilot.md)


### H7 전체 키 확인과 날짜별 적재

`historical_db_load`는 완료된 FULL_SELECTED CPU 집계와 동일한 package-version/달력 원천을 확인한다.
DB의 `package_version_snapshot`에는 선정 대상의 0 포함 버전별 count만 기록한다. 참조 수는 전체 source 버전이 참조하는 수이며,
원본 미해석 관계는 계속 PARTIAL로 보존한다. `PUBLISHED`는 해당 날짜 적재가 원자적으로 성공했다는 뜻이다.

아래 명령은 **읽기 전용 키 검증만** 실행한다. 데이터 전송을 위한 PostgreSQL TEMP 테이블만 만든다.

```powershell
python -m pipeline.version_dependents.historical_db_load `
  --run-dir data/vd-full-20260912-01/run `
  --manifest-sha256 1b6c01042e43de9da897a647b52dc1a76ef555385d4716bab91c8e934a32bc94 `
  --output data/vd-h7-load-new `
  --container pickage-267-validation --database pickage_267_full_defaulted
```

실제 쓰기는 `--publish`를 명시해야 한다. 날짜를 지정하지 않으면 229개 날짜 전체가 대상이며,
`--date YYYY-MM-DD`를 반복하면 해당 날짜들만 적재한다. 입력·연결 대상·날짜·코드가 같은 명령과 출력 폴더로 재실행한다.
코드가 달라지면 기존 계획을 덮어쓰지 말고 변경을 검토한 후 새 출력 폴더를 사용한다.
완료 날짜는 DB 값을 재검증하고 미완료 날짜를 적재한다. 날짜 중간 실패는 해당 날짜 전체를 rollback한다.
서로 다른 입력으로 게시된 날짜와 출처 없는 기존 행은 자동 덮어쓰지 않는다.

`status.json`은 현재 실행 상태, `progress.jsonl`은 단계별 이력이다. `result.json`은 마지막 완료 결과이므로
현재 실행이 실패했는지는 `status.json`을 먼저 확인한다. 매 실행의 영구 결과는 `attempt-*/result.json`,
날짜별 결과는 `attempt-*/YYYY-MM-DD.json`에 보존된다. DB의 execution/attempt 이력이 실제 COMMIT의 기준이다.
동일 실행을 재확인할 때도 날짜 COPY 파일을 다시 만들므로 재개가 즉시 끝나는 것은 아니다.
한 날짜의 COPY 파일만 재사용하고 전체 10억 행을 임시 파일 하나에 미리 생성하지 않는다.

이전 전체 적재는 43일/106,346,692행에서 중단되어 보존 중이다. 위 실행기는 그 이전 방식이다.
빠른 전체 재적재는 별도 날짜별 partition 대상에 229일을 다시 저장하도록 준비했다.
기본 점검은 `scripts/version-dependents-reload.ps1 -Action Check`를 사용한다.
2026-09-12 전체 재적재를 시작했으며, 조회 구조 검토를 위한 사용자 요청으로 19일/43,616,976행 적재 후 정상 중단했다.
자동 재개하지 않으며 이후 재개할 때는 `-Action Resume`을 사용한다. 서비스 테이블 전환은 하지 않았다.
[실행·중단 기록](../../docs/worklogs/S15P21A506-193/41-fast-full-reload-run.md)과
[빠른 적재 실행 안내](../../docs/worklogs/S15P21A506-193/40-fast-reload-runbook.md)에서 설정·재개·서비스 전환의 범위를 확인한다.
