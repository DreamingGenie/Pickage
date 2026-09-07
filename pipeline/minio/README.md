# Pickage local MinIO

## MinIO를 사용하는 이유

MinIO는 S3 API로 파일을 저장하고 조회하는 객체 저장소다.
Pickage에서는 수집한 원본 Parquet와 이후 전처리·분석 결과를 보관하는 용도로 사용한다.
PostgreSQL의 테이블처럼 행을 직접 조회·수정하는 저장소가 아니라,
Parquet나 모델 파일을 객체 단위로 보관하는 저장소다.

- **원본 보존과 재사용**: 기존에 수집한 deps.dev Parquet를 보관해,
  전처리 규칙이 바뀌어도 BigQuery에서 다시 수집하지 않고 재처리할 수 있다.
- **원본과 결과 분리**: 원본은 그대로 두고 정제 결과·벡터·모델 산출물을 구분해 관리한다.
- **실행 결과 추적**: 데이터셋·스냅샷·실행 ID별 경로와 manifest로
  어떤 원본을 입고했는지, 검증이 완료됐는지 확인한다.
- **후속 처리의 입력 저장소**: 향후 Spark 등이 로컬 파일 경로 대신
  접근 가능한 객체 저장소 경로를 입력으로 사용하도록 준비한다.
  현재는 로컬 구성만 완료했으며, 여러 서버에서의 접근 설정과 Spark 연동은 아직 없다.

PostgreSQL에는 향후 서비스 조회에 필요한 `package`, `version` 등의 데이터를 적재하고,
MinIO에는 그 데이터를 만드는 원본과 중간·최종 파일을 보관할 예정이다.
MinIO를 실행하는 것만으로 전처리나 PostgreSQL 적재가 수행되지는 않는다.

## 버킷의 역할

버킷은 객체를 담는 최상위 저장 단위다. 버킷 안에서는 객체 이름의 경로(prefix)로
데이터셋과 실행 결과를 구분한다. 아래 역할은 Pickage의 저장 용도 구분이며,
현재 버킷별 접근 권한이나 보존 기간이 자동 설정되는 것은 아니다.

| 버킷 | 역할 | 저장 대상 | 현재 상태 |
| --- | --- | --- | --- |
| `pickage-raw` | Bronze 원본 보관 | 수집된 Parquet 원본, 원본·검증 manifest, 완료 표시 | deps.dev 데이터 입고 완료 |
| `pickage-curated` | 정제·가공 데이터 보관 | `package`·`version` 적재용 Parquet, ID 매핑, 품질 검증 결과 | 2026-08-31 스냅샷 전처리·저장·재검증 완료; [Curated 안내](../curated/README.md) 참고 |
| `pickage-vectors` | 벡터 산출물 보관 | 향후 패키지 임베딩과 패키지·모델 버전 연결 정보 | 버킷 생성만 완료; 벡터 생성·검색 연동 미구현 |
| `pickage-mlflow-artifacts` | 학습·실험 산출물 보관 | 향후 MLflow의 모델 파일, 평가 보고서 등 | 버킷 생성만 완료; MLflow 연동 미구현 |
| `pickage-quarantine` | 검증 실패 데이터 격리 | 향후 오류 레코드와 실패 사유 등 조사 대상 | 버킷 생성만 완료; 자동 격리 미구현 |

`pickage-vectors`는 벡터 파일 보관용이지 벡터 검색 엔진 자체가 아니다.
`pickage-mlflow-artifacts`도 MLflow 서비스나 실험 메타데이터 DB를 대신하지 않는다.
현재 입고 스크립트는 검증 실패 시 오류로 종료하며, 실패 데이터를
`pickage-quarantine`으로 자동 이동하지 않는다.

## 현재 진행 상황

2026-09-07 확인 기준이다. 아래 입고 수치는 저장된 검증 manifest 기준이며,
이 문서 작성 시 전체 객체의 해시를 다시 계산한 결과는 아니다.

- [x] 루트 Compose에서 로컬 MinIO 실행 및 데이터 볼륨 관리
- [x] MinIO 준비 완료 후 없는 버킷만 자동 생성
- [x] 원본 사전 검증, 병렬 업로드, 업로드 후 SHA-256 비교 구현
- [x] 동일 실행 ID 재개 및 기존 객체 내용 불일치 시 실패 처리
- [x] deps.dev Bronze 데이터 입고 완료
- [x] `package`·`version` Curated 전처리 구현 및 로컬 전체 데이터 저장·재검증
- [ ] PostgreSQL 적재
- [ ] Spark·벡터 생성·MLflow 연동
- [ ] 서버 배포, 권한 분리, 백업 및 자동 스케줄링

입고 실행 ID: `bronze-20260907-v1`

| 항목 | 확인 결과 |
| --- | --- |
| 데이터셋 | `projects`, `pkg_project`, `requirements`, `versions_full` |
| 데이터셋별 스냅샷 묶음 | 총 232개 |
| Parquet 파일 | 3,231개 |
| 파일 크기 합계 | 33,443,300,362바이트 (약 33.44GB) |
| 원본 행 수 합계 | 1,098,457,021행 |
| 검증 상태 | 모든 run manifest가 `PASSED`, `GET_SHA256_ALL_FILES` |
| 완료 표시 | `_SUCCESS` 232개 |

행 수 합계는 서로 다른 데이터셋의 행을 합한 값이며, 패키지 수를 의미하지 않는다.
원본 파일과 실제 `.env`는 Git에 포함하지 않는다.

