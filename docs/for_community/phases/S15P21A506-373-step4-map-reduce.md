# Phase 6, 4단계 — S15P21A506-373 Map-Reduce 재구조화(④)

Spec: [`specs/S15P21A506-373-step4-map-reduce.md`](../specs/S15P21A506-373-step4-map-reduce.md)
(2026-09-16 승인 — AskUserQuestion 2건, Reduce 방식·배치 상수 포함 4가지 결정 전부 승인)

## 무엇을 구현했는가

이슈 요약 입력이 단일 48,000자 예산을 넘는 경우(`CommunitySummarySourceBundle.from(issue).limited()
== true`)만 배치로 나눠 배치별 GMS 호출(Map) + 배치별 검증 → 검증된 부분 결과만 합성하는
GMS 호출(Reduce) 1회로 최종 `TopicSummary`를 만든다. 그 외 이슈는 기존 단일 호출 경로를
그대로 쓴다(회귀 없음 — 기존 유닛 테스트가 전부 이 경로만 타는 것으로 확인됨).

- **추가**: `CommunityMapReduceSummarizer.java` — Map(배치별 `BoundedCommunitySummarizer.mapAsync`
  동시 디스패치 + 배치별 `CommunitySummaryValidator.validate`) → Reduce
  (`BoundedCommunitySummarizer.reduce`) 오케스트레이션. 최종 검증은 하지 않고 `SummaryAttempt
  (bundle, raw)`를 돌려줘 `CommunityRefreshOrchestrator`가 기존과 동일하게 "호출자가 쓴
  bundle로 한 번만 검증한다" 계약을 유지한다.
- **수정**: `CommunitySummarySourceBundle.batches(CollectedIssue)` 추가 — 기존 `priorityOrder`
  (작성자 최초 댓글 특례 → 반응 수 내림차순 → 동률 시 최신)를 재사용해 배치당
  `SUMMARY_BATCH_CHAR_BUDGET`(12,000자) 예산으로 나누고, `MAX_SUMMARY_BATCHES`(5)를 넘는
  댓글은 버리며 마지막 배치를 `limited=true`로 표시한다.
- **수정**: `CommunitySummarizer` 인터페이스에 `reduce(List<BatchSummary>, Duration)` 추가 —
  **default 메서드**로 둬서 기존 람다 기반 테스트 대역(`(issue, budget) -> ...`)과의 함수형
  인터페이스 호환을 깨지 않았다.
- **수정**: `GmsCommunitySummarizer.reduce(...)` 구현 — Reduce 전용 system prompt +
  json_schema. `id` 필드를 자유 문자열이 아니라 그 호출에 실제로 주어진 source id들의
  **enum**으로 제한해(strict json_schema) 모델이 없는 id를 지어내도 스키마 자체가 거부하게
  했다(1차 방어) — 최종 검증(2차 방어)은 `CommunityMapReduceSummarizer`가 배치들의 source id
  합집합(union bundle)에 대해 기존 `CommunitySummaryValidator.validate`를 그대로 호출한다.
- **수정**: `BoundedCommunitySummarizer` — worker 수·큐 용량을 하드코딩된 `2, 2, ...,
  ArrayBlockingQueue<>(2)`에서 `CommunityProperties.SUMMARIZER_WORKER_COUNT`(6)·
  `SUMMARIZER_QUEUE_CAPACITY`(8)로 연결했다. **주의**: Spec 작성 시점엔 기존
  `EXECUTOR_WORKER_COUNT`(=2)를 재사용할 계획이었으나, 코딩 중 그 상수가 이미
  `RefreshAdmissionCoordinator`(refresh task 자체의 동시 실행 풀)가 쓰고 있는 걸 발견해
  — 재사용하면 무관한 두 풀이 한 상수로 묶여 버리므로 — 새 전용 상수 2개를 대신 추가했다.
- **수정**: `CommunityRefreshOrchestrator` — GMS 호출 대상을 `p.sources()`(48,000자 단일
  bundle)에서 `p.issue()`(원본, 미클립)로 바꿨다. 배치가 원본 댓글 전체를 다시 봐야 하는데
  기존처럼 이미 48,000자로 잘린 bundle을 넘기면 그 이상 복구할 게 없어지기 때문이다. 최종
  검증 대상 bundle도 `CommunityMapReduceSummarizer`가 돌려주는 `SummaryAttempt.bundle()`로
  바꿨다(비배치 경로는 단일 bundle, 배치 경로는 union bundle).
- **수정**: `CommunityConfig`(운영 배선)·`CommunityControllerIntegrationTest`(통합 테스트
  전용 배선) 둘 다 `CommunityMapReduceSummarizer` bean을 추가하고 `CommunityRefreshOrchestrator`
  생성자에 그걸 넘기도록 갱신.

## 실행한 테스트와 결과

- `./gradlew test --tests "com.ssafy.pickage.domain.community.*"` — 전부 통과. 신규:
  `CommunityMapReduceSummarizerTest`(5개), `CommunitySummarySourceBundleTest`에 `batches()`
  케이스 3개 추가, `GmsCommunitySummarizerTest`에 `reduce()` 케이스 4개 추가.
