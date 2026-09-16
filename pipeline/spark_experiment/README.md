# 기존 전처리와 Spark 전처리 비교

일반 실행은 계속 `python -m pipeline.orchestration`을 사용한다. 이 모듈은 별도 실험용이다.
기존 계산 코드는 보존되어 있고, Spark 구현은 이 디렉터리에만 추가한다.

## 비교하는 내용

| 단계 | baseline | spark |
| --- | --- | --- |
| package/version 및 ID | DuckDB | Spark DataFrame |
| 구간 다운로드 | DuckDB | Spark DataFrame |
| 저장소 지표 | 기존 local Spark | 같은 규칙의 Spark |
| package snapshot | DuckDB | Spark DataFrame |
| 직접 dependents | DuckDB + Node semver | Spark 집계 + executor의 Node semver |

baseline에도 저장소 지표용 Spark가 이미 포함되어 있다. 따라서 순수 비-Spark와의 비교는 아니다.
Node의 npm 버전 해석 규칙은 유지한다. 전역 데이터 전체를 driver의 Python 목록으로 가져오지 않으며,
dependents 해석은 패키지 이름 단위로 executor에 모은다. 단일 패키지의 버전·요구사항이 매우 많으면
그 그룹이 병목이 될 수 있으므로 운영 측정에서 확인해야 한다.
기존과 같은 순서로 ID를 부여하기 위한 전역 정렬도 단일 파티션 병목 후보다.
전체 데이터에서 메모리·스필·정렬 비용을 아직 검증하지 않은 초기 비교 구현이다.

`prepare`는 기존 입력 검증과 기준 계산을 수행하되, Curated 쓰기를 **로컬 파일 저장소로 우회**한다.
실제 MinIO에서는 raw와 지정한 부모 ID 실행을 읽는다. 운영 ID 포인터와 완료 manifest를 갱신하지 않는다.
이후 각 단계가 받을 입력 파일 목록·SHA-256을 고정하여 두 엔진에 똑같이 전달한다.
후속 단계는 각 엔진의 직전 결과가 아니라 고정된 기준 입력을 받는다.
이는 **단계 계산 비교**이며, Spark 결과를 연속 연결한 운영 전체 파이프라인 검증은 아니다.

## 로컬 실행

저장소 루트에서 실행한다. Python 환경에는 기존 파이프라인 의존성(DuckDB/boto3 등)이 필요하고,
기준 입력 준비에는 기존 repository 단계의 Docker Spark 실행 환경이 필요하다.

```powershell
docker build -f pipeline/spark_experiment/Dockerfile -t pickage-spark-experiment:local .

# 외부 서비스 연결 없이 작은 합성 입력을 준비한다. 새롭고 짧은 경로를 사용한다.
python -m pipeline.spark_experiment fixture --work-dir C:/tmp/spark-exp-01

# 같은 이미지, CPU, 컨테이너 메모리 상한에서 순차 실행한다.
python -m pipeline.spark_experiment benchmark --manifest C:/tmp/spark-exp-01/i/experiment.json --repetitions 3 --threads 2 --memory 2GB --container-memory 6g
```

실제 raw 입력을 읽어 준비하려면 기존 실행기의 요청 JSON과 MinIO 환경변수를 사용한다.

```powershell
python -m pipeline.spark_experiment prepare --request data/request.json --work-dir C:/tmp/spark-exp-raw
```

각 반복은 새 컨테이너와 새 출력 디렉터리를 쓰며 실행 순서를 번갈아 바꾼다.
두 엔진에 같은 이미지 ID를 사용하고, 실행 시작 시 소스도 복사해 고정한다.
호스트/디스크 캐시는 통제하지 않는다. 다운로드·기준 계산·결과 대조 시간은 별도이며,
프로세스 시간에는 컨테이너/엔진 기동과 입력 해시 검사가 포함된다. 단계별 시간도 따로 기록한다.

출력은 `experiment.json` 옆의 `b-<식별자>/`에 생성한다.

- `summary.json`: 자원 제한, 반복별 순서, 프로세스 시간, 비교 결과와 비율
- `rN-baseline/report.json`, `rN-spark/report.json`: 단계별 시간과 계산 결과, 코드 해시
- `rN-*.log`: 실제 실행 로그
- `compare-N/`: 행 비교를 위한 정규화 파일

서비스 및 품질 Parquet 22개 그룹을 비교한다. NULL과 0, 중복 행 개수, 스키마를 구별하고
JSON 객체 키 순서·열 순서·명시적인 UTC timestamp 표현 차이만 정규화한다.
결과가 다르면 실행을 실패 처리하고 속도 비율을 유효한 수치로 제공하지 않는다.
실행기는 cgroup CPU 시간, 메모리(current/peak 및 anon/file/kernel 구분), 디스크 입출력과
Spark event log의 단계별 셔플·스필을 기록한다. 누락된 측정값은 NULL이다.
분산 worker는 각 EC2에서 별도 monitor를 실행해야 한다. host network의 트래픽은
호스트 전체 범위이며 실험 전용 수치로 해석하지 않는다.
작은 fixture 결과는 운영 속도 향상을 입증하지 않는다.

