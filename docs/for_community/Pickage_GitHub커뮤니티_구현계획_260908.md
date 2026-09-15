# Pickage GitHub 커뮤니티 현황 구현계획

최초 작성: 2026-09-08 · 실행 계약 재검수: 2026-09-11

문서 작업: `S15P21A506-307` · 이전 최신화: `S15P21A506-284`

이 문서의 본문은 **앞으로 구현할 작업과 인수 조건**이다. 현재 구현 완료를 뜻하지 않는다.
현행 코드 기준선·과거 결정·보관 일정·허용한 한계는 부록으로 분리했다.
제품 기준은 [요구사항 명세서](../Pickage_요구사항_명세서_0915.md)의 확장-03이고,
backend/frontend가 공유할 community 상세 계약은 이 문서 하나를 사용한다.
외부 GMS 연결 정보의 미확인 값은 §10의 담당자가 확보해야 하며 임의 endpoint를 만들지 않는다.

## 1. 구현 범위와 완료 정의

비교 대상을 확정한 사용자의 **최초 기준 패키지 하나**에 대해 GitHub 커뮤니티 현황을 제공한다.
후보 노출 최대 3개·최초 기준만 선택·총 비교 1~3개라는 제품 결정을 바꾸지 않는다.
community의 Issue 최대 2개·Issue별 대표 메시지 최대 3개는 비교 후보 개수와 별개다.

- 기존 `/report/:reportId` 공통 shell에 세 번째 lazy tab을 추가한다. 새 최상위 route·중복 header는 만들지 않는다.
- 기준 패키지의 저장소를 검증하고 Issue만 수집한다. PR·다른 패키지·시안의 예시 패키지로 대체하지 않는다.
- GitHub의 사실 수치·원문에 근거한 요약·확인 가능한 역할만 표시한다. 숫자·역할·합의는 모델이 만들지 않는다.
- 화면에 공개할 결과는 PostgreSQL `community_snapshot`의 최신 한 행으로 원자 게시한다.
- raw 본문·댓글·prompt는 refresh 중 메모리에서만 사용한다. 원문 저장·이력 테이블·Redis·새 worker 서비스를 추가하지 않는다.
- Spring → GMS 직접 호출은 이 bounded refresh에만 허용한다. 일반 분석 실행 경로까지 확대하지 않는다.
- 저장소·작성자 식별자는 읽기 전용 텍스트다. 외부 이동·GitHub 원문 링크 버튼은 만들지 않는다.
- Issue 장기 시계열은 ecosystem Activity 확장 소유다. 여기서 배치 시계열을 구현하지 않는다.

완료는 “화면이 보임”이 아니라, §11의 각 파트 산출물과 §12의 실패·경계 시험을 모두 통과한 상태다.
GMS 실연결 확인 전에는 fake client로 개발할 수 있지만 운영 연동 완료로 표시하지 않는다.

## 2. 시작부터 표시까지의 실행 순서

1. frontend가 입력 검증을 완료하고 `basePackage`와 비교 목록을 캡처한다.
2. `POST refresh(ANALYSIS_CONFIRMED)`를 비차단으로 보낸다. 응답을 기다리지 않고 기존 보고서 이동을 계속한다.
3. community 탭 최초 진입은 `POST refresh(TAB_OPENED)`로 작업을 보장한 뒤 GET한다. POST 실패여도 GET으로 기존 결과를 확인한다.
4. backend는 package 존재 → 기존 작업 참여 → 저장 결과/재시도 자격 → 설정/호출량/실행 용량 순으로 판단한다.
5. 허용된 작업만 저장소 검증 → Issue 검색 → 댓글 수집 → GMS 요약 → 검증 → 게시를 수행한다.
6. frontend는 탭이 보이고 refresh가 QUEUED/RUNNING일 때만 GET polling한다.
7. 결과가 있으면 먼저 표시하고 갱신 진행·실패를 함께 알린다. 이전 결과는 7일 경계 이후 표시하지 않는다.

GET은 수집을 시작하지 않는다. hover prefetch는 tab code chunk만 읽는다.
현재 보고서 ID는 frontend 임시 ID이므로 존재하지 않는 서버 report 생성 API를 선행 조건으로 만들지 않는다.
기준 패키지는 report ID나 알파벳순 query key에서 추론하지 않는다.

## 3. 저장소 검증과 수집 정책

### 3.1 npm → GitHub 연결

npm `/{encodedPackageName}/latest` metadata의 repository와 DB `package.repo_url`을 각각 정규화한다.
scoped 이름은 URL component로 인코딩한다. npm name이 요청 이름과 다르면 검증 실패다.

| 입력 상황 | 선택·중단 규칙 |
|---|---|
| npm repository가 유효한 GitHub 주소 | npm 우선. DB가 다르면 REPOSITORY_SOURCE_CONFLICT limitation |
| npm repository가 명시적으로 비 GitHub 주소 | UNSUPPORTED_HOST. DB의 과거 GitHub 주소로 우회하지 않음 |
| npm repository 필드 없음, DB에 GitHub 주소 있음 | DB 후보 사용. root package.json 이름 일치를 반드시 요구 |
| npm repository 값이 있으나 파싱 불가 | UNVERIFIED_REPOSITORY. DB로 조용히 대체하지 않음 |
| 양쪽 후보 없음 또는 npm 404/name 불일치 | UNVERIFIED_REPOSITORY |
| npm/GitHub 통신 실패·rate limit | 확정적인 연결 실패로 저장하지 않고 일시 refresh 실패 |
| 공개 repository 확인 실패·GitHub 404 | rate limit과 구분한 뒤 UNVERIFIED_REPOSITORY |

허용 정규화는 `git+https`, 정상 GitHub git/SSH 표기의 owner/repo, 끝의 `.git`, fragment 제거다.
임의 사용자 정보가 있는 HTTPS URL·임의 port·IP host·경로 탈출은 거부한다.
실제 요청은 고정 npm registry와 `api.github.com` base에 검증된 path segment로 조립한다.
모델·metadata가 준 임의 URL을 fetch하지 않는다. 자동 cross-host redirect를 끄고 GitHub 이동 시에도
허용 host·최종 owner/repo·공개 여부를 다시 검증한다. 인증으로 보이는 private repository도 범위 밖이다.

GitHub repository metadata 확인 후 지정 경로의 package.json을 Contents API로 읽는다.
directory는 상대 segment만 허용하고 decoding 전후 `..`, 절대경로, 역슬래시, 빈 탈출 segment를 거부한다.
package.json은 JSON 데이터로만 파싱하며 script·archive·download_url을 실행/추적하지 않는다.
Contents API가 파일로 반환하는 repository 내부 symlink를 항상 식별할 수 있다고 가정하지 않는다.

| 검증 증거 | 최종 scope / 처리 |
|---|---|
| npm directory가 명시되고 해당 package.json name 일치 | REPOSITORY_WIDE; package 연결은 확인했지만 Issue는 저장소 전체 |
| npm directory가 명시됐지만 파일 없음·name 불일치 | AMBIGUOUS_SCOPE; root로 우회하지 않고 중단 |
| directory 없음, root name 일치, root workspaces 증거 없음 | PACKAGE_SCOPED; root 연결에 기반한 추정임을 한계 문구로 명시 |
| directory 없음, root name 일치, workspaces 존재 | REPOSITORY_WIDE |
| npm GitHub 후보, directory 없음, root name 불일치/파일 없음 | REPOSITORY_WIDE; npm repository 연결만 확인했다는 limitation |
| DB만 후보, root name 불일치/파일 없음 | AMBIGUOUS_SCOPE; npm 보강 없이 연결을 확정하지 않음 |

