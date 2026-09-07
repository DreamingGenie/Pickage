# 로컬 개발 환경

리포 루트에서 실행한다. compose 파일은 `compose.yaml` 하나다.

```bash
docker compose --profile api  up     # postgres + api
docker compose --profile data up     # minio + spark
docker compose --profile all  up     # 전부
```

매번 `--profile` 붙이기 번거로우면 `cp .env.example .env` 후 작업에 맞는 프로파일을 적어 두면
`docker compose up` 만으로 뜬다. (`.env` 는 커밋되지 않으므로 각자 취향대로 두면 된다)

## 데이터 파트는 첫 실행 전 준비가 하나 있다

MinIO 자격증명은 커밋하지 않는다. 각자 만든다.

```bash
cp pipeline/minio/.env.example pipeline/minio/.env
# MINIO_ROOT_PASSWORD 를 임의 값으로 채운다
```

## 접속 정보

Postgres·API 값은 로컬 전용이라 커밋되어 있다. **운영 서버 자격증명과 절대 같게 두지 말 것.**
전부 `127.0.0.1` 에만 열려 있어 같은 네트워크의 다른 사람은 접근할 수 없다.

| | 주소 | 계정 |
| --- | --- | --- |
| API | http://localhost:8080/swagger-ui/index.html | |
| Postgres | `localhost:15432` | `postgres` / `pickage` |
| MinIO | `http://localhost:9000` | `pipeline/minio/.env` 의 값 |
| MinIO 콘솔 | http://localhost:9001 | 위와 같음 |

버킷 5종은 `minio-init` 이 기동 시 **없는 것만** 만든다. 기존 버킷과 객체는 유지된다.
`minio-init` 이 `Exited (0)` 인 것은 초기화 성공을 뜻한다.

`pickage-raw` · `pickage-curated` · `pickage-vectors` · `pickage-mlflow-artifacts` · `pickage-quarantine`

버킷별 역할은 [pipeline/minio/README.md](../../pipeline/minio/README.md) 참고.

## ⚠ 초기화 — `down -v` 를 쓰지 말 것

`docker compose down -v` 는 **MinIO 에 적재한 원본까지 지운다.** 재수집에 로컬 원본 수십 GB 가 필요하다.

```bash
docker compose --profile all down       # 내린다. 데이터는 남는다
docker compose --profile all stop       # 컨테이너만 멈춘다
```

DB 만 초기화해야 하면 볼륨을 지정해서 지운다.

```bash
docker compose --profile api down
docker volume rm pickage-local_pgdata
```

> 스키마 변경은 대부분 이게 필요 없다. 마이그레이션이 자동으로 맞춰 준다.

## Spark

```bash
docker compose exec spark pyspark
docker compose exec spark spark-submit /opt/work/작업파일.py
```

`pipeline/` 이 컨테이너의 `/opt/work` 로 마운트된다. 호스트에서 고치면 바로 반영된다.

**s3a 설정과 자격증명은 이미 되어 있다.** 코드에 config 를 쓰지 않아도 된다.

```python
spark = SparkSession.builder.master("local[*]").getOrCreate()
spark.read.parquet("s3a://pickage-raw/...")
```

자격증명은 `pipeline/minio/.env` 를 그대로 물려받는다. `spark-env.sh` 가 `MINIO_ROOT_*` 을
s3a 가 읽는 `AWS_*` 이름으로 바꿔 주므로 `.env` 에 같은 값을 두 번 적지 않아도 된다.

## 지켜야 할 것 두 가지

**1. 경로는 `key=value/` 로 쓴다.**

```
s3a://pickage-raw/npm/downloads/collected_date=2026-09-07/
```

이렇게 쓰면 Spark 가 `collected_date` 를 컬럼으로 자동 인식한다.
그냥 `2026-09-07/` 로 쓰면 파일명을 파싱하는 코드를 매번 써야 하고 파티션 프루닝도 안 된다.

**2. 버킷 이름에 언더스코어를 쓰지 않는다.** `pkg_vectors`(X) → `pickage-vectors`(O)

