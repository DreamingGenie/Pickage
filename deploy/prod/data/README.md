# `data` 노드 (j15a506a.p.ssafy.io)

수집 결과가 쌓이는 곳이다. **외부에 열린 포트가 없다** — 접속은 SSH 터널로만 한다.

| 서비스 | 무엇 |
| --- | --- |
| `minio` | S3 호환 저장소. 9000 = API(코드가 붙는 곳), 9001 = 웹 콘솔(사람이 보는 곳) |
| `minio-init` | 없는 버킷만 만드는 일회성 컨테이너. `Exited (0)` 이 정상이다 |
| `mlflow` | 모델 레지스트리. 5000 = API·웹 UI, 루프백만 (터널로 붙는다). **어느 모델이 `@production` 인지 아는 유일한 곳** |
| `spark-master` · `spark-worker-1` | 배치 시각에만. `profiles` 에 들어 있다 |
| `ai-stage` · `ai-similarity` · `ai-collect` | 유사도 배치 한 회차. **셋 다 상주가 아니다** — `run --rm` 으로 한 번 돌고 끝난다. 스테이징 → 배치 → 회수 순서 |

`app` 노드는 `j15a506` 이다 — **뒤에 `a` 가 없다.** 붙은 다음 `hostname` 을 먼저 확인할 것.

## ⚠ 로컬과 MinIO 버전이 다르다

| | 이미지 |
| --- | --- |
| 로컬 (`compose.yaml`) | `quay.io/minio/minio@sha256:14cea493…` — **더 새 것** |
| 여기 | `minio/minio:RELEASE.2025-04-22T22-12-26Z` — **더 오래된 것** |

여기가 오래된 쪽인 것은 실수가 아니다. 이 버전은 **웹 콘솔이 온전한 것을 직접 확인해
고정한 것**이다 — MinIO 는 커뮤니티 빌드의 콘솔 기능을 축소한 이력이 있고, 콘솔이
사라지면 팀원이 브라우저로 확인할 길이 없어진다.

**그래서 로컬에서 검증한 S3 동작이 여기서 그대로라는 보장이 없다.** 아래 증상이면
코드보다 버전 차이를 먼저 의심할 것.

- 로컬에서 되는 `mc` 명령이 여기서는 없거나 다르게 동작한다
(`mc admin` 하위 명령 구성이 릴리스마다 바뀌었다)
- 멀티파트 업로드 · 프리사인 URL · 객체 잠금 오류가 **서버에서만** 난다
- 콘솔 화면 구성이 로컬과 다르다

**맞출 때는 로컬을 이 버전으로 내리는 쪽을 먼저 검토한다.** 이쪽을 올리려면
백업 → 콘솔 확인 순서가 필요하고, 데이터 디렉터리 형식이 바뀌면 되돌릴 수 없다.
그리고 **이관과 같은 날 하지 않는다** — 둘을 한꺼번에 바꾸면 뭐가 깨졌는지 못 가린다.

[AGENTS.md](../../../AGENTS.md) 의 "알려진 환경 차이" 에도 적어 두었다.

## ⚠ 손으로 띄운 것에서 넘어오기 — 순서를 지킬 것

MinIO 가 지금 `docker run` 으로 떠 있고 **그 안에 수집 데이터가 들어 있다.**
compose 로 옮기는 건 데이터를 옮기는 게 아니라 **같은 디렉터리를 가리키는 컨테이너로 갈아타는 것**이다.

### 1. 지금 도는 컨테이너의 실제 설정을 확인한다

이 compose 는 이미지·데이터 경로를 **적어 둔 값**으로 갖고 있다. 실제와 다르면 안 된다.

```bash
docker inspect minio --format '{{.Config.Image}}'
docker inspect minio --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
docker inspect minio --format '{{range .Config.Env}}{{println .}}{{end}}' | grep MINIO_ROOT
```

- 이미지가 `minio/minio:RELEASE.2025-04-22T22-12-26Z` 인지
- 데이터 경로가 `/srv/minio/data` 인지 — **다르면 `compose.yaml` 맨 아래 `volumes:` 블록의**
**`device:` 를 실제 경로로 고친다.**
경로가 틀리면 MinIO 는 **빈 스토리지로 뜨고 버킷이 사라진 것처럼 보인다**
- 위에서 나온 `MINIO_ROOT_USER` · `MINIO_ROOT_PASSWORD` 를 그대로 `.env` 에 넣는다

### 2. 백업한다 — 지금이 가장 싸다

```bash
docker stop minio
sudo tar czf ~/minio-backup-$(date +%F).tar.gz -C /srv/minio data
ls -lh ~/minio-backup-*.tar.gz
```

**이 드라이브는 이중화가 없다** (단일 볼륨, 이레이저 코딩 0). 드라이브가 죽으면 끝이고,
`pickage-raw` 는 **MinIO 가 유일본**이다. 지금은 사용량이 적어 백업이 몇 분이면 끝난다 —
데이터가 쌓인 뒤에는 이 단계가 비싸진다.

### 3. 옛 컨테이너를 없애고 compose 로 띄운다

```bash
docker rm minio                      # stop 만으로는 안 된다. 이름과 포트를 계속 잡고 있다
cd ~/S15P21A506/deploy/prod/data
cp .env.example .env                 # 1번에서 확인한 자격증명을 넣는다
docker compose up -d
docker compose ps -a
```

**컨테이너를 반드시 먼저 없앤다.** 두 컨테이너가 같은 데이터 디렉터리를 동시에 쓰면
**MinIO 가 서로의 메타데이터를 덮어써서 데이터가 깨진다.**

> **이 노드의 `.env` 는 CI 가 만들어 줄 수 없다.** 배포 러너는 `app` 노드에만 있고
> 이 노드의 러너는 테스트용(docker executor)이라 서버 파일을 건드리지 않는다.
> 그래도 부담은 아니다 — MinIO 자격증명은 **한 번 정하고 바꾸지 않는다.**
> 자격증명 관리 방침은 [../README.md](../README.md) 의 "자격증명은 어디에 사나".

### 4. 이게 보이면 성공

```
minio        Up (healthy)
minio-init   Exited (0)
```

볼륨이 호스트 경로를 가리키는지 함께 본다. 여기가 틀리면 아래 `mc ls` 가
**빈 버킷 다섯 개**를 보여 주는데, 그게 "성공" 처럼 보여서 제일 위험하다.

```bash
docker volume inspect pickage-data_minio-data --format '{{.Options.device}}'
# /srv/minio/data
```

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls l'
```

버킷 다섯이 **기존 객체를 그대로 담은 채로** 보여야 한다.

```
pickage-raw  pickage-curated  pickage-vectors  pickage-mlflow-artifacts  pickage-quarantine
```

### 5. 진짜 성공 조건 — 손 안 대고 돌아오는가

**재부팅할 필요는 없다.** Docker 데몬만 새로 띄우면 같은 경로를 지난다 —
데몬이 시작하면서 restart 정책에 따라 컨테이너를 다시 올리는 그 동작이 핵심이다.

```bash
docker inspect $(docker ps -q) --format '{{.Name}} → {{.HostConfig.RestartPolicy.Name}}'
systemctl is-enabled docker
sudo systemctl restart docker
sleep 25 && docker compose --profile batch ps -a
```

**이게 보이면 성공** — 손으로 아무것도 안 했는데 이렇게 돌아와 있어야 한다.

```
minio           Up (healthy)
spark-master    Up
spark-worker-1  Up
minio-init      Exited (0)     ← 일회성 컨테이너라 안 돌아오는 것이 정상
```

**이게 이 작업의 목적이다.** `docker run` 으로 띄운 컨테이너는 서버가 재시작되면
돌아오지 않고, 수집이 무인으로 도는 구성에서 그건 **조용한 실패**가 된다.
아무도 모르는 채로 며칠이 지나고, npm 다운로드 수는 **놓친 기간을 소급 조회할 수 없다.**

#### ✔ 결과 (2026-09-09, 양 노드)

```
data   minio Up (healthy) · spark-master Up · spark-worker-1 Up · minio-init Exited (0)
       바인딩 127.0.0.1:9000-9001 + 172.26.8.249:9000 둘 다 유지
