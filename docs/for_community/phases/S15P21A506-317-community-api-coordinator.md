# Phase 4 완료 기록 — S15P21A506-317 커뮤니티 API 계약·제한 갱신·결과 게시

Spec: [`../specs/S15P21A506-317.md`](../specs/S15P21A506-317.md) · 브랜치:
`api/feat/S15P21A506-317-community-api-coordinator` (base: 212 브랜치 tip)

## 구현한 것 (3단계 커밋, 승인된 계획대로)

**1/3 — DTO·설정·GMS 경계** (`691efc8`)

- `CommunityProperties` — 상수 클래스로 시작(2026-09-11 사용자 결정, `application.yaml`
  미변경). 이슈/댓글 상한(`MAX_ISSUE_COUNT`·`MAX_COMMENTS_PER_ISSUE`)은 code-review 이후
  추가하고 212의 실제 상한과 같음을 계약 시험으로 고정(아래 참고)
- `refresh/{RefreshTrigger, RefreshStatus, RefreshStage}` — `RefreshStage`는 5단계 중
  `COMMENTS`·`PUBLISHING`만 구현계획 §API 예시에 실제 문자열이 있고 나머지 3개
  (`REPOSITORY_VERIFY`·`ISSUE_SEARCH`·`GMS`)는 같은 명명 스타일로 추정 — **Swagger·Notion
  정본과 맞춰야 할 항목**
- `dto/*` — 구현계획 §API 응답 예시 그대로의 wire record 묶음, `AuthorRoleMapper`
- `CommunitySummarizer`/`FakeCommunitySummarizer`/`TopicSummary` — GMS 실연동은 이 Phase
  범위 밖(Jira 원문 명시), fake만 제공

**2/3 — 동시성 제어** (`e86c607`, code-review 수정 `8e82435`)

- `RefreshTask` — "TAB_OPENED queue4·대기20초"와 "실행20초"를 admission 시점부터 시작하는
  **단일 20초 예산**으로 해석(큐 대기 시간도 소진) — 213/212가 이미 "남은 시간을 매개변수로
  받는다"는 계약이라 이 해석이 그대로 들어맞는다
- `RefreshTaskRegistry` — `ConcurrentHashMap.compute()` 기반 single-flight, 완료 10분 보존
- `StartTokenBucket` — 표준 토큰 버킷, `refund()`(code-review 이후 추가)
- `RefreshAdmissionCoordinator` — 세마포어(2)+토큰 버킷(10/분·burst4)+대기 큐(4)+고정
  worker 2개 조율. 큐에 넣을 때 `work.apply(task)`를 즉시 호출해 완성된 `Runnable`을
  저장한다 — 처음 설계는 dequeue 시점에 넘겨받은 콜백으로 다시 만들려 했는데, 그러면
  A 요청이 큐에 넣은 작업이 B 요청의 permit 반납 시점에 B의 콜백(다른 package_id·repo_url)
  으로 실행되는 버그였다. 코드 리뷰 전 자체 발견·수정(클래스 javadoc에 근거 기록)

**3/3 — orchestrator·컨트롤러·서비스** (`15c7dcd`)

- `CommunityRefreshOrchestrator` — 213→212→(fake)GMS→314 순서. 일시적 실패(`FetchLimited`)는
  314에 아무것도 쓰지 않고 task만 FAILED로 남긴다. 확정적 결과(미확인·모호·미지원 host·
  논의 없음·부분/전체 성공)는 전부 실제 게시 대상 — "결과가 있다"가 "성공"과 같은 뜻이
  아니다. 이슈별 GMS 요약 실패는 그 이슈만 SKIPPED/FAILED로 격리
- `CommunityService` — admission 순서(Spec §3.1: single-flight 참여 → fresh(24h) 재사용,
  단 이전 요약 전체 FAILED면 5분 쿨다운 후 재시도 허용 → coordinator.admit()) 조립.
  용량 초과는 이전 결과 유무로 FAILED/RESULT를 가른다
- `CommunityController` — `POST /api/packages/community/refresh`, `GET
  /api/packages/community`. `name`/`trigger` 검증은 스프링 기본 예외 변환에 맡겨 기존
  `GlobalExceptionHandler`의 V001/V004를 그대로 재사용. 두 응답 모두 `no-store`(이
  저장소에서 처음 추가하는 헤더)
