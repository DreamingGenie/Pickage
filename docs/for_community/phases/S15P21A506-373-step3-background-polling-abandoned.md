# Phase 기록 — S15P21A506-373 3단계 (⑤-A: background:true + 폴링) — 폐기

> 0~2단계: [step0](S15P21A506-373-step0-diagnostics.md)·
> [step1](S15P21A506-373-step1-max-tokens-and-schema-flatten.md)·
> [step2](S15P21A506-373-step2-reaction-based-selection.md). 3단계는 구현·테스트까지
> 마쳤으나 실네트워크 확인에서 GMS 프록시가 폴링 엔드포인트를 지원하지 않음이
> 확인돼 **폐기하고 되돌렸다.** 코드는 커밋되지 않았다(작업트리만 있던 상태를
> `git restore`로 복원) — 이 파일은 "왜 시도했다가 되돌렸는지"를 남기기 위한
> 기록이다.

## 무엇을 시도했는가

Spec: [S15P21A506-373-step3-background-polling.md](../specs/S15P21A506-373-step3-background-polling.md).
`GmsCommunitySummarizer.summarize`가 `background: true`로 GMS 요청을 시작하고
`GET {endpoint}/{id}`를 예산 안에서 짧은 간격으로 폴링하도록 구현했다.

## 구현·테스트 결과 (되돌리기 전)

- 단위 테스트(mock 서버) 12/12 통과 — 정상 폴링, id 없음, 폴링 결과 실패, 예산 소진
  4가지 신규 케이스 포함.
- `CommunityAcceptanceIntegrationTest` R11/R12 17/17 통과.
- `/code-review` — finding 0건(로직 정확성 자체는 문제없음, 타임아웃/인터럽트 처리도
  기존 계약과 정확히 맞물림을 리뷰어가 확인).

## 실네트워크 확인 결과 — 폐기 사유

`GMS_API_KEY`로 `GmsCommunitySummarizerRealNetworkTest` 2개를 실행, **둘 다
`status=FAILED`.** 진단 로그(0단계에서 추가해 둔 것):

```
GMS 폴링 실패: issue=7, status=500
GMS 폴링이 예산 안에 완료되지 않음: issue=7
GMS 폴링 실패: issue=479, status=500
```

초기 POST(`background:true`)는 성공해 `queued`+`id`로 응답 — GMS가 `background:true`
파라미터는 받아준다. 하지만 `GET {endpoint}/{id}` 폴링은 매번 HTTP 500 — 이 GMS
프록시가 상태 조회 엔드포인트를 지원하지 않는 것으로 확인됐다.

**이게 단순 "효과 없음"이 아니라 폐기해야 하는 이유**: `background:true`를 켜면
초기 POST가 더는 `status=completed`로 오지 않는데(`queued` 고정) 폴링도 항상
실패하므로, 이 상태로 배포하면 **GMS 요약이 100% 실패한다** — 3단계 착수 전(동기
호출)보다 명백히 더 나쁜 결과. 코드는 안전하게 FAILED로 저하됐지만(크래시 없음),
기능 자체가 이 환경에서 성립하지 않는다.

## 되돌린 내용

- `backend/src/main/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizer.java`,
  `backend/src/test/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerTest.java`
  의 3단계 변경분을 `git restore`로 작업트리에서 제거 — 2단계 종료 시점(커밋
  `91d7f56`) 상태로 정확히 복귀.
- 이 변경은 한 번도 커밋된 적이 없어 별도 revert 커밋이 불필요했다.
- 되돌린 뒤 `./gradlew test`(전체 단위 테스트) 재실행해 2단계 상태로 정확히
  돌아왔음을 확인.

## 오세진 님 결정 (2026-09-16)

"이런 작업은 아예 하지 말자. 되돌리고 앞으로도 하지 말자." — ⑤-A는 이 GMS 프록시
환경에서 폐기. 향후 GMS 프록시가 업데이트되거나 다른 폴링 URL 형태가 확인되는 등
명시적 근거가 없는 한 재시도하지 않는다.

## 이 결정의 범위

- ⑤-A(3단계)만 폐기. 4단계(Map-Reduce)는 별개 접근이라 영향받지 않는다(계획 문서
  §4.2 — 두 접근 사이 구현 순서상 하드 의존 없음).
- ⑤-B(진짜 cross-request 비동기)는 원래도 보류 상태 — 이번 결정으로 재검토 유인이
  더 줄었으나 별도 판단 필요.
- Jira S15P21A506-373의 "완료 판단 기준"에는 "0~4단계가 각각 구현·테스트·리뷰를 거쳐
  병합된다"고 돼 있으나, 3단계는 "구현·테스트·리뷰까지 마치고 실측으로 폐기 결정"이라는
  이례적인 완료 형태다 — 병합 대상은 없지만 Verify Loop 자체(Coding→Test→Review→
  Verify→Decide)는 전부 거쳤다.