app    postgres · api · web 전부 Up (healthy) · https://j15a506.p.ssafy.io/ → 200
```

#### 재부팅이 추가로 확인하는 것 둘

데몬 재시작으로는 안 보이는 것이 있다. 여유가 생기면 한 번 해 볼 것.

| | 지금 상태 |
| --- | --- |
| 부팅 시 `docker.service` 자동 기동 | `systemctl is-enabled docker` = `enabled` 로 갈음 |
| **방화벽 규칙 잔존** | `ufw` 면 남고, 순수 `iptables` 면 **사라진다.** 확인 필요 |

## ⚠ `docker compose up -d --wait` 를 쓰지 말 것

`app` 노드에서는 `--wait` 를 쓴다. **여기서는 안 된다.**

```bash
docker compose up -d --wait          # 종료 코드 1 ← minio-init 이 끝난 것을 실패로 집계한다
docker compose up -d                 # 이걸 쓴다
```

`--wait` 는 모든 컨테이너가 계속 떠 있기를 기다린다. `minio-init` 은 일을 마치고
정상적으로 끝나는 컨테이너라서, 성공했는데도 실패로 보인다. **확인은 `ps -a` 로 한다.**

`minio-init` 이 `Exited (0)` 이면 그 자체가 MinIO 가 healthy 였다는 증거다 —
`minio` 가 healthy 가 된 뒤에만 돌기 때문이다.

**이 노드에는 그런 컨테이너가 둘이다.** `ai-similarity`(유사도 배치)도 한 번 돌고 끝난다.
그래서 `--profile batch` 를 붙여도 `--wait` 는 여전히 못 쓴다. 그 잡은 애초에
`up` 이 아니라 `run --rm` 으로 돌린다 — 아래 "유사도 배치 돌리기".

## 평소

```bash
cd ~/S15P21A506/deploy/prod/data
```

```bash
docker compose ps -a                 # minio·mlflow = Up (healthy), minio-init = Exited (0)
docker compose logs -f minio
docker compose restart minio
docker compose down                  # 내린다. 데이터는 남는다 (바인드 마운트)
```

```bash
df -h /                              # 디스크. MinIO·Spark 셔플·Docker 가 같은 파티션을 쓴다
```

**디스크 감시가 중요하다.** MinIO 가 파티션을 채우면 컨테이너 하나가 아니라
**Docker 데몬과 OS 가 같이 죽는다.** 70% 에서 정리를 시작할 것.

## 노트북에서 붙기

포트를 열지 않는다. 터널을 쓴다.

```bash
ssh -L 9000:localhost:9000 -L 9001:localhost:9001 -L 5000:localhost:5000 <user>@j15a506a.p.ssafy.io
```

터널을 연 채로 브라우저에서 MinIO 콘솔은 `http://localhost:9001`,
MLflow UI 는 `http://localhost:5000`. **터널을 닫으면 안 보이는 것까지
확인할 것** — 보이는 것만 확인하면 포트가 열려 있어서 보이는 건지 구분이 안 된다.

코드로 붙을 때는 **path-style 접근을 켜야 한다.** boto3·s3fs·Spark 의 기본값은
virtual-host style(`http://버킷명.endpoint/`)이고 MinIO 는 그 주소로 응답하지 않는다.
그냥 붙이면 DNS 오류나 404 가 난다.

```python
config=boto3.session.Config(s3={"addressing_style": "path"})
```

Spark 는 `fs.s3a.path.style.access=true`. 버킷별 역할과 경로 규칙은
[pipeline/minio/README.md](../../../pipeline/minio/README.md).

## MLflow — 모델 레지스트리

GPU(jupyter05)가 학습한 ONNX 를 `@candidate` 로 등록하고, 평가를 통과한 것을
`@production` 으로 승격한다.

> **유사도 배치가 여기를 보고 모델을 고른다.** `run-similarity-batch.sh` 가 매 회차
> `@production` 이 무엇인지 물어서 그 `source` 경로를 받아 온다 — 승격하면 다음 배치가
> 새 모델로 돈다. `.env` 를 고칠 일이 없다 (아래 "유사도 배치 돌리기").
>
> 잡 이미지에는 mlflow 클라이언트가 없다. 묻는 것은 **호스트의 스크립트**가 REST 로 한다.

`docker compose up -d` 에 같이 뜬다. 배치 전용이 아니다 — GPU 가 학습을 끝낼 때마다 붙는다.

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose up -d mlflow
docker compose ps mlflow                 # Up (healthy) 여야 한다
```

**첫 기동은 30초쯤 걸린다.** alembic 이 스키마를 처음부터 만든다 —
그동안은 `health: starting` 이고 정상이다 (`start_period: 90s`).

### 이게 보이면 성공

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/health      # 200
curl -fsS -X POST http://127.0.0.1:5000/api/2.0/mlflow/experiments/search \
  -H 'Content-Type: application/json' -d '{"max_results":1}' | tr ',' '\n' | grep artifact
# "artifact_location": "s3://pickage-mlflow-artifacts/mlflow/0"
```

두 번째 명령의 `s3://` 가 중요하다. 여기가 로컬 경로(`/mlflow/...`)로 나오면
`--default-artifact-root` 가 안 먹은 것이고, **모델이 컨테이너 안에 쌓이다가
볼륨과 함께 사라진다.**

주소만 맞는 것과 실제로 올라가는 것은 다르다. **한 번은 올려서 MinIO 에 떨어지는지 본다.**

```bash
docker run --rm --network pickage-data_default \
  -e MLFLOW_TRACKING_URI=http://mlflow:5000 \
  -e MLFLOW_S3_ENDPOINT_URL=http://minio:9000 \
  -e AWS_ACCESS_KEY_ID=<MinIO 키> -e AWS_SECRET_ACCESS_KEY=<MinIO 시크릿> \
  python:3.11-slim sh -c 'pip install -q mlflow-skinny==3.1.0 boto3 && python - <<PY
import mlflow, pathlib
mlflow.set_tracking_uri("http://mlflow:5000"); mlflow.set_experiment("artifact-smoke")
p = pathlib.Path("/tmp/x.bin"); p.write_bytes(b"x" * 1024)
with mlflow.start_run() as r: mlflow.log_artifact(str(p), artifact_path="onnx")
print([a.path for a in mlflow.MlflowClient().list_artifacts(r.info.run_id, "onnx")])
PY'
```

`['onnx/x.bin']` 이 나오고, **MinIO 에 실물이 있어야 한다.**

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls --recursive l/pickage-mlflow-artifacts'
# mlflow/1/<run_id>/artifacts/onnx/x.bin
```

끝나면 지운다.

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc rm -r --force l/pickage-mlflow-artifacts/mlflow/'
```

### 노트북·GPU 에서 붙기

포트를 열지 않는다. 터널을 쓴다.

```bash
ssh -L 5000:localhost:5000 <user>@j15a506a.p.ssafy.io
```

터널을 연 채로 브라우저에서 `http://localhost:5000`.
GPU 쪽은 `ai/training/run_pipeline.sh` 가 이 터널을 알아서 연다 (`-L 5000` + `-L 9000`).

### ⚠ 아티팩트는 서버를 거치지 않는다

`--no-serve-artifacts` 로 띄웠다. **서버는 `s3://...` 주소를 문자열로만 들고 있고,
실제 업로드·다운로드는 클라이언트가 자기 자격증명으로 MinIO 에 직접 한다.**

| | 서버가 하는 일 | 클라이언트가 해야 하는 일 |
| --- | --- | --- |
| 실험·런·등록모델·별칭 | 전부 서버(sqlite) | — |
| 모델 파일 | 주소만 기록 | **MinIO 에 직접 읽고 쓴다** |

그래서 클라이언트에는 MLflow 주소만으로 부족하다. 아래가 같이 필요하다.
(지금 그 클라이언트는 **GPU 쪽뿐이다** — 유사도 배치는 아직 MLflow 를 쓰지 않는다.)

```
MLFLOW_TRACKING_URI=http://<mlflow>:5000
MLFLOW_S3_ENDPOINT_URL=http://<minio>:9000
AWS_ACCESS_KEY_ID=<MinIO 키>          # boto3 가 읽는 이름이다. MINIO_* 가 아니다
AWS_SECRET_ACCESS_KEY=<MinIO 시크릿>
```

> **여기서는 path-style 을 따로 켜지 않아도 된다 (확인함).** 위 "노트북에서 붙기" 는
> path-style 을 켜라고 하는데, 그건 `endpoint_url` 을 직접 다룰 때의 이야기다.
> MLflow 아티팩트 경로는 `MLFLOW_S3_ENDPOINT_URL` 이 **호스트명**(`minio`)이라
> botocore 가 알아서 path-style 로 보낸다 — 업로드가 그대로 통했다.
>
> **`endpoint_url` 에 버킷명이 붙을 수 있는 주소(도메인)를 쓰게 되면 이 줄을 다시 볼 것.**