- `CommunityPackageLookup` — `package.name → package_id/repo_url`. `PackageQueryRepository`
  (다른 명세 소유)에 얹지 않고 같은 방식(JdbcTemplate 직접)으로 새로 둠
- `CommunityConfig` — 213/212 HTTP client·서비스·refresh 동시성 계층·orchestrator를 실제
  Spring 빈으로 처음 연결. `GITHUB_COMMUNITY_TOKEN` 없어도 core startup은 막히지 않음
  (213 클라이언트가 이미 그렇게 설계됨, Jira "설정 누락은 새 작업만 막는다" 기준 충족).
  `RefreshAdmissionCoordinator.shutdown()`은 이름이 Spring의 추론 destroy 메서드와 일치해
  별도 지정 없이 컨텍스트 종료 시 호출됨

## Verify Loop 결과

- **Test**: `./gradlew clean test integrationTest` → `BUILD SUCCESSFUL` (314·213·212 포함
  전체 회귀 없음). 단위 60개 이상(`RefreshTaskRegistryTest`·`StartTokenBucketTest`·
  `RefreshAdmissionCoordinatorTest` 11개·`CommunityRefreshOrchestratorTest` 13개·
  `CommunityServiceTest` 9개 등) + 통합 5개(`CommunityControllerIntegrationTest`, 314와
  같은 `DisposableTestDatabase` 재사용, POST→백그라운드 완료 폴링→GET 전체 경로)
- **Mockito를 새로 들이지 않음**(이 저장소 기존 관례 — 지금까지 어떤 테스트도 Mockito를
  쓰지 않았다). 213/212/314의 public 메서드가 `final`이 아닌 점을 이용해 하위 클래스
  대역(`Stub*`·`InMemory*`)으로 실제 네트워크·DB 없이 orchestrator/service를 검증
