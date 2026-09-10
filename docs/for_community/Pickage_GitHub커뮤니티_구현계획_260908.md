# Pickage GitHub 커뮤니티 현황 구현 계획

작성일 2026-09-08 · 최신 업그레이드 2026-09-09
(구조화 진행 화면 확정, 담당 작업 구체화, MR !90·!91·!92 병합 예정 기준과 단일 결과 테이블 반영)

이 문서는 실행 전 계획서다. 본문에는 현재 유효한 결정과 개발 계획만 두고, 수정 경위와
검수 기록은 부록에 둔다.

---

## 요약 정리

### 한눈에 보는 개발 방식

사용자가 비교할 패키지를 확정하면 서버는 **기준 패키지 하나의 커뮤니티 자료 수집을 뒤에서 시작**한다. 보고서 이동은 기다리지 않는다. 수집 중 커뮤니티 탭에는 저장소 확인, 이슈 검색, 댓글 수집, 요약 같은 실제 진행 단계를 안내하고, 완료되면 같은 자리에서 결과 화면으로 바꾼다.

서버는 Pickage 데이터베이스의 패키지 이름과 저장소 후보, npm의 공식 저장소 정보, GitHub의 이슈·댓글·작성자 관계·댓글 수·반응 수를 사용한다. 저장소를 확인한 뒤 최근에도 활동이 있는 이슈를 최대 2개 고르고, 이슈마다 최신 댓글을 최대 100개까지 가져온다. 저장소가 확실하지 않으면 비슷한 다른 저장소 자료로 대신하지 않는다.

요약 모델은 이슈 제목·본문·댓글을 받아 한국어 제목, 상황 요약, 논의 흐름, 대표 메시지를 이슈당 최대 3개 만든다. 서버는 모델이 고른 대표 메시지가 실제 원문에 있는지 검증하고, 작성자 역할·개수·시각은 GitHub 원본으로 직접 계산한다.

진행 단계와 실패 이유는 서버가 잠시 보관한다. 수집과 검증이 끝나기 전의 중간 자료는 데이터베이스에 저장하지 않는다. 화면에 제공할 수 있는 결과만 `community_snapshot` 한 테이블에 저장하며, 선택된 이슈와 대표 메시지는 검증이 끝난 JSON 한 묶음으로 넣는다. 원문 댓글과 계산 가능한 합계·역할·만료 시각은 별도 컬럼으로 만들지 않는다.

커뮤니티 탭을 열면 서버는 이 행 하나를 읽어 상단 통계와 이슈·대표 메시지 화면을 조립한다. 완료 후 24시간까지는 그대로 재사용하고, 이후에는 새로 수집한다. 갱신이 실패해도 수집 후 7일 이내의 이전 결과는 수집 시각과 함께 보여주며, 사용할 결과가 없을 때만 실패 이유를 안내한다.

