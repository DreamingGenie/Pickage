# Spec — S15P21A506-373 3단계 (⑤-A: GMS background:true + 예산 내 폴링)

> 0~2단계: [step0](S15P21A506-373-step0-diagnostics.md)·[step1](S15P21A506-373-step1-max-tokens-and-schema-flatten.md)·
> [step2](S15P21A506-373-step2-reaction-based-selection.md). 3단계는 오세진 님의 "진행하자"
> 지시(2026-09-16)로 착수한다. Jira 본문 "선행 작업·인계"가 3단계 착수 전 별도 Spec을
> 명시적으로 요구한다.

## 0. 대상 Phase

- Jira: [S15P21A506-373](https://ssafy.atlassian.net/browse/S15P21A506-373) — 3단계만
- 브랜치: 0~2단계와 같은 브랜치(`api/feat/S15P21A506-373-max-output-tokens-and-schema-flatten`)
  위에 이어서 커밋 — 여전히 미push, "커밋까지만" 지시 유지.
- 구현계획 문서 참고 절: [`../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md`](../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md)
  §3 "⑤ GMS background:true 비동기 분리", §4(⑤-A/⑤-B 심층 분석), §5 3단계
- 선행 Phase: 2단계(같은 브랜치, 로컬 커밋 완료)

## 1. 작업 개요

- 작업명 / 목표: `GmsCommunitySummarizer.summarize`가 1회 blocking POST 대신
  `background: true`로 요청을 시작하고, **같은 호출 예산(`clampTimeout(budget)`, 최대
  15초) 안에서** 짧은 간격으로 `GET {endpoint}/{id}`를 폴링해 완료를 기다린다.
  `RefreshTask`/`RefreshAdmissionCoordinator` 소유권 모델, DB 스키마, wire 상태는
  **전혀 바꾸지 않는다** — 계획 문서 §4.2가 "⑤-A는 위 7가지 계약 중 어느 것도 위반하지
  않는다"고 명시한 그대로, 이 Spec도 그 경계를 유지한다.
- Jira 이슈 "필요한 이유" 요약(재인용): 대용량 이슈에서 GMS 처리 시간 자체가 15초를
  넘겨 타임아웃(§2 "경로 A")으로 실패하는 경우, blocking POST 대신 폴링 방식이 서버
  측 지연을 흡수할 여지가 있는지 확인한다.
- **범위의 한계(계획 문서 §4.2 표에서 재인용)**: ⑤-A는 "호출 방식만 바꿀 뿐 GMS의
  실제 생성 시간이나 처리량을 줄여주지 않는다." 입력이 48,000자를 넘는 문제나 GMS 자체
  처리 시간이 15초를 넘는 경우는 여전히 실패한다 — 이 Spec은 "경로 A의 **일부**(HTTP
  연결 유지 방식 때문에 생기는 불필요한 타임아웃)"만 다룬다는 것을 분명히 해 둔다.

## 2. 변경 대상 (Scope)

- **수정될 파일**
  - `backend/src/main/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizer.java`
    - `buildRequestBody`(`:134-143`)에 `root.put("background", true)` 추가.
    - `summarize`(`:91-120`)를 아래 §3 흐름으로 재구성 — POST 응답이 이미 터미널
      상태(`completed` 등)면 폴링 없이 그대로 진행(짧은 처리라면 background 모드에서도
      즉시 완료 상태로 올 가능성 대비 — 계획 문서·GMS_연동_참고.md 어디에도 이 케이스가
      배제된다는 근거가 없어 방어적으로 처리).
    - 신규 `awaitCompletion(CollectedIssue, String initialJson, Instant deadline)` —
      폴링 루프. 신규 `isTerminal(String status)`, `remaining(Instant deadline)` 헬퍼.
    - 신규 인스턴스 필드 `pollInterval`(기본 500ms) + 패키지 전용 `setPollInterval`
      (시험 전용, `GitHubIssueCommentsClient.setRateGate`와 같은 기존 패턴 — 실제
      500ms 간격으로 시험하면 느려지므로 테스트에서 줄여 쓴다).
    - `parseResponse`/`toTopicSummary`/`schema()`는 **수정하지 않는다** — 최종 완료된
      JSON의 모양(`status`, `output`)은 이전과 동일하다고 가정한다(백그라운드 완료
      응답도 동기 완료 응답과 같은 envelope라는 전제 — §4 "미확인" 항목 참고).
  - `backend/src/test/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerTest.java`
    — mock 서버로 폴링 흐름 5개 케이스(§5).
  - `docs/for_community/GMS_연동_참고.md` — §7/미확인 목록에 있던 "GMS가 background:true·
    폴링 엔드포인트를 프록시하는지" 항목을 이번 실네트워크 확인 결과로 갱신(§6에서 실행).
