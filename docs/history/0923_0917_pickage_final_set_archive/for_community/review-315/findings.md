# Phase 1~4 검수 결과 — 수정 전

기준: `d9193a3`, 2026-09-11. 기획 원문은 [구현계획](../Pickage_GitHub커뮤니티_구현계획_260908.md), 요구별 연결은 [추적표](traceability.md).

**현재 코드는 Phase별 구성 요소를 갖췄지만, 커뮤니티 기능을 인수 가능한 상태로 볼 수 없다.** 전체 wire와 저장 계약의 불일치, 불완전 자료를 정상/논의 없음으로 표시하는 경우, 실행·게시 제한 미보장, 기존 seed 회귀가 있다. 기존 테스트 일부가 요구사항과 다른 동작을 기대값으로 삼아 통과한다.

아래 F01~F20은 원인별 수정 단위다. **35개의 실패 테스트를 35개 독립 결함으로 세지 않는다.** 단위 반례 27개 실패, 실제 Spring+격리 DB 반례 11개 중 8개 실패·3개 통과. 정적 근거와 실행 재현을 구분한다. 이는 **수정 전** 판정이며 본문·라인 번호는 d9193a3 기준으로 보존한다. 현재 수정 상태와 증거는 [수정 대장](remediation.md)을 따른다.

우선순위: P1은 기능 인수·자료 신뢰·자원 격리·기존 작업을 막는 문제, P2는 그 밖의 계약·정확성·효율 문제다. 운영 장애가 실제 발생했다는 뜻은 아니다.

## F01 · P1 · 공유 API 사전과 실제 응답 구조가 다르다

- 요구 R08 / §6.2. `CommunityService.java:152`, `dto/CommunityResultResponse.java`, `TopicResponse.java`, `RepositoryInfoResponse.java`, `DataLimitsResponse.java` 등.
- `summary_retry_at` 없음; repository는 owner/name/full_name/archived 없이 identifier/scope만 반환. issue_count 대신 analyzed_issue_count, title_original/state/comments_count/reactions_count/created_at/updated_at/flow 대신 다른 필드 또는 누락. message의 role/kind/text/created_at 및 flow 구조도 다름. limitations는 code/message/issue_number 객체 대신 문자열, data_limits는 policy/lookback/source_note 등 누락.
- FE가 §6 fixture로 구현되면 자료를 읽지 못하거나 누락된 정보를 추정하게 된다. snake_case 설정 자체는 실제 Spring에서 정상이다.
- 재현: `CommunityContractReviewTest.R08_fullResultKeysMustMatchContract`. 실제 runtime 직렬화 확인은 `ApplicationContractReviewTest.R12_actualRuntimeSnakeCaseAndNullKeys` 통과. 단순 naming 설정 교체로 해결되지 않는다.
- 수정: 공개 DTO·저장 payload·수집 입력·서비스 변환을 함께 맞추고 전체 JSON fixture 및 Swagger를 대조.

## F02 · P1 · 최초·stale 갱신·종료 상태가 UI 계약과 다르다

- 요구 R08 / §6.3. `CommunityService.java:47,123,142`, `refresh/RefreshTask.java:40,75`, `RefreshStage.java`.
- 최초 GET은 IDLE/refresh=null이어야 하지만 FAILED/NOT_STARTED. 반환 가능한 stale 결과가 있어도 active 작업이 있으면 PROCESSING. QUEUED의 started_at이 수락 시각이며 RUNNING 외에도 stage가 남는다. COLLECTING_DISCUSSIONS는 사전에 없는 값이고 VALIDATING 단계가 없다.
- 첫 진입이 실패로 보이고 갱신 중 기존 결과 표시·polling 판단이 어긋난다. 작업 없는 POST 용량 거절 뒤 GET도 IDLE로 돌아오지 않는다.
- 재현: `R08_initialGetMustBeIdleWithNullRefresh`, `R08_staleWithActiveMustKeepResultView`, `R08_completedStageMustBeNull`, `R09_queuedTaskMustNotHaveWorkerStartTime`, 실제 앱 최초 응답 반례.
- 수정: 상태 우선순위와 task 전이를 함께 정리. nullable을 단순 삭제하는 방식으로 우회하지 않는다.

## F03 · P2 · 잘못된 입력과 오류 응답의 캐시 정책이 다르다

