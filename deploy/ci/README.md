# CI — GitLab Runner 와 파이프라인

MR 을 열면 무엇이 돌고, `develop`·`main` 에 머지되면 무엇이 뜨는지, 그리고 그것을 돌리는
러너를 어떻게 세우는지. (S15P21A506-143 · 배포는 S15P21A506-223)

파이프라인 정의는 저장소 루트의 [`.gitlab-ci.yml`](../../.gitlab-ci.yml) 한 파일이고,
**각 잡을 왜 그렇게 썼는지는 그 파일의 주석에 있다.** 이 문서는 그 밖의 것 — 러너를 어디에
세우고, 무엇을 조심하고, 깨졌을 때 어디를 보는지 — 를 다룬다.

> **lab.ssafy.com 은 GitLab 18.11.5 다** (2026-09-12, `https://lab.ssafy.com/help` 에서 확인).
> CI 문법은 버전마다 있고 없고가 갈리므로 — `compare_to`(15.3+), `auto_cancel`(16.8+),
> 러너 등록 방식(16 에서 바뀜) — 검색한 예시를 그대로 붙이기 전에 이 버전을 기준으로 본다.

## 지금 무엇이 도나

| 잡 | 이미지 | 무엇을 검증하나 |
| --- | --- | --- |
| `frontend` | `node:22-alpine` | `npm ci` → `npm run typecheck` → `npm run lint` → `npm run build` |
| `backend-test` | `eclipse-temurin:21-jdk` | `gradlew test` — DB 가 필요 없는 단위 시험 |
| `backend-integration-test` | `eclipse-temurin:21-jdk` + `postgres:16` 서비스 | `gradlew integrationTest` — 진짜 Postgres 에 Flyway 전체를 적용하고 도는 시험 |
| `pipeline-ok` | `alpine:3.21` | 코드는 검증하지 않는다. **맨 앞에서 2초** — 아래 "맨 앞에서 2초" |
| `deploy-app` | (컨테이너 아님 — shell 러너) | 검증하지 않는다. **`develop`·`main` 에 머지된 것을 app 노드에 띄운다** — 아래 "배포" |

이미지는 `frontend/Dockerfile`·`backend/Dockerfile` 의 빌드 단계와 같은 것을 쓴다.
CI 에서 통과한 것이 배포 이미지 빌드에서 처음 깨지면 CI 를 둔 의미가 없다.

### 언제 도나

러너가 하나뿐이라 돌 수 있는 모든 때에 돌리면 대기열이 밀린다. **리뷰를 요청한 시점과
반영된 시점**, 두 군데로 좁혀 뒀다.

| 무엇을 했나 | 도나 |
| --- | --- |
| 브랜치에 push (MR 없음) | ❌ 아무것도 안 돈다 |
| MR 생성 · MR 소스 브랜치에 push | ✅ MR 파이프라인 |
| 위와 같지만 **Draft MR** | ❌ Ready 로 바꾸기 전까지 안 돈다 |
| `develop`·`main` 에 머지 | ✅ 전체 + **배포** (아래 "배포") |
| Pipelines → **Run pipeline** (수동) | ✅ 돈다. **`develop`·`main` 에서 누르면 배포까지 돈다** — 아래 "배포" |

> ⚠ **Draft → Ready 로 바꾸는 것은 파이프라인 트리거가 아니다.**
>
> GitLab 이 MR 파이프라인을 만드는 사건은 세 가지뿐이다 — MR 생성, 소스 브랜치에 push,
> MR 의 Pipelines 탭에서 Run pipeline. Draft 로 열어 두고 push 를 다 끝낸 뒤 Ready 로만
> 바꾸면 **한 번도 검증하지 않은 MR** 이 된다.
>
> Ready 로 바꾼 뒤 확인하는 법:
>
> ```
> MR → Pipelines 탭 → 최신 파이프라인의 커밋 SHA 가 소스 브랜치 HEAD 와 같은가
> ```
>
> 없거나 낡았으면 같은 탭의 **Run pipeline** 을 누른다. (GitLab 이슈 25426 — 아직 열려 있다)

수동 실행(`$CI_PIPELINE_SOURCE == "web"`)을 열어 둔 이유는 두 가지다. 위의 Ready 전환
직후가 하나, `.gitlab-ci.yml` 자체를 고칠 때가 다른 하나다 — MR 없이 확인할 방법이
그것뿐이다.

### 바뀐 폴더의 잡만 돈다

러너가 하나뿐이라 문서만 고친 MR 이 7~10분을 쓰면 그동안 코드 MR 이 그대로 기다린다.
그래서 `rules: changes:` 로 가른다.

| 무엇을 고쳤나 | 도는 잡 |
| --- | --- |
| `frontend/` 아래 | `frontend` |
| `backend/` 아래 | `backend-test`, `backend-integration-test` |
| `.gitlab-ci.yml` | **전부** (CI 를 고친 MR 이 CI 를 안 돌리고 통과하면 안 된다) |
| 문서·`pipeline/` 등 그 외 | `pipeline-ok` 만 |
| `develop`·`main` 브랜치, `main` 으로 가는 MR | **전부** (머지 뒤 한 번은 전체가 도는 안전망) |

조건부 실행은 **"아무것도 안 돌았는데 초록불"** 을 만들기 쉬워서, 세 가지를 같이 뒀다.
경로 목록에 `.gitlab-ci.yml` 자신을 넣은 것, 통합 브랜치에서는 조건을 걸지 않는 것,
그리고 아래 `pipeline-ok` 다.

> ⚠ **브랜치 파이프라인(= 수동 실행)에는 `compare_to: develop` 이 붙어 있다.** 이게 없으면
> `changes` 가 **직전 커밋과** 비교해서, 같은 브랜치에 두 번째 push 를 하는 순간 첫 push 에
> 바꾼 폴더의 잡이 사라진다. MR 파이프라인은 타깃 브랜치와의 분기점을 기준으로 비교하므로
> 이 문제가 없다.
>
> 이 문법(`changes: paths:` + `compare_to`)은 **GitLab 15.3 이상**이다.
> **lab.ssafy.com 은 18.11.5** 라 문제없다 (2026-09-12 `/help` 에서 확인).

### 맨 앞에서 2초 — `pipeline-ok`

**모든 파이프라인의 맨 앞**에서 도는 2초짜리 잡이다(`smoke` 스테이지). 두 가지를 한다.

