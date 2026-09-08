# 운영 배포

서버가 둘이다. **노드 이름은 `app` 과 `data`** 이고, 서로 다른 호스트라 compose 파일도 둘이다.

| 노드 | 호스트 | 디렉터리 | 무엇이 도나 |
| --- | --- | --- | --- |
| **`app`** | `j15a506.p.ssafy.io` | [`app/`](app/) | postgres · api · **web**(nginx + 프런트 정적파일) |
| **`data`** | `j15a506**a**.p.ssafy.io` | [`data/`](data/README.md) | minio (이후 spark · mlflow · 수집 cron) |

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

### 2. `.env` 를 만든다

```bash
cd ~/S15P21A506/deploy/prod/app
cp .env.example .env
openssl rand -base64 24        # 나온 값을 .env 의 POSTGRES_PASSWORD 에 넣는다
```

채우지 않고 `up` 하면 **컨테이너를 만들기 전에 멈추고 어느 변수가 비었는지 알려 준다.**
스프링은 그 말을 안 해 주기 때문에(빈 값을 문자열 그대로 넘긴다) 검사를 compose 로 앞당겼다.

`.env` 는 커밋되지 않는다. **서버에 한 번 두고 계속 쓴다.** CI 는 이 파일을 만들지 않고
`API_TAG` · `WEB_TAG` 두 줄만 갈아 끼운다.

### 3. 자격증명은 어디에 사나

| 값 | 어디 | 누가 바꾸나 |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | 서버의 `.env` | **사람이 한 번.** 그다음 안 바꾼다 |
| `API_TAG` · `WEB_TAG` | 서버의 `.env` | **배포가 매번** (`sed` 로 갈아 끼운다). 비밀이 아니다 |

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

## 평소

```bash
cd ~/S15P21A506/deploy/prod/app
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

## 배포 (손으로)

CI 자동 배포가 붙기 전까지, 그리고 **CI 가 고장 났을 때** 쓰는 절차다.
**CI 도 정확히 이 순서를 돌린다.**

```bash
cd ~/S15P21A506
git checkout main && git pull
cd deploy/prod/app

TAG=$(git rev-parse --short HEAD)
sed -i "s/^API_TAG=.*/API_TAG=$TAG/; s/^WEB_TAG=.*/WEB_TAG=$TAG/" .env

docker compose build
docker compose up -d --wait --wait-timeout 300
```

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

## 롤백

**태그를 되돌리고 다시 올리는 것이 전부다.**

```bash
cd ~/S15P21A506/deploy/prod/app
docker images pickage-api --format '{{.Tag}}\t{{.CreatedSince}}'   # 되돌아갈 곳 고르기
docker images pickage-web --format '{{.Tag}}\t{{.CreatedSince}}'

sed -i "s/^API_TAG=.*/API_TAG=<이전 SHA>/" .env      # 프런트만 되돌릴 거면 WEB_TAG 만
docker compose up -d --no-build --wait
```

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

오래된 태그를 줄여야 하면 **눈으로 보고 하나씩** 지운다. 최근 5개는 남긴다.

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

---

## 아직 없는 것

| | 지금은 어떻게 되어 있나 |
| --- | --- |
| CI 자동 배포 | 위 "배포 (손으로)" 를 사람이 실행한다. 붙으면 `main` push 로 자동이 된다 |
| `data` 노드의 Spark · MLflow · 수집 cron | 없다. [data/README.md](data/README.md) 의 compose 에 서비스로 추가된다 |
