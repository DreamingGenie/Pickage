# Pickage GitHub 커뮤니티 현황 구현 계획

최초 작성: 2026-09-08
현행 기준 업그레이드: 2026-09-11
연결 결정: `DEC-COMMUNITY-20260909-01`
문서 최신화 이슈: `S15P21A506-284`
검토 기준: `origin/develop@6f4fe68`, 원문 보존 커밋 `1b60139`

이 문서는 GitHub 커뮤니티 확장 기능을 실제로 구현할 때 사용하는 실행 기준이다. 제품 계약,
현재 구현 사실, 목표 구현, 허용한 v1 한계를 구분한다. 코드가 이 문서와 달라지면 구현자가
임의로 둘 중 하나를 고르지 않고 Jira와 MR에서 계약을 먼저 갱신한다.

## 1. 결론

사용자가 비교 대상을 확정하면 Spring Boot는 **사용자가 최초 입력한 기준 패키지 하나**의
커뮤니티 refresh를 비차단으로 요청한다. 다른 후보나 비교 패키지로 자동 대체하지 않는다.
커뮤니티 탭은 기존 `/report/:reportId` 보고서 shell의 세 번째 확장 탭이며 별도 최상위 route나
중복 header를 만들지 않는다.

refresh는 저장소 검증 → Issue 검색 → 댓글 수집 → GMS 요약 → 검증 → 게시 순서로 수행한다.
진행 상태는 메모리에 잠시 보관하고, 화면에 제공 가능한 완성 결과만 PostgreSQL의
`community_snapshot` 한 행 JSONB로 게시한다. raw Issue 본문과 댓글은 게시 전에 폐기한다.

기본 정책은 최근 180일 Issue를 댓글 수 중심으로 정렬해 최대 2건 선택하고, 결과가 없을 때만
365일로 한 번 확장한다. Issue마다 최신 댓글을 최대 100개 수집하고 대표 메시지는 최대 3개만
제공한다. 완료 결과는 24시간 재사용하며, 갱신 실패 시 수집 후 7일 미만인 결과를 stale로 제공한다.

현재 저장소에는 community migration, backend endpoint, frontend tab, 외부 연동 설정이 없다.
따라서 이 문서의 설계 절은 **목표 계약**이지 구현 완료 현황이 아니다.

## 2. 기준과 불변 계약

충돌 시 사용자 확정 지시와 `DEC-COMMUNITY-20260909-01` → docs root 0910 기획 세트 → 현재
코드·migration·배포 파일 → GitHub 공식 문서 → 과거 제안 순으로 판단한다.

- community 대상은 기준 패키지 하나다.
- 미검증·모호·미지원 저장소이면 다른 패키지로 fallback하지 않는다.
- 상단 수치·Issue 카드·대표 메시지는 같은 snapshot과 Issue 집합을 사용한다.
- 모델이 역할·수치·시각·원문에 없는 합의를 만들지 않는다.
- 저장소 주소는 읽기 전용 식별 정보다.
- Issue 장기 시계열은 ecosystem Activity 확장 소유다.
- Spring → GMS 호출은 이 refresh의 bounded 예외에만 허용한다.

## 3. 2026-09-11 구현 기준선

| 영역 | 현재 사실 | 근거 |
|---|---|---|
| DB | V1~V4가 각각 하나이며 V4에 `similar_package` 존재 | `backend/src/main/resources/db/migration/` |
| backend | Java 21, Spring Boot 4.0.8, MVC, JdbcTemplate 명시 SQL | `backend/build.gradle`, `PackageQueryRepository.java` |
| API | `/api` 아래 package 조회 6개, `success/data`, 전역 snake_case | `PackageController.java`, `application.yaml` |
| frontend | React 19, Router 7, Query 5, ecosystem/features 두 lazy tab | `frontend/package.json`, `report-page.tsx` |
| route | `/report/:reportId`, 이동 시 `state.packages`만 전달 | `routes.ts`, `analyze-page.tsx` |
| runtime | local/prod API 메모리 1.6 GiB, 운영 Swap 0 | local/prod compose, `AGENTS.md` |
| seed | 데이터 시드 3개와 비우기 스크립트 2개 | `deploy/local/seed/` |