1. **돌 잡이 없을 때 대신 서 있는다.** 문서만 고친 MR 은 해당되는 잡이 하나도 없다.
   그러면 파이프라인이 아예 생기지 않아서 MR 화면에 검증 흔적이 남지 않는다 —
   "검사할 것이 없었다" 와 "검사가 고장 났다" 가 똑같이 보인다.
2. **환경이 멀쩡한지 먼저 본다.** Docker Hub pull 한도, 디스크 참, 러너 설정 문제라면
   `npm ci` 를 3분 기다린 뒤가 아니라 여기서 드러난다. 클론도 하지 않는다
   (`GIT_STRATEGY: none`).

> ⚠ **러너가 아예 없거나 죽어 있으면 이 잡도 똑같이 `pending` 이다.** 그건 이 잡이
> 잡아 주는 문제가 아니라 파이프라인 전체가 못 도는 상태다 — 위 "러너가 없으면" 을 볼 것.

다른 잡들은 이 2초를 기다린다. 러너가 하나라 어차피 잡이 순서대로 도니 잃는 것이 없다.

## 배포 — `develop`·`main` 에 머지되면 app 노드에 뜬다

`deploy-app` 잡이 [`deploy/prod/README.md`](../prod/README.md) 의 "배포 (손으로)" 절과
**같은 순서**를 돌린다. 이미지 태그를 커밋 SHA 로 갈아 끼우고, 굽고, `--wait` 로 healthy 를
기다리고, TLS 를 지나는 요청을 한 번 쳐 본다.

**스테이징이 없다.** 서버가 한 벌뿐이라 `develop` 에 머지된 것이 곧 사용자가 보는 것이다
(2026-09-14 결정). `main` 머지도 같은 곳에 뜬다 — 릴리스 시점에 한 번 더 도는 셈이다.

배포가 도는 조건은 **`develop`·`main` 의 브랜치 파이프라인**이다. MR 파이프라인에서는
돌지 않는다. 머지 말고 두 가지가 더 걸린다는 것을 알고 있을 것.

| | 배포가 도나 |
| --- | --- |
| MR 을 머지했다 | ✅ 이게 보통 경우다 |
| `develop`·`main` 에 **직접 push** 했다 | ✅ 훅은 경고만 하고 막지 않는다 |
| `develop`·`main` 에서 **Run pipeline** 을 눌렀다 | ✅ 커밋 없이 다시 띄우는 **재배포 버튼**이다 |
| MR 을 열었다 / 작업 브랜치에 push 했다 | ❌ |
| 작업 브랜치에서 Run pipeline 을 눌렀다 | ❌ |

재배포 버튼을 남겨 둔 것은 의도다. 서버에서 컨테이너를 내렸다가 되돌릴 때 손으로 `up`
하지 않아도 되고, 이미지가 그대로면 **아무 컨테이너도 다시 뜨지 않으므로** 눌러도 안전하다
(아래 "안 바뀐 것은 다시 띄우지 않는다").

| | |
| --- | --- |
| 대상 | `app` 노드의 `api`·`web` 두 컨테이너 |
| 태그 | `$CI_COMMIT_SHORT_SHA` (8자리). 손 배포의 `git rev-parse --short`(7자리)와 자릿수만 다르다 |
| 자격증명 | `/srv/pickage/app.env` — 서버에 있는 파일이다. CI 변수에도 저장소에도 없다 |
| 걸리는 시간 | **1분 45초** (2026-09-15 리허설. 두 이미지를 실제로 다시 구운 경우이고, 의존성 레이어는 캐시가 들었다) |
| 끊김 | **바뀐 쪽만** 다시 뜬다 — 아래 "안 바뀐 것은 다시 띄우지 않는다" |

### 안 바뀐 것은 다시 띄우지 않는다

잡은 매번 두 이미지를 굽는다. 그다음 **구운 결과가 전과 같은 이미지면 태그를 되돌려서**
compose 가 그 컨테이너를 건드리지 않게 한다.

| 무엇이 바뀐 머지인가 | 다시 뜨는 것 | 끊김 |
| --- | --- | --- |
| 프런트만 | `web` | 수 초 |
| 백엔드만 | `api` (그리고 의존 관계로 `web` 도 같이) | **1분 가까이** — 기동 + Flyway |
| 둘 다 | `api` · `web` | 1분 가까이 |
| 문서·`pipeline/` 만 | 없다. 굽기만 하고 끝난다 | 없음 |
| `compose.yaml`·`nginx/app.conf` | 이미지와 무관하게 compose 가 알아서 다시 만든다 | 바뀐 서비스만 |

**판단 기준은 이미지 ID 다.** `docker compose build` 가 전 단계 캐시 히트로 끝나면 도커는
새 이미지를 만들지 않고 **있던 이미지에 새 태그만 붙인다.** 그러면 새 태그와 이전 태그의
`.Id` 가 같은 값이 되고, 그걸 그대로 비교한다 — "비슷한가" 가 아니라 "같은 이미지인가" 다.

```bash
docker image inspect -f '{{.Id}}' pickage-api:<새 SHA>
docker image inspect -f '{{.Id}}' pickage-api:<이전 태그>
```

> ⚠ **그래서 이 판단은 빌드 캐시가 살아 있다는 전제 위에 있다.** 캐시가 사라진 뒤
> (일주일 지나 프루닝됐거나 도커를 갈아엎었거나) 다시 구우면, 소스가 같아도 레이어
> 다이제스트가 달라질 수 있다 — jar 안에 타임스탬프가 들어가는 식이다. 그러면 "새
> 이미지" 로 판정되어 **안 바뀐 쪽도 한 번 다시 뜬다.** 틀리는 방향이 안전한 쪽이라
> 그냥 둔다: 필요 없는 재시작 한 번이지, 바뀐 것을 안 띄우는 일은 생기지 않는다.

무엇을 건너뛰었는지는 잡 로그에 남는다.

```
[api] 내용이 그대로다 — 1a2b3c4d 를 유지한다. 이 컨테이너는 다시 뜨지 않는다
[web] 새 이미지 — 9f8e7d6c 로 뜬다
```

> **경로(`rules: changes:`)로 가르지 않았다.** 검증 잡은 그렇게 하지만 배포는 다르다 —
> 조건에 안 걸리면 **배포 잡 자체가 파이프라인에서 사라지는데 화면은 초록이다.**
> "머지했는데 안 떴다" 를 아무도 못 보게 된다. 지금은 잡이 항상 돌고 판단이 로그에 남는다.
> 덤으로, 경로 규칙이 놓치는 것(기반 이미지 갱신, `Dockerfile` 변경)도 구운 결과로는 드러난다.

