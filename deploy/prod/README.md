# 운영 배포

서버가 둘이다. **노드 이름은 `app` 과 `data`** 이고, 서로 다른 호스트라 compose 파일도 둘이다.

| 노드 | 호스트 | 디렉터리 | 무엇이 도나 |
| --- | --- | --- | --- |
| **`app`** | `j15a506.p.ssafy.io`<br>사설 `172.26.6.235` | [`app/`](app/) | postgres · api · **web**(nginx + 프런트 정적파일) · Spark worker② |
| **`data`** | `j15a506**a**.p.ssafy.io`<br>사설 `172.26.8.249` | [`data/`](data/README.md) | minio · **mlflow** · Spark master·worker① · **ai-similarity**(유사도 배치, 1회성) (이후 수집 cron) |

**이 문서는 `app` 노드를 다룬다.** `data` 노드는 명령이 꽤 다르다(`--wait` 를 붙이면 안 된다,
손으로 띄운 컨테이너에서 넘어오는 절차가 있다) — [data/README.md](data/README.md) 를 볼 것.

> **호스트명이 한 글자 차이다.** 그래서 문서에서는 항상 노드 이름과 호스트를 붙여 쓴다 —
> `app (j15a506)` · `data (j15a506a)`. 서버에 붙은 다음에도 `hostname` 을 먼저 확인할 것.

### 이름에 대해
설계 문서의 `#2`·`#1` 이 각각 `app`·`data` 다. **번호는 쓰지 않는다** —
`#2` 가 [기본]인데 번호가 더 커서 처음 보는 사람이 반드시 한 번 틀린다.

`worker` 도 쓰지 않는다. Spark 의 worker 와 충돌하는데, 하필 **Spark worker 하나가
`app` 노드에 올라간다.** "worker 재시작" 이 두 가지로 읽히면 장애 대응 중에 엉뚱한 걸 건드린다.

`data` 는 로컬 `compose.yaml` 의 `--profile data`(minio · spark)와 같은 단어다.
로컬에서 프로파일로 띄우는 그 묶음이 운영에서 `data` 노드에 올라간다.

디렉터리를 나눈 이유는 두 가지다. **명령에서 `-f` 가 사라지고**(파일 이름이 compose 의
기본값이라 `cd` 만 하면 된다), **`.env` 가 노드별로 갈린다.** 한 파일로 두면 `app` 의 `.env`
안에 `data` 의 MinIO 루트 자격증명이 같이 들어가게 된다.

프로젝트 이름도 갈라 둔다 — `pickage-app` · `pickage-data`. 운영에서는 호스트가 달라
안 겹치지만 **로컬 리허설은 한 PC 에서 하므로** 같은 이름이면 컨테이너·볼륨이 충돌한다.

**모든 명령은 해당 디렉터리 안에서 실행한다.**

## 요청이 흐르는 길

```
브라우저 ──443──▶ web (nginx)  ─┬─ /            → 프런트 정적파일 (SPA)
                                ├─ /api/        → api:8080
                                ├─ /swagger-ui/ → api:8080
                                └─ /actuator/health → api:8080
                                         api ──▶ postgres:5432
```

`api` 와 `postgres` 는 **호스트 밖에서 못 닿는다.** 들어오는 문은 nginx 의 80·443 뿐이다.
(80 은 443 으로 되돌려 보내기만 한다)

> ### ⚠ 백엔드 컨트롤러는 `/api` 로 시작해야 한다
>
> 프런트가 `import.meta.env.VITE_API_BASE_URL ?? '/api'` 를 쓴다
> (`frontend/src/api/client.ts`). nginx 는 **경로를 고치지 않고 그대로 넘긴다** —
> `proxy_pass` 끝에 `/` 를 붙여 `/api` 를 잘라 내면 브라우저가 보는 경로와 백엔드가
> 받는 경로가 달라져서 로그·Swagger·에러 메시지가 전부 어긋난다.
>
> 그래서 컨트롤러를 `@RequestMapping("/api/packages")` 처럼 쓴다.
> `server.servlet.context-path` 로 잡지 말 것 — actuator 와 Swagger 까지 같이 끌려가서
> 컨테이너 healthcheck 가 깨진다.

---

## 서버에 올리기 전에 — 로컬 리허설

**서버에서 처음 돌리지 말 것.** 여기서 걸리는 문제는 서버에서도 그대로 걸린다.

인증서만 흉내 낸다. 나머지는 운영과 같은 파일이다.

```bash
LE=/tmp/le && mkdir -p $LE/live/j15a506.p.ssafy.io
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "//CN=j15a506.p.ssafy.io" \
  -keyout $LE/live/j15a506.p.ssafy.io/privkey.pem \
  -out    $LE/live/j15a506.p.ssafy.io/fullchain.pem
printf 'ssl_session_cache shared:le_nginx_SSL:10m;\nssl_protocols TLSv1.2 TLSv1.3;\n' > $LE/options-ssl-nginx.conf
openssl dhparam -out $LE/ssl-dhparams.pem 2048        # ⚠ 2048. 1024 로 만들면 nginx 가 거부한다
```

```bash
cd deploy/prod/app
printf 'POSTGRES_DB=pickage\nPOSTGRES_USER=pickage\nPOSTGRES_PASSWORD=rehearsal\nAPI_TAG=rehearsal\nWEB_TAG=rehearsal\n' > /tmp/rehearsal.env
cat > /tmp/rehearsal.override.yaml <<'YAML'
services:
  api:
    ports: !reset []          # 로컬 개발 스택이 8080 을 쓰고 있으면 충돌한다
  web:
    volumes:
      - /tmp/le:/etc/letsencrypt:ro
YAML
docker compose --env-file /tmp/rehearsal.env -f compose.yaml -f /tmp/rehearsal.override.yaml up -d --wait --wait-timeout 200
```

확인 (Windows 는 `curl` 이 아니라 **`curl.exe`** — PowerShell 의 `curl` 은
`Invoke-WebRequest` 별칭이라 `-s` 를 못 읽는다):