`PACKAGE_SCOPED`도 모든 Issue의 주제가 해당 패키지라고 증명하지 않는다.
v1은 label·본문으로 monorepo package별 Issue를 분리하지 않는다.
archived는 수집 중단 이유가 아니라 `REPOSITORY_ARCHIVED` limitation이다.
원문 수집 전에 terminal 판정이 나오면 빈 topics를 가진 결과를 게시하고 GMS를 호출하지 않는다.

### 3.2 Issue 선택: github-active-v1

- 작업 시작 UTC 시각에서 180일 전의 UTC 날짜를 구해 `repo:owner/repo is:issue updated:>=YYYY-MM-DD`로 검색한다.
- `sort=comments&order=desc&per_page=30&page=1`. raw `total_count=0`이고 incomplete가 아닐 때만 365일로 한 번 확장한다.
- 결과에서 PR, locked, `user.type=Bot`인 Issue를 제외한다. 필터 후 0건이어도 기간을 추가 확장하거나 다른 page를 채우지 않는다.
- 받은 최대 30개 안에서 comments desc → updated_at desc → issue_number desc로 정렬해 최대 2개를 선택한다.
- tie-break는 검색 전체가 아니라 받은 상위 30개 안에서만 보장한다.
- `incomplete_results=true`면 SEARCH_INCOMPLETE. 0건이어도 “논의 없음 확정”이 아닌 PARTIAL이다.
- 정상 완전 검색에서 선택 결과 0개면 NO_DISCUSSION_DATA. 필터로 제외된 경우도 limitation으로 사유를 표시한다.

수치는 선택된 Issue record의 `comments`, `reactions.total_count`, `state`만 사용한다.
댓글 수는 수집한 100개나 사람이 쓴 댓글만의 수가 아니며, 반응에 comment reaction을 중복 합산하지 않는다.
상단 issue_count/open_issue_count/comment_count/reaction_count는 **같은 topics 집합**의 합계다.
저장소 전체 수치·고유 참여자 수·실시간 원자 스냅샷이라고 표기하지 않는다.

### 3.3 최신 댓글 최대 100개

Issue별 comments endpoint는 오름차순으로 반환하므로 첫 page만 읽고 최신 100개라고 하지 않는다.
`per_page=100`으로 page 1을 읽고 Link의 last를 확인한다.

1. last가 없으면 page 1을 사용한다.
2. last가 있으면 마지막 page를 읽는다. 마지막 page가 100개 미만이면 직전 page를 한 번 읽는다.
3. page 1이 직전 page면 재요청하지 않고 재사용한다. Issue당 comments 호출은 최대 3회다. Link URL을 그대로 fetch하지 않고 검증한 page 정수만 고정 API path에 적용한다.
4. source ID로 중복 제거하고 created_at·수치 ID 오름차순 정렬 후 끝 100개를 선택한다.
5. 101개면 마지막 1개+직전 99개, 199개면 마지막 99개+직전 1개, 301개면 마지막 1개+page 3의 99개가 된다.

ID는 입출력에서 십진 문자열로 보존하고 수치 비교 시 BigInteger 등 손실 없는 비교를 쓴다.
pagination 중 댓글 삭제/추가, page 실패, 응답 크기 제한, 원래 댓글 100개 초과는 TRUNCATED다.
일부 읽힌 댓글은 사용할 수 있지만 완전 수집으로 표시하지 않는다. 모든 댓글 page 실패는 FAILED다.
GitHub는 이 요청들을 원자화하지 않으므로 감지할 수 없는 동시 변경까지 “정확한 최신 100개”라고 보장하지 않는다.
Bot 댓글은 사실 댓글 수에 포함하되 대표 메시지에서 제외한다. 알려진 삭제 작성자는 역할 null로 둔다.

### 3.4 응답·메모리 상한

HTTP body를 전부 메모리에 올린 뒤 글자를 자르는 구현은 금지한다.
압축 해제 후 streaming decode 누적 bytes를 검사하고 상한 초과 시 닫는다.

| 응답 | 요청당 decoded bytes 상한 |
|---|---|
| npm latest metadata | 1 MiB |
| GitHub repository / package.json Contents | 각각 1 MiB |
| GitHub Search / comments page | 각각 8 MiB |
| GMS response | 256 KiB |

이 값은 v1 구현 기본값이다. 큰 응답을 받으면 body 전체를 log로 출력하지 않는다.
필수 검증 응답 초과는 refresh GITHUB_UNAVAILABLE/NPM_UNAVAILABLE 및 정제 reason `RESPONSE_TOO_LARGE`,
일부 Issue 자료만 사용 가능한 경우는 PARTIAL + RESPONSE_SIZE_LIMITED로 처리한다.
전체 refresh deadline 안에서만 다음 호출을 시작한다. 숨은 자동 HTTP retry는 끈다.

## 4. GMS 입출력·환각 방지

### 4.1 입력

Issue 원제목과 source 목록을 전달한다. source는 `ISSUE_BODY` 또는 `COMMENT`,
`source_id`, 원문 text, 원본 created_at, 서버가 확인한 author 식별자를 가진다.
Issue body와 comment는 같은 숫자 ID여도 source type을 포함해 구분한다.
제목을 포함한 전체 입력 text는 Issue당 48,000자, 각 source text는 4,000자 이하로 자른다.
제목·본문 우선, 나머지는 최신 댓글부터 예산에 담은 뒤 모델에는 시각순으로 전달한다.
절단하면 SUMMARY_INPUT_LIMITED. 모델에 실제 전달하지 않은 source ID는 support로 인정하지 않는다.
빈 body는 가짜 내용을 넣지 않는다. 제목만 있으면 제목 근거 요약은 가능하나 대표 댓글은 0개다.

외부 원문은 명령이 아니라 데이터로 경계 표시한다. system prompt에 새 지시·링크 따라가기·역할 추정 금지를 둔다.
Issue당 max output 2,048 tokens이며 재생성·JSON repair 재호출은 v1에 없다.
실제 model context 한도에서 system prompt와 출력 2,048 tokens를 뺀 입력 token 예산도 지킨다.
48,000자는 token 상한을 대신하지 않는다. token 계산/허용 context는 C1 실연결 계약에 포함한다.

### 4.2 모델 JSON 계약

아래는 합성 fixture이며 실제 GitHub Issue에 대한 주장이 아니다.
모든 key 필수, additional property 금지, source는 전달된 해당 Issue의 것만 허용한다.

```json
{
  "issue_number": 7,
  "title_ko": "설정 동작 확인",
  "summary_ko": "작성자가 설정 동작을 질문했고 댓글에서 확인 방법이 제시됐다.",
  "summary_support": [{"type": "ISSUE_BODY", "id": "701"}, {"type": "COMMENT", "id": "9007199254740993"}],
  "flow": [
    {"text": "설정 동작에 관한 질문이 제기됐다.", "support": [{"type": "ISSUE_BODY", "id": "701"}]},
    {"text": "댓글에서 확인 방법이 제시됐다.", "support": [{"type": "COMMENT", "id": "9007199254740993"}]}
  ],
  "messages": [
    {"source_comment_id": "9007199254740993", "kind": "DISCUSSION", "text": "설정을 확인하는 방법을 제시했다."}
  ]
}
```

| 필드 | 제약 |
|---|---|
| issue_number | 요청 Issue number와 동일한 양의 정수 |
| title_ko | 공백 제외 비어 있지 않음, 최대 200자; 원제목의 의미를 보존 |
| summary_ko / summary_support | 최대 500자 / 1~101개, 중복 없음 |
| flow | 1~4개; text 최대 200자, support 1~101개 |
| messages | 0~3개; source_comment_id 중복 없음, text 최대 300자 |
| kind | DISCUSSION 또는 USER_SOLUTION |
| support type/id | ISSUE_BODY 또는 COMMENT / 십진 문자열 |