> ⚠ **그래서 `.env` 의 두 태그가 서로 다른 커밋을 가리키는 것이 정상이다.** 그게 원래
> 태그를 둘로 나눠 둔 이유고(프런트만 롤백), "지금 서버에 뜬 커밋" 은
> `git -C /srv/pickage/repo log -1` 이 답한다.

**환경변수만 고쳤을 때**는 이미지가 안 바뀌므로 다시 굽지 않는다. 그래도 컨테이너는
대개 다시 뜬다 — compose 가 치환된 설정까지 해시로 비교하기 때문이다. 예외가 하나 있어서
(MinIO 자격증명) 절차를 따로 적어 뒀다:
[`prod/README.md`](../prod/README.md) 의 "환경변수만 고쳤을 때".

배포 잡이 빨간불일 때 서버가 어떤 상태로 남는지도 거기 있다 — "배포가 실패하면".

> ⚠ **`data` 노드는 이 잡이 건드리지 않는다.** minio·mlflow·Spark·유사도 배치는 아직
> 손으로 올린다. 다른 호스트라 SSH 키나 그쪽 러너가 필요하고, `--wait` 를 쓸 수 없는
> 일회성 컨테이너(`minio-init`)까지 같이 풀어야 해서 이번에 넣지 않았다.

> ⚠ **배치 시각에 머지하지 말 것.** 배포가 배치와 겹치면 메모리가 상한을 넘고, 컨테이너
> 스왑이 0 이라 즉시 OOM Kill 이다. 자동이 된 뒤로는 **머지 시각으로** 피하는 수밖에 없다.

### 사람이 찾아갈 경로

배포 잡은 러너의 작업 디렉터리에서 돈다. 이름에 토큰이 섞여 있어 외울 수 없는데,
**운영 `web` 컨테이너가 물고 있는 nginx 설정이 그 디렉터리 안의 파일이다.** 그래서 잡이
매번 고정 경로로 심볼릭 링크를 걸어 둔다.

```bash
cd /srv/pickage/repo/deploy/prod/app     # 여기가 운영 디렉터리다
docker compose ps
git -C /srv/pickage/repo log -1 --oneline # 지금 서버에 뜬 커밋
```

**`cd` 를 빠뜨리면** compose 가 `compose.yaml` 을 못 찾고 `no configuration file
provided: not found` 로 끝난다. 홈 디렉터리에서 친 경우다.

DB 만 잠깐 볼 거라면 compose 를 거치지 않는 쪽이 짧다. `.env` 도 필요 없다.

```bash
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -c '\dt'
```

컨테이너 이름은 `<프로젝트>-<서비스>-1` 이다. 프로젝트 이름은 `compose.yaml` 에 박혀 있는
`pickage-app` 이라 바뀌지 않는다. 확실치 않으면 `docker ps --format '{{.Names}}'`.

**손으로 배포하거나 nginx 를 reload 할 때도 이 디렉터리에서 한다.** 다른 체크아웃에서
`nginx -s reload` 를 치면 컨테이너가 물고 있는 파일이 아니라 **다른 파일을 고친 것**이라
아무 일도 일어나지 않는다. 증상이 "설정을 고쳤는데 안 바뀐다" 라 원인을 찾기 어렵다.

## 배포 러너 (shell executor) — 최초 1회

검증 잡이 도는 docker executor 는 **컨테이너 안**이라 호스트의 compose 를 건드릴 수 없다.
그래서 `app` 노드에 러너를 하나 더 등록한다. 이 러너는 배포 잡 하나만 집어간다.

### 1. 서버에 자리를 만든다

```bash
sudo mkdir -p /srv/pickage
sudo chown gitlab-runner:gitlab-runner /srv/pickage

# 기존 .env 를 옮긴다. 복사가 아니라 이동이다 — 두 벌이 되면 어느 쪽 태그가 떠 있는지 모른다
sudo mv ~/S15P21A506/deploy/prod/app/.env /srv/pickage/app.env
sudo chown gitlab-runner:"$(id -gn)" /srv/pickage/app.env
sudo chmod 640 /srv/pickage/app.env
```

**소유자는 러너, 그룹은 사람**이다. 쓰는 것은 배포 잡 하나뿐이지만(태그 두 줄), 읽는
쪽에는 사람도 들어가야 한다.

```bash
sudo -u gitlab-runner test -r /srv/pickage/app.env && echo "러너가 읽는다"
```

```bash
test -r /srv/pickage/app.env && echo "사람 계정도 읽는다"
```

**둘 다 찍혀야 한다.** `600` 으로 두면 아래 "사람이 찾아갈 경로" 에서 친 `docker compose`
명령이 전부 **".env 를 만들고 POSTGRES_DB 를 채울 것" 으로 죽는다** — compose 는 `.env` 를
못 읽으면 없는 것과 똑같이 굴어서, 원인이 권한이라는 게 메시지에 안 드러난다.
이 노드에 로그인할 수 있는 사람은 어차피 `sudo` 를 쓸 수 있으므로 `640` 이 비밀을 더
노출하지는 않는다.

`docker` 를 칠 수 있어야 한다.

```bash
sudo usermod -aG docker gitlab-runner
sudo -u gitlab-runner docker ps >/dev/null && echo "러너가 docker 를 쓸 수 있다"
```

### 2. `develop`·`main` 을 보호 브랜치로 만든다

**3번의 Protected 러너가 성립하려면 이게 먼저다.** Settings → Repository →
**Protected branches** 에서 `main` 과 `develop` 이 목록에 있어야 한다. `main` 은 기본
브랜치라 대개 이미 들어 있고, **`develop` 은 손으로 넣어야 한다.**

```
Allowed to merge : Maintainers   (팀 상황에 맞게)
Allowed to push  : No one        (MR 로만 들어오게 — AGENTS.md 4.1)
```

> ⚠ **순서를 뒤집지 말 것.** 러너를 Protected 로 만들어 놓고 `develop` 이 보호 브랜치가
> 아니면, `develop` 의 배포 잡을 집어갈 러너가 없어서 **파이프라인이 영영 `pending`** 이다.
> 실패가 아니라 멈춰 있는 상태라 알아채기 어렵다.

