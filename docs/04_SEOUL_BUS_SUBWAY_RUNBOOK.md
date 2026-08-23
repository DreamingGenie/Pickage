# Seoul Bus/Subway Evidence Runbook

> **2026-08-23 정정:** "Kakao alternate boarding"으로 표기됐던 항목은 실제로는
> 서울시 data.go.kr mixed-route(`getPathInfoByBusNSub`) 응답의 대안 후보다 — Kakao는
> 이 프로젝트의 provider가 아니다. 근거: `03_SEOUL_MIXED_ROUTE_AND_WALK_RUNBOOK.md` 상단,
> `docs/history/transit_journey_handoff_FINAL_v3/docs/05_DECISION_LOG.md`(D-024/D-043/D-045).

## 1. 공통 원칙

- 실제 approved limit·remaining을 확인한 뒤 시작한다.
- 기존 collector가 있으면 수정 없이 사용한다.
- 필요한 기능이 없으면 새 collector를 개발하지 않고 `BLOCKED_TOOLING`으로 기록한다.
- requestedAt은 send 직전, receivedAt은 receive 직후에 기록한다.
- source time과 collector receive time을 분리한다.
- raw row count를 independent support로 사용하지 않는다.
- prediction 시점 이후에 알게 된 Actual 정보를 prediction feature로 사용하지 않는다.

## 2. Bus target contract

Route A 핵심 identity:

| 역할 | 값 |
|---|---|
| route | 01A |
| busRouteId | `100100001` |
| approved boarding | 춘추문 `stId=100000417`, `staOrd=19` |
| target alight | 안국역6번출구 `stId=100000104`, `staOrd=21` |
| Mixed-route(data.go.kr) alternate boarding | 경복궁.국립민속박물관 `stId=100000418`, `staOrd=20` |

Mixed-route alternate와 approved Route A의 event/residual을 합치지 않는다.

## 3. Bus Run B1 — Credential/quota preflight

1. portal의 approved limit·현재 사용량·remaining을 캡처한다.
2. Arrival 1회, Position 1회를 호출한다.
3. counter 전후와 business status를 비교한다.
4. Arrival+Position이 같은 quota group인지 분리 집계인지 기록한다.
5. approved limit가 확인되지 않으면 sustained run을 중단한다.

`ERROR`, no-data, HTTP 200 business error를 모두 raw로 보존한다. quota 확인을 위해 고의 소진하지 않는다.

## 4. Bus Run B2 — Coordinated target collection

각 window에서 Arrival과 Position을 같은 logical cycle로 묶는다.

필수 observation:

- route/stop/vehicle identity
- target stId/staOrd
- candidate vehId 1/2
- prediction ETA와 provider 생성시각
- position stopFlag/section/last stop context
- requestedAt/receivedAt/source time
- response hash·cycleId

권장 cadence는 `02_API_BUDGET_AND_DAY_SCHEDULE.md`의 예산 안에서 30초를 기본으로 한다. 실제 counter가 예상과 다르면 즉시 중단한다. cadence는 실험 schedule이며 제품 stale threshold가 아니다.

## 5. Bus Run B3 — Actual interval

Actual candidate는 다음을 모두 충족해야 한다.

- same `busRouteId`
- same `vehId`
- validated target stop context
- nondecreasing source time 또는 명시적 out-of-order flag
- target에서 `stopFlag 0→1`

polling으로 exact arrival instant를 알 수 없으면:

```text
ActualArrivalInterval = (previousObservedAt, firstArrivalObservedAt]
midpoint = interval midpoint
width = upper - lower
```

다음을 Actual로 만들지 않는다.

- `1→0` departure
- 단순 차량 교체
- 다른 stop의 `0→1`
- missing target identity
- source-time reversal을 정렬로 숨긴 observation

event가 없으면 `NO_VALID_ACTUAL_EVENT`이며 rule을 느슨하게 바꾸지 않는다.

## 6. Bus Run B4 — Prediction→Actual Residual

Actual event 이전의 동일 vehicle/target prediction만 사용한다.

```text
predictedArrival = predictionObservedAt + providerETA
residualLower = actualLower - predictedArrival
residualMid = actualMid - predictedArrival
residualUpper = actualUpper - predictedArrival
```

- signed residual을 유지한다.
- `abs(residual)`을 ride duration으로 쓰지 않는다.
- 춘추문→안국 traverse duration 11건을 residual로 재분류하지 않는다.
- event 수가 적어도 builder correctness는 평가할 수 있지만 distribution maturity는 평가하지 않는다.

## 7. Bus Run B5 — WAIT event unit/dependence

동일 boarding stop의 snapshot을 다음 단위로 비교한다.