USER_SOLUTION은 댓글의 해결 방법 제시 유형이지 작성자 역할이나 채택·정답 판정이 아니다.
Issue body를 대표 메시지로 만들지 않는다. 모델은 작성자·association·시각·수치·상태·URL을 출력하지 않는다.
텍스트는 plain text로만 제공하고 HTML 태그·URL·Markdown link를 거부한다.

### 4.3 검증과 게시 가능 범위

schema·길이·enum·source 존재/소속·중복·source 종류 위반은 해당 Issue 요약 전체 FAILED다.
대표 메시지 작성자·시각·역할은 source_comment_id로 원본에서 붙인다.
Issue author와 comment author의 **존재하는 안정 ID**가 같으면 ISSUE_AUTHOR를 우선한다.
null ID끼리 일치로 처리하지 않는다. 나머지 association은 다음 표대로만 표시한다.

| author_association | role |
|---|---|
| OWNER | REPOSITORY_OWNER |
| MEMBER | ORGANIZATION_MEMBER |
| COLLABORATOR | COLLABORATOR |
| CONTRIBUTOR | CONTRIBUTOR |
| 그 외·작성자 삭제/확인 불가 | null |

MAINTAINER를 association에서 추정하지 않는다. 여러 댓글의 말을 한 사람 발화로 합치지 않는다.
**source ID 실재 검사만으로 의미 왜곡을 자동 검출할 수는 없다.**
담당 AI와 기획자가 원문/요약 쌍을 사람이 읽어 반박·부정·조건·해결 미확정·악성 지시 fixture를 검수한다.
수치·역할은 서버 결정으로 봉쇄하고 의미 품질은 이 고정 평가 세트로 merge gate를 운영한다.
추가 검증 모델 호출을 조용히 도입하지 않는다.

요약 실패여도 이미 검증한 Issue 원제목·수치·시각은 게시할 수 있다.
실패 topic은 title_ko/summary_ko=null, flow/messages=[]로 두고 원제목을 표시한다.
support 목록은 생성 시 메모리 검증 후 폐기한다. 장기 저장에는 issue source ID와 선택된 대표 comment ID만 남긴다.
따라서 모든 요약 문장의 장기 원문 재감사까지 지원한다고 주장하지 않는다.

## 5. 데이터·상태·TTL

### 5.1 저장 스키마와 직렬화

새 migration 후보는 `V5__community.sql`이지만 구현 착수 시 최신 develop의 다음 빈 번호로 확정한다.
기존 V1~V4 편집·rename·Flyway repair는 금지한다. JPA Entity 없이 JdbcTemplate·record를 사용한다.

| column | type / constraint |
|---|---|
| package_id | INT PK, FK package(id), ON DELETE CASCADE |
| snapshot_id | UUID NOT NULL UNIQUE |
| payload_version | SMALLINT NOT NULL CHECK > 0; 최초 1 |
| collected_at | TIMESTAMPTZ NOT NULL |
| data_status | VARCHAR(30) NOT NULL, 아래 6개 값 CHECK |
| result | JSONB NOT NULL CHECK jsonb_typeof(result) = 'object' |

`collected_at` index를 추가한다. 7일 정리 조건과 배치 DELETE 계획을 확인한다.
result JSON은 §6의 repository/topics/limitations를 저장하되 각 topic에 내부 `source_issue_id`,
각 message에 `source_comment_id`·원본 `author_association`·검증된 `is_issue_author:boolean`을 추가한다.
message의 author_login/created_at/kind/text는 보존하고 role은 is_issue_author와 association으로 재계산한다.
원본 author ID 전체를 저장하지 않아도 재시작 후 ISSUE_AUTHOR를 복원할 수 있어야 한다.
result 최상위에는 `policy_version`, `lookback_days`, `summary_retry_at:nullable timestamp`도 저장한다.
365일 확장 여부를 메모리만 기억하면 재시작 때 180일로 오표시되므로 실제 정책 입력을 보존한다.
표시 role/order, summary 합계, data_limits의 표시 문구·상한, fresh_until/serve_until은 조회 때 계산한다.
data_limits 상한은 저장된 policy_version의 상수로 복원한다. 정책 변경은 version과 fixture를 함께 올린다.
raw body·raw comment·prompt·hash·외부 response·URL은 저장하지 않는다.

알 수 없는 payload_version 또는 등록하지 않은 policy_version은 변환을 추측하지 않고 결과 없음으로 취급해 refresh 자격을 부여한다.
지원 version의 JSON이 깨졌으면 S001로 처리하고 snapshot ID와 정제 원인만 log에 남긴다.
Jackson typed payload 검증은 쓰기와 읽기 모두 수행한다.

### 5.2 자료 상태와 요약 상태

| data_status | 판정 |
|---|---|
| AVAILABLE | 검증·검색·선택 Issue 자료 수집이 완전함 |
| PARTIAL | 검색 incomplete, 댓글 TRUNCATED/FAILED 등 일부 자료의 완전성을 보장 못함 |
| UNVERIFIED_REPOSITORY | 공개 저장소 연결 증거 부족 |
| AMBIGUOUS_SCOPE | 지정 package 경로/이름 또는 DB-only 연결 모호 |
| UNSUPPORTED_HOST | 최종 repository가 GitHub 외 host |
| NO_DISCUSSION_DATA | 완전한 정책 검색 후 선택 Issue 0개 |

data_status는 자료 수집 축이고 summary_status는 요약 축이다.
예를 들어 자료 AVAILABLE + 전체 GMS 실패 summary FAILED는 가능하며 사실 자료는 저장한다.
GMS timeout이 언제나 DB 저장 금지라는 뜻이 아니다.
필수 npm/GitHub 통신 전면 실패·deadline·게시 실패는 새 snapshot 없이 refresh FAILED로 남긴다.
게시 가능한 자료를 이미 확보했다면 남은 요약을 FAILED로 끝내고 deadline 전에 게시할 수 있다.

topic collection_status: COMPLETE/TRUNCATED/FAILED. topic summary_status: READY/FAILED/SKIPPED.
대상이 없는 결과는 전체 SKIPPED, 모든 대상 READY면 READY, 일부만 READY면 PARTIAL,
대상이 있고 READY가 0개이며 실패가 있으면 FAILED다. 수집 문제로 요약을 시작하지 못한 topic도 FAILED로 둔다.
SKIPPED는 요약 대상이 없는 경우에만 사용한다.

### 5.3 게시와 보존

collected_at은 worker가 실제 수집을 시작한 UTC 시각이다. 완료 시각으로 관측 시각을 늦추지 않는다.
외부 I/O는 transaction 밖에서 수행한다. 게시만 짧은 transaction으로 아래를 수행한다.

1. 현재 task 소유권·취소·남은 게시 예산을 확인한다.
2. connection 획득도 남은 게시 예산 이내로 제한한다. 같은 DataSource의 transaction 안에서 SET LOCAL lock_timeout/statement_timeout을 남은 시간 이내로 설정한다(각 최대 1초/2초).
3. package ID 기반 PostgreSQL transaction advisory lock을 잡고 남은 시간을 다시 확인해 INSERT ... ON CONFLICT UPDATE한다. SELECT형 lock 요청도 timeout 시험 대상이다.
4. commit 성공 후 registry COMPLETED. rollback 시 이전 행을 그대로 남긴다.

refresh의 마지막 2초는 게시용으로 예약한다. 기한 뒤 도착한 외부 future는 게시할 수 없다.
JPA transaction manager에 JdbcTemplate이 같은 connection으로 참여하는지 강제 rollback 시험으로 입증한다.
connection 고갈·lock 경합·statement 지연을 각각 주입해 게시 예산을 시험한다.
annotation만 붙이고 원자성 검증을 생략하거나 pool 기본 대기를 그대로 두고 deadline을 보장하지 않는다.

