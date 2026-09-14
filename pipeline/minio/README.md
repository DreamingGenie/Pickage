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
| `pickage-curated` | 정제·가공 데이터 보관 | `package`·`version` 적재용 Parquet, ID 매핑, 품질 검증 결과, 빌더가 만든 파생 데이터셋 | 2026-08-31 스냅샷 전처리·저장·재검증 완료; [Curated 안내](../curated/README.md) 참고 |
| `pickage-vectors` | 벡터 산출물 보관 | 향후 패키지 임베딩과 패키지·모델 버전 연결 정보 | 버킷 생성만 완료; 벡터 생성·검색 연동 미구현 |
| `pickage-mlflow-artifacts` | 학습·실험 산출물 보관 | 향후 MLflow의 모델 파일, 평가 보고서 등 | 버킷 생성만 완료; MLflow 연동 미구현 |
| `pickage-quarantine` | 검증 실패 데이터 격리 | 향후 오류 레코드와 실패 사유 등 조사 대상 | 버킷 생성만 완료; 자동 격리 미구현 |

`pickage-vectors`는 벡터 파일 보관용이지 벡터 검색 엔진 자체가 아니다.
`pickage-mlflow-artifacts`도 MLflow 서비스나 실험 메타데이터 DB를 대신하지 않는다.
현재 입고 스크립트는 검증 실패 시 오류로 종료하며, 실패 데이터를
`pickage-quarantine`으로 자동 이동하지 않는다.

## 현재 진행 상황

2026-09-14 확인 기준이다. 아래 입고 수치는 저장된 검증 manifest 기준이며,
이 문서 작성 시 전체 객체의 해시를 다시 계산한 결과는 아니다.

- [x] 루트 Compose에서 로컬 MinIO 실행 및 데이터 볼륨 관리
- [x] MinIO 준비 완료 후 없는 버킷만 자동 생성
- [x] 원본 사전 검증, 병렬 업로드, 업로드 후 SHA-256 비교 구현
- [x] 동일 실행 ID 재개 및 기존 객체 내용 불일치 시 실패 처리
- [x] deps.dev Bronze 데이터 입고 완료
- [x] `package`·`version` Curated 전처리 구현 및 로컬 전체 데이터 저장·재검증
- [x] 서버 MinIO 기동 및 로컬에서 터널로 적재하는 경로 (2026-09-09)
- [x] ecosyste.ms keywords 원본 서버 입고 (`keywords-20260909-v1`)
- [x] 파생 데이터셋 입고 경로 (`ingest_derived.py`) — 폐기→대체 데이터셋 서버 입고 (`deprecated-replacement-20260914-v1`)
- [ ] npm registry 원본 입고 — **수집이 아직 진행 중이다.** 입고 경로는 준비되어 있고,
      `manifest.json` 의 `pending` 이 0 이 되면 실행한다
- [ ] PostgreSQL 적재
- [ ] Spark·벡터 생성·MLflow 연동
- [ ] 권한 분리(서비스 계정), 백업 및 자동 스케줄링

서버 MinIO는 루트 자격증명 하나를 함께 쓰는 상태다. 버킷별 권한을 가른 서비스 계정은
아직 없다. 지금은 적재하는 사람이 곧 버킷 전체를 지울 수 있는 사람과 같다.

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

파생 데이터셋은 `deprecated-replacement-20260914-v1` 로 폐기→대체 데이터셋
Parquet 1개(2,839,460바이트·28,241행)를 서버 `pickage-curated` 에 넣었다. 같은 실행 ID로
재실행해 객체가 늘지 않고 해시 재검증만 통과하는 것을 확인했다. 같은 버킷의
`migration-pairs-20260909-v1`(Parquet 3개)은 이 경로가 생기기 전에 손으로 올린 것이라
`run_manifest.json` 형태가 조금 다르다.

수집기 원본은 `keywords-20260909-v1` 로 ecosyste.ms keywords 수집일 `2026-09-08` 을
서버 `pickage-raw` 에 넣었다. gzip JSONL 1,000개(184,154,394바이트)에 관리 파일 3개를
더해 1,003객체이며, 원본 manifest 기준 1,000/1,000페이지·100만 행이다. 같은 실행 ID로
재실행해 객체 수가 늘지 않고 전량 해시 검증만 통과하는 것을 확인했다.

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

## 서버 MinIO 로 적재하기

여기까지는 전부 로컬 이야기다. 서버(`data` 노드)의 MinIO에 넣으려면 두 가지가 필요하다 —
SSH 터널과 별도 자격증명 파일이다.

서버 MinIO는 **외부에 열린 포트가 없다.** S3 API 9000·콘솔 9001 모두 루프백에만
묶여 있어 터널로만 닿는다. 서버 구성은 [deploy/prod/data/README.md](../../deploy/prod/data/README.md)를 본다.

### 1. 터널을 연다 — 내 PC 쪽 입구를 19000 으로 낸다

```bash
ssh -i ~/.ssh/J15A506T.pem -N -L 19000:localhost:9000 ubuntu@j15a506a.p.ssafy.io
```

