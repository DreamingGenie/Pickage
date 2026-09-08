# A506 팀의 빅데이터 분산 프로젝트

에이전트·팀 협업 규칙(초안): [`.agents/AGENTS.md`](.agents/AGENTS.md)

## 개발 환경 셋업

클론 직후 **1회만** 실행하세요. 커밋 메시지에 Jira 이슈 키를 강제하는 git hook이 켜집니다.

```bash
# macOS / Linux / Git Bash
sh scripts/setup-hooks.sh
```

```bat
:: Windows CMD / PowerShell
scripts\setup-hooks.bat
```

### 커밋 메시지 규칙

제목 맨 끝에 Jira 키를 괄호로 붙입니다.

```
feat: deps.dev BigQuery 수집기 추가 (S15P21A506-122)
```

훅은 **브랜치명에 Jira 키가 있을 때만** 동작합니다.

- `feat/S15P21A506-122-bq-collector` → 메시지에 키가 없으면 **자동 삽입**. 키를 엉뚱한 위치에 쓰면 거부.
- `develop`, `chore/project-setting` 등 키 없는 브랜치 → 검사하지 않음.
- Merge / Revert / fixup! 커밋 → 검사 제외.

## 저장소 구조

| 폴더 | 내용 |
|---|---|
| `docs/` | 기획·요구사항·수집계획·검증 문서. `docs/api & data/`가 수집계획 정본, `docs/history/`는 폐기·아카이브 |
| `pipeline/` | 데이터 수집·변환 코드. `collectors/`(deps.dev BigQuery · npm downloads · ecosyste.ms keywords), `curated/`(PostgreSQL 적재용 정제), `minio/`, `duckdb/`(로컬 분석·데이터셋 빌더). 지도는 `pipeline/README.md` |
| `datasets/` | 팀 공유용 작은 파생 데이터(추적). 폐기→대체 쌍, 마이그레이션 이동쌍, 학습 후보 표본, 수집 대상 목록. 지도는 `datasets/README.md` |
| `data/` | 로컬 수집 데이터(gitignore). GCS `gs://oss-shift-a506-raw`가 팀 공유 정본 |
| `backend/` | Spring Boot 서빙 API. Flyway 마이그레이션(`src/main/resources/db/migration/`)이 DB 스키마 정본 |
| `frontend/` | Vite + React + TS SPA. 문서는 `frontend/README.md` |
| `deploy/local/` | 로컬 개발용 MinIO·Spark·시드. 루트 `compose.yaml`과 함께 사용. 절차는 `deploy/local/README.md` |
| `scripts/` | git hook 설치 스크립트(위 "개발 환경 셋업") |
| `.venv-bq/` | 수집용 Python 가상환경(gitignore) |

폐기된 교통 데이터 수집기는 `docs/history/0901_journey_reliability_legacy/collector/`에 있다.
