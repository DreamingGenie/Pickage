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

## Swap — 이 노드는 파티션을 같이 쓴다

두 노드에 스왑 2 GiB 가 있고, **모든 컨테이너에는 `memswap_limit` 으로 스왑을 0 준다.**
절차와 이유는 [../README.md](../README.md) 의 "Swap" — **두 노드에서 같은 절차를 돈다.**

이 노드에서만 추가로 걸리는 것: `/swapfile` 이 **MinIO 데이터(`/srv/minio/data`)·Docker·
Spark 셔플과 같은 파티션**에 놓인다. 스왑을 실제로 쓰기 시작하면 MinIO 읽기와 셔플 쓰기의
IOPS 를 같이 갉아먹는다. `df -h /` 를 먼저 보고, 스왑을 2 GiB 보다 크게 잡지 말 것.

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

### GPU 서버용 읽기 전용 계정

외부 GPU 서버가 학습 데이터를 가져갈 때 쓴다. **`pickage-curated` 읽기만** 된다.
권한 내용은 [pipeline/minio/policies/gpu-readonly.json](../../../pipeline/minio/policies/gpu-readonly.json).

**1. 정책을 만든다** — JSON 을 stdin 으로 컨테이너에 밀어 넣는다.

```bash
cd ~/S15P21A506/deploy/prod/data
docker compose exec -T minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && cat > /tmp/p.json && mc admin policy create l pickage-gpu-readonly /tmp/p.json' < ../../../pipeline/minio/policies/gpu-readonly.json
```

**2. 사용자를 만들고 정책을 붙인다.**

```bash
docker compose exec minio sh -c 'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; S=$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9); mc admin user add l pickage-gpu "$S" >/dev/null && mc admin policy attach l pickage-gpu-readonly --user pickage-gpu >/dev/null && printf "ACCESS %s\nSECRET %s\n" pickage-gpu "$S"'
```

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

> **Windows 에서 `docker compose exec` 를 쓸 때**: Git Bash 가 `/opt/spark/...` 를
> 윈도우 경로로 바꿔서 `no such file or directory` 가 난다.
> `MSYS_NO_PATHCONV=1` 을 앞에 붙이거나 서버에 SSH 로 들어가서 실행할 것.

## 아직 없는 것

MLflow 와 수집 cron 이 이 노드에 올라올 예정이고,
그때 이 `compose.yaml` 에 서비스로 추가된다.

배포 명령 전반은 [../README.md](../README.md).