**19000 은 서버 포트가 아니라 내 PC 의 포트다.** `-L` 의 두 번호는 기준점이 다르다.

```text
-L 19000:localhost:9000
   └─┬─┘ └────┬───────┘
     │        └── 서버에서 봤을 때의 목적지. 서버 자신의 9000
     └── 내 PC 에 여는 입구 번호

내 코드 → localhost:19000 ─[SSH 터널]─→ 서버의 localhost:9000 → MinIO
          (내 PC)                        (서버. 여기는 9000 그대로다)
```

**서버 설정은 아무것도 바꾸지 않는다.** 바꾸는 것은 내 PC 안에서 서버로 가는 입구의
번호뿐이고, 그 번호가 로컬 MinIO 의 9000 과 겹치지 않는 것이 이 구성의 핵심이다.

| 내 PC 의 주소 | 실제로 닿는 곳 |
| --- | --- |
| `localhost:9000` | 내 PC 의 Docker MinIO |
| `localhost:19000` | 터널 → 서버 MinIO |

입구도 9000 으로 잡으면 두 가지 일이 생긴다. 로컬 MinIO 가 떠 있으면 포트가 이미
점유되어 **터널이 아예 안 열린다**(`bind [127.0.0.1]:9000: Address already in use`).
꺼져 있으면 터널은 열리지만, 이제 `localhost:9000` 이 터널인지 로컬 MinIO 인지
**구분할 방법이 없다.** 나중에 터널 없이 로컬 MinIO 만 켜고 적재를 돌리면 주소가 같으니
**아무 오류 없이 로컬로 들어간다.** 서버에 넣은 줄 알고 넘어가고 한참 뒤에 드러난다.

19000 으로 갈라 두면 그 애매함이 없다. 로컬 MinIO 가 쓰지 않는 번호라서, 응답이 있으면
터널이 열린 것이고 없으면 그 자리에서 연결이 거부된다. 안전이 사람의 기억이 아니라
포트 번호에 걸려 있게 된다.

숫자 자체는 임의다. 조건은 **로컬에서 쓰지 않는 번호** 하나뿐이다. 다만 사람마다 다른
번호를 쓰면 이 문서와 각자의 `.env.server` 가 갈라지므로 팀에서 19000 으로 통일한다.

터널은 창을 닫으면 끊긴다. 적재가 끝날 때까지 열어 둔다.

### 2. 자격증명 파일을 만든다

```bash
cp pipeline/minio/.env.server.example pipeline/minio/.env.server
```

값은 서버에서 돌고 있는 컨테이너에서 꺼낸다. 따로 발급받을 필요가 없다.

```bash
ssh -i ~/.ssh/J15A506T.pem ubuntu@j15a506a.p.ssafy.io   'docker inspect pickage-data-minio-1 --format "{{range .Config.Env}}{{println .}}{{end}}" | grep MINIO_ROOT'
```

`.env.server` 는 `.gitignore` 가 막는다(`.env.*` 전체를 막고 `.example` 만 예외로 둔다).
**로컬 `.env` 에 서버 값을 넣지 말 것** — 그 파일은 루트 compose 가 로컬 컨테이너를
띄울 때 함께 읽는다.

### 3. 대상을 지정해 실행한다

환경변수로 자격증명 파일을 고른다. 지정하지 않으면 로컬이다.

```powershell
$env:PICKAGE_MINIO_ENV=".env.server"
```

```bash
export PICKAGE_MINIO_ENV=.env.server
```

이제 이 문서의 입고·적재 명령이 그대로 서버를 향한다. `pipeline/curated/build.py`와
`pipeline/postgresql/load.py`도 같은 `client()` 를 쓰므로 함께 바뀐다.

실행할 때마다 첫 줄에 붙은 곳이 찍힌다. **로그에서 이 줄을 먼저 볼 것.**

```text
PICKAGE_S3_ENDPOINT=http://localhost:19000 (.env.server)
```

로컬로 돌아가려면 변수를 지운다 (`Remove-Item Env:PICKAGE_MINIO_ENV` / `unset PICKAGE_MINIO_ENV`).

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

## 파생 데이터셋 입고 실행

`pipeline/duckdb/build_*.py` 가 원본에서 계산해 낸 작은 데이터셋은 `pickage-raw` 가 아니라
`pickage-curated` 에 넣는다. 원본이 아니라 원본을 가공한 결과이기 때문이다.

```powershell
$env:PICKAGE_MINIO_ENV=".env.server"
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset deprecated-replacement --dry-run
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset deprecated-replacement --run-id deprecated-replacement-20260914-v1
```

`--dataset` 에 넣을 수 있는 값과 각 데이터셋의 로컬 경로·설명·Jira 키는
`ingest_derived.py` 의 `DATASETS` 에 있다. 빌더를 먼저 돌려 Parquet 을 만들어 둬야 한다.

**재생성할 수 있는데 왜 올리나.** 빌더는 `data/raw` 의 수십 GB Parquet 을 그대로 들고 있는
PC 에서만 돈다. 그 PC 가 사라지면 git 의 CSV 만 남고, 그것을 만든 계산은 복원할 수 없다.

