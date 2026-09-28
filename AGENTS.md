# S15P21A506 팀 공통 에이전트 규칙

사람 팀원과 AI 에이전트가 함께 지키는 협업 규칙입니다. **작업을 시작하기 전에 읽어 주세요.**

- **AI 에이전트용**: 이 파일이 규칙 정본입니다. Claude Code 는 루트 [`CLAUDE.md`](CLAUDE.md) 를 통해,
  Codex 등 다른 도구는 저장소 루트의 이 `AGENTS.md` 를 직접 읽습니다.
  (~2026-09-09 까지 이 문서는 `.agents/AGENTS.md` 에 있었고, 그 경로는 어느 도구도
  자동으로 읽지 않아 규칙이 지켜지지 않았습니다. 그래서 루트로 옮겼습니다.)
- **확정**: 기록 언어 규칙 · 작업 전 Jira 연동 워크플로우 · Git 브랜치·커밋 컨벤션 ·
  MR 템플릿 · Jira 이슈 템플릿
- 아직 합의되지 않은 항목은 8번 항목에 모여 있습니다.

## 1. Jira 프로젝트 정보

- Cloud: `ssafy.atlassian.net`
- Project Key: `S15P21A506`
- Board(Timeline): https://ssafy.atlassian.net/jira/software/c/projects/S15P21A506/boards/14925/timeline
- 이슈 유형 (한글 이름으로 JQL 검색하면 `이슈 유형 = 에픽` 같은 쿼리가 실패하는 경우가 있어
  **ID로 검색하는 것을 권장**):
  | 이름 | ID |
  | --- | --- |
  | 에픽 (Epic) | `10000` |
  | 스토리 (Story) | `10001` |
  | 작업 (Task) | `10002` |
  | 하위 작업 (Subtask) | `10003` |
  | 버그 (Bug) | `10004` |
- 에픽 연결: `createJiraIssue`의 `parent` 파라미터에 에픽 키(예: `S15P21A506-20`)를 지정
  (classic 프로젝트라 내부적으로 `customfield_10014` 에픽 링크 필드와 동기화됨)
- 스프린트 연결: `customfield_10020` (스프린트 ID 정수 단일값, 예: `53719`. 배열로 감싸면
  `createJiraIssue`에서 "스프린트에 유효한 값을 지정하세요" 오류 발생) — `additional_fields`로 지정

## 2. 기록 언어 규칙 — MR / Jira (확정)

에이전트가 생성하는 Merge Request와 Jira 이슈는 **한국어로 기록**합니다.
영어로만 작성하면 팀원들이 리뷰/추적하기 어렵기 때문입니다.

- **Merge Request**
  - 제목(title): 영어 가능 (커밋 메시지 컨벤션과 맞춰도 무방)
  - 본문(description): **반드시 한국어**로 작성 — 변경 이유, 주요 변경 내용,
    영향 범위, 확인/테스트 방법 등을 팀원이 읽고 리뷰할 수 있게 기술
- **Jira 이슈**
  - 제목, 설명, 코멘트 전부 **한국어**로 작성 (`createJiraIssue`,
    `addCommentToJiraIssue` 등으로 생성/갱신하는 모든 텍스트 포함)

커밋 메시지 자체의 언어(영어/한국어)는 이 규칙과 별개이며 기존 관례를 따릅니다.

**구현 참고 (에이전트용): MR 본문은 push 옵션으로 쓰지 않는다.**

`git push -o merge_request.description="..."` 는 실제 개행문자를 담을 수 없다(git이 거부함).
그래서 개행을 번호(`1)`, `2)`)나 가운뎃점(`·`)으로 눌러 한 줄에 우겨넣게 되는데, 그러면
5번 항목의 MR 템플릿 섹션 구성을 지킬 수 없다. **2026-09-08 MR !80~!82 가 이 방식으로
한 줄짜리 본문이 되어 리뷰하기 어려웠다.**

절차는 이렇게 한다.

1. push 할 때는 **제목만** 옵션으로 준다.
   ```bash
   git push -u origin HEAD \
     -o merge_request.create \
     -o merge_request.target=develop \
     -o merge_request.title="chore: 제목 (S15P21A506-000)"
   ```
