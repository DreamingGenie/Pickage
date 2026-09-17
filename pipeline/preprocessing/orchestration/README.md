# MinIO raw → Curated 실행기

하나의 명시적 raw 스냅샷을 기존 전처리에 연결하고, 검증된 결과 묶음을 MinIO에 게시한다.
수집·BigQuery/npm API 호출·DB 적재·Java 구현·스케줄러는 포함하지 않는다.

## 실행

저장소 루트에서 기존 Python 환경(DuckDB/boto3), Node/npm의 semver 및 npm-package-arg,
기존 repository-metrics용 Spark 실행 환경을 사용한다. 새 라이브러리를 추가하지 않았다.
MinIO 설정은 기존 `pipeline/minio/README.md`의 `.env` 설정을 그대로 사용한다.
`PICKAGE_MINIO_ENV`가 설정되어 있으면 기존 client가 해당 설정 파일을 선택한다.

```powershell
python -m pipeline.preprocessing.orchestration plan --request request.json
python -m pipeline.preprocessing.orchestration run --request request.json --work-dir data/orchestration
python -m pipeline.preprocessing.orchestration status --request request.json
python -m pipeline.preprocessing.orchestration resume --request request.json --work-dir data/orchestration
```

`plan`은 네트워크 없이 요청 형식·실행 순서·출력 위치를 보여준다. raw 도착을 확인하는 명령은
`run`이며 필수 입력 미도착은 `WAITING_INPUT` 및 종료 코드 2, 잘못된 입력은 실패로 구분한다.
`status`는 완료 marker/manifest를 확인하지만 모든 출력 바이트를 다시 읽지는 않는다.
`run`/`resume`은 완료된 결과도 실제 객체 해시를 재검증한다. `resume`은 등록된 run에만 가능하다.

`request.example.json`은 **형식 예제**다. SHA 값을 실제 생산자 명세의 값으로 바꿔야 실행할 수 있다.
Windows에서는 `--work-dir C:/pickage-work`, `run_id=s20260831`처럼 짧은 경로를 사용한다.
Docker가 만든 긴 파일 경로를 Windows에서 읽지 못하는 경우가 있어, 예상 Spark 출력 경로가
260자 이상이면 원격 실행 등록 전에 거부한다. Linux 운영 실행에는 이 Windows 제한을 적용하지 않는다.
다운로드 대상은 downloads Bronze manifest 안의 target CSV로 고정된다. dependents 대상은 별도의
`name VARCHAR` Parquet에 고정한다. 두 목록이 같다고 가정하지 않는다.

## 주간 실행

### 주간 입고 데이터 한 명령 실행 (v2)

최초 full 스냅샷의 **전체 Curated bundle**이 완료된 뒤 실행한다. package/version만
적재된 예전 결과로 주간 처리를 시작하지 않는다. 서버 연결과 스케줄 등록은 별도 작업이다.

```powershell
python -m pipeline.preprocessing.orchestration weekly --snapshot 2026-09-07 --run-id weekly-20260907 --work-dir C:/pickage-work --repository-engine docker
```

Linux에서 Python·Java·Spark·Node가 함께 설치된 실행 환경이면 `--repository-engine native`를
사용한다. 기본 raw run ID는 `bronze-weekly-YYYYMMDD`, 다운로드 run ID는
`downloads-weekly-YYYYMMDD`다. 실제 수집기가 다른 ID를 사용했다면 `--bronze-run-id`,
`--download-run-id`로 지정한다. 정확한 관측 시각은 승인된 Projects Parquet에서 읽는다.

이 명령은 원천을 재수집하지 않는다. 기존 MinIO 설정으로 다음 작업을 이어서 수행한다.

1. 원천 명세·완료 marker와 직전 완료 bundle을 확인하고, 다운로드 CSV의 대상 이름을 중복 제거한 Parquet로 고정한다.
2. `<work-dir>/requests/<run-id>.json`에 원천 SHA·부모·달력·자원 설정을 저장한다.
3. `versions_min`에 이전 Curated 메타데이터를 결합하고 기존 6단계 전처리를 실행한다.
4. 검증된 결과와 변경분을 게시한 뒤, 완료 bundle의 `_current.json`을 조건부로 갱신한다.