MR !90·!91의 작업은 이미 develop에 병합됐다. 현재 마지막 migration은 V4이므로 community는
V5 후보지만 실제 구현 브랜치 생성 직후 빈 번호를 다시 확인한다. 적용된 V1~V4는 수정하지 않는다.

아직 없는 것은 `community_snapshot`, community backend/frontend 코드, npm/GitHub/GMS client,
refresh registry·executor·scheduler, Swagger/fixture, community 환경설정이다. Jira
`S15P21A506-137`의 완료 상태만으로 구현됐다고 판단하지 않는다. `212`, `213`은 해야 할 일 상태다.

### 선행 차이

| 차이 | 처리 |
|---|---|
| 후보 화면 최대 2개 | community 변경에 섞지 않고 기존 후속 결함으로 추적 |
| `analyze-page.tsx` 미정의 `setError` | frontend 검증 선행 결함으로 별도 처리 |
| route state에 `basePackage` 없음 | community 연동에서 명시적 필드 추가 |
| 직접 진입이 기본 fixture 사용 | community 실호출 금지 문맥 guard 추가 |
| POST query·호출자 signal 미지원 | 기존 호출 호환 request option으로 확장 |
| GitLab CI 없음 | MR에 로컬 명령과 결과 기록 |

과거 일정표의 2026-09-20은 보관 일정이다. Jira에서 다시 확정하기 전 새 완료일을 만들지 않는다.

## 4. 종단 흐름

```text
분석 확정 → POST refresh(ANALYSIS_CONFIRMED, 비차단) → report shell 이동
→ community tab open → POST refresh(TAB_OPENED, 작업 보장) → GET polling
→ 저장소 검증 → Issue 검색·댓글 수집 → GMS 요약·검증
→ community_snapshot 원자 upsert → 같은 tab에서 진행 화면을 결과로 교체
```

분석 확정 POST 실패는 ecosystem 이동을 막지 않고 tab open POST가 안전망이 된다. GET은 조회만
하며 외부 수집을 시작하지 않는다. hover prefetch는 code chunk만 가져온다.

## 5. 저장소와 Issue

### 5.1 후보 검증

DB `package.repo_url`과 npm latest packument의 `repository`를 독립 정규화한다. npm 값이 객체면
`url`과 선택적 `directory`를 읽는다. 최종 후보의 scheme·host·owner·repo를 다시 검사한다.

허용 대상은 공개 GitHub repository로 정규화 가능한 주소다. `git+https`, `.git`, fragment는
정규화하되 사용자 정보, 임의 port, IP literal, `..`, absolute directory, decoding 후 경로 탈출은
거부한다. API path는 검증된 owner/repo와 안전한 directory segment로만 조립한다.

| 상황 | 판정 |
|---|---|
| DB·npm 같은 GitHub 저장소 | 진행 |
| 서로 다르고 npm이 GitHub | npm 우선, 충돌 limitation·로그 |
| DB만 GitHub 또는 npm repository 없음 | root package.json 이름 일치 시 진행 |
| npm만 GitHub | npm 후보로 진행 |
| 최종 후보가 GitHub 외 host | `UNSUPPORTED_HOST`, 중단 |
| npm 404 | identity 재확인 후 `UNVERIFIED_REPOSITORY` |
| network·rate limit | 일시 refresh 실패로 분리 |
| GitHub 404/접근 불가 | rate limit과 구분 후 `UNVERIFIED_REPOSITORY` |

| 증거 | 연결 | Issue scope |
|---|---|---|
| npm directory package.json 이름 일치 | 확인 | `REPOSITORY_WIDE` |
| directory 없음, root 이름 일치 | 확인 | `PACKAGE_SCOPED` |
| directory 없음, root 이름 불일치 | repository만 확인 | `REPOSITORY_WIDE` + limitation |
| directory 없음/이름 불일치 | 모호 | `AMBIGUOUS`, 중단 |

directory 일치는 repository 전체 Issue가 package 전용이라는 증거가 아니다. v1은 label·본문으로
package별 Issue를 필터링하지 않는다. archived는 `REPOSITORY_ARCHIVED` limitation으로 표시하고,
provenance·gitHead·tag/commit은 보조 증거로만 쓴다.

### 5.2 `github-active-v1`

