# Pickage GitHub 커뮤니티 — 대용량 이슈 요약 개선 계획

> 2026-09-16, 오세진 님 지시로 작성. S15P21A506-368(요약 병렬화)·S15P21A506-370(시간
> 예산 재조정)이 운영 배포·검증까지 끝난 뒤에도, 댓글이 많은 이슈(예: `colinhacks/zod`
> #479 — 88개, #372 — 81개)에서 `SUMMARY_INPUT_LIMITED`("입력 한도로 원문 일부만
> 요약에 사용했습니다")와 `SUMMARY_UNAVAILABLE`("요약을 제공하지 못해 확인된 원문
> 제목과 수치를 표시합니다")이 재현되는 것을 스크린샷으로 확인한 뒤 착수했다.
>
> 이 문서는 **계획 문서이며 구현 문서가 아니다.** 어떤 코드도 이 문서 작성 중에
> 바꾸지 않았다. `docs/history/0923_0917_pickage_final_set_archive/for_community/AGENTS.md`가 정한 "PRD/Spec 원본은 바로 고치지
> 않고 무엇을·왜 바꿀지 먼저 제안한다" 규칙에 따라, 이 문서는
> [`Pickage_GitHub커뮤니티_구현계획_260908.md`](Pickage_GitHub커뮤니티_구현계획_260908.md)
> (이하 "본 PRD")를 대체하지 않고 그 위에 얹는 **제안**이다. 실제 구현은 이 문서가
> 사람 재검수를 거쳐 승인된 뒤, `phases/README.md`의 WIP=1 Phase 순서에 새 Phase로
> 편입되어야 시작한다(현재 Phase 5=S15P21A506-315가 아직 "진행 중"이므로 그 뒤).
>
> 근거 표기 규칙: 모든 주장에 정확한 파일 경로와 (가능하면) 줄 번호를 붙인다. 실제로
> 실행/재현하지 않은 것은 "미확인"이라고 명시한다 — 이 프로젝트가 반복적으로 요구해 온
> "화면 표시만으로 완료 간주 금지" 원칙을 계획 문서 자체에도 적용한다.

## 0. 지금까지의 경과 (이 문서가 왜 필요한가)

| 이슈 | 무엇을 고쳤는가 | 상태 |
|---|---|---|
| S15P21A506-368 | `CommunityConfig`의 blank-string 설정값이 조용히 GMS 400을 유발하던 버그 | 배포·검증 완료 |
| S15P21A506-370 | 이슈 2개를 순차 GMS 호출하던 것을 병렬 디스패치로 바꾸고 `TOTAL_BUDGET`을 20s→30s로 올림 | 배포·검증 완료, 운영에서 `axios`/`got` 조합으로 실측 확인 |

370 배포 후에도 `zod` #479(88개 댓글)·#372(81개 댓글)에서 요약이 실패하는 것을
사용자가 새 스크린샷으로 재확인했다. 즉 368·370이 고친 것은 **"이슈 2개를 순차로
부르면 두 번째 이슈가 예산을 못 받는 문제"**였고, 지금 남은 문제는 **"이슈 1개 안에서
댓글 수가 많을 때 입력이 잘리거나 모델이 완결된 JSON을 못 만드는 문제"**다. 서로 다른
증상이므로 서로 다른 코드 경로를 고쳐야 한다 — 이 구분이 아래 §2의 핵심이다.

## 1. 현재 파이프라인의 정밀 분석 (코드 기준)

### 1.1 이슈 1건이 GMS에 도달하기까지

```
IssueCollectionService.collect(...)                         // 최대 100개 댓글 수집
  → CollectedIssue (comments: 최대 100개, 최신순 아님 — 시각순)
  → CommunitySummarySourceBundle.from(issue)                 // ★ 여기서 2차 절단
  → BoundedCommunitySummarizer.summarizeAsync(bundle, budget)
  → GmsCommunitySummarizer.summarize(bundle.issue(), budget) // ★ 단일 GMS 호출
  → CommunitySummaryValidator.validate(bundle, summary)      // 서버 재검증
  → TopicPayload (CommunityRefreshOrchestrator.run 내부)
```

**1차 절단 (수집 단계)**: `CommentWindowResolver`/`IssueSelectionPolicy`가
`CommunityProperties.MAX_COMMENTS_PER_ISSUE = 100`(`CommunityProperties.java:69`)개까지만
수집한다. zod #479(88개)·#372(81개)는 이 상한에 걸리지 않는다 — 즉 **100개 상한 자체는
이번 재현의 원인이 아니다.**

**2차 절단 (`CommunitySummarySourceBundle.from`, `CommunitySummarySourceBundle.java:10-59`)**:
전체 입력을 이슈당 48,000자로 자른다. 제목·본문을 각 4,000자로 clip한 뒤
(`:12`), 남은 예산(`remaining`, `:13-16`)을 **댓글 리스트의 뒤에서부터**
(`for (int i = input.size() - 1; i >= 0; i--)`, `:24`) 채워 넣고 마지막에
`Collections.reverse(selected)`(`:41`)로 시각순으로 되돌린다. 즉 **선택 기준은
"최신 댓글 우선"이며 반응(👍/🎉 등) 수와는 무관하다.** 예산을 다 못 채운 댓글은
통째로 버려진다 — 자르는 게 아니라 배열에서 빠진다(`if (text.isBlank()) continue;`
전에 이미 `remaining`이 바닥나면 `clip`이 빈 문자열을 반환하고 `isBlank()`로
걸러짐). 하나라도 원문 그대로 못 들어가면 `limited=true`가 되고
(`:17-19,27`), 오케스트레이터가 이를 `SUMMARY_INPUT_LIMITED` 제한으로 승격한다
(`CommunityRefreshOrchestrator.java:105-108`).

**GMS 호출 (`GmsCommunitySummarizer.java`)**: 이슈 하나에 system+user 메시지
**한 번**을 보내고(`:137-139`), `max_output_tokens = 2048`(`:48`)로 구조화 출력
(json_schema strict)을 요청한다. 응답은 `status == "completed"`일 때만 처리하고
(`:248`) 그 외의 모든 실패 원인은 `TopicSummary.failed()`로 수렴한다 —
`status != "completed"`이면 `:248` 한 줄에서 바로 실패 처리되고, JSON 자체는
파싱됐지만 페이로드 파싱이 실패하는 경우는 별도로 `:254-256`의 catch 블록에서
실패 처리된다(두 경로가 별개 분기라는 점을 구분해 둔다). **둘 다 로그를 전혀
남기지 않는다** — `log.warn`은 HTTP status가 200이 아닐 때만 호출되고(`:105`),
HTTP 200인데 응답 바디의 `status`가 `incomplete`이거나 페이로드 파싱이
실패하는 경우는 **아무 로그도 남지 않는다.** 이 때문에 지금까지 운영에서
재현된 zod #479/#372 실패가 "경로 A(타임아웃)"·"경로 B(incomplete)"·"경로
C(validator 거부)" 중 정확히 무엇이었는지 사후에 구분할 방법이 없다(§3의
0단계에서 이 로그 공백을 먼저 메운다). `docs/history/0923_0917_pickage_final_set_archive/for_community/GMS_연동_참고.md:36-39`가
이미 "여전히 미확인: `max_output_tokens`(2048) 초과 시 `status`가 `incomplete`로
오는지" 라고 명시해 뒀다 — 이번 재현이 바로 그 미확인 경로를 실제로 밟았을
가능성이 높다(§2에서 근거를 좁힌다).