### 3. GitLab 에서 러너를 만든다 (웹)

Settings → CI/CD → Runners → **New project runner**

- **Tags 에 `deploy` 를 넣는다.**
- **"Run untagged jobs" 는 끈다.** 켜 두면 이 러너가 `frontend` 잡을 집어가서
  `node: command not found` 로 죽는다 — 호스트에는 node 도 JDK 도 없다.
  증상이 "어떤 파이프라인은 되고 어떤 파이프라인은 안 된다" 라서 원인을 찾기 어렵다.
- **"Protected" 를 켠다.** ← **빠뜨리면 안 되는 항목이다.**

> ### ⚠ Protected 를 켜지 않으면 리뷰 전 코드가 운영 서버에서 돈다
>
> 태그는 접근 제어가 아니라 **이름표**다. 누구든 자기 브랜치에서 `.gitlab-ci.yml` 에
> `tags: [deploy]` 를 단 잡을 하나 써 넣고 MR 을 열면, 그 잡이 이 러너에 배정된다.
> 그리고 이 러너는 **shell executor** 다 — 컨테이너 안이 아니라 **운영 호스트에서 직접**
> 돌고, `gitlab-runner` 계정은 docker 그룹에 들어 있다. docker 소켓은 호스트 root 와
> 동등하다. 즉 리뷰도 승인도 거치지 않은 코드가 운영 서버에서 무엇이든 할 수 있고,
> `/srv/pickage/app.env` 의 DB 비밀번호와 MinIO 키도 그중 하나다.
>
> **Protected 러너는 보호 브랜치의 잡만 집어간다.** 그래서 작업 브랜치의 MR 파이프라인은
> 무슨 태그를 달든 이 러너를 쓰지 못한다(그 잡이 `pending` 으로 남는다). 여기서부터는
> "`develop` 에 머지할 수 있는 사람은 운영 서버에서 코드를 돌릴 수 있다" 가 되는데,
> 그건 CD 를 두기로 한 이상 받아들이는 경계다.
>
> 이 러너는 **검증 잡용 docker 러너와 성질이 다르다.** 그쪽은 컨테이너 안에서 돌고 운영
> 자격증명에 닿지 않아 Protected 가 아니어도 된다. 같은 화면에서 만드는 바람에 같은
> 설정을 쓰기 쉬운데, 여기서는 갈라야 한다.

### 4. 등록

```bash
sudo gitlab-runner register --non-interactive \
  --url "https://lab.ssafy.com/" \
  --token "glrt-여기에-복사한-토큰" \
  --executor "shell" \
  --shell "bash" \
  --description "pickage-app-deploy"
```

`--docker-image` 는 주지 않는다. shell executor 에는 이미지가 없다 — 잡이 호스트에서 그대로 돈다.

### 5. 확인

```bash
sudo gitlab-runner verify
sudo gitlab-runner list          # 둘이 보여야 한다: pickage-app-docker, pickage-app-deploy
```

Settings → CI/CD → Runners 에서 새 러너가 초록이고, **태그가 `deploy` 하나**이고,
**Protected 뱃지가 붙어 있는지** 본다. 셋 다여야 한다.

### 6. 첫 배포는 컨테이너를 전부 새로 만든다

지금까지는 `~/S15P21A506` 에서 `up` 했다. 첫 배포부터는 러너의 작업 디렉터리에서 돈다 —
compose 가 보기에 **설정이 바뀐 것**이라(`web` 의 nginx 설정이 다른 경로에서 온다)
컨테이너를 다시 만든다. 평소 배포보다 조금 더 끊긴다.

**운영 DB 는 그대로다.** 볼륨 이름은 디렉터리가 아니라 프로젝트 이름(`pickage-app`)에서
나오고, 그 이름은 `compose.yaml` 에 박혀 있다.

```bash
docker volume ls | grep pickage-app_pgdata     # 첫 배포 뒤에도 같은 볼륨 하나여야 한다
```

두 개가 보이면 프로젝트 이름이 갈린 것이다. **`up` 을 더 하지 말고** 어느 쪽에 데이터가
있는지부터 확인한다 (`docker volume inspect` 의 `CreatedAt`).

> ⚠ **shell executor 의 잡은 상한 밖에서 돈다.** `[runners.docker]` 의 `memory` 는 docker
> executor 에만 걸린다. 배포 잡이 쓰는 것은 대부분 `docker build` 라 그 메모리는 docker
> 데몬 쪽에서 나가지만, **호스트에서 직접 도는 프로세스라는 점은 기억할 것** — 잘못 짠
> 스크립트가 호스트를 그대로 건드린다.

## 러너가 없으면 아무 일도 일어나지 않는다

파이프라인은 **실패하지 않고 `pending` 으로 멈춰 있는다.** 잡을 집어갈 러너가 없다는 뜻이고,
화면에는 보통 이렇게 뜬다.

```
This job is stuck because the project doesn't have any runners online assigned to it.
```

`.gitlab-ci.yml` 을 아무리 고쳐도 이 상태는 안 풀린다. 러너부터 세운다.

## 어디에 등록하나 — `app` 노드 (`j15a506.p.ssafy.io`)

두 노드 다 15 GiB 인데, 걸어 둔 컨테이너 상한의 합이 다르다
([`deploy/prod/README.md`](../prod/README.md) 의 "Swap", [`data/README.md`](../prod/data/README.md)).

| | 배치 중 상한 합 | 남는 것 | `df -h /` |
| --- | --- | --- | --- |
| `app` | postgres 2g + api 1.6g + web 0.25g + worker② 6.5g ≈ **10g** | ~5g | 300G 남음 (09-13, DB 비었을 때) → **137G (09-15)** |
| `data` | minio 1g + mlflow 0.5g + master 1g + worker① 10g + ai 2g ≈ **14.5g** | ~0.5g | 264G 남음 (09-13) |

> **`app` 의 09-13 값(4% 사용, 300G)은 DB 가 비어 있을 때의 총량으로 남겨 둔 것이다.**
> 09-15 에 56%(137G 남음)가 됐고, 줄어든 대부분은 **Postgres 에 넣은 데이터**다.
> 앞으로 더 들어온다 — **여유는 계속 줄어드는 쪽**이라고 보고 움직인다.
>
> 도커 이미지·빌드 캐시가 같은 파티션에 산다. 그래서 배포 잡이 이미지 태그를 5개로
> 제한한다(아래 "디스크"). **디스크가 차면 먼저 깨지는 것은 CI 가 아니라 Postgres 의
> 쓰기다** — 그때는 배포가 문제가 아니게 된다.