- 요구 R08 / §6.1. `CommunityService.java:90`, `CommunityController.java`.
- 빈 name/형식 오류를 DB 조회까지 보내 C006/404로 처리한다. 각각 V001/400, V004/400이어야 한다. 파라미터 누락 오류 응답에는 no-store가 없다.
- 재현: 실제 앱 `R08_blankNameMustBeV001`, `R08_malformedNameMustBeV004`, `R08_errorMustAlsoBeNoStore`.
- 수정: 기존 `domain/packages/PackageNames.java` 재사용, community 경로에 한정한 헤더 처리. 공용 오류 처리 동작 변경은 피할 수 있다.

## F04 · P1 · 일부 요약 성공과 전체 실패를 구분하지 않는다

- 요구 R05/R07 / §5.2~5.3. `CommunityService.java:215`, `CommunityRefreshOrchestrator.java:146,160`, `FakeCommunitySummarizer.java`.
- READY+FAILED를 전체 FAILED로 집계한다. 하나라도 실패하면 5분 재시도를 저장해 일부 성공 결과의 24시간 재사용을 깨뜨린다. 실제 topic이 있는데 fake는 SKIPPED를 반환한다(SKIPPED는 topic 없음). 요약 실패 한계도 전달하지 않는다.
- 자료 상태는 모든 limitation 존재 여부로 결정해 archived/repo-wide 같은 범위 설명만 있어도 PARTIAL이 된다. 자료 완전성과 요약 성공은 별도 축이다.
- 재현: `R05_mixedSummariesMustBePartial`, `R05_fakeForExistingTopicsMustReportFailure`, `R05_partialSummaryMustNotScheduleFiveMinuteRetry`.
- 수정: topic 집합 기반 집계, 전체 요약 실패에만 완료+5분 저장, fake 미연결의 명시적 실패와 사실 자료 유지.

## F05 · P1 · 미지원·손상 snapshot을 정상 자료로 읽는다

- 요구 R06 / §5.1. `CommunitySnapshotRepository.java:122,161`, `payload/CommunityResultPayload.java`와 중첩 record.
- payload_version/policy_version 지원 여부를 검사하지 않는다. 지원 버전 result={}가 typed record로 만들어지고 null/0을 포함한 채 반환된다. 쓰기에도 필수값·enum·범위·길이·source 관계 검증이 없다.
- 재시작 후 잘못된 자료를 재사용하거나 이후 변환에서 NPE가 난다. 미지원 버전은 결과 없음, 지원 버전 손상은 S001이어야 한다.
- 재현: 실제 DB `R06_unsupportedPayloadMustBeIgnored`, `R06_unsupportedPolicyMustBeIgnored`, `R06_invalidSupportedPayloadMustBeRejected`; 단위 `R06_typedPayloadMustRejectMissingRequiredFields`.
- 수정: 읽기/쓰기 validator, 명시적 버전 분기. v1의 누락 source/created_at을 추측해 채우지 않고 새 payload 버전으로 전환·재수집. 이미 병합된 V5 수정 불필요.

## F06 · P2 · TTL 양쪽 경계가 포함 처리된다

- 요구 R07 / §5.3. `CommunitySnapshotTtl.java:28,33`, `CommunitySnapshotRepository.java:139`.
- 정확히 24시간을 fresh, 정확히 7일을 노출 가능으로 처리한다. 각각 stale·비노출이어야 한다. 정리 조건도 strict <다.
- 재현: `R07_exact24HoursMustBeStale`, `R07_exact7DaysMustNotBeServed`.
- 수정: Clock 기반 경계, 조회/재사용/정리의 동일 판정. 기존 경계 테스트 기대값도 원문 기준으로 수정.

## F07 · P1 · 실패 cooldown을 POST가 우회한다

- 요구 R07 / §5.3/7.2. `CommunityService.java:68`, `CommunityRefreshOrchestrator.java:199`.
- 최근 종료 실패의 retry_at을 조회하지 않고 새 admission으로 간다. 외부 retry_at과 완료+5분 중 늦은 값도 취하지 않고 외부 값이 있으면 그대로 사용한다.
- 실패 직후 반복 POST로 제한된 외부 요청을 다시 시작할 수 있다. 용량 거절은 짧은 retry_at조차 없다.
- 재현: `R07_recentFailureMustRejectNewRefresh`; 나머지는 분기 정적 확인.
- 수정: active→재사용·재시도 자격→설정·호출량·용량 순서, 최근 실패와 snapshot 및 전역 gate의 최대 retry 시각 적용.