왜 이렇게 했나: 서버가 아티팩트를 중계하게 하려면 boto3 가 필요한데
**공식 이미지에 boto3 가 없다**(확인함). 커스텀 이미지를 만들어 유지하는 대신,
어차피 MinIO 자격증명을 갖고 있는 클라이언트에게 맡겼다.

### ⚠ `mlflow.db` 는 모델 파일이 아니다 — 더 잃기 쉬운 것이다

`mlflowdb` 볼륨의 sqlite 파일이 **"어느 모델이 `@production` 인가" 를 아는 유일한 곳**이다.
모델 파일은 MinIO 에 있어서 남지만, 이걸 잃으면 **어느 게 운영인지 모르게 된다.**

`minio-data` 와 달리 이 볼륨은 호스트 경로로 도망갈 곳이 없다 —
`down -v` 경고가 **글자 그대로 적용된다.**

학습을 돌린 날 한 번 백업한다. 258 KB 짜리라 순식간이다.

```bash
docker compose exec mlflow python -c "
import sqlite3
src = sqlite3.connect('/mlflow/mlflow.db')
dst = sqlite3.connect('/mlflow/backup.db')
with dst: src.backup(dst)
"
docker cp $(docker compose ps -q mlflow):/mlflow/backup.db ~/mlflow-$(date +%F).db
ls -lh ~/mlflow-*.db
```

> **⚠ `cp` 나 `shutil.copy` 로 파일만 떠 가지 말 것.** `journal_mode` 가 `delete` 라
> 쓰는 중에는 일관된 상태가 `mlflow.db` 와 **`mlflow.db-journal` 에 나뉘어 있다.**
> `.db` 만 복사하면 찢어진 사본이 나올 수 있다 — 그것도 **조용히**, `integrity_check` 는
> 통과하는 모양으로.
>
> `Connection.backup()` 은 sqlite 의 온라인 백업 API 라 **쓰는 중에도 일관된 한 파일**을
> 만든다. GPU 가 모델을 등록하는 중에 백업이 돌아도 안전하다.

복구는 컨테이너를 멈추고 파일을 되돌려 놓는 것이 전부다.

```bash
docker compose stop mlflow
docker compose run --rm --no-deps --entrypoint sh mlflow -c 'rm -f /mlflow/mlflow.db /mlflow/mlflow.db-journal'
docker cp ~/mlflow-2026-09-11.db $(docker compose ps -aq mlflow):/mlflow/mlflow.db
docker compose start mlflow
docker compose ps mlflow        # Up (healthy)
```

**`mlflow.db-journal` 을 같이 지우는 것이 중요하다.** 옛 저널이 남은 채로 다른 `.db` 를
넣으면 sqlite 가 그 저널로 롤백을 시도한다 — 되살린 백업이 도로 망가질 수 있다.

복구됐는지는 별칭으로 확인한다. 파일이 있는 것과 장부가 살아 있는 것은 다르다.

```bash
curl -fsS "http://127.0.0.1:5000/api/2.0/mlflow/registered-models/alias?name=pickage-similarity&alias=production" \
  | tr ',' '\n' | grep -E '"name"|"version"'
```

### backend store 를 sqlite 로 둔 이유

**먼저 MinIO 는 후보가 아니다.** backend store 는 `s3://` 를 못 받는다 — 지원 스킴이
아니다. 넣어 보면 기동 자체가 안 된다.

```
Model registry functionality is unavailable; got unsupported URI 's3://...'
Supported URI schemes are: ['', 'file', 'postgresql', 'mysql', 'sqlite', 'mssql']
```

모델 **파일**은 MinIO 에 있지만, "몇 번째 버전이고 무엇이 `@production` 인가" 를 적는 장부는
저기 못 둔다. 그래서 선택지가 셋이었다.

| | 되나 | 왜 골랐나 / 왜 뺐나 |
| --- | --- | --- |
| **PostgreSQL** | 됨 | **뺐다.** `app` 노드의 **5432 를 열어야 한다** — 로더를 `app` 노드에 두어 그 포트를 닫아 두기로 한 결정과 정면으로 맞바꾼다 ([../README.md](../README.md) 의 "유사도 결과 로더는 어디서 도나") |
| **`file`** | **됨** (버전·별칭까지 동작하는 것을 확인했다) | 안 골랐다. 아래 한 줄 차이뿐이다 |
| **sqlite** | 됨 | **골랐다.** DB 가 **파일 하나**라 백업·복구가 `mlflow.db` 하나로 끝난다 |

**`file` 과의 차이는 그것뿐이다.** 지금 규모(학습 몇 회/일, 쓰는 주체는 GPU 하나)에서
둘의 실질 차이는 크지 않다 — 바꾸고 싶으면 `--backend-store-uri` 한 줄이다.

PostgreSQL 로 옮겨야 할 만큼 커지면 **그 시점에 포트 결정을 다시 본다.** 다만
**MLflow 에 sqlite → PostgreSQL 데이터 이관 명령은 없다** (`mlflow db upgrade` 는 한 DB 의
스키마를 올리는 것뿐이다). 옮길 때는 손으로 덤프·적재해야 하고, 그건 `file` 에서 옮기는
것과 난이도가 비슷하다.

## 하지 말 것

| | 무슨 일이 생기나 |
| --- | --- |
| `docker compose down -v` | MinIO 는 `/srv/minio/data` 의 파일이 남는다 (확인함). **하지만 `mlflowdb` 볼륨은 진짜로 지워진다** — 어느 모델이 `@production` 인지 잃는다. 위 "MLflow" 를 볼 것 |
| `volumes:` 의 `device:` 변경·`driver_opts` 삭제 | MinIO 가 빈 스토리지로 뜬다. **데이터는 `/srv/minio/data` 에 그대로 있는데 컨테이너가 다른 곳을 보는** 상태다 |
| 루트 자격증명 교체 | 발급한 서비스 계정이 못 쓰게 될 수 있다. **수집이 그 키로 붙고 있다** |
| MinIO 버전 올리기 | 콘솔 기능이 축소된 이력이 있다. 백업 → 콘솔 확인 순서로, **이관과 다른 날에** |
| `ports` 의 `127.0.0.1:` 제거 | 자격증명만 통과하면 버킷 전체를 읽고 쓸 수 있는 문이 열린다 |

## Swap — 이 노드는 파티션을 같이 쓴다

두 노드에 스왑 2 GiB 가 있고, **모든 컨테이너에는 `memswap_limit` 으로 스왑을 0 준다.**
절차와 이유는 [../README.md](../README.md) 의 "Swap" — **두 노드에서 같은 절차를 돈다.**

이 노드에서만 추가로 걸리는 것: `/swapfile` 이 **MinIO 데이터(`/srv/minio/data`)·Docker·
Spark 셔플과 같은 파티션**에 놓인다. 스왑을 실제로 쓰기 시작하면 MinIO 읽기와 셔플 쓰기의
IOPS 를 같이 갉아먹는다. `df -h /` 를 먼저 보고, 스왑을 2 GiB 보다 크게 잡지 말 것.

## 유사도 배치 돌리기

Spark 가 curated 를 만든 다음 단계다. `ai/similarity/` 의 파이썬 잡이 코퍼스를 걸러
ONNX 로 임베딩하고 유사 후보를 뽑는다. **PostgreSQL 은 건드리지 않는다** — 적재는
`app` 노드의 로더가 따로 한다 ([../README.md](../README.md) 의 "유사도 결과 로더는 어디서 도나").

**상주 서비스가 아니다.** 한 번 돌고 끝난다 — `profiles` 에 있어서 `up -d` 로는 뜨지 않는다.

### 이미지는 이제 손으로 굽지 않는다 (S15P21A506-339)

`develop`·`main` 에 머지되면 **`deploy-ai` 잡이 이 노드에서 굽고 `.env` 의 `AI_TAG` 를
커밋 SHA 로 갈아 끼운다.** 그래서 아래 절차에서 빠진 것이 둘이다.

| 전에 손으로 하던 것 | 지금 |
| --- | --- |
| `docker compose --profile batch build ai-similarity` | `deploy-ai` 가 한다 |
| `.env` 의 `AI_TAG` 수정 | `deploy-ai` 가 한다 |
| `sh run-similarity-batch.sh` | **그대로 사람이 친다** |