**검증 (`CommunitySummaryValidator.java`)**: 모델이 지어낸 값(작성자·시각·역할)은
전부 버리고 원문에서 재구성한다는 원칙(`:9`)은 그대로 유효하고, 이번 문제와
직접 충돌하지 않는다 — 스키마 자체(§1.2)나 소스 절단(§1.1) 쪽이 원인이다.

### 1.2 GMS 요청 스키마의 중첩 깊이

`GmsCommunitySummarizer.schema()` (`:183-232`)가 만드는 구조:

```
topic_summary (object, depth 0)
 ├ summary_support: array<sourceRef>            (depth 1 → sourceRef object depth 2)
 ├ flow: array<flowItem>                        (depth 1 → flowItem object depth 2)
 │   └ flowItem.support: array<sourceRef>        (depth 3 → sourceRef object depth 4)
 └ messages: array<messageItem>                 (depth 1 → messageItem object depth 2)
```

`flow[].support[]`가 실질적으로 **object 깊이 4단**(topic_summary → flow item →
support 배열 → sourceRef object)에 이른다. OpenAI Structured Outputs strict 모드의
문서화된 한도는 nesting depth 5, property 100개로 알려져 있다(**출처 표시 보완
필요** — 이 수치는 웹 검색으로 얻은 일반 지식이며, 이 문서 서두가 스스로 정한
"모든 주장에 정확한 근거를 붙인다" 규칙에 맞춰 착수 전 OpenAI 공식 문서 링크로
재확인해야 한다. 이번 재검수에서도 별도로 검증하지 못했다). 이 값이 맞다면
지금 스키마는 절대 한도를 넘지는 않지만 여유가 많지 않다. `docs/history/0923_0917_pickage_final_set_archive/for_community/GMS_연동_참고.md:29-34`가
2026-09-16 실측으로 "중첩 배열/객체 스키마... strict 모드가 그대로 동작함"을 이미
확인했으므로 **스키마 자체가 GMS에서 거부된다는 증거는 없다** — 이 부분은 §3③에서
"낮은 확신, 낮은 리스크의 보험성 변경"으로만 다룬다.

### 1.3 시간 예산과의 상호작용

`CommunityProperties.TOTAL_BUDGET = 30s`(`CommunityProperties.java:38`)를
`RefreshTask`가 소유하고(`RefreshTask.java:21,30,56`), `RefreshAdmissionCoordinator`가
25ms마다 `expire()`를 돌며(`RefreshAdmissionCoordinator.java:38`) 마감을 넘긴
task를 **강제로 인터럽트하고 FAILED로 만든다**(`:124-143,145-148`). 이슈 2개 병렬
호출 시 각 `GmsCommunitySummarizer` 호출의 상한은
`MAX_CALL_TIMEOUT = 15s`(`GmsCommunitySummarizer.java:43`)이고, 실제로는
`clampTimeout`(`:127-131`)이 그 시점의 남은 예산에서 300ms 여유를 뺀 값을 쓴다.
**댓글 88개짜리 입력(최대 48,000자)에 대해 GMS가 15초 안에 완결된 JSON을
끝내지 못하면 `HttpTimeoutException` → `TopicSummary.failed()`로 수렴하고,
이는 화면에 `SUMMARY_UNAVAILABLE`로 나타난다** — 사용자가 본 두 번째 증상과
정확히 일치하는 코드 경로다.

## 2. 근본 원인 ↔ 관측 증상 매핑

| 관측 증상 (문구) | 발생 조건 | 코드 경로 |
|---|---|---|
| `SUMMARY_INPUT_LIMITED`("입력 한도로 원문 일부만 요약에 사용했습니다") | 이슈 1건의 title+body+comments 합이 48,000자를 넘어 오래된 댓글이 통째로 빠짐 | `CommunitySummarySourceBundle.from` (§1.1 2차 절단) |
| `SUMMARY_UNAVAILABLE`("요약을 제공하지 못해...") — 경로 A | GMS가 15초(`MAX_CALL_TIMEOUT`) 안에 응답을 못 끝냄 | `GmsCommunitySummarizer.summarize` 의 `HttpTimeoutException` (`:111-114`) |
| `SUMMARY_UNAVAILABLE` — 경로 B | GMS가 `max_output_tokens=2048`을 넘겨 `status != "completed"` 으로 잘림 (미확인, §7) | `GmsCommunitySummarizer.parseResponse` `:248,250` |
| `SUMMARY_UNAVAILABLE` — 경로 C | 스키마 위반·source 불일치 등으로 `CommunitySummaryValidator`가 거부 | `CommunitySummaryValidator.validate` (`:84-86`) |