- `repo:owner/repo is:issue updated:>=<180일>`; 결과 0건일 때만 365일로 한 번 확장
- Search comments desc 상위 30개; 서버 tie-break는 updated_at, issue_number desc
- 최대 Issue 2개, open/closed 허용, PR 제외
- locked·Bot 작성 Issue 제외
- `incomplete_results=true`면 `PARTIAL` + `SEARCH_INCOMPLETE`
- 정책 변경 시 payload version과 backend/frontend fixture를 함께 변경

댓글은 issue별 endpoint에서 `per_page=100`과 Link header를 사용해 **최신 100개**를 확정하고
`created_at`, source ID 순으로 복원한다. pagination 도중 증감·page 실패가 있으면 `TRUNCATED` 또는
`FAILED`다. Bot comment는 전체 댓글 수에 포함하지만 대표 후보에서 제외한다. 반응 수는 선택 Issue
record의 reaction 합이며 comment reaction과 중복 합산하지 않는다.

## 6. GMS 요약·검증

입력은 Issue 원제목을 항상 포함하고 원문당 4,000자, Issue당 48,000자로 제한한다. 본문 우선,
남은 예산은 최신 댓글부터 선택한 뒤 모델에는 시각 순으로 전달한다. 절단은
`SUMMARY_INPUT_LIMITED`로 표시한다. Issue당 출력 상한은 2,048 token이다.

GMS endpoint/path/auth header는 팀의 실제 계약을 구현 이슈에서 확인한 뒤 고정한다.
`GMS_BASE_URL`에 임의 path를 추측하지 않는다. 출력은 issue_number, title_ko, summary_ko,
support source IDs, flow 1~4개, 대표 message 0~3개의 JSON만 허용한다. 제목 200자, Issue 요약
500자, flow 각 200자, message 각 300자 상한을 둔다.

서버는 schema·길이·enum·Issue/source 소속·support 실재를 검증한다. 다른 Issue source 혼입,
여러 원문을 한 발화로 합치기, 본문을 사용자 해결안으로 분류하기, HTML·외부 URL·Markdown link는
해당 Issue 요약 전체를 거부한다. 작성자·association·시각·상태·수치는 서버가 원본에서 붙인다.

역할은 Issue 작성자면 `ISSUE_AUTHOR`가 우선이다. 나머지는 OWNER → `REPOSITORY_OWNER`, MEMBER →
`ORGANIZATION_MEMBER`, COLLABORATOR → `COLLABORATOR`, CONTRIBUTOR → `CONTRIBUTOR`로 의미를
보존하고 그 외는 null이다. `USER_SOLUTION`은 역할이 아니라 message kind다.

raw source는 refresh 메모리에서만 사용하며 DB/API/log에 본문·댓글·prompt 전체를 남기지 않는다.

## 7. 데이터베이스

### 7.1 migration gate

현재 후보는 `V5__community.sql`이다. 구현 직전 최신 develop, version 중복·V5 선점, 빈 DB 전체
migration, V1~V4 upgrade, `ddl-auto=validate`를 확인한다. 선점 시 다음 빈 번호를 쓴다. 기존
migration을 rename/edit하거나 Flyway repair로 우회하지 않는다.

### 7.2 `community_snapshot`

| column | type | constraint | 의미 |
|---|---|---|---|
| `package_id` | INT | PK, FK→package, ON DELETE CASCADE | package당 최신 한 건 |
| `snapshot_id` | UUID | NOT NULL, UNIQUE | 응답 버전 |
| `payload_version` | SMALLINT | NOT NULL, CHECK > 0 | JSON 호환성 |
| `collected_at` | TIMESTAMPTZ | NOT NULL | TTL 기준 |
| `data_status` | VARCHAR(30) | NOT NULL, enum CHECK | 게시 자료 상태 |
| `result` | JSONB | NOT NULL, object CHECK | repository·topics·limitations |

`data_status`는 `AVAILABLE`, `PARTIAL`, `UNVERIFIED_REPOSITORY`, `AMBIGUOUS_SCOPE`,
`UNSUPPORTED_HOST`, `NO_DISCUSSION_DATA`다. network/rate/GMS timeout은 저장하지 않고 refresh 상태에
둔다. result는 typed payload record로 직렬화하며 repository, topics, messages, limitations를 담는다.
messages에는 내부 source ID·author association·시각·kind·요약을 저장하되 source ID는 wire에서 뺀다.

