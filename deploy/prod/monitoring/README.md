# 서버 모니터링 — 구축 계획 (S15P21A506-362)

**아직 서버에 아무것도 떠 있지 않다.** 파일은 [`app/`](app/)·[`data/`](data/) 에 있고
**로컬 리허설까지는 돌려 봤다**(Phase 0.5). 서버에서 잰 숫자는 아직 하나도 없다 —
단계가 하나씩 서면 그 자리에 실측값과 운영 절차로 바꿔 쓴다.

대상은 두 노드 다다 — `app (j15a506)` · `data (j15a506a)`.
노드 구성과 지금 도는 것들은 [`../README.md`](../README.md) · [`../data/README.md`](../data/README.md).

---

## 1. 보고 싶은 것 → 실제로 필요한 것

| 보고 싶은 것 | 어디서 나오나 | 누가 주나 |
| --- | --- | --- |
| 서버 사양 (코어·RAM·디스크·커널) | `lscpu` `free` `lsblk` — **변하지 않는다** | 모니터링이 아니라 **한 번 실측해 문서에 박을 것** (Phase 0) |
| CPU·메모리·디스크 사용률 | `/proc/stat` `/proc/meminfo` `/proc/diskstats` `statvfs` | 에이전트가 공짜로 준다 |
| 디스크 **여유** | `df` — `/dev/root` 하나에 DB·도커·MinIO·백업이 다 있다 | 에이전트 + **알람이 진짜 필요한 항목** |
| 도커 컨테이너 상태 | `/sys/fs/cgroup`(자원) + Docker API(이름·상태·재시작 횟수·health) | 에이전트 + 도커 소켓 |
| 프로세스 | `/proc/<pid>` | 에이전트. 단 **호스트 PID 네임스페이스가 필요**하다 (4절) |
| **배치 상태** | `pickage-weekly` systemd 유닛 (`data` 노드) | 에이전트 + dbus. **계획 중에 생겼다** (6절) |

여섯 다 기성 에이전트 하나로 끝난다. **배치 상태는 계획을 세울 때 스케줄러가 없어서**
**직접 설계해야 하는 항목이었는데, 그 사이에 systemd timer 가 들어왔다** — 이제 읽기만 하면 된다.

---

## 2. 후보

| | 구성 | 이 서버에서 |
| --- | --- | --- |
| **Netdata** ← 권장 | 컨테이너 **1개**. 대시보드·수집기·알람 내장 | 붙이면 위 5항목이 설정 없이 바로 나온다 |
| Prometheus + node_exporter + cAdvisor + Grafana | 컨테이너 **4~5개** + 대시보드 JSON | 표준이지만 여기서는 비싸다 (아래) |
| Glances / btop | SSH 로 붙어서 본다 | 이력·알람이 없다. **지금 상태**이므로 개선이 아니다 |
| Zabbix | 서버 + DB + 에이전트 | 이 규모에 과하다 |

### 왜 Prometheus 스택이 아닌가

**그 스택이 나빠서가 아니라 이 두 노드의 제약 때문이다.**

- **코어가 2개다** (`app` 노드 — `application-prod.yaml` 의 Hikari 풀 주석이 그 근거다).
  사용자 트래픽·api·postgres 가 이미 그 2코어를 나눠 쓴다. 여기에 scrape + TSDB 쓰기 +
  Grafana 렌더링이 들어간다. 특히 cAdvisor 는 컨테이너 수에 비례해 CPU 를 꾸준히 먹는다.
- **메모리가 배치 시각에 가장 빠듯하다.** `app` 이 약 10g/15Gi, `data` 가 약 14g/15Gi 다
  ([`../README.md`](../README.md) 의 "Spark worker② (상시)", [`../data/README.md`](../data/README.md)).
  **남는 자리에 4~5개를 더 넣는 계획은 배치 시각에 검증된다** — 그때 무엇이 죽는지는 커널이 고른다.
- **일정.** 발표가 2026-09-28 이다. Grafana 대시보드를 그리는 시간에 다른 걸 만든다.

### 나중에 Prometheus 가 필요해지면

Netdata 는 `/api/v1/allmetrics?format=prometheus` 로 **Prometheus 형식을 그대로 내보낸다.**
반대로 Netdata 가 다른 `/metrics` 엔드포인트를 **긁어올 수도 있다**(`go.d` 의 prometheus 수집기).
그래서 지금 Netdata 로 시작해도 나중 선택지가 닫히지 않는다 — Phase 6 이 정확히 그 경로다.

---

## 3. 이 저장소에서 특히 조심할 것

**아래는 전부 이미 리포에 적혀 있는 규칙이다.** 모니터링이라고 예외가 아니다.

| | 왜 | 근거 |
| --- | --- | --- |
| `mem_limit` 과 `memswap_limit` 을 **짝으로** 넣는다 | 한쪽만 쓰면 상한이 조용히 2배가 된다 | [`../README.md`](../README.md) "Swap" |
| 포트를 `0.0.0.0` 에 열지 않는다 | `app` 은 **인터넷에 노출된 유일한 노드**다. Netdata 기본 포트 19999 는 **로그인이 없다** | [`../README.md`](../README.md) "하지 말 것" |
| `env_file:` 을 쓰지 않고 `${}` 치환으로 받는다 | `env_file` 이면 `.env` 의 **아무 줄이나** 바뀔 때 컨테이너가 재생성된다 | [`../README.md`](../README.md) "환경변수만 고쳤을 때" |
| dbengine 디스크 상한을 **명시**한다 | `/dev/root` 하나에 DB·백업·도커가 같이 산다. 09-15 에 이미 56% 였다 | [`../README.md`](../README.md) "백업" |
| **별도 compose 프로젝트**로 띄운다 (`pickage-monitoring-app` · `pickage-monitoring-data`) | `app/compose.yaml` 에 넣으면 배포 잡이 돌 때마다 같이 재생성 후보가 된다. **배포가 흔들릴 때 모니터링은 살아 있어야 한다** | — |