**중요한 재평가**: 사용자가 제시한 두 증상은 "느려서" 실패하는 것(시간 예산 문제)과
"입력/출력 용량이 부족해서" 실패하는 것(크기 문제)이 섞여 있다. 뒤에 제안하는 5개
수정안 중 **⑤(백그라운드 분리)는 시간 예산 문제만 해결하고 크기 문제는 그대로
남긴다** — 이 구분을 명시하지 않으면 ⑤만 구현하고 "다 고쳤다"고 오판할 위험이 있다.
그래서 우선순위는 크기 문제(①②③④)를 먼저, 시간 문제(⑤)를 나중에 둔다(§6).

## 3. 수정안 5개 — 코드 변경 지점과 리스크

### 0단계 (신규, 재검수 반영) — 배포 전 무위험 진단 두 가지

①~⑤ 중 어느 것도 아직 "왜 실패했는지"를 확정하지 못한 채 제안됐다(§2의
경로 A/B/C 구분 자체가 추정이다). 코드/운영 변경 없이, 또는 최소한의 코드
변경만으로 §2의 경로를 실측으로 좁힐 수 있는 두 가지를 ①보다 먼저 한다.

1. **진단 로그 추가**: `GmsCommunitySummarizer.parseResponse`(`:241-258`)의
   `status != "completed"` 분기(`:248`)와 페이로드 파싱 실패 분기(`:254-256`)에
   각각 `log.warn`을 추가해 실제 `status` 값과 (있다면) `output` 형태를
   남긴다. 위험이 사실상 0에 가까운 변경(로그 한 줄)이므로 ①③보다도 먼저
   배포해, 이후 단계들이 "정말 이 경로가 원인이었는지"를 운영 로그로 사후
   확인할 수 있게 한다. 이 로그가 없으면 ①(`max_output_tokens` 상향)을
   배포한 뒤에도 그게 실제로 효과가 있었는지 판단할 근거가 없다.
2. **`GmsCommunitySummarizerRealNetworkTest` 확장**: 이 테스트는 실제로
   존재하며(`backend/src/integrationTest/java/.../GmsCommunitySummarizerRealNetworkTest.java`,
   `@EnabledIfEnvironmentVariable(named="GMS_API_KEY", ...)`) 현재는 댓글
   1개짜리 최소 fixture만 쓴다. 여기에 댓글 80~90개 안팎의 합성(fabricated,
   실제 GitHub 이슈가 아닌) fixture를 추가해 실제 GMS를 한 번 호출해 보면,
   §7의 "`max_output_tokens` 초과 시 실제 `status`/`output` 형태" 미확인
   항목을 **운영 배포나 zod 재현 없이, 개발 중에 며칠 안에** 닫을 수 있다.
   원래 이 계획의 §6·§7은 검증 경로로 "zod #479/#372 재수집"만 제시했는데,
   이는 실제 배포 이후에나 가능한 훨씬 비싼 경로이므로 이 저비용 대안을
   먼저 시도한다.

### ① `max_output_tokens` 상향

- **목표**: §2의 "경로 B"(출력 중 JSON이 잘려 `status=incomplete`)를 줄인다.
- **변경 지점**: `GmsCommunitySummarizer.java:48` `MAX_OUTPUT_TOKENS = 2048` 상향
  (예: 4096). `buildRequestBody`(`:133-142`)는 이미 이 상수를 참조하므로 상수만
  바꾸면 된다.
- **리스크**: 낮음. 다만 `MAX_CALL_TIMEOUT=15s`는 그대로이므로, 토큰을 더 많이
  생성하게 하면 응답 시간도 늘어나 §2 "경로 A"(타임아웃)를 오히려 악화시킬 수
  있다 — ①만 단독으로 배포하지 말고 §4(시간 예산 재점검)와 함께 평가한다.
- **미확인**: GMS/gpt-5.4-mini의 실제 max context 한도, 4096 토큰 생성이 15초
  안에 끝나는지는 실측 필요(§7). **이번 재검수로도 못 좁힌 갭**: 48,000자
  입력(§1.1)이 대략 몇 토큰에 해당하는지 어림 환산조차 시도하지 않았다 —
  한국어/영어 혼합 텍스트라 문자당 토큰비가 일정하지 않지만, 최소한 "48,000자
  ≈ 대략 몇만 토큰" 수준의 근사치를 내지 않고는 "입력 자체가 이미 context
  한도에 근접해 있어서 ①(출력 토큰 상향)이 무의미할 가능성"을 배제할 수
  없다. 착수 전 0단계 실측(위)과 함께 이 어림도 해 둔다.

### ② 댓글 선택 기준을 "최신순"에서 "반응 수 기반"으로

- **목표**: §2의 "`SUMMARY_INPUT_LIMITED`" 자체를 줄이거나, 잘리더라도 더
  대표성 있는 댓글이 남게 한다.
- **현재 코드**: `CommunitySummarySourceBundle.from`(`:23-40`)이 배열 뒤(최신)부터
  채우는 단순 반복문. **댓글별 반응 수 필드 자체가 현재 `CollectedComment`
  레코드에 없다** — 확인 결과 `CollectedComment`는
  `sourceCommentId/authorLogin/authorAssociation/isBot/createdAt/body/authorId`만
  가진다(`CommunitySummarySourceBundle.java:32-39`의 재구성 호출부로 필드 목록
  확인). 즉 이 수정은 스코어링 로직 교체만으로 끝나지 않고 **GitHub 댓글 수집
  단계(`GitHubIssueCommentsClient`/`CollectedComment`)부터 `reactions.total_count`를
  새로 끌어와야 하는, ②라는 이름보다 범위가 넓은 변경이다.**
