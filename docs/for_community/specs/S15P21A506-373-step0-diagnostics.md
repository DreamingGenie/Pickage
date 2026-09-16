# Spec — S15P21A506-373 0단계 (진단 로그 + 실네트워크 대형 fixture)

> 이 Spec은 S15P21A506-373(0~4단계) 전체가 아니라 **0단계만** 다룬다. 1~4단계는 0단계
> 결과(§7 미확인 항목 확인)를 본 뒤 각 단계 착수 전 이 파일에 절을 추가하거나 별도
> Spec으로 분리한다(3·4단계는 계획 문서·Jira 본문이 이미 별도 Spec을 명시).

## 0. 대상 Phase

- Jira: [S15P21A506-373](https://ssafy.atlassian.net/browse/S15P21A506-373) `[BE] [구현] GMS 대용량 이슈 요약 실패 개선(0~4단계)` — 이 Spec은 그중 0단계만
- 브랜치: `api/feat/S15P21A506-373-large-issue-summary-diagnostics`
  (`sh scripts/new-branch.sh api feat 373 large-issue-summary-diagnostics`)
- 구현계획 문서 참고 절: [`../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md`](../Pickage_GitHub커뮤니티_대용량요약_개선계획_260916.md)
  §3 "0단계", §5, §6(0행), §7 1번째 항목
- 선행 Phase: 없음 (Phase 5=S15P21A506-315는 2026-09-16 기준 Jira 상태 `완료` —
  `phases/README.md`의 "진행 중" 표기는 병합 전 스냅샷이라 stale. WIP=1 기준으로 이
  Phase 착수에 걸림돌 없음 — Documenter 단계에서 표를 갱신한다)

## 1. 작업 개요

- 작업명 / 목표: `GmsCommunitySummarizer.parseResponse`의 두 실패 분기(상태 비정상,
  페이로드 파싱 실패)에 진단 로그를 남기고, `GmsCommunitySummarizerRealNetworkTest`에
  댓글 80~90개 안팎의 합성(fabricated) 이슈로 실제 GMS를 호출하는 테스트를 추가해
  §7의 "max_output_tokens(2048) 초과 시 실제 status/output 형태" 미확인 항목을 좁힌다.
  코드 동작(성공/실패 판정)은 바꾸지 않는다 — 순수 관측성 추가.
- Jira 이슈 "필요한 이유"·"영향 범위" 요약 (재인용): 댓글이 많은(80개 이상) 인기
  저장소일수록 GMS 요약이 `SUMMARY_INPUT_LIMITED`/`SUMMARY_UNAVAILABLE`로 실패한다.
  368·370은 "이슈 2개 순차 호출" 문제를 고쳤을 뿐 "이슈 1개 안의 대용량 입력/출력"
  문제는 남아 있다. 영향 범위: 백엔드 API, 문서(체크 표시됨) — 데이터 저장소·분석·
  프론트엔드·인프라는 이 Jira 전체 기준 미해당(0단계는 그중에서도 백엔드 코드 2개
  파일만 건드린다).

## 2. 변경 대상 (Scope)

- **수정될 파일**
  - `backend/src/main/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizer.java`
    - `parseResponse(CollectedIssue, String)` (현재 `:241-258`)의 두 지점에
      `log.warn` 추가:
      1. `:248` `if (!"completed".equals(root.path("status").asText()))` 분기 —
         실제 `status` 값과, 있으면 `incomplete_details.reason`을 로그로 남긴다.
         원문 텍스트(댓글 내용)는 남기지 않는다.
      2. `:254-256` `JSON.readTree(text)`의 `catch (IOException e)` 분기 —
         추출된 `text`의 길이와 앞부분 일부(최대 200자, 잘렸으면 표시)만 로그로
         남긴다(원문 그대로 전부 로그에 남기지 않는다 — 운영 로그에 GitHub
         댓글 원문이 과도하게 쌓이는 것을 피한다).
    - 기존 로직(성공/실패 판정, 반환값)은 바꾸지 않는다 — `log.warn` 호출만 추가.
  - `backend/src/integrationTest/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerRealNetworkTest.java`
    - 기존 단일 댓글 테스트(`실제_GMS_호출로_구조화_요약을_받는다`)는 그대로 두고,
      새 `@Test` 메서드를 추가한다(가칭 `실제_GMS_호출로_대용량_댓글_이슈를_요약한다`).
    - 댓글 85개 안팎(80~90 범위, 정확히 88/81을 흉내 내지 않고 근사치)의 **합성**
      `CollectedComment` 목록을 코드로 생성(반복문 + 몇 가지 템플릿 문장 조합)해
      `CollectedIssue`를 구성한다. 실제 zod 이슈 원문은 쓰지 않는다(합성 데이터
      원칙 — 계획 문서 §3 0단계 2번 항목).
    - `client().summarize(issue, Duration.ofSeconds(15))` 호출 결과를
      `System.out.println`으로 상태·필드 개수를 출력한다.
    - **assert는 `summary`가 null이 아니라는 것만 한다 — `SummaryStatus.READY`를
      단정하지 않는다.** 이유: 이 테스트의 목적 자체가 "READY로 끝나는지 아니면
      `incomplete`/파싱 실패로 끝나는지 관측"이므로, READY를 미리 단정하면 실패
      시 "버그"처럼 보고돼 진단 목적과 어긋난다. 관측 결과(로그의 status/output,
      필요하면 실패 여부)는 사람이 §7 판단에 직접 쓴다.
- **범위 밖 — 이 Phase에서 하지 않을 일**
  - `MAX_OUTPUT_TOKENS` 값 변경(1단계), 스키마 평탄화(1단계), 반응 수 기반 선택
    (2단계), background 폴링(3단계), Map-Reduce(4단계) — 전부 이후 단계.
  - `CollectedComment`에 `reactionCount` 필드 추가(2단계 항목) — 0단계 fixture는
    현재 레코드 필드 그대로(`reactionCount` 없이) 구성한다.
  - `text==null`(즉 `extractOutputText`가 `output` 배열에서 `output_text`를 못 찾는
    경로, `:249-250`)에는 로그를 추가하지 않는다 — 계획 문서·Jira 세부 항목이
    명시한 두 분기(상태 비정상, JSON 파싱 실패)에만 정확히 범위를 맞춘다. 실행해
    보고 이 경로가 실제로 밟히는 것이 확인되면 별도로 제안한다.
  - `GmsCommunitySummarizerTest`(mock 서버 단위테스트)는 수정하지 않는다 — 기존
    `status가_completed가_아니면_실패로_처리한다`(`:149-159`, `status=incomplete,
    output=[]` 고정)와 `output_text가_유효한_JSON이_아니면_실패로_처리한다`
    (`:161-168`)가 이미 두 분기를 각각 정확히 덮고 있어, 로그 추가만으로는 이
    테스트들의 assertion(둘 다 `SummaryStatus.FAILED`)이 바뀌지 않는다 — 회귀
    확인용으로 그대로 재사용한다.

## 3. 아키텍처 / 데이터 흐름

- 관련 기존 코드 패턴: 같은 클래스 안의 `:104-106`
  (`if (response.statusCode() != 200) { log.warn(...); return TopicSummary.failed(); }`)이
  이미 같은 클래스에서 쓰는 로그 스타일 — 새 로그 두 줄도 이 스타일(`log.warn("...: {}",
  값)`)을 그대로 따른다.
- 데이터 흐름 변화 없음(관측성만 추가). 흐름 자체는 계획 문서 §1.1 그대로:
  `GmsCommunitySummarizer.summarize → parseResponse → (신규 log.warn 두 지점) →
  TopicSummary.failed()`.

## 4. 예외 및 엣지 케이스

- Jira 세부 항목 대조:
  - "0단계: `GmsCommunitySummarizer`에 진단 로그 추가" → §2의 파일 1번 항목으로 구현.
  - "0단계: `GmsCommunitySummarizerRealNetworkTest`에 대형 합성 fixture 추가,
    실제 GMS 호출로 §7 미확인 사항 확인" → §2의 파일 2번 항목으로 구현. **다만
    이 세션에 `GMS_API_KEY` 환경변수가 없으면 실제 호출·§7 확인 자체는 이 세션에서
    완료할 수 없다 — 테스트는 작성·컴파일까지 하고, `@EnabledIfEnvironmentVariable`
    조건으로 키 없는 환경에서는 자동 skip되는 기존 패턴을 그대로 따른다.** 키가
    없으면 §7 확인은 사람이 키를 가진 환경에서 별도로 실행해야 완료된다 — 이 사실을
    Verify 단계에서 명시적으로 보고한다(미확인을 확인된 것처럼 보고하지 않는다).
- 외부 의존성으로 남겨둘 것: GMS 실호출 자체(`gms.ssafy.io`) — 이미 fake/stub 없이
  실제 호출하는 것이 이 테스트의 목적이므로 우회하지 않는다. 다만 이 테스트는
  `integrationTest` 소스셋 + 환경변수 게이팅으로 기본 빌드·CI에 영향을 주지 않는
  기존 경계를 그대로 유지한다.

## 5. 검증 계획

- [ ] `cd backend && ./gradlew test --tests "*.GmsCommunitySummarizerTest"` — 기존
      두 분기 테스트(`status가_completed가_아니면_실패로_처리한다`,
      `output_text가_유효한_JSON이_아니면_실패로_처리한다`) 포함 전체가 여전히
      `SummaryStatus.FAILED`로 통과하는지 확인(로그 추가가 판정 로직에 영향 없음을
      회귀로 확인).
- [ ] `cd backend && ./gradlew compileIntegrationTestJava` (또는 동등 명령)로 새
      `GmsCommunitySummarizerRealNetworkTest` 메서드가 컴파일되는지 확인.
- [ ] `GMS_API_KEY` 보유 시(이 세션에 없으면 스킵하고 그 사실을 명시):
      `GMS_API_KEY=<키> ./gradlew integrationTest --tests
      "*.GmsCommunitySummarizerRealNetworkTest"`로 새 대형 fixture 테스트를 실행,
      콘솔에 찍힌 `log.warn` 출력과 `System.out` 출력을 §7 판단 근거로 기록.
- [ ] `cd backend && ./gradlew test --tests "*CommunityAcceptanceIntegrationTest"`
      (R11/R12 계열 포함) — 0단계는 이 클래스들이 다루는 소유권·재시작·게시 경로를
      건드리지 않으므로 그대로 통과해야 한다. 실패하면 변경을 되돌린다(Jira "완료
      판단 기준" 2번째 항목).
- [ ] 격리 테스트 DB 불필요(이 Phase는 DB·마이그레이션을 건드리지 않음).
- [ ] 시크릿 노출 여부: `GMS_API_KEY`는 로그·커밋·테스트 코드 어디에도 하드코딩하지
      않는다(환경변수로만 주입, 기존 테스트와 동일 패턴). 로그에 GitHub 댓글 원문을
      과도하게 남기지 않는다(§2에서 200자 제한 명시).
- [ ] Jira "완료 판단 기준" 매핑:
      - "계획 문서 §5의 0~4단계가 각각 구현·테스트·리뷰를 거쳐 병합" → 이 Spec은
        0단계분만 충족을 목표로 한다(1~4단계는 별도 Spec/커밋).
      - "각 단계에서 `CommunityAcceptanceIntegrationTest`의 R11/R12 계열이 통과" →
        위 4번째 체크박스로 충족.
      - "zod #479/#372 실측 개선 확인" → 0단계는 진단 전용이라 아직 개선 자체를
        만들지 않는다 — 이 항목은 1단계 이후에나 해당.

## 6. 자체 검증 (승인 요청 전 필수)

- 확인한 실제 파일/패턴:
  - `GmsCommunitySummarizer.java` 전문을 읽고 `:104-106`(기존 로그 스타일),
    `:241-258`(`parseResponse`), `:248`·`:254-256`(변경 지점) 줄 번호를 이 Spec
    작성 시점의 실제 파일과 대조해 확인함.
  - `GmsCommunitySummarizerRealNetworkTest.java` 전문을 읽고 기존 단일 테스트
    구조(`client()` 헬퍼, `@EnabledIfEnvironmentVariable` 게이팅)를 확인함 — 새
    테스트는 같은 `client()` 헬퍼를 재사용한다.
  - `CollectedComment`(`collection/CollectedComment.java:10-17`)·`CollectedIssue`
    (`collection/CollectedIssue.java:10-24`) 레코드 필드를 직접 읽어 합성 fixture
    생성자 인자 순서를 확인함(`reactionCount` 등 이슈 레벨 필드는 있지만 댓글
    레벨에는 없음 — 계획 문서 §3②의 서술과 일치).
  - `GmsCommunitySummarizerTest.java:149-168`에서 두 분기를 이미 덮는 기존 mock
    테스트 2개를 확인해, 새 로그가 이 테스트들의 assertion과 충돌하지 않음(반환값
    불변)을 코드 레벨에서 확인함.
  - Jira S15P21A506-315 상태를 직접 조회해 `완료`임을 확인함(phases/README.md의
    "진행 중" 표기가 stale임을 근거와 함께 확인 — WIP=1 위반 아님).
- 발견해 Spec에 반영한 차이: 없음 — 계획 문서·Jira 본문이 지목한 두 분기·파일
  경로가 실제 코드와 정확히 일치했다.
- 이 Spec에서 아직 못 정한 것 (사용자 확인 필요 항목):
  1. 이 세션에 `GMS_API_KEY`가 있는지 아직 확인하지 않았다 — 없으면 §7의 실제
     "닫기"는 이번 세션에서 못 하고, 테스트 작성·컴파일·기존 회귀까지만 이번
     Phase로 완료 처리하려 한다. 이견 있으면 알려달라.
  2. 합성 댓글 본문의 구체적 문구(템플릿 문장)는 Coder 단계에서 정하려 한다 —
     실제 GitHub 텍스트를 흉내 내되 식별 가능한 실제 사용자/저장소명은 쓰지 않는
     선에서 자유도를 남겨 뒀다.

---
승인 후 이 줄 아래에 승인 일시와 승인자를 기록한다.

**승인**: 2026-09-16, 오세진 님. 조건부 반영 — "GMS_API_KEY는 다른 터미널에서 나중에
입력할 테니, §7 확인까지 실제로 제대로 하자"는 지시에 따라 §7(대형 합성 fixture 실호출
확인)을 "스킵하고 완료 처리"가 아니라 **키가 준비되는 대로 이 세션에서 실제 실행까지
마치는 것**으로 진행한다. 구현·기존 회귀 테스트는 지금 바로 진행한다.
