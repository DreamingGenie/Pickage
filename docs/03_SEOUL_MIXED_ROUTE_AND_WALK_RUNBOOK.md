# Seoul Mixed-Route / TMAP Walk Evidence Runbook

> **파일명 변경 이력:** 원래 `03_KAKAO_ROUTE_WALK_RUNBOOK.md`였다. Kakao는 이
> 프로젝트에서 대중교통 경로 provider였던 적이 없다 — 실제 mixed-route provider는
> 서울시 data.go.kr `getPathInfoByBusNSub`(D-013/D-019/D-024), WALK provider는
> TMAP pedestrian(D-045)이다. Kakao Mobility 도보 API는 partner-only로 BLOCKED다(D-043).
> 아래 raw 파일명·SHA-256·후보 수치는 초판에서 실재하지 않는 Kakao 기준 raw를 가정해
> 만들어졌던 값이므로 전부 제거하고, 실제 decision log와 오늘 재확인한 값으로 대체했다.

## 1. 목표

Mixed-route API의 가용성을 다시 확인하는 것이 아니라(D-024에서 이미 GO) 다음 네 문제를 좁힌다.

1. 동일 OD에서 candidate 구조와 순서가 반복 가능한가(D-031이 야간→주간 재현을 이미 확인 — 오늘은 추가 window에서 검증).
2. mixed-route 응답의 `total - step sum`(있다면) 또는 route/leg 경계가 무엇을 포함하는가.
3. 응답에 이미 존재하는 `fid`/`tid`(정류장·역 코드)를 서울시 canonical identity에 얼마나 안정적으로 연결할 수 있는가 — Demo Corridor 4-node crosswalk는 D-047에서 이미 VERIFIED이므로, 오늘은 그 결과가 다른 topology/시간대에서도 유지되는지 확인한다.
4. Mixed-route candidate와 승인 Route A를 제품에서 어떻게 분리해야 하는가.

## 2. 기준 raw (실제 존재하는 evidence)

| 파일 | 내용 | 상태 |
|---|---|---|
| `docs/history/transit_journey_handoff_FINAL_v3/data/samples/seoul_bus/getPathInfoByBusNSub/2026-08-21/233739_ee60791ea53d.json` | Demo Corridor(삼청동↔역삼역) 최적 경로: 마을버스 소구간 + 3호선 안국→교대(railLinkList 12개) + 2호선 교대→역삼(railLinkList 2개), time=50분/distance=16542m | D-031에서 VERIFIED(주간 재현) |
| `docs/history/transit_journey_handoff_FINAL_v3/data/samples/seoul_bus/getPathInfoByBusNSub/2026-08-23/031632_d18df5a34b21.json` | 2026-08-23 오늘 재확인 호출(아래 3절), 유사 좌표(126.9818,37.5817→127.0365,37.5007) | 오늘 신규, `RECEIVED_HASH_VERIFIED` |

Kakao 관련 raw는 `docs/history/transit_journey_handoff_FINAL_v3/data/samples/examples/kakao_mobility/walking_directions/011033_blocked_partner_only.json` (HTTP 403 permission denied) 하나뿐이며, 이는 "BLOCKED" 사실 자체의 증거일 뿐 오늘 실험의 기준 raw가 아니다.

## 3. 2026-08-23 재확인 호출 결과 (이미 수행됨)

- Endpoint: `GET http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSub`
- Params: `startX=126.9818, startY=37.5817, endX=127.0365, endY=127.0365(오기 아님: destY=37.5007)`
- HTTP 200, `msgHeader.headerCd="0"`, `itemCount` 필드는 0이지만 `msgBody.itemList`에 실제 후보 다수 반환(헤더 필드 자체가 신뢰 불가 — item 개수는 배열 길이로 직접 세야 함, 새 DQ 발견)
- 후보 예시: `time=49, distance=15858` (3호선 안국→교대, 2호선 교대→역삼 조합), `time=51, distance=15706` (다른 접근 버스 조합)
- **DQ 발견(오늘 신규):** 응답 본문의 한글 필드(`routeNm`, `fname`, `tname` 등)가 `mixed_route_spike.py`의 인코딩 처리 문제로 mojibake로 저장됨. `routeId`, `fid`, `fx`, `fy`, `tid`, `tx`, `ty`, `time`, `distance` 등 숫자/ID 필드는 손상되지 않았다. 이 실험 세션에서는 collector를 수정하지 않고(금지 사항) 이 사실만 evidence로 남긴다 — 한글 지명이 필요한 판정(K5 crosswalk 등)은 ID/좌표만으로 수행한다.