- `./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"` — **17/17 통과**
  (R11/R12 계열 포함, 로컬 postgres 컨테이너 사용 — 이 세션에서는 Docker Desktop 데몬이
  처음엔 꺼져 있어 오세진 님이 직접 켠 뒤 재시도해 통과 확인함).
- `./gradlew integrationTest --tests "com.ssafy.pickage.domain.community.*"` — 커뮤니티 도메인
  전체 integrationTest 통과.

## 리뷰 결과 (`/code-review medium`)

2건 지적, 둘 다 반영·재확인:

1. **(높음)** `CommunityMapReduceSummarizer.unionBundle()`이 `batches.get(0)`을 빈 리스트에
   호출할 수 있어 크래시 위험 — 댓글이 하나도 없거나 전부 blank인 이슈가 본문만으로도
   `limited=true`가 되면(예: 본문이 4,000자를 넘는데 댓글이 0개) `batches()`가 빈 리스트를
   돌려주는데, 이걸 그대로 `mapReduce`에 넘기면 `unionBundle`이
   `IndexOutOfBoundsException`을 던져 **해당 이슈뿐 아니라 refresh 전체**가
   `CommunityRefreshOrchestrator`의 최상위 catch로 떨어져 실패한다(기존 단일 호출 경로였다면
   그 이슈만 `SUMMARY_UNAVAILABLE`로 저하됐을 상황). **수정**: `summarizeAsync`에서
   `batches.isEmpty()`면 단일 호출 경로로 폴백하도록 바꿨다. 회귀 테스트
   (`댓글이_없어도_본문만으로_limited인_이슈는_배치_대신_단일_호출_경로로_떨어진다`) 추가.
2. **(중간)** `perCallBudget`이 남은 예산을 배치 수+1로 나눠 Map 호출에 줬는데, 배치는
   **동시에** 디스패치되므로 이렇게 나누면 실제로 쓸 수 있는 시간보다 훨씬 적은 타임아웃을
   각 호출에 주게 돼(예: 5배치+예산 4초 → 배치당 ~667ms) 예산이 남았는데도 불필요하게
   실패로 처리되는 경우가 늘어난다. **수정**: Map 호출에는 예산을 나누지 않고 남은 전체를
   그대로 넘기고(개별 호출 상한은 `GmsCommunitySummarizer.MAX_CALL_TIMEOUT`이 따로 건다),
   Map이 실제로 걸린 시간을 측정해 그만큼 뺀 **진짜 남은 예산**을 Reduce에 넘기도록 바꿨다.

수정 후 유닛·통합 테스트 재실행, 전부 통과 확인.

## Jira "완료 판단 기준" 대조 (4단계 관련分만 — 정본은 Jira)

- "계획 문서 §5의 0~4단계가 각각 구현·테스트·리뷰를 거쳐 병합된다" — 구현·테스트·`/code-review`
  까지 완료. **병합(MR)은 오세진 님 지시로 이번 라운드에 하지 않는다** — 로컬 커밋까지만.
- "각 단계에서 `CommunityAcceptanceIntegrationTest`의 R11/R12 계열이 그대로 통과한다" —
  17/17 통과로 충족.
- "zod #479/#372를 포함한 대용량 댓글 이슈에서 요약 성공률이 실측으로 개선됐음을 확인한다" —
  **미확인**. 이번 구현은 fake/mock GMS로만 검증했다(Spec §4 "외부 의존성" 결정 그대로).
  `GMS_API_KEY`가 있을 때 실네트워크로 zod 재수집해 비교하는 절차는 아직 진행하지 않았다.
- "⑤-B는 이번 범위에서 미착수 상태로 남긴다" — 변경 없음, 그대로 미착수.

## 남은 위험, 다음 Phase에 넘길 것

- **실측 미확인**: 위 항목대로 zod #479/#372 재수집 비교가 아직 없다. `GMS_API_KEY`가 준비되면
  0단계와 같은 방식으로 실네트워크 확인이 필요하다.
- **예산 실측 미확인**: Spec §3 "동시성·예산"이 예상한 대로 worker 6개·배치 상한 5로 30초
  예산 안에 N+1 호출이 들어가는지는 fake 테스트로는 확인이 안 된다 — 실네트워크(또는 부하
  유사 테스트)로 확인 전까지는 `TOTAL_BUDGET` 상향 필요 여부를 판단할 수 없다.
- **GMS 공유 조직 계정 quota**: Spec 결정대로 이번 Phase에서는 확인하지 않았다. 4단계
  구현·병합 이후 인프라 담당과 별도로 진행해야 한다.
- **MR 미생성**: 오세진 님이 "나중에 직접 확인하고 지시하겠다"고 해 이번엔 push·MR을 만들지
  않았다. 이 브랜치(`api/feat/S15P21A506-373-map-reduce-summary`)는 로컬에만 있다.