> ⚠ **`app/compose.yaml` 에 서비스를 추가하지 않는다.** 디렉터리를 따로 두는 이유가
> 그것이다. **지금은 `app/` 쪽 파일을 하나도 고치지 않는다** — nginx 노출(Phase 2)을
> 보류했기 때문이다. 살리게 되면 `app/nginx/app.conf` 한 곳만 건드린다.

### 파일 배치 — 노드별로 가른다

두 노드에 각각 뜨고 **설정이 다르다**(parent / child). `../app/` 과 `../data/` 를 가른 것과
같은 이유다 — `cd` 만 하면 `-f` 가 필요 없고, 노드별 값이 섞이지 않는다.

```
deploy/prod/monitoring/
├── README.md               ← 이 문서
├── app/    parent   compose.yaml · netdata.conf · status.html · stream.conf.example · .env.example
└── data/   child    compose.yaml · netdata.conf · stream.conf.example · .env.example
```

compose 프로젝트 이름도 가른다 — `pickage-monitoring-app` · `pickage-monitoring-data`.
**운영 스택(`pickage-app`·`pickage-data`)과도 다른 이름이다.** 같으면
`docker compose down` 한 번에 운영 DB 나 MinIO 가 같이 내려간다.

`stream.conf` 와 `.env` 는 커밋되지 않는다. 각각 `.example` 을 복사해 채운다.

### 서버에서는 `~/S15P21A506` 에서 띄운다 — ⚠ `/srv/pickage/repo` 가 아니다

**클론을 새로 만들지 않는다.** 두 노드에 이미 사람용 체크아웃 `~/S15P21A506` 이 있고,
`data` 노드의 minio·mlflow·spark·유사도 배치·주간 타이머가 전부 거기서 돈다
([`../data/README.md`](../data/README.md)). 모니터링도 같은 곳을 쓴다.

```bash
cd ~/S15P21A506 && git pull                 # 두 노드에서 각각
cd deploy/prod/monitoring/app               # data 노드는 .../monitoring/data
```

**피해야 하는 것은 `/srv/pickage/repo` 하나다.** 그건 배포 잡의 작업 디렉터리를 가리키는
심볼릭 링크이고, 잡이 매번 `git checkout -f` 와 `GIT_CLEAN_FLAGS` 로 정리한다.

```yaml
GIT_CLEAN_FLAGS: -ffdx -e deploy/prod/app/.env     # .gitlab-ci.yml 의 deploy-app
```

**예외가 `app/.env` 하나뿐이다.** 거기에 모니터링의 `stream.conf`·`.env` 를 두면
**다음 배포에 조용히 사라진다.**

```bash
git -C ~/S15P21A506 log -1 --oneline   # 여기는 사람이 pull 한다. CI 가 안 건드린다
```

> `~/S15P21A506` 은 주간 배치(`pickage-weekly.service` 의 `WorkingDirectory`)도 쓰는
> 체크아웃이다. **배치가 도는 중에 `git pull` 하지 않는다** — 그 회차가 읽는 스크립트가
> 중간에 바뀐다. 확인: `docker ps --filter name=pickage-weekly-run`

---

## 4. 권한을 어디까지 줄 것인가

호스트를 관측하려면 호스트 권한이 든다. 어느 도구를 골라도 같다.
다만 **어디까지 줄지는 단계별로 고를 수 있고, 각 단계가 무엇을 사는지가 다르다.**

| 주는 것 | 얻는 것 | 없으면 |
| --- | --- | --- |
| `/proc` `/sys` `/` 읽기 전용 마운트 | CPU·메모리·디스크·네트워크·**컨테이너별 자원**(cgroup) | 아무것도 안 보인다. **최소선** |
| `pid: host` + `cap_add: SYS_PTRACE` | **프로세스별** CPU·RSS·I/O | 컨테이너 단위까지만 보인다 |
| `/var/run/docker.sock` | 컨테이너 **이름**·상태·재시작 횟수·health | cgroup ID 앞 12자리로만 보인다 |
| `cap_add: SYS_ADMIN` + `apparmor:unconfined` | eBPF 수집기 (syscall·파일 접근 수준) | **필요 없다. 안 준다** |

Netdata 공식 compose 예시는 맨 아래 줄까지 전부 주지만, **위 네 줄은 서로 독립이라 골라 줄 수 있다.**
`SYS_ADMIN` 은 주지 않는다.

> ⚠ **`docker.sock` 에 `:ro` 를 붙여도 API 가 읽기 전용이 되지는 않는다.** `ro` 는 소켓
> *파일*의 권한일 뿐이고, 그 소켓으로 말하는 Docker API 에는 읽기/쓰기 구분이 없다.
> **소켓을 주는 것은 호스트 root 를 주는 것과 같다** — 이 리포는 같은 이유로 이미 한 번
> 소켓 공유를 거부했다 ([`../README.md`](../README.md) 의 "왜 상시로 두나" 1번).

### ✔ 결정 (2026-09-16) — 소켓을 직접 마운트한다

**5절에서 대시보드를 밖에 열지 않기로 했기 때문이다.** 두 결정은 따로 고른 게 아니라
서로를 받친다 — 인터넷에서 이 컨테이너로 들어올 네트워크 경로가 **없다.**
위 선례(Spark worker)가 거부한 것은 *다른 호스트에서 소켓을 조작하는* 구성이었고,
여기서는 같은 호스트의 컨테이너가 자기 호스트의 소켓을 읽는다.

**그래서 한 가지가 조건으로 남는다.**

> ⚠ **5절을 A(nginx 노출)로 바꾸면 이 결정을 같이 다시 본다.** 노출되는 순간
> 소켓을 물린 컨테이너 앞에 인터넷이 생기고, 그때는 **소켓 프록시(`GET /containers` 만
> 통과)를 앞에 세우는 것이 맞다.** 컨테이너 하나가 늘지만 수십 MB 다.

소켓이 실제로 값을 사고 있는지는 **이름이 보이느냐**로 판정한다 (Phase 1 에서 확인).