**돌리는 절차는 아무것도 안 바뀌었다.** 다음 회차가 어느 이미지로 도는지만 확인하면 된다.

```bash
grep ^AI_TAG= /srv/pickage/data.env
```

```bash
docker images pickage-ai-similarity --format '{{.CreatedAt}}\t{{.Tag}}' | sort -r | head -3
```

**위에서 나온 태그가 아래 목록에 있으면 준비된 것이다.** 없으면 `deploy-ai` 가 아직 안
돌았거나 실패한 것이다 — GitLab 의 Build → Pipelines 에서 그 잡을 보고 **Retry** 하면 된다
([`../../ci/README.md`](../../ci/README.md) 의 "유사도 배치 이미지").

> ⚠ **`deploy-ai` 는 배치가 도는 중인지 보지 않는다.** `deploy-app` 과 같은 모양이라
> 머지되면 그냥 굽는다. 겹치는 것을 막는 것은 아래 "Spark 배치와 시간을 겹치지 말 것" 과
> 같은 규칙 하나뿐이다 — **배치 시각에는 머지하지 않는다.**

> ⚠ **`.env` 는 `/srv/pickage/data.env` 하나뿐이고, 이 디렉터리의 것은 그것을 가리키는
> 심볼릭 링크다.** 두 벌이 되면 잡이 고친 태그와 여기서 읽는 태그가 갈라진다.
>
> ```bash
> readlink -f .env      # /srv/pickage/data.env
> ```

> `deploy-ai` 는 **이미지만 굽는다.** minio·mlflow·Spark 는 여전히 사람이 이 디렉터리에서
> 올린다 — 그 잡은 `up` 도 `down` 도 치지 않는다.

### 사람이 인자를 주지 않는다 — 포인터 둘이 정한다

`run-similarity-batch.sh` 는 **인자를 받지 않는다.** 무엇을 돌릴지는 두 포인터가 정하고,
스크립트가 매번 읽어 확정한다.

```
코퍼스   $AI_CORPUS_PREFIX/_current.json      →  run_path(코퍼스 경로) + run_id(산출물 이름)
모델     MLflow  $AI_MODEL_NAME@$AI_MODEL_ALIAS  →  s3:// 경로
```

**새 코퍼스가 게시되거나 모델이 승격되면 다음 실행이 알아서 집는다.** `.env` 에는 날짜도
모델 버전도 없다 — 회차마다 고칠 것이 없어야 자동화다.

둘 다 그대로면 **아무것도 하지 않고 0 으로 끝난다.** 타이머를 촘촘히 걸어도 헛돌지 않고,
스케줄러가 "새 것이 있나" 를 판단할 필요가 없다.

```
[timer] → 확정 → 이미 했나? ─ 예 ─→ exit 0
                            └ 아니오 ─→ 스테이징 → 배치 → 회수
```

#### 확정한 값을 산출물 경로에 박는다

```
pickage-vectors/model=v7/corpus=package-text-20260908-v1/
```

포인터를 따라가면서도 **"이 결과가 어느 모델·어느 코퍼스에서 나왔나" 가 경로에 남는다.**
`_current.json` 은 다음 실행에 바뀌므로, 재현하려면 이 경로를 봐야 한다
(`pipeline/curated/README.md` 의 같은 원칙).

##### `_current.json` 이 싣는 값 (S15P21A506-348)

```json
{"collected_date":"2026-09-08","manifest_sha256":"…",
 "run_id":"package-text-20260908-v1",
 "run_path":"collected_date=2026-09-08/run_id=package-text-20260908-v1"}
```

| 키 | 쓰임 | 왜 이 모양인가 |
| --- | --- | --- |
| `run_path` | 코퍼스를 찾는다 (`$AI_CORPUS_PREFIX/$run_path/data`) | **prefix 상대**다. `.env` 가 prefix 를 이미 들고 있어서, 전체 경로를 실으면 두 값이 갈라질 자리가 생긴다 |
| `run_id` | 산출물 경로 `corpus=<run_id>` 에 박는다 | **평평해야 한다.** `/` 가 들어가면 `/work/out` 의 깊이가 한 단 깊어져 `ai-collect` 의 `for d in /work/out/*/*` 가 `_SUCCESS` 를 한 단계 위에 찍는다. 중복 확인은 전체 경로를 보므로 같은 회차를 매번 다시 돌게 된다 |
| `manifest_sha256` | 그 실행의 `run_manifest.json` 바이트 해시 | `depsdev` 포인터와 같은 항목 |

게시하는 쪽은 `pipeline/minio/ingest_derived.py`(`pointer` 가 켜진 데이터셋)다.

그 경로의 `_SUCCESS` 가 곧 "이미 했다" 의 근거다. 별도 상태 저장소를 두지 않는다.

#### ⚠ JSON 해석은 컨테이너가 아니라 스크립트에서 한다

`mc` 를 담은 MinIO 이미지에는 **`sed`·`grep`·`jq`·python 이 없다**(확인함). `curl` 은 있다.
그래서 포인터 해석은 호스트에서 하고, 컨테이너에는 **확정된 경로만** `-e` 로 넘긴다.
MLflow 도 `127.0.0.1:5000` 이라 호스트가 바로 부를 수 있다.

`ai-stage`·`ai-collect` 를 직접 `run` 하면 그 변수가 없어서 거부한다. 스크립트로 부를 것.

#### 스케줄러는 아직 없다

붙일 때는 **cron 보다 systemd timer** 를 권한다. cron 의 기본 실패 모드가 침묵인데,
이 리포는 이미 그걸로 한 번 데었다 (위 "손 안 대고 돌아오는가"). timer 는
`systemctl list-timers` 로 마지막·다음 실행이, `journalctl -u` 로 지난 로그가 바로 보인다.

스크립트가 인자를 안 받고 멱등하므로 **timer 는 이 파일을 부르기만 하면 된다.**

#### 아직 서지 않은 것 — 이 순서로 풀린다

| | 없으면 어디서 멈추나 | 누구 |
| --- | --- | --- |
| ~~`package_text` + `_current.json`~~ | **2026-09-14 게시됨** (`package-text-20260908-v1`, S15P21A506-348) | 데이터 |
| MLflow 에 등록된 모델 | **2단계.** `@production` 이 없다 | AI |
| **로더** | 배치는 돌지만 `similar_package` 가 계속 비어 서비스에 안 닿는다 | 미정 |
| 스케줄러 | 사람이 스크립트를 친다 | 인프라 |

### ⚠ 이 잡은 MinIO 를 직접 읽지 않는다

입출력이 **전부 로컬 경로**다. 이미지에 boto3 가 없다 (`requirements.txt` 는
numpy·onnxruntime·pyarrow·transformers뿐). 산출물의 `s3://` 출력은 후속 작업이다 —
`similarity_batch_pipeline.py` 의 "현재 구현 상태" 6번.

그래서 **MinIO 에서 꺼내 오고 다시 넣는 것은 사람이 한다.** 그 통로가 `aiwork` 볼륨이다.

```
MinIO ──(1) 스테이징──▶ aiwork:/work/in ──(2) 배치──▶ /work/out ──(3) 올리기──▶ MinIO
```

### 0. 처음 한 번 — 볼륨 소유권

컨테이너는 uid 1000(`appuser`)으로 도는데 **새 볼륨은 root 소유로 만들어진다.**
그냥 돌리면 `--out` 쓰기에서 `Permission denied` 다.

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose run --rm --user root --entrypoint sh ai-similarity \
  -c 'mkdir -p /work/in /work/out && chown -R 1000:1000 /work'
```

```bash
docker compose run --rm --entrypoint sh ai-similarity -c 'id -u; touch /work/out/.probe && echo ok'
# 1000
# ok
```

### 돌리기

```bash
cd ~/S15P21A506/deploy/prod/data
sh run-similarity-batch.sh
```

**인자가 없다.** 스크립트가 포인터 둘을 읽어 확정하고, 이미 한 회차면 넘어간다.

```
[1/5] 코퍼스 확정
  run_id=package-text-20260908-v1  run_path=collected_date=2026-09-08/run_id=package-text-20260908-v1
[2/5] 모델 확정
  v7  pickage-mlflow-artifacts/v7
[3/5] 중복 확인  model=v7/corpus=package-text-20260908-v1
[4/5] 스테이징
[5/5] 배치
      회수