`data` 노드는 배치 중에 CI 잡 하나를 얹을 자리가 없다. 그리고 배포 잡(S15P21A506-223)이
`app` 의 compose 를 직접 조작하는데, 러너가 그 노드에 있어서 SSH 키나 Docker 소켓을
다른 호스트에 넘기지 않아도 됐다.

> ⚠ **여유가 5g 라는 것은 배치 시각에 CI 가 겹쳐도 된다는 뜻이 아니다.** 아래 "메모리" 에서
> 잡 컨테이너에 상한을 박고, 그래도 불안하면 배치 전에 `sudo gitlab-runner stop` 한다.

## 등록 절차 — 검증 잡용 docker 러너

**배포 러너는 이 절차가 아니다.** executor 도 설정도 달라서 위의
"배포 러너 (shell executor)" 에 따로 있다. 여기는 `frontend`·`backend-*` 를 집어가는
러너다.

### 0. GitLab 에서 러너를 만든다 (웹)

프로젝트 → **Settings → CI/CD → Runners → New project runner**

- **Run untagged jobs 를 체크한다.** 안 하면 태그 없는 잡을 집어가지 않는데,
  `.gitlab-ci.yml` 의 잡에는 태그가 없다. 체크를 잊으면 증상이 "러너는 초록인데
  파이프라인은 계속 pending" 이라 원인을 찾기 어렵다.
- 태그는 비워 둔다. 러너가 하나뿐이라 구분할 것이 없다.
- 만들고 나면 `glrt-` 로 시작하는 토큰이 한 번 보인다. **그 화면을 닫으면 다시 못 본다.**

> 인터넷에서 보이는 `--registration-token "GR1348941…"` 방식은 **옛 방식이다.** GitLab 16
> 에서 폐기됐고 우리 서버(18.11.5)에서는 쓰지 않는다. 위 화면에서 만든 `glrt-` 토큰을
> `--token` 으로 준다.

### 1. 설치 (`app` 노드에서)

공식 안내는 `curl … | sudo bash` 지만 **파이프로 넘기지 않는다.** 받아서 확인하고 실행한다.

```bash
curl -fL "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" -o /tmp/runner-repo.sh
sudo bash /tmp/runner-repo.sh
sudo apt-get install -y gitlab-runner
```

> ### ⚠ `curl … | sudo bash` 는 실패를 삼킨다
>
> curl 이 아무것도 못 받아도 `sudo bash` 는 빈 입력을 읽고 조용히 끝난다. 화면에는 오류가
> 없는데 저장소는 안 붙어 있고, 그다음 `apt-get install` 이 이렇게 말한다.
>
> ```
> E: Unable to locate package gitlab-runner
> ```
>
> **2026-09-13 설치 때 실제로 여기서 막혔다.** 배포판이 지원되지 않는 것으로 오해하기 쉬운데
> (Ubuntu 24.04 `noble` 은 정상 지원된다), 원인은 그냥 내려받기가 실패한 것이었다. 위처럼
> `-f`(HTTP 오류를 실패로) 와 `-o`(파일로) 를 쓰면 그 자리에서 드러난다. 구분하는 법:
>
> ```bash
> ls /etc/apt/sources.list.d/ | grep -i runner   # 없으면 내려받기 실패
> apt-cache policy gitlab-runner                 # Candidate: (none) 이면 코드명 미지원
> ```

docker executor 를 쓰므로 **Docker 가 이미 깔려 있어야 한다.** `app` 노드는 compose 가
돌고 있으니 이미 있다.

### 2. 등록

```bash
sudo gitlab-runner register --non-interactive \
  --url "https://lab.ssafy.com/" \
  --token "glrt-여기에-복사한-토큰" \
  --executor "docker" \
  --docker-image "alpine:3.21" \
  --description "pickage-app-docker"
```

`--docker-image` 는 **잡이 `image:` 를 지정하지 않았을 때의 기본값**이다. 우리 잡은 셋 다
직접 지정하므로 실제로는 거의 안 쓰이지만, 인자 자체는 빠지면 등록이 안 된다.

### 3. `/etc/gitlab-runner/config.toml` 을 손본다

등록이 만들어 준 파일에서 **세 군데**를 고친다.

```toml
concurrent = 1          # ← 파일 맨 위. 기본값 1 이지만 확인할 것

[[runners]]
  name = "pickage-app-docker"
  url = "https://lab.ssafy.com/"
  executor = "docker"
  [runners.docker]
    image = "alpine:3.21"
    memory = "2g"
    memory_swap = "2g"        # ← memory 와 같은 값 = 이 컨테이너는 스왑을 0 쓴다
    cpus = "2"
    pull_policy = ["if-not-present", "always"]
    volumes = ["/cache"]
```

- **`concurrent = 1`** — 잡을 하나씩만 돌린다. 2 로 두면 `frontend`(npm)와
  `backend-integration-test`(JVM + postgres)가 같이 떠서 메모리 계산이 한 번에 무너진다.
  대신 잡이 하나씩 차례로 돈다 — 전부 도는 파이프라인이면 7~10분쯤이다. 러너가 하나인
  이상 이게 맞고, 그래서 위 "바뀐 폴더의 잡만 돈다" 가 실제로 체감되는 절약이다.
- **`memory` / `memory_swap`** — 잡 컨테이너와 **서비스 컨테이너 각각에** 걸린다
  (`backend-integration-test` 면 JDK 2g + postgres 2g). 둘을 같은 값으로 두는 이유는
  운영 compose 의 `memswap_limit` 과 정확히 같다 — 한쪽만 주면 Docker 가 총량을 2배로 잡고,
  호스트에 스왑 2 GiB 가 있는 지금은 그게 실제로 동작한다.
  근거는 [`deploy/prod/README.md`](../prod/README.md) 의 "Swap".
- **`pull_policy`** — 앞의 것부터 시도한다. 이미 받아 둔 이미지가 있으면 그걸 쓰고,
  없을 때만 받는다. Docker Hub 익명 pull 한도(IP 기준)에 걸리는 것을 늦춘다.
  ⚠ `node:22-alpine` 같은 **움직이는 태그**의 갱신이 늦어진다는 뜻이기도 하다.
  기반 이미지를 새로 받고 싶으면 서버에서 `docker pull node:22-alpine` 을 한 번 친다.