| 경계 | 반환 |
|---|---|
| now < collected_at + 24h | FRESH |
| 24h <= age < 7d | STALE |
| age >= 7d | 결과 반환 금지 |

정상 FRESH는 재수집하지 않는다. **전체 summary FAILED인 FRESH는 수집 시작 후가 아니라 해당 실패 완료 후 5분부터 사용자 요청으로 재수집**할 수 있다.
재시도 시 raw가 없으므로 저장소/Issue부터 다시 수집한다. 일부 요약 성공 PARTIAL은 기본 24시간 재사용한다.
일시 refresh 실패는 기존 collected_at을 바꾸지 않는다. rate limit retry_at이 더 늦으면 그것을 따른다.
전체 요약 실패를 확정한 시각 + 5분을 summary_retry_at에 저장하고 wire에도 제공한다.
그 외 결과는 summary_retry_at=null이다. collected_at+5분으로 추정하지 않는다.
POST와 UI 버튼은 summary_retry_at 및 최근 refresh 실패/외부 gate의 retry_at 중 늦은 시각을 따른다.
재시작으로 registry를 잃어도 저장된 summary_retry_at 이전에 다시 요약하지 않는다.

매시간 `collected_at <= now - 7d`인 행을 정렬해 최대 500개 삭제한다. GET의 TTL 검사를 정리 작업으로 대체하지 않는다.
현재 package TRUNCATE가 있는 seed_sample/seed_mock_parity/seed_service_full/seed_reset **4개**의 같은 목록에 새 테이블을 추가한다.
seed_clear_snapshots는 package를 유지하므로 community를 지우지 않는다.
seed는 격리된 로컬 검증 DB에서만 실행하고 운영/Curated DB에 실행하지 않는다.

## 6. backend/frontend 공유 API 계약

이 절은 새 API의 구현 목표다. 기존 Notion 정본/Swagger에 이미 등록됐다는 뜻이 아니다.
BE 담당자가 구현 전 동일 계약을 등록하고 FE/QA가 fixture와 함께 확인한다.

### 6.1 endpoint·오류

- POST `/api/packages/community/refresh?name=<encoded base>&trigger=ANALYSIS_CONFIRMED`
- POST `/api/packages/community/refresh?name=<encoded base>&trigger=TAB_OPENED`
- GET `/api/packages/community?name=<encoded base>`

CommunityController를 별도로 둔다. name은 PackageNames.isValidName을 재사용하되 단일 이름만 받는다.
없는 DB package는 기존 C006/404를 재사용한다. 이 신규 적용 범위는 ExceptionType 설명·Swagger에도 반영한다.
name/trigger 누락 또는 빈 값은 V001/400, 잘못된 name 형식·알 수 없는 trigger는 V004/400이다.
trigger enum 바인딩은 현재 GlobalExceptionHandler.typeMismatch의 V004 매핑을 따른다. 기존 error envelope를 사용한다.
내부 오류는 S001/500. API 계층 오류와 아래 정상 data 안의 refresh 실패를 섞지 않는다.

POST가 새 task를 수락하면 202, fresh hit·기존 작업 참여·정상적인 admission 거절이면 200이다.
GET은 부작용 없이 200. 반환형은 `ResponseEntity<ApiResponseBody<CommunityResponse>>`.
GET/POST 모두 `Cache-Control: no-store`. API wrapper는 기존 `success/data`, key는 snake_case.
미사용 nullable key도 생략하지 않고 null로 직렬화하며 계약 시험으로 확인한다.

### 6.2 data 필드 사전

아래 모든 필드는 필수 key다. nullable이라고 쓴 필드만 null 가능하다.
string은 UTF-8, timestamp는 UTC ISO 8601 Z, count는 음수가 아닌 안전 정수다.
Java long을 무조건 JS number로 내리지 않는다. GitHub source ID는 공개하지 않고 내부에서는 십진 문자열이다.

| 객체 | 필드와 타입 |
|---|---|
| CommunityResponse | package_name:string, view_status:enum, freshness:nullable enum, refresh:nullable Refresh, result:nullable Result |
| Refresh | refresh_id:nullable UUID string, status:enum, stage:nullable enum, stage_message:string, started_at:nullable timestamp, last_updated_at:timestamp, poll_after_seconds:nullable integer, retry_at:nullable timestamp, error_code:nullable enum |
| Result | snapshot_id:UUID string, collected_at:timestamp, fresh_until:timestamp, serve_until:timestamp, data_status:enum, summary_status:enum, summary_retry_at:nullable timestamp, repository:nullable Repository, summary:Summary, topics:Topic[], limitations:Limitation[], data_limits:DataLimits |
| Repository | owner:string, name:string, full_name:string, scope:PACKAGE_SCOPED or REPOSITORY_WIDE, archived:boolean |
| Summary | issue_count:integer, open_issue_count:integer, comment_count:integer, reaction_count:integer |
| Topic | issue_number:positive integer, title_original:string, title_ko:nullable string, summary_ko:nullable string, state:OPEN or CLOSED, comments_count:integer, reactions_count:integer, created_at:timestamp, updated_at:timestamp, collection_status:enum, summary_status:enum, flow:Flow[], messages:Message[] |
| Flow | text:string |
| Message | author_login:nullable string, role:nullable enum, created_at:timestamp, kind:DISCUSSION or USER_SOLUTION, text:string |
| Limitation | code:enum, message:string, issue_number:nullable positive integer |
| DataLimits | policy_version:string, lookback_days:180 or 365, max_issues:2, max_comments_per_issue:100, max_messages_per_issue:3, source_note:string |

terminal 검증 결과에서는 repository=null, summary 수치 모두 0, topics=[]다.
repository는 연결을 확인한 경우에만 채운다. model generated URL, package_id, author ID, source ID, support 목록은 wire에서 제외한다.
title_original은 출력할 때 200자로 제한하고 잘림을 표시한다. 원본 전체 제목을 요약 입력과 혼동하지 않는다.
data_limits.lookback_days는 실제 마지막 검색 기간이며 검색 전 중단이면 기본 정책 180이다.

topics는 §3.2 선택 순서, messages는 원본 created_at·수치 source ID 오름차순이다.
flow는 모델이 검증 가능한 사건 순으로 작성하되 동일 시각 인과관계를 임의로 만들지 않는다.
summary는 topics의 사실 수치 합계다. 요약 실패나 댓글 절단으로 사실 comments_count를 100으로 자르지 않는다.

limitation code는 아래 목록에서만 사용하고 설명은 서버 템플릿으로 만든다.
REPOSITORY_SOURCE_CONFLICT, REPOSITORY_WIDE_SCOPE, ROOT_PACKAGE_SCOPE_HEURISTIC,
NPM_REPOSITORY_ONLY, REPOSITORY_ARCHIVED, SEARCH_INCOMPLETE, ISSUE_FILTERED,
COMMENTS_TRUNCATED, COMMENTS_UNAVAILABLE, SUMMARY_INPUT_LIMITED, SUMMARY_UNAVAILABLE,
RESPONSE_SIZE_LIMITED. 추가할 때 backend/frontend enum·fixture·이 문서를 같이 갱신한다.

### 6.3 view·refresh 판정

view_status 우선순위는 “반환 가능한 result 있으면 RESULT → active task면 PROCESSING
→ 최근 작업/이번 admission 실패면 FAILED → 나머지 IDLE”다.
freshness는 result가 있을 때만 FRESH/STALE, 없으면 null.
재시작 후 결과도 task도 없으면 IDLE이지 영구 PROCESSING이 아니다.