```bash
H="Host: j15a506.p.ssafy.io"
curl.exe -s  -o /dev/null -w '%{http_code}\n'      -H "$H" http://127.0.0.1/          # 301
curl.exe -sk -o /dev/null -w '%{http_code}\n'      -H "$H" https://127.0.0.1/         # 200 SPA
curl.exe -sk -o /dev/null -w '%{http_code}\n'      -H "$H" https://127.0.0.1/analyze  # 200 (SPA 딥링크)
curl.exe -sk -H "$H" https://127.0.0.1/actuator/health                                # {"status":"UP"}
curl.exe -sk -o /dev/null -w '%{http_code}\n' -H "$H" https://127.0.0.1/swagger-ui/index.html  # 200
```

`/analyze` 가 **200 인 것이 중요하다.** 404 면 SPA 딥링크가 깨진 것이고,
새로고침할 때만 드러나서 데모 중에 발견하게 된다.

끝나면 지운다. 여기서는 `-v` 를 붙인다 — **리허설 데이터고 내 PC 다.**

```bash
docker compose --env-file /tmp/rehearsal.env -f compose.yaml -f /tmp/rehearsal.override.yaml down -v
docker rmi pickage-api:rehearsal pickage-web:rehearsal
```

---

## 최초 1회 (서버에서)

### 1. 호스트 nginx 를 끈다

```bash
sudo systemctl disable --now nginx
```

nginx 가 컨테이너로 들어왔다. 호스트 것을 켜 두면 **80·443 을 먼저 잡고 있어서
`up` 이 실패한다.** 설정은 `deploy/prod/app/nginx/app.conf` 가 소유한다.

인증서는 호스트의 certbot 이 만든 것을 **그대로 읽어 쓴다**(`/etc/letsencrypt` 읽기 전용 마운트).
옮기거나 복사하지 않는다.

> **호스트 nginx 를 끄면 certbot 자동 갱신이 멈춘다.** 이 프로젝트에서는 괜찮다 —
> 인증서 만료가 **2026-11-30**, 최종 발표가 **2026-09-28** 이다. 확인했다.
> 일정이 밀리면 갱신을 webroot 방식으로 바꿔야 한다.

### 2. `.env` 를 만든다 — 실체는 `/srv/pickage/app.env` 다

```bash
sudo mkdir -p /srv/pickage && sudo chown gitlab-runner:gitlab-runner /srv/pickage
cp deploy/prod/app/.env.example /tmp/app.env
openssl rand -base64 24        # 나온 값을 POSTGRES_PASSWORD 에 넣는다
sudo install -o gitlab-runner -g gitlab-runner -m 600 /tmp/app.env /srv/pickage/app.env && rm /tmp/app.env
```

```bash
sudo -u gitlab-runner grep -c '^POSTGRES_PASSWORD=.' /srv/pickage/app.env   # 1 이면 채워졌다
```

**체크아웃 안이 아니라 `/srv/pickage/app.env` 에 두는 이유**는 배포가 CI 로 넘어갔기
때문이다. 배포 잡은 매번 새 작업 디렉터리에서 돌고 그 안의 추적되지 않는 파일은 지워진다.
파일을 바깥에 두고 **배포 잡이 `.env` 심볼릭 링크를 걸어** 쓴다
([`deploy/ci/README.md`](../ci/README.md) 의 "배포 러너").

채우지 않고 `up` 하면 **컨테이너를 만들기 전에 멈추고 어느 변수가 비었는지 알려 준다.**
스프링은 그 말을 안 해 주기 때문에(빈 값을 문자열 그대로 넘긴다) 검사를 compose 로 앞당겼다.

`.env` 는 커밋되지 않는다. **서버에 한 번 두고 계속 쓴다.** CI 는 이 파일을 만들지 않고
`API_TAG` · `WEB_TAG` 두 줄만 갈아 끼운다.

> ⚠ **두 벌을 만들지 말 것.** 예전 체크아웃(`~/S15P21A506/deploy/prod/app/.env`)에 파일이
> 남아 있으면, 거기서 손으로 `up` 한 날 CI 가 아는 태그와 실제로 뜬 태그가 갈린다.
> 옮겼으면 원본은 남기지 않는다.

### 3. 자격증명은 어디에 사나

| 값 | 어디 | 누가 바꾸나 |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | `/srv/pickage/app.env` | **사람이 한 번.** 그다음 안 바꾼다 |
| `API_TAG` · `WEB_TAG` | `/srv/pickage/app.env` | **배포 잡이 매번** (`sed` 로 갈아 끼운다). 비밀이 아니다 |

**"env 를 바꿀 때마다 손으로 해야 하나" 의 답은 아니다.** 비밀은 한 번 정하고 안 바꾸고,
매번 바뀌는 건 이미지 태그뿐인데 그건 배포가 알아서 한다.

#### GitLab CI/CD 변수로 옮길 수도 있다

GitHub Actions 의 Secrets 에 해당하는 것이 **Settings → CI/CD → Variables** 다.
**Protected**(보호 브랜치 job 에만 노출) + **Masked**(로그에서 가려짐) 로 두고 배포 job 이
`.env` 를 만들게 할 수 있다.

```yaml
- printf 'POSTGRES_DB=%s\nPOSTGRES_USER=%s\nPOSTGRES_PASSWORD=%s\n' \
    "$POSTGRES_DB" "$POSTGRES_USER" "$POSTGRES_PASSWORD" > .env
```

**얻는 것**: 서버가 날아가도 자격증명이 남는다. 서버 `.env` 가 유일본이면
**PostgreSQL 볼륨은 살아 있는데 비밀번호를 몰라 못 여는** 상황이 생길 수 있다.

**잃는 것**: 비밀의 사본이 하나 늘고, 그 사본은 **Maintainer 이상이면 누구나 읽을 수 있다.**
보호 브랜치의 job 은 그 값을 출력할 수도 있다.

**지금은 서버에 두고 있다.** 대신 **자격증명을 팀 비밀 저장소에도 반드시 남길 것** —
서버 `.env` 가 세상의 유일본이면 안 된다. 그게 CI 변수를 쓰는 진짜 이유고,
비밀 저장소가 그 역할을 이미 한다면 CI 변수는 사본을 하나 더 만드는 것에 가깝다.

> **Masked 의 조건**: 값이 8자 이상이고 공백·개행이 없어야 한다.
> `openssl rand -base64 24` 결과에 섞이는 `+` `/` `=` 는 GitLab 버전에 따라
> 거부될 수 있다 — 거부되면 마스킹이 안 되므로 **로그에 그대로 찍힐 수 있다.**

