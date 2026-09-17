# Phase 기록 — S15P21A506-373 5단계: 하이라이트 요약(반응 최다 댓글+유지관리자 답글+주변 댓글)

> **정상적인 Researcher→Spec→승인 절차를 따르지 않았다** — 4단계(Map-Reduce) 실측 도중
> 시연 시간·비용이 감당 안 되는 게 드러나, 오세진 님과 실시간 대화로 설계를 여러 차례
> 반복하며 정했다. 이 문서는 사전 Spec이 아니라 **그 결정 과정과 결과를 사후에 기록**한
> 것이다 — `docs/for_community/AGENTS.md`의 Workflow Rule 위반을 인지하고 남긴다(시연
> 임박 상황에서의 예외적 처리).

## 배경 — 왜 Map-Reduce(4단계)를 버렸는가

[4단계 Spec](../specs/S15P21A506-373-step4-map-reduce.md)·
[4단계 Phase 기록](S15P21A506-373-step4-map-reduce.md)대로 구현·병합까지 마친 뒤,
2026-09-16~17 실사용(로컬에서 실제 웹앱 띄워 axios/vite/express/rollup 등으로 반복
확인)으로 다음이 드러났다.

- 이슈 하나가 크면 배치(Map) 5회 + Reduce 1회, 최대 **호출 6회**까지 늘어 시간·GMS
  크레딧 소모가 컸다(axios 실측 기준 합계 약 26,000토큰/이슈, 여러 차례 재시도까지
  더하면 훨씬 큼).
- 시연이 목적인 프로젝트인데, 텍스트 검증(`plain()`)에 걸려 "확인된 제목·수치만 있고
  요약은 없습니다" 메시지가 뜨는 이슈가 잦아, 정작 보여줄 콘텐츠가 부족했다.
- 오세진 님이 "가장 반응 많은 댓글 + 그에 대한 maintainer 답글 + 주변 댓글 하나(최대
  3개)만 보여주고, 그 대신 예산을 확실히 아끼자"는 방향을 제시했고, 실측으로 비교한 뒤
  채택했다.

## 무엇으로 바꿨는가

- **입력 선택**: `CommunitySummarySourceBundle.highlights(CollectedIssue)`(신규) —
  반응 최다 댓글 1개 + 그 이후 첫 유지관리자(OWNER/MEMBER/COLLABORATOR) 답글 1개 +
  (있으면) 그 답글 이후 첫 댓글 1개, 최대 3개. 유지관리자 답글이 없으면 반응 1·2순위
  댓글로 2개만 채운다. 댓글당 clip을 4,000→2,000자로 낮춰 3개를 담아도 이슈당 최악
  입력을 작게 유지한다.
- **오케스트레이션**: `CommunityMapReduceSummarizer`를 `CommunityHighlightSummarizer`로
  이름을 바꾸고(더 이상 Map-Reduce를 하지 않으므로), 이슈 크기와 무관하게 항상
  `highlights()` bundle로 `BoundedCommunitySummarizer` 단일 호출만 한다. 배치 분해
  (`batches()`)·Map/Reduce 오케스트레이션(`mapReduce()`/`unionBundle()`)·
  `CommunitySummarizer.reduce()`/`BatchSummary`·`GmsCommunitySummarizer.reduce()`와
  그 스키마/프롬프트 빌더는 전부 **삭제**했다(죽은 코드 — `필요 없는 것은 지운다`).
- **prompt·schema**: 하이라이트 전용으로 다시 썼다 — flow 최대 3단계(주어진 댓글마다
  1단계), messages 최대 3개, summary_support 최대 4개(ISSUE_BODY + 댓글 3개). "모든
  flow 단계는 예외 없이 flow_support 근거가 있어야 한다"를 명시해, 근거 없는 단계 때문에
  검증 전체가 실패하는 사례(rollup 실측으로 발견)를 막았다.
- **텍스트 검증 완화**: `CommunitySummaryValidator`에 `stripLinks` 추가 — `<`/`>`(HTML,
  XSS 방어)는 그대로 거부하되 URL·마크다운 링크는 "(링크 생략)"으로 지우고 나머지
  텍스트는 통과시킨다. 검증 실패 원인도 `require()`마다 구체적 사유를 로그로 남기도록
  고쳤다(이전엔 크기만 찍혀 원인 추적이 안 됐다).