완료: pickage-vectors/model=v7/corpus=...
```

종료 코드를 그대로 올린다. **스케줄러는 이 값만 보면 된다** — 로그를 파싱할 이유가 없다.
`PYTHONUNBUFFERED=1` 이 이미지에 박혀 있어 배치 로그는 실시간으로 흐른다.

#### 단계별로 무엇을 하나

| | 서비스 | 하는 일 |
| --- | --- | --- |
| 1 | (스크립트) | `_current.json` → `run_path`(코퍼스)·`run_id`(산출물 이름) 확정 |
| 2 | (스크립트) | MLflow `@production` → 모델 `s3://` 경로 확정 |
| 3 | (스크립트) | 산출물 경로에 `_SUCCESS` 가 있으면 **여기서 끝** |
| 4 | `ai-stage` | MinIO → `/work/in/`, `uid 1000` 으로 `chown` |
| 5 | `ai-similarity` | 배치. `/work/out/model=vN/corpus=<run>/` 에 쓴다 |
| — | `ai-collect` | `/work/out` → MinIO, `_SUCCESS` 게시 |

`ai-stage`·`ai-collect` 를 **직접 `run` 하지 말 것.** 확정된 경로를 스크립트가 `-e` 로
넘기므로, 단독으로 부르면 그 변수가 없어서 거부한다.

#### 배치 옵션

전체 목록은 `docker compose run --rm ai-similarity --help`. 자주 볼 것:

| 옵션 | 무엇 |
| --- | --- |
| `--state` | 이전 회차의 `text_hash_state.parquet`. 주면 **바뀐 것만 재임베딩**한다 |
| `--batch-size` · `--query-block` | 메모리를 지배한다. **OOM 이 나면 상한보다 이 둘을 먼저 줄인다** |
| `--no-gate` | 구조적 관문을 끈다. 게이트 때문에 후보가 비는지 가릴 때만 |

스크립트가 넘기는 인자를 바꾸려면 `run-similarity-batch.sh` 의 5단계를 고친다.

#### 결과 확인

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls --recursive l/pickage-vectors/'
# model=v7/corpus=package-text-20260908-v1/_SUCCESS
# model=v7/corpus=package-text-20260908-v1/...
```

**`_SUCCESS` 가 곧 "이 회차는 끝났다" 의 근거다.** 이게 있으면 다음 실행이 건너뛴다 —
다시 돌리고 싶으면 그 객체를 지운다.

> **Windows 에서 칠 때는 `MSYS_NO_PATHCONV=1` 을 앞에 붙인다.** 안 붙이면 Git Bash 가
> `/work/in/...` 를 `C:/Program Files/Git/work/in/...` 으로 바꿔서 `FileNotFoundError` 가 난다
> (확인함). 서버에서는 이 문제가 없다.

### ⚠ Spark 배치와 시간을 겹치지 말 것

이 잡이 도는 시각이 이 노드가 가장 빠듯한 시각이다.

```
Spark 셋 12g + ai-similarity 2g ≈ 14g / 15Gi
```

`mem_limit` 을 올리려면 worker① 의 `SPARK_WORKER_MEMORY` 를 먼저 내려야 한다.
상한만 올리면 배치 때 커널이 아무거나 하나 죽인다 — 위 "메모리가 터졌을 때".

### `up -d --profile batch` 로 띄우지 말 것

이 잡은 정상적으로 끝나는데 compose 는 그걸 컨테이너가 죽은 것으로 본다 —
`minio-init` 과 같은 사정이다 (위 `--wait` 절). 이 노드에 그런 컨테이너가 셋이다
(`minio-init`, `ai-*`, `ingest-weekly`).

## 주간 수집

매주 화요일, deps.dev 주간 증분과 npm 다운로드 직전 14일을 받아 MinIO Bronze 까지 넣는다.
**systemd 타이머가 10분마다 깨우고, 할 일이 없으면 아무것도 하지 않고 끝난다.**

```
[timer 10분] → run-weekly-ingest.sh → docker compose run --rm ingest-weekly
                (잠금·정리만)          (판정도 실행도 컨테이너 안에서)
```

실행기 자체의 설명(단계·날짜 규약·유예·정리)은 [`pipeline/weekly/README.md`](../../../pipeline/weekly/README.md).

### 0. 처음 한 번 — 디렉터리와 자격증명

```bash
sudo mkdir -p /srv/pickage/ingest-work /srv/pickage/secrets
sudo chown -R 1000:1000 /srv/pickage/ingest-work /srv/pickage/secrets
# GCP 서비스 계정 키를 /srv/pickage/secrets/gcp-service-account.json 으로 둔 뒤
sudo chown 1000:1000 /srv/pickage/secrets/gcp-service-account.json
sudo chmod 600 /srv/pickage/secrets/gcp-service-account.json
```

⚠ **소유권을 넘기지 않으면 쓰기가 막힌다.** 컨테이너가 uid 1000 으로 돌고, 없는 바인드
디렉터리는 Docker 가 root 소유로 만든다. root 로 쓰게 두지 않는 이유는 그렇게 쌓인
산출물을 `ubuntu` 계정이 못 지워서 **지난 회차 정리가 거기서 막히기** 때문이다.
키 파일도 같은 이유로 uid 1000 소유여야 한다 — `600` 이면서 root 소유면 못 읽는다.

⚠⚠ **부모 `/srv/pickage` 를 통째로 `chown` 하지 말 것.** 그 디렉터리는 이 노드에서
이미 쓰이고 있다 — 배포 러너가 `gitlab-runner` 소유로 만들고 그 아래 `data.env`
(MinIO 루트 자격증명)를 둔다([`deploy/ci/README.md`](../../ci/README.md) 의 "데이터 노드
배포 러너"). 통째로 넘기면 `deploy-ai` 잡이 `AI_TAG` 를 고치지 못해 **유사도 배치 이미지
배포가 실패한다.** 증상이 주간 수집과 연결되지 않아 원인을 찾기 어렵다.

부모 디렉터리 권한은 컨테이너와 무관하다. 바인드 경로는 Docker 데몬(root)이 해석해서
마운트하므로, 컨테이너 안의 uid 1000 은 호스트의 부모 경로를 거치지 않는다. **마운트되는
두 디렉터리의 소유권만 맞으면 된다.**

자격증명은 환경변수가 아니라 **파일**이다(`pipeline/minio/ingest_raw.py` 의 `client()`).

```bash
cd ~/S15P21A506
cp pipeline/minio/.env.data.example pipeline/minio/.env.data
# 같은 노드의 MinIO 값을 넣는다:
docker inspect pickage-data-minio-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep MINIO_ROOT
```

`deploy/prod/data/.env` 에 `OSS_SHIFT_UA_CONTACT` 도 채운다. 비어 있으면 수집기가
시작하지 않는다.

### 1. 이미지 빌드

이 노드에는 CI 배포 러너도 레지스트리도 없다. `app` 노드의 api·web 과 같이 서버에서 빌드한다.

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose build ingest-weekly
docker compose run --rm ingest-weekly --help      # 인자 목록이 나오면 성공
```

**이미지에는 코드가 없다.** `pipeline/` 은 마운트된다 — 코드를 고쳤을 때 다시 빌드할 필요가
없고, 되돌리는 방법도 태그 교체가 아니라 `git checkout` 이다. 다시 빌드할 일은 의존성이
바뀔 때뿐이다.

### 2. 손으로 한 번 돌려 본다

타이머를 켜기 전에 확인한다. `--dry-run` 은 단계를 돌리지 않고 **판정만 흉내 낸다.**

```bash
sh run-weekly-ingest.sh --dry-run
```

**상태 객체에는 쓰지 않는다.** 전이는 메모리에서만 일어나고 `run.json` 은 그대로다.
그래서 수집 창이 열린 뒤에 돌려도 그 주 회차를 건드리지 않는다.

그리고 **실제 자격증명이 통하는지**는 따로 본다. 드라이런은 외부 CLI 를 부르지 않으므로
여기서 드러나지 않는다.

```bash
docker compose run --rm ingest-weekly --only gcs_sync
```

⚠ gcloud 와 파이썬이 **인증 경로가 다르다.** BigQuery 파이썬 클라이언트는
`GOOGLE_APPLICATION_CREDENTIALS` 를, `gcloud storage` 는 자체 저장소를 본다. 이미지가
둘 다 같은 키 파일을 가리키게 해 뒀지만, 실제로 불러 봐야 확인된다.

### 3. 타이머를 켠다

```bash
sudo cp systemd/pickage-weekly.service systemd/pickage-weekly.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pickage-weekly.timer
systemctl list-timers pickage-weekly.timer
```