고치고 나서:

```bash
sudo systemctl restart gitlab-runner
sudo gitlab-runner verify          # 등록이 살아 있는지
```

### 4. 확인

1. **Settings → CI/CD → Runners** 에서 러너가 초록(online)인지 본다.
2. 아무 작업 브랜치나 push 한다 → Build → Pipelines 에 파이프라인이 생기고 잡이 도는지 본다.
3. 첫 파이프라인은 이미지를 전부 내려받느라 느리다. 두 번째부터 캐시가 듣는다.

> `gitlab-runner` 가 Docker 소켓에 접근하지 못하면(`permission denied … docker.sock`)
> `sudo usermod -aG docker gitlab-runner && sudo systemctl restart gitlab-runner`.

### 지금 붙어 있는 것 (2026-09-13)

| | |
| --- | --- |
| 노드 | `app` (`j15a506.p.ssafy.io`), Ubuntu 24.04.4 LTS, 코어 4개 |
| 러너 | `pickage-app-docker` (id 2119), docker executor |
| 적용한 값 | `concurrent = 1`, `memory`·`memory_swap` = `2g`, `cpus = "2"`, `pull_policy = ["if-not-present", "always"]` |

배포 잡이 붙으면서 같은 노드에 `pickage-app-deploy`(shell executor)가 하나 더 올라간다.

> **`concurrent = 1` 은 파일 맨 위에 있는 값이라 러너 둘에 함께 걸린다.** 그래서 검증 잡과
> 배포 잡이 동시에 도는 일이 없다 — 이 노드에서는 그게 맞다. 배포는 어차피 `test`
> 스테이지가 끝난 뒤에 돌기 때문에 잃는 시간도 없다.

`cpus = "2"` 는 **4코어의 절반**이다. 나머지 절반이 api·postgres·Spark worker② 몫으로
남는다. 코어가 2개인 노드에 붙일 때 이 값을 그대로 복사하면 제한이 없는 것과 같아진다.

## 메모리 — CI 는 상한 밖에서 도는 또 하나의 프로세스다

운영 compose 는 서비스마다 `mem_limit` 이 박혀 있지만 **러너가 만드는 잡 컨테이너는 그
바깥이다.** 위의 `[runners.docker] memory` 가 그 자리를 대신한다. 박지 않으면 Gradle 이
호스트 메모리를 기준으로 힙을 잡고, 그 결과가 "커널이 무엇을 죽일지 우리가 못 고르는" 상황이다 —
**Postgres 를 고를 수도 있다.**

그래서 컨테이너 상한(`[runners.docker] memory = "2g"`) 안에 **JVM 세 개의 힙을 각각** 박는다.

> ### ⚠ 백엔드 잡 하나에 JVM 이 셋이다
>
> `-Dorg.gradle.jvmargs` 는 **데몬에만** 걸린다. 하나만 박고 "막았다" 고 보면 나머지 둘이
> 계산에서 빠진다.
>
> | JVM | 힙 | 어디서 정하나 |
> | --- | --- | --- |
> | gradle 런처 | 256m | `.gitlab-ci.yml` 의 `GRADLE_OPTS` 앞부분 `-Xmx256m` |
> | single-use 데몬 | 768m | 같은 변수의 `-Dorg.gradle.jvmargs` |
> | Test 워커 | 512m | `backend/build.gradle` 의 `maxHeapSize` |
>
> `--no-daemon` 은 잡이 끝난 뒤 JVM 이 남지 않게 하는 것이지 데몬을 안 만드는 것이 아니다.
> `jvmargs` 가 있으면 Gradle 이 single-use 데몬을 따로 포크한다 — 로그에 이렇게 나온다.
>
> ```
> To honour the JVM settings for this build a single-use Daemon process will be forked.
> ```
>
> 시험은 그 데몬도 아닌 **Test 워커**에서 돈다. `backend-integration-test` 는 그 워커에
> Spring 컨텍스트·Flyway·Hibernate 가 다 뜨므로 셋 중 RSS 가 가장 크다. 값을 지정하지
> 않으면 Gradle 기본값 512m 이 조용히 쓰이고, 상한을 계산할 때 이 몫이 보이지 않는다.

힙 합계는 1536m 이고, 나머지가 JVM 세 개의 메타스페이스·코드캐시·스레드 스택 몫이다.

### 여유가 얼마인지는 계산하지 말고 잡 로그를 본다

`-Xmx` 는 예약이 아니라 상한이라, 위 합계를 더해도 실제 사용량은 알 수 없다. 백엔드 잡은
Gradle 이 끝난 직후 실측값을 찍는다.

```
[메모리] 최대 사용: 1092 MiB   (읽은 곳: /sys/fs/cgroup/memory.peak)
[메모리] 상한: 2048 MiB
```

**기준선 — `backend-integration-test` 1092 MiB / 2048 MiB (2026-09-14).** 세 잡 중 이것이
가장 크다(워커에 Spring 컨텍스트·Flyway·Hibernate 가 뜬다). 여유가 956 MiB 라 지금 상한은
넉넉하다.

여기서 크게 벗어나면 **상한을 올리기 전에 무엇이 늘었는지부터** 본다 — 의존성이 늘었거나,
시험이 늘었거나, 힙 설정이 바뀐 것이다. 1600 MiB 를 넘기 시작하면 그 확인을 할 때다.

> ⚠ 이 출력은 `script` 안에 있다. **`after_script` 로 옮기지 말 것** — 거기서는 시험이 돌던
> cgroup 이 아닌 값이 나온다. 2026-09-14 에 그렇게 넣었다가 JVM 셋을 돌린 직후에
> `4 MiB` 를 받았다. 그래서 그 자리에 자기 검사를 넣어 뒀다 — 64 MiB 미만이면
> `⚠ 값이 비정상적으로 작다` 가 같이 찍힌다. 그 줄이 보이면 숫자를 믿지 말 것.
>
> 대신 **잡이 실패하면 이 줄은 안 찍힌다.** exit 137 이면 사용량을 물어볼 필요가 없다 —
> 상한에 닿았다는 뜻이고 그 값이 곧 상한이다.

**두 줄의 차이가 여유다.** 200 MiB 밑으로 붙으면 줄일 곳은 **데몬**이다 — 컴파일만 하므로
시험이 도는 워커보다 클 이유가 없다. 그래도 모자라면 러너의 `memory` 를 올리는데,
`backend-integration-test` 는 postgres 서비스 컨테이너에 2g 가 **따로** 걸려 잡 하나가
도는 동안 노드에서 4g 를 쓴다. `app` 노드 여유가 ~5g 이므로 2.5g 가 현실적인 상한이다.

