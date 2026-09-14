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
CPU 사용 시간, 최고 메모리, 셔플/네트워크 바이트는 아직 측정하지 않으며 보고서에서 NULL로 표시한다.
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

운영 실험에서는 동일 입력으로 baseline 1대, Spark local 1대, Spark 두 노드를 각각 비교하고,
코어·메모리·스필·executor 배치·MinIO 트래픽을 함께 기록해야 한다. 노드 수가 다른 결과를
엔진 자체의 성능 차이라고 단정하지 않는다. S3 업로드 완료만으로 게시 완료를 판단하지 않고,
모든 단계의 보고서와 결과 대조를 확인한 후 별도 판단한다.

설계 참고: [Spark 제출 및 Python 배포 모드](https://spark.apache.org/docs/3.5.8/submitting-applications.html),
[Spark 배열 필터 API](https://spark.apache.org/docs/3.5.8/api/python/reference/pyspark.sql/api/pyspark.sql.functions.filter.html).
공식 3.5 계열 문서 확인과 실제 로컬 3.5.7 실행을 구분하며, 운영 3.5.3 실행은 미검증이다.