## 4. Run manifest 필수 필드

각 호출은 다음을 저장한다.

- runId, purpose, scenarioId
- providerKey=`SEOUL_MIXED_ROUTE`(data.go.kr `getPathInfoByBusNSub`) 또는 `TMAP_PEDESTRIAN`
- endpoint, adapter/probe file hash
- exact request params와 coordinate role
- requestedAtUtc, receivedAtUtc, response Date, x-request-id(있는 경우)
- HTTP status, business status(`comMsgHeader`/`msgHeader`), business error
- sanitized response file path와 SHA-256
- data.go.kr 공용 키 used/remaining before·after (Bus Arrival/Position과 합산)
- secretIncluded=false 검사 결과

API key는 환경변수로만 사용하고 manifest·명령 history·raw에 기록하지 않는다.

## 5. Experiment K1 — Same-OD candidate stability

Demo Corridor OD(126.9809,37.5825→127.0362,37.5006, 또는 오늘 재확인에 쓴 근사 좌표)를 오전·낮·저녁 window에서 각각 두 번 호출한다. 같은 window의 두 요청은 정확히 같은 params를 사용한다.

각 candidate의 signature:

```text
candidateIndex
time, distance
ordered(pathList[].routeNm 또는 routeId — routeId가 있으면 그것을 우선)
ordered(pathList[].fid, pathList[].tid)
ordered(railLinkList가 있는지 여부와 개수)
first/last path 좌표(fx/fy, tx/ty)
```

판정:

| 결과 | 상태 |
|---|---|
| 같은 window의 signature·순서가 동일 | `BURST_STABLE_FOR_TESTED_OD` |
| 같은 window에서 순서 또는 topology가 다름 | `BURST_VARIABLE` |
| 다른 시간대에서만 변화 | `TIME_WINDOW_VARIATION_OBSERVED` |
| raw/params 불완전 | `INCONCLUSIVE` |

D-031이 이미 야간→주간 안정 재현을 확인했으므로, 오늘 결과가 이를 뒤집으면 그 자체가 중요한 신규 finding이다. 한 OD의 안정성을 서울 전체 mapping failure rate로 바꾸지 않는다.

## 6. Experiment K2 — Topology 다변화

기존 프로젝트가 이미 ID와 좌표를 가진 서울 지점을 사용하여 다음 topology를 선택한다. 각 scenario는 같은 request를 두 번 호출한다.

| Scenario | 목적 | 필수 확인 |
|---|---|---|
| subway-only | station×line 표현 | railLinkList 개수, fid/tid 유무 |
| bus-only | bus route/stop 표현 | routeId 유무(D-024는 bus-only 조합만 확인됨) |
| bus→subway / subway→bus | 경계 leg | alight→station WALK와 line identity |
| multi-transfer | 여러 leg 순서 | leg 수와 순서 의미 |
| short/edge OD | no route·walking-heavy 상태 | empty/business error taxonomy |

새로운 POI를 임의 선택하기보다 기존 Demo Corridor와 supporting evidence의 좌표를 우선한다. 각 결과는 scenario 범위로만 판정한다. **주의:** D-024에서는 서울역↔강남역 20개 대안이 전부 버스만의 조합이었다 — 실제 railLinkList가 채워진(지하철 구간 포함) 응답은 Demo Corridor(D-031)에서만 확인됐다. bus-only 결과가 나온다고 "지하철 구간 미지원"으로 단정하지 않는다.

## 7. Experiment K3 — Total/step gap decomposition (있는 경우)

이 API 응답에 `route.totalDistance`/`sum(step.distance)` 같은 명시적 total-vs-step 필드가 있는지부터 확인한다. 없다면(현재 확인된 필드는 `time`/`distance`만 최상위에 있고 leg별 합산 필드가 별도로 없을 수 있음) 이 실험은 `NOT_APPLICABLE`로 기록하고, 대신 leg 간 시간/거리 합이 top-level `time`/`distance`와 일치하는지만 확인한다.