`[메모리] 상한 없음` 이 찍히면 러너에 `memory` 가 안 걸린 것이다. 그 상태로는 위의 힙
설정이 아무 의미가 없다 — `config.toml` 부터 확인할 것.

잡이 **exit code 137** 로 죽으면 컨테이너 상한에 걸린 것이다. 로그 마지막에 아무 설명이
없는 것이 특징이다. 힙을 늘려야 하면 위 표의 값과 `[runners.docker] memory` 를 **함께**
올린다 — `memory_swap` = `memory` 라 넘기는 순간 완충 없이 죽는다.

## 디스크 — 정리는 하되, `-a` 는 쓰지 않는다

CI 가 돌수록 이미지·빌드 캐시·죽은 컨테이너가 쌓이고, **배포가 자동이 된 뒤로는 머지마다
이미지가 하나씩 는다.** 배포 잡이 `after_script` 에서 아래 두 가지를 스스로 한다.

- `pickage-api`·`pickage-web` 의 **최근 5개 태그만 남기고** 그보다 오래된 태그를 뗀다
  (수동 정리 지침과 같은 범위다 — [`prod/README.md`](../prod/README.md) 의 "정리")
- 일주일 지난 빌드 캐시와 dangling 이미지를 지운다

그래서 평소에 손으로 칠 일은 없다.

**이 노드에서 디스크를 실제로 먹는 것은 도커가 아니라 Postgres 데이터다**(위 표).
그쪽은 줄일 수 있는 성질의 것이 아니므로, 도커가 차지하는 몫을 작게 유지하는 것이
여기서 할 수 있는 전부다. 얼마인지는 이렇게 본다.

```bash
docker system df -v | head -30
```

**배포 한 번이 얼마를 먹나** (2026-09-15 실측, `docker system df -v` 의 UNIQUE SIZE).

| | 이미지 전체 | 그중 새로 쌓인 것 |
| --- | --- | --- |
| `pickage-api` | 615MB | **500MB** |
| `pickage-web` | 77.8MB | **25MB** |

기반 레이어(`eclipse-temurin`·`nginx:alpine`)는 태그끼리 공유하므로 두 번째 배포부터는
**한 번에 약 525MB** 다. 양쪽이 다 바뀐 경우이고, 한쪽만 바뀌면 그쪽만 는다.
태그를 5개로 제한하니 이미지가 차지하는 양의 상한은 **대략 2.6GB** 다. 여기에 빌드
캐시가 따로 붙는다.

`Images`·`Build Cache` 합계가 10G 를 넘으면 아래를 손으로 한 번 친다 — 배포 잡의 정리는
일주일 지난 캐시만 건드리므로, 그 안쪽에 몰려 쌓인 것은 남아 있다.

```bash
docker system prune -f --filter "until=168h"   # 떠 있지 않은 컨테이너·dangling 이미지·안 쓰는 네트워크
docker builder prune -f --filter "until=168h"
```

> ### ⚠ `docker system prune -af` 를 치지 말 것
>
> `-a` 는 **컨테이너가 쓰고 있지 않은 이미지를 전부** 지운다. `app` 노드에는 이전 배포의
> `pickage-api:<이전 SHA>` 가 남아 있고 **그게 롤백 수단이다**
> ([`deploy/prod/README.md`](../prod/README.md) 의 "롤백"). 한 줄로 롤백을 잃는다.

## 자주 걸리는 것

| 증상 | 대개 이것 |
| --- | --- |
| 파이프라인이 계속 `pending` | 러너가 없거나 offline. 또는 러너에 **Run untagged jobs 가 꺼져 있다** |
| 잡이 `exit code 137` | 메모리 상한. 위 "메모리" |
| `Connection refused` (postgres) | 서비스 별칭은 `postgres` 다. `localhost` 로는 못 닿는다 — 서비스는 다른 컨테이너다 |
| `npm ci` 가 매번 오래 걸린다 | `frontend/package-lock.json` 이 바뀌면 캐시 키가 바뀐다. 안 바뀌었는데도 그렇다면 러너의 캐시 디렉터리를 확인 |
| `toomanyrequests` (Docker Hub) | 익명 pull 한도. `pull_policy` 로 늦추고, 그래도 걸리면 서버에서 `docker login` |
| MR 한 번에 파이프라인이 두 개 | `.gitlab-ci.yml` 의 `workflow:` 규칙이 빠졌거나 어긋난 것 |
| 배치 시각에 서버가 느려진다 | CI 가 겹친 것. 배치 전에 `sudo gitlab-runner stop`, 끝나면 `start` |
| **배포 잡만** 계속 `pending` | `deploy` 태그를 가진 러너가 없거나 offline. 위 "배포 러너" |
| 배포 잡이 `.env 를 만들고 POSTGRES_DB 를 채울 것` 으로 죽는다 | `/srv/pickage/app.env` 가 없다. 위 "1. 서버에 자리를 만든다" |
| 배포 잡이 `permission denied … docker.sock` | `gitlab-runner` 가 docker 그룹에 없다. 위 `usermod -aG docker` |
| `frontend` 잡이 `node: command not found` | shell 러너가 집어간 것. 그 러너의 **Run untagged jobs 를 끈다** |
| 설정을 고쳤는데 nginx 가 안 바뀐다 | 컨테이너가 물고 있는 파일은 `/srv/pickage/repo/...` 다. 위 "사람이 찾아갈 경로" |
| 배포 잡이 `pending` 인데 러너는 초록 | 러너가 **Protected** 인데 그 브랜치가 보호 브랜치가 아니다. 위 "2. 보호 브랜치" |
| 작업 브랜치의 `deploy` 태그 잡이 안 돈다 | **설계대로다.** Protected 러너는 보호 브랜치의 잡만 집어간다 |
| 앱만 배포했는데 Spark worker 가 재시작한다 | `compose.yaml` 의 spark-worker-2 에 `env_file` 이 되살아났는지 본다. 위 "안 바뀐 것은…" |
| 돌아야 할 잡이 파이프라인에 아예 없다 | `changes:` 규칙. 바꾼 경로가 목록에 없거나(위 "바뀐 폴더의 잡만 돈다"), 수동 실행에서 `compare_to` 기준으로 이미 develop 과 같은 상태다 |
| push 했는데 **파이프라인 자체가 안 생긴다** | 설계대로다. MR 이 없거나 Draft 다 — 위 "언제 도나" |
| Ready 로 바꿨는데 파이프라인이 안 생긴다 | Draft → Ready 는 트리거가 아니다. Pipelines 탭의 **Run pipeline** — 위 "언제 도나" |

