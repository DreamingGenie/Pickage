---
doc_id: JR-DOC-031
title: Screen Specification
version: 1.1
status: REVIEW
owner: UI/UX
last_updated: 2026-08-22
depends_on:
  - JR-DOC-030
  - JR-DOC-020
  - JR-DOC-021
source_of_truth_for:
  - screen-behavior
  - ui-states
supersedes: []
---

# Screen Specification

## 공통 UI 정책

### Probability
- default display: integer %
- 내부 계산 정밀도와 display 정밀도 분리
- confidence/support를 확률 색상 하나로 암시하지 않음

### Time
- Asia/Seoul
- 사용자에게 `HH:mm`
- 상세에서 calculated_at/source update 표시

### Evidence Badge
표시 후보:
- `근거 높음`
- `근거 보통`
- `근거 낮음`
- `분석 근거 부족`

정확한 mapping은 `43_VALIDATION_PLAN.md` calibration 후 rule version으로 확정한다.

---

# SCR-01 Journey Input

## 목적
사용자의 deadline 중심 Journey Request 생성.

## Entry
- 앱 최초 진입
- 분석 실패 후 수정
- 새 Journey

## Inputs

| Field | Required | Rule |
|---|---:|---|
| Origin | Y | 서울 scope/좌표로 resolve 가능해야 함 |
| Destination | Y | Demo default: 멀티캠퍼스 역삼 가능 |
| Target arrival | Y | future datetime |
| Target reliability | N | default 90% |

## Primary CTA
`도착 가능성 계산`

## Loading
- CTA disabled
- `경로와 도착 가능성을 계산하고 있어요`
- indefinite fake progress % 사용 금지

## Errors

### INPUT_INVALID
해당 field inline.

### UNSUPPORTED_GEOGRAPHY
`현재 서울 내 지원 범위에서만 분석할 수 있어요.`

### ROUTE_NOT_FOUND
`분석할 수 있는 대중교통 경로를 찾지 못했어요.`

### PROVIDER_ERROR
`교통정보를 불러오지 못했어요. 다시 시도해주세요.`

## Mobile
- target time CTA가 keyboard에 가리지 않아야 함
- primary CTA sticky 가능

## Dependencies
- API-001 Route candidates
- API-002 Journey analyze

## Requirements
REQ-001/002/033

---

# SCR-02 Pre-trip Result

## 목적
출발 의사결정.

## Header
- destination
- target arrival
- selected route summary

## Primary Result Block

반드시:
- `정시 도착확률`
- `P50 예상 도착`
- `P90 보수적 도착`
- `이 경로 기준 90% 권장 출발` 또는 unavailable
- Evidence badge

## Recommended Departure unavailable

원인에 따라:
- `아직 권장 출발시각을 계산할 근거가 부족해요`
- future WAIT/timetable/headway source 부족 가능
- 상세 reason in Evidence Detail

임의 time 제공 금지.

## Route
selected structural route 1개 표시.

선택은 provider order + supported/mappable policy를 따르며 Reliability ranking UI가 아니다.
현재 product scope에서는 route alternatives comparison UI를 제공하지 않는다.

## Connection
환승이 있으면:
- 계획 connection success
- final on-time과 시각적으로 분리

## Primary CTA
`이 경로로 이동 시작`

## Secondary
- `계산 근거 보기`
- `공유`

## Partial Model Banner
WALK/transfer uncertainty 미모델링 등:
`일부 구간은 기준 소요시간을 사용해 계산했어요.`

## Stale
분석 이후 source가 stale이면:
- result freeze/grey
- refresh CTA
- 최신 결과처럼 애니메이션 갱신 금지

## Requirements
REQ-010~015, REQ-030~034

---

# SCR-03 Live Journey

## 목적
현재 이동상태와 남은 정시확률 확인.

## Top
- `멀티캠퍼스 역삼 09:30`
- current P(on-time)
- last calculated time

## Journey Timeline
각 leg:
- completed
- active
- future

Transfer/Wait를 분리해 표시.

예:
```text
✓ 01A 탑승
✓ 안국 하차
● 버스→지하철 환승
○ 3호선 대기
○ 안국→교대
...
```

## Active Actions

상태에 따라 노출.

### BUS_WAIT
- `탑승했어요`
- `이번 버스는 보낼게요`

### SUBWAY_WAIT
- `탑승했어요`
- missed action은 요구사항이 준비된 경우만

## Freshness
- `방금 업데이트`
- exact threshold 전에는 semantic state를 backend에서 받음

## Provider Error
Live source 실패:
- 마지막 성공시각
- stale banner
- retry
- 이전 결과를 “현재 확률”처럼 무표식 유지하지 않음

## Requirements
REQ-020~025/032/050

---

# SCR-04 Reforecast Result

## 형태
SCR-03 내 transition panel 또는 bottom sheet.

## Before/After

```text
정시 도착확률  old → new
P50             old → new
P90             old → new
```

실제 값만 사용.

## Reason

우선 deterministic reason code:

- `BUS_SKIPPED_NEXT_SERVICE`
- `TRANSFER_MISSED`
- `SOURCE_STATE_UPDATED`
- `USER_BOARD_CONFIRMED`

AI 문장은 optional.

## Rule
완료 history가 바뀌었다는 표현 금지.

## CTA
`계속 이동하기`

## Requirements
REQ-022~025

---

# SCR-05 Evidence Detail

## 목적
확률 숫자의 근거/한계를 이해.

## User-facing Summary
- 근거 수준
- 실측 구간/기준 구간
- fallback 존재
- data freshness
- 미모델링 uncertainty

## Detail
개발모드/발표에서만 선택적으로:
- sample_count
- observation window
- fallback level
- rule version
- distribution version
- simulation run id
- validation scope (`COMPONENT_ONLY / CORRIDOR_REPLAY / END_TO_END`)
- coordinate/source role debug metadata(개발/발표 모드)

Raw API payload 자체는 일반 사용자 화면에 노출하지 않는다.

## Examples of honest wording

`버스 구간은 최근 실측 자료를 사용했어요.`

`일부 도보 구간의 시간 변동성은 아직 모델링하지 않았어요.`

`지하철 구간의 실측 표본이 적어 더 넓은 조건의 데이터를 함께 사용했어요.`

`현재 확률은 개별 교통구간 검증을 기반으로 하며 전체 여정의 실사용 calibration은 아직 진행 중이에요.` — 실제 validation_scope가 COMPONENT_ONLY일 때만 표시.

실제 metadata와 맞을 때만 표시.

---

# SCR-06 Share Snapshot

## 목적
약속 상대에게 현재 도착 가능성 전달.

## 포함
- destination
- target time
- current expected arrival summary
- on-time probability
- calculated_at

## 제외
- exact origin
- precise route coordinates
- API IDs
- support debug internals

## Expired
`공유 링크가 만료되었어요.`

TTL은 Security Gate 전까지 TBD.

---

# Global UI State Matrix

| State | Result number | CTA | Required label |
|---|---|---|---|
| FRESH | show | normal | updated time optional |
| AGING | show | normal | last update |
| STALE | show with caution or block action by backend policy | refresh | stale |
| PARTIAL_MODEL | show | normal | partial/fallback |
| LOW_SUPPORT | show if policy allows | normal | low support |
| INSUFFICIENT | do not fabricate | retry/back | insufficient |
| PROVIDER_ERROR | last result only if clearly stale | retry | provider error |
| UNSUPPORTED | no probability | change input | unsupported |