Curated 전처리는 위 Bronze 중 `2026-08-31` 스냅샷의 `versions_full`과
`requirements`를 입력으로 사용한다. 릴리스·배포일 필터, 패키지 ID 유지,
대표 저장소 선정, 표시용 의존성 JSON 변환을 수행한다.
실행 명령과 실제 검증 결과는 [Curated README](../curated/README.md)에 별도로 정리한다.
품질 사유 파일은 해당 Curated 실행의 `quality/`에 기록하며,
Bronze 원본을 변경하거나 `pickage-quarantine`으로 이동하지 않는다.
`curated-20260907-v2`에서 package 11,080,940행과 version 54,188,349행을 생성했고,
관리·품질 파일을 포함해 Parquet 44개(약 4.85GB)를 저장했다.

## 로컬 실행

Docker Desktop의 Linux engine을 사용한다. 저장 데이터는 Docker named volume
`pickage-local_minio-data`에 유지된다. API/console은 localhost에만 공개한다.

이 디렉터리의 `.env`에 `.env.example`의 변수와 별도 비밀번호를 설정한다.
`.env`는 Git에서 제외된다.

```powershell
docker compose -f docker-compose.local.yaml up -d
docker compose -f docker-compose.local.yaml ps -a
```

- Console: http://localhost:9001
- S3 API: http://localhost:9000
- 로그인: 로컬 `.env`의 값

프로젝트 루트의 `docker-compose.local.yaml`에서 로컬 서비스를 관리한다.
위 명령은 프로젝트 루트에서 실행한다.
MinIO가 healthy 상태가 되면 `minio-init`이 `init-buckets.sh`를 실행해
위 5개 버킷 중 없는 버킷만 생성한다. 기존 버킷과 객체는 유지한다.
일회성 서비스인 `minio-init`의 `Exited (0)` 상태는 초기화 성공을 뜻한다.
초기화 로그는 `docker compose -f docker-compose.local.yaml logs minio-init`으로 확인한다.
중지는 `docker compose -f docker-compose.local.yaml stop`으로 한다.
`down -v`는 저장 데이터를 삭제하므로 사용하지 않는다.

## Bronze 입고 실행

원본 Parquet는 MinIO 기동과 별개의 입고 작업으로 `pickage-raw`에 복사한다.
로컬 `data/raw`에 원본 Parquet와 `_MANIFEST.json`이 있어야 한다.
아래 명령도 프로젝트 루트에서 실행한다.

```powershell
.venv-bq/Scripts/python.exe -m pip install -r pipeline/minio/requirements.txt
.venv-bq/Scripts/python.exe pipeline/minio/ingest_raw.py --dry-run
.venv-bq/Scripts/python.exe pipeline/minio/ingest_raw.py --run-id bronze-20260907-v1 --workers 8
```

위 실행 ID는 기존 입고를 검증·재개할 때 사용한다.
별도 입고 이력을 만들려면 새로운 실행 ID를 지정한다.
`--run-id`를 생략하면 자동 생성되므로 새 실행 경로에 복사본이 저장된다.
`--dry-run`으로 원본 manifest와 파일 수/크기/Parquet 행 수를 먼저 검증한다.
`--dataset projects --snapshot 2022-05-08`로 범위를 좁힐 수 있다.
대상은 `data/raw`의 deps.dev 데이터이며 다운로드 API 데이터는 포함하지 않는다.

`boto3`는 로컬 MinIO의 S3 API 호출에, `duckdb`는 입고 전 Parquet 메타데이터의
행 수 확인에 사용한다. DuckDB 서버를 별도로 띄우거나 MinIO 컨테이너에 설치하지 않는다.

## 저장 경로와 검증 규칙

목적지 버킷은 `pickage-raw`이며, 실행별 객체 이름은 다음과 같다.

```text
depsdev/v1/{table}/snapshot={date}/run_id={run}/
  data/*.parquet        # 수집된 Parquet 원본
  source_manifest.json # 원본 _MANIFEST.json 보존
  run_manifest.json    # 파일별 크기·SHA-256 및 입고 검증 결과
  _SUCCESS             # 해당 데이터셋·스냅샷·실행의 검증 완료 표시
```

Projects는 여러 provider의 데이터이므로 `system=npm` prefix를 사용하지 않는다.
모든 업로드 객체는 GET으로 읽어 로컬 SHA-256과 비교한다.
원본 manifest를 보존하고 검증 결과 manifest 이후 `_SUCCESS`를 기록한다.
`_SUCCESS`는 이 입고 단계의 파일 무결성 검증 완료를 뜻하며,
원본의 의미적 품질이나 후속 전처리·PostgreSQL 적재 완료를 보장하지 않는다.
실패 시 같은 run ID로 재개하면 기존 파일은 해시 검증하고 빠진 파일만 전송한다.
단, 이미 `_SUCCESS`가 있는 실행에서 파일이 누락돼 있으면 자동 복구하지 않고 실패한다.
기존 객체의 내용이 다르면 덮어쓰지 않고 실패한다. 같은 run은 동시에 실행하지 않는다.
향후 Spark 연동 시 여러 run을 한꺼번에 읽는 glob 대신 검증된 특정 run 경로를 넘긴다.

## 테스트와 운영 주의사항

```powershell
.venv-bq/Scripts/python.exe -m unittest discover -s pipeline/minio -p "test_*.py" -v
```

단위 테스트는 스트림 해시 계산, 동일 manifest 재사용,
내용이 다른 manifest의 덮어쓰기 거부를 검증한다.
실제 MinIO 업로드·버킷 생성 검증은 별도의 로컬 실행 확인이 필요하다.

named volume은 컨테이너 교체 시 데이터를 유지하기 위한 장치이지 별도 백업이 아니다.
이 구성은 로컬 단일 노드 개발용이며 서버 백업/권한 구성을 대신하지 않는다.