```bash
curl -s 'http://127.0.0.1:19999/api/v3/contexts' | grep -c 'pickage-app'
# 0 이면 소켓이 안 붙은 것이다 — 컨테이너가 cgroup ID 로만 보인다
```

---

## 5. 어떻게 접속해서 볼 것인가 — ✔ **SSH 터널만** (2026-09-16 결정)

`app` 노드는 밖에서 **80·443·22** 만 열려 있다. **19999 를 인터넷에 열지 않는다.**

```bash
ssh -N -L 19999:127.0.0.1:19999 <계정>@j15a506.p.ssafy.io
# 그다음 브라우저에서 http://127.0.0.1:19999/status.html
#
# ⚠ 이 명령을 외우게 하지 않는다 — scripts/open-monitoring.bat 이 이걸 대신 한다 (8.1)
```

| | 어떻게 | 값 |
| --- | --- | --- |
| **B. SSH 터널만** ← **고름** | 위 명령 | **새로 여는 문이 없다.** 4절의 소켓 결정이 여기에 기댄다 |
| A. nginx 경유 (보류) | `https://j15a506.p.ssafy.io/netdata/` + **basic auth** | 팀 누구나 보고 발표에서도 띄운다. nginx 설정 · `htpasswd` · 소켓 프록시가 같이 는다 |

**B 를 고른 값은 "안 여는 것" 이고, 치르는 값은 둘이다.**

- 팀원이 각자 터널을 열어야 본다. **서버 SSH 접근이 없는 팀원은 못 본다.**
- **발표에서 띄우려면 터널이 열린 노트북이어야 한다.** 그 자리에서 여는 게 아니라
  미리 열어 두고 확인한 상태로 들어간다.

> **A 로 바꾸게 되면** Phase 2 를 살리고 **4절(소켓)을 같이 다시 본다.**
> Netdata 에이전트 대시보드에는 로그인이 없어서, 인증 없이 `/netdata/` 를 열면
> **컨테이너 이름·프로세스 목록·디스크 사용량이 인터넷에 공개된다.**

> ⚠ **`network_mode: host` 를 쓰면 `ports:` 로 바인딩을 제한할 수 없다.**
> (네트워크 인터페이스 메트릭 때문에 host 모드가 권장된다.)
> 그때는 `netdata.conf` 의 `[web] bind to` 로 주소를 직접 묶는다 —
> `app` 노드의 `spark-worker-2` 가 같은 이유로 host 모드이고, 거기서는
> **막는 것이 보안그룹뿐**이라는 경고가 이미 붙어 있다 ([`../README.md`](../README.md)).

---

## 6. 배치 상태 — 스케줄러가 이미 있다

**계획을 세울 때는 스케줄러가 없었는데, 그 사이에 생겼다.**
`data` 노드에 systemd timer 가 들어가 있다 (S15P21A506-273):

```
deploy/prod/data/systemd/pickage-weekly.timer     10분마다 발화
deploy/prod/data/systemd/pickage-weekly.service   oneshot, 한 회차 최대 30h
deploy/prod/data/run-weekly-ingest.sh
```

**하필 systemd timer 다** — 이 문서가 "cron 말고 timer" 라고 권한 그 방식이다.
그래서 **감쌀 것이 없고 읽기만 하면 된다.**

### 무엇을 읽나

| 알고 싶은 것 | 어디서 | 상태 화면에 |
| --- | --- | --- |
| 유닛이 active·failed 인가 | `systemd.service_unit_state` | **나온다** (8.2 의 배치 섹션) |
| 타이머가 켜져 있나 | `systemd.timer_unit_state` | **나온다.** 꺼져 있으면 🔴 문제 |
| 마지막 실행 시각·지난 로그 | `journalctl -u pickage-weekly.service` | **안 나온다** (아래) |
| 처리 행수·소요시간 | 없다 | `batch_run_stats` 테이블 — 별건 |

> ⚠ **"마지막으로 언제 돌았나" 는 메트릭으로 알 수 없다.** `pickage-weekly.service` 는
> oneshot 이고 보통 **1초쯤 뜨다 진다.** 수집 주기가 그보다 길어서 그 순간을 놓친다.
> 그래서 상태 화면은 **지금 상태만** 보여주고 실행 이력은 `journalctl` 명령을 안내한다.
> 없는 것을 있는 척 보여주지 않는다.

**타이머가 꺼진 것을 🔴 문제로 올리는 이유**: 서비스 실패는 10분 뒤 타이머가 다시
시도하므로 한 번 실패가 곧 사고는 아니다. 반면 **타이머가 꺼져 있으면 아무것도 안 돌고,
아무 에러도 안 난다.** 이 리포가 cron 을 피한 이유가 그 침묵이다.

---

## 7. 단계 — 각 단계는 마지막 명령으로 성공을 판정한다

### Phase 0 — 사양을 실측해 박는다 (30분, 에이전트 없이)

지금 리포의 "물리 2코어" · "15Gi" 는 흩어져 있고 출처가 없다. 두 노드에서 각각:

```bash
hostname; lscpu | grep -E '^(Model name|CPU\(s\)|Thread|Core)'; free -h; df -h /; lsblk; uname -r
```

```bash
docker info --format '{{.ServerVersion}} {{.Driver}} {{.NCPU}}cpu {{.MemTotal}}'
```

결과를 이 문서에 표로 남긴다. **여기서 `df -h /` 의 숫자가 Phase 3 의 알람 임계값을 정한다.**

### Phase 0.5 — 로컬 리허설 (✔ 2026-09-16 실행)

**서버에서 처음 돌리지 말 것.** 운영 `app` 스택과 같은 방침이다 ([`../README.md`](../README.md)).
그리고 이 리허설은 실제로 값을 했다 — 아래 "여기서 걸린 것" 이 서버에서 났으면
**컨테이너 메트릭이 조용히 빠진 채로 며칠 갔을 것이다.**

Linux 호스트 전제인 두 가지만 흉내 낸다. 나머지는 운영과 같은 파일이다.

