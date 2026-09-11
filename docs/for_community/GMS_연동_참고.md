# GMS(LLM) 연동 참고 — Phase 4(S15P21A506-317)용

> 2026-09-11, 오세진 님이 실제 GMS 키를 발급받은 뒤 확인한 호출 방식을 기록한다. 아직
> 어떤 Phase도 이 정보로 코드를 만들지 않았다 — Phase 4(317)가 GMS 요약 연동을 실제
> 구현할 때 이 문서를 시작점으로 쓴다.

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