- **범위 밖 — 이 Phase에서 하지 않을 일**
  - ⑤-B(진짜 cross-request 비동기) — 계획 문서 §4.2·Jira 완료 판단 기준이 이번 범위
    밖으로 명시.
  - `RefreshTask`/`RefreshAdmissionCoordinator`/DB 마이그레이션/wire 상태 — 전혀 손대지
    않는다.
  - `BoundedCommunitySummarizer`의 동시성(worker 수) — 4단계 항목.

## 3. 아키텍처 / 데이터 흐름

```
summarize(issue, budget)
  deadline = now + clampTimeout(budget)           // 기존과 동일한 예산 계산
  POST {endpoint}  (background:true 추가)          // .timeout(remaining(deadline))
  if status != 200 → failed()                      // 기존과 동일
  json = 응답 바디
  json = awaitCompletion(issue, json, deadline)     // ★ 신규
    root = readTreeOrNull(json)
    if root == null → return json                  // 파싱 실패는 parseResponse가 처리
    if isTerminal(root.status) → return json        // 이미 끝났으면 폴링 안 함
    id = root.id
    if id 없음/blank → 진단 로그 남기고 return json  // 폴링 불가, 있는 그대로 넘겨 FAILED 처리
    while (now < deadline):
      sleep(pollInterval)
      if (now >= deadline) break
      GET {endpoint}/{id}                            // .timeout(remaining(deadline))
      if status != 200 → 진단 로그, return null
      polled = readTreeOrNull(응답 바디)
      if polled == null → return 응답 바디            // 파싱 실패는 parseResponse가 처리
      if isTerminal(polled.status) → return 응답 바디
    return null                                       // 예산 소진 — 완료 못 봄
  if json == null → 진단 로그, return failed()
  return parseResponse(issue, json)                   // 기존과 동일, 무수정
```

- 관련 기존 코드 패턴: `parseResponse`의 `JSON.readTree` try/catch를
  `readTreeOrNull(String)` 공용 private 헬퍼로 추출해 `awaitCompletion`과 공유한다
  (중복 방지 — 지난 두 단계 `/code-review`가 이런 중복을 지적했던 패턴을 미리 피한다).
- `GitHubIssueCommentsClient.setRateGate`(`:41-43`)의 "시험 전용 세터" 패턴을
  `setPollInterval`에 그대로 재사용한다.
- `Thread.sleep(pollInterval)`은 인터럽트 가능 — `RefreshAdmissionCoordinator`의 강제
  인터럽트(예산 초과 시)가 기존과 동일하게 이 sleep도 깨울 수 있다. 이미 있는
  `catch (IOException | InterruptedException e)`가 그대로 처리한다(별도 처리 불필요 —
  §4.1 R05_summaryTimeoutCancelsWorkerAndPoolCanRecover가 이 인터럽트 경로를 이미
  검증하고 있고 이번 변경으로 그 계약이 깨지지 않는지 §5에서 재확인한다).

## 4. 예외 및 엣지 케이스

