# 14. 날짜별 Parquet 저장과 재개

## 변경 범위와 작업 계획

사용자의 다음 단계 진행 요청에 따라 H4를 수행한다. H3의 계산 결과를 파일로 고정하고,
날짜별 양수 count·품질·입력 이력을 저장한다. 완료한 날짜는 검증 후 재사용하며 미완료
날짜는 새 시도로 저장한다. 중단된 시도와 기존 성공 파일은 보존한다.

1. H3 결과를 인계할 정규화된 DuckDB 테이블 계약과 Parquet cache를 만든다. target 목록은
   한 번, 양수 count는 유지 구간으로 저장한다. 입력·정책·코드·runtime SHA와 calendar를 고정한다.
2. cache를 읽어 날짜별 count·quality·lineage Parquet를 저장하고 별도 파일 검증을 통과한
   시도만 완료 기록에 연결한다. 모든 날짜가 끝나야 전체 완료 manifest를 만든다.
3. OS가 프로세스 종료 시 해제하는 로컬 파일 잠금, 새 attempt, 재개 시 입력·코드 identity
   대조로 동시 실행·중단·변조·누락·다른 코드의 결과 재사용을 검사한다.
4. 합성 데이터에서 저장·중단·재개·별도 CLI 검증을 실행하고 H2/H3와 값·상태를 대조한다.

기존 resolver/H1/H2/H3 계산식·기존 단일 날짜 저장 기능·서비스 DDL은 보존한다. 이번에는
정규화된 계산 결과의 파일 인계와 저장·재개를 연결한다. 실제 H1 원본 선언을 대용량으로
전개해 worker에 분할 공급하는 실행기, 실제 데이터 성능 측정과 229일 전체 실행은 H5에서
연결·검증한다. 전체 입력을 작은 fixture adapter에 넣는 방식으로 확장하지 않는다.

DB의 0·누락·미계산 조회 계약과 PARTIAL 서비스 게시 여부는 별도 결정으로 남긴다.
계산·파일 검증 완료를 DB 게시 승인으로 표시하지 않으며 ready_for_load=false를 유지한다.
DB/Jira/commit/push, 원본 데이터 수정·삭제와 실제 229일 전수 실행은 이번 범위 밖이다.

## 실제 결과

H4의 정규화 cache·날짜별 Parquet·검증·재개를 구현했다. 기존 121개와 신규 36개,
전체 **157개 테스트가 45.686초에 통과**했고 Python 24개 파일의 AST 검사도 통과했다.
이전 H3 검증에 기록된 21개 코드/재현 파일의 SHA가 그대로였다. 독립 검토는 PASS다.

### 저장하는 데이터

공통 cache는 세 테이블을 받는다. 입력은 이미 H3 방식으로 계산한 정규화 결과이며,
현재 실제 H1 원본을 직접 읽는 실행기는 없다. `create_fixture_cache`는 4MiB·512버전·
2,048선언·32일 제한의 합성 예제 전용이다.

| 공통 Parquet | 행 단위와 역할 |
| --- | --- |
| `count_intervals.parquet` | package_id·version·[start_index,end_index)·양수 count. 같은 숫자가 유지되는 기간을 저장 |
| `target_population.parquet` | 전체 유효 target package_id·version·birth_index. 대상 버전은 한 번만 저장 |
| `quality.parquet` | snapshot_index·H3 quality JSON. source·선언·미해석·제외·품질 상태 유지 |

날짜별 결과는 아래 세 파일이다. source-target 관계 파일과 0 count 행은 생성하지 않는다.

| 날짜별 Parquet | 저장 내용 |
| --- | --- |
| `counts.parquet` | package_id INTEGER·version VARCHAR·snapshot_at DATE·snapshot_timestamp TIMESTAMPTZ·dependents_count INTEGER. count > 0만 저장 |
| `quality.parquet` | target 전체/양수/0 수, source 수, 선언·해석·미해석 수, 고유 관계 합계, 중복 선언, 원본 품질 JSON·상태 |
| `lineage.parquet` | 입력/cache/정책/코드 SHA, 계산 날짜·관측 시각, 지표 정의, 검증 범위, ready_for_load=false |