- **변경 지점 (실제 필요 작업)**:
  1. `CollectedComment`에 `reactionCount` 필드 추가 (record이므로 모든 생성
     지점 — `CommunitySummarySourceBundle.java:32-39`, 테스트 fixture들 — 동반 수정)
  2. GitHub Issue Comments API 응답에서 `reactions.total_count`를 파싱하는 지점을
     `GitHubIssueCommentsClient`에서 찾아 추가 — **재검수로 확인: 현재
     `GitHubIssueCommentsClient.parseComments`는 `reactions` 필드를 전혀
     파싱하지 않는다(이 계획의 원래 "미확인"이 실제로 "맞다, 없다"로
     확정됨).** 다만 리스크를 낮추는 선례가 이미 저장소에 있다 —
     `CollectedIssue`는 **이슈 레벨** `reactionCount`를 이미 가지고 있고
     (`CommunityRefreshOrchestrator.java:149`, `CommunityService.java`의
     결과 조립부에서 사용), 이는 `GitHubIssueSearchClient.java:153-170`이
     GitHub Search API 응답의 `reactions.total_count`를 파싱해 채운 것이다.
     즉 "GitHub JSON에서 `reactions.total_count` 꺼내기"는 이미 동작하는
     패턴이 이 저장소에 있으므로, 댓글 쪽에 같은 패턴을 적용하는 것은
     설계를 새로 고안하는 일이 아니라 기존 패턴을 재사용하는 일에 가깝다.
     또한 GitHub Issue Comments API는 댓글을 가져오는 같은 응답 안에
     `reactions` 객체를 이미 포함해서 주므로(현재도 호출 중인 엔드포인트),
     **추가 GitHub API 호출이나 rate limit 소모 없이** 파싱 로직만
     추가하면 된다 — 아래 "리스크" 평가에 반영.
  3. `CommunitySummarySourceBundle.from`의 선택 로직을 "최신순"에서 "반응 수
     내림차순, 동률은 최신순"으로 교체 — 다만 **본문(issue body)과 이슈 작성자
     최초 댓글처럼 반응이 적어도 맥락상 필수인 댓글**을 무조건 배제하지 않도록
     선택 정책을 설계해야 한다(순수 반응 수 정렬만 하면 "질문은 잘리고 인기
     댓글만 남는" 왜곡이 생길 수 있음 — 이 설계는 Spec 단계에서 fixture로
     검증 필요).
- **PRD와의 관계 — 2026-09-16 승인·반영 완료**: 본 PRD §4.1은 원래 "제목·본문
  우선, 나머지는 최신 댓글부터 예산에 담은 뒤 모델에는 시각순으로 전달한다"라고
  **명시적으로 "최신 댓글 우선"을 계약으로 정해 두었다.** 즉 ②는 버그 수정이
  아니라 PRD §4.1의 명시적 계약을 바꾸는 변경이었다 — `docs/history/0923_0917_pickage_final_set_archive/for_community/AGENTS.md`의
  "PRD 변경은 먼저 제안" 규칙에 따라 이 계획 문서가 제안했고, 사용자가 승인해
  본 PRD §4.1을 반응 수 기반 문구로 이미 갱신했다(§8). **다만 코드는 아직
  이 갱신을 반영하지 않았다** — PRD 문구와 실제 `CommunitySummarySourceBundle.from`
  동작이 373의 2단계 구현 전까지는 서로 다른 상태이며, PRD §4.1 자체에도 이
  괴리를 명시해 뒀다.
- **리스크**: 중간. GitHub API 응답 파싱 확장 + PRD 계약 문구 변경 + 신규 정렬
  fixture 테스트가 함께 필요해 ①③보다 작업량이 크다. 다만 위에서 확인했듯
  파싱 확장 자체는 기존 패턴 재사용이고 추가 API 호출도 없으므로, "중간"
  리스크의 대부분은 파싱 난이도가 아니라 **PRD 계약 문구 변경에 대한 사용자
  승인**과 **선택 정책 설계(질문/맥락 필수 댓글을 반응 수로만 걸러내지
  않는 것)** 쪽에 있다.

### ③ 스키마 평탄화 (닉네임 기반 평면 목록)

- **목표**: §1.2의 4단 중첩을 낮춰 strict 모드 거부 가능성을 원천적으로
  줄인다(다만 §1.2에서 확인했듯 **현재 거부된다는 직접 증거는 없다** — 예방적
  조치).
- **변경 지점**: `GmsCommunitySummarizer.schema()`(`:183-232`). `flow[].support`
  중첩을 없애려면 `flow`의 각 항목에 `support`를 직접 두지 않고,
  `summary_support`처럼 최상위에 `flow_support: array<{flow_index, type, id}>`
  형태의 평면 배열로 옮겨 `flowIndex`로 역참조하게 바꾼다. 이 경우
  `toTopicSummary`(`:273-306`)의 파싱 로직과
  `CommunitySummaryValidator.validate`의 `flowSupport` 검증(`:28-30,35`)도
  함께 바뀌어야 한다 — **`TopicSummary`/`TopicSummary.SourceRef` 레코드 자체의
  구조(`TopicSummary.java`)까지는 안 바꿔도 되지만, `flowSupport`를
  `List<List<SourceRef>>`(현재, `:16`)로 유지할지 평면 리스트+인덱스로 바꿀지
  결정해야 한다.**
- **리스크**: 낮음~중간. 스키마·파싱·검증 3곳을 함께 바꿔야 하므로 회귀
  테스트(`GmsCommunitySummarizerTest`, `CommunityContractReviewTest`)를
  전부 다시 통과시켜야 한다. 실제 효과가 있는지 **검증 불가능**(재현 조건을
  만들 수 없음 — GMS가 스키마를 거부하는 사례를 아직 한 번도 관측 못함)이므로
  우선순위는 ①②보다 낮게 둔다(§6).

### ④ Map-Reduce 재구조화

- **목표**: 이슈 하나의 입력이 48,000자를 넘거나(§2 `SUMMARY_INPUT_LIMITED`)
  모델이 한 번에 소화하기엔 댓글 수가 너무 많을 때, 댓글을 배치로 나눠 여러 번
  GMS를 호출한 뒤 합성한다.
