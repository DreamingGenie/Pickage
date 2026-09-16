# GMS(LLM) 연동 참고 — Phase 4(S15P21A506-317)용

> 2026-09-11, 오세진 님이 실제 GMS 키를 발급받은 뒤 확인한 호출 방식을 기록한다. 아직
> 어떤 Phase도 이 정보로 코드를 만들지 않았다 — Phase 4(317)가 GMS 요약 연동을 실제
> 구현할 때 이 문서를 시작점으로 쓴다.

## 2026-09-16 실측 결과 (S15P21A506-365 착수 전 검증)

아래 "아직 확인 안 된 것" 항목 중 4개를 실제 호출로 확인했다(`gpt-4.1` 기준, `S15P21A506-365`가
쓸 모델은 `gpt-5.4-mini`로 별도 결정 — 이 모델명 자체는 아직 호출 검증 안 됨, 착수 시 한 번
더 확인할 것).

- **구조화 출력(JSON Schema strict) 지원됨.** `text.format`에 `{"type":"json_schema",
  "name":..., "schema":{...}, "strict":true}`를 넘기면 GMS 프록시가 그대로 통과시키고,
  응답의 `output[0].content[0].text`에 스키마와 정확히 일치하는 JSON 문자열이 온다(그 자체가
  문자열이라 한 번 더 파싱해야 함).
- **역할 분리 입력 배열 지원됨.** `input`을 문자열 대신 `[{"role":"system","content":...},
  {"role":"user","content":...}]` 배열로 보내면 system 지시가 실제로 반영된다(한국어 한 문장
  요약 지시 → 정확히 한국어 한 문장 응답).
- **에러 응답은 OpenAI 원본이 아니라 GMS 자체 포맷.** 존재하지 않는 모델명으로 호출하면
  `HTTP 400` + `{"statusCode":400,"message":"[GMS 에러] Model X is not available in
  Model"}` — OpenAI의 `{"error": {...}}` 형태가 아니다. 파싱 코드는 `error` 필드를 찾지
  말고 `statusCode`/`message`를 봐야 한다.
- **rate limit 헤더 있음, OpenAI 표준 그대로 통과.** `X-Ratelimit-Limit-Requests: 10000`,
  `X-Ratelimit-Limit-Tokens: 30000000` 등. `Openai-Organization: ssafy-bq2l7v`로 찍히는
  것으로 보아 **SSAFY 조직 계정 하나를 팀 전체가 공유**하는 구조로 보인다 — 한도 자체는
  넉넉하지만 공유 자원이라는 점은 인지해 둘 것.

**2026-09-16 추가 확인 (S15P21A506-365 구현 후 실제 클라이언트로 재검증):**
`gpt-5.4-mini` 모델명 허용됨, 중첩 배열/객체 스키마(`summary_support`·`flow`·`messages`
전부 array-of-object, 당시엔 `flow[].support`처럼 2단 중첩까지 포함)에도 strict 모드가
그대로 동작함 — `GmsCommunitySummarizerRealNetworkTest`로 실제 GitHub 이슈 fixture
하나를 넣어 `status=READY`, 스키마와 정확히 일치하는 응답을 확인했다(대표 메시지
kind가 `USER_SOLUTION`으로 올바르게 분류됨).

**2026-09-16 S15P21A506-373 0단계 진단**: 댓글 85개 안팎 합성 fixture(경량·중량 두
버전, 중량은 코드블록·스택트레이스 포함 500~1200자)로 실제 GMS를 호출했는데 둘 다
`status=READY`로 끝났다 — `max_output_tokens`(당시 2048) 초과로 `status=incomplete`가
되는 경로가 재현되지 않았다. 요약 태스크 특성상 입력이 커져도 모델이 출력을 압축하는
경향을 보였다(중량 fixture에서 오히려 `messages` 배열이 더 작아짐). 상세는
`docs/for_community/specs/S15P21A506-373-step0-diagnostics.md`.

**2026-09-16 S15P21A506-373 1단계 반영**: 위 0단계 진단에도 불구하고 계획대로
`MAX_OUTPUT_TOKENS`를 2048→4096으로 상향하고(여전히 낮은 위험의 보험성 변경),
`flow[].support` 2단 중첩을 없애 최상위 `flow_support` 평면 배열
(`{flow_index, type, id}`)로 옮겼다 — `GmsCommunitySummarizer.schema()`/
`toTopicSummary()` 참고. `max_output_tokens` 초과 시 실제 `status`/`output` 형태
자체는 여전히 완전히는 미확인이다(0단계 두 fixture 모두 `completed`로 끝나
`incomplete` 응답 형태를 직접 관찰하지 못함) — 다만 `GmsCommunitySummarizer`는
`completed`가 아니면 무조건 실패 처리(`TopicSummary.failed()`)하므로 안전하게
저하된다.

설정 이름 6종(`GMS_API_KEY`/`GMS_BASE_URL`/`GMS_REQUEST_PATH`/`GMS_AUTH_HEADER`/
`GMS_AUTH_SCHEME`/`GMS_MODEL`)은 `S15P21A506-363`에서 운영 compose에 이미 선택값으로
배선됨 — `GMS_BASE_URL=https://gms.ssafy.io/gmsapi/api.openai.com`,
`GMS_REQUEST_PATH=/v1/responses`, `GMS_AUTH_HEADER=Authorization`,
`GMS_AUTH_SCHEME=Bearer`가 이번 실측으로 확정됐다.

