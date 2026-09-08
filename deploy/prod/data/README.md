# `data` 노드 (j15a506a.p.ssafy.io)

수집 결과가 쌓이는 곳이다. **외부에 열린 포트가 없다** — 접속은 SSH 터널로만 한다.

| 서비스 | 무엇 |
| --- | --- |
| `minio` | S3 호환 저장소. 9000 = API(코드가 붙는 곳), 9001 = 웹 콘솔(사람이 보는 곳) |
| `minio-init` | 없는 버킷만 만드는 일회성 컨테이너. `Exited (0)` 이 정상이다 |

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

[.agents/AGENTS.md](../../../.agents/AGENTS.md) 의 "알려진 환경 차이" 에도 적어 두었다.

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

### 5. 진짜 성공 조건 — 재부팅

```bash
sudo reboot
# 다시 접속해서
docker ps
```

**손으로 아무것도 안 했는데 MinIO 가 떠 있어야 한다.** 이게 이 작업의 목적이다 —
`docker run` 으로 띄운 컨테이너는 재부팅 후 돌아오지 않고, 수집이 무인으로 도는 구성에서
그건 **조용한 실패**가 된다. 아무도 모르는 채로 며칠이 지나고,
npm 다운로드 수는 **놓친 기간을 소급 조회할 수 없다.**

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

## 평소

```bash
cd ~/S15P21A506/deploy/prod/data
```

```bash
docker compose ps -a                 # minio = Up (healthy), minio-init = Exited (0)
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
ssh -L 9000:localhost:9000 -L 9001:localhost:9001 <user>@j15a506a.p.ssafy.io
```

터널을 연 채로 브라우저에서 `http://localhost:9001`. **터널을 닫으면 안 보이는 것까지
확인할 것** — 보이는 것만 확인하면 포트가 열려 있어서 보이는 건지 구분이 안 된다.

코드로 붙을 때는 **path-style 접근을 켜야 한다.** boto3·s3fs·Spark 의 기본값은
virtual-host style(`http://버킷명.endpoint/`)이고 MinIO 는 그 주소로 응답하지 않는다.
그냥 붙이면 DNS 오류나 404 가 난다.

```python
config=boto3.session.Config(s3={"addressing_style": "path"})
```

Spark 는 `fs.s3a.path.style.access=true`. 버킷별 역할과 경로 규칙은
[pipeline/minio/README.md](../../../pipeline/minio/README.md).

## 하지 말 것

| | 무슨 일이 생기나 |
| --- | --- |
| `docker compose down -v` | 지금 구성에서는 볼륨 정의만 지우고 `/srv/minio/data` 의 파일은 남는다 (확인함). **단 누가 `driver_opts` 를 지운 뒤라면 진짜로 지워진다** — 습관으로 치지 말 것 |
| `volumes:` 의 `device:` 변경·`driver_opts` 삭제 | MinIO 가 빈 스토리지로 뜬다. **데이터는 `/srv/minio/data` 에 그대로 있는데 컨테이너가 다른 곳을 보는** 상태다 |
| 루트 자격증명 교체 | 발급한 서비스 계정이 못 쓰게 될 수 있다. **수집이 그 키로 붙고 있다** |
| MinIO 버전 올리기 | 콘솔 기능이 축소된 이력이 있다. 백업 → 콘솔 확인 순서로, **이관과 다른 날에** |
| `ports` 의 `127.0.0.1:` 제거 | 자격증명만 통과하면 버킷 전체를 읽고 쓸 수 있는 문이 열린다 |

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

`app` 노드에서는 별도로 올려야 한다 (그쪽은 사용자 트래픽을 받으므로 배치 시각만).

```bash
# app 노드에서
cd ~/S15P21A506/deploy/prod/app
docker compose --profile batch up -d spark-worker-2
```

### 이게 보이면 성공 — worker 가 둘

```bash
curl -s http://127.0.0.1:8080/json/ | grep -c '"id" : "worker-'
```

`2` 여야 한다. `1` 이면 `app` 노드의 worker② 가 못 붙은 것이고, **거의 항상 네트워크 문제다**
(아래 참고).

### 스모크 잡 — 배치보다 먼저 이걸 돌린다

```bash
docker compose --profile batch exec --user root spark-worker-1 \
  /opt/spark/bin/spark-submit --master spark://172.26.8.249:7077 \
  --total-executor-cores 2 --executor-cores 1 --executor-memory 512m \
  /opt/work/spark/smoke_distribution.py
```

```
EXECUTOR_HOSTS: ['j15a506', 'j15a506a']    ← 호스트가 둘이면 분산 성립
ROWS_READ_BACK: 1000
SMOKE_OK
```

**호스트가 하나만 나오면 분산이 안 된 것이다.** 종료 코드도 1 이 된다.
실제 배치를 먼저 돌리면 실패했을 때 배치 로직인지 클러스터 배선인지 가릴 수 없다.

`--user root` 가 붙는 이유: 이미지는 `spark`(uid 185) 로 도는데 JAR 캐시 볼륨이
root 소유라 **`spark.jars.ivy` 에 쓸 수 없다.** 제출만 root 로 하면 되고,
worker 데몬과 executor 는 계속 비루트로 돈다 (`exec spark-worker-1 id` → uid=185).
compose 에 `user: root` 를 넣으면 executor 까지 root 가 되므로 그렇게 하지 않았다.

### 막히면 — 거의 다 네트워크다

| 증상 | 원인 |
| --- | --- |
| worker② 가 master 에 안 붙는다 | 두 노드 사이 **7077 이 안 열렸다.** `python3 -m http.server 7077` 로 맨 포트부터 확인할 것 |
| worker 는 붙었는데 job 이 executor 붙는 데서 멈춘다 | **동적 포트가 막혔다.** master↔worker 만 열려도 driver↔executor 는 임의의 높은 포트를 쓴다 |
| master 로그의 worker 주소가 `172.17.x.x` 나 `172.19.x.x` | docker0 이나 컨테이너 IP 를 광고했다. `SPARK_LOCAL_IP` 가 사설 IP 로 설정됐는지 볼 것 |
| executor 만 s3a 오류 | `spark-defaults.conf` 의 endpoint 가 **서비스 이름**이면 다른 호스트에서 못 푼다. 사설 IP 여야 한다 |
| `NoSuchMethodError` | `hadoop-aws` 버전이 Spark 내장 Hadoop 과 다르다 ([../spark/README.md](../spark/README.md)) |

> **Windows 에서 `docker compose exec` 를 쓸 때**: Git Bash 가 `/opt/spark/...` 를
> 윈도우 경로로 바꿔서 `no such file or directory` 가 난다.
> `MSYS_NO_PATHCONV=1` 을 앞에 붙이거나 서버에 SSH 로 들어가서 실행할 것.

## 아직 없는 것

MLflow 와 수집 cron 이 이 노드에 올라올 예정이고,
그때 이 `compose.yaml` 에 서비스로 추가된다.

배포 명령 전반은 [../README.md](../README.md).