## 아직 없는 것

| | 왜 아직 없나 |
| --- | --- |
| **파이썬(`pipeline/`) 시험** | 폴더마다 실행 방법이 다르다 — `python -m unittest discover -s pipeline/curated`, `python -m unittest pipeline.package_snapshot.test_input`, 그 폴더 안에서만 되는 import 까지 섞여 있다. 게다가 일부는 docker·Postgres 를 요구한다(`test_postgres`·`test_integration`). **어느 것을 CI 대상으로 삼을지 고르는 것 자체가 작업**이라 후속 이슈로 뺐다 |
| **`data` 노드 배포** | `deploy-app` 은 `app` 노드만 띄운다. `data` 는 다른 호스트라 SSH 키나 그쪽 러너가 필요하고, `--wait` 를 쓸 수 없는 일회성 컨테이너(`minio-init`)도 같이 풀어야 한다 (S15P21A506-223 후속) |
| **무중단 배포** | api 인스턴스가 하나라 블루/그린이 필요하다. 배포마다 수십 초 끊긴다 ([`prod/README.md`](../prod/README.md)) |
| **Gradle 캐시를 호스트 볼륨으로** | 지금은 GitLab 캐시(압축·해제)를 쓴다. `[runners.docker] volumes` 에 호스트 디렉터리를 물리면 더 빠르지만, 러너 설정과 파이프라인이 묶인다 |
| **프런트 포맷 검사(Prettier)** | 프런트는 한 사람이 단독으로 작업해 포맷이 갈릴 상대가 없고, 동작에 영향을 주는 검사도 아니다. 넣어 두면 develop 기준 **71개 파일**(2026-09-12)이 걸려 항상 빨간불이거나 항상 무시하는 노란불이 되고, 그러면 나머지 검사의 신호까지 갉아먹는다. 여럿이 만지기 시작하면 `npm run format` 으로 한 번 정리하고 `frontend` 잡의 script 를 `npm run check` 한 줄로 바꾼다. 그 전까지도 로컬에서는 `npm run format:check` 로 언제든 볼 수 있다 |

## 올리기 전에 로컬에서 확인한 것 (2026-09-12)

CI 로 처음 돌렸을 때 **우리 코드가 아니라 파이프라인 설정 때문에** 빨간불이 나는지 가리려고,
잡이 부르는 명령을 먼저 내 PC 에서 그대로 돌려 봤다.

| 명령 | 결과 |
| --- | --- |
| `npm run typecheck` | 통과 |
| `npm run lint` | 통과 (경고 4개, 오류 0 — eslint 는 경고로 실패하지 않는다) |
| `npm run build` | 통과 |
| `npm run format:check` | **실패** — 71개 파일. 이래서 CI 에 넣지 않았다 (위 "아직 없는 것") |
| `./gradlew test` | 통과 (3분 20초) |
| `./gradlew integrationTest` | 통과 — 다만 **이 잡은 로컬 통과가 CI 통과를 뜻하지 않는다.** 아래 "통합 시험은 CI 조건으로 돌려 봐야 한다" |

`npm run lint` 의 경고 4개는 그대로 둔다. `--max-warnings 0` 을 붙이면 오류로 바뀌는데,
그건 CI 를 세우는 일이 아니라 코드를 고치는 일이라 여기서 같이 하지 않는다.

### 통합 시험은 CI 조건으로 돌려 봐야 한다

로컬에는 `localhost:15432` 에 postgres 가 떠 있다. 그래서 **앱의 기본 DB 주소에 그냥
붙어 버리는 시험**은 로컬에서 통과하고 CI 에서만 깨진다 — CI 러너의 `localhost` 에는
아무것도 없고, postgres 는 서비스 별칭 `postgres:5432` 로만 닿기 때문이다.

격리 DB 를 다른 포트에 띄우고 `15432` 를 내리면 그 조건을 로컬에서 만들 수 있다.

```bash
docker run -d --name pg-ci-check -e POSTGRES_PASSWORD=pickage -p 15433:5432 postgres:16
docker compose --profile api stop postgres

cd backend
PICKAGE_TEST_POSTGRES_URL_PREFIX="jdbc:postgresql://localhost:15433/" ./gradlew integrationTest

docker rm -f pg-ci-check && docker compose --profile api start postgres
```

**`BUILD SUCCESSFUL` 이면 CI 에서도 통과한다.** 여기서 `Connection refused ... localhost:15432`
가 나오면 그 시험이 격리 DB 를 안 쓰고 앱 설정의 주소로 붙고 있다는 뜻이다
(`DisposableTestDatabase` 를 거치지 않거나, `@SpringBootTest` 에
`@DynamicPropertySource` 가 빠진 경우).

실행 수를 세어 확인하려면:

```bash
grep -ho 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' \
  backend/build/test-results/integrationTest/*.xml \
  | awk -F'"' '{t+=$2; s+=$4; f+=$6; e+=$8} END {print "tests="t, "skipped="s, "failures="f, "errors="e}'
```

`skipped` 가 3이면 정상이다 — `RepositoryVerificationRealNetworkTest` 가
`GITHUB_COMMUNITY_TOKEN` 없이 건너뛴 것이다.

### 같이 고친 것 — `backend/gradlew` 의 실행 권한

git 에 **`100644`(실행 불가)로 들어가 있었다.** Windows 에서는 이걸 알아챌 수 없다 —
`git-bash` 가 실행해 주기 때문이다. 그대로 두면 리눅스 러너에서 `./gradlew` 가
`Permission denied` 로 죽는다. `backend/Dockerfile` 이 `RUN chmod +x gradlew` 를 갖고 있는
것이 같은 문제를 이미 한 번 만났다는 흔적이다.

```bash
git update-index --chmod=+x backend/gradlew   # → 100755
```

CI 스크립트에서 `chmod` 하지 않고 **저장소의 파일 모드 자체를 고쳤다.** 잡마다 고치면
같은 문제가 다음 잡·다음 Dockerfile 에서 또 나온다.
