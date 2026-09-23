# A506 팀의 빅데이터 분산 프로젝트

팀 협업 규칙: [`AGENTS.md`](AGENTS.md) — 브랜치·커밋 컨벤션, Jira 연동 절차, MR 템플릿, 환경 차이.
AI 에이전트를 쓰면 Claude 는 [`CLAUDE.md`](CLAUDE.md), Codex 등은 `AGENTS.md` 를 자동으로 읽습니다.

## 개발 환경 셋업

클론 직후 **1회만** 실행하세요. 브랜치명·커밋 메시지를 검사하는 git hook 이 켜집니다.

```bash
# macOS / Linux / Git Bash
sh scripts/setup-hooks.sh
```

```bat
:: Windows CMD / PowerShell
scripts\setup-hooks.bat
```

## 브랜치·커밋 규칙

정본은 [`AGENTS.md`](AGENTS.md) 4번 항목입니다. 여기는 실제로 쓰는 명령만 적습니다.

### 브랜치는 헬퍼로 만듭니다

```bash
sh scripts/new-branch.sh data feat 290 downloads bronze ingest
# → origin/develop 에서 data/feat/S15P21A506-290-downloads-bronze-ingest 생성
```

```bat
:: Windows CMD / PowerShell
scripts\new-branch.bat data feat 290 downloads bronze ingest
```

이름 형식은 `<part>/<type>/<이슈키>-작업내용` 입니다.

- `part` — `frontend` `api` `data` `ai` `worker` `infra` `docs` `plan` (**담당 파트. 폴더명이 아닙니다**)
- `type` — `feat` `fix` `refactor` `test` `chore` `docs` `style` `config`
- 이슈키는 `S15P21A506-290` 처럼 프로젝트 키까지 씁니다

`part` 를 빠뜨린 `feat/S15P21A506-290-...` 는 규칙 위반입니다. **2026-09-09 이전 브랜치는 전부
이 형태이므로 기존 이름을 보고 새 브랜치를 만들지 마세요.**

### 커밋 제목

```
feat: deps.dev BigQuery 수집기 추가 (S15P21A506-122)
```

- `type: subject` — 콜론 **뒤에만** 공백. 50자 이내(넘으면 경고), 끝에 마침표 없음
- 본문에는 어떻게가 아니라 **무엇을·왜** 바꿨는지 씁니다
- Jira 키는 제목 맨 끝 괄호. **브랜치명에 키가 있으면 훅이 자동으로 넣어 줍니다**

### 훅이 언제 막는지

| 훅 | 언제 | 거부 | 경고만 |
|---|---|---|---|
| `commit-msg` | 커밋할 때마다 | `type:` 형식 위반, 제목 끝 마침표, Jira 키 위치 오류 | 제목 50자 초과, 브랜치와 다른 키 |
| `pre-push` | **새 브랜치를 처음 push 할 때** | 브랜치명 규칙 위반 | `develop`·`main` 직접 push |

- 이미 원격에 있는 브랜치의 추가 push 는 이름을 검사하지 않습니다 — 규칙 도입 전 브랜치의 작업이 막히지 않습니다.
- Merge / Revert / fixup! 커밋과 태그 push 는 검사 대상이 아닙니다.
- 규칙 구현은 `scripts/lib/check-branch-name.sh` 한 곳에 있습니다. 훅과 헬퍼가 같은 파일을 씁니다.
- 예외가 꼭 필요하면 `git commit --no-verify` / `git push --no-verify` 입니다. 상시로 쓰지 마세요.

## 저장소 구조

| 폴더 | 내용 |
|---|---|
| `docs/` | 기획·요구사항·수집계획·검증 문서. `docs/api & data/`가 수집계획 정본, `docs/history/`는 폐기·아카이브 |
| `exec/` | **제출용 포팅 매뉴얼** — 빌드·배포 매뉴얼, 외부 서비스 정보, DB 덤프, 시연 시나리오. 폴더명은 제출 규격이라 바꾸지 않는다. 운영 절차의 정본은 `deploy/` 쪽이다 |
| `pipeline/` | 데이터 수집·변환 코드. `collectors/`(deps.dev BigQuery · npm downloads · ecosyste.ms keywords), `curated/`(PostgreSQL 적재용 정제), `minio/`, `duckdb/`(로컬 분석·데이터셋 빌더). 지도는 `pipeline/README.md` |
| `datasets/` | 팀 공유용 작은 파생 데이터(추적). 폐기→대체 쌍, 마이그레이션 이동쌍, 학습 후보 표본, 수집 대상 목록. 지도는 `datasets/README.md` |
| `data/` | 로컬 수집 데이터(gitignore). GCS `gs://oss-shift-a506-raw`가 팀 공유 정본 |
| `backend/` | Spring Boot 서빙 API. Flyway 마이그레이션(`src/main/resources/db/migration/`)이 DB 스키마 정본 |
| `frontend/` | Vite + React + TS SPA. 문서는 `frontend/README.md` |
| `deploy/local/` | 로컬 개발용 MinIO·Spark·시드. 루트 `compose.yaml`과 함께 사용. 절차는 `deploy/local/README.md` |
| `deploy/ci/`, `.gitlab-ci.yml` | MR 에서 도는 검증 파이프라인(프런트 검사·빌드, 백엔드 단위·통합 시험). 러너 등록 절차는 `deploy/ci/README.md` |
| `scripts/` | git hook 설치·브랜치 생성 헬퍼. 브랜치명 규칙 구현은 `scripts/lib/check-branch-name.sh` |
| `.githooks/` | `commit-msg`(커밋 형식·Jira 키), `pre-push`(브랜치명). `setup-hooks` 로 켭니다 |
| `.venv-bq/` | 수집용 Python 가상환경(gitignore) |

폐기된 교통 데이터 수집기는 `docs/history/0901_journey_reliability_legacy/collector/`에 있다.