2. 본문은 GitLab 웹의 MR 편집 화면에서 채운다. 편집기를 **플레인텍스트 모드로 전환**한 뒤
   템플릿 원문을 넣는다 — 리치텍스트 모드에 마크다운을 붙여넣으면 깨진다.
   (전환 버튼은 편집기 왼쪽 아래 "Switch to plain text editing")
3. 한글 본문에 `\uXXXX` 손이스케이프를 쓰지 않는다. 조용히 오타가 난다.
4. 저장된 git 자격증명을 추출해 API를 직접 호출하는 것은 지양한다.

## 3. 작업 전 Jira 연동 워크플로우 (AI 에이전트 필수 준수)

코드/문서 작업을 시작하기 전, 반드시 아래 절차를 따릅니다.

1. **기존 이슈 검색**: `searchJiraIssuesUsingJql`로 작업 내용과 관련된 이슈가 이미 있는지 확인합니다.
   ```
   project = S15P21A506 AND text ~ "<키워드>" ORDER BY created DESC
   ```
2. **있으면 연결**: 찾은 이슈 키를 작업 기준으로 삼습니다. 착수 시 `addCommentToJiraIssue`로
   진행 사실을 남기고, 필요하면 `transitionJiraIssue`로 상태를 "진행 중"으로 바꿉니다.
3. **없으면 생성 후 연결**:
   - 현재 진행 가능한 에픽 확인 (완료되지 않은 에픽만):
     ```
     project = S15P21A506 AND issuetype = 10000 AND statusCategory != Done ORDER BY created ASC
     ```
     작업 내용과 가장 맞는 에픽을 고릅니다. 애매하면 추측하지 말고 사용자에게 물어봅니다.
   - 현재 활성 스프린트 확인:
     ```
     project = S15P21A506 AND sprint in openSprints()
     ```
     반환된 이슈 중 아무거나 `customfield_10020` 필드를 읽어 활성 스프린트 id를 확인합니다
     (스프린트는 주 단위로 바뀌므로 매번 새로 조회 — 하드코딩 금지).
   - `createJiraIssue`로 이슈를 생성하며 `parent`에 위에서 고른 에픽 키를,
     `additional_fields`에 `{"customfield_10020": <sprintId>}`를 지정합니다.
4. **작업 종료 후**: 완료되면 `transitionJiraIssue`로 상태를 "완료"로 전이하고,
   필요하면 `addCommentToJiraIssue`로 결과를 요약합니다.

## 4. Git 브랜치·커밋 컨벤션 (확정)

정본은 노션 문서 **"repo 구조 & 브랜치 규칙"**·**"커밋 컨벤션"** 이고, 이 절은 그 규칙을
저장소에서 바로 참조할 수 있게 옮겨 둔 것입니다. 둘이 어긋나면 노션을 따르고 이 절을 고칩니다.

### 4.1 병합 흐름

```
기능 브랜치 → develop → main
```

`develop`·`main` 에 직접 push 하지 않습니다. MR을 만들어 리뷰를 거칩니다.

### 4.2 브랜치 이름

```
<part>/<type>/<issue_no>-작업내용
```

예) `data/feat/S15P21A506-290-downloads-bronze-ingest`

| 자리 | 값 |
| --- | --- |
| `part` | `frontend` `api` `data` `ai` `worker` `infra` `docs` `plan` |
| `type` | `feat` `fix` `refactor` `test` `chore` `docs` `style` `config` |
| `issue_no` | Jira 이슈 키 — `S15P21A506-290`. 숫자만(`290-...`) 쓰지 않습니다 |
| `작업내용` | 영문 kebab-case. 브랜치명의 한글·공백·대문자는 도구 호환 문제가 있습니다 |

**`part` 는 폴더명이 아니라 담당 파트입니다.** 노션 폴더 구조 안(`api/`·`worker/`·`infra/`)과
현재 저장소 배치(`backend/`·`pipeline/`·`deploy/`)가 아직 다르므로 아래 대응을 씁니다.