실패 후에는 **같은 명령·run ID·work-dir**로 재실행한다. 저장된 요청을 그대로 사용하며,
완료된 단계는 SHA 검증 후 재사용한다. 옵션을 바꿔 다시 계산하려면 새 run ID가 필요하다.
입력/코드가 바뀐 실행을 같은 run ID로 이어 붙이지 않는다.
v2는 새 날짜를 직전 완료 날짜에 이어 붙이는 흐름이다. 완료된 같은 날짜를 새 코드로 교체하거나,
다른 미완료 run이 package-version pointer를 이미 갱신한 상태에서 새 run으로 갈아타는 작업은
자동으로 하지 않는다. 해당 경우에는 기존 요청·pointer를 확인하는 별도 복구가 필요하다.

입고 간격이 14일보다 길어 현재 downloads raw만으로 `[직전 스냅샷, 현재 스냅샷)`을
채우지 못하면 `--download-history-run-id <이전 raw ID>`를 반복 지정할 수 있다.
현재 회차 우선, 추가 회차는 지정한 순서로 동일 `(name,date)`를 선택한다.
값 충돌·중복은 input manifest의 history 품질 정보로 남긴다. 확보되지 않은 날짜는 기존
coverage/NULL 정책으로 표시하며, 입고 성공을 구간 전체 다운로드 확보로 간주하지 않는다.
대상 목록과 상태는 현재 회차를 기준으로 한다. history의 현재 대상 밖 행·현재 READY가 아닌
행은 제외하고 건수를 기록한다. 중복 품질에는 전체 키 건수와 최대 100개의 사례를 기록한다.
같은 원천 회차 내부의 중복이나 물리 날짜/partition 날짜 불일치는 병합 전에 실패시킨다.

### 주간 메타데이터와 변경분

- 기존 package ID, repo_url과 기존 version의 description/licenses를 유지한다.
- 신규 패키지는 이 메타데이터가 NULL이다.
- 기존 패키지의 신규 버전은 직전 완료 Curated에도 있고 현재 min에도 있는 낮은 ordinal 버전 중 가장 가까운 버전에서 복사한다. ordinal 비교는 현재 스냅샷 기준이며 동률일 때만 버전 문자열 오름차순으로 고정한다. 같은 회차 신규 버전끼리는 복사하지 않는다.
- 후보가 없거나 후보 값이 NULL이면 NULL을 유지한다. 출처 버전과 부모 SHA는 `quality/metadata_provenance`에 남긴다.
- 저장소 URL은 기존 Curated의 **package 단위 값**을 보존한다. 과거 version별 원천 URL을 새로 복원했다고 주장하지 않는다.
- `Deprecated`, 의존성 등 min/requirements에 있는 값은 현재 원천으로 계산한다.

package-version stage의 승인 파일 목록에는 다음 추가 산출물이 포함된다.

| 경로 | 용도 |
| --- | --- |
| `package/data`, `version/data` | 현재 스냅샷의 전체 적격 모집단 |
| `changes/package_upserts.parquet`, `changes/version_upserts.parquet` | 신규 INSERT·값 변경 UPDATE; 변경 없는 행 제외 |
| `changes/missing_previous_*.parquet` | 이전에는 있었지만 현재 원천에는 없는 행; 삭제 명령이 아님 |
| `master_package/data`, `master_version/data` | 현재 원천에서 빠진 과거 행도 유지하는 누적 master |
| `weekly_versions/data` | repository 계산용 파생 full 형태 입력; raw full로 위장하지 않음 |

최초 full 회차는 전체 package/version으로 초기화한다. 부모가 있는 회차부터 upsert 차분을
만든다. snapshot 지표는 매 회차 전체 계산한다. **변경분 출력이 계산 자체의 증분화를 뜻하지 않는다.**

### 로컬 회귀 검증

`pipeline.preprocessing.tests.orchestration.test_weekly_integration`은 실제 6단계를 실행하는 합성 full→min 테스트다.
Spark를 포함한 기존 `pickage-spark-experiment:runtime-3.5.3` 환경을 사용할 수 있다.
`WEEKLY_FIXTURE_PACKAGES=1000`으로 표본 크기를 늘린다. 외부 API·DB는 호출하지 않는다.
`WEEKLY_TEST_ENDPOINT` 미설정 시 메모리 S3, 설정 시 전용 로컬 MinIO 주소만 허용한다.
이 테스트의 성공은 실제 두 스냅샷의 성능 비교 또는 운영 EC2 검증을 뜻하지 않는다.