`run_manifest.json` 에는 업로드 시각을 넣지 않는다. 같은 실행 ID 로 다시 돌리면 만들어지는
manifest 가 이미 올라간 것과 한 바이트도 다르지 않아야, 덮어쓰기 대신 **전량 해시 재검증**으로
통과한다. 시각이 들어가면 재검증 자체가 실패한다.

## 수집기 원본 입고 실행

deps.dev 스냅샷은 위의 `ingest_raw.py` 가 맡는다. API 수집기(ecosyste.ms keywords,
npm registry)의 원본은 `ingest_collector_raw.py` 로 넣는다. 둘을 가른 이유는 원본의
형태가 다르기 때문이다 — 수집기 쪽은 `data/<소스>/raw/run=<날짜>/` 에 gzip JSONL 조각과
수집기가 직접 쓴 `manifest.json` 이 함께 있다. 업로드·검증 규칙은 같은 것을 쓴다.

```powershell
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_collector_raw --source keywords --dry-run
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_collector_raw --source keywords --run 2026-09-08 --run-id keywords-20260909-v1 --workers 8
```

`--source` 는 `keywords` 와 `registry` 를 받는다. `--run` 으로 수집일을 지정하고,
생략하면 **날짜 형태의 run 만** 쓸어 담는다.

### 미완료 수집은 입고되지 않는다

수집기의 `manifest.json` 을 읽어 **수집이 끝났는지 먼저 판정한다.** 끝나지 않았으면
그 자리에서 실패한다.

| 소스 | 완료 조건 |
| --- | --- |
| `keywords` | `final: true` 이고 `pages_done == pages_planned` |
| `registry` | `final: true` 이고 `tasks_by_status.pending == 0` |

`final` 만으로는 부족하다. 수집기가 체크포인트마다 manifest 를 다시 쓰기 때문에
진행 중에도 파일은 늘 존재한다. 진행 카운터가 **없는** manifest 도 완료로 보지 않는다 —
형태가 다른 manifest 를 "빠진 값 = 문제 없음" 으로 읽으면 부분 수집이 그대로 통과한다.

부분 수집을 올리면 `_SUCCESS` 가 함께 기록되어 **나중에 검증된 완전한 원본으로 읽힌다.**
그 뒤로는 아무도 의심하지 않는다. 그래서 여기서 막는다.

### 스모크 런은 쓸어 담지 않는다

시험 실행(`run=smoke-2026-09-08`)이 실제 수집 폴더와 같은 자리에 남는다.
`--run` 없이 돌리면 날짜 형태만 고르므로 시험 데이터가 섞여 들어가지 않는다.
굳이 올리려면 `--run smoke-2026-09-08` 처럼 이름을 대야 한다.

`pickage-raw` 는 수집 원본이 사는 버킷이다. 시험 데이터가 한 번 들어가면
나중에 그것이 무엇이었는지 아무도 기억하지 못한다.

## 저장 경로와 검증 규칙

목적지 버킷은 `pickage-raw`이며, 실행별 객체 이름은 다음과 같다.

```text
depsdev/v1/{table}/snapshot={date}/run_id={run}/
  data/*.parquet        # 수집된 Parquet 원본
  source_manifest.json # 원본 _MANIFEST.json 보존
  run_manifest.json    # 파일별 크기·SHA-256 및 입고 검증 결과
  _SUCCESS             # 해당 데이터셋·스냅샷·실행의 검증 완료 표시
```

빌더가 만든 파생 데이터셋은 `pickage-curated` 의 다음 경로에 넣는다. 관리 파일에
`source_manifest.json` 이 없는 것은 원본 manifest 를 물려받을 원본이 없기 때문이고,
대신 `run_manifest.json` 에 빌더 경로·원천·Jira 키·주의사항을 적는다.

```text
depsdev/v1/{dataset}/snapshot={date}/run_id={run}/
  data/*.parquet        # 빌더 산출물
  run_manifest.json     # 파일별 크기·행 수·SHA-256, 빌더·원천·README 위치, notes
  _SUCCESS              # 해당 데이터셋·스냅샷·실행의 검증 완료 표시
```

수집기 원본은 소스별로 다음 경로에 넣는다. 검증 규칙과 관리 파일은 위와 같다.

```text
ecosystems-keywords/v1/collected_date={date}/run_id={run}/
npm-registry/v1/collected_date={date}/run_id={run}/
  data/part-*.jsonl.gz  # 수집된 gzip JSONL 원본
  source_manifest.json  # 수집기 manifest.json 보존
  run_manifest.json     # 파일별 크기·SHA-256 및 입고 검증 결과
  _SUCCESS              # 해당 수집일·실행의 검증 완료 표시
```

수집기의 체크포인트 DB(`checkpoint.sqlite`)와 로그는 올리지 않는다. 수집기가 도는 동안
계속 바뀌는 작업 상태이지 원본이 아니다. `npm-downloads/v1/` 은 별도 입고 경로가 맡는다
([pipeline/downloads](../downloads/)).

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