| `part` | 실제 폴더 |
| --- | --- |
| `frontend` | `frontend/` |
| `api` | `backend/` |
| `data` | `pipeline/`, `datasets/` |
| `ai` | (미착수) |
| `worker` | (미착수) |
| `infra` | `deploy/`, `compose.yaml`, `.githooks/`, `scripts/` |
| `plan` | `docs/` 중 기획·요구사항·구상안 |
| `docs` | `docs/` 중 그 외, 루트 문서·README |

손으로 만들지 말고 헬퍼를 쓰면 규칙을 외우지 않아도 됩니다.

```bash
sh scripts/new-branch.sh data feat 290 downloads-bronze-ingest
# → origin/develop 에서 data/feat/S15P21A506-290-downloads-bronze-ingest 생성
```

`.githooks/pre-push` 가 **새 브랜치를 처음 push 할 때** 이름을 검사합니다. 이미 원격에 있는
브랜치의 추가 push 는 검사하지 않으므로, 규칙 도입 전에 만든 브랜치의 작업은 막히지 않습니다.

### 4.3 커밋 메시지

```
type: subject

body

footer
```

- **type** — 브랜치의 `type` 과 같은 목록. 콜론 **뒤에만** 공백을 둡니다 (`feat: …`, `feat : …` 아님).
- **subject** — 50자 이내, 끝에 마침표를 붙이지 않습니다. 영문이면 동사원형으로 시작하고
  과거시제를 쓰지 않습니다 (`Fixed` 아니라 `Fix`).
- **body** — 어떻게가 아니라 **무엇을·왜** 바꿨는지 씁니다. 분량 제한 없음.
- **footer** — 선택. `Fixes:` `Resolves:` `Ref:` `Related to:`

**Jira 이슈 키는 제목 맨 끝 괄호에 붙입니다.**

```
feat: deps.dev BigQuery 수집기 추가 (S15P21A506-122)
```

노션 커밋 컨벤션의 footer 예시(`Resolves: #45`)는 GitHub 이슈 번호 기준이라 이 저장소에는
맞지 않습니다. 제목 끝 괄호를 쓰는 이유는 ①GitLab↔Jira 연동이 제목의 키를 읽어 커밋을
이슈에 자동 연결하고(`S15P21A506-47`), ②`.githooks/commit-msg` 가 브랜치명에서 키를 읽어
**자동으로 삽입**해 주므로 손으로 적을 일이 거의 없기 때문입니다.

### 4.4 훅 설치 (클론 후 1회)

훅은 저장소에 들어 있지만 git 이 자동으로 켜 주지 않습니다. 각자 1회 실행해야 합니다.

```bash
sh scripts/setup-hooks.sh      # macOS / Linux / Git Bash
scripts\setup-hooks.bat        # Windows CMD / PowerShell
```

검사 내용과 우회 방법은 [`README.md`](README.md) 의 "브랜치·커밋 규칙" 절에 있습니다.

## 5. MR 템플릿 (확정)

모든 Merge Request는 저장소의 기본 템플릿을 사용합니다.

- 위치: [`.gitlab/merge_request_templates/default.md`](.gitlab/merge_request_templates/default.md)
- GitLab에서 MR을 생성하면 Description 템플릿 드롭다운에서 `default`를 고를 수 있고,
  프로젝트 설정에서 기본 템플릿으로 지정되어 있으면 자동으로 채워집니다.
- 본문 작성 언어는 2번 항목(한국어)을 따릅니다.
- 채우는 방법
  - **관련 이슈**: Jira 이슈 키(예: `S15P21A506-42`)를 적고, MR 제목에도 넣어 Jira와 연결합니다.
  - **변경 영역**: 6인 다직군(PM·AI·BE·Fullstack) 구성이라 리뷰어가 자기 영역을 빨리 찾도록 반드시 체크합니다.
  - **데이터·파이프라인 영향**: 스키마 변경·backfill·외부 교통 API 호출량·배치 주기 변화는
    머지 후 되돌리는 비용이 크므로 해당하면 반드시 기재하고, 없으면 "없음"이라고 적습니다.
  - **체크리스트**: API 키 등 시크릿이 커밋에 포함되지 않았는지 확인하고, 리뷰어·라벨을 지정합니다.