- **현재 구조와의 충돌**: 지금은 `CommunityRefreshOrchestrator.run`이 **이슈당
  정확히 GMS 호출 1번**을 가정한다(`:117-119`,
  `pending.stream().map(p -> summarizer.summarizeAsync(...))`). Map-Reduce로
  바꾸면 이슈 1건이 배치 수만큼(N번) 호출 + 합성 1번, 총 N+1번 호출이 되고,
  **이 전체가 여전히 `task.collectionTimeLeft()`(`CommunityRefreshOrchestrator.java:116`)
  하나의 예산 안에서 끝나야 한다.** 88개 댓글을 배치 20개씩 5묶음으로 나누면
  5+1번의 호출이 그 예산 안에 들어가야 하므로 처리량이 부족해질 위험이 크다.
  **재검수로 정정**: 이 처리량 문제를 푸는 것은 ⑤-A(§4, blocking POST를
  background+폴링으로 바꾸는 것)가 아니다 — ⑤-A는 호출 방식만 바꿀 뿐 GMS의
  실제 생성 시간이나 처리량을 줄여주지 않는다(`BoundedCommunitySummarizer`의
  `ThreadPoolExecutor(2, 2, ...)`(`BoundedCommunitySummarizer.java:9-10`)가
  동시 실행 상한 2를 이미 고정하고 있고, ⑤-A는 이 상한을 건드리지 않는다).
  ④가 예산 안에서 성립하려면 실제로는 **①(더 큰 `MAX_CONCURRENT_EXECUTIONS`/
  `BoundedCommunitySummarizer` worker 수로 배치를 동시에 처리)이나 §4의
  `TOTAL_BUDGET` 자체를 늘리는 것**이 필요할 가능성이 높다 — "⑤-A가 먼저
  깔려 있어야 한다"는 단정은 원래 초안의 과장이었고, 정확히는 **"④를
  구조 변경만으로 두 배치 전략 없이 예산 안에 넣으려면, ⑤-A와는 별개로
  동시성 상향 또는 예산 재조정이 필요할 수 있다"**로 완화한다. 즉 ④와 ⑤-A
  사이에 구현 순서상의 하드 의존은 없다 — 다만 ④ 착수 시 반드시 동시성/예산
  여유를 함께 재설계해야 한다는 점은 여전히 유효하다.
- **변경 범위(개략)**: `BoundedCommunitySummarizer`/`GmsCommunitySummarizer`
  사이에 새 배치 분해·합성 레이어 추가, `CommunitySummarySourceBundle`을
  "이슈 전체 48,000자 예산"에서 "배치별 예산"으로 재정의, `TopicSummary` 조립
  로직을 배치 결과 병합으로 확장, `CommunitySummaryValidator`는 병합된 최종
  결과에 대해 지금과 동일한 규칙(support 존재성 등)을 적용 — **검증 계약
  자체는 안 바뀌어도 되지만, 배치 경계를 넘는 `support` 참조(배치 A에서 만든
  flow가 배치 B의 댓글을 인용하는 경우)를 어떻게 막을지 새로 설계해야 한다.**
- **리스크**: 높음. 가장 큰 구조 변경이고, PRD §4의 "환각 방지" 계약
  (`Pickage_GitHub커뮤니티_구현계획_260908.md:188-212`)을 배치 병합 상황에서도
  똑같이 지켜야 한다는 제약이 새로 생긴다. **재검수로 추가된 항목**: N+1배
  호출은 팀 전체가 공유하는 GMS 조직 계정에도 영향을 준다 —
  `docs/history/0923_0917_pickage_final_set_archive/for_community/GMS_연동_참고.md:24-27`가 "SSAFY 조직 계정 하나를 팀
  전체가 공유...공유 자원이라는 점은 인지해 둘 것"이라고 이미 경고했다.
  실측된 rate limit 헤더(`X-Ratelimit-Limit-Requests: 10000` 등)가 넉넉해
  당장 한도에 걸릴 가능성은 낮아 보이지만, 이슈 2개 x 배치 5~6개 x
  동시 refresh 여러 개가 겹치면 팀의 다른 GMS 사용(예: 다른 기능 개발 중
  테스트 호출)과 공유 quota를 경합할 수 있다는 점을 착수 전 인프라 담당과
  확인한다. 이번 계획에서는 **설계 방향만 제시하고 상세 스펙은 별도 Phase
  Spec에서 작성**하도록 범위를 한정한다(§6).

### ⑤ GMS `background: true` 비동기 분리

이 항목이 **가장 큰 구조적 리스크**를 가진다. 아래 §4에서 별도로 깊게 다룬다.

## 4. ⑤ 심층 분석 — 왜 "그냥 비동기로 돌리면 된다"가 아닌가

### 4.1 현재 아키텍처가 "동기 1회성 소유권" 모델이라는 증거

1. **`RefreshTask.requirePublishable()`**(`RefreshTask.java:107-113`)은
   `status != RUNNING || isTerminal() || isPastDeadline() || 인터럽트됨`이면
   무조건 예외를 던진다. 즉 **task의 `budget`(기본 30초)이 지난 뒤에는 그
   task로 아무것도 게시할 수 없다** — 설계상 불가능이 아니라 코드로 강제된
   불가능이다.
2. **`RefreshAdmissionCoordinator`의 25ms watchdog**(`:38,124-143`)이 RUNNING
   상태의 모든 task를 감시하다가 마감을 넘기면 **스레드를 강제 인터럽트하고
   즉시 FAILED로 만든다**(`:136-139`, `deadline()` → `markFailed(...)`). 즉
   GMS 호출이 아무리 오래 걸려도, task 자체가 30초를 넘기면 그 실행 스레드는
   강제로 끊긴다 — "그냥 기다리게 두면" 되는 구조가 아니다.
3. **`CommunitySnapshotPublisher.publish`**(`CommunitySnapshotPublisher.java:19-20`)의
   첫 줄이 `task.requirePublishable()`이다. 게시 자체가 살아있는 `RefreshTask`
   객체의 소유권 확인에 강결합돼 있다.
4. **DB 스키마 자체가 "진행 중" 상태를 허용하지 않는다.**
   `DataStatus.java:6-8`의 javadoc: "일시적인 외부 호출 실패...나 진행 중
   상태는 완성 결과가 아니므로 여기 없다 — 그런 상태는 이 테이블에 아예
   저장하지 않는다." `community_snapshot.data_status` CHECK 제약
   (`V5__community.sql`)도 6개 완결 상태만 허용한다.