## 운영 두 노드 실험 준비

현재 운영 구성은 `deploy/prod/README.md`를 따른다. data 노드의 driver/worker1과 app 노드의 worker2가
서로 다른 호스트에 있으므로 driver의 로컬 파일 경로만 전달하면 안 된다.
입력/출력에는 공통 MinIO의 `s3a://` 경로를 쓰고, 코드와 Node 런타임은 같은 경로로 두 worker에 제공해야 한다.

```powershell
python -m pipeline.spark_experiment cluster-bundle --manifest C:/tmp/spark-exp-01/i/experiment.json --output-dir C:/tmp/spark-cluster-bundles
```

이 명령은 업로드나 서버 실행을 하지 않고 입력 파일·코드·실행 스크립트를 로컬에 묶는다.
묶음의 README와 `launch_cluster.sh`에 환경변수, read-only mount 및 자원 설정이 기록된다.
스크립트를 나중에 실행하면 입력을 `pickage-curated/experiments/<고유 ID>/`에 복사하고
Spark standalone **client mode** 작업을 제출한다. 기존 운영 Curated 경로에는 게시하지 않는다.
실패한 묶음의 출력에 덮어쓰지 않고 새로운 묶음을 준비한다.

운영 Spark 3.5.3/Hadoop 3.3.4의 기존 S3A endpoint·path style·자격증명 설정을 유지한다.
driver와 executor의 Python 버전, 코드 경로, Node/semver/npm-package-arg 경로가 같아야 한다.
로컬 비교 이미지는 Spark 3.5.7/Python 3.11/Java 17이므로 운영 호환성과 두 노드 성능은 별도 확인 대상이다.
이번 준비는 운영 배포 파일이나 컨테이너를 수정하지 않는다.

## 로컬 두 worker 런타임 스모크

후속 실제 EC2 검증은 `runtime/ec2_smoke.py`, 단기 launcher `runtime/ec2_launch.py`,
서비스 감시/실험 중단 도구 `runtime/ec2_guard.py`를 사용했다. 기존 app/data 배포는 유지하고
별도 실험 master/worker를 실행했다. 이 파일들의 host/port/run ID는 해당 단기 실행에 고정되어
있으므로 자동 운영 실행기로 사용하지 않는다. 재실행 전에는 새 run ID/빈 경로, 포트 가용성,
운영 작업과 서비스 상태를 다시 확인해야 한다. 이전 결과에 덮어쓰지 않는다.
실측 결과와 실패/복구 이력은 `docs/worklogs/raw-to-curated-pipeline/06-bounded-ec2-runtime.md`에 있다.
두 EC2의 runtime/shuffle 검증은 통과했으며 실제 raw 성능 비교는 별도다.

`runtime/compose.local.yaml`은 로컬 Docker 전용 standalone 클러스터다. `master`, `worker1`,
`worker2`는 내부 네트워크에서만 통신하며 포트를 호스트에 공개하지 않는다. 공통 실험 이미지에
CPU/메모리 상한을 적용하고 swap은 허용하지 않는다. driver는 `smoke` 프로필에서만 실행한다.
코드 한 파일만 읽기 전용으로 mount하고, JSON 증거 파일을 쓰는 전용 출력 폴더만 쓰기 가능하다.
입력 데이터, 사용자 홈, Docker socket, 자격증명, MinIO는 연결하지 않는다.

이번 공통 런타임은 Spark 3.5.3 / Python 3.11 / Java 17 / Node 24다.
`runtime/images.lock.json`에 amd64 베이스 이미지 digest를 고정했고, 아래 빌드 도구는 Docker Desktop의
로컬 named pipe를 확인한 뒤 빈 build context로 별도 태그를 만든다. 기존 `:local` 이미지와
Dockerfile 기본 Spark 3.5.7 설정은 유지한다. apt 및 pip 전이 의존성은 빌드 시 결정되므로 비교할 때는
반드시 완성된 이미지 ID를 고정한다. 서버 배포/실행은 이 도구의 범위에 포함되지 않는다.

```powershell
& ./pipeline/spark_experiment/runtime/build.local.ps1
```

그 다음 저장소 루트 PowerShell에서 아래처럼
명시적으로 Docker Desktop Linux context와 이미지 tag를 지정해 실행한다. 출력 디렉터리는 새 경로여야
하며, compose는 자동으로 시작되지 않는다.