- Jira 세부 항목 대조: "3단계: GMS 클라이언트를 background:true+폴링으로 전환,
  CommunityAcceptanceIntegrationTest R11/R12 계열 회귀 확인" → §2·§5로 충족.
- id 없이 비-터미널 상태로 응답이 오면(GMS가 background를 지원 안 하거나 다르게
  동작하는 경우) 폴링 없이 그대로 `parseResponse`로 넘어가 `status != completed`
  분기에서 기존 로그와 함께 실패 처리된다 — 새 코드가 이 경우를 흡수하지 못해도 안전
  저하(FAILED)로 수렴하지, 예외를 던지거나 무한 대기하지 않는다.
- 폴링 GET이 비-200이면 첫 실패에서 바로 포기한다(재시도하지 않음) — 초기 POST의
  기존 "비-200이면 즉시 실패" 정책과 대칭.
- 폴링이 예산 안에 끝나지 않으면(`while` 루프가 deadline에 걸려 빠져나옴) `null`을
  반환해 `TopicSummary.failed()`로 수렴 — 기존 `HttpTimeoutException` 경로와 같은
  최종 결과(FAILED), 다만 진단 로그 문구로 "타임아웃"과 "폴링 예산 소진"을 구분한다.
- 외부 의존성(확인 필요): **GMS가 `background:true`를 실제로 지원하는지, `GET
  {endpoint}/{id}` 폴링 엔드포인트를 프록시하는지는 이 Spec 작성 시점까지 미확인이다**
  (`GMS_연동_참고.md`가 이미 이렇게 명시해 둠). §6에서 실네트워크로 이 Phase 안에
  직접 확인한다 — 확인 결과에 따라 구현이 그대로 유효한지, 되돌려야 하는지 판단한다
  (Verify 단계에서 결정, 미리 가정하지 않는다).

## 5. 검증 계획

- [ ] `cd backend && ./gradlew test --tests "*.GmsCommunitySummarizerTest"` — 신규
      케이스 5개:
      1. **초기 응답이 이미 완료 상태면 폴링 없이 바로 파싱** — POST가 completed
         envelope를 바로 주면, poll 경로(GET)를 아예 등록하지 않은 mock 서버로도
         성공해야 한다(폴링을 실제로 안 한다는 것 자체를 이 방식으로 증명).
      2. **정상 폴링**: POST가 `{"status":"queued","id":"resp_1"}` → 1차 poll GET이
         `in_progress` → 2차 poll GET이 `completed` envelope → 최종 `READY`.
      3. **id 없이 비완료 상태**: POST가 `{"status":"queued"}`(id 없음) → 즉시
         `FAILED`(폴링 시도 안 함, 빠르게 끝남).
      4. **폴링 결과가 실패로 끝남**: poll GET이 `{"status":"failed","id":"resp_1"}`
         → `FAILED`.
      5. **예산 안에 완료 못 함**: `setPollInterval(짧은 값)`로 테스트를 빠르게 만들고,
         poll GET이 항상 `in_progress`만 반환하도록 구성 → 작은 `budget`으로 호출 →
         `FAILED`(폴링 타임아웃 경로).
- [ ] `cd backend && ./gradlew test --tests "*.CommunityContractReviewTest"` — 특히
      `R05_summaryTimeoutCancelsWorkerAndPoolCanRecover`(인터럽트 기반 취소 계약)가
      `Thread.sleep` 추가 이후에도 그대로 통과하는지.
- [ ] `cd backend && ./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"`
      (로컬 postgres 필요) — R11/R12 계열 통과.