5. **설계 결정 `DEC-COMMUNITY-20260909-01`**
   (`Pickage_GitHub커뮤니티_구현계획_260908.md:730`): "기준 하나, fallback
   금지, **단일 snapshot**, bounded Spring→GMS 예외."
6. **본 PRD §12.1의 명시적 합격 기준**
   (`Pickage_GitHub커뮤니티_구현계획_260908.md:652-653`):
   - `npm/GitHub/GMS 정지·queue timeout·shutdown` → `deadline·소유권 지킴,
     뒤늦은 publish 없음`
   - `재시작 후 미게시 작업` → `GET IDLE, 영구 PROCESSING 없음`

   이 두 줄은 **지금 이미 통과하는 테스트로 지켜지고 있다**
   (`CommunityAcceptanceIntegrationTest.R11_lateConnectionIsClosedWithoutPublication`,
   `R11_publisherLockTimeoutPreservesOldResultAndRecovers`, `R12_restartPreservesCompleteWireContract`
   — 세 테스트 모두 이전 세션에서 전문을 확인함). **GMS 호출이 요청/Task의
   생명주기를 넘어 살아남아 나중에 결과를 써 넣는 것은, 정의상 "뒤늦은
   publish"이고 이 합격 기준을 정면으로 위반한다.**
7. **FE 폴링도 QUEUED/RUNNING 두 상태에만 반응한다.**
   `frontend/src/api/queries/index.ts:223-227`의 `refetchInterval`은
   `status !== 'QUEUED' && status !== 'RUNNING'`이면 폴링을 끈다. 새로운
   "백그라운드 대기" 상태를 wire에 추가하려면 이 스위치, `RefreshStatus` enum,
   `CommunityProgress`/`toProgressModel`(FE, `community-report-tab.tsx`가
   import) 전부를 동반 수정해야 폴링이 멈추지 않는다.

### 4.2 결론 — ⑤를 두 단계로 쪼갠다

위 7가지 증거는 전부 "task 예산을 넘어 GMS 완료를 기다리는" **진짜 의미의
비동기 분리(이하 ⑤-B)**가 기존 계약 6개와 충돌한다는 것을 보여준다. 반면
"GMS 호출 자체를 `background:true`로 시작하고, **같은 30초 예산 안에서**
동기 대기 대신 폴링으로 기다리는" 방식(이하 ⑤-A)은 위 7가지 중 **어느 것도
위반하지 않는다** — task 소유권, 예산, DB 스키마, wire 상태 전부 지금 그대로다.

| | ⑤-A: 예산 내 폴링 | ⑤-B: 진짜 cross-request 분리 |
|---|---|---|
| 무엇이 바뀌나 | `GmsCommunitySummarizer.summarize`가 1회 blocking POST 대신 `background:true`로 시작 → `GET /v1/responses/{id}`를 짧은 간격으로 폴링, 여전히 같은 `budget` 안에서 | 예산 안에서는 PARTIAL 상태로 우선 게시하고, 별도 스케줄러가 나중에 완료된 GMS 응답을 받아 같은 snapshot 행을 다시 갱신 |
| 해결하는 증상 | §2 "경로 A"(15초 타임아웃)의 일부 — GMS 서버 측 지연이 원인일 때만 도움. **입력이 48,000자를 넘는 문제(`SUMMARY_INPUT_LIMITED`)는 그대로 남는다. 호출 방식만 바꾸는 것이라 처리량을 늘리지 않으므로 ④(Map-Reduce)의 N+1 호출 처리량 문제도 해결하지 않는다(재검수로 정정 — §3④ 참고)** | 이론상 "얼마나 걸리든" 완료를 기다릴 수 있음 |
| 기존 계약 충돌 | 없음 | §4.1의 4~7번과 직접 충돌 — 새 DB 마이그레이션(진행 중 상태 허용), `RefreshTask`/`RefreshAdmissionCoordinator` 소유권 모델 재설계, 새 wire 상태, FE 폴링 로직 확장이 전부 필요 |
| 리스크 | 낮음 | 높음 — PRD 재작성 수준. **이번 계획에서는 설계만 제시하고 구현하지 않는다** |
| 권고 | 채택 (§6 순서 3) | 보류. 필요성이 실측으로 입증되면(§7) 별도 PRD 개정 제안으로 사용자 승인 후 별도 Phase로 진행 |

⑤-B를 굳이 진행해야 한다면 최소 설계 방향(구현하지 않음, 참고용): 기존
`community_snapshot` 테이블은 §4.1의 4번 원칙(완결 결과만 저장)을 유지한 채
그대로 두고, "이 snapshot의 일부 topic이 아직 백그라운드에서 처리 중"이라는
사실은 **완전히 별도의 신규 테이블**(예: `community_pending_summary` — 신규
migration, 다음 빈 번호는 이번 조사 시점 기준 V8)에 `response_id`만 저장하고,
별도 스케줄드 잡이 그 테이블을 폴링해 완료되면 `CommunitySnapshotRepository`의
UPDATE 경로(현재의 `RefreshTask` 소유권 체크를 우회하는 새 메서드)로 topic만
갱신한다. 이는 "단일 snapshot" 결정과 "뒤늦은 publish 없음" 기준을 글자 그대로
지키려는 절충안이지 검증된 설계는 아니다 — 실제로 착수하게 되면 이 자체를
Spec 단계에서 다시 정밀 설계해야 한다.

## 5. 우선순위와 실행 순서