fresh/serve 시각, 상단 합계, 표시 역할·순서는 저장하지 않고 조회 시 계산한다. raw 원문·hash·외부
응답 원형·prompt도 저장하지 않는다.

### 7.3 게시·TTL

외부 작업은 transaction 밖에서 끝낸다. 게시만 `SET LOCAL lock_timeout='2s'` →
`statement_timeout='5s'` → package advisory transaction lock → `INSERT ... ON CONFLICT` 순으로
수행한다. 실패 시 rollback되어 이전 행이 남는다.

- FRESH: `now < collected_at + 24h`
- STALE: `collected_at + 24h <= now < collected_at + 7d`
- EXPIRED: `now >= collected_at + 7d`, 반환 금지

매시간 7일 초과 행을 최대 500개 정리하되 조회가 TTL을 먼저 검사한다.

### 7.4 seed

package를 TRUNCATE하는 `seed_sample`, `seed_mock_parity`, `seed_service_full`, `seed_reset` **4개**에
`community_snapshot`을 같은 목록으로 추가한다. `seed_clear_snapshots`는 package를 유지하므로
community를 지우지 않는다. community 상태는 DB 가짜 행이 아니라 backend source fixture와 frontend
public fixture로 시험한다. local README도 함께 갱신하고 실제 Curated DB에는 seed를 실행하지 않는다.

## 8. API

- `POST /api/packages/community/refresh?name=<base>&trigger=ANALYSIS_CONFIRMED`
- `POST /api/packages/community/refresh?name=<base>&trigger=TAB_OPENED`
- `GET /api/packages/community?name=<base>`

`CommunityController`를 별도로 두고 이름 형식은 `PackageNames.isValidName`을 재사용한다. POST 새
task는 202, fresh hit·single-flight 참여·capacity 응답은 200이며
`ResponseEntity<ApiResponseBody<CommunityResponse>>`로 표현한다. GET은 200 조회만 수행한다.
protocol error는 기존 envelope를 따르고 package 없음은 실제 `C006`에 연결한다.

| namespace | 값 |
|---|---|
| `view_status` | `PROCESSING`, `RESULT`, `FAILED` |
| `freshness` | 결과가 있을 때 `FRESH`, `STALE`; 없으면 null |
| `refresh.status` | `NOT_STARTED`, `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CAPACITY_LIMITED` |
| `data_status` | DB persistent 6개 상태 |
| topic collection | `COMPLETE`, `TRUNCATED`, `FAILED` |
| topic summary | `READY`, `FAILED`, `SKIPPED` |

refresh error는 `GITHUB_RATE_LIMITED`, `GITHUB_UNAVAILABLE`, `NPM_UNAVAILABLE`, `GMS_UNAVAILABLE`,
`REFRESH_DEADLINE_EXCEEDED`, `PUBLISH_FAILED`, `CAPACITY_LIMITED`, `LOCAL_RATE_LIMITED`로 제한한다.
`FETCH_LIMITED`를 persistent data_status로 쓰지 않는다. 제한 전면 실패는 refresh error, 일부 게시
가능 결과는 `PARTIAL` + limitation이다.

진행·최초 실패는 `result=null`이다. stale 갱신은 이전 result와 refresh를 함께 제공한다. 배열은
빈 경우 `[]`, 시각은 UTC ISO 8601 `Z`, wire는 전역 snake_case다. topics는 comments·updated_at·
number 내림차순, messages는 created_at·내부 source ID 오름차순이다. package_id·raw source·내부
source ID·외부 응답 원형은 공개하지 않는다.

## 9. backend 구조·동시성

`com.ssafy.pickage.domain.community` 아래 controller/service/coordinator/registry,
`CommunitySnapshotRepository`, properties, npm/GitHub/GMS clients, repository/Issue policy,
summary validator, payload/API DTO를 분리한다.

JPA Entity를 만들지 않는다. 기존 관례대로 JdbcTemplate·record·명시 SQL을 사용하고 JSONB는 Jackson
typed payload로 직렬화한다. 외부 HTTP는 MVC stack의 `RestClient`를 사용하며 client 하나 때문에
WebFlux를 추가하지 않는다. GitHub 요청은 Accept, 최소 권한 token, 고정 User-Agent,
`X-GitHub-Api-Version: 2026-03-10`을 넣는다.