### 지금 어디까지 왔나

**이것이 배포와 무관한 확인 경로다.** 운영자용 조회 API(S15P21A506-347)는 백엔드가
배포된 뒤에야 쓸 수 있고, 지금 운영 이미지에는 그 API 가 없다.

```bash
cd ~/S15P21A506/deploy/prod/data
mc() { docker compose exec -T minio sh -c "mc alias set l http://127.0.0.1:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null && $1"; }

# 어떤 회차들이 있나
mc "mc ls l/pickage-raw/_ops/weekly/"

# 그 회차의 상태 전부 (status·coverage·연속 실패·단계별)
mc "mc cat l/pickage-raw/_ops/weekly/2026-09-21/run.json"
```

읽는 법.

| 보는 것 | 뜻 |
| --- | --- |
| `coverage.downloads_through` | **언제 데이터까지 들어왔나.** `SUCCEEDED` 회차 중 최신 것이 지금 가진 데이터의 끝이다 |
| `status` | `PENDING`·`RUNNING`·`SUCCEEDED`·`FAILED`·`BLOCKED` |
| `consecutive_failures` | 이 회차에서 연속 몇 번 실패했나. 10 이면 `BLOCKED` 다 |
| `steps[]` 중 `SUCCEEDED` 가 아닌 첫 항목 | 어디서 멈췄나. `error_message` 에 꼬리 4 KB |

타이머 쪽은 systemd 로 본다.

```bash
systemctl list-timers pickage-weekly.timer     # 다음 발화 시각
journalctl -u pickage-weekly.service -n 50     # 최근 발화들
docker ps -a --filter name=pickage-weekly-run  # 지금 도는 중인가
```

단계별 출력 전문은 `/srv/pickage/ingest-work/downloads-weekly/<week_of>/logs/<step>.log`.

### `BLOCKED` 을 푸는 법

연속 10회 실패하면 자동 재시도를 멈춘다. 같은 실패를 10분마다 영원히 반복하지 않기
위한 것이다. 푸는 방법은 **수동 실행 요청 하나**다.

정상 경로는 백엔드 API(`POST /api/v1/ops/weekly/runs/{weekOf}/manual-request`)지만,
그것이 배포되기 전에는 우편함 객체를 직접 넣으면 된다.

```bash
mc 'printf "{\"requested_at\": \"%s\"}" "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" \
    | mc pipe l/pickage-raw/_ops/weekly/2026-09-21/manual-request.json'
```

다음 발화(최대 10분)에서 실행기가 집어 가며 연속 실패 횟수를 0으로 되돌린다. 집어 갔는지는
`run.json` 의 `manual_claimed_at` 으로 확인한다 — 그 값이 `requested_at` 보다 나중이면
소비된 것이다.

**지난 회차에도 걸 수 있다.** 실행기는 이번 주에 할 일이 없을 때 우편함이 걸린 지난 회차를
훑어 **오래된 것부터** 한 회차씩 집어 간다(다시 받을 수 있는 한계가 18개월이라 오래된 쪽이
급하다). 다만 이번 주 수집이 우선이므로, 화요일 창이 열려 회차가 도는 동안(약 23시간)은
지난 회차가 기다린다 — 러너는 한 번에 한 회차만 돈다.

⚠ 지난 회차를 다시 돌리면 그 주 로컬 산출물이 이미 정리됐을 수 있다(`--keep-weeks` 기본
2주). 그러면 체크포인트가 없어 **처음부터 다시 받는다** — 약 23시간이다.

`mc pipe` 를 쓰는 이유는 호스트에서 컨테이너로 파일을 옮기는 단계가 없어서다.
시각은 컨테이너 안에서 만든다(호스트 셸의 `date` 형식에 의존하지 않는다).

**먼저 원인을 보라.** `BLOCKED` 은 같은 실패가 10번 반복됐다는 뜻이라, 요청만 넣으면
11번째 실패가 난다. `run.json` 의 `last_error` 와 단계 로그를 먼저 읽는다.

### ⚠ 유사도 배치와 시간을 겹치지 말 것

평소에는 여유롭다 — 상주가 `minio` 1g + `mlflow` 512m 뿐이라 수집 3g 를 얹어도 4.5g 다.

문제는 **배치 시각**이다.

```
Spark 셋 12g + ai-similarity 2g ≈ 14g / 15Gi      ← 여기에 3g 를 더 얹을 자리가 없다
```

수집 창은 **화 10:00 부터 다음 날 09:00 KST** 다(한 바퀴 약 23시간). 유사도 배치 타이머는
아직 없으므로, **그것을 만들 때 이 창 밖으로 잡으면 충돌이 애초에 생기지 않는다.**

### ⚠ 디스크 — MinIO 와 같은 파티션이다

산출물이 주당 약 10 GB 쌓인다. 실행기가 성공한 회차에 한해 2주치만 남기고 지우지만,
그게 멈추면 계속 쌓인다.

```bash
df -h /
du -sh /srv/pickage/ingest-work
```

여기를 채우면 수집만 멈추는 게 아니다. **MinIO 가 같은 파티션을 쓰므로 저장소가 통째로 선다.**

## Spark (배치)

이 노드에 master 와 worker① 이 있고, `app` 노드에 worker② 가 있다.
**두 노드에 나뉘어 있는 것이 요구사항이다** — 분산 처리를 실제로 했다는 증빙이 필요하다.

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose --profile batch up -d          # master + worker①
docker compose --profile batch ps
```

`--profile batch` 가 없으면 **MinIO 만** 뜬다. 일부러 그렇게 뒀다 — 아직 배치를 돌릴
데이터가 없고, MinIO 만 다룰 때 Spark 가 같이 뜨면 메모리를 괜히 잡는다.
정기 배치가 시작되면 `profiles:` 를 떼서 상시 기동으로 바꾸는 게 맞다.

`app` 노드의 worker② 는 **상시로 떠 있다.** `docker compose up -d` 에 같이 들어가서
따로 올릴 필요가 없다 (이유는 [../README.md](../README.md) 의 "왜 상시로 두나").

### ⚠ 먼저 방화벽 — 이걸 안 하면 job 이 조용히 멈춘다

**두 노드 사이는 기본적으로 막혀 있다.** 필요한 포트를 하나씩 열어야 한다.
Spark 는 기본값으로 임의의 높은 포트를 쓰기 때문에 `spark-defaults.conf` 에서
**고정해 두었다** — 그래서 아래 목록이 유한하다.

**`data` 노드 인바운드** (출처: `app` = `172.26.6.235`)

| 포트 | 무엇 | 없으면 |
| --- | --- | --- |
| **7077** | master RPC | worker② 가 아예 등록되지 않는다 |
| **9000** | MinIO S3 API | executor 가 파티션을 못 읽는다. **driver 만 닿으면 파티션 1개짜리 잡은 통과해서 더 헷갈린다** |
| **40001** | driver RPC | executor 가 driver 에 되연결하지 못한다 |
| **40002** | driver blockManager | 결과 수집이 멈춘다 |
| **40010-40014** | executor blockManager (셔플) | 셔플이 있는 잡만 멈춘다 |

**`app` 노드 인바운드** (출처: `data` = `172.26.8.249`)

| 포트 | 무엇 | 없으면 |
| --- | --- | --- |
| **40020** | worker RPC | worker 는 등록되는데 **executor 가 안 뜬다.** master 가 "executor 띄워라" 를 못 보낸다 |
| **40010-40014** | executor blockManager (셔플) | 셔플이 있는 잡만 멈춘다 |

**출처 IP 를 상대 노드로 제한할 것.** 40001 같은 포트가 인터넷에 열리면 인증 없는
Spark RPC 가 노출된다.

**웹 UI(8080·8081)는 열지 않는다.** 사람이 보는 것이라 SSH 터널로 충분하다.

```bash
ssh -L 8080:172.26.8.249:8080 <user>@j15a506a.p.ssafy.io
```

> **범위로 여는 게 편하면** `40000-40030` 을 상대 노드 IP 에서만 열어도 된다.
> 위 목록이 그 안에 다 들어간다. 포트를 하나 빠뜨렸을 때의 증상이
> **"조용히 멈춤"** 이라 진단이 오래 걸리므로, 범위 쪽이 실수에 강하다.

> **driver 가 어디서 도는지에 따라 목록이 바뀐다.** 위는 `data` 노드에서
> `spark-submit` 하는 것을 전제한다 (40001·40002 가 `data` 인바운드).
> `app` 에서 제출하면 그 둘이 `app` 인바운드로 뒤집힌다.

### 이게 보이면 성공 — worker 가 둘

```bash
curl -s -o /dev/null -w 'master UI → %{http_code}\n' http://172.26.8.249:8080/json/
curl -s http://172.26.8.249:8080/json/ | grep -c '"id" : "worker-'
```

**주소가 `127.0.0.1` 이 아니라 사설 IP 인 것에 주의할 것.** `spark-env.sh` 가
`SPARK_LOCAL_IP` 를 내보내면 Spark 는 웹 UI 를 포함해 서비스를 **그 주소에만** 바인딩한다.
루프백으로 두드리면 `000`(리스너 없음)이 나오는데, 그건 master 가 죽은 것과 구분되지 않는다.
그래서 위 두 줄을 같이 본다 — HTTP 코드가 `200` 인데 개수가 `0` 이어야 "master 는 살아 있고
worker 가 안 붙었다" 가 증명된다.

`2` 여야 한다. `1` 이면 `app` 노드의 worker② 가 못 붙은 것이고, **거의 항상 네트워크 문제다**
(아래 참고).

### app 노드 worker 에 줄 자격증명 — 루트를 주지 말 것

worker② 의 executor 가 s3a 로 MinIO 를 읽고 쓴다. 그래서 **`app` 노드의 `.env` 에도
MinIO 자격증명이 있어야 한다.** 없으면 worker 는 정상 등록되고 잡도 시작하는데
**쓰기 단계에서 executor 만** `NoAuthWithAWSException` 으로 죽는다.

**루트 자격증명을 복사해 주지 말 것.** `app` 은 인터넷에 노출된 유일한 노드다 —
거기가 뚫리면 수집 데이터 전체를 잃는다. 여기서 서비스 계정을 발급해서 그 키를 준다.

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc admin user svcacct add l "$MINIO_ROOT_USER"'
```