- **Review**: `/code-review`(전체 diff) — 10건 발견, 이번 Phase가 만든 코드의 결함 4건은
  즉시 수정(커밋 `8e82435`), 213/212의 기존 파일에 있는 별개 결함 2건은 이 Phase 범위
  밖이라 완료 기록에만 남김(아래 "남은 것" 참고), 나머지 4건은 이미 문서화된 의도적 절충
  이거나 저위험 효율성 항목으로 그대로 둠
  1. **(수정)** `RefreshAdmissionCoordinator`가 `registry.size()`만으로 용량을 판단해
     이미 자기 자리를 차지한(terminal) package의 재시도까지 잘못 거절 — `createOrJoin()`의
     `compute()`는 같은 key를 덮어쓸 뿐 늘리지 않는다는 사실을 반영해 수정
  2. **(수정)** 같은 package로 동시 요청이 경합해 registry 등록에 진 쪽도 실행 permit은
     돌려주면서 시작 토큰은 버리던 문제 — `StartTokenBucket.refund()` 추가. 중복 탭·더블
     클릭 트래픽이 전역 토큰 예산을 조용히 갉아먹어 **다른** package의 정상 요청까지
     거절될 수 있었다
  3. **(수정)** `RefreshTask.markCapacityLimited()`가 `errorCode`를 비워 둬서, 대기 큐
     만료로 이 상태가 되는 경로가 동기 거절 경로(`CommunityService.buildRejectedResponse`)
     와 다른 응답을 주고 있었다 — `CommunityErrorCode.CAPACITY_LIMITED`로 채움
  4. **(수정)** `CommunityProperties`의 이슈/댓글 상한이 212의 실제 상한과 같다는
     javadoc의 약속을 실제 계약 시험(`CommunityDataLimitsContractTest`)으로 채움(전에는
     시험이 없었다)
  5. **(문서만 보완, 코드는 그대로)** `CommunitySummarizer`는 "동시성 2로 독립 호출"을
     약속하지만 `CommunityRefreshOrchestrator.summarizeAndPublish`는 지금 순차 for
     루프다. `FakeCommunitySummarizer`가 즉시 반환하는 지금은 예산에 영향이 없지만, 실제
     GMS 클라이언트가 들어오면 20초 예산을 앞당겨 소진시킬 수 있다 — javadoc에 간극을
     명시하고 실제 병렬화는 후속 작업으로 남김
  6. **(범위 밖, 완료 기록에만 기록)** `IssueCollectionService.collect()`(212, 기존 파일)가
     선택된 이슈를 순회하는 도중 시간 예산이 떨어지면, 그 전에 이미 수집해 둔
     `topics`를 전부 버리고 `FetchLimited`(전체 실패)만 반환한다 — 부분 성공
     (`Success(topics, limitations)`)으로 승격할 수 있는데 못 하고 있다. 213/212 파일을
     고치지 않는다는 이번 Phase 제약 때문에 고치지 않았다. **후속 Jira 이슈 제안**
  7. **(범위 밖, 완료 기록에만 기록)** `CommentWindowResolver`(212, 기존 파일)의
     `new BigInteger(sourceCommentId)`가 무방비라, GitHub 응답의 댓글 `id`가 비정상이면
     `NumberFormatException`이 `IssueCollectionService`의 이슈 단위 격리(`TRUNCATED`)를
     건너뛰고 전체 refresh를 깨뜨릴 수 있다. 같은 이유로 이번 Phase에서 고치지 않음.
     **후속 Jira 이슈 제안**
  8. **(그대로 둠, 이미 문서화된 절충)** `CommunityRefreshOrchestrator.classify()`가
     213/212의 자유 텍스트 `reason()`을 `retryAt` 유무 + 일부 문자열로 분류 — 213/212에
     구조화된 에러 타입이 없어 생기는 근본적 제약이라 이미 클래스 javadoc에 상세히
     기록돼 있음
  9. **(그대로 둠, 저위험 효율성)** `CommunityService`가 같은 요청 안에서
     `registry.find()`/`snapshotRepository.findByPackageId()`를 여러 번 재조회 — registry는
     최대 128개 in-memory 스캔, DB 조회는 PK 단건 조회라 비용이 작음. 필요해지면 Phase 5나
     별도 성능 작업에서 최적화
  10. **(범위 밖, 완료 기록에만 기록)** `GitHubIssueSearchClient`/`GitHubIssueCommentsClient`
      (212, 기존 파일)의 rate-limit 판정·재시도 로직이 근접 복제돼 있음(212 자체에서도
      `GitHubRepositoryClient`와 일부 중복 — 213 리뷰 때 "기존 병합 코드는 건드리지
      않는다"는 사용자 결정으로 남겨 둔 것과 같은 종류). 이번 Phase가 새로 만든 코드가
      아니라 손대지 않음
- **Verify(Jira 완료 판단 기준 대조, Spec §4)**:
  - [x] wire 3종(progress/failed/success) — `CommunityControllerIntegrationTest`,
        `RefreshAdmissionCoordinatorTest`/`CommunityRefreshOrchestratorTest`의 상태별 시험
  - [x] POST 두 trigger, GET 수집 금지(코드 구조상 `getStatus`는 admission 경로를
        전혀 부르지 않음), 양쪽 no-store + 기존 envelope + snake_case —
        `CommunityControllerIntegrationTest`(메시지 컨버터를 운영과 같은 snake_case
        `ObjectMapper`로 맞춰 확인)
  - [x] admission 순서(§3.1) 전부 — `RefreshAdmissionCoordinatorTest`(11개)·
        `CommunityServiceTest`(9개)
  - [x] single-flight, worker 2개, TAB_OPENED 큐4·대기, ANALYSIS_CONFIRMED 무대기 거절,
        registry 128·완료 10분 보존, 실행 20초·게시 2초 예약(314가 이미 구현) —
        `RefreshAdmissionCoordinatorTest`·`RefreshTaskRegistryTest`
  - [x] fresh24h 재사용·7d 비노출·summary FAILED 완료+5분·외부 retry_at 우선 —
        `CommunityServiceTest`
  - [x] 새 task 202 / 기존 참여·거절 200, V001/V004/C006/S001 정확한 매핑, null 직렬화,
        no-store — `CommunityControllerIntegrationTest`
  - [x] C1(GMS)/C6(인프라) 미연결을 실연동 완료로 표시하지 않음 —
        `FakeCommunitySummarizer` 그대로 사용, 이 문서와 코드 javadoc에 명시
  - [x] 설정 누락은 새 작업만 막고 core startup·기존 fresh 결과·active task는 막지 않음 —
        `GITHUB_COMMUNITY_TOKEN` 없이 `PickageApplicationTests`(전체 컨텍스트 로드) 통과 확인
  - [x] raw 예외·prompt·응답·인증을 전역 로그에 흘리지 않음 — `GlobalExceptionHandler`
        재사용(수정 없음), orchestrator는 실패 사유를 `errorCode`로만 응답에 노출

## 알려진 단순화 (Swagger·Notion 정본과 맞춰야 할 항목 포함)

- `RefreshStage`의 `REPOSITORY_VERIFY`·`ISSUE_SEARCH`·`GMS` wire 이름은 구현계획 §API
  예시에 없어 추정했다(Stage 1 시점에 이미 기록, 재확인 필요)
- `RefreshStage.ISSUE_SEARCH`를 실제로 쓰지 않는다 — 212의 `collect()`가 검색+댓글 수집을
  한 호출로 묶어 그 경계를 이 Phase가 관찰할 수 없다. `COMMENTS` 하나로 두 활동을 나타냄
- 저장 payload의 `lookbackDays`는 항상 180으로 기록한다 — 212의 공개 계약이 365일 확장
  여부를 노출하지 않고, 이 값은 API 응답에도 없는 저장 전용 감사 필드라 213/212 파일을
  고치지 않는 이번 Phase 제약 안에서는 정확히 복원할 수 없다
- GMS 요약 호출이 순차다(위 code-review 5번) — 실제 GMS 연동 시 재검토 필요

## 213·212·314와의 관계

- 이 Phase가 셋을 실제로 조합하는 유일한 지점이다 — `CommunityRefreshOrchestrator`가
  세 Phase의 공개 진입점(`RepositoryVerificationService.verify`·
  `IssueCollectionService.collect`·`CommunitySnapshotRepository.upsert`)만 생성자로
  조립해서 부른다
- 213·212의 기존 파일은 수정하지 않았다(가시성 변경도 없음, 213/212 자체가 이미
  Phase 3에서 필요한 만큼 공개해 둠). 상수 하나(`CommunityProperties`의 이슈/댓글 상한)만
  212의 값과 의도적으로 중복시키고 계약 시험으로 어긋남을 잡는다
- 314의 `CommunitySnapshotRepository`도 수정하지 않았다 — `CommunityRefreshOrchestrator`가
  `CommunitySnapshotRow`/payload record를 그대로 만들어 넘긴다

## 남은 것 / 다음 Phase(315)에 넘기는 것

- 위 code-review 6·7번(212의 예산 소진 시 부분 결과 폐기, 댓글 ID 파싱 무방비) — 후속
  Jira 이슈로 분리 제안, 사용자 확인 필요
- `RefreshStage`의 추정 wire 이름 3개 — Swagger·Notion 정본 확정 시 재확인
- GMS 실제 Responses API 연동 — 현재 Jira에 없음, 필요 시 새 이슈
- `GITHUB_COMMUNITY_TOKEN`/`GMS_API_KEY` 실제 값 운영 주입 방식 — 인프라 경계, 이 Phase가
  정하지 않음
- 동시성 시험은 단위/통합 시험으로 잡을 수 있는 것까지만 했다(2026-09-11 사용자 결정) —
  운영 수준 부하 시험은 Phase 5(315, 통합 인수)의 몫

## 커밋 전 최종 확인

- 3단계 커밋 각각 컴파일·관련 테스트가 되는 상태로 커밋(Spec §7 승인 사항)
- 변경 파일이 Spec §2 범위(`domain/community/**` 신규 파일 + `CommunityProperties`·
  `CommunityConfig` 보강)를 벗어나지 않음 — 213·212·314의 기존 파일 수정 없음
- `/code-review` 발견 사항 중 이번 Phase 범위 안의 4건은 전부 반영하고 재검증(`8e82435`)