전체 target 목록과 birth index, 완료한 날짜의 양수 결과를 함께 사용하면 해당 날짜의
성공 관계 기준 0을 구분할 수 있다. PARTIAL의 0은 실제 의존자가 전혀 없다는 증명이 아니다.
아직 계산하지 않은 날짜에는 완료 기록이 없고, 0으로 채우지 않는다. DB의 저장·조회 계약은 별도다.

### 재개와 검증 방식

```text
cache/
  count_intervals.parquet
  target_population.parquet
  quality.parquet
  cache_manifest.json
run/
  run_plan.json
  .writer.lock
  snapshot=YYYY-MM-DD/
    attempts/<시도 ID>/
      counts.parquet
      quality.parquet
      lineage.parquet
      snapshot_manifest.json
    complete.json
  run_manifest.json
```

1. cache의 최초 manifest SHA를 호출 인자로 고정한다. 모든 파일의 이름·크기·SHA·스키마,
   구간 경계·중복·target birth·count 합계·품질 보존식과 코드 지문을 검증한다.
2. 날짜별로 새 attempt에 저장하고 공통 cache에서 만든 기대값과 파일을 양방향으로 대조한다.
   파일 manifest와 SHA를 검증한 후 `complete.json`을 원자적으로 게시한다.
3. `--resume`은 먼저 모든 완료 날짜의 파일·값·입력·코드 이력을 검증한다. 성공한 날짜는
   재사용하고 미완료 날짜만 새 attempt로 저장한다. 기존 실패 시도는 보존한다.
4. calendar의 모든 날짜가 끝난 경우에만 전체 `run_manifest.json`을 만든다. 별도 `verify`
   명령은 이 파일의 최초 SHA와 cache SHA를 받아 읽기 전용으로 검사한다.

Windows/POSIX의 OS 파일 잠금을 사용한다. 프로세스가 종료되면 잠금은 해제되며,
`.writer.lock` 파일이 남아 있다는 이유로 실행 중이라고 판단하지 않는다. 테스트용 별도
프로세스를 실제 강제 종료한 뒤 잠금 재취득을 확인했다. 컴퓨터 재부팅/전원 차단 자체는
테스트하지 않았다. 저장 중 손상·누락이 발견되면 완료 결과 재사용을 거부한다.

입력과 결과는 reparse point·symlink 경로를 거부한다. 검증은 Parquet VIEW로 수행하고
DuckDB 2스레드·메모리 1GB·임시 디스크 4GB 상한을 둔다. `create_cache`의 입력 연결과
대량 COPY 자원은 호출자가 소유한다. 실제 229일의 최고 메모리·디스크·성능은 미측정이다.

### 검증의 의미와 한계

`quality_origin=UPSTREAM_H3_METADATA_WITH_CONSERVATION_CHECKS`를 cache에 명시했다.
원본 source/선언 상태는 H3가 제공한 메타데이터다. H4는 상세 상태 보존식과 PARTIAL 판정,
실제 target 수와 count 합계를 대조하지만 원본 선언을 다시 해석하지 않는다. 입력 manifest
SHA와 정책 SHA도 호출자가 제공한 식별자이며, 원본 파일의 완전성을 별도로 승인하지 않는다.

Node/npm 버전·모듈/의존 모듈 SHA·옵션은 상위 계산의 실행 이력으로 보존한다. 날짜 파일
저장 시 Node를 다시 실행하지 않는다. Python 코드와 DuckDB 버전이 바뀌면 기존 run을
재사용하지 않는다. 과거 부분 calendar는 허용하되 각 날짜의 UTC 시각은 관측 시각 이하여야 한다.

`calculation_status=COMPLETE`는 고정된 cache 기준의 날짜 출력 완료다. 원본 해석 상태는
`resolution_status=PARTIAL` 또는 `COMPLETE`로 따로 보존하며 모든 파일은
`ready_for_load=false`다. 전체 파일 검증 완료를 서비스 DB 게시 승인으로 표시하지 않는다.

### 실제 합성 예제

