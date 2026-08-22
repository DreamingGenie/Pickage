---
doc_id: JR-DOC-003
title: Evidence Register
version: 1.1
status: LOCKED
owner: Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
  - JR-DOC-002
source_of_truth_for:
  - verified-claims
  - phase0-evidence
supersedes:
  - mixed evidence rows in legacy 05_DECISION_LOG.md
---

# Evidence Register

## 1. Artifact path convention

이 문서의 artifact path는 별도 표시가 없으면 **이 패키지 root 기준**이다.
`baseline/phase0/`는 사용자가 제공한 `result.zip`의 Phase 0 산출물 중 핵심 재현자료를 그대로 보관한 archive다.

`VERIFIED`/`CONDITIONAL`이라도 raw가 패키지에 포함되지 않고 Decision Log 요약만 남은 경우 `SUMMARY_ONLY`라고 명시한다.
Phase 1에서는 가능한 한 재수집해 raw artifact를 새로 남긴다.

## 2. Evidence

| ID | Status | Claim | Scope / support | Artifact | Limitation |
|---|---|---|---|---|---|
| EVD-BUS-001 | VERIFIED | `getArrInfoByRouteAll` 실제 호출 성공 | route 753 smoke | `baseline/phase0/data/samples/examples/seoul_bus/getArrInfoByRouteAll/144628_23c91c338f4c.json` | 한 노선 smoke |
| EVD-BUS-002 | VERIFIED | `getBusPosByRouteSt` 실제 호출 성공 | route 753 | `baseline/phase0/data/samples/examples/seoul_bus/getBusPosByRouteSt/144750_cc447827df6f.json` | endpoint semantics는 현재 서울 버스 API 기준 |
| EVD-BUS-003 | VERIFIED | Arrival `vehId1/2` ↔ Position `vehId` direct join 가능 | 753 + Phase 0 extended 01A summary | 위 raw + `baseline/phase0/docs/05_DECISION_LOG.md` D-035/D-048 | 서울 전체 join SLA 아님 |
| EVD-BUS-004 | VERIFIED | Position 실제 response에는 `vehId, routeId, sectOrd, sectionId, sectDist, stopFlag, dataTm, congetion, isFullFlag, plainNo...`; 초기 가정의 `nextStId/nextStTm/rtDist` 없음 | live raw | `baseline/phase0/data/samples/examples/seoul_bus/getBusPosByRouteSt/144750_cc447827df6f.json` | provider schema 변경 모니터 필요 |
| EVD-BUS-005 | VERIFIED | Bus Arrival `mkTm`은 response-level 공통시각, Position `dataTm`은 vehicle-level source time | 104 arrival items + position snapshot | EVD-BUS-001/002 raw | API별 timestamp semantics 별도 처리 |
| EVD-BUS-006 | VERIFIED | `congetion`은 실제 주간 응답에서 0 이외 값 관측 | route 753 daytime summary | `baseline/phase0/docs/05_DECISION_LOG.md` D-035 | 개인 승차 실패 GT 아님 |
| EVD-BUS-007 | VERIFIED | mixed-route Route A의 `01A routeId=100100001`과 realtime `busRouteId` direct join | Demo OD | `baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json` + Decision D-038 | 다른 bus route/stop ID까지 자동 보장하지 않음 |
| EVD-BUS-008 | CONDITIONAL | 01A extended run에서 `stopFlag 0→1` transition 54건, vehId join 2174/2174가 기록됨 | 약 15분, 20초 poll, route-level multi-stop observations | `baseline/phase0/docs/05_DECISION_LOG.md` D-048 (`SUMMARY_ONLY`: long-run raw 미포함) | **특정 춘추문→안국 leg의 54 residual이라는 뜻이 아님**; multi-window/target-leg residual 재수집 필요 |
| EVD-BUS-009 | VERIFIED | data.go route resolver가 `DATA_GO_BUS_API_KEY`로 정상 동작 | route 753 resolver | `baseline/phase0/scripts/spikes/resolve_bus_route.py` + Decision D-046 | station-master까지 동일 수준으로 검증됐다는 뜻 아님 |
| EVD-SUB-001 | VERIFIED | `realtimeStationArrival` / `realtimePosition` 실제 호출 성공 | 서울 실시간 지하철 sample | `baseline/phase0/data/samples/examples/seoul_subway/` | quota/coverage는 운영 별도 관리 |
| EVD-SUB-002 | VERIFIED | `arvlCd`의 `{0,1,2,3,4,5,99}`와 progression이 일부 1·2·3호선 표본에서 관측됨 | non-citywide sample | `baseline/phase0/docs/05_DECISION_LOG.md` D-021/D-034 | citywide 모든 상태전이를 보장하지 않음 |
| EVD-SUB-003 | CONDITIONAL | Arrival `btrainNo` ↔ Position `trainNo` join은 Demo Route A 4 node sustained summary에서 100% | 안국3/교대3/교대2/역삼2 | `baseline/phase0/docs/05_DECISION_LOG.md` D-048 (`SUMMARY_ONLY`) | 다른 station/platform 일반화 금지 |
| EVD-SUB-004 | VERIFIED | 특정 2호선 `statnId=1002000201`에서 6/11(54.5%) join gap 재현 기록 | 특정 station code | baseline subway example + Decision D-026/D-033/D-036 | root cause 미해결 |
| EVD-SUB-005 | CONDITIONAL | Demo 15분 sustained summary에서 join은 100%였으나 `arvlCd=1` completed actual은 0건 | 4 stations, 60 polls summary | `baseline/phase0/docs/05_DECISION_LOG.md` D-048 | subway residual distribution 준비 안 됨 |
| EVD-ROUTE-001 | VERIFIED | mixed bus+subway endpoint `getPathInfoByBusNSub` 실제 성공 | live call | `baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json` | catalog 명칭/URL 오타 주의 |
| EVD-ROUTE-002 | VERIFIED | 동일 OD에서 실제 mixed-mode 대안 여러 개 반환 | 삼청동 coordinate→역삼 coordinate | EVD-ROUTE-001 raw | provider rank가 reliability ranking은 아님 |
| EVD-ROUTE-003 | CONDITIONAL | provider top Route A가 두 시점에 `01A→3호선→2호선`, time=50, distance=16542로 재현됨 | Demo OD 2시점 | `baseline/phase0/docs/05_DECISION_LOG.md` D-030/D-031 + raw | 장기 route stability 아님; `time=50`은 provider value이지 Reliability GT 아님 |
| EVD-CROSS-001 | VERIFIED | **Phase 0 실제 mixed-route Raw의 동일 OD 대안에 `SUBWAY→BUS` 구조가 존재**: `01A → 3호선(안국→압구정) → 147(압구정역4번출구→역삼역6번출구)` | provider alternative, time=52/distance=13048 | `baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json` | 구조적 경로 존재만 VERIFIED; realtime ID/Wait/Actual 연결은 별도 |
| EVD-CROSS-002 | TO_VERIFY | Route B의 압구정 3호선→147 bus transfer를 realtime station/route/stop/Wait와 E2E 연결 | Cross-mode Route B | Phase 1 output 예정 | product `SUBWAY_TO_BUS` 계산 가능성의 실제 Gate |
| EVD-ID-001 | CONDITIONAL | mixed-route subway code와 realtime `statnId`는 다른 ID 공간 | Route A 4 nodes | `baseline/phase0/docs/data-contract/ID_MAPPING.md` | citywide resolver 없음 |
| EVD-ID-002 | VERIFIED | Route A 4개 line-specific subway node 수작업 crosswalk 완성 | 안국3/교대3/교대2/역삼2 | `baseline/phase0/docs/data-contract/ID_MAPPING.md` | corridor-specific |
| EVD-WALK-001 | FAILED | Kakao Mobility walking API는 일반 REST key로 403 permission denied | 실제 key call | `baseline/phase0/data/samples/examples/kakao_mobility/walking_directions/011033_blocked_partner_only.json` | 별도 제휴 승인 시 재검증 가능 |
| EVD-WALK-002 | VERIFIED | TMAP pedestrian API 실제 HTTP 200, GeoJSON/`totalDistance`/`totalTime` 수신 | 교대→역삼 generic real call | `baseline/phase0/data/samples/examples/tmap/routes_pedestrian/012739_success_after_subscribe.json` | **Demo ACCESS/FINAL/TRANSFER pair 자체가 검증된 것은 아님**; point estimate only |
| EVD-WALK-003 | VERIFIED | TMAP appKey 발급만으로는 부족했고 해당 상품 구독 후 동일 key가 200 성공한 기록 | 403→200 | `baseline/phase0/data/samples/examples/tmap/routes_pedestrian/` | 온보딩 함정 |
| EVD-HIST-001 | FAILED | OA-21217은 의도한 pollable historical baseline으로 사용하기 부적절해 MVP에서 DROP | dataset 조사 | `baseline/phase0/docs/05_DECISION_LOG.md` D-025/D-028 | historical baseline 후보 제거 |
| EVD-TRANSFER-001 | TO_VERIFY | 교대 3→2 official static transfer row와 실제 column/값 | Route A | OA-22521/OA-13290 | row-level 미검증 |
| EVD-ACCESS-001 | TO_VERIFY | Demo origin coordinate→춘추문(100000417) ACCESS_WALK point route/time | Route A | Phase 1 output 예정 | Phase 0 TMAP success는 다른 pair |
| EVD-XFER-B2S-001 | TO_VERIFY | 01A 하차정류장(100000104)→안국 3호선 boarding point의 BUS_TO_SUBWAY transfer time decomposition | Route A | Phase 1 output 예정 | street walk와 station internal access를 분리해야 함 |
| EVD-DEST-001 | TO_VERIFY | 역삼 2호선 endpoint→멀티캠퍼스 역삼 FINAL_WALK point route/time | Route A | Phase 1 output 예정 | start coordinate가 station center/exit 중 무엇인지 기록 필요 |
| EVD-SCHED-001 | TO_VERIFY | OA-22522 timetable을 안국/교대/역삼의 future SUBWAY_WAIT/service availability에 사용할 수 있는지, station code crosswalk 포함 | Route A | official dataset + Phase 1 ingest 예정 | catalog 존재 ≠ 현재 ID interoperability 검증 |
| EVD-WAIT-001 | TO_VERIFY | 01A/Route B bus의 future PRE_TRIP wait를 time-conditioned empirical headway/wait로 구성 가능한지 | selected routes | Phase 1 extended collection 예정 | exact future vehicle ID를 요구하지 않음 |

## 3. Evidence 사용 규칙

- `CONDITIONAL` Evidence를 citywide 문장에 사용하지 않는다.
- `TO_VERIFY`를 사실 문장으로 바꾸지 않는다.
- `SUMMARY_ONLY` evidence는 Phase 1에서 가능한 한 raw 재수집한다.
- 경로 구조 존재(`EVD-CROSS-001`)와 Reliability E2E 가능(`EVD-CROSS-002`)을 섞지 않는다.