## F08 · P1 · GitHub rate 제한이 클라이언트 전역 상태로 공유되지 않는다

- 요구 R10 / §7.2. `verification/GitHubRepositoryClient.java:183`, `collection/GitHubIssueSearchClient.java`, `GitHubIssueCommentsClient.java`의 개별 checkRateLimit.
- 각 응답에서 예외를 던질 뿐 같은 token의 core/search 중단 시각을 저장·참조하는 공통 gate가 없다. 200 remaining=0은 무시, Retry-After 없는 secondary 403은 저장소 접근 거부 등으로 분류될 수 있다. retry 값 누락 시 최소 1분도 보장되지 않는다.
- 다른 package 요청이 소진된 token으로 계속 호출한다. 숫자 헤더 파싱 예외 처리도 필요하다.
- 증거: 세 클라이언트·Config·admission의 호출 경로 정적 확인. 실제 GitHub 제한을 유발하는 시험은 실행하지 않음.
- 수정: 주입되는 공유 gate와 정제 오류 타입, local fixture로 core/search/secondary/잘못된 헤더 검증.

## F09 · P1 · admission 상한 검사와 등록이 원자적이지 않다

- 요구 R09 / §7.2. `refresh/RefreshAdmissionCoordinator.java:70`.
- registry.size 검사 후 createOrJoin이 분리된다. 종료 기록 127개에서 서로 다른 요청 둘이 동시에 size를 읽으면 129개가 등록된다. ANALYSIS_CONFIRMED가 permit 부족으로 거절될 때 이미 소비한 start token도 반환하지 않는다.
- 재현: `ConcurrencyContractReviewTest`의 registry 경합·거절 토큰 반례. barrier로 검사 시점을 맞춘 실제 두 스레드 경합이며 registry map 자체를 바꾸지 않는다.
- 수정: registry/queue/permit/token을 일관된 admission 구역에서 결정. 동일 패키지 참여와 fresh 재확인도 최종 수락 직전에 보장.

## F10 · P1 · 대기·실행 수명과 종료 전이가 보장되지 않는다

- 요구 R09 / §7.2. `RefreshTask.java:40,64`, coordinator `152,178`.
- 수락 때 정한 deadline을 대기·실행이 공유한다. queued 만료는 worker 반환 시에만 처리하므로 막힌 worker 둘이면 계속 QUEUED. 만료도 CAPACITY_LIMITED로 바꾼다. terminal task를 markRunning으로 되살릴 수 있다.
- shutdown은 새 admission 거절 상태·대기 목록 취소·남은 task 취소를 보장하지 않는다. executor submit 거절 시 등록/permit 정리도 없다.
- 재현: queued 시각·queued 만료·terminal 재활성화 반례. shutdown 부분은 정적 확인, 개선 후 실제 종료 시험 필요.
- 수정: queue 20초/run 20초 별도 시계, 독립 만료 감시, 단방향 terminal 전이, 수락부터 취소/게시까지 소유권 관리.

## F11 · P1 · HTTP body를 읽는 동안 deadline을 넘겨도 성공한다

- 요구 R10 / §3.4/7.2. `verification/BoundedHttpReader.java:36`, npm lookup `67,87` 및 GitHub 세 클라이언트.
- HttpRequest.timeout 뒤 ofInputStream을 받아 blocking read하며 reader에 deadline/취소 수단이 없다. byte cap은 무한히 느린 body를 제한하지 않는다.
- 재현: loopback HTTP 서버가 headers와 `{`를 보낸 뒤 700ms 지연. 150ms 예산의 npm 호출이 끝까지 읽고 성공한다(`VerificationContractReviewTest` body timeout). 외부 네트워크 없이 확인.
- worker 둘이 이런 응답을 읽으면 전체 커뮤니티 큐와 종료가 막힐 수 있다. 무기한 정지 자체는 시험하지 않았고 동일 blocking 구조에서 가능한 위험이다.
- 수정: 전송부터 body 완료까지 byte+시간 상한과 취소를 적용하는 subscriber/client. unbounded 추가 thread로 감싸지 않는다.

