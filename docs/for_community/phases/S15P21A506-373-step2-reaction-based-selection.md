# Phase 기록 — S15P21A506-373 2단계 (반응 수 기반 댓글 선택)

> 0단계: [S15P21A506-373-step0-diagnostics.md](S15P21A506-373-step0-diagnostics.md).
> 1단계: [S15P21A506-373-step1-max-tokens-and-schema-flatten.md](S15P21A506-373-step1-max-tokens-and-schema-flatten.md).
> 2단계는 오세진 님의 "이어서 진행해줘, 또 커밋까지만 해" 지시(2026-09-16)로 1단계와
> 같은 브랜치 위에 이어서 진행했다.

## 무엇을 구현했는가 / 변경한 파일

- `CollectedComment`에 `reactionCount` 필드 추가(레코드 끝).
- `GitHubIssueCommentsClient.parseComments`가 `reactions.total_count`를 파싱·검증
  (`GitHubIssueSearchClient`와 동일한 규칙을 신규 `GitHubReactionCounts` 공용 헬퍼로
  추출 — `/code-review` 지적 반영).
- `CommunitySummarySourceBundle.from`의 댓글 선택을 "최신순"에서 "반응 수 내림차순
  (동률은 최신 우선) + 이슈 작성자의 최초 댓글은 무조건 우선 포함"으로 교체. 최종
  전달 순서는 여전히 시각순(명시적 정렬로 전환).
- 신규 `CommunitySummarySourceBundleTest`(4개 — 반응 수 우선, 동률 tie-break, 작성자
  최초 댓글 특례+나머지 댓글은 특례 없음, 최종 시각순 정렬).
- `GitHubIssueCommentsClientTest`에 신규 2개(reactions 파싱 확인, reactions 누락 시
  실패) + 기존 fixture에 `reactions` 필드 보강.
- 기존 `CollectedComment` 생성자 호출부(6개 파일) 전부 `reactionCount` 인자 추가.
- 부수 수정: `IssueCollectionServiceTest`의 댓글 fixture에 `reactions` 필드가 없어
  새 검증에 걸려 2개 테스트가 깨졌던 것을 발견해 함께 고침(범위는 아니었지만 이번
  변경이 직접 유발한 회귀).

## 실행한 테스트와 결과

- `./gradlew test`(전체 단위 테스트) — 전부 통과(282+4개, 중간에 발견된
  `IssueCollectionServiceTest` 2건도 수정 후 통과).
- `./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"` — 17/17
  통과(R11/R12 계열 포함).
- `./gradlew integrationTest --tests "com.ssafy.pickage.domain.community.*"` — 커뮤니티
  도메인 전체 integrationTest 통과(`GmsCommunitySummarizerRealNetworkTest`는
  `GMS_API_KEY` 없어 스킵, 정상).

## 리뷰 결과 (`/code-review`)

- effort medium, 포크 실행. Finding 1건 — `reactions.total_count` 검증이
  `GitHubIssueSearchClient`와 중복. `GitHubReactionCounts` 공용 헬퍼로 추출해 즉시
  반영·재검증(전체 재실행 통과).

## Jira "완료 판단 기준" 대조 (2단계 해당분만)

- "계획 문서 §5의 0~4단계가 각각 구현·테스트·리뷰를 거쳐 병합된다" — 2단계분 구현·
  테스트·리뷰 완료. **병합(MR)은 여전히 보류** — "커밋까지만" 지시가 이번에도 그대로
  적용됨.
- "각 단계에서 `CommunityAcceptanceIntegrationTest`의 R11/R12 계열이 통과한다" — 충족.
- "zod #479/#372 실측 개선 확인" — 아직 미배포라 해당 없음.

## 남은 위험, 다음 단계에 넘길 것

- 이 브랜치(`api/feat/S15P21A506-373-max-output-tokens-and-schema-flatten`)는 여전히
  push되지 않았다 — 로컬 커밋만 누적 중(Spec/구현 총 5개: 1단계 3개 + 2단계 Spec·구현).
  push·MR은 오세진 님 지시 대기. (`origin/develop`은 이 브랜치 분기 이후 추가 커밋이
  없음을 2026-09-16 재확인 — rebase 불필요.)
- "이슈 작성자의 최초 댓글 특례" 설계는 이 Spec에서 확정한 것으로, PRD §4.1이 위임한
  세부 정책이다 — 실제 zod 재현 시 이 정책이 유효한지도 배포 후 확인 필요.
- 3단계(⑤-A, background+폴링) 착수 전 Jira 본문이 명시한 별도 Spec 작성이 필요하다.