s3a 와 일부 SDK 가 거부한다. 데이터가 들어간 뒤에는 이름을 못 바꿔 전부 복사해야 한다.

## boto3

```python
s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    config=boto3.session.Config(s3={"addressing_style": "path"}),   # 필수
)
```

`addressing_style="path"` 가 없으면 연결되지 않는다. 기본값은 `http://버킷명.endpoint/`
형태로 붙는데 MinIO 는 그 주소로 응답하지 않는다. Spark 의 `path.style.access=true` 와 같은 이유다.

## 막히면

| 증상 | 원인 |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker Desktop 이 꺼져 있다. `docker info` 로 확인 (`docker --version` 은 데몬이 죽어도 답한다) |
| `up` 했는데 아무것도 안 뜸 | `--profile` 을 빠뜨렸다 |
| `env file ... not found` | `pipeline/minio/.env` 가 없다. 위 "첫 실행 전 준비" 참고 |
| `Port 8080 already in use` 인데 브라우저는 뜸 | 이전 앱 프로세스가 남아 있다. `netstat -ano \| findstr :8080` |
| `NoSuchMethodError` (Spark) | `hadoop-aws` 버전 불일치 (아래) |
| MinIO 연결 실패 | `path.style.access` / `addressing_style` 누락 |
| s3a 에서 403 · `AccessDenied` | `pipeline/minio/.env` 를 바꾼 뒤 spark 컨테이너를 재기동하지 않았다 |
| 셸 스크립트가 컨테이너에서 깨짐 | CRLF. 루트 `.gitattributes` 가 막아 주지만, 이미 받은 파일은 다시 체크아웃해야 한다 |
| `.env` 를 고쳤는데 안 먹음 | **셸 환경변수가 `.env` 보다 우선한다.** `echo $COMPOSE_PROFILES` 로 확인 |
| `.env` 에 키를 넣었는데 앱이 못 읽음 | 루트 `.env` 는 compose 파일 해석에만 쓰인다. 컨테이너로 넘기려면 `env_file:` 또는 `environment:` 가 필요하다 |
| PowerShell 에서 `curl` 이 이상함 | PowerShell 의 `curl` 은 `Invoke-WebRequest` 별칭이다. `curl.exe` 를 쓰거나 Git Bash |
| Git Bash 에서 `/opt/...` 가 `C:\...` 로 바뀜 | `MSYS_NO_PATHCONV=1` 을 앞에 붙인다 |

## 버전을 고정한 이유

올리기 전에 읽을 것.

| 대상 | 버전 | 이유 |
| --- | --- | --- |
| `apache/spark` | `3.5.3-python3` | 내장 Hadoop 이 3.3.4 |
| `hadoop-aws` | `3.3.4` | **Spark 내장 Hadoop 과 정확히 같아야 한다.** 어긋나면 `NoSuchMethodError` 로 죽고 원인이 드러나지 않는다 |
| `minio/minio` | 다이제스트 고정 | 태그는 같은 이름으로 재발행될 수 있다 |
| `postgres` | `16` | 운영 서버와 같은 메이저 버전 |

Spark 를 올리면 `hadoop-aws` 도 같이 맞춘다. 내장 버전 확인:

```bash
docker run --rm apache/spark:<태그> ls /opt/spark/jars | grep hadoop-client-api
```

설정 파일은 `deploy/local/spark/` 아래에 있다.

## 프로젝트 이름

컨테이너·볼륨 이름의 접두사다.

| 환경 | 이름 | 예 |
| --- | --- | --- |
| 로컬 | `pickage-local` | `pickage-local-api-1`, `pickage-local_minio-data` |
| 운영 | `pickage-prod` | `pickage-prod-api-1` |

이름이 환경을 드러내므로, 운영 compose 를 실수로 로컬에서 띄우면 `docker ps` 에서 바로 보인다.

**이 이름을 바꾸면 볼륨 이름도 같이 바뀌어 기존 데이터가 고아 볼륨으로 남는다.**
증상이 "컨테이너는 정상인데 데이터만 없음" 으로 나타나 원인 찾기 어렵다.