## F12 · P1 · 실패한 작업도 결과를 게시하고 수집 시각을 뒤로 미룬다

- 요구 R11 / §5.3/7.2. `CommunityRefreshOrchestrator.java:184`, `CommunitySnapshotRepository.java:81`.
- upsert 직전 task ID/active 소유권/deadline 검사가 없다. task 실패 후 결과가 도착해도 저장·COMPLETED 전이가 가능하다. collected_at은 worker 시작 대신 게시 시각.
- 게시 2초 예약 상수는 실행 경로에서 사용되지 않으며 lock 2초/statement 5초 고정값은 계획의 최대 1초/2초와 다르다. connection 대기 제한도 게시 예산과 연결하지 않는다.
- 재현: `R11_failedTaskMustNotPublishLateResult`, `R11_collectedAtMustBeWorkerStart`. **실제 Spring transaction rollback으로 이전 row가 보존되는 것은 통과**했으므로 트랜잭션 자체가 없다는 지적은 하지 않는다.
- 수정: deadline 예산 분리, 같은 DataSource의 제한된 transaction·commit 전 fence, 취소 후 late result 폐기, collected_at 고정. 실제 connection/lock 지연 재검증 필요.

## F13 · P1 · 잘못된 npm 저장소 입력을 ‘없음’으로 바꿔 DB로 우회한다

- 요구 R01 / §3.1. `RepositoryUrlParser.java:44,81`, `RepositoryCandidatePolicy.java`, `NpmRepositoryLookup.java:94`.
- malformed URL이 Absent가 되어 DB GitHub 후보로 fallback. HTTPS userinfo를 거절하지 않고 npm directory의 traversal을 검증하지 않는다. directory가 contents URL에 그대로 결합된다. latest payload의 name 일치도 검사하지 않는다.
- 잘못된 연결을 검증 대상으로 승격할 수 있다. 고정 GitHub host·redirect 차단은 있어 임의 호스트 SSRF가 재현됐다고 주장하지 않는다.
- 재현: malformed npm fallback, credential URL, ../../../../search directory 단위 반례. npm name 검사는 정적 근거.
- 수정: absent/invalid/unsupported 구분, 원문·decode 후 경로 검증, latest name 확인과 고정 API 경로 조립.

## F14 · P1 · public·monorepo·모호한 연결 판단이 빠져 있다

- 요구 R01 / §3.1 판정표. `GitHubRepositoryClient.java:67,151`, `RepositoryScopePolicy.java:20`, `RepositoryVerificationService.java:80`.
- metadata 200이면 private=true여도 archived만 읽고 허용. root package name만 읽어 workspaces 증거를 잃는다. DB-only root mismatch는 AMBIGUOUS_SCOPE 대신 UNVERIFIED_REPOSITORY. npm/DB 충돌과 root heuristic 한계도 결과로 인계되지 않는다.
- 비공개 자료를 공개 커뮤니티 대상으로 수집할 수 있고 monorepo 전체 논의를 패키지 전용처럼 표시할 수 있다. 실제 비공개 저장소에 접근하는 시험은 하지 않았다.
- 재현: private metadata 200, DB-only mismatch 반례. workspaces·한계 전달은 정적 근거.
- 수정: 공개 metadata·root 증거 DTO, 결정표 fixture. 연결 미확정 terminal 결과 repository=null.

## F15 · P1 · 불완전 검색을 논의 없음으로 확정하고 기간을 잘못 저장한다

- 요구 R03/R06 / §3.2/5.1. `IssueCollectionService.java:55,75`, `IssueCollectionResult.java`, orchestrator `58,188`.
- incomplete_results=true이고 total_count=0이어도 365일로 확장. 필터 후 0에서 accumulated limitation을 잃고 NoDiscussionData로 반환. 실제 365일 검색을 해도 orchestrator는 180 고정 저장.
- ‘확인하지 못함’과 ‘없음’이 섞이고 재시작 후 조사 범위도 틀리게 표시한다.
- 재현: `CollectionContractReviewTest` incomplete zero. 기간·한계 손실은 result 타입과 게시 코드로 확인.
- 수정: complete raw0만 확장, filter0/incomplete0 구별, 결과 타입에 실제 lookback 및 한계를 보존.

## F16 · P2 · 댓글 절단 상태·시간순·추가 호출이 계약과 다르다