최종 예제 폴더: `data/version-dependents/historical-artifact-examples/run_id=h4-20260910T141251907045Z`

첫 실행에서 8월 10일 하나만 완료하고 INCOMPLETE로 종료했다. 재개 시 그 날짜를 재사용하고
8월 21일·31일을 추가해 COMPLETE가 됐다. 별도 프로세스 검증은 3개 날짜에 통과했다.
재개 전후 기존 날짜의 파일 수정 시각·바이트 보존은 회귀 테스트에서 확인했다.

| 날짜 | dep 1.0.0 | dep 1.2.0 | util 1.0.0 | 전체 target / 양수 / 0 |
| --- | ---: | ---: | ---: | --- |
| 2026-08-10 | 1 | 대상 아님 | 2 | 3 / 2 / 1 |
| 2026-08-21 | 0 | 2 | 2 | 5 / 2 / 3 |
| 2026-08-31 | 0 | 2 | 2 | 6 / 2 / 4 |

표의 0은 공통 target 목록과 완료 결과를 통해 설명한 값이며 count 파일에는 없다.
공통 cache의 count 구간은 3행, target은 6행이다. 날짜별 count는 총 6행이며,
공통 3개+날짜별 9개로 Parquet 12개를 생성했다. 모두 합성 데이터다.

초기 손계산 대조 스크립트는 package_id를 20/30으로 잘못 적어 실패했다. fixture의 실제
ID 2/3으로 기대값을 수정한 뒤 저장 파일 그대로 대조를 통과했다. 계산 결과 수정은 없었다.

### 발견한 문제와 해결

- 초안 cache 검증은 runtime·코드 지문·품질 상세·calendar 일부만 검사했다. 필수 runtime
  지문, 생성 전후 코드 SHA, 각 날짜 검증, 실제 count/target 수 및 상세 상태 대조를 추가했다.
- 초기 일부 변조 테스트가 SHA를 생략하거나 keyword 전용 API를 위치 인자로 호출해 다른
  오류를 잡았다. 호출을 고치고 오류 메시지를 확인했으며 값·manifest를 함께 재해시한 변조도
  cache와 값이 다르면 실패하는 독립 테스트를 추가했다.
- 빈 target/count 입력에서 행별 INSERT가 실패할 수 있었다. 예제 adapter를 명시적 타입의
  JSON 입력으로 바꾸고 전체 배포일 NULL인 예제의 빈 Parquet 저장·재검증을 확인했다.

### 결과 확인과 재현

- [합성 실행·재개·손계산 대조 영수증](evidence/historical-artifact-run.json)
- [전체 테스트 결과](evidence/historical-artifact-validation.json), [테스트 로그](evidence/historical-artifact-tests.log)
- [독립 검토](evidence/historical-artifact-review.md)
- [예제 저장 영수증](../../../data/version-dependents/historical-artifact-examples/run_id=h4-20260910T141251907045Z/demo_receipt.json)

새 예제는 다음과 같이 실행한다. output은 아직 없는 새 디렉터리여야 한다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.historical_artifact demo `
  --fixture pipeline/version_dependents/fixtures/historical_reference.json `
  --output data/version-dependents/historical-artifact-examples/my-new-example
```

완료한 run의 재검증은 `demo_receipt.json`의 cache 경로/SHA와 final run 경로/SHA를
`verify --cache-dir ... --cache-sha256 ... --run-dir ... --run-manifest-sha256 ...`에 전달한다.
확인 편의를 위해 지금 파일에서 새 해시를 계산해 최초 해시를 대체하지 않는다.

## 남은 작업

H5에서 실제 H1 원본을 분할해 읽고 큰 패키지의 후보·요구조건을 worker 상한 안에서 공급하는
실행기를 연결한다. 정규화 계산 구간을 H4 cache로 넘긴 뒤 작은 실제 범위에서 최신 진단
결과와 비교하고 시간·메모리·임시 디스크를 측정한다. 이 결과로 전체 229일 실행 자원을 정한다.

실제 229일 count 계산, 69.7억 0 포함 행 생성, DB/Jira 접속, commit/push는 실행하지 않았다.