## Swap — 2 GiB 를 넣고, 컨테이너에는 주지 않는다

**두 노드 모두 원래 Swap 이 0 B 였다.** 상한을 넘기는 순간 완충 없이 OOM Kill 이고,
커널이 무엇을 죽일지 우리가 고를 수 없었다 — **Postgres 를 고를 수도 있다.**

그래서 2 GiB 를 넣었다. 다만 **컨테이너가 쓰라고 넣은 것이 아니다.**

### ⚠ 호스트에 스왑을 넣으면 걸어 둔 상한이 전부 두 배가 된다

Docker 는 `--memory-swap`(compose 의 `memswap_limit`)을 안 주면 **총량을 `mem_limit` 의
2배로 잡는다.** 스왑을 넣기 전에는 스왑이 없어서 이 기본값이 아무 일도 하지 않았다.
넣는 순간부터는 한다. 확인:

```bash
docker run --rm -m 100m alpine cat /sys/fs/cgroup/memory.swap.max
# 104857600   ← RAM 100m 을 다 쓴 뒤 스왑을 100m 더 쓸 수 있다
docker run --rm -m 100m --memory-swap 100m alpine cat /sys/fs/cgroup/memory.swap.max
# 0           ← 스왑 금지
```

> cgroup v2 기준이다. `stat -fc %T /sys/fs/cgroup` 이 `cgroup2fs` 여야 위 경로가 있다
> (양 서버 확인 필요). v1 이면 `memory/memory.memsw.limit_in_bytes` 를 보고, 그 값은
> **RAM+스왑 합계**라서 `mem_limit` 과 같으면 스왑 0 이라는 뜻이다.

그리고 스왑 2 GiB 는 공유 자원이라 **worker① 하나가 먼저 다 먹을 수 있다.**
완충으로 넣은 것이 가장 완충이 필요 없는 쪽으로 간다.

### 그래서 모든 서비스에 `memswap_limit` 을 `mem_limit` 과 같게 박았다

같은 값 = **그 컨테이너는 스왑을 0 쓴다.** 서비스별 이유는 compose 파일의 주석에 있고,
공통된 근거는 둘이다.

- **Spark 는 스왑과 특히 안 맞는다.** JVM 힙이 스왑으로 밀리면 GC 가 디스크를 기다린다.
잡이 죽는 게 아니라 **한없이 느려지다가 heartbeat 타임아웃으로 executor 가 떨어진다.**
지금 Spark 의 실패 증상이 이미 "조용히 멈춘다" 인데 똑같이 생긴 실패 모드가 하나 더
생기는 셈이다 — **깨끗하게 OOM 나고 재시도하는 쪽이 진단 가능하다.**
- **`data` 노드는 스왑 파일이 MinIO 데이터·Docker·Spark 셔플과 같은 파티션을 쓴다.**
스왑 I/O 가 MinIO 읽기와 셔플 쓰기의 IOPS 를 같이 갉아먹는다.

그래서 스왑이 실제로 하는 일은 **컨테이너 상한 밖의 것들** — 호스트 프로세스, Docker
데몬, 배포 중의 Gradle·npm 빌드 — 의 완충과 유휴 페이지 배출이다. **커널이 Postgres 를
고르는 시나리오가 거기서 온다.**

> **`mem_limit`·`memswap_limit`, `--memory`·`--memory-swap` 은 짝으로 쓴다.**
> 한쪽만 쓰면 그것만 상한이 조용히 2배가 되고, 아무 경고도 없다.
> compose 밖에서 `docker run` 하는 코드도 같다 — `pipeline/repository_metrics/` 가 그렇다.
> 짝이 빠진 곳을 찾는 명령:
>
> ```bash
> grep -rn --include='*.py' --include='*.sh' -e '--memory"' . | grep -v 'memory-swap'
> ```
>
> 아무것도 안 나와야 한다.

### 넣기 — 두 노드에서 각각, 1회