```bash
cd deploy/prod/monitoring/app
printf 'DOCKER_GID=0\n' > .env                      # Docker Desktop 의 소켓은 root:root 다
cp stream.conf.example stream.conf
sed 's|bind to = 127.0.0.1:19999|bind to = 0.0.0.0:19999|' netdata.conf > netdata.rehearsal.conf
```

```bash
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f rehearsal.override.yaml \
  -p pickage-monitoring-rehearsal up -d
```

> **`MSYS_NO_PATHCONV=1`** — Git Bash 가 `/host/proc` 같은 인자를 `C:/Program Files/Git/...`
> 로 바꿔 버린다. 리포의 다른 곳에도 같은 경고가 있다 ([`../data/README.md`](../data/README.md)).

브라우저에서 `http://127.0.0.1:19999`. **첫 화면은 Netdata Cloud 로그인 권유다** —
아래의 "Skip and use the dashboard anonymously" 를 누르면 그냥 들어간다.

끝나면 지운다. 여기서는 `-v` 를 붙인다 — 리허설 데이터고 내 PC 다.

```bash
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f rehearsal.override.yaml \
  -p pickage-monitoring-rehearsal down -v
rm .env stream.conf netdata.rehearsal.conf
```

#### ⚠ 리허설이 운영과 다른 점 — 방어선이 바뀐다

| | 로컬 | 운영 |
| --- | --- | --- |
| 네트워크 | `bridge` + `ports: 127.0.0.1:19999:19999` | `network_mode: host` |
| **밖에 안 열리게 막는 것** | **`ports:` 의 `127.0.0.1` 접두사** | **`netdata.conf` 의 `bind to`** |
| `bind to` | `0.0.0.0` (bridge 안이라 그래야 포트 매핑이 닿는다) | `127.0.0.1` |
| `rslave` | 못 쓴다 (아래) | 쓴다 |
| 보이는 호스트 | Docker Desktop VM (`/proc`·`/etc` 가 전부 VM 것) | 진짜 서버 |

**그래서 로컬에서 잰 CPU·메모리는 서버 값이 아니다.** 모양이 맞는지만 본다.

#### 여기서 걸린 것 (둘 다 실제로 밟았다)

1. **`rslave` 가 거부된다** — `path / is mounted on / but it is not a shared or slave mount`.
   Docker Desktop VM 의 `/` 가 shared/slave 가 아니라서다. 리허설에서만 뗀다.
   **서버에서는 반대로 먹는지 확인한다**: `findmnt -no PROPAGATION /`
2. **컨테이너별 메트릭이 통째로 안 나왔다.** netdata 2.10.1 은 cgroup 루트를
   `<host access prefix>/parent-distro/sys/fs/cgroup` 에서 찾는다. **공식 compose 예시에
   그 마운트가 없다.** `/:/host/parent-distro` 를 붙여서 고쳤고, 그 줄은 이제
   양 노드 compose 에 들어가 있다. 기본 설정 그대로 띄워도 똑같이 실패하는 것을 확인했으므로
   **우리 설정 문제가 아니다** — 서버에서도 같은 줄이 필요하다.

#### 실측 (로컬, 컨테이너 1개짜리 한산한 VM)

| | 값 |
| --- | --- |
| 메모리 | **98 MiB** / 상한 512m |
| CPU | 3.6% (≈ 1코어의 3.6%) |
| 수집 메트릭 | 1,713 · 차트 267 |
| 클라우드 | `agent-claimed: false` · `aclk-available: false` — **밖으로 나가는 연결 없음** |

**서버 값은 다르다.** 컨테이너가 5~7개고 코어가 2개다 — Phase 1 에서 다시 잰다.

### Phase 1 — `app` 노드에 Netdata 하나만, 127.0.0.1 로

파일은 [`app/`](app/) 에 있다. **nginx 는 건드리지 않는다** — 확인은 5절의 SSH 터널로 한다.

```bash
cd ~/S15P21A506/deploy/prod/monitoring/app
cp .env.example .env
getent group docker | cut -d: -f3        # 나온 값을 .env 의 DOCKER_GID 에 넣는다
cp stream.conf.example stream.conf       # Phase 1 에서는 내용을 안 채워도 된다 (받을 child 가 없다)
docker compose up -d
```

`stream.conf` 를 **비워 두더라도 파일은 있어야 한다.** 없으면 Docker 가 그 경로에
디렉터리를 대신 만들어 붙이고, netdata 는 설정을 못 읽는다.

#### 확인 — 네 줄이 다 통과해야 한다

```bash
ss -ltn | grep 19999
# 127.0.0.1:19999 한 줄만. ⚠ 0.0.0.0 이 나오면 즉시 내리고 netdata.conf 의 bind to 를 볼 것
```

```bash
curl -s http://127.0.0.1:19999/netdata.conf | grep -A12 '^\[db\]'
# 적어 둔 retention 값이 그대로 보여야 한다. 1GiB 등 다른 숫자면 이 버전에서 키 이름이
# 다른 것이다 — 모르는 키는 조용히 무시되고 기본값(합 3GiB)이 쓰인다
```

```bash
curl -s 'http://127.0.0.1:19999/api/v3/contexts' | grep -c 'pickage-app'
# 0 이면 DOCKER_GID 가 틀린 것이다 — 컨테이너가 이름 없이 cgroup ID 로만 보인다
```

```bash
du -sh /var/lib/docker/volumes/pickage-monitoring-app_netdatalib   # 하루 뒤. 상한 안이어야 한다
```

#### 그리고 하루 돌려 자기 비용을 잰다

**2코어짜리 노드다.** 여기서 부담이 크면 `data` 노드 확장(Phase 4)을 재검토한다.

```bash
docker stats --no-stream pickage-monitoring-app-netdata-1
```

### Phase 2 — nginx 로 노출 — 🚫 **보류** (5절에서 B 를 골랐다)

살릴 때 하는 일만 적어 둔다. `app/nginx/app.conf` 에 `location /netdata/` + `auth_basic`.
**배포 대상 파일이다.** 설정만 고쳤으므로 다시 굽지 않는다 — `nginx -t` 후 `reload`.
**그리고 4절로 돌아가 소켓 프록시를 같이 세운다.**