```
0단계 (즉시, 위험 거의 0): 진단 로그 추가 + GmsCommunitySummarizerRealNetworkTest에
   대형 합성 fixture 추가해 실제 GMS 호출로 §7의 incomplete/refusal 경로를 먼저 좁힌다
   → 이 결과로 §2의 경로 A/B/C 중 실제 원인을 좁힌 뒤 1단계 착수(재검수 반영)

1단계 (즉시, 위험 낮음): ① max_output_tokens 상향 + ③ 스키마 평탄화
   → 배포 후 zod #479/#372로 재현 시도, 개선 여부 관측(0단계 로그로 사후 확인 가능)

2단계 (PRD §4.1 계약 변경 필요, 사용자 재확인 후): ② 반응 수 기반 댓글 선택
   → 파싱 확장 자체는 기존 GitHubIssueSearchClient 패턴 재사용(§3② 참고), 리스크의
     핵심은 PRD 계약 문구 변경 승인과 선택 정책 설계

3단계 (⑤-A만, 예산 내 폴링): GMS 호출을 background:true + 폴링으로 전환
   → §2 "경로 A"(타임아웃)에만 도움. 여전히 실패하면 4단계로
   → **2026-09-16 폐기**: 구현·실측 결과 이 GMS 프록시가 폴링 엔드포인트를
     지원하지 않아(§7) 되돌렸다. 4단계로 직행한다.

4단계 (구조 변경, Spec 별도 작성): ④ Map-Reduce
   → 3단계(⑤-A)를 전제조건으로 두지 않는다(재검수로 정정 — ⑤-A는 호출 방식만
     바꿀 뿐 처리량을 늘리지 않는다). 대신 착수 시 MAX_CONCURRENT_EXECUTIONS/
     BoundedCommunitySummarizer worker 수 또는 TOTAL_BUDGET 자체의 상향을
     함께 설계해야 예산 안에서 N+1 호출이 성립한다. GMS 공유 조직 계정에 대한
     quota 영향도 인프라 담당과 확인한다(§3④)

보류: ⑤-B (진짜 cross-request 비동기) — §4.2의 근거로 이번 계획에서는 미착수.
   0~4단계로도 zod급 사례가 계속 실패하면 그때 별도 PRD 개정으로 재제안한다.
```

각 단계는 `docs/history/0923_0917_pickage_final_set_archive/for_community/AGENTS.md`의 Phase/Spec 절차를 따라 새 Jira
하위 이슈(에픽 S15P21A506-323)로 등록하고, 착수 전 Spec을 작성해 승인받는다 —
이번 계획 문서는 PRD 갱신 제안이지 Spec을 대신하지 않는다.

## 6. 테스트 계획 (단계별 최소 추가분)

| 단계 | 추가/수정할 테스트 |
|---|---|
| 0 | `GmsCommunitySummarizerRealNetworkTest`에 댓글 80~90개 안팎 합성 fixture 추가(§3 0단계) — `GMS_API_KEY` 있을 때만 실행, 기본 테스트에는 포함 안 함 |
| ① | `GmsCommunitySummarizerTest`에 큰 `max_output_tokens` 값으로도 기존 fixture가 통과하는지 회귀만 확인(값 자체는 mock 서버라 실제 토큰 소비를 검증 못함 — 실제 영향은 `GmsCommunitySummarizerRealNetworkTest`로만 확인 가능, §7) |
| ② | `CommunitySummarySourceBundle`의 선택 순서를 반응 수 fixture로 새로 검증하는 테스트 추가(현재 이런 테스트 없음). `CollectedComment` 필드 추가에 따른 전 테스트 fixture 갱신 |
| ③ | `GmsCommunitySummarizerTest`의 스키마 검증 테스트, `CommunitySummaryValidator`의 `flowSupport` 검증 테스트 갱신, `CommunityContractReviewTest`의 계약 라운드트립 재확인 |
| ⑤-A | `GmsCommunitySummarizerTest`에 background 폴링 mock 경로 추가, `BoundedCommunitySummarizer`의 예산 소진 시 폴링 취소 테스트 |
| ④ | 배치 경계를 넘는 source 참조가 거부되는지, 배치 일부 실패 시 병합 결과가 PARTIAL로 내려가는지 — 새 fixture 다수 필요 |

모든 단계에서 `CommunityAcceptanceIntegrationTest`의 R11/R12 계열(재시작·소유권·
뒤늦은 publish 거부)은 **손대지 않고 그대로 통과**해야 한다 — 이게 깨지면 §4.1의
불변식이 깨졌다는 뜻이므로 해당 변경은 되돌린다.

## 7. 미확인 — 착수 전 반드시 실측해야 하는 것

- `max_output_tokens` 초과 시 GMS 응답의 실제 `status` 값과 `output` 형태
  (`incomplete`인지, 부분 텍스트가 오는지) — 실제 대형 이슈로 아직 시험 안 함
  (`GMS_연동_참고.md:36-39`에 이미 기록된 미확인 사항). **재검수로 저비용
  검증 경로 확보**: zod 재현이나 운영 배포 없이 §3 0단계(`GmsCommunitySummarizerRealNetworkTest`
  확장)로 개발 중에 직접 닫을 수 있다 — 더 이상 "미확인 상태로 착수"가
  아니라 "착수 전 0단계에서 반드시 닫는다"로 격상한다.
- ~~`GitHubIssueCommentsClient`가 현재 `reactions.total_count`를 이미 파싱하고
  있는지~~ — **재검수로 확인 완료**: 파싱하지 않는다(§3②). 더 이상 미확인이
  아니다.
- ~~GMS(`gms.ssafy.io` 프록시)가 OpenAI `background: true` 파라미터를 그대로
  통과시키는지, `GET /v1/responses/{id}` 폴링 엔드포인트를 프록시하는지~~ —
  **2026-09-16, S15P21A506-373 3단계 실측으로 확인 완료(부정적 결과)**:
  `background:true`는 받아주지만(`queued`+`id` 응답), `GET
  {endpoint}/{id}` 폴링은 매번 HTTP 500 — 이 GMS 프록시는 폴링 엔드포인트를
  지원하지 않는다. ⑤-A(3단계) 구현을 완료해 검증했으나 이 결과로 **폐기하고
  되돌렸다**(배포 시 요약이 100% 실패하게 됨) — 오세진 님 결정, 상세 근거는
  [`specs/S15P21A506-373-step3-background-polling.md`](specs/S15P21A506-373-step3-background-polling.md)
  §6과 [`phases/S15P21A506-373-step3-background-polling-abandoned.md`](phases/S15P21A506-373-step3-background-polling-abandoned.md).
  향후 GMS 프록시가 바뀌거나 다른 폴링 URL 형태가 확인되지 않는 한 재시도하지
  않는다.
