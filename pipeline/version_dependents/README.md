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
전체 worker request/response byte, 실제 해석 표본 성능, interval-only production 경로와
229일 count는 후속 H5 범위다. [자세한 입력·파일·자원·실행 계약](../../docs/worklogs/S15P21A506-193/15-historical-production-run.md)