```powershell
$env:EXPERIMENT_IMAGE = docker --context desktop-linux image inspect pickage-spark-experiment:runtime-3.5.3 --format '{{.Id}}'
$env:EXPERIMENT_OUTPUT_DIR = "C:/tmp/spark-local-cluster-evidence"
New-Item -ItemType Directory -Path $env:EXPERIMENT_OUTPUT_DIR
$compose = "pipeline/spark_experiment/runtime/compose.local.yaml"
docker --context desktop-linux compose -p pickage-runtime-local-20260915 -f $compose up -d --wait master worker1 worker2
docker --context desktop-linux compose -p pickage-runtime-local-20260915 -f $compose --profile smoke run --rm driver
Get-Content "$env:EXPERIMENT_OUTPUT_DIR/cluster-smoke.json"
docker --context desktop-linux compose -p pickage-runtime-local-20260915 -f $compose down --remove-orphans
```

두 파티션의 barrier stage가 함께 실행되므로 worker가 모자라면 Spark가 작업을 실패 처리한다.
성공 증거의 `distinct_workers_observed`는 2 이상이어야 하며 `worker_hostnames`에 두 executor
컨테이너의 호스트명이 기록된다. `runtime_versions`에는 각 worker의 Python·Java·Node 버전이,
`node_semver_passed`에는 Node.js가 `semver.valid('1.2.3')`를 성공 호출했는지가 기록된다.
이 스모크는 런타임 배치만 검증하며 실제
고정 입력의 전처리 결과, 성능, 운영 호환성 또는 서버 네트워크를 검증하지 않는다.

운영 실험에서는 동일 입력으로 baseline 1대, Spark local 1대, Spark 두 노드를 각각 비교하고,
코어·메모리·스필·executor 배치·MinIO 트래픽을 함께 기록해야 한다. 노드 수가 다른 결과를
엔진 자체의 성능 차이라고 단정하지 않는다. S3 업로드 완료만으로 게시 완료를 판단하지 않고,
모든 단계의 보고서와 결과 대조를 확인한 후 별도 판단한다.

설계 참고: [Spark 제출 및 Python 배포 모드](https://spark.apache.org/docs/3.5.8/submitting-applications.html),
[Spark 배열 필터 API](https://spark.apache.org/docs/3.5.8/api/python/reference/pyspark.sql/api/pyspark.sql.functions.filter.html).
공식 3.5 계열 문서 확인, 로컬 3.5.7 실행, 별도 3.5.3 이미지의 두 EC2 runtime/shuffle
스모크를 구분한다. 실제 raw 성능 비교는 아직 실행하지 않았다.

## 실제 raw 고정과 측정 준비

`freeze_raw`는 raw 객체를 실험 전용 MinIO prefix와 data EC2 로컬 파일에 복사하고
모든 객체의 SHA-256을 검증한다. 전처리는 실행하지 않는다. 작업 이력과 실제 입력 identity는
`docs/worklogs/raw-to-curated-pipeline/07-real-input-and-telemetry.md`에 기록한다.

`prepare-frozen --manifest <raw-inputs.json> --work-dir <새 경로>`는 고정된 로컬 raw만
읽으며 기존 전처리를 실행해 5개 단계의 기준 입력을 만든다. 따라서 이 명령부터 실제 계산이다.
raw 고정 완료와 5개 단계의 기준 입력 생성 완료를 혼동하지 않는다.

각 서버에서 실험 컨테이너의 정확한 이름과 `pickage.experiment` 라벨을 지정해 측정한다.
모니터는 Docker daemon을 조회할 권한 및 해당 cgroup/proc 읽기 권한이 필요하다.

```bash
sudo env PYTHONPATH="$CODE_ROOT" python3 -m pipeline.spark_experiment.runtime.monitor_container \
  --container "$EXACT_CONTAINER_NAME" --run-id "$RUN_ID" \
  --output "$NEW_METRICS_DIRECTORY" --duration-seconds 3600
```

data의 driver/master/worker와 app의 worker 각각에 실행한다. 컨테이너 교체·종료 시 측정을
끝내며 기존 출력에 덮어쓰지 않는다. 모니터는 컨테이너를 중단하지 않는다. 서비스 감시 및
실험 중단은 별도의 `ec2_guard.py` 역할이다. 작업 제출 전 모든 모니터의 첫 샘플을 확인한다.
실험 전용 컨테이너를 새로 만들어 누적 CPU/메모리 peak 범위를 이전 작업과 분리한다.

`job --telemetry-dir <새 로컬 경로>`는 `samples.json`, Spark `events/`, 종료 후 최종
`report-with-telemetry.json`을 남긴다. S3의 report는 Spark 종료 전 기록이며 최종 측정은
이 로컬 companion 보고서를 사용한다. Spark 이벤트는 `telemetry.parse_event_log(path)`로
집계한다. 불완전 로그/누락 지표를 0으로 채우지 않는다. worker 측정의 CPU 시간은 합산하되,
메모리는 같은 시각의 합계와 컨테이너별 peak를 구분한다.

자원 상한 비교안은 `evidence/real-input-preparation/resource-profile.json`에 있다.
전체 raw의 메모리 적합성, MinIO S3A 실제 전처리 실행과 성능은 후속 실험에서 확인한다.