- **모델·타임아웃**: `GMS_MODEL=gpt-5.4-mini`로 고정(실측상 `gpt-5-mini`보다 확연히
  빠름). `GmsCommunitySummarizer.MAX_CALL_TIMEOUT` 15→30초,
  `CommunityProperties.TOTAL_BUDGET` 30→35초, `MAX_OUTPUT_TOKENS` 4096→3072(1536은
  너무 타이트해 `incomplete_reason=max_output_tokens`로 잘림을 실측으로 확인).
- **댓글 수집 병렬화**: `IssueCollectionService.collect()`가 선택된 이슈들의 댓글을
  순차로 수집하던 것을 `CompletableFuture`로 동시 디스패치하도록 바꿨다(GMS 호출은
  이미 병렬인데 그 앞 수집 단계가 병목이었다). `GitHubRateLimitException`이
  `CompletionException`에 감싸여 기존 catch를 피해가는 회귀를 `joinUnwrapping`으로
  막았다. 테스트용 `FakeHttpServer`가 기본 executor(단일 스레드)라 동시성 시험 자체가
  무의미했던 것도 발견해 가상 스레드 executor로 바꿨다.
- **GMS worker 수**: 배치가 없어지며 필요량이 줄어 `SUMMARIZER_WORKER_COUNT`를
  12(Map-Reduce 대비 상향값)에서 4로, 큐도 16→8로 다시 낮췄다(이슈 최대 2개 동시
  디스패치 기준 + 여유).

## 실측 결과

| 시점 | 조건 | 결과 |
| --- | --- | --- |
| Map-Reduce, gpt-5-mini | vite | 29.5초, 검증 실패 다수(`max_output_tokens`) |
| 하이라이트, gpt-5-mini | vite | 8.7초, 검증 실패 1건(`max_output_tokens`, 3072로 상향 후 해소) |
| 하이라이트, gpt-5.4-mini | express | **6.2초**, 2건 중 1건 검증 실패(`flowSupport[2] empty`) |
| 하이라이트, gpt-5.4-mini + flow_support 필수 prompt | express, rollup | 각 **8.7초**, 검증 실패 없음, 흐름 3단계·메시지 최대 3개까지 채움 |

## 완료 판단 기준 대조 (Jira S15P21A506-373, 정본은 Jira)

원래 계획 문서(§5)가 정의한 "0~4단계"의 4단계(Map-Reduce)는 구현·테스트·리뷰를 거쳐
**병합됐다가 실사용 평가로 되돌려졌다** — 완료 판단 기준의 "구현·테스트·리뷰를 거쳐
병합된다"는 4단계 자체로는 충족했지만, 최종적으로 채택된 설계는 계획 문서 밖의
새 방향(5단계, 이 문서)이다. Jira 완료 판단 기준 중 "zod #479/#372를 포함한 대용량
댓글 이슈에서 요약 성공률이 실측으로 개선됐음을 확인한다"는 이번 5단계 실측(express·
rollup·vite 등, 검증 실패 0건까지 도달)으로 사실상 충족됐다고 본다 — 다만 zod 저장소
자체로 재확인은 아직 안 했다.

## 남은 위험, 다음에 할 것

- zod #479/#372로 최종 재확인 아직 안 함(다른 저장소로는 확인 완료).
- 운영 환경변수 `GMS_MODEL`이 `gpt-5.4-mini`인지 확인 필요(외부 의존성, 인프라 담당) —
  이번 튜닝값(`MAX_OUTPUT_TOKENS`·`MAX_CALL_TIMEOUT`·`TOTAL_BUDGET`)은 이 모델 기준
  실측이라, 운영에 다른 모델이 설정돼 있으면 다시 확인이 필요하다.
- GMS 공유 조직 계정 quota 확인은 여전히 미착수(4단계 Spec 때부터 보류 상태 유지).
- 정식 Spec 없이 진행한 점은 이 문서로 사후 보완했지만, 다음에 비슷한 실시간 튜닝이
  필요하면 최소한 "결정 요약"만이라도 진행 중에 남기는 걸 권장.