- 요구 R04 / §3.3. `CommentWindowResolver.java:32,47`, `IssueCollectionService.java:105`.
- 101개에서 마지막 100개만 남겨도 COMPLETE. created_at을 사용하지 않고 numeric ID 내림차순으로 전달. 마지막 page가 이미 100개여도 직전 page를 조회한다. 중간 추가/삭제를 partial로 판단할 증거 검사가 없다.
- 요약 입력 순서가 거꾸로 되고 생략 사실이 숨겨지며 불필요한 API 호출로 예산이 줄어든다.
- 재현: 101개 절단·서로 다른 created_at와 같은 시각 ID tie 반례. 추가 호출·변경 검사는 정적 근거.
- 수정: 필요한 page만 최대 3회, created_at→numeric ID 오름차순 최신 100개, 상태/한계 인계. 199/200/301·삭제·page 실패·큰 ID 재검증.

## F17 · P1 · 요약 근거를 보장할 수 있는 입력과 검증 경계가 없다

- 요구 R05/R06 / §4/5.1. `collection/SearchResultItem.java:12`, `CollectedIssue.java:12`, `CollectedComment.java:12`, `CommunitySummarizer.java`, orchestrator `170` 및 `payload/TopicPayload.java`.
- issue source ID/body/created_at·stable author ID가 수집 DTO에서 누락된다. topic source_issue_id도 저장하지 않는다. summarizer 반환 메시지의 source 존재·author 동일성·허용 role/kind·상한을 검증하지 않고 게시한다. 별도 GMS pool2/queue2와 제한된 future 대기 경계도 없다.
- 나중에 실제 GMS client만 연결해도 ISSUE_AUTHOR와 원문 근거를 입증할 수 없다. 모델 문장 의미 평가는 별도 C1이지만 **BE가 검증 가능한 근거를 인계하고 반환값을 제한할 책임**은 남는다.
- 증거: DTO→summarizer→payload 경로 정적 확인. 실제 GMS를 연결하거나 의미 평가를 했다는 주장은 하지 않는다.
- 수정: refresh 메모리 source bundle, 구조·근거 validator 인터페이스 및 fake fixture, 분리된 bounded executor. 원문은 DB/wire/log에 저장하지 않음.

## F18 · P2 · 외부 예외 메시지·cause가 정제 없이 로그로 흐른다

- 요구 R10 / §10. orchestrator `76,174,194`, verification service `52,80,95,116`, collection service `67,129`.
- summarizer의 e.getMessage 및 원본 cause를 로그에 전달한다. DB repository 원문도 충돌 로그에 남긴다. client 파싱 예외에 response 일부가 들어오면 상위 cause 출력으로 이어질 수 있다.
- 실제 토큰 유출을 관측한 것은 아니다. 외부 구현이 바뀌어도 민감 원문을 남기지 않는다는 계약을 현재 경계가 보장하지 못한다.
- 수정: 원인 enum·refresh/package ID·수량/길이 등 허용 필드만 기록. synthetic secret/raw sentinel을 넣은 log capture 시험.

## F19 · P1 · V5 이후 기존 공용 seed 4개가 FK 오류로 중단된다

- 요구 R14 / §9. `deploy/local/seed/seed_sample.sql:31`, `seed_mock_parity.sql:35`, `seed_service_full.sql:62`, `seed_reset.sql:28`.
- 모두 package를 TRUNCATE하지만 이를 참조하는 새 community_snapshot이 목록에 없다. **community_snapshot이 비어 있어도** 실패한다.
- 재현: 실제 Spring+격리 DB `R14_existingSeedTruncateMustRemainExecutable`; 동일 SQL에 대한 FK 오류. 개발 DB에서 seed를 실행하지 않았다.
- 수정 제안: 위 4곳에 community_snapshot 명시 추가. 광범위 CASCADE를 사용하지 않는다. seed_clear_snapshots는 현재 의미상 제외. 공용 seed 변경은 local AGENTS의 담당 경계이므로 구체적 Spec에 별도 표시.

## F20 · P1 · disabled/설정 누락 상태에서도 새 수집을 수락한다