refresh.status는 QUEUED/RUNNING/COMPLETED/FAILED/CAPACITY_LIMITED다.
stage는 VERIFYING_REPOSITORY/SEARCHING_ISSUES/COLLECTING_COMMENTS/SUMMARIZING/VALIDATING/PUBLISHING이며
RUNNING 외에는 null. stage_message는 서버의 한국어 고정 문구다. 가짜 퍼센트를 반환하지 않는다.
poll_after_seconds는 QUEUED/RUNNING일 때 2, 종료/거절이면 null.
started_at은 실제 worker 시작 전 null, last_updated_at은 상태 전이 시각이다.
task 미생성 admission 거절은 refresh_id=null이고 status=CAPACITY_LIMITED(용량/로컬 호출량) 또는 FAILED(설정/외부 cooldown)다.

error_code: GITHUB_RATE_LIMITED, GITHUB_UNAVAILABLE, NPM_UNAVAILABLE, GMS_UNAVAILABLE,
REFRESH_DEADLINE_EXCEEDED, PUBLISH_FAILED, CAPACITY_LIMITED, LOCAL_RATE_LIMITED, COMMUNITY_DISABLED.
GMS만 실패해 사실 결과를 게시했으면 refresh COMPLETED/error_code=null이고 topic/summary FAILED 및 SUMMARY_UNAVAILABLE로 알린다.
FETCH_LIMITED는 저장 자료 상태가 아니다. 원인별 refresh error 또는 PARTIAL limitation을 사용한다.

refresh=null은 추적 가능한 task/거절이 없다는 뜻이다. 재시작 후에도 DB 결과는 RESULT로 조회한다.
동일 package의 종료 task는 10분간 조회 가능하며 그 뒤 result만 남는다.
이미 active task가 있으면 뒤늦은 실패 요청이 registry를 덮어쓰지 않고 그 task를 반환한다.

### 6.4 완전한 wire 예시

아래는 FE/BE 계약 시험용 합성 데이터다. 실제 npm/GitHub 현황을 주장하지 않는다.
서버 재시작 후 task가 없어도 사실 결과와 전체 요약 실패의 재시도 시각을 복원한 GET이다.

```json
{
  "success": true,
  "data": {
    "package_name": "community-fixture",
    "view_status": "RESULT",
    "freshness": "FRESH",
    "refresh": null,
    "result": {
      "snapshot_id": "00000000-0000-4000-8000-000000000001",
      "collected_at": "2026-09-11T00:00:00Z",
      "fresh_until": "2026-09-12T00:00:00Z",
      "serve_until": "2026-09-18T00:00:00Z",
      "data_status": "AVAILABLE",
      "summary_status": "FAILED",
      "summary_retry_at": "2026-09-11T00:05:12Z",
      "repository": {
        "owner": "pickage-fixture",
        "name": "community-fixture",
        "full_name": "pickage-fixture/community-fixture",
        "scope": "PACKAGE_SCOPED",
        "archived": false
      },
      "summary": {"issue_count": 1, "open_issue_count": 1, "comment_count": 2, "reaction_count": 1},
      "topics": [{
        "issue_number": 7,
        "title_original": "Configuration question",
        "title_ko": null,
        "summary_ko": null,
        "state": "OPEN",
        "comments_count": 2,
        "reactions_count": 1,
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-09-10T00:00:00Z",
        "collection_status": "COMPLETE",
        "summary_status": "FAILED",
        "flow": [],
        "messages": []
      }],
      "limitations": [
        {"code": "ROOT_PACKAGE_SCOPE_HEURISTIC", "message": "루트 패키지 연결에 기반하며 모든 Issue의 주제를 보장하지 않습니다.", "issue_number": null},
        {"code": "SUMMARY_UNAVAILABLE", "message": "요약을 제공하지 못해 확인된 제목과 수치만 표시합니다.", "issue_number": 7}
      ],
      "data_limits": {
        "policy_version": "github-active-v1",
        "lookback_days": 180,
        "max_issues": 2,
        "max_comments_per_issue": 100,
        "max_messages_per_issue": 3,
        "source_note": "수치는 선택한 Issue 집합의 값이며 저장소 전체나 고유 참여자 수가 아닙니다."
      }
    }
  }
}
```

결과도 작업도 없는 최초 GET은 다음과 같다. 이 응답 때문에 GET이 자동 수집을 시작하지 않는다.

```json
{"success": true, "data": {"package_name": "community-fixture", "view_status": "IDLE", "freshness": null, "refresh": null, "result": null}}
```

## 7. backend 파일별 구현과 자원 제어

### 7.1 구성 단위

새 코드는 `backend/src/main/java/com/ssafy/pickage/domain/community/`에 둔다.
아래 이름은 새 파일의 책임 분리 기준이며 기존 구현 파일이 있다고 가정하지 않는다.

| 단위 | 구현 책임 / 입력 → 출력 |
|---|---|
| CommunityController / DTO records | §6 검증·envelope·status code·no-store; request → wire |
| CommunityService | DB package 존재·snapshot read·TTL·view 조합; 외부 수집 금지 |
| CommunityRefreshCoordinator | admission·single-flight·단계·deadline·게시 소유권 |
| CommunityRefreshRegistry | 한 임계구역의 bounded task/queue 상태; 유휴 정리 |
| CommunitySnapshotRepository | typed JSONB 읽기·원자 upsert·TTL 삭제 |
| NpmMetadataClient / GitHubCommunityClient | 고정 host·headers·decoded byte cap·deadline·원본 transient DTO |
| GmsSummaryClient | 확인된 외부 프로토콜과 §4 내부 JSON 사이 adapter |
| RepositoryPolicy / IssueSelectionPolicy | 네트워크 없는 판정 함수 |
| CommunitySummaryValidator | schema·source·역할·길이 검증; 외부 호출 없음 |
| CommunityProperties / configuration | MVC RestClient·bounded executors·scheduler·feature enable |
| unit / integration tests | fake source, clock, executor 및 격리 PostgreSQL |

프로젝트는 MVC이므로 RestClient를 사용하며 client 하나 때문에 WebFlux를 추가하지 않는다.
기존 JdbcTemplate SQL 관례와 전역 snake_case를 따른다.

### 7.2 기본 예산

| 항목 | v1 기본값 |
|---|---|
| refresh admission rate | refill 10건/분, token bucket burst 4; 엄격한 rolling 1분 10건 보장이 아님 |
| refresh worker | 2 threads |
| TAB_OPENED 대기열 | 최대 4; 대기 최대 20초 |
| ANALYSIS_CONFIRMED | worker permit 없으면 무대기 거절 |
| 실행 deadline | worker 시작부터 20초; 마지막 2초 게시 예약 |
| GMS executor | 전역 2 threads, queue 최대 2; refresh pool과 분리 |
| task registry | accepted task 최대 128; 종료 기록 10분, active 강제 퇴출 금지 |
| 실패 cooldown | 완료 후 5분; 외부 retry_at이 더 늦으면 우선 |
| polling / shutdown grace | 2초 / 5초 |

대기 20초 + 실행 20초까지 가능하므로 “요청 수락부터 무조건 20초 완료”라고 표시하지 않는다.
queue deadline 초과는 REFRESH_DEADLINE_EXCEEDED이고 worker를 시작하지 않는다.
전역 rate token은 새 작업 수락에만 소비한다. fresh hit·GET·single-flight 참여에는 쓰지 않는다.

registry·permit·queue를 하나의 원자 admission 구역에서 검사/갱신한다.
상태 조회 시에도 종료 TTL을 정리한다. 등록 공간이 없으면 종료 기록 정리 후 거절하고 active task를 없애지 않는다.
거절 요청마다 영구 registry entry를 만들지 않는다. prefetch 용량 거절은 5분 실패 cooldown을 만들지 않아 탭 안전망을 막지 않는다.
용량/로컬 rate 거절은 해당 여유가 예상되는 짧은 retry_at(최소 2초)을 반환하되 자동 POST loop를 만들지 않는다.