먼저 `df -h /` 를 본다. `data` 노드는 이 파티션에 MinIO 데이터가 같이 있다 —
70% 를 넘고 있으면 스왑 파일을 넣을 자리부터 만들어야 한다.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile        # 빼먹으면 서버에 들어온 누구나 스왑 내용을 읽는다
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab      # 재부팅 후에도
grep -c '^/swapfile ' /etc/fstab   # 1 이어야 한다. tee -a 는 다시 돌리면 줄을 또 붙인다
sudo systemctl daemon-reload    # fstab 을 고쳤으니 systemd 에도 알린다
sudo findmnt --verify --fstab   # ⚠ fstab 이 깨지면 다음 부팅이 멈춘다. errors 가 0 이어야 한다
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf
sudo sysctl -p /etc/sysctl.d/99-swap.conf
swapon --show                   # /swapfile 2G 가 보이면 됨
free -h
```

> **`findmnt --verify` 의 경고는 대부분 무해하다.** 봐야 하는 것은 `0 errors` 한 줄이다.
>
> - `cannot detect on-disk filesystem type (Permission denied)` — `sudo` 없이 돌려서
>   블록 디바이스를 못 열었다는 뜻이다. `sudo` 를 붙이면 사라진다.
> - `non-bind mount source /swapfile is a directory or regular file` —
>   **스왑 파일은 원래 정규 파일이다.** findmnt 가 swap 항목을 특별 취급하지 않아서
>   나오는 경고다. 실제로 붙었는지는 `swapon --show` 가 답한다.
> - `your fstab has been modified, but systemd still uses the old version` —
>   위의 `daemon-reload` 를 빼먹었을 때 나온다. 재부팅하면 systemd 가 fstab 을 다시
>   읽으므로 부팅이 깨지는 것은 아니고, **지금 시점의 systemd 뷰만 낡은 것이다.**

`vm.swappiness=10` 은 "상시 경로가 아니라 예비로 쓴다" 는 뜻이다. 기본값 60 은 RAM 에
여유가 있어도 익명 페이지를 내보낸다.

`fstab` 한 줄은 **재부팅으로만 진짜 검증된다.** 이 프로젝트는 이미 재부팅 복귀를 한 번
확인해 뒀다([data/README.md](data/README.md) 의 "진짜 성공 조건") — 스왑을 넣은 뒤 그
확인을 한 번 더 돌리면 `swapon` 까지 같이 검증된다.

**2 GiB 보다 크게 잡지 않는다.** 크면 죽기 전에 느려지는 시간만 길어지고, 그동안
사용자 요청은 계속 타임아웃난다. 여기서 원하는 것은 "더 버티기" 가 아니라
"커널이 고르기 전에 우리가 골라 두기" 다.

#### ✔ 결과 (2026-09-10, 양 노드)

| 확인 | `app` (j15a506) | `data` (j15a506a) |
| --- | --- | --- |
| `swapon --show` | `/swapfile file 2G 0B -2` | `/swapfile file 2G 0B -2` |
| `free -h` 의 Swap | `2.0Gi` / used `0B` | `2.0Gi` / used `0B` |
| `vm.swappiness` | 10 | 10 |
| `stat -fc %T /sys/fs/cgroup` | `cgroup2fs` | `cgroup2fs` |
| `findmnt --verify --fstab` | `0 errors` (sudo 없이 돌려 경고 6) | `0 errors` (경고 1 — 위의 무해한 것) |
| `df -h /` | 4% 사용 (300G 남음, 09-13 — **DB 가 비었을 때**) → 56% (137G, 09-15) | 15% 사용 (264G 남음, 09-13) |

`cgroup2fs` 라서 이 문서의 `memory.swap.max` 경로가 양 노드에서 그대로 통한다.

> **호스트만 끝난 상태다.** 아래 compose 적용 전까지는 컨테이너가 상한 밖으로 스왑을
> 빌릴 수 있다 — 2배씩 늘어난 것이 아니라 **빌릴 수 있는 총량이 스왑 파일 2 GiB 이고
> 먼저 가져가는 컨테이너가 다 쓴다.** 배치 중이라면 worker①(10g)이 그 후보다.
> 적용이 늦어지는 동안 배치나 배포를 돌려야 하면 그때까지 `sudo swapoff /swapfile` 로
> 내려 둔다(fstab 은 그대로 두고, 나중에 `sudo swapon -a`).

### compose 를 같이 올려야 의미가 있다

`memswap_limit` 이 들어간 compose 를 적용하지 않으면 위의 "2배" 가 그대로 남는다.

```bash
cd /srv/pickage/repo/deploy/prod/app && docker compose up -d --wait
```

`data` 노드는 **`--wait` 를 붙이지 않는다** — [data/README.md](data/README.md) 의
"`docker compose up -d --wait` 를 쓰지 말 것".

> **⚠ `git pull` 로는 `SPARK_WORKER_MEMORY` 가 안 바뀐다.** 그 값은 서버의 `.env` 에
> 있고 `.env` 는 커밋되지 않는다 — 저장소에 있는 것은 `.env.example` 뿐이다.
> **두 노드에서 손으로 고쳐야 한다.**
>
> ```bash
> grep SPARK_WORKER_MEMORY .env        # app 은 5g, data 는 7g 여야 한다
> ```
>
> 안 고치면 광고하는 풀이 상한보다 큰 상태가 그대로 남아, **첫 풀사이즈 executor 에서
> OOM Kill** 이다. 산수는 각 노드 `.env.example` 에 있다. 고친 뒤 worker 를 다시 띄운다.

> **⚠ 컨테이너가 재생성된다.** `memswap_limit` 은 생성 시점에 정해지는 설정이라
> 재시작이 아니라 새로 만든다. `postgres` 는 데이터가 볼륨에 있어 안전하지만
> **연결이 끊기고 기동까지 수십 초 멈춘다** — 배치 시각이나 데모 중에 하지 말 것.

적용 확인 (`0` 이면 스왑 금지가 걸린 것이다):

```bash
docker inspect pickage-app-postgres-1 --format '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}'
# 2147483648 2147483648   ← 두 값이 같아야 한다
```

### 되돌리기

호스트만 되돌리면 된다. `memswap_limit` 은 스왑이 없으면 아무 일도 하지 않으므로
compose 는 그대로 둬도 된다.

```bash
sudo swapoff /swapfile          # 스왑에 있던 페이지를 RAM 으로 되읽는다 — 여유가 있을 때 할 것
sudo cp /etc/fstab /etc/fstab.bak     # fstab 이 깨지면 다음 부팅이 멈춘다
sudo sed -i '/swapfile/d' /etc/fstab
findmnt --verify --fstab              # 지운 뒤 문법 확인 — 여기서 통과해야 재부팅해도 된다
sudo rm /swapfile /etc/sysctl.d/99-swap.conf
```

### ⚠ OOM 진단이 한 군데 달라진다

`memswap_limit` 을 박아 둔 서비스는 예전과 똑같이 동작한다. 달라지는 것은
**상한 밖에서 도는 것들**(빌드, 호스트 프로세스)이다 — 이제 OOM 으로 죽는 대신
**서버 전체가 느려지는 것으로 먼저 나타난다.**

그래서 "느린데 아무것도 안 죽었다" 를 볼 때 `free -h` 의 `Swap` used 를 같이 본다.
**여기가 0 이 아니면 어딘가 상한 밖에서 RAM 을 넘겼다는 뜻이다.**

## 평소

```bash
cd /srv/pickage/repo/deploy/prod/app
```

**이 경로에서 한다.** `/srv/pickage/repo` 는 배포 잡이 매번 갱신하는 심볼릭 링크로,
**지금 떠 있는 컨테이너가 물고 있는 파일들이 이 아래 있다** (`nginx/app.conf`, `.env`).
다른 체크아웃에서 같은 명령을 쳐도 compose 프로젝트 이름이 같아 대개는 동작하지만,
**설정 파일을 고치는 명령만은 다른 파일을 고치게 된다** — 아래 nginx reload 가 그렇다.

```bash
git -C /srv/pickage/repo log -1 --oneline   # 지금 서버에 뜬 커밋
```

```bash
docker compose ps                        # 셋 다 Up (healthy) 여야 한다
docker compose logs -f api               # 따라가며 보기
docker compose logs --since 10m web      # 최근 것만
docker compose restart api               # 앱만 다시
docker compose down                      # 내린다. 데이터는 남는다
```

nginx 설정만 고쳤을 때는 **다시 빌드하지 않는다.** 설정은 마운트라 reload 로 끝난다.

```bash
docker compose exec web nginx -t         # 문법 먼저
docker compose exec web nginx -s reload
```

DB 는 컨테이너 안으로 들어간다. 호스트에 5432 를 열어 두지 않았다.

```bash
docker compose exec postgres psql -U pickage -d pickage
```

---

## 배포 — `develop`·`main` 에 머지되면 저절로 뜬다

`.gitlab-ci.yml` 의 `deploy-app` 잡이 아래 "손으로" 와 **같은 순서**를 돌린다
(S15P21A506-223). 잡의 구성과 러너 등록은 [`deploy/ci/README.md`](../ci/README.md).

**스테이징이 없다.** 서버가 한 벌뿐이라 `develop` 에 머지된 것이 곧 사용자가 보는 것이다.

```
MR 머지 → 파이프라인 → 검증 잡 전부 → deploy-app → 수십 초 끊김 → 새 버전
```

확인은 GitLab 의 **Deployments → Environments → `production`** 에서 한다. 어느 커밋이
언제 떴는지가 거기 남는다. 서버에서 보려면 위 "평소" 의 `git -C /srv/pickage/repo log -1`.

> ⚠ **배치 시각에는 머지하지 말 것.** 배포가 배치와 겹치면 메모리가 상한을 넘고, 컨테이너
> 스왑이 0 이라 즉시 OOM Kill 이다 (아래 "하지 말 것"). 배포가 자동이 된 뒤로 이것을
> 막아 주는 것은 **머지 시각뿐이다.**

## 배포 (손으로)

**CI 가 고장 났을 때** 쓰는 절차다. 위 `deploy-app` 이 정확히 이 순서를 돌린다 —
한쪽을 고치면 다른 쪽도 고친다.

한 가지만 다르다. **손으로 할 때는 두 태그를 다 갈아 끼우므로 api·web 이 둘 다 다시 뜬다.**
잡은 내용이 안 바뀐 쪽의 태그를 되돌려 그 컨테이너를 건드리지 않는다
([`deploy/ci/README.md`](../ci/README.md) 의 "안 바뀐 것은 다시 띄우지 않는다").
급할 때 쓰는 절차라 단순한 쪽을 남겨 뒀다 — 대신 **1분 가까이 끊긴다.**

```bash
cd /srv/pickage/repo
git fetch origin && git checkout -f origin/main    # develop 을 띄우려면 origin/develop
cd deploy/prod/app

