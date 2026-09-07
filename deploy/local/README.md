# 로컬 개발 환경

리포 루트에서 실행한다.

```bash
docker compose --profile api  up     # postgres + api
docker compose --profile data up     # minio + spark
docker compose --profile all  up     # 전부
```

매번 `--profile` 붙이기 번거로우면 `cp .env.example .env` 후 작업에 맞는 profile을 적용하여 `docker compose up`.

| | |
| --- | --- |
| `docker compose --profile all down` | 내린다 (데이터 유지) |
| `docker compose --profile all down -v` | 볼륨까지 삭제 (초기화) |
| `docker compose ps` / `logs -f <서비스>` | 상태 / 로그 |

## 접속 정보

전부 로컬 전용 값이라 비밀이 아니다. **운영 서버 자격증명과 절대 같게 두지 말 것.**

| | 주소 | 계정 |
| --- | --- | --- |
| API | http://localhost:8080/swagger-ui/index.html | |
| Postgres | `localhost:15432` | `postgres` / `pickage` |
| MinIO | `http://localhost:9000` | `pickage` / `pickage123` |
| MinIO 콘솔 | http://localhost:9001 | 위와 같음 |

버킷 넷(`raw` `curated` `pkg-vectors` `mlflow-artifacts`)은 자동으로 생성된다.
`minio-init` 이 `Exited (0)` 인 것은 정상이다 — 한 번 돌고 끝나는 컨테이너다.

## Spark

```bash
docker compose exec spark pyspark
docker compose exec spark spark-submit /opt/work/작업파일.py
```

`pipeline/` 이 컨테이너의 `/opt/work` 로 마운트된다. 호스트에서 고치면 바로 반영된다.

**s3a 설정은 이미 되어 있다.** 코드에 config 를 쓰지 않아도 된다.

```python
spark = SparkSession.builder.master("local[*]").getOrCreate()
spark.read.parquet("s3a://raw/npm/downloads/")
```

## 지켜야 할 것 두 가지

**1. 경로는 `key=value/` 로 쓴다.**

```
s3a://raw/npm/downloads/collected_date=2026-09-07/
```

이렇게 쓰면 Spark 가 `collected_date` 를 컬럼으로 자동 인식한다.
그냥 `2026-09-07/` 로 쓰면 파일명을 파싱하는 코드를 매번 써야 하고 파티션 프루닝도 안 된다.

**2. 버킷 이름에 언더스코어를 쓰지 않는다.** `pkg_vectors`(X) → `pkg-vectors`(O)

s3a 와 일부 SDK 가 거부한다. 데이터가 들어간 뒤에는 이름을 못 바꿔 전부 복사해야 한다.

## boto3

```python
s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="pickage",
    aws_secret_access_key="pickage123",
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
| `Port 8080 already in use` 인데 브라우저는 뜸 | 이전 앱 프로세스가 남아 있다. `netstat -ano \| findstr :8080` |
| `NoSuchMethodError` (Spark) | `hadoop-aws` 버전 불일치 (아래) |
| MinIO 연결 실패 | `path.style.access` / `addressing_style` 누락 |
| 버킷·데이터가 옛날 상태 | `docker compose --profile all down -v` |
| `.env` 를 고쳤는데 안 먹음 | **셸 환경변수가 `.env` 보다 우선한다.** `echo $COMPOSE_PROFILES` 로 확인 (비어 있어야 `.env` 가 이긴다) |
| `.env` 에 키를 넣었는데 앱이 못 읽음 | **`.env` 는 compose 파일을 해석할 때만 쓰인다.** 컨테이너로 넘기려면 `env_file:` 또는 `environment:` 를 따로 써야 한다 |
| `--env-file` 썼더니 `.env` 값이 사라짐 | `--env-file` 은 추가가 아니라 **대체**다. 기본 `.env` 를 읽지 않는다 |
| PowerShell 에서 `curl` 이 이상함 | PowerShell 의 `curl` 은 `Invoke-WebRequest` 별칭이다. `curl.exe` 를 쓰거나 Git Bash |
| Git Bash 에서 `/opt/...` 가 `C:\...` 로 바뀜 | `MSYS_NO_PATHCONV=1` 을 앞에 붙인다 |

## 버전을 고정한 이유

올리기 전에 읽을 것.

| 대상 | 버전 | 이유 |
| --- | --- | --- |
| `apache/spark` | `3.5.3-python3` | 내장 Hadoop 이 3.3.4 |
| `hadoop-aws` | `3.3.4` | **Spark 내장 Hadoop 과 정확히 같아야 한다.** 어긋나면 `NoSuchMethodError` 로 죽고 원인이 드러나지 않는다 |
| `minio/minio` | `RELEASE.2025-04-22T22-12-26Z` | 운영 서버와 같은 태그. 이후 릴리스는 커뮤니티 빌드의 웹 콘솔이 축소됐다 |
| `postgres` | `16` | 운영 서버와 같은 메이저 버전 |

Spark 를 올리면 `hadoop-aws` 도 같이 맞춘다. 내장 버전 확인:

```bash
docker run --rm apache/spark:<태그> ls /opt/spark/jars | grep hadoop-client-api
```

설정 파일은 `deploy/local/spark/spark-defaults.conf`.