모든 외부 호출은 동일 deadline의 남은 시간으로 connect/read timeout을 제한한다.
GMS 자식 future 대기는 별도 pool을 사용하고 남은 요약 예산이 없으면 FAILED로 완료한다.
timeout/취소된 task가 뒤늦게 upsert하지 못하도록 task ID·active 소유권·기한을 게시 직전 재검사한다.
shutdown은 새 작업을 거절하고 5초 후 남은 작업을 취소하며 이전 snapshot을 훼손하지 않는다.

GitHub token 공유 rate 상태는 package별이 아니라 client 전역으로 관리한다.
core/search budget을 구분하고 primary remaining=0이면 reset까지, secondary는 Retry-After를 우선하며
값이 없으면 최소 1분 backoff한다. task의 5분 cooldown과 충돌하면 더 늦은 retry_at을 적용한다.
rate 제한 이후 같은 refresh의 다른 Issue 호출도 새로 시작하지 않는다.
운영 API 한 인스턴스에서만 single-flight가 보장된다. scale-out 전 분산 coordinator는 별도 작업이다.

## 8. frontend 파일별 구현과 사용자 상태

### 8.1 문맥·통신

`analyze-page.tsx`에서 검증된 기준과 비교 목록을 캡처해
`{ basePackage: string; packages: string[] }`를 route state로 전달한다.
packages는 중복 없는 유효 이름 1~3개이며 packages[0]은 basePackage와 같아야 한다.
명시 basePackage가 없고 과거 packages가 유효할 때만 index 0 호환을 허용한다.
명시 값과 목록이 충돌하면 임의 교정하지 않고 community 실호출을 막는다.
직접 진입·새로고침으로 유효 문맥이 없으면 입력으로 안내한다. 기본 fixture를 실제 package로 보내지 않는다.

공통 API client에 params/body/caller signal option을 추가한다. 기존 호출 서명은 호환 유지한다.
frontend endpoint 상수는 `/packages/community`이며 기존 base URL의 `/api`를 중복 붙이지 않는다.
POST도 query builder를 사용하고 scoped 이름을 인코딩한다.
caller abort와 15초 timeout을 결합하되 body parsing까지 해제/오류 구분을 유지한다.
POST는 자동 재시도하지 않는다. GET은 일시 네트워크/5xx만 최대 2회, 400/404/C006/사용자 abort는 재시도하지 않는다.

분석 확정 POST는 화면 unmount 때문에 바로 취소하지 않고 catch로 처리한다.
StrictMode/effect 재실행의 중복 POST는 동일 분석 intent/탭 진입 단위의 in-flight promise로 합친다.
client의 중복 억제는 backend single-flight를 대체하지 않는다.

### 8.2 탭과 query 생명주기

`frontend/src/routes/report/community/`에 model/adapter/report-tab/progress/result/issue-card/thread/data-limits/sample을 둔다.
실제 HTTP 함수·mock 분기는 기존 중앙 `src/api` endpoint 관례를 따라 하나만 둔다.
Query key는 `['packages','community',basePackage]`. adapter는 wire를 표시 모델로만 변환하며 숫자·역할을 재추론하지 않는다.

최초 진입은 POST 후 GET. 재진입은 GET으로 active/fresh 상태를 먼저 복원하고,
result가 없거나 stale/전체 summary FAILED 재시도 자격이 있을 때만 이 진입에서 POST 한 번을 허용한다.
탭 진입 도중 POST가 실패해도 GET은 실행한다. retry_at 전에는 재수집 버튼을 비활성화한다.
task를 만들지 않은 admission 거절은 GET registry에 없으므로, POST의 거절 안내/retry_at은 기준 패키지별
일시 action notice로 보존한다. 뒤따른 GET IDLE이 이를 지워 거절 원인이 사라지지 않게 한다.
이 notice로 GET wire를 변조하지 않고, 새 active task 확인·성공·명시적 재시도 시 해제한다.
capacity 이후 자동 POST 반복을 하지 않으며 retry_at 이후 명시적 사용자 행동으로 다시 요청한다.

GET polling은 탭/문서가 보이고 QUEUED/RUNNING일 때만 유지한다.
숨김·unmount는 GET만 취소하고 서버 작업을 취소하지 않는다. 재개 시 GET으로 상태를 동기화한다.
서버 작업 추적이 사라진 IDLE은 무한 로딩이 아니라 “수집 시작” 행동을 제공한다.
serve_until에 도달한 client cache 결과는 즉시 숨기고 GET으로 재평가한다.
fresh_until 경계를 넘으면 FRESH 배지를 유지하지 않고 STALE로 재평가한다.

기존 Tabs는 content unmount로 ecosystem의 local filter state를 잃는다.
community 왕복에도 기간/집계/필터를 유지하도록 controls를 공통 shell state로 올리거나 mount 보존을 적용한다.
mount 보존을 택해도 숨은 탭 community polling은 반드시 중단한다.

### 8.3 화면 인수 조건

| 상태 | 표시·행동 |
|---|---|
| IDLE | 결과 없음과 수집 시작 버튼; 가짜 진행 없음 |
| PROCESSING | 실제 stage_message·경과 시간·aria-live polite; 가짜 %/STEP_MS 금지 |
| RESULT/FRESH | 동일 snapshot의 repository·합계·topics·한계 |
| RESULT/STALE + active | 이전 결과 유지 + 작은 갱신 진행 카드 |
| RESULT + refresh FAILED | 기존 결과·관측 시각 유지 + 원인/재시도 가능 시각 |
| RESULT + summary FAILED/PARTIAL | 사실 제목·수치는 유지; 없는 한국어 요약/발화는 생성하지 않음 |
| terminal data_status | 해당 검증/미지원/논의 없음 안내; 다른 package 대체 금지 |
| FAILED, result 없음 | 정제 오류·retry_at·재시도 행동 |
| EXPIRED | 이전 결과 비노출; 서버 refresh 상태에 맞춰 안내 |

공통 shell header를 복제하지 않는다. 저장소·작성자·Issue 번호는 plain text다.
대표 메시지는 실제 댓글만 보여주며 역할 null이면 역할 배지를 생략한다.
Figma `485:936`의 `02-package-intro`~`05-discussion-threads`만 참고한다.
시안 수치 `2·40·17·2`는 layout fixture다. fixture와 runtime policy 시험은 분리한다.
mock 모드에서는 GET/POST 모두 public JSON/fake state로 처리하며 npm/GitHub/GMS network 0건을 입증한다.

## 9. DB·배포 안전성

- 새 migration의 빈 DB 전체 적용과 기존 V1~V4 DB upgrade를 각각 검사한다.
- `ddl-auto=validate`만으로 JDBC 전용 새 테이블은 검증되지 않는다. pg_catalog/정보 스키마로 column·PK/FK·CHECK·UNIQUE·index를 직접 검사한다.
- integration DB 이름은 `pickage_community_test_<uuid>`로 격리하고 cleanup target이 그 DB인지 확인한다.
- local README에 새 migration/seed 순서와 테스트 DB 전용 실행법을 기록한다.
- 기존 app 배포와 함께 additive table을 올리고, 실패 시 community enable을 끄거나 app을 이전 버전으로 돌린다.
- rollback을 이유로 기존 데이터·새 테이블을 즉시 DROP하지 않는다. payload version 호환 여부를 확인한다.
- GET core package API와 ecosystem/features는 community key 누락·장애에도 동작해야 한다.
- 운영 API 1.6 GiB·Swap 0 기준으로 heap peak·thread 수·동시 작업·응답 상한을 확인한다.