TAG=$(git rev-parse --short HEAD)
sed -i "s/^API_TAG=.*/API_TAG=$TAG/; s/^WEB_TAG=.*/WEB_TAG=$TAG/" /srv/pickage/app.env

docker compose build
docker compose up -d --wait --wait-timeout 300
```

`.env` 가 아니라 `/srv/pickage/app.env` 를 고치는 것에 주의한다. 체크아웃 안의 `.env` 는
그 파일을 가리키는 심볼릭 링크고, `sed -i` 는 링크를 **덮어써서 일반 파일로 바꿔 버린다** —
그러면 다음 배포부터 태그가 두 곳에서 갈린다.

```bash
ls -l /srv/pickage/repo/deploy/prod/app/.env   # -> /srv/pickage/app.env 여야 한다
```

> 이 체크아웃은 배포 잡의 작업 디렉터리다. **다음 배포가 `git checkout -f` 로 덮어쓴다** —
> 여기서 소스를 고쳐 두지 말 것. 급히 고쳐야 하면 고치고 배포한 뒤, 같은 내용을 MR 로 올린다.

### `--wait` 가 무엇을 해 주나

`--wait` 는 **모든 컨테이너가 healthy 가 될 때까지 기다리고, 안 되면 0 이 아닌 코드로 끝난다.**
없으면 컨테이너가 뜨자마자 명령이 성공으로 끝나서 **앱이 30초 뒤에 죽어도 배포는
초록으로 보인다.** 그래서 이 노드에서는 붙이는 편이 낫다 — 나중에 CI 가 배포할 때
성공 여부를 종료 코드로 판단할 수 있다.

> **`data` 노드에서는 붙이면 안 된다.** 거기에는 일을 마치고 정상 종료하는
> 일회성 컨테이너(`minio-init`)가 있어서 `--wait` 가 그것을 실패로 집계한다 —
> 성공했는데 종료 코드 1 이 나온다. 확인을 `ps -a` 로 한다.
> [data/README.md](data/README.md) 를 볼 것.

확인:

```bash
curl -fsS https://j15a506.p.ssafy.io/actuator/health     # {"status":"UP"}
curl -fsS -o /dev/null -w '%{http_code}\n' https://j15a506.p.ssafy.io/   # 200
```

> 배포 중 **수십 초 끊긴다.** 무중단은 v1 에서 하지 않는다 — api 인스턴스가 하나라
> 블루/그린이 필요하고, 3주 프로젝트에서 그 값을 치를 이유가 없다.

## 환경변수만 고쳤을 때 — 이미지는 그대로다

비밀번호를 잘못 넣었다거나 `SPARK_WORKER_CORES` 를 바꾸는 경우다. `/srv/pickage/app.env`
를 고치고 **Run pipeline 을 누르면** 배포 잡이 그대로 돈다(`develop`·`main` 에서).
손으로 할 거면 `docker compose up -d` 다.

`.env` 는 **빌드 컨텍스트(`backend/`·`frontend/`) 밖**이라 아무리 고쳐도 이미지는 안 바뀐다.
그래서 배포 잡의 "내용이 같으면 태그 유지" 가 그대로 걸리고, **다시 굽지 않는다.** 맞는 동작이다.

컨테이너를 다시 만들지 말지는 compose 가 따로 판단한다. **이미지 이름만 보는 게 아니라
치환까지 끝난 서비스 설정 전체를 해시로 비교**한다. `${POSTGRES_PASSWORD}` 처럼
`compose.yaml` 안에서 치환되는 값은 여기 들어가므로, 고치면 그 서비스가 다시 뜬다.

`app` 노드의 compose 는 **모든 값을 `${}` 치환으로 받는다.** `env_file` 을 쓰는 서비스가
하나도 없다. 그래서 고친 변수를 쓰는 서비스만 다시 뜬다.

| 값 | 쓰는 서비스 | 고치면 다시 뜨나 |
| --- | --- | --- |
| `POSTGRES_*` | postgres · api | ✅ |
| `API_TAG` · `WEB_TAG` | api · web | ✅ |
| `PRIVATE_IP` · `SPARK_MASTER_HOST` · `SPARK_WORKER_*` | spark-worker-2 | ✅ |
| `MINIO_ROOT_USER` · `MINIO_ROOT_PASSWORD` | spark-worker-2 | ✅ |

> **예전에는 spark-worker-2 가 `env_file: ./.env` 로 파일을 통째로 받았다.** 그러면 파일의
> **어느 줄이 바뀌어도** 그 서비스의 설정이 바뀐 것이 되어 worker 가 다시 만들어진다.
> 배포가 매번 `API_TAG`·`WEB_TAG` 를 고치므로, **앱만 배포해도 Spark worker 가 재시작**
> 하고 그때 돌던 배치의 executor 가 같이 죽었다. 2026-09-15 에 compose 29.6.1 로
> 재현해서 확인했다 — `env_file` 쪽만 `Recreated`, 치환 쪽은 `Running` 이었다.
> 그래서 이 컨테이너가 실제로 쓰는 두 값만 이름을 대서 넘기도록 고쳤다.

무엇이 다시 뜰지 미리 보려면:

```bash
docker compose up -d --dry-run
```

`Recreate` 라고 찍힌 서비스만 다시 뜬다. 이 플래그가 없는 버전이면 다음으로 확인한다.

```bash
docker compose config --hash='*'
```

```bash
docker inspect --format '{{.Name}} {{index .Config.Labels "com.docker.compose.config-hash"}}' $(docker compose ps -q)
```

두 값이 다른 서비스가 다시 뜬다. **같은데 반영되어야 한다면 그 서비스만 강제로 만든다.**

```bash
docker compose up -d --force-recreate spark-worker-2
```

> **마운트한 파일의 내용은 여기 안 걸린다.** `nginx/app.conf` 가 그렇다 — 내용을 고쳐도
> compose 가 보는 설정은 그대로라 컨테이너를 다시 만들지 않는다. 그래서 배포 잡이 마지막에
> `nginx -t` 와 `nginx -s reload` 를 따로 친다. 손으로 고쳤을 때도 같다.

## 배포가 실패하면 서버는 어떤 상태인가

배포 잡이 빨간불이어도 **앞 단계까지는 이미 적용된 상태**다. 어디서 멈췄는지에 따라 다르다.

| 어디서 실패했나 | 서버 상태 |
| --- | --- |
| `docker compose build` | 컨테이너는 **그대로 전 버전**이다. 사이트는 멀쩡하다 |
| `up -d --wait` 시간 초과 | **새 컨테이너로 이미 바뀌었고 healthy 가 아니다.** 사이트가 내려가 있다 |
| `nginx -t` | 컨테이너는 새것으로 떴고 **nginx 는 옛 설정으로 돈다.** 사이트는 멀쩡하다 — `nginx/app.conf` 의 문법을 고쳐 다시 배포한다 |
| 마지막 `curl` | 컨테이너는 healthy 인데 nginx·TLS 쪽이 이상하다. 아래 "평소" 의 로그부터 본다 |

> ⚠ **`/srv/pickage/app.env` 의 태그는 "마지막으로 성공한 것" 이 아니라 "마지막으로 시도한
> 것" 이다.** 실패한 배포의 SHA 가 남아 있다. 되돌릴 때 그 값을 기준으로 삼지 말고
> `docker images` 에서 **날짜를 보고** 고를 것 (아래 "롤백").

가장 흔한 실패는 Flyway 다. 마이그레이션이 깨지면 api 가 기동에 실패하고 `--wait` 가
시간 초과로 끝난다. 이때 `restart: unless-stopped` 때문에 **컨테이너가 계속 다시 뜨면서
같은 실패를 반복한다** — 로그가 같은 스택트레이스로 채워지는 것이 그 신호다.

```bash
docker compose logs --since 5m api | head -50
```

**그다음은 롤백이다.** 그리고 `develop` 에 무엇이든 머지되면 배포가 다시 돌아 같은 실패를
반복하므로, 고치는 커밋이 올라갈 때까지 팀에 머지를 멈추라고 알린다.

## 롤백

**태그를 되돌리고 다시 올리는 것이 전부다.**

```bash
cd /srv/pickage/repo/deploy/prod/app
docker images pickage-api --format '{{.Tag}}\t{{.CreatedSince}}'   # 되돌아갈 곳 고르기
docker images pickage-web --format '{{.Tag}}\t{{.CreatedSince}}'

