# Spec — S15P21A506-373 2단계 (반응 수 기반 댓글 선택)

> 0단계: [S15P21A506-373-step0-diagnostics.md](S15P21A506-373-step0-diagnostics.md).
> 1단계: [S15P21A506-373-step1-max-tokens-and-schema-flatten.md](S15P21A506-373-step1-max-tokens-and-schema-flatten.md)
> (로컬 커밋만, 아직 push 안 함). 2단계는 오세진 님의 "이어서 진행해줘, 또 커밋까지만
> 해" 지시(2026-09-16)로 착수한다.

## 0. 대상 Phase

- Jira: [S15P21A506-373](https://ssafy.atlassian.net/browse/S15P21A506-373) — 2단계만
- 브랜치: 1단계와 **같은 브랜치**(`api/feat/S15P21A506-373-max-output-tokens-and-schema-flatten`)
  위에 이어서 커밋한다 — 지시가 "이어서 진행"이고 별도 브랜치 분기 지시가 없었고,
  아직 1단계 자체가 push/MR 전이라 origin에 올라간 기준점이 없다. 새 브랜치를 따면
  1단계 커밋 3개를 다시 베이스로 잡아야 해서 오히려 번거롭다.
- 구현계획 문서 참고 절: [`../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md`](../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md)
  §3 "② 댓글 선택 기준을 최신순에서 반응 수 기반으로"
- PRD 계약(이미 갱신됨): [`../Pickage_GitHub커뮤니티_구현계획_260908.md`](../Pickage_GitHub커뮤니티_구현계획_260908.md)
  §4.1 — "제목·본문 우선, 나머지는 댓글 반응(reaction) 수 내림차순으로 예산에 담은 뒤
  (동률은 최신 우선), 모델에는 시각순으로 전달한다. 반응 수만으로 대표성을 판단하면
  질문·문제 제기 댓글처럼 반응은 적어도 맥락상 필수인 댓글이 잘릴 수 있으므로, 선택
  정책은 순수 반응 수 정렬이 아니라 이 위험을 완화하는 규칙(fixture로 검증)을 포함해야
  한다." — 이 Spec은 그 "위험을 완화하는 규칙"을 구체적으로 정의한다(§3).
- 선행 Phase: 1단계(같은 브랜치, 로컬 커밋 완료)

## 1. 작업 개요

- 작업명 / 목표: `CollectedComment`에 `reactionCount` 추가 → `GitHubIssueCommentsClient`가
  GitHub 응답의 `reactions.total_count`를 파싱해 채움 → `CommunitySummarySourceBundle.from`
  의 48,000자 예산 채우기 순서를 "최신순"에서 "반응 수 내림차순(동률은 최신 우선) +
  이슈 작성자의 최초 댓글은 무조건 우선 포함"으로 교체. 최종적으로 모델에 전달하는
  순서는 여전히 시각순(변경 없음).
- Jira 이슈 "필요한 이유" 요약(재인용): 대용량 이슈에서 반응 수가 높은 과거 댓글이
  최신순 절단으로 통째로 빠지는 문제.

## 2. 변경 대상 (Scope)

- **수정될 파일**
  - `backend/src/main/java/com/ssafy/pickage/domain/community/collection/CollectedComment.java`
    — `int reactionCount` 필드를 끝에 추가(레코드).
  - `backend/src/main/java/com/ssafy/pickage/domain/community/collection/GitHubIssueCommentsClient.java`
    — `parseComments()`(`:144-169`)에 `parseReactionCount(JsonNode)` private 헬퍼 추가,
    `GitHubIssueSearchClient.searchActiveIssues` 파싱(`:153-154`, `reactions.total_count`
    `canConvertToInt`+`>=0` 검증)과 동일한 패턴 재사용. `CollectedComment` 생성자의
    **마지막 인자**로 호출해, 기존 `parseCommentId(node)`(1번째 인자)가 먼저 평가되는
    순서를 유지한다 — `id가_없으면_UpstreamFetchException이다` 기존 테스트가 여전히
    "id 문제"로 실패하게 하려는 의도(§6에서 실제 평가 순서 재확인).
  - `backend/src/main/java/com/ssafy/pickage/domain/community/CommunitySummarySourceBundle.java`
    — `from()`(`:10-59`)의 댓글 선택 루프를 교체. 상세 알고리즘은 §3.
  - `backend/src/test/java/com/ssafy/pickage/domain/community/collection/GitHubIssueCommentsClientTest.java`
    — `commentsJson(...)` 헬�`퍼(`:41-51`)에 `"reactions": {"total_count": 0}` 추가,
    `id를_십진_문자열로_보존한다`(`:73-81`) 원문 JSON에도 동일 필드 추가(안 하면 새
    검증에 걸려 실패). 신규 테스트 2개: reactions 필드 자체가 없으면
    `UpstreamFetchException`, `reactions.total_count`를 실제로 읽어
    `CollectedComment.reactionCount()`에 반영하는지.
  - `backend/src/test/java/com/ssafy/pickage/domain/community/collection/CollectionContractReviewTest.java`,
    `backend/src/test/java/com/ssafy/pickage/domain/community/collection/CommentWindowResolverTest.java`,
    `backend/src/test/java/com/ssafy/pickage/domain/community/CommunityContractReviewTest.java`,
    `backend/src/test/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerTest.java`,
    `backend/src/integrationTest/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerRealNetworkTest.java`
    — 전부 `new CollectedComment(...)` 호출부가 있어 새 필드를 인자로 추가해야 컴파일된다
    (`reactionCount=0` 고정값으로 채움 — 이 파일들의 테스트 목적 자체가 반응 수 로직과
    무관하므로 값 자체는 의미 없음). `CommunityContractReviewTest`의
    `R05_sourceBudgetCountsUnicodeCharactersAndExcludesDroppedSources`(`:116-156`)는
    20개 댓글 전부 `reactionCount=0`(동률)로 채우면 동률 tie-break(최신 우선)가 기존
    "최신순" 동작과 동일해져 **기존 assertion을 그대로 통과한다**(§6에서 근거 확인).
  - 신규 파일:
    `backend/src/test/java/com/ssafy/pickage/domain/community/CommunitySummarySourceBundleTest.java`
    — 지금까지 이 클래스 전용 테스트가 없었다(계획 문서 §6 "현재 이런 테스트 없음").
    §5에 케이스 목록.
- **범위 밖 — 이 Phase에서 하지 않을 일**
  - `CommentWindowResolver`/`IssueCollectionService`(1차 절단, 최대 100개 수집) — Jira
    2단계 항목이 명시한 변경 지점은 `CommunitySummarySourceBundle.from`뿐이다.
  - `CommunitySummaryValidator`/`TopicSummary` — `reactionCount`는 GMS에 보내는 입력
    선택에만 쓰이고 GMS 응답·검증 계약에는 등장하지 않는다.
  - PRD §4.1 문구 자체 — 이미 2026-09-16에 갱신·승인됨(Jira 세부 항목에도 "완료"로
    표시).

## 3. 아키텍처 / 데이터 흐름 — 선택 알고리즘

기존 `from()`은 `input.size()-1`부터 역순으로(최신→과거) 순회하며 예산을 채우고, 마지막에
`Collections.reverse`로 시각순 복원했다. 새 알고리즘:

1. **우선순위 정렬**: `input`(수집된 댓글, 시각순)을 아래 기준으로 정렬한 `priorityOrder`를
   만든다(원본 `input`은 그대로 둔다).
   1. **이슈 작성자의 최초 댓글**(있다면) — 항상 최우선(0순위). 판정:
      `comment.authorId() != null && comment.authorId().equals(source.authorId())`인
      댓글 중 `createdAt`이 가장 이른 것 하나. PRD §4.1 문구의 "질문·문제 제기 댓글처럼
      반응은 적어도 맥락상 필수인 댓글" 완화 규칙을 이 구조적 대리 지표(이슈 작성자의
      첫 후속 댓글 — 보통 재현 정보 보강·질문에 대한 답)로 구현한다. **작성자의
      나머지 댓글은 이 특례를 받지 않는다** — 전부 우선 포함시키면(작성자가 댓글을
      많이 단 경우) 정작 반응 수 높은 다른 사용자 댓글을 밀어낼 수 있어, 계획 문서가
      예로 든 "최초 댓글"만 좁게 구현한다.
   2. 나머지 댓글: `reactionCount` 내림차순, 동률은 `createdAt` 내림차순(최신 우선 —
      PRD §4.1 "동률은 최신 우선"과 정확히 일치).
2. **예산 채우기**: `priorityOrder`를 앞에서부터 순회하며 기존과 동일한 clip/누적 로직
   (`Math.min(4000, remaining)`, `limited` 판정, `refs`에 등록)을 그대로 적용한다 —
   **알고리즘의 이 부분(자르기·budget 차감·limited 판정)은 바꾸지 않는다**, 순회 순서만
   바뀐다.
3. **최종 정렬**: 선택된 댓글(`selected`)을 `createdAt` 오름차순으로 정렬해 모델에
   시각순으로 전달한다는 계약을 지킨다(기존엔 `Collections.reverse`로 이 효과를
   냈는데, 이제 선택 순서 자체가 시각순이 아니므로 명시적 `sort`로 바꾼다).

의사코드:

```java
String firstAuthorCommentId = input.stream()
        .filter(c -> c.authorId() != null && c.authorId().equals(source.authorId()))
        .min(Comparator.comparing(CollectedComment::createdAt))
        .map(CollectedComment::sourceCommentId)
        .orElse(null);

var priorityOrder = new ArrayList<>(input);
priorityOrder.sort(
        Comparator.comparingInt((CollectedComment c) ->
                        c.sourceCommentId().equals(firstAuthorCommentId) ? 0 : 1)
                .thenComparing(Comparator.comparingInt(CollectedComment::reactionCount).reversed())
                .thenComparing(Comparator.comparing(CollectedComment::createdAt).reversed()));

// (기존과 동일한 clip/remaining/limited/refs 루프, 순회 대상만 priorityOrder로 교체)

selected.sort(Comparator.comparing(CollectedComment::createdAt));
```

## 4. 예외 및 엣지 케이스

- 이슈 작성자가 댓글을 하나도 안 달았으면(`firstAuthorCommentId == null`) 특례 없이
  순수 반응 수 정렬만 적용 — `sourceCommentId().equals(null)`은 항상 `false`라
  자연히 처리된다(별도 분기 불필요).
- `authorId`가 `null`인 댓글(작성자 계정 삭제 등 기존에도 있던 케이스)은 애초
  `filter`에서 걸러지므로 특례 후보가 되지 않는다 — 기존 null 허용 동작과 충돌 없음.
- 반응 수가 전부 0으로 동률이면 tie-break(최신 우선)만 적용돼 **기존 "최신순" 동작과
  결과가 동일**하다 — 이 성질을 §6·§5에서 회귀 테스트 근거로 쓴다.
- Jira 세부 항목 대조: "`CollectedComment.reactionCount` 추가, `GitHubIssueCommentsClient`
  파싱 확장, 선택 로직 교체 및 fixture 테스트" → §2·§3·§5로 전부 충족.

## 5. 검증 계획

- [ ] `cd backend && ./gradlew test --tests "*.GitHubIssueCommentsClientTest"` — 기존
      전체 + 신규 2개(reactions 누락 실패, reactionCount 파싱 확인) 통과.
- [ ] `cd backend && ./gradlew test --tests "*.CommunitySummarySourceBundleTest"`(신규
      파일) — 최소 4개 케이스:
      1. 반응 수 높은 과거 댓글이 반응 수 낮은 최신 댓글보다 우선 선택된다(budget 강제
         eviction 시나리오 — 댓글 본문을 크게 만들어 3개 중 2개만 들어가게 구성).
      2. 반응 수가 동률이면 최신 댓글이 우선된다.
      3. 이슈 작성자의 최초 댓글은 반응 수가 0이고 오래됐어도 다른 고반응 댓글들 때문에
         예산이 부족해도 포함된다(작성자의 **나머지** 댓글은 이 특례가 없음을 함께 확인).
      4. 선택된 댓글의 최종 순서는 항상 시각순 오름차순이다(선택 우선순위와 무관하게).
- [ ] `cd backend && ./gradlew test --tests "*.CommunityContractReviewTest"` — 특히
      `R05_sourceBudgetCountsUnicodeCharactersAndExcludesDroppedSources`가 20개 댓글
      전부 `reactionCount=0`(동률)으로 갱신해도 기존 assertion 그대로 통과하는지
      (동률 tie-break=기존 최신순과 동치이므로 통과해야 정상).
- [ ] `cd backend && ./gradlew test --tests "*.GmsCommunitySummarizerTest" --tests "*.CommentWindowResolverTest" --tests "*.CollectionContractReviewTest"` —
      순수 컴파일 통과(새 필드 추가로 인한 생성자 인자) 확인용 회귀.
- [ ] `cd backend && ./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"`
      (로컬 postgres 필요) — R11/R12 계열 통과. 이 2단계는 `CommunitySummarySourceBundle`
      만 건드리므로 이 테스트들과 직접 겹치지 않지만, 회귀 확인 원칙(각 단계마다 확인)
      그대로 유지.
- [ ] 격리 테스트 DB: `CommunityAcceptanceIntegrationTest`만 필요, 기존 패턴 그대로.
- [ ] 시크릿 노출 여부: 해당 없음.

## 6. 자체 검증 (승인 요청 전 필수)

- 확인한 실제 파일/패턴:
  - `CollectedComment.java`(`:10-17`)·`CollectedIssue.java`(`:10-24`) 전문을 다시 읽어
    필드 순서·`authorId` 존재를 확인.
  - `GitHubIssueSearchClient.java:130-177`을 다시 읽어 `reactions.total_count` 파싱·
    검증 패턴(canConvertToInt + `>=0`)을 정확히 확인, 그대로 재사용하기로 함.
  - `GitHubIssueCommentsClient.java` 전문을 읽고 `parseComments()`(`:144-169`)의 현재
    생성자 인자 순서(`parseCommentId`가 1번째)를 확인 — 새 `parseReactionCount`를
    **마지막** 인자로 넣어야 `id가_없으면_UpstreamFetchException이다` 테스트가 여전히
    "id 문제"로 실패함을 코드 레벨에서 확인함(Java는 인자를 좌→우 순서로 평가).
  - `GitHubIssueCommentsClientTest.java` 전문을 읽고 `commentsJson` 헬퍼·원문 JSON
    테스트 2개(`id를_십진_문자열로_보존한다`, `id가_없으면_UpstreamFetchException이다`)를
    확인 — 전자만 `reactions` 필드 추가가 필요하고 후자는 필요 없음(§4에서 이미 설명한
    이유)을 재확인.
  - `CommunityContractReviewTest.java:116-156`(`R05_sourceBudgetCountsUnicodeCharactersAndExcludesDroppedSources`)
    을 다시 읽고, 20개 댓글이 전부 `authorId="456"`(이슈 `authorId="123"`과 다름 —
    `CommunityContractReviewTest.issue()`의 `authorId` 확인)이라 이슈 작성자 특례가
    적용되지 않음을 확인 — 순수 동률(reactionCount=0) tie-break만 적용되므로 기존
    "가장 오래된 2000이 빠지고 2019가 남는다" assertion과 새 알고리즘이 동일한 결과를
    낸다는 근거를 직접 확인함.
  - `CommunitySummarySourceBundle.java` 전문을 다시 읽어 `clip`/`limited`/`refs` 로직이
    선택 순서와 독립적임을 확인 — §3의 "이 부분은 바꾸지 않는다" 판단의 근거.
- 발견해 Spec에 반영한 차이: 계획 문서 §3②가 "이슈 작성자 최초 댓글" 예시를 던지기만
  하고 구체적 규칙을 정하지 않았음(그 자체가 "Spec 단계에서 fixture로 검증 필요"라고
  명시) — 이 Spec의 §3에서 "최초 댓글 1개만 특례, 나머지는 특례 없음"으로 구체화했다.
  이건 Jira/PRD가 위임한 설계 결정이라 별도 재승인 없이 이 Spec에서 확정한다.
- 이 Spec에서 아직 못 정한 것: 없음.

---
**승인**: 2026-09-16, 오세진 님 — "이어서 진행해줘, 또 커밋까지만 해" 지시로 착수.
선택 정책 세부 규칙(§3)은 PRD가 Spec 단계 설계로 위임한 부분이라 별도 승인 절차 없이
이 Spec에서 확정하고 구현한다. push·MR은 여전히 보류(로컬 커밋까지만).