나온 Access Key / Secret Key 를 `app` 노드의 `.env` 에 `MINIO_ROOT_USER` ·
`MINIO_ROOT_PASSWORD` 로 넣는다. **변수 이름이 ROOT 인 것은 `spark-env.sh` 가 그 이름을
읽기 때문이고, 값은 서비스 계정 키다.**

```bash
# app 노드에서 — 값을 바꾼 뒤에는 반드시 재생성한다.
# spark-env.sh 는 컨테이너가 뜰 때 읽히므로 restart 로는 반영되지 않는다.
docker compose up -d --force-recreate spark-worker-2
```

키를 잃거나 유출되면 그 키만 폐기하면 된다.

```bash
docker compose exec minio sh -c 'mc admin user svcacct ls l "$MINIO_ROOT_USER"'
docker compose exec minio sh -c 'mc admin user svcacct rm l <ACCESS_KEY>'
```

### app 노드 api 에 줄 계정 — 주간 수집 운영 API 전용

`app` 노드의 백엔드가 주간 수집 현황을 보여 주고 수동 실행 요청을 받는다
(S15P21A506-347). 그 api 컨테이너가 쓸 계정이다.

⚠ **위 worker② 의 키를 재사용하지 말 것.** 그건 `spark-env.sh` 가 읽는 자리라 이름이
`MINIO_ROOT_*` 이고 권한도 넓다. 여기는 `_ops/weekly/` 밖으로 나갈 일이 없다.

권한 내용은 [pipeline/minio/policies/ops.json](../../../pipeline/minio/policies/ops.json).

| | |
| --- | --- |
| 목록 | `pickage-raw` 의 `_ops/weekly/` prefix **만** |
| 읽기 | `_ops/weekly/**` |
| **쓰기** | **`_ops/weekly/*/manual-request.json` 만** |
| 삭제 | **없다** |

**`run.json` 에 못 쓰는 것이 이 계정의 핵심이다.** 그 객체의 필자는 수집 러너 하나뿐이고,
그래서 러너가 잠금 없이 읽고-고쳐-쓰기를 한다. 백엔드가 같이 쓰기 시작하면 그 전제가
무너진다. 여기서는 그걸 **규약이 아니라 권한으로** 막는다 — 코드가 실수해도 저장소가 거부한다.

**1. 정책을 만든다.**

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose exec -T minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && cat > /tmp/p.json && mc admin policy create l pickage-ops /tmp/p.json' < ../../../pipeline/minio/policies/ops.json
```

**2. 사용자를 만들고 정책을 붙인다.**

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; S=$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9); mc admin user add l pickage-ops "$S" >/dev/null && mc admin policy attach l pickage-ops --user pickage-ops >/dev/null && printf "ACCESS %s\nSECRET %s\n" pickage-ops "$S"'
```

나온 값을 `app` 노드의 `deploy/prod/app/.env` 에 `PICKAGE_OPS_S3_ACCESS_KEY` ·
`PICKAGE_OPS_S3_SECRET_KEY` 로 넣고 api 를 다시 만든다.

⚠ **`PICKAGE_` 를 빼지 말 것.** 백엔드가 읽는 프로퍼티가 `pickage.ops.s3.*` 이고,
스프링이 **이름만으로** 이어 준다 — `application-prod.yaml` 에 배선이 없다. 이름이
어긋나면 오류가 아니라 **조용히** 기본값으로 떨어져서, 값을 제대로 넣고도 운영 API 가
"설정이 없습니다" 로만 답한다 (S15P21A506-347).

**3. 권한이 의도대로인지 확인한다.**

여섯 가지가 전부 맞아야 한다. 특히 2번(`ListBucket` 의 prefix 조건)과 4번이 중요하다 —
2번이 틀리면 목록 조회가 조용히 비고, 4번이 뚫려 있으면 이 계정을 만든 의미가 없다.

```bash
docker compose exec -T minio sh -c '
mc alias set chk http://127.0.0.1:9000 <ACCESS> <SECRET> >/dev/null
echo "1 상태 읽기     :"; mc cat chk/pickage-raw/_ops/weekly/ 2>&1 | head -1
echo "2 prefix 목록   :"; mc ls  chk/pickage-raw/_ops/weekly/ >/dev/null 2>&1 && echo 허용 || echo "거부(문제!)"
echo "3 우편함 쓰기   :"; echo "{}" | mc pipe chk/pickage-raw/_ops/weekly/2099-01-05/manual-request.json >/dev/null 2>&1 && echo 허용 || echo "거부(문제!)"
echo "4 run.json 쓰기 :"; echo "{}" | mc pipe chk/pickage-raw/_ops/weekly/2099-01-05/run.json      >/dev/null 2>&1 && echo "허용(문제!)" || echo 거부
echo "5 원본 읽기     :"; mc ls  chk/pickage-raw/depsdev/ >/dev/null 2>&1 && echo "허용(문제!)" || echo 거부
echo "6 삭제          :"; mc rm  chk/pickage-raw/_ops/weekly/2099-01-05/manual-request.json >/dev/null 2>&1 && echo "허용(문제!)" || echo 거부'
```

> `mc admin` 하위 명령 구성은 릴리스마다 바뀐 이력이 있다. 이 절은 로컬(더 새 `mc`)에서
> 확인했으므로, 이 노드의 더 오래된 이미지에서 안 되면 `mc admin policy --help` 를 먼저 볼 것.

### GPU 서버용 계정

외부 GPU 서버가 학습 데이터를 가져가고 **모델을 올릴 때** 쓴다.
권한 내용은 [pipeline/minio/policies/gpu.json](../../../pipeline/minio/policies/gpu.json).

| | |
| --- | --- |
| 읽기 | `pickage-raw` · `pickage-curated` |
| **쓰기** | **`pickage-mlflow-artifacts` 만** |
| 삭제 | **없다.** 어느 버킷이든 |

**원본에 못 쓰는 것이 이 계정의 핵심이다.** 쓰기가 열린 곳은 학습 산출물 버킷 하나뿐이고,
거기 있는 것은 다시 만들 수 있다. `pickage-raw` 의 소급 불가능한 수집분은 그대로 보호된다.

> 멀티파트 권한(`AbortMultipartUpload`·`ListMultipartUploadParts`·
> `ListBucketMultipartUploads`)이 들어 있다. **빠뜨리면 작은 파일만 되고 132 MiB 모델만
> `AccessDenied`** 가 나서 진단이 오래 걸린다.