- 요구 R08/R12 / §10, Jira317 설정 누락 항목. `CommunityConfig.java:81,112`, `CommunityProperties.java`, `CommunityService.java:68`.
- token을 null로 client에 넣고 fake summarizer를 항상 연결한다. COMMUNITY_ENABLED와 설정 준비 여부를 admission에서 확인하는 분기가 없다.
- 기본 비활성·외부 연결 전 차단 의도와 달리 실제 요청을 시작할 수 있다. 기존 fresh/active와 core 기동은 계속 허용해야 한다.
- 증거: 전체 bean wiring/admission 정적 확인. 설정 상수 클래스 선택·application.yaml 보존은 사용자 승인 사항이며 그 선택 자체를 결함으로 분류하지 않는다.
- 수정: community 내부 readiness abstraction과 기본 false switch, active/fresh 이후 검사. 인프라 secret·실제 GMS 프로토콜을 임의 확정하지 않는다.

## 기존 테스트·기존 기능·승인된 선택의 판정

- `CommunitySnapshotTtlTest`의 24h/7d 포함, `CommunityServiceTest`의 FAILED/NOT_STARTED, `RefreshStageTest`의 COLLECTING_DISCUSSIONS, 댓글 테스트의 101 COMPLETE 기대는 현재 구현을 고정한다. 같은 테스트 재실행만으로 기획 적합성을 보장하지 못한다. 수정 시 근거를 §6/§12에 연결한다.
- 기준선 `test build`는 기존 `domain/report/PdfStoreTest.java:23,35`의 save 인자 누락으로 compileTestJava 실패. 과거 Phase2 기록에도 동일 문제. **커뮤니티가 새로 유발한 결함으로 세지 않는다.** 격리 init script로 이 한 파일만 제외하면 나머지 기존 단위 테스트 197개 통과. 전체 무조건 통과라고 기록하지 않는다.
- 기존 community DB 테스트 15개 통과. 새 실제 앱 검사에서 이전 row transaction rollback·기존 패키지 검색·실제 snake_case/null key 직렬화 통과.
- 최신 develop `8372b17`과 317을 별도 worktree에 merge한 결과 충돌 없음. PdfStoreTest 제외 backend test/build 통과, frontend typecheck/build 통과. 기존 브랜치 frontend setError 오류는 최신 develop에서 이미 수정됐다.
- FE `ReportTab`은 ecosystem/features만 존재. API→DB→FE 신규 community 화면·탭 왕복·hidden polling의 종단 검증은 **미실시**다. 타입·번들 빌드 통과가 화면 회귀 통과를 뜻하지 않는다.
- 기존 정적 경로 확인 범위: report 탭/analysis run/API client·global envelope와 errors·PackageNames/검색·DB FK·PDF 변경·compose 설정. 실제 생태계·기능 비교의 모든 오류 조합이나 PDF 시각 비교는 미실시.
- JDK HttpClient, 2MiB 응답 cap(213 Spec §7), 상수 설정 클래스, 단일 인스턴스 registry, fake GMS 사용은 승인된 선택이다. 이러한 기술 선택 자체를 버그로 세지 않는다. 시간 제한·실패 표기 등 요구된 동작의 누락은 별도다.

## 남은 인수 증거

50 동일 package/50 서로 다른 package 병렬 요청, 실제 DB connection/lock 지연 및 취소 후 commit 차단, 재시작 전체 wire·역할 복원, 로그 sentinel, HTTP body 취소 후 worker 회복, seed 파일 전체 실행은 수정 후 인수 항목이다. 이번 반례의 좁은 실패를 전체 부하·실연결 통과로 확대하지 않는다.

C1 GMS 실제 I/O·prompt·사람 의미 평가, C6 secret/운영/부하, FE316 화면 연동은 외부 gate. 승인된 구현·mock 시험·실DB·실외부 자료를 따로 기록한다. Jira315의 최종 완료 선언은 아직 할 수 없다.

## 실행 증거

[38개 시험별 결과](evidence/probe-results.json), [101개 community 소스·시험 파일 목록과 SHA-256](evidence/community-file-inventory.json), [재현 방법·검증 제한](evidence/README.md), [Phase 5 수정 Spec](../specs/S15P21A506-315-community-integration-acceptance.md).

파일 목록은 탐색/변경 범위 고정용이다. 모든 파일에 독립 runtime 시험을 했다는 뜻이 아니다. 확정 결함의 위치는 위 경로·기준 commit을 기준으로 읽는다.