- [ ] **실네트워크 확인(필수, §4 외부 의존성 항목을 닫기 위해)**:
      `GmsCommunitySummarizerRealNetworkTest`의 기존 두 테스트를 `GMS_API_KEY`로
      재실행 — `background:true` 요청도 실제 GMS가 받아주고, 폴링이 실제로 동작하는지
      확인한다. 두 테스트 모두 기존처럼 `status=READY`로 끝나야 한다(이번엔 그 경로가
      폴링을 거쳐서 나온 결과라는 점이 다르다). **GMS가 background:true를 지원하지
      않으면(예: 즉시 동기 completed로 응답하거나, id 없는 큐 상태로 응답하거나, poll
      엔드포인트가 404) 이 Spec의 §3 방어 로직이 그 상황도 안전하게(READY 또는 진단
      로그와 함께 FAILED) 처리하는지까지 관찰한다** — 실패해도 코드가 무너지지 않는지가
      이 확인의 핵심이다.
- [ ] 격리 테스트 DB: `CommunityAcceptanceIntegrationTest`만 필요, 기존 패턴 그대로.
- [ ] 시크릿 노출 여부: 해당 없음.

## 6. 자체 검증 (승인 요청 전 필수)

- 확인한 실제 파일/패턴:
  - `GmsCommunitySummarizer.java` 전문을 다시 읽어 `summarize`(`:91-120`)·
    `clampTimeout`(`:128-132`)·`buildRequestBody`(`:134-143`)·`parseResponse`(`:257-286`)
    줄 번호를 이 Spec 작성 시점 기준으로 확인. `BoundedHttpReader.send`가
    `request.timeout()`을 그대로 future 대기 시간으로 쓴다는 것을 `BoundedHttpReader.java`
    전문을 읽고 확인 — 각 poll GET에 `.timeout(remaining(deadline))`을 설정하면 그
    대기 시간이 정확히 적용됨을 코드 레벨에서 확인함.
  - `GitHubIssueCommentsClient.java:39-43`의 `setRateGate` "시험 전용 세터" 패턴을
    확인, `setPollInterval`에 그대로 재사용하기로 함.
  - `FakeHttpServer.java` 전문을 읽고 `respondDynamic(path, Function<String,Answer>)`이
    쿼리 문자열과 무관하게 클로저 캡처 상태(예: `AtomicInteger` 호출 횟수)로 응답을
    바꿀 수 있음을 확인 — 폴링 시나리오(1차 in_progress, 2차 completed) mock에 이
    메커니즘을 그대로 쓸 수 있다.
  - `com.sun.net.httpserver.HttpServer.createContext`가 경로별로 별도 등록되므로
    `/v1/responses`(POST)와 `/v1/responses/resp_1`(GET, id 포함 구체 경로)을 같은
    서버에 별도 context로 등록해 두 요청을 구분할 수 있음을 확인함(JDK 문서 근거 —
    가장 구체적인 prefix가 우선).
  - `CommunityContractReviewTest.java:159-190`의
    `R05_summaryTimeoutCancelsWorkerAndPoolCanRecover`를 다시 읽고, 이 테스트가
    `FakeCommunitySummarizer`가 아니라 커스텀 람다로 인터럽트 흐름을 시험하는 것이라
    `GmsCommunitySummarizer` 내부 구현(폴링 유무)과 무관하게 통과함을 확인 — 다만
    회귀로 재실행해 실제로 안 깨짐을 확인하는 것은 §5에 남겨 둠.
  - `docs/for_community/GMS_연동_참고.md`의 "아직 확인 안 된 것"/"미확인" 절에
    background/폴링 항목이 실제로 남아 있음을 재확인(§4 외부 의존성 서술의 근거).
- 발견해 Spec에 반영한 차이: 없음.
- 이 Spec에서 아직 못 정한 것 (사용자 확인 필요 항목): 없음 — 외부 의존성 확인은
  "사용자 확인이 필요한 결정"이 아니라 §5의 Verify 단계에서 직접 실행해 닫을 항목이다
  (0단계와 같은 패턴).

---
**승인**: 2026-09-16, 오세진 님 — "진행하자" 지시로 착수. push·MR은 계속 보류(로컬
커밋까지만). 외부 의존성(GMS의 background/폴링 지원 여부) 확인은 구현 직후 실네트워크
테스트로 이 Phase 안에서 직접 닫는다.