- 에이전트가 MR을 만들 때도 이 템플릿의 섹션 구성을 그대로 따릅니다. 본문을 넣는 방법은
  2번 항목의 구현 참고를 볼 것 — push 옵션이 아니라 웹 편집입니다.

## 6. Jira 이슈 템플릿 (확정)

Jira 이슈를 만들 때는 저장소의 템플릿을 기준으로 설명(Description)을 작성합니다.

- 위치: [`docs/templates/jira/`](docs/templates/jira/) — `스토리.md`, `작업.md`, `버그.md`
- **자동 삽입은 되지 않습니다.** 이 프로젝트는 company-managed(classic) 프로젝트라 이슈 생성
  화면에서 설명을 미리 채워 주는 Jira 기본 기능이 없습니다(team-managed 프로젝트 전용 기능).
  따라서 이슈를 만들 때 해당 템플릿 본문을 **복사해 붙여넣고** 채웁니다.
  Jira Cloud 편집기는 마크다운 붙여넣기를 인식해 제목·체크박스로 변환합니다.
- 에이전트가 `createJiraIssue`로 이슈를 생성할 때도 이 템플릿의 섹션 구성을 따라
  설명을 작성합니다(언어는 2번 항목에 따라 한국어).
- 템플릿을 고르는 기준
  | 이슈 유형 | 템플릿 | 쓰는 경우 |
  | --- | --- | --- |
  | 스토리 | `스토리.md` | 사용자에게 보이는 기능 단위 |
  | 작업 | `작업.md` | 기술 작업·인프라·문서 등 기능 외 작업 |
  | 버그 | `버그.md` | 결함 |
- (선택) 프로젝트 관리자 권한이 있으면 Jira 자동화 규칙
  "이슈 생성됨 → 설명이 비어 있으면 → 이슈 편집으로 템플릿 삽입"으로 생성 **직후** 자동 삽입이
  가능합니다. 생성 화면에서 미리 보이지는 않습니다.

### 6.1 Jira 분류 규칙 (2026-09-11 후속 결정, S15P21A506-327)

- **에픽 제목**은 `[MVP]`, `[확장]`, `[인프라]`, `[기획]`, `[운영]`으로 범위를 표시합니다.
  모호한 `[기능]`은 새 에픽에 사용하지 않습니다.
- **에픽 아래 업무 제목**은 `[영역] [행동] 구체적 대상` 형식입니다.
  예: `[FE] [보완] 후보 3개 노출`, `[BE] [구현] 기능 비교 API`, `[AI] [설계] RAG 인수 계약`,
  `[공통] [검증] 기능 비교·PDF 결과 일치`. 영역은 FE·BE·AI·데이터·공통·기획·운영 등을 씁니다.
  행동은 설계·구현·연동·보완·수정·검증·수집·전처리·검토·평가·제작·정비 등 실제 산출물로 결정합니다.
- `[검증]`은 시험·검수·인수입니다. 검증기/validator 코드를 만드는 작업은 `[구현]`입니다.
  `[공통]`은 여러 파트의 계약·통합 산출물에만 쓰며 담당자 미정을 뜻하지 않습니다.
  버그 유형은 그대로 `버그`로 두고 제목은 `[FE] [수정] …`처럼 씁니다.
- 에픽은 담당 파트가 아니라 **제품 기능 또는 공통 기반의 결과 단위**입니다.
  같은 기능의 FE·BE·AI 업무는 같은 에픽에 연결하고 파트 라벨로 구분합니다.
- 파트는 Jira 라벨 `프런트엔드`, `백엔드`, `데이터`, `AI`, `인프라`, `기획`, `문서`, `검수`,
  `운영`으로 기록합니다. 실제 공동 산출물만 복수 파트를 표시하고, 담당자 이름으로 파트를 추정하지 않습니다.
  이 라벨은 개인 담당자 필드·이슈 유형·기능/확장 범위를 대신하지 않습니다.
- 범위는 에픽과 업무 본문으로 판단합니다. 공통 에픽의 확장 전용 검수처럼 예외가 있으면
  제목의 대상에도 `확장 도메인`을 명시합니다. 행동 접두사 변경으로 MVP에 승격하지 않습니다.