## 처리 순서

1. 입력 manifest/SHA·완료 표시·시각·스키마·ID 부모를 검사한다.
2. 명시된 Projects 달력으로 snapshot candidate를 만들고 Curated에 게시한다.
3. 기존 package/version builder가 raw를 정규화하고 이전 ID를 유지한다.
4. `[직전 달력 날짜, 이번 날짜)` 다운로드 집계와 동일 관측 시각의 저장소 지표를 생성한다.
5. package_snapshot을 통합한다.
6. 8번의 자격 판정·npm semver resolver·SQL 집계를 재사용하여 이번 날짜의 version dependents를 만든다.
7. 모든 필수 산출물을 검증한 뒤 bundle manifest, `_SUCCESS` 순서로 게시한다.

각 단계의 계산 엔진과 기존 manifest 형식은 유지한다. 저장소 지표는
`options.repository_engine=native`이면 기존 로컬 Spark, `docker`이면 저장소에 고정된 Spark 컨테이너를
쓴다. Docker Spark는 읽기 전용 입력 마운트와 `--network none`을 사용한다.
`memory_limit`은 DuckDB 및 Spark driver 설정이며 전체 프로세스·컨테이너 메모리 합계의 상한이 아니다.
기존 Docker Spark 컨테이너 메모리 제한은 6 GiB다.

## 실패·재개와 로그

- 요청·코드 계약·작업 디렉터리가 같은 경우에만 기존 run ID를 재사용한다. 입력 또는 코드가 달라지면 새 run ID를 쓴다.
  package/version 완료 후 후속 단계가 실패한 경우에도 새 run ID는 현재 ID 부모를 명시하여 같은 날짜를 다시 계산할 수 있다.
  기존 실행 결과를 새 코드의 산출물로 재인증하지 않는다.
- `work-dir/run_id`를 유지한다. 첫 구현은 동일 호스트·동일 작업 디렉터리에서 재개한다.
  로컬 경로를 포함하는 기존 snapshot/repository 명세 때문에 다른 머신으로 무조건 이동해 재개하지 않는다.
- 단계별 attempt, 시작/종료, 오류, manifest SHA는 `status.json`과 개별 `events/*.json`에 남는다.
  원격 로그는 `depsdev/v1/curated-bundle/snapshot=S/run_id=R/` 아래에 저장된다.
- 단계 완료 checkpoint가 있으면 파일을 재검증한 뒤 재사용한다. 실패한 단계의 임시 결과는 이력으로 보존한다.
- 운영은 단일 실행 호스트를 전제로 한다. 호스트 OS 잠금은 프로세스 종료 시 풀린다.
  기존 builder의 객체 잠금은 해당 run이 획득하려던 정확한 토큰을 기록하며, 재개 때 일치하는 자기 잠금만 복구한다.
  다른 실행의 잠금은 지우지 않는다. 이 기능은 여러 호스트의 분산 잠금이나 운영 failover를 보장하지 않는다.
- MinIO 업로드 실패 중에도 로컬 상태 기록을 먼저 남긴다. 완료 marker가 게시된 뒤 상태 기록만 실패했다면
  marker가 완료 사실의 기준이며 재개로 상태 기록을 정리할 수 있다.

## 인수 및 검증 경계

수집 담당자는 [입력·출력 계약](CONTRACT.md)에 맞는 raw와 완료된 producer manifest를 제공한다.
후속 Java 적재기는 완료 bundle의 정확한 경로를 받아 파일을 소비한다. dataset별 최신 경로를 따로 찾지 않는다.

작은 스냅샷의 실제 전처리 및 실패 시험과 전체 규모 성능 검증은 구분한다.
과거 전체 데이터 정합성 검증을 다시 실행하지 않는다. 운영 raw 한 스냅샷 전체 실행, 처리 시간·메모리·임시 디스크
용량의 실제 규모 측정, 운영 버전 MinIO 호환성 시험은 별도 실행 항목이다.
세부 결과는 `docs/worklogs/raw-to-curated-pipeline/02-validation.md`에 기록한다.