```text
legSumDistance = sum(pathList[].거리 관련 필드가 있다면)
legSumTime = sum(pathList[].시간 관련 필드가 있다면)
gapDistance = distance - legSumDistance
gapTime = time - legSumTime
```

필드가 없어 계산 불가능하면 `INCONCLUSIVE`로 남기고 임의 tolerance를 발명하지 않는다.

## 8. Experiment K4 — TMAP WALK contract

다음 좌표쌍을 TMAP pedestrian으로 조회한다.

- Route A origin→춘추문 ACCESS
- 01A 안국 하차점→안국 station reference B2S street
- 역삼 station reference→멀티캠퍼스 FINAL
- Demo Corridor mixed-route 응답의 hidden access/final 후보 좌표(있다면)

확인:

- route total과 leg 합(TMAP GeoJSON turn-by-turn)
- geometry first/last와 request point 관계
- reverse request 결과
- empty/too-short/error semantics

각 값은 `DETERMINISTIC_POINT`다(TMAP 하나뿐이므로 provider 간 비교는 불가). 반복 결과가 같아도 개인 WALK distribution이 아니다.

## 9. Experiment K5 — Canonical crosswalk

### 9.1 Payload 사실 (2026-08-23 재확인)

기준 raw에서는:

- bus leg: `routeNm`(mojibake), `routeId`(예: `100900008`), `fname`/`tname`(mojibake), `fid`/`tid`(정류장 코드), `fx/fy/tx/ty`(좌표) — **provider ID가 이미 존재한다**(초판 문서의 "Kakao는 ID가 없다"는 서술은 이 API에 해당하지 않는다).
- subway leg: `routeNm`(호선명, mojibake), `routeId=null`, `fname/tname`(역명, mojibake), `fid/tid`(역 코드, 예: 서울시 station 코드 체계), `railLinkList`(구간 수).

### 9.2 Crosswalk 상태

Demo Corridor 4-node(안국/교대 3호선측/교대 2호선측/역삼)는 D-047에서 이미 `MAPPED`로 VERIFIED — `fid/tid`를 realtime subway API의 `statnId`와 좌표 소수점까지 대조 완료. 오늘 실험은 이 결과를 **다른 topology(K2에서 선택한 시나리오)** 로 확장했을 때도 유지되는지만 확인한다. 새로 확인하지 못한 topology는 `INCOMPLETE`로 남긴다.

### 9.3 Route A mismatch test

승인 Route A:

- 01A `춘추문(stId=100000417, staOrd=19)`
- → `안국역6번출구(stId=100000104, staOrd=21)`

mixed-route 응답이 이와 다른 정류장(예: 다른 staOrd)을 후보로 제시하면, 검증되더라도 두 route는 동일하지 않다. mixed-route 값을 승인 Route A의 19→21 BUS_RIDE에 재사용하지 않는다.

## 10. Mixed-Route Gate 출력

| Gate | 판정 | Evidence | 적용범위 | 남은 조치 |
|---|---|---|---|---|
| API access | GO (D-024) | `031632_d18df5a34b21.json`, D-024 원본 | endpoint | — |
| app limit | UNCONFIRMED | portal 미확인, Bus와 공유 키 | account(Bus+Mixed-route+Route/Station-master) | portal 캡처 |
| raw integrity | PARTIAL — 숫자/ID 필드 정상, 한글 필드 mojibake(DQ 발견) | 오늘 재확인 호출 | files/hash | collector encoding 버그는 별도 후속 작업으로 이관 |
| time semantics |  |  | candidate/OD |  |
| canonical mapping | Demo Corridor MAPPED(D-047), 그 외 topology 미확인 | ID_MAPPING.md | topology/corridor | K2 확장 결과로 갱신 |
| repeat stability | D-031 VERIFIED(야간→주간), 오늘 window 추가 확인 필요 |  | OD/windows |  |
| Primary eligibility |  |  | deployment |  |

Gate 하나라도 핵심적으로 미통과면 `ROUTE_A_ONLY`를 유지한다. Mixed-route 첫 candidate는 Route A Demo나 BUS_SKIPPED narrative를 대신하지 않는다.
