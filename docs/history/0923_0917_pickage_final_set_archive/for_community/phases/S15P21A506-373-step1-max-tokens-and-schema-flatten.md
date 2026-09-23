# Phase 기록 — S15P21A506-373 1단계 (max_output_tokens 상향 + GMS 스키마 평탄화)

> 0단계 기록: [S15P21A506-373-step0-diagnostics.md](S15P21A506-373-step0-diagnostics.md).
> 1단계는 0단계의 §7 실측(경로 B 미재현)에도 불구하고 오세진 님 지시("원래 계획대로
> 하자")로 계획 문서 §3 ①+③ 그대로 진행했다.

## 무엇을 구현했는가 / 변경한 파일

- `backend/src/main/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizer.java`
  - `MAX_OUTPUT_TOKENS` 2048 → 4096.
  - `schema()`: `flow[].support` 제거, 최상위 `flow_support: array<{flow_index, type,
    id}>` 추가(nesting depth 4 → 최대 2로 축소).
  - `toTopicSummary()`: `flow_support` 평면 배열을 `flow_index`로 재조립해 기존
    `List<List<SourceRef>>` 모양으로 복원 — `TopicSummary`/`CommunitySummaryValidator`
    는 수정하지 않음.
  - 클래스 Javadoc의 스키마 관련 서술을 현재 상태(평탄화 이후)로 갱신.
- `backend/src/test/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerTest.java`
  - `VALID_PAYLOAD`를 새 평면 스키마로 갱신, `flowSupport` 재조립 결과 assertion 추가.
  - 신규 테스트 2개: `flow_index가_flow_범위를_벗어나면_실패로_처리한다`,
    `요청_스키마는_flow_support를_평면_배열로_보낸다`(와이어 스키마 계약 고정 —
    `support` 키가 flow item에 없고 `flow_support`가 최상위에 있는지, `max_output_tokens`
    가 4096인지까지 확인).
- `docs/for_community/GMS_연동_참고.md` — 0단계 실측 결과와 1단계 반영 사실을 시간순으로
  추가, `flow[].support` 언급을 과거형으로 정정.

## 실행한 테스트와 결과

- `./gradlew test --tests "*.GmsCommunitySummarizerTest"` — 8/8 통과(기존 6개 +
  신규 2개).
- `./gradlew test --tests "*.CommunityContractReviewTest"` — 통과(특히
  `R05_summaryCannotInventSourceOrAuthorMetadata` — `CommunitySummaryValidator`가
  실제로 안 바뀌었음을 회귀로 확인).
- `./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"` — 17/17
  통과(R11/R12 계열 포함), 로컬 postgres 컨테이너 사용.
- **실네트워크 재확인 완료(2026-09-16, 오세진 님 환경)**: `GmsCommunitySummarizerRealNetworkTest`
  2개 테스트를 새 평탄화 스키마(`MAX_OUTPUT_TOKENS=4096`, 최상위 `flow_support`)로
  재실행, 둘 다 `status=READY`. 단일 댓글 fixture의 `flowSupport`가
  `[[SourceRef[type=ISSUE_BODY, id=701]], [SourceRef[type=COMMENT,
  id=9007199254740993]]]`로 정확히 재조립됨을 확인 — `flow_index` 역참조 파싱이
  mock이 아니라 실제 GMS 응답에서도 정상 동작한다. 대형 fixture도 `status=READY`
  유지(flow.size=5, messages.size=5, 0단계 결과와 동일 수준).

## 리뷰 결과 (`/code-review`)

- effort medium, 포크 실행. Finding 없음(clean) — `flow_index` 범위 밖 처리가 기존
  `catch(RuntimeException)` 경로로 자연스럽게 `FAILED`로 수렴함을 리뷰어가 별도로
  재확인, `CommunitySummaryValidator`가 재조립된 shape에 대해서만 동작해 하류 영향
  없음도 확인.

## Jira "완료 판단 기준" 대조 (1단계 해당분만)

- "계획 문서 §5의 0~4단계가 각각 구현·테스트·리뷰를 거쳐 병합된다" — 1단계분 구현·
  테스트·리뷰 완료. **병합(MR)은 오세진 님 지시로 이번엔 진행하지 않음** — "MR을
  먼저 열지 말고 커밋까지만" 지시(2026-09-16)에 따라 로컬 커밋 상태로 둔다. 다음
  지시가 있을 때 push·MR 생성.
- "각 단계에서 `CommunityAcceptanceIntegrationTest`의 R11/R12 계열이 통과한다" — 충족.
- "zod #479/#372 실측 개선 확인" — 1단계는 아직 미배포라 해당 없음(배포 후 확인 필요).

## 남은 위험, 다음 단계에 넘길 것

- 이 브랜치(`api/feat/S15P21A506-373-max-output-tokens-and-schema-flatten`)는 아직
  push되지 않았다 — 로컬 커밋 2개(Spec, 구현) 상태.
- 0단계의 "경로 B 미재현" 발견은 여전히 유효하다 — 1단계가 실제 zod #479/#372를
  고치는지는 배포 후 재수집으로만 확인 가능(Jira 완료 판단 기준 3번째 항목).
- 2단계(반응 수 기반 댓글 선택) 착수 전 WIP=1 — 이 브랜치를 push·MR·머지하거나,
  최소한 사람이 이 상태를 Decide한 뒤 다음 브랜치를 따야 한다.
