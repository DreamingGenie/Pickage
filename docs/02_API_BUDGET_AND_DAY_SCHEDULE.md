# API Budget and Day Schedule

> 모든 숫자는 2026-08-23 하루 실험의 안전 상한이다. 제품 SLA·collector 운영 threshold·provider 공식 보장으로 사용하지 않는다.

## 1. Preflight ledger

실험 전 실제 화면·응답에서 다음 표를 채운다. `remaining` 또는 approved limit가 확인되지 않은 credential은 반복 수집을 시작하지 않는다.

| Provider/Endpoint | Approved daily limit | Start used | Start remaining | Reset evidence | Billing/overage | Experiment cap | Reserve | 상태 |
|---|---:|---:|---:|---|---|---:|---:|---|
| Kakao publictraffic | 1,000 confirmed |  |  | console/response | unconfirmed | 30 | `start remaining-actual calls` | READY after counter check |
| Kakao WALK | 1,000 confirmed |  |  | console/response | unconfirmed | 40 | `start remaining-actual calls` | READY after counter check |
| Seoul realtime subway | official base 1,000; actual key 확인 |  |  | portal/error | N/A | 최대 750 | 최소 200 | remaining 확인 후 |
| Seoul Bus Arrival | portal 값 |  |  | portal/error | N/A | 아래 산식 | 최소 50% 또는 200 | `UNCONFIRMED` 전 금지 |
| Seoul Bus Position | portal 값 |  |  | portal/error | N/A | Arrival과 합산 | 동일 | `UNCONFIRMED` 전 금지 |
| TMAP public transit | free trial 10/day |  |  | response/console | policy 확인 | 최대 3 | 최소 7 | validation-only |
| TMAP pedestrian | project credential 값 |  |  | console | policy 확인 | 최대 3 | 확인값-실사용 | limit 확인 후 |

## 2. 공통 예산 산식

```text
confirmed_remaining = provider console 또는 응답으로 확인한 remaining
reserved_calls = demo/recovery/오류 방지를 위해 남길 양
allowed_experiment_calls = min(documented_experiment_cap,
                               confirmed_remaining - reserved_calls)
```

- `confirmed_remaining - reserved_calls <= 0`이면 해당 provider 실험을 실행하지 않는다.
- retry·business error·timeout도 사용량으로 계산한다.
- 여러 process가 같은 credential을 쓰면 하나의 shared ledger로 합산한다.
- quota 한도를 알아내기 위해 고의로 끝까지 호출하지 않는다.
- 사용량 counter가 예상보다 빠르게 증가하면 즉시 모든 poller를 중단한다.

## 3. Provider별 권장 예산

### 3.1 Kakao publictraffic · 최대 30회

| 묶음 | 호출 상한 | 목적 |
|---|---:|---|
| 기존 Route A OD 반복 | 6 | 오전·낮·저녁 각 2회 signature 비교 |
| topology matrix | 12 | subway-only, bus-only, mixed, multi-transfer 등 6 OD×2회 |
| coordinate/edge/error semantics | 4 | 동일점·짧은 거리·서울 밖 또는 invalid를 bounded 확인 |
| 재시도·예외 reserve | 8 | timeout/business error 발생 시에도 cap 유지 |

동일 request가 이미 2026-08-22 한 번 존재하므로 각 window 2회면 burst stability를 볼 수 있다. API가 departure time을 입력받지 않으므로 시간대가 다른 결과는 구조 변화와 시간 변화로 분리 기록한다.

### 3.2 Kakao WALK · 최대 40회

| 묶음 | 호출 상한 | 목적 |
|---|---:|---|
| 동일 Route A ACCESS 반복 | 3 | point repeatability |
| B2S·FINAL 동일 좌표 | 6 | 각 pair 반복 및 provider provenance |
| publictraffic hidden access/egress | 16 | 대표 후보 최대 4개×양 끝×최대 2회 |
| route_mode comparison | 6 | 한 대표 pair에서 3 mode×2회 |
| reverse/short/invalid semantics | 3 | coordinate role·오류 taxonomy |
| reserve | 6 | 오류·재수행 |

hidden segment 검증이 1~2개 후보에서 명확해지면 나머지 호출은 중단한다. 같은 결론을 반복하기 위한 호출은 evidence 가치가 없다.

### 3.3 Seoul realtime subway · 최대 750회