```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://j15a506.p.ssafy.io/netdata/                  # 401
curl -sk -u USER:PW -o /dev/null -w '%{http_code}\n' https://j15a506.p.ssafy.io/netdata/       # 200
```

**401 이 먼저 나오는 것이 핵심이다.** 200 이 그냥 나오면 인증이 안 걸린 것이다.

### Phase 3 — 알림 발송 — 🚫 **보류** (2026-09-16 결정: 일단 알람 없이)

> **알람 자체는 꺼지지 않는다.** Netdata 의 기본 알람 룰은 그대로 돌고, 발동하면
> **대시보드 상단에 뜬다.** 보류한 것은 **바깥으로 보내는 경로**뿐이다 —
> 즉 **누가 대시보드를 열어 봐야 알게 된다.**

아래 넷은 **터널을 열 때마다 눈으로 확인할 목록**이고, 나중에 채널이 정해지면
그대로 발송 대상이 된다.

| 무엇 | 왜 이 서버에서 중요한가 |
| --- | --- |
| `/` 디스크 80% · 90% | DB·백업·도커가 한 파티션이다. **백업이 DB 를 멈추게 할 수 있다** |
| 컨테이너 OOM kill | 컨테이너 스왑이 0 이라 **경고 없이 즉사**한다 |
| 컨테이너 재시작 반복 | `restart: unless-stopped` 라 Flyway 실패가 **조용한 무한 재시작**으로 보인다 |
| 호스트 Swap used > 0 | **상한 밖에서 RAM 을 넘겼다는 신호**다 ([`../README.md`](../README.md) "OOM 진단") |

```bash
# 지금 발동 중인 알람 — 터널 없이 서버에서 바로 볼 수 있다
curl -s 'http://127.0.0.1:19999/api/v1/alarms?active' | grep -o '"status":"[A-Z]*"' | sort | uniq -c
```

채널을 붙이게 되면 (Mattermost 는 Slack 호환 incoming webhook 으로 붙는다):

```bash
docker compose exec netdata /usr/libexec/netdata/plugins.d/alarm-notify.sh test   # 채널에 메시지가 와야 한다
```

### Phase 4 — `data` 노드를 같은 화면에 — ✔ **스트리밍** (2026-09-16 결정)

```
data (j15a506a)  child  ──19999──▶  parent  app (j15a506)  ──터널──▶  사람
   mode = ram                       두 노드치를 보관
```

