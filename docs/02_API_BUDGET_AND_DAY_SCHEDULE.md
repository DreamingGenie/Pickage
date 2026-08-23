# API Budget and Day Schedule

> 모든 숫자는 2026-08-23 하루 실험의 안전 상한이다. 제품 SLA·collector 운영 threshold·provider 공식 보장으로 사용하지 않는다.

> **2026-08-23 정정(2차):** 1차 정정에서 "Kakao"를 "data.go.kr 공용 키 하나가 Bus+Mixed-route
> 쿼터를 전부 공유한다"로 바꿔 썼으나, 이는 과도한 통합이었다. 실제로 각 포털에 로그인해
> 마이페이지를 직접 확인한 결과는 다음과 같다.
>
> - **data.go.kr**: `DATA_GO_BUS_API_KEY`는 계정 전체에서 값이 동일한 키 문자열이지만
>   (D-013/D-046), **일일 트래픽 한도는 활용신청(서비스)×상세기능 단위로 각각 1,000건씩
>   독립 부여**된다 — 마이페이지에서 Bus Arrival(`getArrInfoByRouteAllList` 등 4개 기능),
>   Bus Position(`getBusPosByRouteStList` 등 5개 기능), Mixed-route(`getPathInfoByBusNSubList`
>   등 4개 기능) 각각의 "일일 트래픽" 열이 모두 1,000으로 별도 표시됨. 즉 mixed-route 호출은
>   bus arrival/position의 예산을 갉아먹지 않는다 — 이 문서 3.1/3.4의 "차감" 서술은 폐기한다.
> - **서울 열린데이터광장 일반인증키**(`SEOUL_OPEN_API_KEY`): 포털 공식 안내("인증키
>   관리" 페이지) 기준 **호출 "횟수" 제한은 없음** — 1회 호출당 최대 1,000건(row) 조회
>   제한만 있다(페이지네이션 상한이지 daily call quota가 아니다).
> - **서울 열린데이터광장 지하철인증키**(`SEOUL_SUBWAY_REALTIME_KEY`): 포털 공식 안내
>   기준 **1일 1,000회/키**(활용사례 갤러리 등록·승인 시 무제한 전환 가능 — 이 프로젝트는
>   미등록 상태). 오늘 실험은 등록 여부와 무관하게 1,000/day 상한으로 취급한다.
>
> "오늘 사용량(used-so-far)"은 두 포털 모두 실시간 카운터 UI가 없어(서울 일반인증키의
> "이용내역"은 0건으로 표시되지만 이는 조회 자체가 비어있는 것이지 실시간 사용량 대시보드가
> 아니다) 직접 확인 불가 — 첫 preflight 호출 자체를 오늘의 시작점으로 삼는다.

## 1. Preflight ledger

실험 전 실제 화면·응답에서 다음 표를 채운다. `remaining` 또는 approved limit가 확인되지 않은 credential은 반복 수집을 시작하지 않는다.

| Provider/Endpoint | Approved daily limit | Start used | Start remaining | Reset evidence | Billing/overage | Experiment cap | Reserve | 상태 |
|---|---:|---:|---:|---|---|---:|---:|---|
| data.go.kr Bus Arrival(`getArrInfoByRouteAllList` 등, 서비스별 독립 집계) | 1,000/day(portal 확인, 2026-08-23) | 미상(대시보드 없음) | ≤1,000 | portal 정책 텍스트 | N/A | 3.4 참조 | 최소 200 | READY |
| data.go.kr Bus Position(`getBusPosByRouteStList` 등, 독립 집계) | 1,000/day(portal 확인) | 미상 | ≤1,000 | portal 정책 텍스트 | N/A | 3.4 참조 | 최소 200 | READY |
| data.go.kr Mixed-route(`getPathInfoByBusNSubList`, 독립 집계) | 1,000/day(portal 확인) | 미상 | ≤1,000 | portal 정책 텍스트 | N/A | 최대 30 | 최소 100 | READY |
| 서울 열린데이터광장 일반인증키(SEOUL_OPEN_API_KEY, 역사적 데이터 등) | 호출 횟수 무제한(portal 공식 안내, 1회당 최대 1,000건 page cap만 존재) | 0(이용내역 조회 결과) | 사실상 무제한 | portal 정책 텍스트 | N/A | 필요 시에만 | — | READY |
| 서울 열린데이터광장 지하철인증키(SEOUL_SUBWAY_REALTIME_KEY) | 1,000/day(portal 공식 안내, 갤러리 미등록) | 미상(대시보드 없음) | ≤1,000 | portal 정책 텍스트 | N/A | 최대 750 | 최소 200 | READY |
| TMAP pedestrian | project credential 값(구독 기반, 대시보드 미확인) | 미상 | 미상 | response/console | policy 확인 | 최대 10 | 최소 3 | `UNCONFIRMED` 전 대규모 반복 금지 |

오늘 사용하지 않는 provider(참고용, 재시도 금지):

| Provider | 상태 | 근거 |
|---|---|---|
| Kakao Mobility 도보 길찾기 | `BLOCKED` — 제휴 미승인 | D-043, `HTTP 403 permission denied` |
| TMAP 대중교통(길찾기) | `NOT_SUBSCRIBED` — 이 프로젝트에서 구독/검증된 적 없음 | `01_PROJECT_HANDOFF.md` §6.2 Walking/Access Time 섹션 |

## 2. 공통 예산 산식

```text
confirmed_remaining = provider console 또는 응답으로 확인한 remaining
reserved_calls = demo/recovery/오류 방지를 위해 남길 양
allowed_experiment_calls = min(documented_experiment_cap,
                               confirmed_remaining - reserved_calls)
```

- `confirmed_remaining - reserved_calls <= 0`이면 해당 provider 실험을 실행하지 않는다.
- retry·business error·timeout도 사용량으로 계산한다.
- **data.go.kr은 서비스(Bus Arrival/Position/Mixed-route)별로 별도 1,000/day이므로
  서로 차감하지 않는다** — 각 서비스 자신의 ledger row만 본다. 단, 여러 process가 같은
  서비스의 같은 기능을 동시에 폴링하면 그 서비스 안에서는 합산한다.
- quota 한도를 알아내기 위해 고의로 끝까지 호출하지 않는다.
- 사용량 counter가 예상보다 빠르게 증가하면 즉시 모든 poller를 중단한다(포털에
  실시간 대시보드가 없으므로 business error 발생 자체를 신호로 삼는다).

## 3. Provider별 권장 예산

### 3.1 Mixed-route(`getPathInfoByBusNSub`) · data.go.kr · 최대 30회

Bus Arrival/Position과 키 문자열은 같지만 예산은 **별도**다(1절 정정 참고). 30회는 mixed-route 자신의 1,000/day 안에서 쓰는 예산이다.

| 묶음 | 호출 상한 | 목적 |
|---|---:|---|
| Demo Corridor(삼청동↔역삼역) OD 반복 | 6 | 오전·낮·저녁 각 2회 signature 비교 — D-031에서 주/야간 안정 재현 이미 확인, 오늘은 추가 window 검증 |
| topology 다변화 | 12 | subway-only, bus-only, mixed, multi-transfer 등 6 OD×2회 |
| coordinate/edge/error semantics | 4 | 동일점·짧은 거리·서울 밖 또는 invalid를 bounded 확인 |
| 재시도·예외 reserve | 8 | timeout/business error 발생 시에도 cap 유지 |

동일 request가 이미 2026-08-21/22에 여러 번 존재하므로(D-024, D-031, D-047) 각 window 2회면 burst stability를 볼 수 있다. API가 departure time을 입력받지 않으므로 시간대가 다른 결과는 구조 변화와 시간 변화로 분리 기록한다.

### 3.2 TMAP pedestrian(WALK) · 최대 10회

| 묶음 | 호출 상한 | 목적 |
|---|---:|---|
| Route A ACCESS 좌표 반복 | 3 | point repeatability |
| B2S·FINAL 동일 좌표 | 3 | 각 pair 반복 및 provider provenance |
| mixed-route hidden access/final walk 비교 | 3 | 대표 후보 1~2개 첫/끝 지점 |
| reserve | 1 | 오류·재수행 |

D-045에서 이미 GO/스키마 확인이 끝났으므로, 오늘은 반복 안정성과 hidden-gap 비교에 집중하고 같은 결론을 반복하기 위한 호출은 하지 않는다.

### 3.3 서울 열린데이터광장 지하철인증키(realtime subway) · 최대 750회

approved limit는 포털 공식 안내로 confirmed(1,000/day, 갤러리 미등록 기준). Route A station×line 4개와 line position 2개를 coordinated 수집한다.

한 45분 window의 보수적 산식:

```text
arrival = 4 station×line × 45회(60초 cadence) = 180
position = 2 lines × 90회(30초 cadence) = 180
window total = 360 calls
2 windows = 720 calls
preflight/recovery reserve inside cap = 30 calls
```

실제 endpoint가 한 요청에 여러 대상을 반환하더라도 budget은 보수적으로 요청 수를 센다. 사용량 대시보드가 없으므로 720+30=750이 1,000/day 한도의 75%에 그친다는 점을 여유로 삼되, quota business error가 나오면 즉시 중단한다. D-048에서 15분 창으로는 `arvlCd=1` 실제 도착 event가 0건이었으므로, 오늘은 window를 45분으로 늘려 재시도한다.

### 3.4 data.go.kr Bus Arrival · Bus Position · 각각 독립 최대 400회

approved limit는 각각 1,000/day로 confirmed(portal). 서로 다른 서비스이므로 각자의 cap을 쓴다 — mixed-route(3.1)의 30회를 여기서 차감하지 않는다.

```text
bus_experiment_cap = min(400, 1000 - reserved(200))  # 서비스별로 각각 적용
```

Arrival과 Position이 각각 한 번 호출되는 30초 cycle이면:

```text
2 endpoints × 60 cycles(30분) = 120 calls/window (Arrival 60 + Position 60, 각자 cap 안에서 집계)
3 windows = 360 calls
preflight/recovery = 최대 40
```

- 두 서비스 모두 1,000/day이고 오늘 계획한 최대 사용량(360+40=400)은 각각 40%에 불과하므로 3 window 전부 가능
- business error나 예상 밖 counter 증가가 보이면 그 즉시 해당 서비스만 중단(다른 서비스는 별도 quota이므로 영향 없음)

### 3.5 TMAP

- pedestrian은 project limit 확인 후 기존과 같은 세 좌표쌍을 최대 몇 회씩 호출한다(3.2 참조).
- TMAP 대중교통(길찾기) 상품은 이 프로젝트에서 구독·검증된 적이 없으므로 오늘 사용하지
  않는다. 필요하면 `BLOCKED_TOOLING`(미구독)으로 기록하고 별도 구독 신청 이후 재평가한다.
- 기존 evidence(D-044/D-045)가 충분하면 새 호출보다 pedestrian reserve를 우선한다.
- mixed-route 결과 실패를 TMAP 값으로 조용히 대체하지 않는다.

## 4. 2026-08-23 KST 실행 일정

2026-08-23은 일요일이므로 timetable/service day는 `END`다. 이 하루로 `DAY` 또는 `SAT` 동작을 검증했다고 주장하지 않는다.

| 시간 | 작업 | 주요 provider | 종료조건 |
|---|---|---|---|
| 시작 직후 | portal 캡처, remaining·reset·credential 상태 입력(완료 — 1절 참고) | 전체 | ledger 미완성 provider는 호출 금지 |
| 07:20~07:30 | endpoint별 1회 preflight, counter 전후 확인 | data.go.kr(Bus×2+Mixed-route)/Subway/TMAP 선택 | 예상과 다른 counter 증가 시 중단 |
| 07:30~08:15 | Subway window S1, Mixed-route Demo Corridor burst K1 | Subway/Mixed-route | subway budget 360, mixed-route 2회 |
| 08:20~08:50 | Bus window B1 | Bus | cap에 따른 30분 |
| 09:00~11:00 | raw/hash/schema·crosswalk·hidden segment 분석 | Mixed-route/기존 evidence | 신규 호출 없이 판정 |
| 12:20~12:50 | Bus window B2, Mixed-route burst K2 | Bus/Mixed-route | quota forecast 갱신 |
| 13:00~15:00 | topology 다변화·WALK boundary(TMAP) | Mixed-route/TMAP | 중복 결과면 조기 종료 |
| 17:30~18:15 | Subway window S2 (45분으로 확장, D-048 후속) | Subway | reserve 최소 200 유지 |
| 18:20~18:50 | Bus window B3, Mixed-route burst K3 | Bus/Mixed-route | provider cap 도달 전 종료 |
| 19:00 이후 | evidence manifest, decision sheet, planning docs upgrade | 호출 없음 | raw 누락 확인 시 claim 승격 금지 |

사용자의 실제 시작시간이 다르면 시각 자체보다 `서로 분리된 window`와 shared budget을 유지한다.

## 5. 공통 중단 기준

다음 중 하나면 해당 provider를 즉시 중단한다.

- quota/entitlement/rate-limit business error
- remaining 또는 counter를 확인할 수 없음(두 포털 모두 실시간 사용량 대시보드가 없으므로, business error 발생 자체가 사실상 유일한 신호다)
- 계획 대비 counter 증가가 2배 이상
- secret이 raw/log/terminal 저장물에 포함됨
- 응답 timestamp·request boundary time을 기록하지 못함
- 동일 schema 결과만 반복되어 신규 evidence yield가 없음
- target identity 또는 coordinate role이 불명확함
- collector 두 개가 같은 서비스의 같은 quota를 중복 계산함(단, Bus Arrival/Position/
  Mixed-route는 서로 다른 quota이므로 이들 간에는 중복 계산 문제가 없다)

중단은 실패가 아니라 `SAFE_STOP` evidence다. 다른 key로 우회하지 않는다.