## 10. 설정과 실제 외부 연결

| 설정 | 역할·검증 |
|---|---|
| COMMUNITY_ENABLED | 기본 false; 운영 연결 검증 후 true |
| GITHUB_COMMUNITY_TOKEN | 서버 전용, 공개 repository 읽기에 필요한 최소 권한 |
| GMS_API_KEY | 기존 팀 보유 key 연결; 신규 발급을 전제로 하지 않음 |
| GMS_BASE_URL / GMS_REQUEST_PATH | BE+AI가 실제 사용 경로 확인. 임의 OpenAI 호환 path 가정 금지 |
| GMS_AUTH_HEADER / GMS_AUTH_SCHEME | 실제 인증 형식 확인 후 고정; value는 log 금지 |
| GMS_MODEL | 실제 허용 model 식별자 |
| prompt / policy / payload version | 소스의 버전 상수와 fixture를 함께 갱신 |

설정명은 이 기능에 새로 연결할 목표이며 현재 존재한다고 주장하지 않는다.
root `.env.example`, local compose api environment, prod app `.env.example`, prod compose api environment,
Spring application.yaml/CommunityProperties를 같은 매핑으로 갱신한다.
로컬 Gradle bootRun은 root .env를 자동 로드하지 않으므로 셸 환경변수 또는 IDE run config 주입법도 README에 적는다.

BE+AI는 secret을 제거한 요청/응답 fixture로 실제 method/path/auth/envelope/model/timeout/usage/error 매핑을 확인한다.
infra는 서버 secret 주입, egress/TLS, 종료 동작을 확인한다. 이 확인이 없는 상태는 “연결 대기”다.
key는 이미 보유했다는 결정과 실제 연결 계약이 repo에 없다는 사실을 구분한다.

disabled/설정 누락은 새 작업만 막는다. active task 또는 fresh cache가 있으면 그것을 먼저 반환한다.
새 수집이 필요하지만 설정이 없으면 COMMUNITY_DISABLED이며 기존 stale 결과가 있으면 함께 보여준다.
민감 설정 누락으로 core application 전체 startup을 실패시키지 않는다. 배포 smoke에서는 community 연결 실패를 별도 실패 gate로 다룬다.

로그는 refresh ID, package ID, stage/duration, freshness, 정제 오류, retry_at,
GitHub remaining/reset, model/prompt version, source 수·입력 길이만 남긴다.
secret/header·raw prompt·source text·전체 외부 body를 남기지 않는다.
외부 client 예외는 body/인증 값을 제거한 domain 오류로 변환한다. 원본 HTTP 예외나 raw cause를
전역 unexpected handler에 넘겨 stack trace에 response body가 기록되지 않도록 실패 시험으로 확인한다.
단일 refresh 진단은 가능해야 하지만 원문 복원 가능한 로그 저장소를 만들지 않는다.

## 11. 파트별 작업 패키지와 전달 순서

특정 사람 이름 대신 담당 파트와 산출물로 인수한다. 아래 표의 “전달물”을 받은 다음 단계가 독립 구현 가능해야 한다.

| 순서 / 주 담당 | 해야 할 일 | 전달물 / 인수자 | 완료 조건 |
|---|---|---|---|
| C0 기획 + BE + FE + AI | §3~8 enum·JSON·실패 행동을 fixture로 동결, 새 API 정본 등록 | JSON schema, 성공/실패 fixture, API 문서 → 전 파트 | 제품 결정과 동일; 미확인 외부 값 분리 |
| C1 AI + BE, infra 협조 | 실제 GMS 프로토콜 확인, §4 prompt/validator/사람 평가 세트 설계 | 정제 외부 I/O fixture, prompt version, 평가표 → BE/QA | 부정·반박·조건·해결 미확정 보존, source ID 혼입 거부 |
| C2 BE, data 협조 | migration·typed payload·JDBC·정리 SQL·4개 seed/local README | DB migration와 통합 시험 → BE/infra | 빈 DB·upgrade·rollback·제약·index·seed 통과 |
| C3 BE | npm/GitHub client·검증/선택/pagination policy | fake client fixture와 단위 시험 → coordinator | SSRF/미지원/monorepo/101·199·301 댓글 처리 |
| C4 BE | registry·bounded pool·deadline·GMS 연결·원자 게시 | service/coordinator/API/Swagger → FE/QA | single-flight·20초 실행·포화·실패 이전 결과 보존 |
| C5 FE | basePackage route·API option·query·mock·세 번째 tab | 화면/상태 fixture와 테스트 → 기획/QA | 기준 1개·비차단·GET만 retry·탭 왕복 상태 보존 |
| C6 infra, BE 협조 | local/prod env 주입·enable·redaction·메모리·shutdown | secret 없는 설정 예시와 smoke/rollback 기록 → QA | key 미연결 core 정상, 실제 연결 smoke 성공 |
| C7 QA 역할(각 구현 담당 + 기획 교차 검수) | §12 통합 시나리오·사람 요약 평가·정본 일치 | 명령/결과/화면/fixture 증거 → MR reviewer | 모든 gate 통과 또는 별도 승인된 범위로 제외 |

C2/C3/FE mock 화면은 C0 뒤 병행 가능하다. C4 실연결은 C1 확인에 의존한다.
data 파트는 기존 package/snapshot/seed 경계 검수만 수행하며 새 community 배치를 만들지 않는다.
AI 파트는 기존 유사후보 랭커를 수정하지 않는다. worker 파트에 별도 서비스 구축을 배정하지 않는다.
FE의 기존 후보 최대 2개·미정의 setError 등 선행 결함은 별도 이슈/변경으로 처리하고 community 완료에 숨기지 않는다.

## 12. 검증 체크리스트와 merge gate

### 12.1 반드시 재현할 사례

| 시험 | 기대 결과 |
|---|---|
| npm non-GitHub + DB GitHub / DB-only root 불일치 | UNSUPPORTED_HOST / AMBIGUOUS_SCOPE, fallback 0 |
| npm directory 누락과 명시 directory의 파일 누락 | 서로 다른 §3.1 분기 |
| known workspaces / root package 일치 | repo-wide / heuristic 한계 표시 |
| private/redirect host/path traversal/large body | 외부 임의 요청·무제한 decode 없음 |
| 180일 raw 0 / 필터 후 0 / incomplete 0 | 365일 1회 / 재검색 없음 / PARTIAL |
| 댓글 0·100·101·199·200·301 | 최신 최대 100, 호출 최대 3, 100초과 TRUNCATED |
| 큰 ID·null author·Bot·다른 Issue source | 손실 없음·역할 추정 없음·대표 제외·요약 거부 |
| GMS JSON/schema 오류·의미 반전·prompt injection | 구조 오류 자동 거부, 의미 품질은 사람 fixture 평가 실패 |
| GMS 모두 실패 / 하나 실패 | 사실 자료 게시 + summary FAILED / PARTIAL |
| 전체 summary 실패 fresh 4분59초 / 5분 | 재수집 불가 / 사용자 재시도 가능 |
| age 24h 직전·정각 / 7d 직전·정각 | FRESH→STALE / 반환→비반환 |
| stale 갱신 실패 / 게시 rollback | 이전 snapshot ID·collected_at 불변 |
| 동일 package 50요청 / 서로 다른 package 50요청 | single-flight 1개 / queue·registry·pool 상한 유지 |
| npm/GitHub/GMS 정지·queue timeout·shutdown | deadline·소유권 지킴, 뒤늦은 publish 없음 |
| 재시작 후 미게시 작업 | GET IDLE, 영구 PROCESSING 없음 |
| API snapshot serialization roundtrip | null key·snake_case·enum·source 비노출 |
| 400/404/500·caller abort·timeout | 오류 구분, GET 일시 실패만 최대 2회 |
| 빠른 분석 이동·탭 왕복·StrictMode | POST 중복 억제, GET 취소/재개, 필터 보존 |
| 무효 route / mock mode | 실제 외부 호출 0 |
| payload version 미지원 / 지원 JSON 손상 | 결과 없음+refresh 가능 / S001 |
| PostgreSQL JDBC 전용 schema / seed 반복 | 제약·index 직접 검사, 4개 초기화 정상 |