| 항목 | v1 기본값 |
|---|---|
| refresh start | 10건/분, burst 4 |
| 동시 refresh | 2 |
| TAB_OPENED queue | 4 |
| ANALYSIS_CONFIRMED | permit 없으면 무대기 |
| task deadline | 20초 |
| 완료 상태 보존 | 10분 |
| 실패 cooldown | 5분, GitHub reset/retry-after 우선 |
| poll 안내 | 2초 |
| shutdown grace | 5초 |

registry·permit·queue는 한 임계구역에서 관리한다. refresh worker pool과 GMS 병렬 pool을 분리해 같은
pool의 자식 future를 기다리는 교착을 막고 둘 다 bounded로 둔다. 단일 deadline의 남은 시간을 모든
외부 호출에 전파하고 소진되면 다음 단계를 시작하지 않는다.

운영은 현재 API 한 인스턴스이므로 in-memory single-flight를 v1에 허용한다. 인스턴스를 늘리기
전에는 DB lease/분산 coordinator가 필요하다. advisory lock은 게시만 보호한다.

## 10. frontend

보고서 이동 state를 `{ basePackage: string; packages: string[] }`로 명시한다. basePackage는 최초 입력한
검증 이름이고 packages[0]과 같아야 한다. 과거 state의 packages[0] fallback은 임시 호환에만 쓰며
정렬된 query key나 mock fixture에서 역추론하지 않는다. 유효 state가 없으면 community를 비활성화하고
입력으로 안내한다.

API client request option은 params/body/caller signal을 지원하고 POST query도 buildUrl을 사용한다.
caller signal과 기존 15초 timeout을 결합하며 tab hide 취소를 timeout으로 오인하지 않는다. query
key는 `['packages','community',basePackage]`, GET transport만 최대 2회 회복한다. QUEUED/RUNNING이고
tab이 보일 때만 서버 poll interval로 refetch한다.

분석 확정 POST는 unhandled rejection 없이 비차단 실행한다. tab open POST 후 GET을 조회하고 capacity
제한은 retry_at 이후 사용자 행동으로 한 번만 admission 재시도한다.

`frontend/src/routes/report/community/`에 api/model/adapter, report-tab, progress/result, header/summary,
issue-card/thread/data-limits/sample을 둔다. 세 번째 lazy tab을 추가하되 기존 `AnalysisProgress`의
`STEP_MS`·가짜 퍼센트를 재사용하지 않는다. 서버 stage_message·경과 시간·실제 단계와
`aria-live="polite"`를 사용한다. stale 결과는 유지하며 작은 진행 카드를 함께 표시한다.

Figma `485:936`에서는 `02-package-intro`~`05-discussion-threads`만 참고하고 공통 shell을 복제하지
않는다. 예시 `2·40·17·2`는 layout fixture이지 운영 기대값이 아니다.

## 11. 설정·보안·관측

`GITHUB_COMMUNITY_TOKEN`, `GMS_API_KEY`, `GMS_BASE_URL`, `GMS_MODEL`을 root `.env.example`, local
compose api, prod app `.env.example`, prod compose api, Spring `CommunityProperties`에 연결한다. 실제
값은 추적 파일이나 frontend에 두지 않는다.

운영 key 누락 시 core API가 아닌 community 시작만 비활성화하고 명확한 상태를 반환한다. 배포 smoke는
운영 key 연결을 별도 실패 gate로 확인한다. GitHub 원문은 비신뢰 입력으로 취급해 raw HTML을 렌더링하지
않고 모델 URL을 따라가지 않는다. secret/header/raw prompt/source 전체를 log에 남기지 않는다.

refresh id, package id, stage/duration, cache/freshness, 정제 failure, retry_at, GitHub remaining/reset,
model/prompt version, source count·입력 길이를 구조화 로그로 남긴다. 1.6 GiB·Swap 0에서 peak heap,
thread 수와 graceful shutdown을 확인한다.

## 12. 구현 순서와 merge gate

1. 팀 규칙대로 Jira를 검색·연결하고 최신 develop/migration/typecheck 기준을 기록한다.
2. GMS 실제 endpoint/path/auth/schema와 상태 enum·JSON schema를 승인한다.
3. migration, 4개 reset 목록, local README를 구현한다.
4. typed payload·JDBC repository·serialization/integration test를 만든다.
5. repository/npm/GitHub policy와 GMS validator를 pure unit test로 만든다.
6. registry/admission/deadline/executor를 fake client로 검증한다.
7. GET/POST controller·Swagger를 연결한다.
8. route basePackage, API client, query/adapter/fixture, progress/result tab을 순서대로 연결한다.
9. local/prod secret wiring, redaction, shutdown, Swagger·Jira·docs 정합을 검수한다.