- 기존 진행 중·완료 이슈는 분류 정리에서도 수정하지 않습니다. 따라서 이전 접두사나
  이전 에픽이 남을 수 있습니다. 상태를 강제로 바꾸거나 삭제·재생성하여 맞추지 않습니다.
- 이번 후속 정리에서는 AI 임베딩·후보 색인·유사도 실험·재학습 및 인프라 영역도
  **제목·설명·라벨을 포함해 변경하지 않습니다.** 기능 비교 RAG 미착수 업무는 적용 대상입니다.
  제외 대상에 이전 `[기능]`/`[인프라]` 접두사가 남는 것은 의도된 예외입니다.
- 이전 FE/AI 에픽 `S15P21A506-115`·`S15P21A506-117`은 `이력보존` 라벨로 구분하며
  신규 업무의 기본 에픽으로 사용하지 않습니다. 남아 있는 진행 중 업무는 그대로 추적합니다.
- 분류 변경은 이슈 키·기존 브랜치명·커밋·MR을 바꾸는 이유가 아닙니다.
  브랜치 `part`와 `type`은 4번 규칙을 그대로 사용합니다(백엔드=`api`, 프런트엔드=`frontend`).
- 에픽별 배치, 예외와 조회 방법은 [`docs/jira/분류_운영규칙.md`](docs/jira/분류_운영규칙.md)를 따릅니다.

## 7. 알려진 환경 차이 (AI 에이전트 필수 확인)

로컬과 운영이 **의도적으로 다른** 지점이다. 여기서 비롯되는 증상을 디버깅할 때는
코드보다 이 표를 먼저 볼 것. "로컬에서는 되는데 서버에서 안 된다" 의 후보 목록이다.

| 무엇 | 로컬 | 운영 | 왜 다른가 |
| --- | --- | --- | --- |
| MinIO 데이터 위치 | named volume (`pickage-local_minio-data`) | **`/srv/minio/data` 바인드** | 운영은 손으로 띄운 컨테이너에서 이관했다. 그 디렉터리에 **수집 원본이 들어 있다** |
| nginx | 없음 (프런트는 `npm run dev`) | **컨테이너 + TLS 종단** | 로컬에서는 프록시를 거치지 않는다 → `X-Forwarded-Proto` 관련 문제는 **로컬에서 재현되지 않는다** |
| **Spark 구성** | 컨테이너 **하나** (local mode, `exec` 해서 쓴다) | **master + worker 둘, `network_mode: host`** | 로컬은 분산이 아니다. **크로스 호스트 네트워킹은 로컬에서 재현되지 않는다** — worker 가 컨테이너 IP(172.19.x.x)를 광고해 상대 호스트가 못 찾는 문제는 서버에서만 드러난다 |
| Spark s3a endpoint | `http://minio:9000` (서비스 이름) | `http://172.26.8.249:9000` (사설 IP) | 다른 호스트의 executor 는 compose 네트워크 이름을 못 푼다 |
| Swap | PC 에 있음 (컨테이너도 씀) | **호스트 2 GiB, 컨테이너 0** | 호스트에만 완충을 뒀다. 모든 서비스에 `memswap_limit` = `mem_limit` 이라 **컨테이너는 상한을 넘기면 즉시 OOM Kill** — 이유는 deploy/prod/README.md 의 "Swap" |
| 프런트 서빙 | Vite dev server | **정적 파일 + nginx** | SPA 딥링크(`/analyze` 새로고침)는 **`try_files` 가 있어야 200 이다.** dev server 는 알아서 처리해서 로컬에서 안 드러난다 |

**MinIO 는 로컬과 운영이 같은 릴리스다** (`minio/minio:RELEASE.2025-04-22T22-12-26Z`).
바꿀 때는 루트 `compose.yaml` 과 `deploy/prod/data/compose.yaml` 을 같이 바꾼다.

## 8. 향후 추가 예정 (팀 합의 필요)

- MR 리뷰 규칙 (리뷰어 지정 인원, 승인 수 등 — 템플릿 자체는 5번 항목에서 확정)
- 스펙 주도 개발(Spec-Driven Development) 여부
- 시크릿/보안 관리 규칙