- gpt-5.4-mini의 실제 max context 토큰 수, 4096 output 토큰 생성이 15초
  타임아웃 안에 들어오는지
- zod #479/#372를 1~3단계 적용 후 실제로 재수집했을 때 결과가 개선되는지 —
  이 문서 작성 시점까지 아직 어떤 코드도 바뀌지 않았으므로 당연히 미확인

## 8. 사용자 확인이 필요한 결정 — 2026-09-16 결정됨

- **②의 PRD §4.1 "최신 댓글 우선" 문구 변경: 승인.** 본 PRD §4.1을 반응 수 기반
  선택으로 갱신했다(현재 코드는 아직 미반영 — 373의 2단계에서 구현).
- **⑤-B(진짜 비동기 분리) 보류: 동의.** 0~4단계 이후에도 필요하면 별도 PRD
  개정 이슈로 재제안한다.
- **Jira 분할: 4단계 전체를 하나의 이슈로.** 각 단계를 별도 하위 이슈로
  쪼개지 않고, [S15P21A506-373](https://ssafy.atlassian.net/browse/S15P21A506-373)
  하나에 0~4단계를 전부 기록해 진행한다(담당 오세진, Story Point 5).
- 기존 커뮤니티 관련 Jira 이슈 중 유일하게 미완료였던
  [S15P21A506-315](https://ssafy.atlassian.net/browse/S15P21A506-315)(통합 인수)는
  완료 처리했고, 그 검수 과정에서 발견된 이번 문제를 S15P21A506-373으로 분리했다.

## 9. 요구사항 추적

이 계획은 본 PRD §13의 요구사항 ID를 새로 만들지 않는다. 관련 기존 ID:
확장-03-R07~R10(§4·6, 근거/역할/순서), 확장-03-R12(§3~4, 수집/요약 한계),
확장-03-R18(부분 결과) — ①~④는 전부 이 범위 안의 **구현 방식 개선**이고
새 요구사항을 추가하지 않는다. ⑤-A도 마찬가지(시간 예산 안에서의 구현
디테일). ⑤-B만이 §5(원자 snapshot)·§11(파트 경계) 수준의 새 요구사항을
필요로 할 수 있으므로, 착수 시점에 별도 ID(예: 확장-03-R19)를 본 PRD에
추가하는 절차를 밟는다.

---

## 재검수 기록

2026-09-16, 이 문서 작성과 독립된(별도 컨텍스트로 새로 시작한) 에이전트가
문서가 인용한 모든 코드·PRD 파일을 직접 다시 읽고 줄 번호·인용문·동작
설명을 원문과 전부 대조하는 방식으로 재검수했다(단순 키워드 매칭이 아니라
§4의 아키텍처 논증 자체가 실제로 성립하는지까지 검토하도록 명시적으로
요청함).

**결론**: §4(⑤-A/⑤-B 분리 논증, 7가지 근거)를 포함해 문서의 파일:줄 인용은
검수자가 확인한 범위 내에서 전부 정확했다 — "이 정도로 줄 단위 인용이 실제
코드와 어긋나지 않는 계획 문서는 흔치 않다"는 평가를 받았다. §4를 구현
순서의 근거로 삼는 것 자체는 승인됐다.

**반영한 지적 (8건, 중요도순)**:

1. **(가장 중요)** ④(Map-Reduce)가 ⑤-A(예산 내 폴링)를 전제조건으로 한다는
   원래 주장은 인과관계가 틀렸다 — ⑤-A는 호출 방식만 바꿀 뿐 처리량을
   늘리지 않는다. §3④·§4.2·§5를 수정해 "⑤-A 선행" 대신 "동시성/예산 상향이
   별도로 필요할 수 있다"로 정정했다.
2. GMS 응답의 `incomplete`/파싱 실패 경로에 로그가 전혀 없어 실제 실패
   원인을 사후 구분할 수 없다는 지적 — §3에 "0단계(진단 로그)"를 신설해
   반영했다.
3. `GmsCommunitySummarizerRealNetworkTest`를 확장하면 §7의 핵심 미확인
   사항을 운영 배포 없이 저비용으로 닫을 수 있다는 지적 — 같은 0단계에
   합쳐 반영하고 §5·§6·§7을 갱신했다.
4. `CollectedComment`에 반응 수가 없다는 원래 "미확인"은 재검수로 "맞다,
   없다"로 확정됐고, 동시에 `CollectedIssue`(이슈 레벨)에는 이미 같은
   패턴(`GitHubIssueSearchClient`의 `reactions.total_count` 파싱)이 존재해
   ②의 파싱 난이도를 낮추는 선례가 된다는 지적 — §3②에 반영, 리스크 평가를
   "파싱 난이도"에서 "PRD 계약 변경 승인·선택 정책 설계"로 재조정했다.
5. ④의 N+1 호출이 팀 공유 GMS 조직 계정 quota에 주는 영향이 누락됐다는
   지적 — §3④에 반영했다.
6. 48,000자 입력 예산과 실제 토큰 한도를 대조한 적이 없다는 지적 — §3①에
   미확인 항목으로 명시했다.
7. §1.1에서 "incomplete 상태" 경로와 "JSON 파싱 실패" 경로 인용이 섞였다는
   지적 — §1.1 본문을 두 경로로 명확히 분리해 재작성했다.
8. §1.2의 OpenAI strict 모드 한도(depth 5, property 100)에 출처 표시가
   없다는 지적 — 이 문서 자신의 근거 표기 규칙과 어긋나므로 "출처 표시 보완
   필요, 착수 전 공식 문서로 재확인" 문구를 추가했다(수치 자체를 검증하지는
   못했다 — 여전히 미확인으로 남는다).

재검수 원문 전체는 이 계획 문서의 작성 세션 기록에 남아 있다.