사람 품질 fixture에는 원문, 기대 보존 사실, 금지 주장, 예상 역할, 허용 support를 함께 둔다.
실제 secret/운영 source를 기본 unit test에 넣지 않는다.

### 12.2 명령과 증거

backend 기존 unit/integrationTest source set을 사용한다. integrationTest는 build에 자동 포함되지 않으므로 별도 실행한다.
frontend에는 현재 test runner가 없으므로 C5에서 최소 Vitest/Testing Library 설정과 test script를 추가하고 그 명령을 MR에 기록한다.
설정하기 전에 “npm test 통과”라고 쓰지 않는다.

```text
backend: gradlew.bat test
backend: gradlew.bat integrationTest
backend: gradlew.bat build
frontend: npm run typecheck
frontend: npm run lint
frontend: npm run format:check
frontend: npm run build
frontend: 새로 등록한 unit/component test 명령
```

현재 contextLoads가 DB 설정을 필요로 할 수 있으므로 tests profile과 격리 DB/fake 외부 연결을 명시한다.
자동 GitLab pipeline이 현재 없으므로 실행 환경·baseline 실패·새 실패를 구분한 결과를 MR에 남긴다.
실제 GitHub/GMS smoke는 기본 시험과 분리하고 승인된 서버 secret을 주입해 수동 수행한다.

GMS 실제 계약 미확인, migration 충돌, raw/secret 노출, package fallback, 상태/schema 불일치,
무제한 queue/응답, 비원자 게시, 해결 안 된 신규 typecheck 실패, 사람 평가의 근거 왜곡이 있으면 merge하지 않는다.

## 13. 요구사항 추적

| 요구사항 ID | 본문 설계 / 시험 |
|---|---|
| 확장-03-R01 | §1·2·8 기준 패키지/공통 shell |
| 확장-03-R02, 확장-03-R03 | §3.2·6 동일 topics 합계·시안 수치 비고정 |
| 확장-03-R04, 확장-03-R05, 확장-03-R06 | §3.2·4 Issue/근거/flow |
| 확장-03-R07, 확장-03-R08, 확장-03-R09, 확장-03-R10 | §4·6 대표 댓글/역할/순서/생성 시 추적 |
| 확장-03-R11 | §5 원자 snapshot·TTL |
| 확장-03-R12 | §3~6 수집/요약 한계 |
| 확장-03-R13, 확장-03-R14 | §1·3·8 대체 금지·읽기 전용 주소 |
| 확장-03-R16, 확장-03-R17, 확장-03-R18 | §3·5·6·8 상한·재시도·부분 결과 |
| 확장-03-R15 (Activity) | 본 기능 외; Issue 장기 시계열은 ecosystem 소유 |

## 부록 A. 현재 구현 사실과 남은 선행 차이

기준: 작업 브랜치 `41e5e9f`, `origin/develop@6f4fe68`를 2026-09-11 확인했다.
이 부록은 코드 관찰이며 본문의 목표 구현과 구분한다.

| 영역 | 확인 사실 / 근거 |
|---|---|
| DB | V1~V4 존재, community table 없음; backend/src/main/resources/db/migration |
| backend | Java 21 / Boot 4.0.8 / MVC / JdbcTemplate 명시 SQL; backend/build.gradle, PackageQueryRepository.java |
| API | /api package 조회 6개, success/data, snake_case; PackageController.java, application.yaml |
| frontend | React 19 / Router 7 / Query 5, ecosystem/features 두 lazy tab; package.json, report-page.tsx |
| route | state.packages만 존재, 임시 report ID, 직접 진입 fixture; analyze-page.tsx, report-page.tsx |
| runtime | local/prod API mem_limit 1.6g; 운영 Swap 0은 AGENTS.md 기록 |
| seed | seed 3개·reset/clear 2개 중 package 초기화는 4개 |
| CI | GitLab CI 설정 없음, integrationTest는 build와 별도 |

community endpoint·DB migration·npm/GitHub/GMS client·registry·scheduler·frontend tab·연결 설정은 아직 없다.
Jira 137 완료나 과거 MR !90·!91 병합만으로 community가 구현됐다고 보지 않는다.
이전 212·213 상태 기록은 조회 시점의 기록이지 실시간 완료 보장이 아니다.

선행 차이: 후보 화면 최대 2개, analyze-page.tsx 미정의 setError, route basePackage 없음,
직접 진입 fixture, POST query/caller signal 미지원, 탭 unmount의 filter 초기화.
community 범위의 문맥/통신/탭 보존은 본문에서 구현하고 나머지는 별도 결함으로 추적한다.

## 부록 B. 결정·이력·허용 한계

- 충돌 우선순위: 사용자의 최신 확정 지시 → AI 결정 문서 → 현행 기획.
  구현 코드는 현재 사실의 근거이고 공식 외부 문서는 외부 API 사실의 근거다. 외부 API 동작을 제품 우선순위로 덮어쓰지 않는다.
- `DEC-COMMUNITY-20260909-01`: 기준 하나, fallback 금지, 단일 snapshot, bounded Spring→GMS 예외.
- 9월 8일 원문 보존 commit: `1b60139`. 이전 최신화: `2648950`, 재검수: `41e5e9f`.
- 원문의 2026-09-20 일정은 보관 이력이며 현재 완료일로 약속하지 않는다.
- 이전 과정은 [284 worklogs](../worklogs/S15P21A506-284/), 이번 과정은 [307 worklogs](../worklogs/S15P21A506-307/)에 남긴다.
- v1은 단일 인스턴스 in-memory 진행/cooldown이므로 재시작 시 잃고 다중 인스턴스 중복 수집을 막지 못한다.
- raw 미보존으로 삭제/편집 source의 장기 감사와 모든 요약 문장의 재현은 보장하지 않는다.
- root package 일치와 PACKAGE_SCOPED는 주제별 Issue 연결의 증명이 아니다.
- GitHub 검색/댓글 다중 요청은 원자 snapshot이 아니고 동시 변경을 모두 감지하지 못한다.
- 캐시 TTL 동안 repository 변경이 늦게 반영될 수 있다. 별도 검증 cache·이력 table·분산 lock은 추가하지 않는다.
- 180/365일·Issue 2·댓글 100·20초 및 본문 자원 상한은 v1 기본값이다. 변경 시 계약/fixture/운영 예산을 함께 갱신한다.

## 부록 C. 외부 사실 근거

2026-09-11 확인. 구현 시에도 외부 버전 만료 여부를 다시 확인한다.

- [GitHub REST API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions):
  `2026-03-10` 지원. GitHub client는 Accept, 고정 User-Agent, 최소 권한 token, X-GitHub-Api-Version을 명시한다.
- [GitHub Search API](https://docs.github.com/en/rest/search/search):
  Issue 검색, comments 정렬, incomplete_results와 검색 budget.
- [GitHub Issue comments API](https://docs.github.com/en/rest/issues/comments):
  Issue별 댓글 오름차순과 page/per_page. repository 전체 comments endpoint의 sort 옵션과 혼동하지 않는다.
- [GitHub Contents API](https://docs.github.com/en/rest/repos/contents):
  package.json 조회·인코딩·파일/symlink 처리 경계.
- [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api):
  primary/secondary와 Retry-After/reset 준수.
- [npm registry API](https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md):
  package latest metadata 조회.