| 단위 | 용도 | support 사용 |
|---|---|---|
| raw poll row | raw observation | independent support 금지 |
| same vehicle progression | diagnostic sequence | 한 event 내부 dependence |
| validated arrival event | passenger-relevant candidate | event unit 후보 |
| inter-arrival/headway | WAIT 후보 | 여러 독립 window 전 maturity 금지 |

window별로 기록한다.

- raw rows
- unique vehicles
- validated arrival events
- duplicate snapshot ratio
- receive-order out-of-order count
- 동일 차량 ETA/position progression
- event 간 시간
- autocorrelation은 사용한 series·lag·sample unit을 명시

하루 세 window는 multi-window mechanics evidence지만 mature empirical WAIT를 확정하기에는 부족하다.

## 8. Subway target contract

Route A station×line:

- 안국 3호선
- 교대 3호선
- 교대 2호선
- 역삼 2호선

같은 `교대` 이름을 line 없이 join하지 않는다. 기본 identity는 `subwayId×statnId×trainNo`다.

## 9. Subway Run S1 — Quota/reset preflight

1. key 사용량·remaining·최근 quota error를 확인한다.
2. station arrival 1회와 line position 1회를 bounded 호출한다.
3. HTTP status와 business error를 분리한다.
4. counter와 call ledger가 맞는지 확인한다.
5. key rotation으로 우회하지 않는다.

오늘은 일요일이므로 service day를 `END`로 기록한다. 평일·토요일 검증으로 일반화하지 않는다.

## 10. Subway Run S2 — Coordinated collection

두 개의 분리된 45분 window에서:

- 네 station×line arrival: 60초 cadence
- 두 line position: 30초 cadence
- 하나의 shared cycle/manifest
- 최대 750 calls
- 최소 200 calls reserve

실제 collector query 구조가 다르면 호출식을 먼저 계산하고 같은 reserve를 유지한다.

## 11. Subway Run S3 — Identity and Actual

각 observation에 다음이 있어야 한다.

- subwayId
- statnId
- station display name
- trainNo
- direction/updnLine
- arvlCd와 ETA/prediction field
- source/receive timestamp

Actual candidate:

```text
same subwayId×statnId×trainNo
and first transition arvlCd != 1 → 1
```

polling interval 때문에 exact time을 모르면 Bus와 동일하게 interval로 저장한다. 교대 L2/L3가 섞이면 해당 event는 invalid다.

## 12. Subway Run S4 — Residual·lateness·out-of-order

- Actual 이전 prediction과만 연결한다.
- signed interval residual을 생성한다.
- receive order에서 source-time reversal을 먼저 측정한다.
- canonical sort 후에는 out-of-order evidence를 제거하지 않는다.
- latency는 requestedAt→receivedAt이며 provider internal processing time으로 부르지 않는다.
- station/line/window별 event 수를 분리한다.

한 일요일 두 window는 component/corridor evidence다. mature distribution, DAY/SAT generalization, Journey calibration은 금지한다.

## 13. Run 결과표

| Run | Window | Calls | Raw rows | Unique entities | Valid Actual | Residual | DQ flags | Quota end | 판정 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| B1/B2/B3 |  |  |  |  |  |  |  |  |  |
| S1/S2 |  |  |  |  |  |  |  |  |  |

event가 없거나 quota 때문에 중단돼도 raw와 `NO_VALID_EVENT/SAFE_STOP`을 보존한다. 이를 0초·0%·support 0으로 변환하지 않는다.

## 14. Zero-call offline evidence checks

API window 사이에는 기존 파일만으로 다음을 확인한다. 새 코드가 필요하면 구현하지 않고 기존 analyzer·read-only 명령만 사용한다.

### Timetable/service day

- Route A timetable source date·version·encoding
- 2026-08-23 `END` service-day 선택
- `>=24:00` rollover가 다음 달력일이 아니라 같은 service date의 연장시각으로 보존되는지
- candidate service set과 direction/line/station identity
- static timetable을 현재 운행 exact guarantee로 사용하지 않는지

### Transfer/reference

- 교대 3→2 source별 거리·시간·산식 의미
- operational reference와 sanity reference를 평균하지 않는지
- B2S street WALK와 station internal component가 분리되는지
- station depth를 초 단위 시간으로 환산하지 않는지

### Existing evidence reconciliation

- Phase 1/2 Bus traverse-time와 ResidualEvent가 분리되는지
- Bus WAIT snapshot 181개를 181 independent event로 세지 않는지
- failed vertical-slice numeric result가 demo/user-facing으로 승격되지 않는지
- TMAP WALK의 좌표쌍·provider·version이 동일하게 추적되는지

이 점검은 source semantics를 확정할 수 있지만 새로운 실제 운행 outcome이나 확률 calibration evidence를 만들지는 않는다.
