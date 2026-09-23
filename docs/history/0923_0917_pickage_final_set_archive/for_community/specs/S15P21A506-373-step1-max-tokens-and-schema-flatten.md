# Spec — S15P21A506-373 1단계 (max_output_tokens 상향 + GMS 스키마 평탄화)

> 이 Spec은 S15P21A506-373의 **1단계만** 다룬다(계획 문서 §3 ①+③). 0단계 기록은
> [`S15P21A506-373-step0-diagnostics.md`](S15P21A506-373-step0-diagnostics.md) 참고 —
> 0단계 실측(경량·중량 합성 fixture 둘 다 `status=READY`)으로 "경로 B"(`incomplete`)
> 가설이 약화됐지만, 오세진 님이 "원래 계획대로 진행" 지시(2026-09-16)를 명시적으로
> 줘서 ①③을 그대로 진행한다 — ①은 여전히 낮은 위험의 보험성 변경이고, ③은 애초부터
> 경로 B와 무관하게 독립적으로 유효한 예방적 조치였다(계획 문서 §3③).

## 0. 대상 Phase

- Jira: [S15P21A506-373](https://ssafy.atlassian.net/browse/S15P21A506-373) — 1단계만
- 브랜치: `api/feat/S15P21A506-373-max-output-tokens-and-schema-flatten`
  (`sh scripts/new-branch.sh api feat 373 max-output-tokens-and-schema-flatten`)
- 구현계획 문서 참고 절: [`../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md`](../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md)
  §1.2, §3 "① max_output_tokens 상향", §3 "③ 스키마 평탄화", §5 1단계
- 선행 Phase: Phase 6/0단계(S15P21A506-373, 병합 완료 — MR !162)

## 1. 작업 개요

- 작업명 / 목표: ① `MAX_OUTPUT_TOKENS` 2048→4096으로 상향. ③ GMS 요청 JSON 스키마의
  `flow[].support` 중첩(depth 4)을 없애고, 최상위 `flow_support` 평면 배열
  (`{flow_index, type, id}`)로 옮긴다. `TopicSummary`/`CommunitySummaryValidator`의
  Java 쪽 인터페이스(`flowSupport: List<List<SourceRef>>`)는 그대로 유지 —
  `GmsCommunitySummarizer.toTopicSummary`에서 평면 배열을 flow_index로 재조립해
  기존 모양으로 되돌린다(계획 문서 §3③이 이미 이 선택지를 명시).
- Jira 이슈 "필요한 이유"·"영향 범위" 요약 (재인용): 댓글이 많은(80개 이상) 이슈에서
  GMS 요약이 계속 실패하는 구조적 문제. 영향 범위: 백엔드 API, 문서(0단계와 동일).

## 2. 변경 대상 (Scope)

- **수정될 파일**
  - `backend/src/main/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizer.java`
    - `MAX_OUTPUT_TOKENS`(`:48`) `2048` → `4096`.
    - `schema()`(`:183-232`): `flowItem`에서 `support` 필드·required 제거. 새
      `flowSupportRef` 객체(`flow_index: integer`, `type: enum[ISSUE_BODY,COMMENT]`,
      `id: string`, 전부 required, `additionalProperties: false`)를 만들고, 루트
      `properties`에 `flow_support: array<flowSupportRef>` 추가, 루트 `required`에도
      `flow_support` 추가.
    - `toTopicSummary()`(`:273-306`): `flow` 파싱은 `text`만 읽도록 단순화. 별도로
      `flow_support` 평면 배열을 순회하며 `flow_index`로 `List<List<SourceRef>>`를
      재조립(각 flow 항목 개수만큼 빈 리스트로 초기화 후 채움). `flow_index`가
      범위를 벗어나면 `IndexOutOfBoundsException`이 자연히 던져지고, 기존
      `catch (RuntimeException e)`(`:303-305`)가 그대로 `TopicSummary.failed()`로
      수렴한다 — 별도 방어 코드를 추가하지 않는다(기존 "모델 주장을 그대로 믿지
      않는다" 원칙과 일관).
    - `TopicSummary`/`CommunitySummaryValidator`/`CommunityContractReviewTest`는
      **수정하지 않는다** — `flowSupport`의 Java 쪽 모양(`List<List<SourceRef>>`)이
      안 바뀌므로 다운스트림 영향 없음(§6 자체 검증에서 직접 확인).
  - `backend/src/test/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerTest.java`
    - `VALID_PAYLOAD`(`:96-110`)의 `flow[0]`에서 `"support"` 키 제거, 최상위에
      `"flow_support": [{"flow_index": 0, "type": "ISSUE_BODY", "id": "701"}]` 추가.
    - `인증_헤더와_모델명을_정확히_보낸다`(`:171-186`) 근처에 새 테스트를 추가해,
      실제로 보내는 요청 JSON의 `text.format.schema.properties.flow.items`에
      `support` 키가 없고(`additionalProperties`도 확인), `flow_support`가
      최상위에 존재하는지 — 즉 평탄화가 실제로 적용됐는지를 계약 테스트로 고정한다.
  - `docs/for_community/GMS_연동_참고.md` — `:30-39`의 "2026-09-16 추가 확인" 문단이
    지금 `flow[].support`처럼 2단 중첩" 표현을 쓰는데 이번 변경으로 더는 사실이
    아니게 된다. `MAX_OUTPUT_TOKENS(2048)` 언급도 4096으로 바뀐다. 두 문장을 이번
    변경 사실에 맞게 갱신하고, 0단계 §7 실측(경로 B 미재현) 결과를 한 줄 추가한다.
- **범위 밖 — 이 Phase에서 하지 않을 일**
  - 반응 수 기반 댓글 선택(2단계), background 폴링(3단계), Map-Reduce(4단계).
  - `CommunitySummaryValidator`·`TopicSummary`·`CommunityContractReviewTest` 수정 —
    위에서 확인했듯 Java 쪽 인터페이스가 안 바뀌므로 손댈 이유가 없다.
  - `GmsCommunitySummarizerRealNetworkTest`의 fixture 내용 변경 — 0단계에서 이미
    만든 것을 그대로 재사용해 §7을 1단계 적용 후 다시 확인하는 용도로만 쓴다(새로
    만들지 않는다).

## 3. 아키텍처 / 데이터 흐름

- 관련 기존 코드 패턴: `schema()`의 `sourceRef`/`arrayOf(...)` 헬퍼 패턴을 그대로
  재사용해 `flowSupportRef`를 만든다 — 새 추상화를 만들지 않는다.
- 요청 스키마 깊이 변화: `topic_summary(0) → flow(1) → flowItem(2)`까지는 그대로,
  `flow[].support` 경로(구 depth 4)가 사라지고 `topic_summary(0) → flow_support(1) →
  flowSupportRef(2)`로 대체 — 계획 문서 §1.2가 지적한 4단 중첩이 실제로 없어진다.
- 파싱 흐름: `parseResponse → toTopicSummary`에서 `flow`(text만)와 `flow_support`
  (평면, flow_index 포함)를 각각 순회해 최종적으로 기존과 동일한
  `List<List<SourceRef>>` 모양으로 합친 뒤 `TopicSummary` 생성 — 이후
  `CommunitySummaryValidator.validate`부터는 완전히 기존 경로 그대로.

## 4. 예외 및 엣지 케이스

- Jira 세부 항목 대조:
  - "1단계: `MAX_OUTPUT_TOKENS` 상향 및 회귀 테스트" → §2 파일 1번 항목 + 기존
    `GmsCommunitySummarizerTest` 전체 재실행으로 충족.
  - "1단계: GMS 요청 스키마 평탄화(`flowSupport` 구조 변경) 및 파싱/검증/계약 테스트
    갱신" → §2 파일 1·2번 항목. "검증" 쪽은 `CommunitySummaryValidator`가 안 바뀌므로
    기존 `CommunityContractReviewTest`(특히 `R05_summaryCannotInventSourceOrAuthorMetadata`)
    재실행으로 "안 바뀌었다"를 회귀로 증명한다.
- flow_index 관련 엣지 케이스: 모델이 `flow_support`에 존재하지 않는 `flow_index`
  (예: `flow`가 2개인데 `flow_index: 5`)를 보내면 `List.get(5)`가
  `IndexOutOfBoundsException` → 상위 catch → `TopicSummary.failed()`. 별도 테스트로
  이 경로를 명시적으로 확인한다(§5).
- `flow_index`가 음수인 경우도 동일하게 `IndexOutOfBoundsException`로 수렴 —
  별도 케이스 분리하지 않는다(같은 예외 타입, 같은 처리).
- 외부 의존성으로 남겨둘 것: 없음 — 이번 변경은 GMS 응답 해석 로직 전체를 이 세션이
  직접 통제한다(fake 서버 기반 단위 테스트 + 실네트워크 테스트로 실제 검증까지 가능).

## 5. 검증 계획

- [ ] `cd backend && ./gradlew test --tests "*.GmsCommunitySummarizerTest"` — 기존
      5개 + 갱신된 `VALID_PAYLOAD` 기반 정상 파싱 테스트 + 신규 계약 테스트(스키마에
      `support` 없음/`flow_support` 있음) + 신규 `flow_index` 범위 밖 실패 테스트 전부
      통과.
- [ ] `cd backend && ./gradlew test --tests "*.CommunityContractReviewTest"` — 특히
      `R05_summaryCannotInventSourceOrAuthorMetadata`가 여전히 통과해
      `CommunitySummaryValidator`가 실제로 안 바뀌었음을 회귀로 확인.
- [ ] `cd backend && ./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"`
      (로컬 postgres 필요, `docker compose --profile api up -d postgres`) — R11/R12
      계열 전부 통과. 실패하면 되돌린다(Jira 완료 판단 기준 2번째 항목).
- [ ] (선택, `GMS_API_KEY` 보유 시) 0단계에서 만든
      `GmsCommunitySummarizerRealNetworkTest`의 두 테스트를 다시 실행해 새 평탄화
      스키마로도 실제 GMS가 정상 응답하는지, `MAX_OUTPUT_TOKENS=4096`으로도 문제
      없는지 재확인 — 있으면 §7 후속 기록에 남긴다, 없으면 스킵하고 그 사실을
      명시(0단계와 동일 원칙).
- [ ] 격리 테스트 DB 불필요 이유: `CommunityAcceptanceIntegrationTest`만 DB가
      필요하고, 그 테스트는 이미 기존 `DisposableTestDatabase` 패턴을 그대로 쓴다.
- [ ] 시크릿 노출 여부: 해당 없음(설정값·키 변경 없음).
- [ ] Jira "완료 판단 기준" 매핑: 위 §4에 이미 기술.

## 6. 자체 검증 (승인 요청 전 필수)

- 확인한 실제 파일/패턴:
  - `GmsCommunitySummarizer.java` 전문을 다시 읽고 `:48`(`MAX_OUTPUT_TOKENS`),
    `:183-232`(`schema()`), `:241-268`·`:273-306`(`parseResponse`/`toTopicSummary`)
    줄 번호를 이 Spec 작성 시점 실제 코드(0단계 로그 추가 반영된 현재 develop 기준)와
    대조함.
  - `TopicSummary.java`(`flowSupport: List<List<SourceRef>>`)·
    `CommunitySummaryValidator.java`(`:28-35` — `flowSupport.size() ==
    discussionFlow.size()` 요구, 인덱스별 `support(...)` 호출)를 직접 읽고, 이번
    변경이 `GmsCommunitySummarizer.toTopicSummary`에서 끝나며 그 아래로는 전파되지
    않음을 확인함.
  - `CommunityContractReviewTest.java`를 전문 읽고, GMS 와이어 스키마가 아니라
    `TopicSummary` Java 객체를 직접 구성해 쓰는 테스트들(`R05_*`)이라 이번 변경과
    무관함을 확인함 — 수정 대상에서 제외한 근거.
  - `GmsCommunitySummarizerTest.java`의 `VALID_PAYLOAD`(`:96-110`)가 실제로
    `flow[0].support`를 갖고 있음을 확인, 갱신 필요 지점으로 확정함.
  - `docs/for_community/GMS_연동_참고.md:30-39`가 실제로 `flow[].support`·`2048`을
    언급함을 확인, 갱신 대상으로 확정함.
- 발견해 Spec에 반영한 차이: 없음 — 계획 문서 §3③이 예고한 "TopicSummary 구조는
  안 바꿔도 됨" 판단이 실제 코드 대조로도 그대로 맞았다.
- 이 Spec에서 아직 못 정한 것 (사용자 확인 필요 항목): 없음 — 2026-09-16 "원래
  계획대로 하자" 지시로 ①③ 범위·우선순위는 이미 확정됨.

---
**승인**: 2026-09-16, 오세진 님 — "원래 계획대로 하자"(대화 지시)로 ①③ 진행을
승인. 이번 단계부터는 "MR을 먼저 열지 말고 커밋까지만" 지시도 함께 받음 — 이
Spec의 구현은 로컬 커밋까지만 진행하고 push/MR은 별도 지시가 있을 때 진행한다.
