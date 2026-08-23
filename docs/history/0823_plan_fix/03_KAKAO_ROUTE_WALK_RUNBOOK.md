# Kakao Route/WALK Evidence Runbook

## 1. 목표

Kakao의 사용 가능 여부를 다시 확인하는 것이 아니라 다음 네 문제를 좁힌다.

1. 동일 OD에서 candidate 구조와 순서가 반복 가능한가.
2. publictraffic `total - step sum` gap은 무엇을 포함하는가.
3. provider ID가 없는 응답을 서울시 canonical identity에 결정적으로 연결할 수 있는가.
4. Kakao candidate와 승인 Route A를 제품에서 어떻게 분리해야 하는가.

## 2. 기준 raw

| 파일 | SHA-256 | 확인 범위 |
|---|---|---|
| `kakao_map_publictraffic_20260822T100523Z.json` | `88feba0e6c6683ce95f155005ba635149b5de3ab87e349d288ceeae07d9e6ede` | HTTP 200/OK, 15 routes, secret false |
| `kakao_map_walk_20260822T100523Z.json` | `f578c91a2a3e5e5505e222fb83867d51cf7e2ddcbbb01128c9f25429cc0ccc16` | HTTP 200/OK, 295m/323s, secret false |

기준 publictraffic input:

- origin: `(126.9818, 37.5817)`
- destination: `(127.0365, 37.5007)`

기준 WALK input은 다른 좌표쌍이다.

- origin: `(126.9809, 37.5825)`
- destination 춘추문: `(126.97965309715137, 37.58308213227146)`

두 결과를 같은 access leg라고 혼합하지 않는다.

## 3. Run manifest 필수 필드

각 호출은 다음을 저장한다.

- runId, purpose, scenarioId
- providerKey=`KAKAO_MAP_PUBLIC_TRANSIT` 또는 `KAKAO_MAP_WALK`
- endpoint, adapter/probe file hash
- exact request params와 coordinate role
- requestedAtUtc, receivedAtUtc, response Date, x-request-id
- HTTP status, Kakao status, business error
- sanitized response file path와 SHA-256
- console used/remaining before·after
- secretIncluded=false 검사 결과

API key는 환경변수로만 사용하고 manifest·명령 history·raw에 기록하지 않는다.

## 4. Experiment K1 — Same-OD candidate stability

기준 OD를 오전·낮·저녁 window에서 각각 두 번 호출한다. 같은 window의 두 요청은 정확히 같은 params를 사용한다.

각 candidate의 signature:

```text
candidateIndex
routeType
totalDistance
totalTime
transfers
ordered(step.type)
ordered(step.distance, step.time)
ordered(vehicle.name, vehicle.type)
ordered(firstStop.name, lastStop.name, stopCount)
first/last path coordinate
```

판정:

| 결과 | 상태 |
|---|---|
| 같은 window의 signature·order가 동일 | `BURST_STABLE_FOR_TESTED_OD` |
| 같은 window에서 order 또는 topology가 다름 | `BURST_VARIABLE` |
| 다른 시간대에서만 변화 | `TIME_WINDOW_VARIATION_OBSERVED` |
| raw/params 불완전 | `INCONCLUSIVE` |

한 OD의 안정성을 서울 전체 mapping failure rate로 바꾸지 않는다.

## 5. Experiment K2 — Topology matrix

기존 프로젝트가 이미 ID와 좌표를 가진 서울 지점을 사용하여 다음 topology를 선택한다. 각 scenario는 같은 request를 두 번 호출한다.

| Scenario | 목적 | 필수 확인 |
|---|---|---|
| subway-only | station×line 표현 | line name, station sequence, transfer WALK |
| bus-only | bus route/stop 표현 | vehicle alternatives, stop sequence, ID 부재 |
| bus→subway | B2S 경계 | alight→station WALK와 line identity |
| subway→bus | S2B 경계 | station exit/버스 stop ambiguity |
| multi-transfer | 여러 WALK/ride 순서 | transfer count와 step count 의미 |
| short/edge OD | no route·walking-heavy 상태 | empty/business error taxonomy |

새로운 POI를 임의 선택하기보다 기존 Route A/B와 supporting evidence의 좌표를 우선한다. 각 결과는 scenario 범위로만 판정한다.

## 6. Experiment K3 — Hidden gap decomposition

### 6.1 기준 후보

후보 index 0:

- route type: SUBWAY
- total: 15,861m / 2,651s
- step sum: 14,942m / 1,764s
- gap: 919m / 887s
- first path point: `(126.9854237, 37.57650012)`
- last path point: `(127.03646947, 37.50067442)`

