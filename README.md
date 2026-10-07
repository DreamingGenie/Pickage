# Pickage

> 패키지 선택에, 확인할 근거를

**Pickage**는 개발자가 npm 패키지를 선택하거나 교체할 때 최대 3개의 패키지를
**생태계 변화, 기능 차이, GitHub 커뮤니티** 관점에서 비교하는 의사결정 보조 서비스입니다.
분석 결과는 사람이 검토하는 PDF와 AI 코딩 에이전트에 전달하는 HAND-OFF Markdown으로
내보낼 수 있습니다.

SSAFY 15기 A506 팀의 빅데이터 분산 프로젝트입니다. 이 README는 2026-09-23의 병합 코드와
기획 정본을 기준으로 작성했습니다.

> **운영 종료 (2026-10)** — 운영 서버(EC2)는 2026-10-02에 정리돼 서비스는 더 이상 열리지 않고,
> 운영 DB도 남아 있지 않습니다. 아래 [프로젝트 실행](#프로젝트-실행) 절차로 로컬에서 띄운 화면의 값은
> 실제 분석 결과가 아니라 **목업 데이터**(프런트 mock 또는 `seed/seed_service_full.sql`)입니다.

## 목차

- [프로젝트 소개](#프로젝트-소개)
- [왜 Pickage인가](#왜-pickage인가)
- [주요 기능](#주요-기능)
- [서비스 흐름과 메뉴](#서비스-흐름과-메뉴)
- [기술 스택](#기술-스택)
- [시스템 구성](#시스템-구성)
- [프로젝트 실행](#프로젝트-실행)
  - [가장 빠른 UI 체험](#가장-빠른-ui-체험)
  - [API와 샘플 데이터 연동](#api와-샘플-데이터-연동)
  - [데이터 개발 환경](#데이터-개발-환경)
  - [접속 주소](#접속-주소)
  - [종료와 초기화 주의사항](#종료와-초기화-주의사항)
- [테스트와 검증](#테스트와-검증)
- [저장소 구조](#저장소-구조)
- [프로젝트 현황과 알려진 제한](#프로젝트-현황과-알려진-제한)
- [프로젝트 문서](#프로젝트-문서)
- [개발 참여 안내](#개발-참여-안내)
- [과거 자료](#과거-자료)

## 프로젝트 소개

패키지를 고를 때 다운로드 수 하나만으로는 충분하지 않습니다. 실제로 사용이 늘고 있는지, 다른
프로젝트가 어떤 패키지로 이동하는지, 필요한 기능과 실행 조건을 만족하는지, 저장소가 유지되고
있는지를 서로 다른 출처에서 확인해야 합니다.

Pickage는 이 근거를 하나의 분석 흐름으로 모읍니다.

- **생태계 변화**로 패키지의 사용 추이와 관측된 이동 신호를 확인합니다.
- **기능 비교**로 선택한 버전의 실행 환경과 README 기반 공통점·차이를 확인합니다.
- **GitHub 커뮤니티**로 기준 패키지 저장소의 공개 활동과 핵심 논의를 확인합니다.
- 같은 결과를 **PDF**로 공유하거나 **HAND-OFF Markdown**으로 에이전트에 전달합니다.

Pickage는 특정 패키지를 승자로 정하거나 교체 결론을 대신 내리지 않습니다. 관측 데이터의 기준일,
단위, 결측과 한계를 함께 보여 주고 최종 판단은 사용자에게 남깁니다.

## 왜 Pickage인가

| 패키지를 비교할 때 생기는 문제 | Pickage가 제공하는 해법 |
| --- | --- |
| 다운로드 수는 인기도는 보여도 실제 이동 방향을 설명하지 못함 | 다운로드·의존 수·유입·유출·제거 이유·관측 이동을 함께 제공 |
| 여러 패키지 README를 같은 기준으로 읽기 어려움 | 버전별 실행 환경과 RAG 공통점·차이를 한 화면에서 비교 |
| GitHub 지표는 기준일과 의미가 달라 단일 숫자로 판단하기 어려움 | 활동·반응·기여·유지보수 근거와 수집 상태를 함께 표시 |
| 조사 결과를 팀원이나 AI 에이전트에게 다시 전달하기 어려움 | PDF와 구조화된 HAND-OFF Markdown 제공 |

분석 대상은 **npm 생태계**이며 비교 대상은 기준 패키지를 포함해 **최대 3개**입니다.

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| 패키지 검색 | 제공 가능한 npm 패키지를 검색하고 기준 패키지를 선택합니다. |
| 유사 후보와 직접 추가 | 임베딩 기반 후보를 최대 3개 보여 주며, 원하는 패키지를 직접 추가할 수도 있습니다. 후보는 자동 선택하지 않습니다. |
| 생태계 변화 | 패키지 개요, Downloads, 의존 수, 버전 점유율, 의존 전환, 제거 이유, 관측 이동 경로를 비교합니다. |
| 기능 비교 | 패키지별 버전을 고르고 module format·타입·의존 조건과 README 기반 공통점·차이를 비교합니다. |
| GitHub 커뮤니티 | 기준 패키지 하나의 저장소 활동, 핵심 Issue와 실제 논의, 수집 상태를 보여 줍니다. |
| PDF | 생태계 분석을 기본으로 커뮤니티와 완료된 기능 비교를 선택해 미리 보고 내려받습니다. |
| HAND-OFF | 현재 분석을 AI 에이전트가 이어서 사용할 수 있는 Markdown 파일로 내려받습니다. |

교체 흐름과 이동 경로는 의존성 선언에서 **함께 관측된 변화**입니다. 실제 대체의 인과관계나
추천 순위를 의미하지 않습니다.

## 서비스 흐름과 메뉴

```text
패키지 검색
    → 유사 후보 선택 또는 직접 추가
    → 기준 패키지를 포함해 최대 3개 확정
    → 생태계 변화 · 기능 비교 · GitHub 커뮤니티 확인
    → PDF 또는 HAND-OFF Markdown 출력
```

### 화면 경로

| 경로 | 화면 | 역할 |
| --- | --- | --- |
| `/` | 서비스 소개·검색 | Pickage의 분석 관점을 확인하고 기준 패키지를 선택합니다. |
| `/analyze` | 비교 대상 구성 | 유사 후보를 선택하거나 다른 패키지를 직접 추가합니다. |
| `/analyze/candidates` | 이전 호환 경로 | 현재 `/analyze`로 이동합니다. |
| `/report/:reportId` | 분석 보고서 | 세 분석 탭을 탐색하고 결과를 내보냅니다. 현재 UI의 `reportId`는 `draft`입니다. |

분석 화면은 `base`, `with`, `nosimilar` 쿼리로 선택을 유지하고, 보고서는 `names` 쿼리로 최대
3개의 패키지를 복원합니다.

### 보고서 메뉴

#### 생태계 변화

- 패키지 개요
- Downloads·의존 수 주간 추이
- 버전 점유율
- 1년·3년·5년 의존 전환
- 제거 이유
- regular·dev 관측 이동 경로

#### 기능 비교

- 패키지별 버전 후보와 버전 선택
- module format, bundled types, direct·peer dependency 등 실행 환경
- README 근거 기반 공통점과 패키지별 차이
- 핵심 용어·핵심 문장 강조와 자료 제한 상태

#### GitHub 커뮤니티

- 기준 패키지 저장소와 기준일
- 저장소 활동과 열린 Issue
- 핵심 논의 요약과 실제 발화
- 수집·갱신·부분 자료 상태

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | React 19, TypeScript 6, React Router 7, TanStack Query 5, Tailwind CSS 4, Vite 8 |
| Backend | Java 21, Spring Boot 4, Spring Data JPA, PostgreSQL 16, Flyway |
| AI | FastAPI, ONNX Runtime, MLflow, `BAAI/bge-small-en-v1.5`, GMS Responses API |
| Data | Python, DuckDB, Apache Spark 3.5, deps.dev BigQuery, npm registry·downloads |
| Storage | PostgreSQL, MinIO, GCS |
| Infra | Docker Compose, nginx, GitLab CI/CD, Netdata |
| Test | Vitest, JUnit, Gradle integration test, pytest |

## 시스템 구성

```text
Browser
  └─ React SPA
      └─ /api
          └─ Spring Boot API
              ├─ PostgreSQL / Flyway V1~V13
              ├─ FastAPI RAG
              ├─ GitHub 수집 / GMS 요약
              └─ PDF / HAND-OFF 생성

Data pipeline
  ├─ npm registry / npm downloads / deps.dev BigQuery
  ├─ Python / DuckDB / Spark 변환
  ├─ GCS / MinIO 원본·중간·모델 보관
  └─ PostgreSQL 서비스 테이블 게시
```

운영은 앱 노드와 데이터 노드로 나뉩니다. 앱 노드는 web·API·RAG·PostgreSQL과 loader를,
데이터 노드는 MinIO·MLflow·Spark와 수집·배치를 담당합니다. 운영 배포의 상세 계약은
[`deploy/prod/README.md`](deploy/prod/README.md)를 참고하세요.

## 프로젝트 실행

### 준비 사항

실행 범위에 따라 필요한 도구가 다릅니다.

| 도구 | 권장 기준 | 필요한 경우 |
| --- | --- | --- |
| Git | 최신 안정 버전 | 공통 |
| Node.js | 22 | 프런트엔드 |
| npm | Node.js에 포함 | 프런트엔드 |
| Docker Desktop·Compose v2 | 최신 안정 버전 | API·DB·MinIO·Spark |
| Java | 21 | 백엔드를 컨테이너 밖에서 직접 실행할 때 |
| Python | 3.11 | AI·데이터 파이프라인을 직접 실행할 때 |

모든 명령은 별도 설명이 없으면 저장소 루트에서 실행합니다.

### 가장 빠른 UI 체험

외부 API 키나 로컬 DB 없이 전체 사용자 흐름을 확인하려면 프런트 mock을 사용합니다.

macOS·Linux·Git Bash:

```bash
cp frontend/.env.example frontend/.env.local
cd frontend
npm ci
npm run dev
```

Windows PowerShell:

```powershell
Copy-Item frontend/.env.example frontend/.env.local
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

`frontend/.env.example`의 기본값은 `VITE_USE_MOCK=true`입니다. 브라우저에서
`http://localhost:5173`에 접속합니다. 화면의 값은 개발용 예시이며 실제 분석 결과가 아닙니다.

### API와 샘플 데이터 연동

Spring API와 PostgreSQL을 실제로 연결하고 기본 생태계 화면을 확인하는 절차입니다.

1. `frontend/.env.local`을 만들고 다음 값으로 바꿉니다.

   ```dotenv
   VITE_API_BASE_URL=/api
   VITE_USE_MOCK=false
   ```

2. PostgreSQL과 API를 빌드해 실행합니다.

   ```bash
   docker compose --profile api up -d --build
   docker compose ps
   ```

3. Flyway 적용이 끝난 뒤 화면 확인용 샘플 데이터를 넣습니다.

   ```bash
   docker compose exec -T postgres \
     psql -U postgres -d pickage -f seed/seed_service_full.sql
   ```

4. 프런트엔드를 실행합니다.

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

Windows PowerShell에서는 `npm` 대신 `npm.cmd`를 사용할 수 있습니다. 백엔드를 컨테이너 밖에서
직접 실행하려면 PostgreSQL만 올린 뒤 `backend`에서 `gradlew.bat bootRun`을 실행합니다.

```powershell
docker compose --profile api up -d postgres
Set-Location backend
.\gradlew.bat bootRun
```

> `seed_service_full.sql`은 화면과 API 계약 확인을 위한 예시 데이터입니다. 실제 분석 근거로 사용하지
> 마세요. 실제 Curated 데이터가 게시된 DB에는 seed를 실행하면 안 됩니다.

루트 `api` profile에는 FastAPI RAG 컨테이너가 없습니다. 따라서 실제 기능 비교 생성은 별도 RAG
실행 환경이 필요합니다. GitHub 커뮤니티의 실제 갱신과 GMS 요약도 외부 자격증명이 없으면 비활성화
되거나 제한된 결과를 반환합니다. 전체 UI 동작을 자격증명 없이 확인할 때는 mock 실행을 사용하세요.

### 데이터 개발 환경

> ⚠ compose가 쓰는 MinIO 이미지(`minio/minio:RELEASE.2025-04-22T22-12-26Z`)는 공식 배포가 중단돼
> 새로 받을 수 없습니다(Docker Hub 저장소 삭제, `quay.io/minio/minio` 익명 pull 차단 — 2026-10-06 확인).
> `--profile data`는 이 이미지를 이미 받아 둔 환경에서만 뜹니다. 화면과 API 확인에는 필요 없습니다.

MinIO와 Spark가 필요한 데이터 작업은 먼저 로컬 전용 자격증명을 만듭니다.

macOS·Linux·Git Bash:

```bash
cp pipeline/minio/.env.example pipeline/minio/.env
# pipeline/minio/.env의 MINIO_ROOT_PASSWORD를 로컬 전용 값으로 변경
docker compose --profile data up -d
```

Windows PowerShell:

```powershell
Copy-Item pipeline/minio/.env.example pipeline/minio/.env
# pipeline/minio/.env의 MINIO_ROOT_PASSWORD를 로컬 전용 값으로 변경
docker compose --profile data up -d
```

모든 로컬 서비스를 함께 올릴 때는 `docker compose --profile all up -d`를 사용합니다. 자세한 seed,
Spark, Curated 적재 절차는 [`deploy/local/README.md`](deploy/local/README.md), 파이프라인별 실행법은
[`pipeline/README.md`](pipeline/README.md)를 참고하세요.

### 접속 주소

| 대상 | 주소·포트 | 비고 |
| --- | --- | --- |
| Web | `http://localhost:5173` | Vite 개발 서버 |
| API 문서 | `http://localhost:8080/swagger-ui/index.html` | API profile 또는 `bootRun` |
| PostgreSQL | `localhost:15432` | `postgres` / `pickage`, 로컬 전용 |
| MinIO S3 API | `http://localhost:9000` | data profile |
| MinIO Console | `http://localhost:9001` | data profile |

포트는 모두 `127.0.0.1`에만 공개됩니다. 운영 자격증명을 로컬 설정에 재사용하지 마세요.

### 종료와 초기화 주의사항

데이터를 유지한 채 서비스를 내립니다.

```bash
docker compose --profile all down
```

컨테이너만 잠시 멈추려면 다음 명령을 사용합니다.

```bash
docker compose --profile all stop
```

> **`docker compose down -v`를 실행하지 마세요.** `-v`는 PostgreSQL뿐 아니라 MinIO에 적재한
> 원본 데이터까지 삭제합니다. DB만 초기화해야 할 때도 먼저
> [`deploy/local/README.md`](deploy/local/README.md)의 초기화 절차와 대상 볼륨을 확인하세요.

## 테스트와 검증

### 프런트엔드

```bash
cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
```

PowerShell 실행 정책으로 `npm.ps1`이 차단되면 `npm.cmd`를 사용합니다.

### 백엔드

macOS·Linux·Git Bash:

```bash
cd backend
./gradlew test
```

Windows PowerShell:

```powershell
Set-Location backend
.\gradlew.bat test
```

실제 PostgreSQL이 필요한 통합 테스트는 DB를 먼저 실행합니다.

```bash
docker compose --profile api up -d postgres
cd backend
./gradlew integrationTest
```

### AI와 RAG

필요한 Python 의존성을 준비한 환경에서 실행합니다.

```bash
python -m pytest ai
```

### 데이터 파이프라인

파이프라인은 수집기·변환기마다 요구하는 의존성과 실행 환경이 다릅니다. 모듈별 테스트는 각 폴더의
README를 따르세요. 현재 저장소 전체 `python -m pytest pipeline`은 중복 모듈명, 상대 import,
로컬 PySpark 의존성 때문에 공통 성공 명령으로 사용하지 않습니다. CI의 `pipeline-ok`도 전체 테스트가
아니라 실행 환경 smoke 검사입니다.

MR에서는 `.gitlab-ci.yml`의 프런트엔드, 백엔드 단위·통합, AI, RAG, pipeline smoke job이
변경 영역에 맞게 실행됩니다.

## 저장소 구조

| 경로 | 내용 |
| --- | --- |
| `frontend/` | React·Vite SPA. 화면·상태·API client와 mock을 포함합니다. 상세 지도는 `frontend/README.md`입니다. |
| `backend/` | Spring Boot API. `src/main/resources/db/migration/`의 Flyway SQL이 DB 스키마 정본입니다. |
| `ai/` | 유사 패키지 ONNX 배치와 기능 비교 RAG API입니다. |
| `pipeline/` | 데이터 수집·변환 코드입니다. `collectors/`는 deps.dev BigQuery·npm downloads·registry 등을 수집하고, `curated/`는 PostgreSQL 적재용으로 정제하며, `minio/`와 `duckdb/`는 입고·로컬 분석·데이터셋 빌드를 담당합니다. 지도는 `pipeline/README.md`입니다. |
| `datasets/` | 팀이 함께 추적하는 작은 파생 데이터입니다. 폐기→대체 쌍, 이동 경로, 학습 후보 표본과 수집 대상 목록의 계약 README를 보관하며 대용량 원본은 넣지 않습니다. |
| `data/` | 로컬 수집 데이터 경로이며 Git에서 제외됩니다. GCS `gs://oss-shift-a506-raw`와 MinIO가 팀 공유 원본·중간 저장소입니다. |
| `deploy/local/` | 루트 `compose.yaml`과 함께 쓰는 로컬 MinIO·Spark·seed 설정입니다. |
| `deploy/prod/` | 앱·데이터 노드 운영 compose, 배포·백업·복구 절차입니다. |
| `deploy/ci/`, `.gitlab-ci.yml` | MR에서 실행하는 프런트 검사·빌드, 백엔드 단위·통합 시험, AI·RAG·pipeline smoke와 develop·main 배포 파이프라인입니다. 러너 절차는 `deploy/ci/README.md`에 있습니다. |
| `docs/` | 기획·요구사항·수집 계획·검증 문서입니다. `docs/api & data/`는 데이터 수집 계획, `docs/history/`는 교체·폐기 문서, `docs/worklogs/`는 작업 근거를 보관합니다. |
| `exec/` | **제출용 포팅 매뉴얼**입니다. 빌드·배포 매뉴얼, 외부 서비스 정보, DB 덤프, 시연 시나리오를 담습니다. 폴더명은 제출 규격이라 바꾸지 않으며, 운영 절차의 정본은 `deploy/` 쪽입니다. |
| `scripts/` | Git hook 설치와 브랜치 생성 helper입니다. 브랜치명 규칙 구현은 `scripts/lib/check-branch-name.sh`에 있습니다. |
| `.githooks/` | `commit-msg`는 커밋 형식·Jira 키를, `pre-push`는 새 브랜치 이름을 검사합니다. `setup-hooks`로 활성화합니다. |
| `tests/` | 저장소 공통 계약과 정적 검증 자료입니다. |
| `.venv-bq/` | 데이터 수집용 로컬 Python 가상환경이며 Git에서 제외됩니다. |

수집·계산으로 만든 파생 데이터의 열 의미와 생성 근거는
[`datasets/README.md`](datasets/README.md)와 각 데이터셋 폴더의 README를 따릅니다.

## 프로젝트 현황과 알려진 제한

2026-09-23 기준으로 패키지 입력부터 보고서 세 탭, PDF, HAND-OFF까지의 핵심 사용자 흐름은
`develop`에 구현돼 있습니다. 다음 경계는 현재 제품 계약의 일부입니다.

- npm 패키지만 분석하며 비교는 최대 3개입니다.
- GitHub 커뮤니티는 비교 목록 전체가 아니라 기준 패키지 하나를 분석합니다.
- 보고서 경로는 현재 `/report/draft`이며 사용자 분석 세션을 영구 저장하지 않습니다.
- 기능 비교와 출력 작업 상태는 서버 프로세스 메모리에 있어 재시작 시 사라질 수 있습니다.
- 확장 대상 목록은 468,519개지만 similarity 배치 기본 범위는 100,000개입니다.
- 관측 이동 경로는 동시 변경 통계이며 실제 대체의 인과관계를 보증하지 않습니다.
- 일부 최신 파생 지표, 운영 모니터링, 직접 추가 URL 상태에는 후속 작업이 남아 있습니다.

완료·부분 완료·운영 확인 필요를 나눈 근거는
[`개발 현황 조사 보고서`](docs/worklogs/S15P21A506-473/01_개발현황_조사보고서_260923.md)를
참고하세요.

## 프로젝트 문서

| 문서 | 역할 |
| --- | --- |
| [`서비스 기획서`](docs/Pickage_서비스_기획서_0923.md) | 제품 정의, 사용자 가치, 현재 범위와 제약 |
| [`요구사항 명세서`](docs/Pickage_요구사항_명세서_0923.md) | 기능·API·데이터·비기능 요구사항과 상태 |
| [`메뉴구조·IA`](docs/Pickage_메뉴구조_IA_0923.md) | 라우트, URL 상태, 화면 계층과 오류·빈 상태 |
| [`기능별 개발 구상안`](docs/Pickage_기능별_개발_구상안_0923.md) | 현재 아키텍처, API, AI, 데이터, 운영 설계 |
| [`0917→0923 변경 상세분석`](docs/Pickage_0917_to_0923_기획변경_상세분석.md) | 이전 기획 대비 추가·삭제·축소·보류 근거 |
| [`로컬 실행 상세`](deploy/local/README.md) | seed, Spark, Curated 적재와 초기화 주의사항 |
| [`운영 배포`](deploy/prod/README.md) | 앱·데이터 노드 배포, 백업과 복구 |
| [`팀 협업 규칙`](AGENTS.md) | Jira, 브랜치, 커밋, MR, 환경 차이의 정본 |

## 개발 참여 안내

팀 협업 규칙의 정본은 [`AGENTS.md`](AGENTS.md)입니다. 브랜치·커밋 컨벤션, Jira 연동 절차,
MR 템플릿과 로컬·운영 환경 차이를 정의합니다. AI 에이전트를 쓰면 Claude는
[`CLAUDE.md`](CLAUDE.md), Codex 등은 `AGENTS.md`를 읽습니다.

### Git hook 설치

클론 직후 한 번 실행합니다. 브랜치명과 커밋 메시지를 검사하는 Git hook이 켜집니다.

macOS·Linux·Git Bash:

```bash
sh scripts/setup-hooks.sh
```

Windows CMD·PowerShell:

```bat
scripts\setup-hooks.bat
```

### 브랜치 생성

브랜치는 helper로 만듭니다.

```bash
sh scripts/new-branch.sh data feat 290 downloads bronze ingest
# origin/develop에서 data/feat/S15P21A506-290-downloads-bronze-ingest 생성
```

```bat
scripts\new-branch.bat data feat 290 downloads bronze ingest
```

이름 형식은 `<part>/<type>/<이슈키>-작업내용`입니다.

- `part`: `frontend` `api` `data` `ai` `worker` `infra` `docs` `plan`
- `type`: `feat` `fix` `refactor` `test` `chore` `docs` `style` `config`
- 이슈 키: `S15P21A506-290`처럼 프로젝트 키까지 사용
- 작업 내용: 영문 kebab-case

`part`는 폴더명이 아니라 담당 파트입니다. `part`를 빠뜨린
`feat/S15P21A506-290-...` 형식은 규칙 위반입니다. 2026-09-09 이전 브랜치 이름을 새 작업의
예시로 사용하지 마세요.

### 커밋 규칙

```text
feat: deps.dev BigQuery 수집기 추가 (S15P21A506-122)
```

- `type: subject` 형식이며 콜론 뒤에만 공백을 둡니다.
- 제목은 50자 이내를 권장하고 끝에 마침표를 붙이지 않습니다.
- 본문에는 구현 방법보다 무엇을·왜 바꿨는지 적습니다.
- Jira 키는 제목 맨 끝 괄호에 둡니다.
- 브랜치명에 Jira 키가 있으면 commit hook이 자동으로 넣습니다.

### Hook 동작

| Hook | 실행 시점 | 거부 | 경고만 |
| --- | --- | --- | --- |
| `commit-msg` | 커밋할 때마다 | `type:` 형식 위반, 제목 끝 마침표, Jira 키 위치 오류 | 제목 50자 초과, 브랜치와 다른 키 |
| `pre-push` | 새 브랜치를 처음 push할 때 | 브랜치명 규칙 위반 | `develop`·`main` 직접 push |

- 이미 원격에 있는 브랜치의 추가 push는 이름을 다시 검사하지 않습니다.
- Merge, Revert, `fixup!` 커밋과 태그 push는 검사 대상이 아닙니다.
- 브랜치 규칙 구현은 `scripts/lib/check-branch-name.sh` 한 곳에 있습니다.
- 예외가 꼭 필요하면 `git commit --no-verify` 또는 `git push --no-verify`를 사용할 수 있지만
  상시 사용하지 않습니다.

## 과거 자료

이 프로젝트의 최초 주제는 서울 대중교통 실시간 데이터 기반 Journey Reliability였습니다.
2026-08-28 폐기 후 관련 기획·수집기·기준 데이터는
[`docs/history/0901_journey_reliability_legacy/`](docs/history/0901_journey_reliability_legacy/)에
보존했습니다. 현재 Pickage 구현과 섞어 사용하지 않습니다.

이전 Pickage 기획 세트와 완료된 작업 기록도 `docs/history/`에 원문을 보존합니다. 현재 기획 정본은
위 [프로젝트 문서](#프로젝트-문서)의 2026-09-23 문서 5종입니다.