더 자세한 내용: [수집·선정 기준](#저장소와-issue) · [데이터베이스 저장 구조](#데이터베이스) · [API 동작과 응답](#api) · [화면 동작](#코드와-화면) · [구현 순서](#실행-계획) · [검증 방법](#테스트-전략)

### 팀별로 실제 해야 할 일

- **인프라 담당**: !91과 그 위의 !90이 develop에 순서대로 병합된 뒤 최신 develop에서 작업한다. `GITHUB_COMMUNITY_TOKEN`, `GMS_API_KEY`, `GMS_BASE_URL`, `GMS_MODEL`을 운영 secret에 등록하고, 루트 `.env.example`, `compose.yaml`의 backend environment, Spring `application.yaml`이 같은 이름을 사용하도록 연결한다. 실제 값은 백엔드 컨테이너에만 전달한다. 두 API 키가 없으면 운영 community 기능이 활성화되지 않는지, 호출 한도와 20초 작업 제한이 적용되는지 확인한다.
- **DB·ERD 담당**: !91 병합으로 중복 V2가 없어지고 `V4__index_similar_package.sql`이 생긴 것을 확인한다. 그 위에 기존 `package`와 연결되는 `community_snapshot` 테이블 **하나만** ERD와 `V5__community.sql`에 추가한다. !90이 추가하는 세 번째 로컬 시드까지 포함해 세 시드가 community 결과를 먼저 비우도록 갱신하되, community 가짜 결과를 넣지는 않는다. 기존 V1~V4는 고치지 않으며 정확한 6개 컬럼과 제약은 [데이터베이스 저장 구조](#데이터베이스)를 따른다.
- **프론트엔드 담당**: `frontend/src/routes/report/community/`에 탭·진행·결과 구성요소를 만들고 `report-page.tsx`에 세 번째 lazy 탭을 연결한다. 분석 확정 시 수집 POST를 뒤에서 보내고, 탭을 열면 POST로 작업을 보장한 뒤 GET을 주기적으로 호출한다. 서버의 안내 문구를 보여주다가 완료 시 같은 영역을 결과로 바꾸고, 이전 결과 갱신 중·부분 결과·자료 없음·실패를 각각 처리한다. mock 모드에서는 공개 fixture만 읽고 외부 서비스를 호출하지 않는다.

### 담당별 빠른 안내

| 담당 | 완료해야 하는 결과 | 문서 바로가기 |
|---|---|---|
| 인프라 담당 | 네 가지 외부 연동 설정을 백엔드 실행 환경에 주입하고 비노출·호출 제한 확인 | [설정과 보안](#설정과-보안) · [관측과 운영 인계](#관측과-운영-인계) |
| DB·ERD 담당 | migration 번호를 정리하고 6개 컬럼의 `community_snapshot` 한 테이블 추가 | [현재 위치와 구현](#현재-위치와-구현) · [데이터베이스](#데이터베이스) · [DB 변경과 초기 데이터](#migration과-seed) |
| 동료 백엔드 검토자 | 수집 정책, 결과 JSON 검증, API 상태, 원자적 교체와 테스트 범위 검토 | [API](#api) · [백엔드](#백엔드) · [실행 계획](#실행-계획) · [테스트 전략](#테스트-전략) |
| 프론트엔드 담당 | 탭·진행 화면·결과 화면·상태별 예외 화면과 mock 연결 | [엔드포인트와 응답](#엔드포인트와-응답) · [프론트엔드](#프론트엔드) · [API와 화면 검증](#api와-화면-검증) |

---

## 배경

### 현재 위치와 구현

커뮤니티는 확장-03이며 일정표상 2026-09-20 목표다. 그러나 v1 API 결정사항과 API 현황에는
아직 등록되지 않아 착수 전에 Jira·Notion 계약을 동기화해야 한다.

현재 프론트에는 ecosystem/features 두 탭만 있고 community 폴더가 없다. 최신 원격 develop에는
PackageController와 공통 wrapper 해제·`message` 오류 처리·전역 snake_case·mock endpoint 분기가
이미 구현돼 있다. community는 이 기반을 재사용하고 `msg→message`나 wrapper 해제를 다시 구현하지
않는다. 다만 공통 `get()`에는 요청별 `signal` 옵션이 아직 없으므로 진행 상태 조회 취소를 위한
작은 확장이 필요하다.

현재 원격 develop에는 V2가 두 개지만, 병합 예정 MR이 구현 기준을 이미 정리했다.

- [!91](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/91): 중복
  `V2__index_similar_etl.sql`을 제거하고 필요한 인덱스와 `similar_package`만
  `V4__index_similar_package.sql`로 옮긴다. develop에 먼저 병합한다.
- [!90](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/90): !91 브랜치를
  대상으로 한 후속 MR이다. 스키마는 바꾸지 않고 로컬 목업용 `seed_service_full.sql`과 사용 설명을
  추가하므로 !91 다음에 develop으로 병합한다.
- [!92](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/92):
  `removal_by_year` 행 수와 MinIO 경로를 고치는 문서 MR이며 community DB·API·화면에는 영향이 없다.

이 계획의 착수 기준은 세 MR이 병합된 develop이다. 그 기준에서 마지막 migration은 V4이므로
community는 `V5__community.sql`을 사용한다. 이후 다른 migration이 먼저 추가된 경우에만 다시 다음
빈 번호를 확인하며, 이미 적용된 V1~V4의 이름이나 내용은 수정하지 않는다.

Figma 기준은 wrapper 485:828과 활성 콘텐츠 485:936이다. community 시각 QA는 485:936을
기준으로 한다. 공통 Header·PDF·탭 shell 차이는 별도 공통 UI 작업으로 추적한다.

---

## 설계

### 저장소와 Issue

#### 저장소 연결 검증

`package.repo_url`은 Curated가 네트워크 호출 없이 정리한 후보일 뿐이다. npm latest metadata의 `repository`가 문자열이면 그 값을, 객체이면 `repository.url`과 선택적 `repository.directory`를 읽는다. DB 후보와 npm 후보를 각각 정규화해 최종 후보를 고른 뒤 host 허용 목록을 다시 검사한다. npm이 GitLab을 가리키는데 DB에 GitHub 주소가 있다는 이유로 GitHub 수집을 진행하지 않는다.

**저장소 후보 결정**

| 상황 | 판정 |
|---|---|
| DB·npm이 같은 GitHub 저장소 | 해당 저장소로 진행 |
| 서로 다르고 npm이 GitHub | npm 후보로 진행하되 충돌 사실을 구조화 로그에 남김 |
| DB만 GitHub 또는 npm에 repository 없음 | 저장소 루트의 package.json 이름이 요청 이름과 같을 때만 진행 |
| npm만 GitHub | npm 후보로 진행 |
| 최종 후보가 GitHub 외 host | `UNSUPPORTED_HOST`, 수집 중단 |
| npm 조회 404 | 패키지 identity 재확인 후 `UNVERIFIED_REPOSITORY` |
| npm/GitHub 네트워크 오류·429·rate-limit 403 | `FETCH_LIMITED`, 저장소 오류로 단정하지 않음 |
| GitHub 404 또는 접근 불가 403 | rate-limit과 구분해 `UNVERIFIED_REPOSITORY` |

후보 주소와 검증 과정은 수집 중 메모리와 구조화 로그에서만 사용한다. 데이터베이스에는 최종 `owner/repo`, 귀속 범위, 화면에 필요한 제한 사유만 결과 JSON에 남긴다. GitHub API 경로는 검증된 최종 `owner/repo`로만 조립한다.

**패키지 연결과 Issue 귀속 범위**

| GitHub 확인 | 연결 결과 | Issue 범위 |
|---|---|---|
| npm directory의 package.json 이름 일치 | 패키지-저장소 연결 확인 | `REPOSITORY_WIDE` — 저장소 전체 이슈가 그 directory 전용이라는 증거는 아님 |
| directory 없음, 루트 package.json 이름 일치 | 연결 확인 | `PACKAGE_SCOPED` |
| directory 없음, 루트 이름 불일치 | 저장소 연결만 확인 가능 | `REPOSITORY_WIDE`로 제공하고 한계 표시 |
| directory 경로 없음 또는 이름 불일치 | 연결 불명확 | `AMBIGUOUS`, 이슈 조회 중단 |

v1은 label·경로·본문 키워드로 이슈를 패키지별 필터링하지 않는다. 확인된 monorepo를 `PACKAGE_SCOPED`로 과장하지 않는다. 저장소가 archived 상태면 검증 실패로 바꾸지 않고 결과 JSON의 `limitations`에 보관 상태임을 남긴다. provenance·gitHead·tag/commit 대조는 v1 필수 조건으로 쓰지 않는다.

별도 저장소 검증 캐시는 두지 않는다. 완성 결과를 24시간 재사용하므로 그 안의 npm metadata나 DB 저장소 주소 변경은 최대 24시간 늦게 반영될 수 있다. 이 단순화를 v1 허용 범위로 두고, 즉시 무효화용 후보 주소·fingerprint 컬럼은 만들지 않는다.

#### Issue 정책

저장소 범위가 모호하거나 미검증이면 이슈를 조회하지 않고 다른 후보 패키지 자료로 자동 대체하지 않는다.

초기 이슈 정책 `github-active-v1`:

- `repo:owner/repo is:issue`, 최근 180일 갱신
- 댓글 수 내림차순, 동률이면 갱신 시각과 이슈 번호 내림차순
- 최대 2건, 결과가 없으면 365일로 한 번 확장
- 검색 응답이 불완전하면 `PARTIAL`과 `SEARCH_INCOMPLETE` 제한을 남김
- 열린 이슈와 닫힌 이슈를 모두 허용하고, 열린 이슈 수는 선택된 결과에서 계산
- GitHub Search가 고른 상위 30건 안에서만 동률을 재정렬
- 잠긴 이슈와 Bot이 작성한 이슈는 후보에서 제외
- 선택된 이슈의 Bot 댓글은 대표 메시지 후보에서만 제외하고 전체 댓글 수에는 포함
- 정책을 바꾸면 코드의 결과 형식 버전과 고정 fixture를 함께 올림

댓글은 이슈당 **최신 100개**를 수집한 뒤 원래 작성 시각 순으로 복원한다. 댓글 API의 마지막 page를 Link header로 교차 확인하고, 최대 3회 호출 안에서 ID가 큰 최신 100개만 남긴다. 호출 사이 댓글 증감이나 일부 page 실패로 끝을 확정하지 못하면 해당 topic의 `collection_status`를 `TRUNCATED` 또는 `FAILED`로 두고 결과의 `limitations`에 이유를 남긴다.

대표 메시지는 **이슈당 최대 3개**다. 이슈 본문과 수집 댓글 원문은 요약·검증이 끝날 때까지만 메모리에 보관하고 DB와 공개 API에는 저장하지 않는다. DB에는 화면에 표시할 대표 메시지의 요약, 작성자, 원천 관계, 작성 시각만 결과 JSON의 topic 아래에 넣는다.

작성자 역할은 JSON에 계산 결과를 저장하지 않고 조회 때 아래처럼 만든다. 댓글 작성자가 이슈
작성자와 같으면 `ISSUE_AUTHOR`가 최우선이다. 그 외에는 GitHub 원천 값을 의미를 바꾸지 않고
OWNER→`REPOSITORY_OWNER`, MEMBER→`ORGANIZATION_MEMBER`, COLLABORATOR→`COLLABORATOR`,
CONTRIBUTOR→`CONTRIBUTOR`로 옮긴다. FIRST_TIMER·FIRST_TIME_CONTRIBUTOR·MANNEQUIN·NONE·결손은
현재 화면 역할로 추측하지 않고 null로 둔다. `USER_SOLUTION`은 작성자 역할이 아니라 메시지 종류다.

요약 입력은 이슈 원제목을 항상 포함하고, 원문 하나당 4,000자·이슈 전체 48,000자를 초기 상한으로 둔다. 이슈 본문을 먼저 포함한 뒤 최신 댓글부터 남은 예산에 넣고, 모델에 보낼 때는 본문 다음 댓글 작성 시각 순으로 복원한다. 절단이나 제외가 생기면 개별 계수 컬럼을 만들지 않고 `SUMMARY_INPUT_LIMITED` 제한만 결과 JSON에 남긴다. 구체적인 입력량과 모델·prompt 버전은 원문 없이 구조화 로그에서 관측한다.

### 데이터베이스

#### 저장 구조 결정

커뮤니티 결과는 이슈별 검색이나 장기 이력 분석용 원천 데이터가 아니라, **패키지 하나의 최신 화면 결과를 통째로 저장하고 통째로 읽는 7일짜리 조회 자료**다. 따라서 이슈와 메시지를 별도 관계형 테이블로 나누지 않고 `community_snapshot` 한 테이블만 추가한다. PostgreSQL의 JSONB는 기존 ERD의 JSON 계열 컬럼 사용 방식과도 맞는다.

#### community_snapshot

| 컬럼 | 타입 | 제약 | 저장 이유 |
|---|---|---|---|
| package_id | INT | PK, FK→package(package_id), ON DELETE CASCADE | 패키지마다 최신 결과 한 건만 보관 |
| snapshot_id | UUID | NOT NULL, UNIQUE | 응답 버전 식별과 동시 갱신 결과 구분 |
| payload_version | SMALLINT | NOT NULL, CHECK > 0 | 배포 후 오래된 JSON을 안전하게 판별 |
| collected_at | TIMESTAMPTZ | NOT NULL | 24시간 재사용·7일 제공·정리 시각의 기준 |
| data_status | VARCHAR(30) | NOT NULL, 허용값 CHECK | 결과 제공 가능·부분 제공·저장소 미확인·논의 없음 구분 |
| result | JSONB | NOT NULL, JSON object CHECK | 저장소 정보, 이슈 최대 2개, 논의 흐름, 대표 메시지, 제한 사유 |

`data_status` 허용값은 `AVAILABLE`, `PARTIAL`, `UNVERIFIED_REPOSITORY`, `AMBIGUOUS_SCOPE`, `UNSUPPORTED_HOST`, `NO_DISCUSSION_DATA`다. 일시적인 외부 호출 실패와 진행 중 상태는 완성 결과가 아니므로 테이블에 저장하지 않는다.

`result`에는 다음 자료만 넣는다.

- 최종 저장소 식별자와 패키지 귀속 범위
- 선택 이슈의 번호·작성자 로그인·상태·제목·한국어 제목·갱신 시각·전체 댓글 수·반응 수
- 이슈별 수집 상태·요약 상태·한국어 요약·논의 흐름
- 화면에 표시할 대표 메시지의 원천 ID·작성자·GitHub 원천 관계·작성 시각·종류·한국어 요약
- 검색 불완전, 댓글 100개 초과, 입력 절단, 저장소 전체 범위, archived 같은 제한 코드

서버는 저장 전 전용 DTO로 JSON 구조, 배열 상한, 문자열 길이, enum, source ID 소속을 검증한다. `result`를 Entity의 임의 Map으로 직접 수정하지 않고 직렬화·역직렬화 계약 테스트를 둔다.

#### 컬럼으로 만들지 않는 값

| 값 | 처리 위치 |
|---|---|
| `fresh_until`, `serve_until` | `collected_at`과 서버 설정의 24시간·7일을 더해 응답에서 계산 |
| 전체 요약 상태와 상단 이슈·댓글·반응·열린 이슈 수 | JSON의 topic을 읽어 서버에서 계산 |
| 작성자 표시 역할 | 저장된 GitHub `author_association`을 서버 매핑표로 변환 |
| 이슈 표시 순서와 대표 메시지 순서 | 확정된 정렬 규칙으로 서버에서 정렬 |
| DB/npm 후보 주소·검증 방식·npm 버전 | 수집 중 판단하고 민감하지 않은 결과만 구조화 로그에 기록 |
| 모델·prompt·입력 길이·정책 버전 | 운영 로그와 배포 버전으로 추적 |
| 원문 본문·댓글·원문 hash·요약 근거 ID 목록 | 저장 전 메모리에서 검증한 뒤 폐기 |
| 이슈·메시지용 별도 테이블과 FK | 한 번에 읽고 교체하는 `result` JSON 안에서 표현 |

이 구조는 기존 3테이블 설계의 68개 물리 컬럼을 1테이블 6개 컬럼으로 줄인다. 이슈별 검색, 장기 이력, 원문 감사가 실제 제품 요구가 되면 그때 이력·원천 테이블을 별도로 추가한다. 현재 화면 조회만을 위해 미리 만들지 않는다.

#### 게시와 읽기

외부 수집·요약·검증은 DB 트랜잭션 밖에서 끝낸다. 게시할 때만 짧은 트랜잭션을 열고
`SET LOCAL lock_timeout='2s'`, `statement_timeout='5s'`를 잠금보다 먼저 적용한다. 그다음 package별
transaction advisory lock을 얻고 `INSERT ... ON CONFLICT (package_id) DO UPDATE`로 한 행을 교체한다.
실패하면 rollback되어 이전 행이 그대로 남는다. 한 행 교체이므로 자식 테이블 삭제 순서, JPA flush
순서, 반복 읽기 격리 수준은 별도 처리하지 않는다.

조회는 package_id로 한 행을 읽고 JSON을 DTO로 변환한 뒤 통계·역할·순서·만료 시각을 계산한다. 읽는 동안 다른 요청이 갱신해도 단일 행은 갱신 전 또는 갱신 후 값 하나로만 보이므로 서로 다른 snapshot의 자료가 섞이지 않는다.

다중 인스턴스의 수집 중복 방지는 v1 범위에 넣지 않는다. 게시 충돌은 DB 잠금으로 막되 외부 API 중복 호출까지 막아야 하는 시점에는 job lease를 별도 설계한다.

#### migration과 seed

!91과 !90 병합 후 최신 develop을 받는다. migration 목록이 V1·V2·V3·V4 각각 하나인지와 Flyway
기동을 확인한 뒤 `V5__community.sql`을 만든다. 여기에는 `community_snapshot` 한 테이블,
data_status·JSON object CHECK, package FK, snapshot_id UNIQUE, `collected_at` 정리용 인덱스만 작성한다.
다른 migration이 먼저 병합된 경우에만 그 시점의 다음 빈 번호로 바꾼다.

과거 `V2__index_similar_etl.sql`을 이미 적용한 개인 로컬 DB는 !91 안내대로 로컬 PostgreSQL volume을
재생성한 뒤 V1~V4를 다시 적용한다. 이는 복구 가능한 로컬 목업 DB에만 해당하며 서버·Curated DB를
삭제하거나 Flyway repair로 억지 통과시키지 않는다.

!91이 `seed_sample.sql`과 `seed_mock_parity.sql`의 snapshot 초기화를 TRUNCATE에서 DELETE로 고친
내용은 되돌리지 않는다. !90 병합 후에는 로컬 시드가 다음 세 벌이 된다.

- `deploy/local/seed/seed_sample.sql`
- `deploy/local/seed/seed_mock_parity.sql`
- `deploy/local/seed/seed_service_full.sql`

세 파일 모두 `package`를 TRUNCATE하기 전에 `community_snapshot`을 함께 TRUNCATE하도록 갱신한다.
PostgreSQL은 FK를 참조하는 테이블이 비어 있어도 이를 함께 지정하지 않으면 package TRUNCATE를
거절하기 때문이다. community 결과는 외부 수집 상태를 시험하는 자료이므로 세 시드에 가짜 행을
INSERT하지 않고, 백엔드 fixture와 프론트 mock으로 검증한다.

실제 Curated 적재 DB에서는 어떤 로컬 시드나 TRUNCATE도 실행하지 않는다. 빈 DB 전체 migration,
기존 DB upgrade, Hibernate validate는 격리된 테스트 DB에서 확인한다.

정리 작업은 서버가 계산한 `현재 시각 - 7일`보다 `collected_at`이 오래된 행을 매시간 최대 500개 삭제한다. 제공 가능 여부도 같은 기준으로 먼저 판정하므로 정리 작업이 늦어져도 만료 결과를 반환하지 않는다.

### API

#### 엔드포인트와 응답

명령과 조회를 분리한다.

- `POST /api/packages/community/refresh?name=pino&trigger=ANALYSIS_CONFIRMED`: 분석 확정 직후 여유가 있을 때만 사전 수집을 시작한다.
- `POST /api/packages/community/refresh?name=pino&trigger=TAB_OPENED`: 탭을 연 사용자의 수집을 시작하거나 이미 실행 중인 같은 작업에 참여한다.
- `GET /api/packages/community?name=pino`: 현재 진행 상태, 마지막 실패 또는 저장된 결과만 읽는다. GET은 새 수집을 시작하지 않는다.

POST는 새 작업을 수락하면 202, 이미 신선한 결과가 있거나 같은 작업 참여·용량 초과이면 200을 반환한다. 두 메서드는 기존 `success/data` wrapper와 snake_case를 사용한다. 용량 초과는 예상 가능한 상태이므로 이전 결과가 없으면 `view_status=FAILED`, 있으면 이전 결과와 함께 표시한다.
단, 전체 요약 상태가 FAILED인 결과는 5분 쿨다운이 지나면 신선하더라도 새 POST를 수락한다.

community DTO에만 `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)`를 적용한다. 프론트 adapter는 wire DTO를 camelCase view model로 변환한다. 기존 wrapper 해제·message 오류 처리·전역 설정은 다시 구현하지 않는다.

**진행 중 조회 예시**

```json
{
  "success": true,
  "data": {
    "package_name": "pino",
    "view_status": "PROCESSING",
    "freshness": null,
    "refresh": {
      "refresh_id": "6494ba6a-bafd-46f0-8f59-f3ace5d779c5",
      "status": "RUNNING",
      "stage": "COLLECTING_DISCUSSIONS",
      "stage_message": "핵심 이슈의 공개 댓글을 확인하고 있습니다.",
      "started_at": "2026-09-09T02:11:10Z",
      "last_updated_at": "2026-09-09T02:11:18Z",
      "poll_after_seconds": 2,
      "retry_at": null,
      "error_code": null
    },
    "result": null
  }
}
```

진행 중과 최초 실패에는 가짜 snapshot이나 빈 topics를 넣지 않는다. `result=null`은 아직 게시 결과가 없다는 뜻이다. `stage_message`는 서버 단계 enum의 고정 한국어 매핑이다.

**저장 결과가 없는 실패 예시**

```json
{
  "success": true,
  "data": {
    "package_name": "pino",
    "view_status": "FAILED",
    "freshness": null,
    "refresh": {
      "refresh_id": "6494ba6a-bafd-46f0-8f59-f3ace5d779c5",
      "status": "FAILED",
      "stage": "SEARCHING_ISSUES",
      "stage_message": "GitHub 요청 제한으로 분석을 완료하지 못했습니다.",
      "started_at": "2026-09-09T02:11:10Z",
      "last_updated_at": "2026-09-09T02:11:14Z",
      "poll_after_seconds": null,
      "retry_at": "2026-09-09T02:16:14Z",
      "error_code": "GITHUB_RATE_LIMITED"
    },
    "result": null
  }
}
```

**성공 응답 예시**

```json
{
  "success": true,
  "data": {
    "package_name": "pino",
    "view_status": "RESULT",
    "freshness": "FRESH",
    "refresh": {
      "refresh_id": "6494ba6a-bafd-46f0-8f59-f3ace5d779c5",
      "status": "COMPLETED",
      "stage": "PUBLISHING",
      "stage_message": "커뮤니티 분석이 완료되었습니다.",
      "started_at": "2026-09-09T02:11:10Z",
      "last_updated_at": "2026-09-09T02:11:28Z",
      "poll_after_seconds": null,
      "retry_at": null,
      "error_code": null
    },
    "result": {
      "snapshot_id": "7b1f9a24-cb1f-44e1-9af1-b0ab9ca62b75",
      "collected_at": "2026-09-09T02:11:28Z",
      "fresh_until": "2026-09-10T02:11:28Z",
      "serve_until": "2026-09-16T02:11:28Z",
      "data_status": "AVAILABLE",
      "summary_status": "READY",
      "repository": {
        "identifier": "pinojs/pino",
        "scope": "PACKAGE_SCOPED"
      },
      "summary": {
        "analyzed_issue_count": 1,
        "comment_count": 30,
        "reaction_count": 3,
        "open_issue_count": 1
      },
      "topics": [
        {
          "issue_number": 2272,
          "issue_state": "OPEN",
          "issue_updated_at": "2026-05-15T10:55:48Z",
          "title": "[Feature Request] Can pass a module NOT STRING to pino transport target?",
          "title_ko": "transport target에 모듈을 직접 전달할 수 있을까?",
          "comment_count": 30,
          "reaction_count": 3,
          "collection_status": "COMPLETE",
          "summary_status": "READY",
          "summary_ko": "transport target의 모듈 전달과 번들러 호환성에 관한 논의입니다.",
          "discussion_flow": [
            { "step_order": 1, "text_ko": "Node.js와 worker thread 제약을 확인했습니다." }
          ],
          "messages": [
            {
              "author_login": "mcollina",
              "author_role": "ORGANIZATION_MEMBER",
              "message_kind": "NORMAL",
              "source_created_at": "2025-10-05T07:25:06Z",
              "summary_ko": "worker thread에서 모듈을 불러오는 제약을 설명합니다."
            }
          ]
        }
      ],
      "limitations": [],
      "data_limits": {
        "max_issue_count": 2,
        "max_comments_per_issue": 100
      }
    }
  }
}
```

DB의 JSON에는 repository, topics, limitations만 저장한다. snapshot_id·collected_at·data_status는 테이블 컬럼에서 넣고, fresh_until·serve_until·summary·summary_status·author_role·data_limits는 서버가 계산해 위 응답을 만든다.

**필드 규약**

| 규약 | 내용 |
|---|---|
| 시각 | 모두 UTC ISO 8601 `Z`; 화면의 지역 시각 변환은 프론트 책임 |
| 이슈 식별 | 화면과 응답은 저장소 안의 `issue_number`만 사용 |
| `source_id` | 모델 출력 검증과 저장 JSON의 대표 메시지 식별에만 쓰고 공개 응답에서는 제거 |
| `result` | 진행 중·최초 실패면 `null`; 게시 결과가 있으면 object |
| 배열과 nullable | 배열은 항목이 없으면 `[]`; 요약 실패 시 한국어 요약은 `null` |
| 통계 | topics의 값을 서버에서 합산하며 JSON에 중복 저장하지 않음 |
| 역할 | JSON의 GitHub 원천 관계를 서버에서 표시 역할로 바꾸며 확인되지 않으면 `null` |
| 순서 | topics는 댓글 수→갱신 시각→번호 순, messages는 원 작성 시각→source ID 순으로 서버 정렬 |
| 만료 시각 | collected_at과 서버 설정으로 계산하고 DB에 중복 저장하지 않음 |
| 미노출 | package_id, 원문, 내부 검증용 source ID, 외부 API 응답 원형 |

#### 상태와 오류

`view_status`는 PROCESSING/RESULT/FAILED, `freshness`는 결과가 있을 때 FRESH/STALE이다. `refresh.status`는 NOT_STARTED/QUEUED/RUNNING/COMPLETED/FAILED/CAPACITY_LIMITED다. 저장 행의 `data_status`는 AVAILABLE/PARTIAL/UNVERIFIED_REPOSITORY/AMBIGUOUS_SCOPE/UNSUPPORTED_HOST/NO_DISCUSSION_DATA다. 전체 `summary_status`는 topic별 READY/PARTIAL/FAILED/SKIPPED를 서버가 합산한다.

| 상황 | 화면 |
|---|---|
| 결과 없이 QUEUED·RUNNING | 구조화 진행 카드와 현재 단계 문구 |
| FRESH AVAILABLE·READY | 전체 결과 |
| FRESH AVAILABLE·FAILED/SKIPPED | GitHub 사실 값과 요약 실패·대상 없음 안내 |
| FRESH 또는 STALE 결과를 갱신 중 | 기존 결과를 유지하고 위에 작은 갱신 진행 카드 |
| PARTIAL | 성공한 내용과 limitations의 수집·입력 한계 |
| NO_DISCUSSION_DATA | 조건에 맞는 논의가 없다는 안내 |
| UNVERIFIED·AMBIGUOUS·UNSUPPORTED | 제공 불가 이유, 다른 저장소로 대체하지 않음 |
| 이전 결과가 있는 갱신 실패 | 7일 안의 이전 결과·수집 시각·실패 이유·재시도 시각 |
| 이전 결과 없는 실패 | 실패 이유·재시도 시각·수동 재시도 |

프로토콜·검증 오류는 기존 `success/code/message` 계약을 사용한다.

| 상황 | HTTP | 처리 |
|---|---|---|
| stale·부분 결과·요약 실패·저장소 미확인 | 200 | 상태 필드로 표현 |
| name 또는 trigger 누락 | 400 | 기존 `REQUIRED_PARAM_MISSING` |
| name 형식 또는 trigger 값 오류 | 400 | 기존 `INVALID_VALUE_FORMAT` |
| package 없음 | 404 | 기존 `RESOURCE_NOT_FOUND` |
| 이전 결과 없음 + 외부 수집 실패 | 200 | `view_status=FAILED`, `result=null` |
| 서버 내부 오류 | 500 | 기존 `INTERNAL_ERROR` |

공개 실패 코드는 `GITHUB_RATE_LIMITED`, `GITHUB_UNAVAILABLE`, `NPM_UNAVAILABLE`, `GMS_UNAVAILABLE`, `REFRESH_DEADLINE_EXCEEDED`, `PUBLISH_FAILED`, `CAPACITY_LIMITED`, `LOCAL_RATE_LIMITED`로 제한한다. 내부 예외명·URL·키는 응답에 넣지 않는다. 일시적 실패는 DB 결과를 덮어쓰지 않으며, `retry_at` 이후 사용자의 POST로 다시 시도한다.

진행 중/정상/정상 빈 결과/부분 수집/요약 실패/stale/수집 전면 실패 fixture를 둔다. 백엔드는 수집 원천 fixture로 검증된 JSON과 공개 응답을 생성해 계약 테스트하고, 프론트 mock에는 공개 응답만 넣는다. query key는 `['packages','community', name]`이다. `refresh.status=QUEUED/RUNNING`일 때만 서버의 `poll_after_seconds`로 조회하며, GET 전송 오류만 최대 2회 재시도한다. POST와 업무상 실패는 자동 재시도하지 않는다.

### 코드와 화면

#### 백엔드

백엔드는 controller/service, bounded RefreshTaskRegistry와 coordinator, DTO, community_snapshot
Entity·repository, GitHub·npm·GMS client, 저장소/Issue/role policy, summarizer/output validator로
분리한다. JSONB는 임의 Map이 아니라 타입이 정해진 payload DTO로 변환하며 Entity·외부 DTO·저장
payload·API DTO를 공유하지 않는다. 진행 stage 전이는 coordinator 한 곳에서만 하고 controller는
POST 명령과 GET 상태 조회만 연결한다. summarizer는 GMS 입력·출력만 다루고, 작성자·역할·시각·순서·
집계 수치는 output validator 이후 서버가 원본 record와 저장 payload에서 조립한다.

`RefreshAdmissionCoordinator`가 refresh start token bucket, 동시 실행 permit 2개와 interactive 전용
4칸 deque를 직접 소유한다. 기존 task/fresh cache를 먼저 확인하고 새 전체 refresh만 token을 예약한다.
ANALYSIS_CONFIRMED는 token 또는 `tryAcquire` 실패 시 즉시 해당 제한 상태이고, TAB_OPENED는 token을
예약한 뒤 permit이 없을 때만 deque에 들어간다. 작업 종료는 `finally`에서 permit을 반환하고 가장 오래 기다린 interactive task를
하나 dispatch한다. 실제 executor는 고정 worker 2개와 무대기 handoff를 써서 라이브러리 내부의
unbounded queue가 문서의 상한을 우회하지 못하게 한다. registry 등록·permit/queue 입장·실패 제거는
coordinator의 한 임계구역에서 처리해 같은 package task가 둘 생기는 race를 막는다.

worker가 시작될 때 20초의 단일 deadline을 만들고 저장소 검증→이슈 검색→댓글 수집→GMS→DB 게시에
남은 시간을 계속 전달한다. 각 외부 요청 timeout은 설정값과 남은 시간 중 짧은 값으로 잡고, 시간이
끝나면 진행 중 요청을 취소하며 다음 단계를 시작하지 않는다. 20초가 충분한지는 운영 p95를 보고
조정하되 프론트 HTTP timeout만 늘려 백그라운드 작업이 계속 남게 만들지 않는다.

#### 프론트엔드

`frontend/src/routes/report/community/`에는 api, model, report-tab, progress-view, result-view, header, summary,
issue-card, discussion-thread, data-limits, sample을 둔다. report-page에는 세 번째 lazy tab과 기준
패키지를 연결한다. progress-view는 기능 비교의 구조화 진행 화면 패턴을 재사용하되 community의
실제 stage_message와 상태 조회 결과만 표시한다. RESULT가 되면 같은 report-tab 내부에서
result-view로 전환해 탭·URL·스크롤 상위 shell을 바꾸지 않는다.

현재 기능 비교의 `AnalysisProgress`는 시각 구조는 적합하지만 `useAnalysisRun`의 `STEP_MS` timer로
단계와 퍼센트를 흉내 낸다. community는 이 hook·`RUN_STEPS`·가짜 `doneCount`를 import하지 않는다.
별도 `CommunityProgressView`가 서버 stage 목록을 같은 카드·step·skeleton 형태로 렌더링하고,
상단에는 추정 퍼센트 대신 현재 `stage_message`와 `started_at` 기준 경과 시간만 표시한다. 현재 메시지는
`aria-live="polite"`로 알리고 spinner에는 대체 텍스트를 둔다. stale 결과가 있으면 기능 비교의
compactCard 패턴처럼 결과 위에 작은 진행 카드를 놓되 결과를 흐리거나 클릭 불가로 만들지 않는다.
완료 응답을 받은 렌더에서 progress와 community 전용 skeleton을 result-view로 원자적으로 바꾼다.

분석 확정 시점에는 기준 패키지 하나에 대해 `trigger=ANALYSIS_CONFIRMED` POST refresh를 비차단으로
시작한다. 이 POST 실패는
생태계 보고서 이동을 막지 않는다. 사용자가 탭을 열면 POST로 작업 존재를 보장한 뒤 GET query를
시작한다(`trigger=TAB_OPENED`). 두 호출은 endpoints.ts의 mock/real 분기를 따라야 하며
`VITE_USE_MOCK=true`에서는 실제
GitHub/GMS를 호출하지 않는다. 공통 client의 이미 구현된 wrapper unwrap·message 처리를 재사용한다.

**보고서 문맥 가드**: report 문맥(비교 대상 선택 상태) 없이 `/report/:reportId`에 직접 진입한 경우
mock 기본 비교 대상을 실제 분석 대상으로 쓰지 않는다 — 이는 커뮤니티가 만든 결함이 아니라
기존 mock report shell의 문제이지만, 이 경계에 커뮤니티가 연결되므로 정상 진입 흐름(입력→후보→
선택)에서 route state로 전달한 기준 패키지(`basePackage`, 없으면 순서를 보존한 `packages[0]`)가
있을 때만 커뮤니티
탭을 활성화하고, 그렇지 않으면 입력 화면으로 안내한다. 정렬된 비교 query key에서 기준 패키지를
역추론하지 않는다.
탭 hover 시에는 코드 청크만 prefetch하며 실제 GitHub/GMS 수집을 시작하지 않는다 — 실제 데이터
수집은 분석 확정 시점의 사전 요청과 탭 오픈 시점, 이 두 곳에서만 발생한다.

**Figma 참고 범위**: `485:936`(활성 community 콘텐츠) 안에는 공통 shell과 동일한
`574:303 / 00-report-shell` 레이어가 함께 들어 있다. 이 프레임 전체를 복제하지 않는다 — 실제
`community-view`가 조립할 범위는 `02-package-intro`부터 `05-discussion-threads`까지이며, 브랜드·
탭·PDF 등 공통 shell은 기존 React report shell을 그대로 재사용한다. 렌더링 결과 자체(공통 shell
1회만 표시)는 이미 확인됐으므로 이 문장은 레이어 복제 실수를 막기 위한 구현 지침이다. Figma에는
"자료 한계" 영역의 구체 화면이 아직 없으므로 위치(하단)·문구·상태 예시는 이 계획으로 확정한다.

#### 설정과 보안

외부 연동 설정은 `GITHUB_COMMUNITY_TOKEN`, `GMS_API_KEY`, `GMS_BASE_URL`, `GMS_MODEL` 네 가지다. 인프라 담당은 운영 secret에 등록하고 compose의 backend environment와 Spring `CommunityProperties`까지 연결한다. `.env.example`에는 실제 값이 아닌 변수 이름과 설명만 둔다. 프론트 환경 변수에는 넣지 않으며 운영 profile은 두 API 키가 없으면 community 기능을 활성화하지 않는다.

비밀이 아닌 기본값도 `CommunityProperties` 한 곳에 둔다: 동시 수집 2, 탭 대기 4, 전체 시작 10건/분·burst 4, 전체 예산 20초, 완료 작업 상태 보존 10분, 실패 쿨다운 5분, 조회 안내 2초, 결과 재사용 24시간, 결과 제공 7일, 이슈 2건, 댓글 최신 100개, 원문별 4,000자·이슈별 48,000자·출력 2,048 token. API의 만료 시각과 data_limits도 이 설정으로 계산한다.

GitHub 원문은 신뢰할 수 없는 입력이다. system 지시와 원문을 분리하고, raw HTML을 렌더링하지 않으며, 모델이 반환한 URL로 추가 수집하지 않는다. GitHub/GMS 키와 prompt·원문 전체는 로그에 남기지 않는다.

GMS는 이슈별로 다음 내부 형식만 반환한다.

```json
{
  "issue_number": 2272,
  "title_ko": "한국어 제목",
  "summary_ko": "쟁점 요약",
  "summary_support_source_ids": ["b-2272", "c-3368825804"],
  "discussion_flow": [
    { "step_order": 1, "text_ko": "논의 단계", "support_source_ids": ["c-3368825804"] }
  ],
  "selected_messages": [
    { "source_id": "c-3368825804", "summary_ko": "댓글 핵심 논지", "message_kind": "NORMAL" }
  ]
}
```

한국어 제목 200자, 이슈 요약 500자, 논의 흐름 1~4개·각 200자, 대표 메시지 0~3개·각 300자, 이슈당 최대 2,048 token을 초기 상한으로 둔다. 이슈 최대 2건은 동시성 2로 독립 호출해 한쪽 실패가 다른 쪽을 막지 않게 한다.

서버는 JSON schema·길이·enum을 검사하고, 모든 support/source ID가 해당 이슈의 입력 목록에 실제 존재하는지 확인한다. 여러 원문을 한 대표 메시지로 합치거나, 이슈 본문을 사용자 해결책으로 분류하거나, HTML·외부 URL·마크다운 링크를 넣은 결과는 그 이슈의 요약 전체를 거절한다. 통과한 뒤 support ID는 저장하지 않고, 선택된 원문의 작성자·관계·시각을 붙여 저장용 JSON을 만든다.

의미 왜곡은 2차 모델로 자동 판정하지 않는다. pino #2272·#2148의 동결 fixture에 조건 제거·주장 반전·가짜 합의·인용 혼동·코드와 로그 오독, prompt injection 사례를 포함하고 prompt나 결과 형식을 바꿀 때 사람이 확인한다.

요약 상태가 READY/PARTIAL/SKIPPED인 신선한 결과는 24시간 그대로 재사용한다. 요약이 FAILED이면
신선한 사실 결과는 화면에 유지하되 5분 쿨다운 뒤 사용자의 재시도를 허용하고 GitHub부터 다시
수집한다. 원문과 hash를 DB에 남겨 요약만 복구하는 경로는 만들지 않는다. 드문 재수집 비용보다
원문 보관·버전 비교·부분 UPDATE·경합 처리 코드를 없애는 편이 v1에는 단순하고 안전하다. 결과
형식이 호환되지 않게 바뀌면 `payload_version`을 올려 이전 행을 사용하지 않고 새로 수집한다.

GitHub Search 한도는 비인증 10회/분, 인증 30회/분이며 구현 API version은 2026-03-10으로 고정한다. core remaining/reset과 retry-after를 함께 확인하고 무한 재시도하지 않는다.

#### 관측과 운영 인계

새 관측 플랫폼을 두지 않고 기존 로그를 구조화해 아래 필드를 매 refresh 시도마다 남긴다:
refresh id, package_id, 단계(REPOSITORY_VERIFY/ISSUE_SEARCH/COMMENTS/GMS/PUBLISH), 단계별
소요시간, cache hit/stale 여부, 정제된 실패 코드, 다음 재시도 가능 시각. 모델·prompt 버전과
수집량·입력 길이도 함께 남겨 요약 품질·비용 회귀를 구분한다. 원문 전체나 시크릿은 로그에
넣지 않는다.

**결과 형식 호환성**: 서버가 지원하지 않는 `payload_version`의 행은 화면 결과로 반환하지 않고 새
수집 대상으로 본다. 정책·모델·응답 구조가 기존 결과의 의미를 바꿀 정도로 변경될 때만 코드의
payload_version을 올린다. 단순 문구 수정이나 운영 한도 조정은 버전을 올리지 않는다.

**종료 처리**: 종료를 시작하면 새 refresh를 받지 않고, 실행 중 작업은 설정된 5초 유예 안에
끝나지 않으면 외부 요청을 취소한다. DB 게시는 짧은 독립 트랜잭션이므로 commit된 snapshot만 남고
미게시 메모리 결과는 버린다. 다음 기동의 탭/분석 요청이 다시 시작한다. executor를 무기한 기다리거나
중간 결과를 성공 snapshot처럼 저장하지 않는다.

---

## 실행 계획

### 착수 전

- !91을 develop에 먼저 병합하고, 그 위에 쌓인 !90을 develop으로 이어서 병합. !92는 독립 문서
  변경이므로 순서와 무관하지만 세 MR 병합 후 최신 develop을 fetch·rebase하고 착수
- V1~V4가 하나씩 적용되어 백엔드가 기동하고 `seed_service_full.sql`까지 존재하는지 확인한 뒤
  community migration 번호를 V5로 고정
- Jira 확장-03과 Notion API 현황 등록
- 이미 병합된 공통 message·wrapper unwrap·전역 snake_case·mock 분기를 재사용하고 회귀 범위 확인
- collected_at 기준 24시간 재사용·7일 제공, github-active-v1 Issue 정책, GitHub API version
  2026-03-10을 계약서에 반영
- 팀이 이미 보유한 GMS_API_KEY와 URL·model·quota·schema 설정값을 ConfigurationProperties에
  연결(키 발급·승인 대기 항목 아님)
- GitHub 원문은 수집·요약·검증 중 메모리에서만 사용하고 DB에는 저장하지 않음
- Figma 자료 한계는 하단 배치. 역할은 실원천 association을 우선하고 고정 fixture의 라벨은 레이아웃
  검사용으로만 사용
- 실제 Curated 적재 DB에서 커뮤니티 seed·TRUNCATE를 실행하지 않는다는 규칙을 작업 문서와 MR
  체크리스트에 명시
- 기존 Jira `S15P21A506-137`(저장소 검증)·`212`(GitHub REST 연동)·`213`(모노레포·rate limit·실패)을
  재사용하고 신규 티켓을 미리 만들지 않는다. 착수 시 제품·wire 계약 / 저장소·읽기 경로 / 게시·
  실패 경로 / 요약 경로 / 사용자 화면 / 통합·운영 인계 6개 실행 단위로 작업을 나눠 담당과 완료
  기준을 정한다

### 데이터베이스와 백엔드

- V5 migration에 6개 컬럼의 community_snapshot 한 테이블·FK·CHECK·index 작성
- 빈 DB와 기존 적용 DB에서 중복 없는 전체 migration·Hibernate validate 검증
- !90 기준 세 로컬 시드의 TRUNCATE 목록에 community_snapshot을 추가하고 pino community fixture는
  별도 테스트 자료로 유지(실제 적재 DB에는 시드 적용 금지)
- community_snapshot Entity·타입이 정해진 JSON payload DTO·repository와 공통 API 계약
- 저장소 후보 결정→최종 host 검사→연결/scope 분리, 최신 댓글 pagination, rate/deadline, Issue policy
- source 소속·역할·reaction, GMS schema validator, 저장 전 JSON validator, 금지 왜곡 fixture
- RefreshTaskRegistry·단계 상태 전이·collected_at 기반 TTL·advisory lock과 upsert 기반 한 행 교체,
  POST 명령/GET 조회 controller, Swagger·API 현황

### 프론트엔드와 마무리

- 기존 API unwrap을 재사용하고 wire/view adapter, AbortSignal, GET transport 최대 2회 retry와 서버 주도 2초 상태 polling
- community progress/result 구성요소, report lazy tab, 분석 확정 시 비차단 POST refresh 연동
- Figma 485:936 비교
- pino fixture/실호출 source ID·count·role 대조
- stale/concurrency/rate/GMS 실패 검증
- Swagger·Notion·Jira·CLAUDE 동기화와 팀 리뷰

---

## 테스트 전략

### 데이터베이스 검증

DB는 !91·!90 병합 기준으로 빈 DB 전체 migration, 기존 DB upgrade, Hibernate validate, package FK·snapshot
UUID unique·data_status CHECK·JSON object CHECK·collected_at index를 확인한다. 같은 package upsert,
timeout 선설정→advisory lock→upsert 순서, 실패 시 이전 행 보존, 지원하지 않는 payload_version 무시,
!90 기준 세 로컬 seed의 반복 실행과 community FK로 인한 package TRUNCATE 실패가 없는지도 검증한다.
격리 테스트 DB(`pickage_community_test_<run_uuid>`)를 DB 통합 test run마다 만들고 `finally`에서
삭제한다. 시나리오는 schema 초기화/rollback으로 격리하고 생성·삭제 권한을 setup 계정으로 제한한다.
순수 단위 테스트에는 DB가 필요 없으며 `pickage` 애플리케이션 DB·세 로컬 seed·267 적재
프로세스는 사용하지 않는다.

### 단위·통합 검증

단위·통합 테스트는 최종 host 재검사, package 연결과 Issue scope 분리, DB/npm 충돌, Issue query·정렬·
fallback·PR 제외, association→표시 역할 변환, reaction, 큰 GitHub ID의 문자열 보존, LLM 허구·다른
Issue source ID 거부, discussion_flow 근거 실재 검증, 저장 JSON schema·배열 상한 검증, 금지 왜곡
fixture, 최신 100개 pagination과 수집 중 댓글 증감, 403/429·reset, search incomplete 결과, GMS 두
Issue 병렬 호출의 한쪽 실패, 24시간 결과 재사용과 7일 만료, 동시 cache miss, 서로 다른 50개 package
burst에서 전역 start token·동시 2·탭 queue 4 준수를 다룬다.

### API와 화면 검증

API/UI는 wrapper·snake_case·message, scoped package, 내부 필드 비노출, 동일 snapshot,
PROCESSING stage 전환, 완료 후 결과 자동 전환, partial/stale/unverified/ambiguous/no-data/error,
자동 패키지 대체 금지, 비클릭 저장소, 집계·source 소속 일치와 Figma 회귀를 확인한다. 분석 확정
직후 탭 진입, 동일 패키지 두 사용자, 요청 취소와 탭 숨김/복귀, 사전 요청 timeout, queue 상한 초과
후 탭의 1회 admission 재시도, GET 일시 오류 후 조회만 회복되고 POST가 중복되지 않는지, 최초 실패
후 retry_at, 전체 재수집 polling, `/report/:reportId` 문맥 가드, progress `aria-live`, mock 분석
확정 시 외부 호출 0건을 포함한다.

**Figma 고정 fixture와 운영 검색 정책은 다른 시험이다.** pino #2272·#2148, 수치 2·40·17·2는
UI 렌더링 회귀(레이아웃·긴 텍스트·0/1/2건 케이스)를 확인하는 **동결 fixture 전용**이며, 실 API
smoke test나 운영 배포 후 점검의 고정 기대값으로 쓰지 않는다. `github-active-v1` 선정 정책
자체의 정합성(180일 조건, comments 정렬, 365일 확장)은 시간과 후보 pool을 동결한 별도 시험으로
확인한다 — 정책은 조회 시점에 따라 결과가 달라지므로 화면 예시와 같은 값이 나오지 않는 것이
정상이다.

---

## 리스크

- !91보다 !90을 먼저 병합하거나, 세 MR 반영 전 브랜치에서 V5를 만들어 migration 계보가 다시 갈릴 위험
- 운영 GITHUB_COMMUNITY_TOKEN 누락·폐기 시 community 수집을 시작할 수 없는 설정 위험
- GMS 20초 예산 초과와 GitHub secondary limit
- 분석 확정 시 비차단 refresh가 커뮤니티 탭을 열지 않는 사용자 몫까지 GitHub 한도를 소비(전역
  상한·queue·fresh cache로 완화하되 실사용 비율을 운영 관측하고 필요하면 사전 트리거를 끔)
- 진행 상태 registry가 프로세스 재시작 때 사라져 최초 실패 쿨다운이 한 번 초기화되는 v1 허용 위험
- 모노레포·오래된 인기 Issue 오판
- prompt injection과 source ID hallucination
- 메모리에서 처리하는 raw source가 로그/API에 노출될 위험
- report shell과 Figma wrapper 차이
- 운영 자동 배포 부재

---

## 부록

### 검토 기준 자료

- 사용자 제공 ERD v0.6 DDL: 기존 5테이블, ETL 3테이블, similar_package
- Downloads: Pickage_IA정정_변경요약_260908.md, api 현황_db.zip, api 현황_페이지.zip,
  API명세_결정사항.pdf, v 0.5.png
- Figma: 제목 없음 파일의 wrapper 485:828, 활성 community 콘텐츠 485:936
- docs root(2026-09-09 0909 세트로 갱신됨): Pickage 서비스 기획서·요구사항 명세서·메뉴구조
  IA·기능별 개발 구상안·개발 일정표·0904_to_0909 기획변경 상세분석·api & data 수집 문서
- 현재 코드: backend Flyway(V1~V3, 9테이블)·공통 응답, frontend report page·API client·mock,
  `pipeline/snapshot/*`(269 실행 이력 패턴), `pipeline/curated/repository.py`·`transform.py`,
  `pipeline/postgresql/*`, `deploy/local/README.md`·`seed_sample.sql`
- 정밀평가: `Pickage_커뮤니티_구현계획_정밀평가_260909.md`와 근거 폴더

### 기준 fixture와 요구사항

#2272는 댓글 30·reaction 3·OPEN, #2148은 댓글 10·reaction 14·OPEN이다. 합계는 Issue 2,
댓글 40, reaction 17, OPEN 2다. 역할은 저장한 GitHub author_association으로 판정하고
USER_SOLUTION은 message kind로 둔다.

R01~R14는 각각 Header, 상단 요약 수치, 실제 snapshot 기준 계산(예시값 하드코딩 금지), 핵심 논의
카드, Issue 카드 필드, 논의 흐름 단계형 문장, 실제 논의 대화 카드, 작성자·역할, 한국어 요약(왜곡
없음), source 추적, snapshot 정합, 자료 한계, 미검증 대체 금지, 저장소 주소 읽기 전용으로
설계·테스트에 연결한다.

### 문서 업그레이드 과정

ERD v0.5 단독 전제, V2 migration 고정, snapshot 추적 부재, 원문 미보존, Issue body/comment 혼합,
중복 집계, API wrapper·필드명 충돌, scoped path, 자동 후보 대체, Issue·대표 메시지 선정 미정,
reaction·역할 혼합, 잘못된 rate 단위, timeout과 Compose 누락, Figma 범위 혼합을 바로잡았다.

아래 차수별 내용은 당시 변경 이력을 보존한 부록이다. 과거 항목의 V4·가장 오래된 100개·MAINTAINER
매핑·fire-and-forget·GET `retry:false`처럼 현재 본문과 충돌하는 표현은 구현 지침이 아니며, 가장
뒤의 업그레이드와 본문 결정이 우선한다.

### 정밀평가 P1 잔여 항목 반영 (2026-09-09)

베테랑 개발자 정밀평가(`Pickage_커뮤니티_구현계획_정밀평가_260909.md`)의 P1 8건 중 이미
docs 세트 정정으로 해결한 2건(패키지 선택 범위, Spring→GMS 호출 예외)을 제외한 나머지 6건을
반영했다. 각 항목은 방금 병합된 팀원 작업(V3 migration, `pipeline/snapshot/*`의 실행 이력
패턴)과 기존 코드(`pipeline/curated/repository.py`, `pipeline/postgresql/*`,
`deploy/local/README.md`)를 대조해 재사용 가능한 부분만 가져오고 과설계를 피했다.

- **저장소 검증**: URL 정규화만으로 검증을 대신하던 것을 host 판정 → npm packument 대조 →
  scope 판정 3단계 절차로 대체. 새 테이블 없이 `community_snapshot`에 검증 증거 컬럼 추가.
- **snapshot 게시 순서**: "새 snapshot 저장 후 이전 것 교체"(package_id UNIQUE와 충돌하던 문장)를
  "메모리에서 완성 후 짧은 트랜잭션 안 DELETE→INSERT→commit"으로 대체. advisory lock·읽기
  트랜잭션 격리 수준 명시. 269의 트랜잭션 규율(외부작업 분리, lock/timeout, 실패 시 이전 상태
  보존)만 가져오고 269의 테이블 자체(다중 계보 원장)는 가져오지 않았다 — 커뮤니티는 package당
  1행 교체가 목적이라 계보를 남길 필요가 없다.
- **원문 보관 vs 이전결과 보존**: 하나의 TTL(24시간)로 세 가지를 표현하려던 것을
  `fresh_until`(24시간)·`serve_until`(7일)·`source_retained_until`(=serve_until) 세 수명으로
  분리하고 정리 스케줄러를 추가.
- **API 계약**: 필드 이름 나열이던 것을 완성된 JSON 예시·필드 규약표·상태 조합표·오류표로 대체.
  백엔드 컨트롤러가 아직 0개라 `msg→message` 정정과 wrapper unwrap의 재작업 비용이 0임을 확인.
  이전 snapshot 없는 전면 실패는 503 대신 200+`FETCH_LIMITED`로 변경(프론트 기본 retry의 고비용
  요청 반복을 막기 위함).
- **source ID 검증 vs 내용 검증**: 작성자·역할·시각·순서·집계 수치를 서버가 원본에서 조립하도록
  분리하고(GMS 출력에서 제거), `discussion_flow_ko`(평문)를 근거 source ID를 포함하는 JSONB
  구조로 교체. 금지 왜곡 5유형(조건 제거·주장 반전·합의 생성·인용 혼동·코드-로그 오독) fixture를
  사람이 검토하는 절차를 추가하고 2차 LLM 재검증은 도입하지 않았다.
- **seed 계획**: migration 번호를 V4로 확정(V1~V3 실존 확인)하고, `similar_package`가 아직 어떤
  migration에도 없음을 발견해 TRUNCATE 목록에서 제외. 실 Curated 적재 DB·로컬 샘플 DB·격리
  테스트 DB 세 종류를 구분하고 각각의 규칙을 명시. `deploy/local/README.md`의 기존 금지 규칙과
  269가 이미 쓰는 격리 테스트 DB 방식을 그대로 인용했다.

이 라운드에서 다루지 않은 것: archived 저장소 의미, Figma 역할 라벨 불일치, 댓글 100개 상한,
"지금 이어지는 논의" 정책, Figma 노드 경계, 호출 예산·조건부 GET, Jira 실행 단위 재편 등 P2
전체. 열린 결정(제공 기한 7일 여부, statement_timeout 5초 여부, 커뮤니티 오류 코드 prefix,
503 유지 여부, REPOSITORY_WIDE 제공/제외, title_ko 제공 여부 등)은 사용자가 확정한 값을 그대로
반영했다.

### 정밀평가의 데이터 정확성 항목 반영 (2026-09-09)

정밀평가 P2 절 중 "데이터 정확성" 묶음 7건을 반영했다. Figma 스크린샷
(`Pickage_커뮤니티_정밀평가_근거_260909/figma-community.png`)을 직접 열어 대표 메시지 개수·역할
라벨 4종·공통 shell 공유 구조를 실제 렌더링으로 재확인했다.

- **archived**: 검증 실패(UNVERIFIED_REPOSITORY)와 분리해 `repository_archived` 컬럼과 별도
  자료 한계 문구로 처리(제외하지 않고 표시). locked·Bot은 대표 후보 제외와 전체 댓글 수 집계
  포함을 구분.
- **역할 라벨**: `author_association`(원천 값)과 `author_role`(서버 계산 표시값)을 분리 저장하고
  ISSUE_AUTHOR 최우선·OWNER/COLLABORATOR→MAINTAINER·CONTRIBUTOR/MEMBER→CONTRIBUTOR·그 외→NULL
  매핑표를 확정. Figma 스크린샷 확인 결과 실제 대댓글 들여쓰기는 뚜렷하지 않아 "reply 관계 오인"
  우려는 낮다고 판단, 관련 문구만 가볍게 정리.
- **댓글 100개/대표 3개**: Figma 실측(#2272·#2148 각 3개, 합 6개)으로 "Issue당 3개"임을 확인해
  계획에 복원(직전 라운드 편집 중 누락됐던 숫자). 댓글 100개가 ID 오름차순 "가장 오래된 100개"임을
  명시.
- **"지금 이어지는" 문구**: docs 0909 세트(§10.1/§11.1)의 화면 카피는 바꾸지 않고, `issue_updated_at`·
  `data_limits.search_window_expanded`·30건 후보 pool 기반 동률 재정렬만 데이터로 추가.
- **정책 vs Figma fixture**: "테스트 전략"에 Figma 동결 fixture(UI 검증 전용)와 운영
  `github-active-v1` 정책 시험(시간 동결 별도 시험)을 구분하는 문단 추가.
- **DB 컬럼 완성**: community_snapshot·issue·message 세 테이블 전체를 타입·NULL·기본값·설명이
  있는 표로 재작성. GitHub numeric ID(BIGINT)/node ID 구분, 시각 3종(collected_at·
  source_updated_at·source_created_at) 명명 분리, count 3종 NOT NULL 정책, Issue 본문 중복
  저장(`community_issue.source_body` vs `ISSUE_BODY` message)의 sha256 동기화 근거를 명시.
- **Figma 노드 경계**: 렌더링 결과는 이미 정상(스크린샷으로 재확인)임을 근거로 실제 조치는
  "02-package-intro~05-discussion-threads만 복제, 574:303 공통 shell 제외"라는 구현 지침
  한 문장으로 한정.

### 정밀평가의 성능·운영·팀 절차 항목 반영 (2026-09-09)

정밀평가 P2의 나머지 세 묶음(성능·비용, 보안·운영 인계, 팀 구현 방식·일정) 8건을 반영했다.

- **20초·30초 timeout은 호출 예산이 아니다**: 전역 동시 실행 상한(세마포어)과 4단계 예산 분해
  (저장소검증→Issue검색→댓글→GMS, 소진 시 다음 단계 미실행)를 추가. 프론트 community 쿼리에
  `retry: false` 명시.
- **변경 없는 자료 재요약 낭비**: 이미 저장해 둔 `summary_input_sha256`을 실제로 비교해 GMS
  재호출을 생략하는 문장을 추가(만들어 놓고 안 쓰던 값). 실패 후 쿨다운(5분, 신규 컬럼 없음)
  추가. 저장소 검증 캐싱·조건부 GET은 이번 v1에 넣지 않고 이유를 명시.
- **비신뢰 입력 원칙을 실패 시험까지 연결**: 저장소 주소를 원문 그대로 넘기지 않는다는 제약이
  이미 현재 검증 흐름으로 충족됨을 명문화. 시크릿·원문 로그 미기록 규칙 추가.
- **장애 원인 구분할 관측값**: refresh 단계별 구조적 로그 필드 표 추가. 정책·스키마 버전이
  바뀌면 TTL이 남아있어도 재수집하는 호환성 규칙 신설. 종료 시 graceful shutdown 명시.
- **ERD v0.6 선행조건**: 남은 우려("ETL이 repo_url을 바꾸면?")는 검증 캐시 테이블을 안 두기로
  한 결정 덕에 구조적으로 이미 해결됨을 확인·명시.
- **보고서 문맥·mock 전환**: report 문맥 없는 직접 진입 가드, prefetch=코드 청크 import(데이터
  수집 아님) 명확화.
- **공통 API 규약 우선순위**: 여러 참고 문서가 충돌할 때 **`api 현황_페이지.zip`을 우선**하도록
  명시. 문서 간 전체 충돌 해소는 이 기능 스코프 밖으로 명시.
- **Jira/실행 단위**: 부록 R01~R14 대응 오류(R02~R04 밀림) 정정. 기존 Jira 137/212/213 재사용,
  신규 티켓은 만들지 않고 착수 시 6개 실행 단위로 나누도록 "착수 전"에 안내 추가.

### GMS 키 보유와 수집 트리거 시점 반영 (2026-09-09)

- **GMS_API_KEY는 팀이 이미 보유**하고 있음을 "설정과 보안"·"착수 전"에 명시했다 — 발급·승인을
  기다리는 항목이 아니라 연결만 하면 되는 항목으로 정정.
- **수집 트리거를 탭 오픈 시점에서 분석 확정 시점으로 앞당겼다.** 사용자가 비교 대상을 확정하고
  분석을 실행하는 순간 기준 패키지 1건에 대해 fire-and-forget 사전 요청을 보내 생태계 보고서
  렌더링과 무관하게 백그라운드에서 미리 수집하고, 탭을 열 때는 이미 끝나 있거나 훨씬 짧게
  기다리게 한다. 안전장치: (1) 새 캐시·엔드포인트를 만들지 않고 기존 `fresh_until`/single-flight
  판단을 그대로 재사용, (2) 전역 동시 실행 상한이 꽉 차면 사전 요청은 조용히 포기하고 탭 오픈
  시점의 기존 lazy 경로가 안전망으로 남는다, (3) 탭을 열지 않는 사용자 몫까지 GitHub 한도를
  소비하는 문제를 리스크로 명시하고 실사용 비율은 운영 관측 대상으로 남겼다.

### 구조화 진행 UX와 정밀 재검토 반영 (2026-09-09)

- **사용자 결정 반영**: 사전 수집은 분석 확정 때 비차단 명령으로 시작하고, 탭 안에서는 기능 비교와
  같은 구조화 카드가 서버 단계별 한국어 메시지를 보여주다가 같은 자리의 결과로 전환한다. 기존
  `AnalysisProgress`의 시각 패턴만 참고하고 `STEP_MS` 가짜 진행률은 재사용하지 않는다.
- **완료 전달 계약**: POST 명령과 GET 조회를 분리하고 같은 응답 모양·refresh_id를 사용한다.
  QUEUED/RUNNING만 서버 주기대로 폴링하며 숨김 탭은 멈춘다. stale 결과와 GMS-only 회복 중인 fresh
  사실 결과도 감추지 않고 진행 카드를 함께 보여준다.
- **admission·실패 수명**: 전체 refresh 10건/분·동시 2·탭 queue 4의 초기 상한, 사전 요청 무대기 원칙, CAPACITY_LIMITED 초기 응답과
  한 번의 탭 재시도, task 10분 관측·5분 실패 쿨다운·GitHub reset 우선 규칙을 확정했다. 성공 결과
  TTL과 최근 실패를 분리하고 실패 때문에 이전 결과의 수명을 늘리지 않는다.
- **저장소와 scope**: DB/npm 후보를 모두 보존하고 최종 host를 다시 검사한다. 패키지 연결 증거와
  저장소 전체 Issue 귀속은 분리해 monorepo를 PACKAGE_SCOPED로 과장하지 않으며, DB repo 후보가
  바뀌면 fresh cache도 무효화한다.
- **댓글과 역할**: 최신 100개를 Link 교차 확인 포함 최대 세 page로 읽고 관측 시점이 다른 count 사이 대소 CHECK를
  제거했다. 역할은 원천 관계를 그대로 설명하는 라벨로 바꿔 MEMBER/COLLABORATOR를 기여자·
  유지관리자로 과장하지 않는다.
- **요약과 게시**: 실제 모델 입력 전체를 hash에 포함하고 성공·검증된 생성 bundle만 재사용한다.
  support/source 연결과 최초 생성 시각도 보존한다. GMS-only 회복은 snapshot_id/source hash를 잠금
  안에서 재확인한 UPDATE로 게시해 뒤늦은 결과가 새 전체 refresh를 덮지 않게 했다.
- **상태·fixture**: 원천 수집 상태와 Issue 요약 상태를 분리하고 진행·최초 실패·정상·빈 결과·부분·
  GMS 실패·stale의 공개 response와 내부 source fixture를 짝으로 둔다. 실제 pino 두 Issue의 합계·
  source 소속·시각·UUID를 바로잡고 내부 source ID는 wire에서 제거했다.
- **DB·최신 develop**: 최신 원격에 중복 V2와 ETL 재정의가 있음을 반영해 community 번호를
  `V{next}`로 되돌리고, 번호 변경만으로 중복 CREATE를 실행하지 못하게 했다. 이미 병합된 공통
  response/client/mock 구현은 재작성하지 않고 AbortSignal만 제한적으로 확장한다.
- **추가 자체 검수 수정**: 20초 예산과 모순되던 30초 성공 예시를 18초로 맞췄고,
  `/report/:reportId` 문맥·기준 패키지 전달을 명확히 했다. read-only GET transport 오류만 최대 2회
  회복하고 POST/domain 실패는 자동 재시도하지 않도록 비용과 복원성을 분리했다.
- **공식 규약 재확인**: [GitHub REST 2026-03-10 지원 버전](https://docs.github.com/en/rest/about-the-rest-api/api-versions),
  [Search의 인증 30회/분·비인증 10회/분](https://docs.github.com/en/rest/search/search),
  [Issue별 댓글의 ID 오름차순·정렬 파라미터 부재](https://docs.github.com/en/rest/issues/comments),
  [403/429 retry-after·reset 처리](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)을
  2026-09-09 기준 다시 확인해 API 버전·최신 댓글 pagination·retry gate 근거를 갱신했다.

### 담당 작업 구체화와 DB 단순화 반영 (2026-09-09)

- 인프라·DB/ERD·프론트엔드가 실제로 만들어야 할 결과를 요약에 직접 적고 상세 절로 연결했다.
- 조회가 package별 최신 결과 한 건이고 자식 행을 따로 검색·수정하지 않는다는 접근 패턴을 기준으로
  기존 community_snapshot·community_issue·community_message 3테이블 설계를 폐기했다.
- 최종 설계는 package_id, snapshot_id, payload_version, collected_at, data_status, result의 6개
  컬럼을 가진 community_snapshot 한 테이블이다. 이 절보다 앞선 부록의 3테이블·원문 보존·hash 재사용·
  GMS-only UPDATE 설명은 변경 이력일 뿐 현재 구현 지침이 아니다.
- 만료 시각·상단 합계·역할·표시 순서는 코드에서 계산하고, 후보 주소·모델 버전·입력량은 구조화
  로그로 관측한다. 원문과 근거 ID는 저장 전 검증 후 폐기한다.
- API·설정·실행 계획·테스트의 관련 항목도 한 행 JSONB upsert 방식으로 함께 갱신했다.

### MR !90·!91·!92 병합 예정 기준 반영 (2026-09-09)

2026-09-09 확인 시 세 MR은 모두 opened·mergeable이며 아직 develop에는 들어오지 않았다. 구현 완료
상태로 기록하지 않고 병합 후 develop을 착수 기준으로 삼았다.

- !91: 중복 V2 제거와 V4 생성, 기존 두 seed의 snapshot 초기화 교정. 가장 먼저 병합.
- !90: !91 위에 쌓인 로컬 `seed_service_full.sql`·README 추가. !91 다음 병합.
- !92: removal_by_year 행 수·MinIO 경로 문서 정정. community 코드와 DB에는 영향 없음.
- community 작업은 병합 후 V5를 사용하고, 세 로컬 seed 모두 package 초기화 전에
  community_snapshot을 비우도록 후속 수정한다.

### 최종 재검수 기준

- 사실: 코드·ERD v0.6·Figma·API 서술이 맞는가
- 계약: DB → backend DTO → wire JSON → frontend model → 화면이 연결되는가
- 실행: 선행 조건·검증·실패 처리가 있는가
- 추적: R01~R14와 발견 문제 모두 설계·테스트에 연결되는가

하나라도 연결되지 않으면 구현 전에 이 문서를 먼저 고친다.