**독립 Netdata 를 두 개 띄우고 터널을 둘 여는 방법도 있었다.** 방화벽 변경이 0 이고,
Spark 웹 UI 를 다루는 기존 방식([`../data/README.md`](../data/README.md) "웹 UI(8080·8081)는
열지 않는다")과 같아서 자연스러운 선택지였다. **스트리밍을 고른 이유는 둘이다.**

- **배치가 두 노드에 걸쳐 있다.** master·worker① 은 `data`, worker② 는 `app` 이다.
  *"worker② executor 가 OOM 났을 때 그 시각 `data` 노드 메모리는 어땠나"* 가
  실제로 물을 질문인데, **같은 타임라인이어야 답이 된다.** 화면이 둘이면 시계를 눈으로 맞춘다.
- **child 를 `mode = ram` 으로 두면 `data` 노드 디스크에 아무것도 안 쓴다.**
  MinIO 데이터와 Spark 셔플이 같은 파티션을 쓰는 노드다 — 독립 두 개로는 이 이득이 없다.

#### 방화벽 한 줄

**`app` 노드 인바운드 19999, 출처 `172.26.8.249`(`data`)** 만. Spark 포트를 같은 방식으로
이미 열어 둔 선례가 있다 ([`../data/README.md`](../data/README.md) "먼저 방화벽").
**child 가 parent 로 접속하므로 방향이 이쪽이다** — 반대로 열면 아무 일도 일어나지 않는다.

인터넷에서 닿는 문은 **여전히 80·443·22 뿐이다.** 5절 결정과 어긋나지 않는다.

#### 순서

```bash
uuidgen        # 한 번만. 양 노드가 이 같은 값을 쓴다 — 팀 비밀 저장소에도 남길 것
```

1. **`app`**: `app/stream.conf` 의 대괄호 안을 그 키로 바꾼다
2. **`app`**: `app/netdata.conf` 의 `bind to` 를 사설 IP 가 든 줄로 바꾼다 (주석에 적어 뒀다)
3. **`app`**: `docker compose up -d`
4. 보안그룹에 위 한 줄을 넣는다
5. **`data`**: `.env`·`stream.conf` 를 만들고 **같은 키**를 넣는다 → `docker compose up -d`

**parent 를 먼저 올린다.** 반대로 하면 child 가 붙을 곳이 없어 재시도 로그만 쌓인다.

#### ⚠ 이 단계에서 제일 틀리기 쉬운 곳

parent 는 사설 IP 에도 바인딩해야 한다 — `bind to = 127.0.0.1:19999 172.26.6.235:19999`.
**`*` 나 `0.0.0.0` 으로 적으면 5절 결정이 조용히 무효가 된다.** 보안그룹만 남고,
`app` 은 인터넷에 노출된 유일한 노드다.

```bash
ss -ltn | grep 19999   # 127.0.0.1 과 172.26.6.235 두 줄. ⚠ 0.0.0.0 이 한 줄이라도 나오면 즉시 되돌린다
```

#### 성공 판정

```bash
# app(parent) 에서 — 두 노드가 다 나와야 한다
curl -s 'http://127.0.0.1:19999/api/v2/nodes' | grep -o '"hostname":"[^"]*"'
```

#### 감수하는 것

**`app` 이 죽으면 `data` 메트릭도 못 본다.** parent 가 잠깐 끊긴 구간은 child 의 메모리
보존분으로 메워지지만(replication), **child 가 재시작되면 그 구간은 없다.**
`mode = ram` 을 고른 대가다 — `data` 노드 디스크를 지키는 쪽을 택했다.

> 이게 실제로 아쉬워지면 child 에 **tier 0 만 아주 작게**(예: 64MB) 디스크 보존을 준다.
> 그때는 `data` 노드의 `df -h /` 와 배치 중 IOPS 를 먼저 보고 정할 것.

### Phase 5 — 배치 상태를 붙인다 (스케줄러는 이미 있다)

**감쌀 것이 없다.** `data` 노드에 `pickage-weekly.timer` 가 이미 들어가 있다(6절).
`/run/dbus` 마운트도 compose 에 있어서 **컨테이너를 다시 만들 필요가 없다.**
Phase 4 로 `data` 노드가 붙으면 배치 섹션이 저절로 채워진다.

확인할 것은 **netdata 가 dbus 에 붙었는지** 하나다. 못 붙으면 유닛이 안 보인다 —
상태 화면은 그 경우 "정보가 안 옵니다" 와 확인 명령을 띄운다(조용히 비우지 않는다).

```bash
docker compose logs netdata | grep -i "SYSTEMD DBUS"   # 아무것도 안 나와야 한다
```

```bash
curl -s 'http://127.0.0.1:19999/api/v2/contexts' | grep -c systemd.service_unit_state
# 1 이어야 한다. 0 이면 dbus 를 못 본 것이다
```

```bash
systemctl list-timers 'pickage-*'                 # 마지막·다음 실행 (메트릭에는 없다)
journalctl -u pickage-weekly.service -n 50        # 지난 회차 로그
```

> ⚠ **로컬 리허설로는 이 단계를 검증할 수 없다.** Docker Desktop VM 에 systemd 가 없어서
> netdata 가 `Failed to connect to system bus` 로 끝난다(2026-09-18 확인).
> 상태 화면의 배치 섹션은 응답을 주입해 네 경우(대기·실행 중·실패·타이머 꺼짐)를
> 확인했지만, **메트릭 이름이 실제로 맞는지는 서버에서 처음 확인된다.**

### Phase 6 (선택) — 애플리케이션 메트릭

지금 actuator 는 **`health` 만, `show-details: never`** 로 닫혀 있다 (`application-prod.yaml`).
**그 줄을 느슨하게 하지 않는다** — 운영에서 `/actuator/env` 로 DB 비밀번호가 보이는 걸
막는 줄이다. 대신:

- `management.server.port` 로 **별도 포트**를 열고 `127.0.0.1` 에만 바인딩
- 거기에만 `prometheus` 엔드포인트를 노출, `micrometer-registry-prometheus` 추가
- Netdata 가 그 주소를 긁는다 (`go.d` prometheus 수집기)

**nginx 에서 `/actuator/prometheus` 를 절대 프록시하지 않는다.** 지금 `app.conf` 는
`location = /actuator/health` 로 **정확히 그 하나만** 넘기고 있다 — 그 모양을 유지한다.

---

## 8. 어떻게 보나

**팀에는 리눅스를 다루지 않는 사람도 있다.** 그 사람이 "지금 서버 괜찮아?" 를 물었을 때
터널·트리·차트 267개를 설명하게 되면 그 도구는 안 쓰이게 된다. 그래서 입구를 둘로 나눈다.

| 누가 | 무엇을 | 어떻게 |
| --- | --- | --- |
| **누구나** | "지금 괜찮은가" | `scripts\open-monitoring.bat` **더블클릭** → `/status.html` |
| 원인을 찾는 사람 | "그때 무슨 일이 있었나" | 같은 창에서 netdata 대시보드로 |

### 8.1 더블클릭 한 번 — `scripts/open-monitoring.*`

리포의 `new-branch` · `setup-hooks` 와 같은 `.sh`/`.bat` 쌍이다.

```
scripts\open-monitoring.bat                  (Windows — 더블클릭)
sh scripts/open-monitoring.sh                (macOS / Linux / Git Bash)
```

SSH 터널을 열고 브라우저까지 띄운다. **끝낼 때는 창을 닫으면 된다**(sh 는 Ctrl+C).
대상 서버와 키는 필요하면 환경변수로 바꾼다 — `PICKAGE_SSH_TARGET` · `PICKAGE_SSH_KEY`.

> **19999 가 이미 열려 있으면 터널을 또 열지 않고 브라우저만 연다.** 두 번 열면 ssh 가
> `bind: Address already in use` 만 찍고 **포워딩 없이 계속 돌아서**, 연결된 줄 알고
> 한참 헤매게 된다. (`nc` 가 아니라 `curl` 로 검사한다 — Git Bash 에 `nc` 가 없다)

### 8.2 "지금 어때" 한 장 — `/status.html`

[`app/status.html`](app/status.html) 을 netdata 웹 루트에 마운트해서 **같은 포트로 같이
서빙한다.** 그래서 팀원이 설치하거나 설정할 것이 없고, 링크 하나면 된다.

```
http://127.0.0.1:19999/status.html
```

신호등(🟢🟡🔴) 하나 + 노드별 숫자 + **컨테이너 목록** + **배치 상태**. 10초마다 저절로
갱신되고, **터널이 끊기면 그 사실을 빨간 화면으로 말해 준다**(무한 로딩으로 두지 않는다).

오른쪽 위 **`지금 확인`** 버튼은 주기를 기다리지 않고 바로 다시 읽는다 — 배포 직후나
누가 "지금 어때?" 라고 물을 때 10초를 세고 있을 이유가 없다.

> 버튼은 **겹쳐 돌지 않게 막아 두었다.** 연타하면 쿼리 15개 × N 이 동시에 나가고,
> 응답이 뒤섞여 **오래된 값이 나중에 도착해 화면을 덮을 수 있다.**
> (동시 호출 3번에 실제로 한 번만 도는 것을 확인했다)

```
🟡 주의   아래 노란색 항목을 보세요. 당장 장애는 아니지만 두면 커집니다.

j15a506-app
  디스크 남음 100%     메모리 6%          CPU 7%
  0.0 / 7.7 GiB 사용   1.0 / 15.4 GiB
  스왑 0 MiB           컨테이너 2          비정상 0
                       실행 중 · 전체 7개

  컨테이너                              상태      메모리    CPU
  pickage-monitoring-app-netdata-1     실행 중    101 MiB   1.7%
  pickage-app-postgres-1               실행 중    412 MiB   3.2%
  멈춘 컨테이너 5개 — pickage-local-api-1, pickage-local-minio-1, …

발동 중인 알람 1건
  WARNING · system_clock_sync_state — …
```

- **비율만 보여주지 않는다.** `100%` 옆에 `0.0 / 7.7 GiB` 가 같이 있어야
  "얼마나 남았지" 가 바로 답이 된다. 메모리도 같다.
- **컨테이너는 이름·메모리·CPU 까지** 준다. 많이 쓰는 것부터 정렬하므로,
  "누가 메모리를 먹고 있나" 가 목록 맨 위다.
- **멈춘 컨테이너는 한 줄로 접는다.** `data` 노드에는 정상적으로 끝나 있는
  일회성 컨테이너(`minio-init` 등)가 있어서, 그것들을 다 펼치면 목록이 그걸로 찬다.
- 컨테이너 목록의 기준은 **Docker API 가 아는 것**이다. cgroup 만 보면
  멈춘 컨테이너가 빠지고 도커 내부 cgroup 이 섞인다.

#### 배치 섹션

맨 아래에 `pickage-*` systemd 유닛이 붙는다 (6절).

```
배치                                    systemd · 실행 이력은 journalctl
  pickage-weekly.service                ● 실행 중
  pickage-weekly.timer                  ● 켜져 있음
  마지막 실행과 로그는 journalctl -u pickage-weekly.service -n 50 ·
  다음 발화는 systemctl list-timers 'pickage-*'
```

| 무엇이 보이면 | 판정 | 왜 |
| --- | --- | --- |
| 타이머 **켜져 있음** + 서비스 대기/실행 중 | 🟢 | 정상. 10분마다 발화한다 |
| 서비스 **실패** | 🟡 주의 | **10분 뒤 타이머가 다시 시도한다.** 한 번 실패가 곧 사고는 아니다 |
| 타이머 **꺼져 있음** | 🔴 문제 | **아무것도 안 돌고 아무 에러도 안 난다.** 이 리포가 cron 을 피한 이유가 그 침묵이다 |
| **정보가 안 옵니다** | — | 유닛 미설치 또는 netdata 가 dbus 에 못 붙음. 확인 명령이 같이 뜬다 |

> ⚠ **로그 줄을 화면에 넣지 않았다.** netdata 의 journal 조회는 별도 함수 API 라
> 검증하지 못했고, **없는 것을 있는 척 보여주지 않는다.** 대신 `journalctl` 명령을
> 그 자리에 적어 둔다 — 복사해서 붙이면 된다.

임계값은 이 저장소의 근거를 그대로 쓴다.

| | 주의 | 문제 | 왜 |
| --- | --- | --- | --- |
| 디스크 남음 | < 20% | < 10% | DB·백업·도커가 한 파티션이다 |
| 메모리 | > 85% | > 95% | 컨테이너 스왑이 0 이라 넘기면 즉사한다 |
| 스왑 사용 | **> 0** | — | **0 이 아니면 상한 밖에서 RAM 을 넘겼다는 신호**다 |
| 비정상 컨테이너 | — | > 0 | healthcheck 실패 |

> **이 페이지는 대시보드를 대신하지 않는다.** 여기는 "지금 괜찮은가" 만 답한다.
> 원인은 아래 8.4 로 간다.

> **커스텀 대시보드(Dashboard 탭)를 쓰지 않은 이유**는 8.5 에 있다 —
> 저장 위치가 **각자 브라우저**라 팀 전체에 줄 수 없다.
> `status.html` 은 **서버가 주는 것**이라 그 문제가 없고, 커밋되니 리뷰도 된다.

### 8.3 평소 "지금 어때" 는 명령이 더 빠르다 (서버에 붙는 사람용)

```bash
docker compose ps                        # 다 Up (healthy) 인가
docker stats --no-stream                 # 어느 컨테이너가 메모리를 먹고 있나
df -h / && free -h                       # 디스크·메모리 여유. Swap used 가 0 이 아니면 신호다
```

### 8.4 "그때 무슨 일이 있었나" — 여기서부터 대시보드다

차트가 **260개**다. 다 볼 필요가 없고, 다 보려고 하면 못 본다.

#### 상단 탭 — 여섯 개 중 넷만 쓴다

| 탭 | 언제 |
| --- | --- |
| **Alerts** | **여기부터 본다.** 빨간 숫자가 0 이 아니면 그것부터 |
| **Metrics** | 차트 전부. 아래 트리 표 |
| **Nodes** | 노드별 한 줄 요약. Phase 4 이후 `app`·`data` 둘이 보인다 |
| **Live** | 지금 이 순간의 프로세스·네트워크 연결 목록 (`top` 에 가깝다) |

#### 어디를 보면 뭐가 나오나 — 오른쪽 트리

| 알고 싶은 것 | 트리 경로 |
| --- | --- |
| CPU·메모리·부하 | `System > Compute` · `System > Memory` |
| **디스크 남은 용량** | `System > Storage` |
| **컨테이너별 자원** (이게 `docker stats` 의 이력판이다) | **`Containers & VMs > Cgroups`** |
| 프로세스 (그룹 단위) | `System > Processes > Apps` |
| 네트워크 | `System > Network` |

#### 시간을 다루는 법 — 이것만 알면 나머지는 따라온다

1. **오른쪽 위 시간 범위**가 기본 **15분**이다. 어제 배치를 보려면 여기부터 바꾼다.
2. **▶ Playing 을 눌러 멈춘다.** 흐르는 채로는 구간을 집기 어렵다.
3. **아무 차트에서나 가로로 드래그**하면 그 구간으로 확대되는데,
   **모든 차트가 같이 움직인다.**

3번이 이 도구를 쓰는 이유 전부다. *"worker② 가 OOM 난 그 순간"* 을 한 차트에서 집으면
**같은 순간의 디스크·네트워크·다른 컨테이너가 전부 같이 맞춰진다.** 명령을 아무리 쳐도
이건 안 된다 — 그리고 Phase 4 로 `data` 노드를 같은 화면에 올리는 이유이기도 하다.

> **첫 화면은 Netdata Cloud 로그인 권유다.** 아래쪽 작은 글씨
> **"Skip and use the dashboard anonymously"** 를 누르면 그냥 들어간다.
> **가입하지 않는다** — 가입(claim)하면 메트릭이 Netdata 서버로 나간다.
> 지금은 `agent-claimed: false` 라 나가는 연결이 없다 (Phase 0.5 에서 확인했다).

### 8.5 안 통한 것 — 기록해 둔다

**둘 다 "화면을 쉽게 만들자" 로 시도했다가 접었다.** 다시 시도하지 않기 위해 남긴다.

#### ① 안 쓰는 수집기를 꺼서 트리 줄이기 — **효과 없음 (측정함)**

netdata 는 **있는 것만 차트를 만든다.** ZFS·btrfs·InfiniBand·무선랜은 애초에 차트가 없어서,
`[plugin:proc]` 에서 꺼도 **컨텍스트가 259 → 259 였다.** 실제 구성은 이랬다.

| | 개수 | |
| --- | --- | --- |
| `system` | 39 | 필요 |
| `cgroup` | 34 | **컨테이너 — 원하던 것** |
| `ipv6`·`ipv4`·`ip`·`net`·`netfilter` | 78 | 실제로 있음 |
| `mem` | 24 | 있음 |
| `user`·`usergroup` | 28 | 사용자별 프로세스 집계 |
| `netdata` | 17 | netdata 자기 자신 |
| `disk`·`disk_ext`·`docker` | 25 | 있음 |

끌 수 있는 것은 많아야 45개(**17%**)고 그마저 장애 때 쓸 수 있는 것들이다.
**처음 보는 사람이 헤매는 문제는 이걸로 안 풀린다** → `status.html` 로 갔다.

#### ② 커스텀 대시보드(Dashboard 탭) — **된다. 다만 브라우저에 저장된다**

`Add chart` 로 담고 `Save`. **Netdata Cloud 로그인 없이 된다.** 그런데 저장 위치가 서버가 아니다.

| 확인한 곳 | 결과 |
| --- | --- |
| 서버(`/var/lib/netdata`) | **없다** |
| `localStorage` | 없다 |
| **IndexedDB `netdata` → `netdata-cache`** | **여기 있다** |

즉 **만든 사람 브라우저에만 남는다.** 이름 옆 `Export dashboard`(⬇)/import(⬆) 로 JSON 을
주고받을 수는 있지만, 고칠 때마다 export·커밋·import 를 다시 해야 해서 결국 안 하게 된다.
**`status.html` 은 서버가 주므로 그 문제가 없다.**

### 8.6 밖으로 나가는 요청이 있나 (✔ 2026-09-16 확인)

대시보드를 한 바퀴 돌며 네트워크 요청을 전부 기록했다.
**약 60건 전부 `127.0.0.1:19999` 였다** — 외부 호스트가 하나도 없다.

> 다만 브라우저 `localStorage` 에 PostHog·Google 계열 키가 만들어지기는 한다.
> 이번 관찰에서는 **나간 요청이 없었다**는 것이지 "추적이 불가능하다" 는 뜻은 아니다.


## 9. 되돌리기

```bash
# 각 노드에서. data(child) 부터 내려야 parent 로그에 연결 실패가 안 쌓인다
cd ~/S15P21A506/deploy/prod/monitoring/<노드> && docker compose down -v   # 모니터링 데이터뿐이다
```

보안그룹 규칙(Phase 4)과 systemd unit(Phase 5)은 따로 걷는다.
**nginx 는 건드릴 게 없다** — Phase 2 를 보류했으므로 `app.conf` 에 들어간 줄이 없다.

> `down -v` 를 여기서는 붙여도 된다. **별도 compose 프로젝트로 띄우는 이득이 이것이다** —
> 운영 볼륨(`pgdata`·`minio-data`)과 이름이 겹치지 않는다.

---

## 10. 결정과 남은 것

### ✔ 정해진 것 (2026-09-16)

| | 정한 것 | 다시 볼 조건 |
| --- | --- | --- |
| 접속 경로 (5절) | **SSH 터널만.** 19999 를 인터넷에 열지 않는다 | 팀원이 못 봐서 막히거나, 발표에서 띄워야 할 때 → Phase 2 |
| 도커 소켓 (4절) | **직접 마운트.** 위 결정 때문에 앞에 인터넷이 없다 | **5절을 A 로 바꾸면 같이 바꾼다** → 소켓 프록시 |
| 알림 (Phase 3) | **발송은 보류.** 알람 룰은 돌고 대시보드에만 뜬다 | 사람이 안 열어 봐서 놓친 일이 생기면 |
| `data` 노드 (Phase 4) | **스트리밍.** child(`data`, ram) → parent(`app`), 한 화면 | `app` 이 자주 죽어 `data` 까지 같이 안 보이면 → 독립 두 개 |
| 배치 스케줄러 (Phase 5) | **보류를 풀었다.** develop 에 timer 가 이미 들어와 있다 | — |

**접속 경로와 소켓은 한 덩어리다.** 하나만 바꾸면 계획이 성립하지 않는다.

### 남은 것

| | 선택지 | 권장 |
| --- | --- | --- |
| 보존량 수치 | 지금 값(합 448MiB) 유지 / 조정 | **Phase 1 을 하루 돌려 본 뒤** 정한다 |
| 이미지 digest 고정 | 태그만 / digest 까지 | **digest 까지** — 첫 pull 후 compose 에 적는다 |
| `data` 노드 착수 시점 | Phase 1 과 동시 / Phase 4 | **Phase 4** — 먼저 한 노드에서 비용을 잰다 |
| 배치 메트릭 이름 | 문서상 이름 그대로 / 서버에서 확인 | **서버에서 확인** — 로컬에 systemd 가 없어 검증 못 했다 |