sed -i "s/^API_TAG=.*/API_TAG=<이전 SHA>/" /srv/pickage/app.env    # 프런트만 되돌릴 거면 WEB_TAG 만
docker compose up -d --no-build --wait
```

> ⚠ **롤백은 다음 머지까지만 유효하다.** `develop`·`main` 에 무엇이든 머지되면 배포 잡이
> 그 커밋으로 다시 덮어쓴다. 되돌린 이유가 남아 있다면 **되돌리는 커밋을 MR 로 올려서**
> 통합 브랜치 자체를 고쳐야 한다. 그 전까지는 팀에 알려 머지를 멈춘다.

태그를 둘로 나눠 둔 이유가 이것이다. **API 는 멀쩡한데 화면만 깨진 배포**가 실제로 생기고,
그때 프런트만 되돌릴 수 있다.

`--no-build` 를 붙이는 이유: 이건 **이미 있는 이미지로 돌아가는 동작**이다. 빼면 compose 가
지금 체크아웃된 소스로 그 태그를 다시 구워서, 이름만 옛날이고 내용은 새것인 이미지가 된다.
그러면 롤백이 아니다.

### ⚠ 스키마는 롤백되지 않는다

Flyway 는 앱이 뜰 때 마이그레이션을 적용하고, **되돌리지는 않는다.**
이미지를 되돌려도 테이블은 새 모양 그대로다.

그래서 **`DROP COLUMN` · `RENAME` 이 들어간 배포는 롤백할 수 없다.** 컬럼을 지울 때는
배포를 둘로 나눈다 — 먼저 코드에서 안 쓰게 만들어 배포하고, 다음 배포에서 지운다.

## 백업

```bash
mkdir -p ~/backup
docker compose exec -T postgres pg_dump -U pickage pickage | gzip > ~/backup/pickage-$(date +%F).sql.gz
```

`-T` 가 없으면 TTY 를 붙이려다 출력에 제어문자가 섞여 **복원할 수 없는 덤프**가 나온다.

> ⚠ **덤프가 DB 와 같은 파티션에 쌓인다.** `/dev/root` 하나뿐이라 `~/backup` 도 도커도
> Postgres 도 같은 309G 를 나눠 쓴다. 데이터가 늘수록 덤프도 같이 커지므로, 날짜별로
> 모아 두면 어느 순간 **DB 를 지키려고 만든 것이 DB 를 멈추게 한다.**
>
> ```bash
> du -sh ~/backup && df -h / | tail -1
> ```
>
> 오래된 덤프는 서버 밖으로 내리거나 지운다. 서버에는 최근 것 두어 개면 된다.

---

## 정리 — 여기서 실수하면 롤백을 잃는다

레지스트리가 없다. **이 서버의 로컬 이미지 스토어가 곧 롤백 자산이다.**

```bash
docker image prune -f          # 이름 없는(dangling) 것만 지운다 — 안전
```

```bash
docker image prune -a          # ❌ 절대 금지
docker system prune -a         # ❌ 절대 금지
```

`-a` 는 **지금 컨테이너가 안 쓰는 이미지를 전부** 지운다. 이전 SHA 태그가 여기 해당해서,
한 번 치면 **되돌아갈 곳이 하나도 안 남는다.** 그리고 그 사실은 롤백이 필요한 순간에 알게 된다.

**배포 잡이 이 정리를 대신 한다.** 매 배포 끝에 `pickage-api`·`pickage-web` 의 최근 5개
태그만 남기고 그보다 오래된 태그를 떼고, 일주일 지난 빌드 캐시와 dangling 이미지를 지운다.
컨테이너가 쓰고 있는 이미지는 docker 가 거부하므로 **떠 있는 것은 지워지지 않는다**
(강제하지 않는다). 무엇을 뗐는지는 잡 로그의 `[정리]` 줄에 남는다.

그래서 아래는 **CI 가 못 돌 때**의 절차다. 오래된 태그를 줄여야 하면 **눈으로 보고 하나씩**
지운다. 최근 5개는 남긴다.

```bash
docker images pickage-api --format '{{.Tag}}\t{{.CreatedSince}}' | sort -k2
docker rmi pickage-api:<지울 태그>
```

---

## 하지 말 것

| | 무슨 일이 생기나 |
| --- | --- |
| `docker compose down -v` | **운영 DB 가 사라진다.** 볼륨까지 지우는 옵션이다 |
| `docker image prune -a` | 롤백 대상이 전부 사라진다 (위) |
| `sudo systemctl start nginx` | 호스트 nginx 가 80·443 을 뺏어 **다음 `up` 이 실패한다** |
| `ports: "8080:8080"` | TLS 도 인증도 없는 문이 열린다. `127.0.0.1:` 접두사를 지우지 말 것 |
| `.env` 를 커밋 | 운영 DB 비밀번호가 GitLab 에 남는다. 지워도 히스토리에 남는다 |
| 적용된 `V__` 파일 수정 | checksum 불일치로 **운영 앱이 기동에 실패한다** |
| `API_TAG=latest` | 지금 뜬 게 어느 커밋인지 알 수 없고 롤백할 이름이 없어진다 |
| 배치 시각에 배포 (= **배치 시각에 머지**) | 메모리가 캡을 넘긴다. **컨테이너 스왑은 0 이라 즉시 OOM Kill** — 커널이 Postgres 를 고를 수도 있다 |
| 배포 디렉터리(`/srv/pickage/repo`)에서 소스 고치기 | 다음 배포의 `git checkout -f` 가 덮어쓴다. 고쳤다는 사실만 남고 내용은 사라진다 |
| 체크아웃 안의 `.env` 심볼릭 링크를 `sed -i` | 링크가 일반 파일이 되어 **태그가 두 곳에서 갈린다.** `/srv/pickage/app.env` 를 고칠 것 |

---

## Spark worker② (상시)

이 노드는 배치 때 Spark worker 를 겸한다. **`docker compose up -d` 에 같이 뜬다** —
별도 프로파일이 없다.

master 는 `data` 노드에 있다. 클러스터 확인과 스모크 잡은 거기서 돌린다 —
[data/README.md](data/README.md) 의 "Spark (배치)".

**먼저 방화벽을 열어야 한다.** 이 노드는 `40020`(worker RPC)과 `40010-40014`
(executor blockManager)를 `data` 노드에서 오는 것만 열어 준다. 목록과 이유는
[data/README.md](data/README.md) 의 "먼저 방화벽" 절 — **빠뜨리면 job 이 조용히 멈춘다.**

**MinIO 자격증명이 이 노드의 `.env` 에도 있어야 한다.** executor 가 s3a 로 읽고 쓴다.
없으면 worker 는 정상 등록되고 잡도 시작하는데 **쓰기 단계에서 executor 만 죽는다.**
루트가 아니라 서비스 계정 키를 쓴다 — [data/README.md](data/README.md) 참고.

### 왜 상시로 두나 (09-09 결정)

원래는 배치 전후로 사람이 켜고 끄게 했다. 뒤집은 이유가 셋이다.

1. **켜고 끄는 주체가 문제다.** 그 코드는 `data` 노드의 배치 cron 에서 돌 텐데, 다른
호스트의 컨테이너를 조작하려면 **SSH 키를 주거나 Docker 소켓을 줘야 한다.** 소켓은
호스트 root 와 동등한 권한이다. 1GB 아끼자고 치를 값이 아니다.
2. **아끼는 게 생각보다 없다.** `mem_limit` 은 상한이지 예약이 아니라서, 놀고 있는
worker 데몬은 6.5g 가 아니라 **1GB 안팎**을 쓴다.
3. **위험이 줄지 않는다.** 진짜 부담은 배치 중 executor 5g 가 사용자 트래픽과 부딪히는
것인데, 그건 컨테이너를 언제 띄웠든 똑같다.

> **되돌릴 조건**: 배치 중 이 노드에서 OOM 이 나거나 사용자 응답이 눈에 띄게 느려지면.
> 그때는 실측이 있으니 판단 근거가 생긴다. 설계 문서는 "배치 시각만" 으로 되어 있고,
> 이건 의도적인 이탈이다.

### ⚠ 배치 시각에는 배포하지 말 것

이 노드의 메모리가 이때 가장 빠듯하다.

```
postgres 2g + api 1.6g + web 0.25g + worker②(executor 5g + 데몬 ~1g) ≈ 10g / 15Gi
```

> **`SPARK_WORKER_MEMORY` 는 `mem_limit` 과 짝이다.** 그 값이 executor 힙의 상한이 되고,
> 힙·비힙·worker 데몬(그리고 `data` 노드에서는 driver)이 **같은 cgroup** 에 들어간다.
> 한쪽만 올리면 **첫 풀사이즈 executor 에서 OOM Kill** 이다. 산수는 각 노드의
> `.env.example` 에 적어 두었다.

여기에 **배포가 겹치면 Gradle·npm 빌드가 메모리를 더 먹는다.** 호스트 스왑 2 GiB 는
빌드 쪽 완충이지 컨테이너 완충이 아니다 — **컨테이너에는 스왑을 0 준다**(위 "Swap").
상한을 넘기는 순간 완충 없이 OOM Kill 이고, 커널이 무엇을 죽일지 우리가 고를 수 없다 —
**Postgres 를 고를 수도 있다.**

### `network_mode: host` 인 이유

`spark-worker-2` 는 다른 서비스와 달리 compose 네트워크에 없다. Spark 의 master·driver·
executor 는 **서로를 되부르는데**, bridge 네트워크에서는 컨테이너가 자기 컨테이너
IP(172.19.x.x)를 광고하고 상대 호스트는 그 주소로 라우팅할 수 없다. job 이 시작은 하고
**executor 붙는 데서 조용히 멈춘다.**

대가로 worker 웹 UI(8081)가 `0.0.0.0` 에 붙는다. 막는 것은 보안그룹뿐이다 —
이 노드는 80·443·22 만 열려 있다. **포트를 더 열게 되면 이 줄을 다시 볼 것.**

## 아직 없는 것

| | 지금은 어떻게 되어 있나 |
| --- | --- |
| CI 자동 배포 | 위 "배포 (손으로)" 를 사람이 실행한다. 붙으면 `main` push 로 자동이 된다. **여기 말하는 것은 배포(CD, S15P21A506-223)다** — MR 에서 도는 검증 파이프라인은 붙었고, 안내는 [`deploy/ci/README.md`](../ci/README.md) |
| `data` 노드의 수집 cron | 없다. MLflow 는 올라갔다 ([data/README.md](data/README.md) 의 "MLflow") |
| 유사도 결과 로더 | 없다. 아래 "유사도 결과 로더는 어디서 도나" 에서 **`app` 노드로 정했고**, 코드는 아직 없다 |
| `batch_run_stats` 테이블 | 없다. 분산 증빙은 지금은 스모크 잡의 `EXECUTOR_HOSTS` 출력으로 한다 |

## 유사도 결과 로더는 어디서 도나 — `app` 노드

AI 파이프라인은 **SIM 과 LOAD 가 나뉘어 있다** (`ai/README.md` 의 "방식 C").

```
data 노드   ai/similarity 배치  →  MinIO 산출물 + manifest      ← 여기까지가 컨테이너
app  노드   로더               →  manifest 읽어 similar_packages staging
                                   → RENAME + model_production 포인터 전환