## 확인된 사실 (사용자가 직접 검증)

```bash
curl "https://gms.ssafy.io/gmsapi/api.openai.com/v1/responses" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $GMS_KEY" \
    -d '{
        "model": "gpt-4.1",
        "input": "Write a one-sentence bedtime story about a unicorn."
    }'
```

- **호출 방식**: REST API. gRPC나 SDK가 아니다 — 백엔드에서 JDK `HttpClient`로 직접
  호출할 수 있다(213·212가 GitHub/npm에 쓴 것과 같은 방식 재사용 가능).
- **엔드포인트**: `https://gms.ssafy.io/gmsapi/api.openai.com/v1/responses` — SSAFY GMS가
  OpenAI API를 프록시하는 형태로 보인다(`/gmsapi/api.openai.com/` 경로가 그 흔적).
  OpenAI의 **Responses API**(`/v1/responses`) 형식을 그대로 쓴다 — Chat Completions
  (`/v1/chat/completions`)이 아니다. 두 API는 요청·응답 스키마가 달라서 클라이언트
  코드를 짤 때 반드시 Responses API 문서 기준으로 맞춰야 한다.
- **인증**: `Authorization: Bearer $GMS_KEY` — 팀이 이미 키를 보유하고 있다(발급 대기
  아님). 구현계획 문서(§설정과 보안)가 말하는 `GMS_API_KEY` 설정 프로퍼티와 이 `GMS_KEY`가
  같은 값을 가리키는 것으로 보이나, **환경변수 이름 자체가 동일한지는 아직 미확인** —
  Phase 4 착수 시 인프라 담당과 실제 이름을 맞춘다.
- **모델**: 예시는 `gpt-4.1`. 구현계획의 `GMS_MODEL` 설정값으로 대응된다.
- **요청 본문**: 최소 형태는 `{"model": ..., "input": "<프롬프트 문자열>"}` — `input`이
  배열이 아니라 문자열 하나로도 동작한다(OpenAI Responses API는 문자열·구조화 입력 배열
  둘 다 받는다).

## 아직 확인 안 된 것 (Phase 4 착수 시 직접 검증 필요)

이 curl 예시는 "호출이 된다"는 것만 보여준다. 구현계획 §설정과 보안이 요구하는 구조화
출력(§ "GMS는 이슈별로 다음 내부 형식만 반환한다" — `title_ko`/`summary_ko`/
`discussion_flow`/`selected_messages` 고정 JSON)을 어떻게 강제할지는 이 예시만으로는
모른다. 확인이 필요한 것들:

- Responses API가 **구조화 출력**(JSON Schema 강제, OpenAI의 `text.format` /
  `response_format` 류 파라미터)을 지원하는지, GMS 프록시가 그 파라미터를 그대로
  통과시키는지
- system/developer 지시와 사용자 입력(GitHub 원문)을 분리하는 파라미터 형태 —
  구현계획이 "system 지시와 원문을 분리한다"고 명시했으므로 Responses API의 `input`
  배열 형태(역할 구분 가능한 메시지 배열)를 써야 할 가능성이 높다
- 응답 스키마 — Responses API 응답 형태(`output` 배열, `output_text` 등)를 실제로
  한 번 호출해 확인해야 파싱 코드를 짤 수 있다
- 실패 응답 형태(4xx/5xx), rate limit 헤더 유무 — GMS 프록시가 OpenAI의 것을 그대로
  전달하는지, 자체 형식으로 감싸는지
- 타임아웃·재시도 정책 — 구현계획의 "이슈 최대 2건은 동시성 2로 독립 호출" 요구와
  20초 전체 예산 안에서 GMS 호출이 차지할 수 있는 몫

## 설정 이름 매핑 (구현계획 §설정과 보안 기준, 잠정)

| 구현계획 설정 프로퍼티 | 이 예시에서의 대응 | 확정 여부 |
| --- | --- | --- |
| `GMS_API_KEY` | `$GMS_KEY` | 이름 동일 여부 미확인 |
| `GMS_BASE_URL` | `https://gms.ssafy.io/gmsapi/api.openai.com` (추정 — `/v1/responses`가 경로인지 base의 일부인지도 확인 필요) | 미확인 |
| `GMS_MODEL` | `gpt-4.1` | 예시값, 실제 사용 모델은 Phase 4 착수 시 재확인 |

## 재사용 가능한 기존 코드

- HTTP 호출: 213의 `GitHubRepositoryClient`/212의 `GitHubIssueSearchClient`와 같은
  패턴(JDK `HttpClient`, `BoundedHttpReader`로 응답 크기 상한, byte 상한 초과·통신
  오류를 `UpstreamFetchException`으로 통일)을 그대로 따르면 된다 — GMS도 외부 REST
  API라 SSRF 우려는 없지만(고정된 신뢰 endpoint), 응답 크기 상한과 타임아웃 처리
  방식은 동일하게 적용할 가치가 있다.
- rate limit 판정은 213·212와 다시 다른 형태일 가능성이 높다(OpenAI/GMS 고유 헤더) —
  Phase 4 착수 시 실제 오류 응답을 보고 판단한다.