**1. 정책을 만든다** — JSON 을 stdin 으로 컨테이너에 밀어 넣는다.

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose exec -T minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && cat > /tmp/p.json && mc admin policy create l pickage-gpu /tmp/p.json' < ../../../pipeline/minio/policies/gpu.json
```

**2. 사용자를 만들고 정책을 붙인다.**

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; S=$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9); mc admin user add l pickage-gpu "$S" >/dev/null && mc admin policy attach l pickage-gpu --user pickage-gpu >/dev/null && printf "ACCESS %s\nSECRET %s\n" pickage-gpu "$S"'
```

> **이미 `pickage-gpu-readonly` 로 만들어 둔 계정이 있으면** 사용자는 그대로 두고 정책만
> 바꿔 붙인다. **키가 안 바뀌므로 담당자에게 다시 전달할 필요가 없다.**
>
> ```bash
> docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc admin policy attach l pickage-gpu --user pickage-gpu && mc admin policy detach l pickage-gpu-readonly --user pickage-gpu && mc admin user info l pickage-gpu'
> ```
>
> 마지막 `user info` 가 **붙은 정책을 찍는다 — `pickage-gpu` 하나여야 한다.**

**⚠ 출력에 시크릿이 찍힌다.** 채팅·MR·이슈에 붙여넣지 말고 담당자에게 직접 전달할 것.
시크릿은 **다시 볼 수 없다** — 잃으면 사용자를 지우고 다시 만든다.

넘길 사용법은 [pipeline/minio/GPU_ACCESS.md](../../../pipeline/minio/GPU_ACCESS.md) 를 같이 보낸다.

```bash
# 확인
docker compose exec minio sh -c 'mc admin user info l pickage-gpu'
# 폐기
docker compose exec minio sh -c 'mc admin user remove l pickage-gpu'
```

**서비스 계정(`svcacct`)이 아니라 별도 사용자로 만든다.** `svcacct` 는 부모 사용자에
매달려서 루트 자격증명을 회전할 때 같이 흔들리고, 권한도 부모에서 좁히는 형태라
"이 계정이 무엇을 할 수 있나" 를 한눈에 못 본다. GPU 는 외부에서 오래 쓰는 소비자라
정책이 명시된 독립 사용자가 맞고, 폐기도 사용자 하나 지우는 것으로 끝난다.

> ### ⚠ 키만으로는 닿지 않는다
> MinIO 는 루프백과 VPC 사설 IP 에만 바인딩돼 있다. **GPU 서버는 VPC 밖이라
> 키가 있어도 연결이 안 된다.** 당장은 SSH 터널로 쓴다 — 팀원 노트북과 같은 방식이고
> 서버에 되돌릴 설정이 안 남는다.
>
> 설계는 Tailscale 로 묶는 것으로 되어 있다. 터널이 불편해지거나(장시간 전송, 자동화)
> GPU 쪽에서 정기적으로 당겨 가야 하면 그때 도입하면 된다.

### 스모크 잡 — 배치보다 먼저 이걸 돌린다

```bash
docker compose --profile batch exec --user root spark-worker-1 \
  /opt/spark/bin/spark-submit --master spark://172.26.8.249:7077 \
  --total-executor-cores 2 --executor-cores 1 --executor-memory 512m \
  --driver-memory 1g \
  /opt/work/spark/smoke_distribution.py
```

```
EXECUTOR_HOSTS: ['j15a506', 'j15a506a']    ← 호스트가 둘이면 분산 성립
ROWS_READ_BACK: 1000
SMOKE_OK
```

**호스트가 하나만 나오면 분산이 안 된 것이다.** 종료 코드도 1 이 된다.
실제 배치를 먼저 돌리면 실패했을 때 배치 로직인지 클러스터 배선인지 가릴 수 없다.

끝나면 지운다. `pickage-raw` 는 수집 원본이 사는 버킷이라 시험 데이터를 남겨 두지 않는다.

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc rm -r --force l/pickage-raw/_smoke/'
```

`--user root` 가 붙는 이유: 이미지는 `spark`(uid 185) 로 도는데 JAR 캐시 볼륨이
root 소유라 **`spark.jars.ivy` 에 쓸 수 없다.** 제출만 root 로 하면 되고,
worker 데몬과 executor 는 계속 비루트로 돈다 (`exec spark-worker-1 id` → uid=185).
compose 에 `user: root` 를 넣으면 executor 까지 root 가 되므로 그렇게 하지 않았다.

### 막히면 — 거의 다 네트워크다

| 증상 | 원인 |
| --- | --- |
| worker② 가 master 에 안 붙는다 | **7077** 이 막혔다. 2026-09-08 에 양방향 200 으로 확인했으니 이게 원인이면 그 사이 바뀐 것이다 |
| worker 는 등록됐는데 executor 가 안 뜬다 | **40020**(worker RPC)이 `app` 인바운드로 안 열렸다. master 가 executor 를 띄우라고 못 보낸다 |
| job 이 executor 붙는 데서 멈춘다 | **40001·40002** 가 `data` 인바운드로 안 열렸다. 위 방화벽 절의 목록을 다시 볼 것 |
| 셔플이 있는 잡만 멈춘다 | **40010-40014** 가 양쪽에 안 열렸다 |
| master 로그의 worker 주소가 `172.17.x.x` 나 `172.19.x.x` | docker0 이나 컨테이너 IP 를 광고했다. `SPARK_LOCAL_IP` 가 사설 IP 로 설정됐는지 볼 것 |
| executor 만 `NoAuthWithAWSException` | **app 노드의 `.env` 에 MinIO 자격증명이 없다.** 위 "자격증명" 절. 값을 넣은 뒤 `--force-recreate` 까지 해야 반영된다 |
| executor 만 s3a 연결 오류 | `spark-defaults.conf` 의 endpoint 가 **서비스 이름**이면 다른 호스트에서 못 푼다. 사설 IP 여야 한다 |
| `NoSuchMethodError` | `hadoop-aws` 버전이 Spark 내장 Hadoop 과 다르다 ([../spark/README.md](../spark/README.md)) |

> **Windows 에서 `docker compose exec`·`run` 을 쓸 때**: Git Bash 가 컨테이너 안의
> 절대 경로를 윈도우 경로로 바꾼다. `/opt/spark/...` 가 `C:/Program Files/Git/...` 이 되어
> `no such file or directory` 가 난다. **`exec` 만이 아니라 `run` 의 인자도 그렇다** —
> 유사도 배치의 `--package-text /work/...` 가 같은 이유로 깨진다 (확인함).
> `MSYS_NO_PATHCONV=1` 을 앞에 붙이거나 서버에 SSH 로 들어가서 실행할 것.
>
> ⚠ `MSYS_NO_PATHCONV=1` 은 **그 명령의 모든 경로 변환을 끈다.** `-f ../some.yaml` 처럼
> 호스트 경로를 같이 넘기면 그쪽이 대신 깨진다. 서버에서는 이 문제가 아예 없다.

## 아직 없는 것

배선은 자동화 전제로 짜 뒀다. 아래가 갖춰지는 대로 **손댈 것 없이** 돌기 시작한다.

| | 없으면 어디서 멈추나 | 누구 |
| --- | --- | --- |
| ~~`package_text` + `_current.json`~~ | **2026-09-14 게시됨** — `package-text-20260908-v1`. 포인터는 `run_path`·`run_id`·`manifest_sha256`·`collected_date` 를 싣는다(위 "`_current.json` 이 싣는 값") | 데이터 |
| MLflow 에 등록된 모델 | **2단계.** `@production` 이 없다. GPU 가 `run_pipeline.sh` 5단계로 등록한다 | AI |
| **로더** | 배치는 돌지만 `similar_package` 가 비어 있어 **서비스에 안 닿는다** ([../README.md](../README.md) 의 "유사도 결과 로더는 어디서 도나") | 미정 |
| 스케줄러 | 사람이 스크립트를 친다. 위가 서면 timer 가 부르기만 하면 된다 | 인프라 |
| 채점 게이트 | `similarity_batch_pipeline.py` 의 5번이 TODO (S15P21A506-169) | AI |
| 잡의 `s3://` 직접 입출력 | 있으면 `ai-stage`·`ai-collect` 두 단계가 통째로 사라진다 | AI |
| `ai-similarity` 전용 MinIO 키 | 스테이징에 루트 자격증명을 쓰고 있다 (`ai/README.md` 의 B4) | 인프라 |
| MLflow 를 **서버에서** 띄우기 | 로컬 compose 검증까지다 | 인프라 |
| 수집 cron | — | 데이터 |

배포 명령 전반은 [../README.md](../README.md).