```

`ai/similarity` 이미지는 **PostgreSQL 을 건드리지 않는다** — PG 드라이버가 없다.
DB 에 쓰는 것은 로더뿐이고, **로더는 `app` 노드에서 돈다.**

### 그래서 `5432` 를 열지 않는다

이게 이 결정의 핵심 이득이다. 로더가 postgres 와 같은 호스트에 있으면
`pipeline/postgresql/load.py` 의 `--docker-container` 모드로 **컨테이너 안에서 `psql` 을
실행**한다. 그러면 아래가 전부 필요 없어진다.

| 로더를 `data` 노드에 두면 필요한 것 | `app` 노드에 두면 |
| --- | --- |
| postgres 를 사설 IP 에 바인딩 | **없음** — `ports:` 를 그대로 비워 둔다 |
| 보안그룹 `app` 인바운드 5432 | **없음** |
| `data/.env` 에 운영 DB 비밀번호 사본 | **없음** — 비밀이 한 군데에만 있다 |
| `--psql` + TCP 경로 (덜 검증됨) | **없음** — 실측한 `--docker-container` 를 그대로 쓴다 |

### 그 대신 로더가 MinIO 를 건너서 읽는다

`app` 노드에서 `172.26.8.249:9000` 으로 읽는다. **이 포트는 Spark executor 용으로
이미 열려 있어서 새 규칙이 없다.**

⚠ 다만 `app` 노드는 **인터넷에 노출된 유일한 노드**다. 여기에 두는 MinIO 키는
루트가 아니라 버킷 범위를 좁힌 것이어야 한다 — `app/.env.example` 의 MinIO 절에
같은 경고가 이미 있다.

### 왜 이 배치가 맞나

방식 C 가 SIM 과 LOAD 를 나눈 이유가 **각자를 자기 데이터 옆에 두려는 것**이다.
SIM 은 MinIO 옆, LOAD 는 PostgreSQL 옆. 핸드오프가 MinIO 객체(manifest)라서
두 반쪽이 같은 호스트에 있을 필요가 없다 — 그게 계약으로 나눈 값어치다.

자원도 이쪽이 낫다. `data` 노드는 배치 시각에 12g 를 이미 쓰고 그 남은 여유를
유사도 배치가 원한다. `app` 노드는 약 4.6g 가 남고, 적재량도
`similar_packages` 는 패키지당 최대 3행이라 **30만행 수준**이다 —
58분 걸린 package·version 5,418만행과는 규모가 다르다.

> **로더를 올릴 때**: `profiles` + `run --rm` 1회성으로 두고
> `mem_limit` 과 `memswap_limit` 을 **짝으로** 넣는다 (위 "Swap").
> 그리고 이 노드는 사용자 트래픽을 받으므로 **배포·배치와 시간을 겹치지 않게** 한다.