후보 index 2:

- route type: BUS_AND_SUBWAY
- total: 16,396m / 2,688s
- step sum: 15,928m / 2,266s
- gap: 468m / 422s
- first path point: `(126.9795745, 37.57933009)`
- last path point: `(127.03646947, 37.50067442)`

### 6.2 WALK 비교

각 후보에 대해 별도 WALK 호출을 수행한다.

1. publictraffic origin → first path point
2. last path point → publictraffic destination

기록:

```text
gapDistance = route.totalDistance - sum(step.distance)
gapTime = route.totalTime - sum(step.time)
walkBoundaryDistance = accessWalk.totalDistance + finalWalk.totalDistance
walkBoundaryTime = accessWalk.totalTime + finalWalk.totalTime
distanceDelta = gapDistance - walkBoundaryDistance
timeDelta = gapTime - walkBoundaryTime
```

판정:

| 상태 | 기준 |
|---|---|
| `EXPLICITLY_EXPLAINED` | API field 또는 공식 계약이 gap 구성요소를 명시 |
| `HIDDEN_WALK_STRONGLY_SUPPORTED` | WALK 비교가 gap을 설명하지만 raw가 명시하지 않음 |
| `PARTIALLY_EXPLAINED` | 일부만 일치하거나 다른 component가 남음 |
| `AMBIGUOUS` | gap과 boundary WALK가 의미 있게 연결되지 않음 |

수치 tolerance를 사전에 발명하지 않는다. exact delta와 route mode를 그대로 기록한다. `HIDDEN_WALK_STRONGLY_SUPPORTED`도 WAIT가 없다는 보장은 아니다.

## 7. Experiment K4 — WALK contract

다음 좌표쌍을 provider별로 분리한다.

- Route A origin→춘추문 ACCESS
- 01A 안국 하차점→안국 station reference B2S street
- 역삼 station reference→멀티캠퍼스 FINAL
- K3의 hidden access/final pairs

확인:

- route total과 leg 합
- leg와 step 합의 차이
- geometry first/last와 request point 관계
- route_mode별 결과
- reverse request 결과
- empty/too-short/error semantics

각 값은 `DETERMINISTIC_POINT` 또는 provider point/reference다. 반복 결과가 같아도 개인 WALK distribution이 아니다.

## 8. Experiment K5 — Canonical crosswalk

### 8.1 Payload 사실

기준 raw에서는:

- stop object: `name`
- vehicle object: `name,type`
- path object: `points`
- busRouteId/stId/stationId: 없음

### 8.2 Crosswalk candidate key

BUS:

```text
vehicle name/type
+ ordered stop names
+ path endpoint coordinates
+ 서울 route stop order/version
```

SUBWAY:

```text
vehicle line name
+ station name
+ ordered station sequence
+ path endpoint coordinates
+ 서울 station×line crosswalk version
```

판정은 `MAPPED/AMBIGUOUS/INCOMPLETE` 중 하나다. fuzzy name match 하나만으로 `MAPPED`를 부여하지 않는다.

### 8.3 Route A mismatch test

승인 Route A:

- 01A `춘추문(stId=100000417, staOrd=19)`
- → `안국역6번출구(stId=100000104, staOrd=21)`

Kakao candidate index 2:

- 01A `경복궁.국립민속박물관(stId=100000418, staOrd=20)` 후보
- → `안국역6번출구(stId=100000104, staOrd=21)` 후보

기존 서울시 route table과 path endpoint로 이 mapping을 검증한다. 검증돼도 두 route는 동일하지 않다. Kakao 값을 승인 Route A의 19→21 BUS_RIDE에 재사용하지 않는다.

## 9. Kakao Gate 출력

| Gate | 판정 | Evidence | 적용범위 | 남은 조치 |
|---|---|---|---|---|
| API access |  |  | endpoint |  |
| app limit |  |  | app/endpoint/day | billing/reset 분리 |
| raw integrity |  |  | files/hash | register enrollment |
| time semantics |  |  | candidate/OD |  |
| canonical mapping |  |  | topology/corridor |  |
| repeat stability |  |  | OD/windows |  |
| Primary eligibility |  |  | deployment |  |

Gate 하나라도 핵심적으로 미통과면 `ROUTE_A_ONLY`를 유지한다. Kakao 첫 candidate는 Route A Demo나 BUS_SKIPPED narrative를 대신하지 않는다.