GMS 계약 미확인, migration 충돌, raw source/secret 노출, package fallback, 상태/schema 불일치,
unbounded queue, 비원자 게시, 새 typecheck 실패가 있으면 merge하지 않는다.

## 13. 테스트

DB는 빈 DB 전체 migration, V1~V4 upgrade, validate, FK/UUID/status/JSON/index, 동시 upsert·rollback,
4개 초기화 SQL 반복 실행을 검사한다. integration DB는 `pickage_community_test_<uuid>`로 격리한다.

backend는 URL/host/directory 검증, DB/npm 충돌, monorepo/archived, 180→365, PR/Bot/locked,
incomplete search, 최신 댓글 pagination, reaction/association/큰 ID, GMS schema/source/왜곡, TTL 경계,
single-flight·50 package burst·pool 포화 무교착·deadline/shutdown을 시험한다.

API/frontend는 wrapper/snake_case/C006/비노출, POST 202/200, GET 무부작용, 모든 상태 fixture,
basePackage/direct-entry, polling abort·재개, GET만 재시도, timer 없는 progress·접근성, mock 외부 호출
0건을 검사한다. Figma fixture와 운영 policy 시험은 분리한다.

```bash
cd backend
./gradlew test
./gradlew integrationTest
./gradlew build

cd ../frontend
npm run typecheck
npm run lint
npm run format:check
npm run build
```

CI가 없으므로 환경·명령·결과와 기존 결함을 MR에 기록한다. 실제 secret smoke는 기본 test에서 분리한
수동 실행으로만 수행한다.

## 14. 요구사항 추적

| 요구사항 | 설계·시험 |
|---|---|
| R01 Header | 기준 패키지·repository scope·공통 shell |
| R02~R03 수치 | topics 합계·예시값 비고정 |
| R04~R06 Issue/flow | selection·support source |
| R07~R10 message/trace | source 소속·역할·순서·wire 비노출 |
| R11 snapshot | 한 행 원자 upsert·동일 snapshot |
| R12 한계 | partial·truncated·archived |
| R13 대체 금지 | ambiguous/unverified fixture |
| R14 주소 | click 행동 없음 |

## 15. v1 한계

- 재시작 시 in-memory 진행·cooldown 상태가 사라진다.
- 다중 인스턴스 외부 호출 중복을 막지 않는다.
- repository 검증 cache가 없어 결과 TTL 동안 후보 변경 반영이 늦을 수 있다.
- raw source 미보존으로 삭제·편집된 원문의 장기 감사가 보장되지 않는다.
- `REPOSITORY_WIDE`는 monorepo 전체 논의를 package 전용으로 보장하지 않는다.
- 180/365일·Issue 2·댓글 100·20초는 초기값이며 변경 시 계약과 fixture를 함께 올린다.
- 자동 MR pipeline이 없어 검증 증거 누락 위험이 있다.

분산 lock, 원문 저장, 이력 table, 큰 queue를 조용히 추가하지 않는다. 한계 제거는 계약과 Jira를 먼저
갱신한다.

## 16. 외부 근거와 provenance

- [GitHub REST API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions)
- [GitHub Search API](https://docs.github.com/en/rest/search/search)
- [GitHub Issue comments API](https://docs.github.com/en/rest/issues/comments)
- [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

2026-09-11 확인 시 `2026-03-10`은 지원 version이다. 일반 인증 REST와 Search budget을 따로 관측하고,
403/429의 `retry-after`를 우선하며 remaining 0이면 reset 전 재시도하지 않는다.

다운로드 원문은 commit `1b60139`에서 재현할 수 있다. 이번 업그레이드는 병합 전제 제거, JdbcTemplate
정합, `seed_reset` 포함 4개 초기화, 명시적 basePackage, POST query/signal, 202 반환형, 상태 namespace,
TTL 경계, executor 교착 방지, 1.6 GiB 운영 제약을 반영했다. 과정은
`docs/worklogs/S15P21A506-284/`에 보존한다.
