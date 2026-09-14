# CI — GitLab Runner 와 파이프라인

MR 을 열면 무엇이 돌고, 그것을 돌리는 러너를 어떻게 세우는지. (S15P21A506-143)

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
| `develop`·`main` 에 머지 | ✅ 전체 (CD 도 여기 붙는다 — S15P21A506-223) |
| Pipelines → **Run pipeline** (수동) | ✅ 돈다 |

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
| `app` | postgres 2g + api 1.6g + web 0.25g + worker② 6.5g ≈ **10g** | ~5g | 300G 남음 |
| `data` | minio 1g + mlflow 0.5g + master 1g + worker① 10g + ai 2g ≈ **14.5g** | ~0.5g | 264G 남음 |

`data` 노드는 배치 중에 CI 잡 하나를 얹을 자리가 없다. 그리고 나중에 CD(S15P21A506-223)가
붙으면 `app` 의 compose 를 조작하게 되는데, 러너가 그 노드에 있으면 SSH 키나 Docker 소켓을
다른 호스트에 넘기지 않아도 된다.

> ⚠ **여유가 5g 라는 것은 배치 시각에 CI 가 겹쳐도 된다는 뜻이 아니다.** 아래 "메모리" 에서
> 잡 컨테이너에 상한을 박고, 그래도 불안하면 배치 전에 `sudo gitlab-runner stop` 한다.

## 등록 절차

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

잡이 **exit code 137** 로 죽으면 컨테이너 상한에 걸린 것이다. 로그 마지막에 아무 설명이
없는 것이 특징이다. 힙을 늘려야 하면 위 표의 값과 `[runners.docker] memory` 를 **함께**
올린다 — `memory_swap` = `memory` 라 넘기는 순간 완충 없이 죽는다.

## 디스크 — 정리는 하되, `-a` 는 쓰지 않는다

CI 가 돌수록 이미지·빌드 캐시·죽은 컨테이너가 쌓인다. 일주일에 한 번쯤:

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
| 돌아야 할 잡이 파이프라인에 아예 없다 | `changes:` 규칙. 바꾼 경로가 목록에 없거나(위 "바뀐 폴더의 잡만 돈다"), 수동 실행에서 `compare_to` 기준으로 이미 develop 과 같은 상태다 |
| push 했는데 **파이프라인 자체가 안 생긴다** | 설계대로다. MR 이 없거나 Draft 다 — 위 "언제 도나" |
| Ready 로 바꿨는데 파이프라인이 안 생긴다 | Draft → Ready 는 트리거가 아니다. Pipelines 탭의 **Run pipeline** — 위 "언제 도나" |

## 아직 없는 것

| | 왜 아직 없나 |
| --- | --- |
| **파이썬(`pipeline/`) 시험** | 폴더마다 실행 방법이 다르다 — `python -m unittest discover -s pipeline/curated`, `python -m unittest pipeline.package_snapshot.test_input`, 그 폴더 안에서만 되는 import 까지 섞여 있다. 게다가 일부는 docker·Postgres 를 요구한다(`test_postgres`·`test_integration`). **어느 것을 CI 대상으로 삼을지 고르는 것 자체가 작업**이라 후속 이슈로 뺐다 |
| **CD(자동 배포)** | 별도 이슈 **S15P21A506-223**. 이 파이프라인은 검증만 한다 |
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