Route A station×line 4개와 line position 2개를 coordinated 수집한다.

한 45분 window의 보수적 산식:

```text
arrival = 4 station×line × 45회(60초 cadence) = 180
position = 2 lines × 90회(30초 cadence) = 180
window total = 360 calls
2 windows = 720 calls
preflight/recovery reserve inside cap = 30 calls
```

실제 endpoint가 한 요청에 여러 대상을 반환하더라도 budget은 보수적으로 요청 수를 센다. confirmed remaining이 950보다 작으면 두 번째 window를 축소하거나 생략해 최소 200회를 남긴다.

### 3.4 Seoul Bus Arrival+Position · 동적 상한

Bus approved limit가 문서에서 미확정이므로 포털 확인 전 숫자를 고정하지 않는다.

```text
bus_experiment_cap = min(400,
                         floor(confirmed_remaining × 0.50))
```

Arrival과 Position이 각각 한 번 호출되는 30초 cycle이면:

```text
2 endpoints × 60 cycles(30분) = 120 calls/window
3 windows = 360 calls
preflight/recovery = 최대 40
```

- cap이 400 이상이면 30분 window 3개
- cap이 240~399이면 30분 window 2개
- cap이 120~239이면 target arrival 가능성이 높은 window 1개
- cap이 120 미만이거나 remaining 불명확하면 sustained collector 금지

### 3.5 TMAP

- 대중교통은 최대 3/10회만 사용한다: Route A OD 2회, alternate 1회.
- pedestrian은 project limit 확인 후 기존과 같은 세 좌표쌍을 최대 1회씩 호출한다.
- 기존 evidence가 충분하면 새 호출보다 7회 이상의 public-transit reserve를 우선한다.
- Kakao 결과 실패를 TMAP 값으로 조용히 대체하지 않는다.

## 4. 2026-08-23 KST 실행 일정

2026-08-23은 일요일이므로 timetable/service day는 `END`다. 이 하루로 `DAY` 또는 `SAT` 동작을 검증했다고 주장하지 않는다.

| 시간 | 작업 | 주요 provider | 종료조건 |
|---|---|---|---|
| 시작 직후 | console/portal 캡처, remaining·reset·credential 상태 입력 | 전체 | ledger 미완성 provider는 호출 금지 |
| 07:20~07:30 | endpoint별 1회 preflight, counter 전후 확인 | Kakao/Seoul/TMAP 선택 | 예상과 다른 counter 증가 시 중단 |
| 07:30~08:15 | Subway window S1, Kakao Route A burst K1 | Subway/Kakao | subway budget 360, Kakao 2회 |
| 08:20~08:50 | Bus window B1 | Bus | cap에 따른 30분 |
| 09:00~11:00 | raw/hash/schema·crosswalk·hidden segment 분석 | Kakao/기존 evidence | 신규 호출 없이 판정 |
| 12:20~12:50 | Bus window B2, Kakao burst K2 | Bus/Kakao | quota forecast 갱신 |
| 13:00~15:00 | topology matrix·WALK boundary·TMAP golden | Kakao/TMAP | 중복 결과면 조기 종료 |
| 17:30~18:15 | Subway window S2 | Subway | reserve 최소 200 유지 |
| 18:20~18:50 | Bus window B3, Kakao burst K3 | Bus/Kakao | provider cap 도달 전 종료 |
| 19:00 이후 | evidence manifest, decision sheet, planning docs upgrade | 호출 없음 | raw 누락 확인 시 claim 승격 금지 |

사용자의 실제 시작시간이 다르면 시각 자체보다 `서로 분리된 window`와 shared budget을 유지한다.

## 5. 공통 중단 기준

다음 중 하나면 해당 provider를 즉시 중단한다.

- quota/entitlement/rate-limit business error
- remaining 또는 counter를 확인할 수 없음
- 계획 대비 counter 증가가 2배 이상
- secret이 raw/log/terminal 저장물에 포함됨
- 응답 timestamp·request boundary time을 기록하지 못함
- 동일 schema 결과만 반복되어 신규 evidence yield가 없음
- target identity 또는 coordinate role이 불명확함
- collector 두 개가 같은 credential budget을 중복 계산함

중단은 실패가 아니라 `SAFE_STOP` evidence다. 다른 key로 우회하지 않는다.
