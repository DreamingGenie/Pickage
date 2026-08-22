---
doc_id: JR-DOC-003
title: Evidence Register
version: 1.2
status: LOCKED
owner: Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
  - JR-DOC-002
source_of_truth_for:
  - verified-claims
  - phase0-evidence
  - phase1-evidence
supersedes:
  - mixed evidence rows in legacy 05_DECISION_LOG.md
---

# Evidence Register

## 1. Artifact path convention

artifact path는 별도 표시가 없으면 **이 패키지 root 기준**이다.

- `baseline/phase0/`: Phase 0 historical archive
- `evidence/phase1/`: 2026-08-22 Phase 1 live API / official-file evidence

`VERIFIED`는 claim과 scope가 같이 VERIFIED라는 뜻이다. corridor-scoped 검증을 citywide로 확대하지 않는다.

## 2. Evidence

| ID | Status | Claim | Scope / support | Artifact | Limitation |
|---|---|---|---|---|---|
| EVD-BUS-001 | VERIFIED | `getArrInfoByRouteAll` 실제 호출 성공 | route 753 smoke | `baseline/phase0/data/samples/examples/seoul_bus/getArrInfoByRouteAll/144628_23c91c338f4c.json` | 한 노선 smoke |
| EVD-BUS-002 | VERIFIED | `getBusPosByRouteSt` 실제 호출 성공 | route 753 | `baseline/phase0/data/samples/examples/seoul_bus/getBusPosByRouteSt/144750_cc447827df6f.json` | endpoint semantics는 현재 서울 버스 API 기준 |
| EVD-BUS-003 | VERIFIED | Arrival `vehId1/2` ↔ Position `vehId` direct join 가능 | 753 + 01A/147 corridor evidence | Phase 0 raw + `evidence/phase1/EVD-CROSS-002/` | 서울 전체 join SLA 아님 |
| EVD-BUS-004 | VERIFIED | Position 실제 response에는 `vehId, routeId, sectOrd, sectionId, sectDist, stopFlag, dataTm, congetion, isFullFlag, plainNo...`; 초기 가정의 `nextStId/nextStTm/rtDist` 없음 | live raw | `baseline/phase0/data/samples/examples/seoul_bus/getBusPosByRouteSt/144750_cc447827df6f.json` | provider schema 변경 모니터 필요 |
| EVD-BUS-005 | VERIFIED | Bus Arrival `mkTm`은 response-level 공통시각, Position `dataTm`은 vehicle-level source time | Phase 0 response profiling | EVD-BUS-001/002 raw | API별 timestamp semantics 별도 처리 |
| EVD-BUS-006 | VERIFIED | `congetion`은 실제 주간 응답에서 0 이외 값 관측 | route 753 + Phase 1 01A/147 | `baseline/phase0/docs/05_DECISION_LOG.md` + `evidence/phase1/BUS_01A_EXTENDED/derived/metrics_raw.json` | 개인 승차 실패 GT 아님 |
| EVD-BUS-007 | VERIFIED | mixed-route Route A의 `01A routeId=100100001`과 realtime `busRouteId` direct join | Demo OD | `baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json` | 다른 bus route/stop ID까지 자동 보장하지 않음 |
| EVD-BUS-008 | CONDITIONAL | Phase 0 01A run에서 `stopFlag 0→1` transition 54건, vehId join 2174/2174가 기록됨 | 약 15분, route-level multi-stop observations | `baseline/phase0/docs/05_DECISION_LOG.md` D-048 | **특정 춘추문→안국 leg의 54 residual이라는 뜻이 아님** |
| EVD-BUS-009 | VERIFIED | data.go route resolver가 `DATA_GO_BUS_API_KEY`로 정상 동작 | route 753 resolver | `baseline/phase0/scripts/spikes/resolve_bus_route.py` | station-master까지 동일 수준 검증은 아님 |
| EVD-BUS-010 | CONDITIONAL | 01A 춘추문(staOrd19)→안국(staOrd21) target range에서 실제 traverse-time 11건 확보: min 100 s, median 약 682 s, max 1,223 s | Phase 1 약 1시간, target-leg-specific first support | `evidence/phase1/BUS_01A_EXTENDED/README.md`, `evidence/phase1/BUS_01A_EXTENDED/derived/metrics_raw.json` | traverse-time sample이지 Prediction→Actual residual이 아님; single window, 12x spread |
| EVD-SUB-001 | VERIFIED | `realtimeStationArrival` / `realtimePosition` 실제 호출 성공 | 서울 실시간 지하철 sample | `baseline/phase0/data/samples/examples/seoul_subway/` | quota/coverage는 운영 별도 관리 |
| EVD-SUB-002 | VERIFIED | `arvlCd`의 `{0,1,2,3,4,5,99}`가 일부 1·2·3호선 실제 표본에서 관측됨 | non-citywide sample | Phase 0 + `evidence/phase1/SUBWAY_SUSTAINED/derived/metrics_raw.json` | citywide 모든 상태전이를 보장하지 않음 |
| EVD-SUB-003 | VERIFIED | Arrival `btrainNo` ↔ Position `trainNo` join이 Route A **station×line 4개**에서 100% 재확인됨 | 안국3 16/16, 교대3 12/12, 교대2 12/12, 역삼2 11/11 | `evidence/phase1/SUBWAY_SUSTAINED/derived/metrics_raw.json` | corridor-scoped; station name만 합치면 오류 발생 가능 |
| EVD-SUB-004 | VERIFIED | 특정 2호선 `statnId=1002000201`에서 6/11(54.5%) join gap 재현 기록 | 특정 station code | Phase 0 Decision D-026/D-033/D-036 | root cause 미해결; Route A 4 node 결과와 별개 |
| EVD-SUB-005 | CONDITIONAL | Route A sustained window에서 실제 `arvlCd=1`과 ActualArrivalInterval 생성: 안국 53 sightings/11 intervals, 교대 name-search combined 40/6, 역삼 0/0 | usable real-data window 약 22~33분, quota-limited | `evidence/phase1/SUBWAY_SUSTAINED/README.md`, `evidence/phase1/SUBWAY_SUSTAINED/derived/metrics_raw.json` | 교대 Actual metrics는 현재 derived artifact에서 line별 분리 안 됨; 역삼 0; mature residual distribution 아님 |
| EVD-ROUTE-001 | VERIFIED | mixed bus+subway endpoint `getPathInfoByBusNSub` 실제 성공 | live call | `baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json` | catalog 명칭/URL 오타 주의 |
| EVD-ROUTE-002 | VERIFIED | 동일 OD에서 실제 mixed-mode 대안 여러 개 반환 | 삼청동 coordinate→역삼 coordinate | EVD-ROUTE-001 raw | provider rank가 reliability ranking은 아님 |
| EVD-ROUTE-003 | CONDITIONAL | provider top Route A가 두 시점에 `01A→3호선→2호선`, time=50, distance=16542로 재현됨 | Demo OD 2시점 | Phase 0 raw/Decision | 장기 route stability 아님; `time=50`은 provider metadata |
| EVD-CROSS-001 | VERIFIED | Phase 0 동일 OD 대안에 `SUBWAY→BUS` 구조 존재: `01A → 3호선(안국→압구정) → 147` | provider alternative | `baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json` | 구조적 경로 존재 claim |
| EVD-CROSS-002 | VERIFIED | Route B의 압구정 3호선 node, 147 route/stop IDs가 realtime feeds와 실제 연결되고, 147 1시간 수집으로 BUS_WAIT source/vehicle turnover feasibility 확인 | Route B corridor-scoped; 압구정 realtime `statnId=1003000336`, 147 target stops exact ID join | `evidence/phase1/EVD-CROSS-002/README.md`, `evidence/phase1/EVD-WAIT-001/README.md` | **Reforecast product code가 구현됐다는 뜻이 아님**; transfer internal/street duration도 별도 모델 필요 |
| EVD-ID-001 | CONDITIONAL | mixed-route subway code와 realtime `statnId`는 다른 ID 공간 | Route A nodes | `baseline/phase0/docs/data-contract/ID_MAPPING.md` | citywide resolver 없음 |
| EVD-ID-002 | VERIFIED | Route A 4개 line-specific subway node crosswalk live 재확인 | 안국3/교대3/교대2/역삼2 | `evidence/phase1/SUBWAY_SUSTAINED/README.md` | arithmetic mapping rule로 일반화 금지 |
| EVD-WALK-001 | FAILED | Kakao Mobility walking API는 일반 REST key로 403 permission denied | 실제 key call | `baseline/phase0/data/samples/examples/kakao_mobility/walking_directions/011033_blocked_partner_only.json` | 별도 제휴 승인 시 재검증 가능 |
| EVD-WALK-002 | VERIFIED | TMAP pedestrian API 실제 HTTP 200, GeoJSON/`totalDistance`/`totalTime` 수신 | generic Phase 0 + demo-specific Phase 1 calls | `baseline/phase0/data/samples/examples/tmap/routes_pedestrian/012739_success_after_subscribe.json` | point estimate only |
| EVD-WALK-003 | VERIFIED | TMAP appKey + 상품 구독 후 동일 key가 200 성공 | 403→200 | `baseline/phase0/data/samples/examples/tmap/routes_pedestrian/` | 온보딩 함정 |
| EVD-HIST-001 | FAILED | OA-21217은 의도한 pollable historical baseline으로 사용하기 부적절해 MVP에서 DROP | dataset 조사 | `baseline/phase0/docs/05_DECISION_LOG.md` | historical baseline 후보 제거 |
| EVD-TRANSFER-001 | VERIFIED | 교대 3→2 공식 row가 OA-22521과 OA-13290 모두 존재: OA-22521 4개 door/direction row **144 s**, OA-13290 75 m / **63 s** | 2025-03 official CSVs | `evidence/phase1/EVD-TRANSFER-001/README.md`, `evidence/phase1/EVD-TRANSFER-001/raw/OA-22521_#Uc218#Ub3c4#Uad8c#Ub3c4#Uc2dc#Ucca0#Ub3c4#Ud658#Uc2b9#Ub370#Uc774#Ud130_20250317.csv` | 두 source semantics가 달라 숫자 충돌; canonical choice는 PD-031 |
| EVD-ACCESS-001 | VERIFIED | Demo origin→춘추문 ACCESS_WALK TMAP point route: **297 m / 245 s** | 1 live call | `evidence/phase1/EVD-ACCESS-001/README.md` | point estimate; time/weather variance 미모델링 |
| EVD-XFER-B2S-001 | CONDITIONAL | 01A 안국 하차 bus stop→안국 mixed subway node street route: **143 m / 101 s** | 1 live TMAP call | `evidence/phase1/EVD-XFER-B2S-001/README.md` | endpoint는 `STATION_CENTER` candidate; entrance→platform internal time 미측정 `UNMODELED_UNCERTAINTY` |
| EVD-DEST-001 | VERIFIED | 역삼 mixed-route `STATION_CENTER` candidate→멀티캠퍼스 POI entrance point route: **329 m / 300 s** | geocode 1 + pedestrian route 1 live call | `evidence/phase1/EVD-DEST-001/README.md` | actual station exit 기반이 아님; PD-035 |
| EVD-SCHED-001 | CONDITIONAL | OA-22522 532,832-row timetable ingest 성공; Route A station codes/weektag/direction/24h rollover 확인, schedule headway 계산 가능 | downloaded file dated 2025-09-30; Route A mapping live cross-check | `evidence/phase1/EVD-SCHED-001/README.md` | 약 11개월 current-validity gap; user-facing future WAIT truth로 미승격 |
| EVD-WAIT-001 | VERIFIED | 01A/147 realtime Arrival을 1시간 수집해 future BUS_WAIT/headway **source feasibility**와 distinct vehicle turnover를 확인 | stop당 `exps1` 181 snapshots; 147 7~8, 01A 7~9 vehId1 transitions | `evidence/phase1/EVD-WAIT-001/README.md`, `evidence/phase1/EVD-WAIT-001/derived/metrics_raw.json` | 181 snapshots는 iid headway sample이 아님; single time window; mature distribution 아님 |
| EVD-VOLUME-001 | CONDITIONAL | Phase 1 session 1,930 raw samples / 61.8 MB over 약 70분, 약 53 MB/h observed workload; bus Arrival payload가 raw bytes 대부분 차지 | 6 source/API types, evidence-session cadence | `evidence/phase1/VOLUME_LATENESS/README.md`, `evidence/phase1/VOLUME_LATENESS/derived/volume_lateness_summary.json` | true `received_at-source_generated_at` / network latency는 baseline harness timestamp 결함으로 NOT_AVAILABLE; production load가 아님 |
| EVD-OPS-001 | VERIFIED | 동일 `SEOUL_SUBWAY_REALTIME_KEY`를 5 poller가 15 s cadence로 공유하면 documented dev quota 1,000/day를 실제 `ERROR-337`로 소진함 | usable station window 약 22~33분 | `evidence/phase1/SUBWAY_SUSTAINED/README.md` | quota 자체의 공식 정책 변경 가능; 운영 cadence/증액 별도 설계 필요 |

## 3. Evidence 사용 규칙

- `CONDITIONAL` Evidence를 citywide 문장에 사용하지 않는다.
- `TO_VERIFY`를 사실 문장으로 바꾸지 않는다.
- `VERIFIED feasibility`를 `IMPLEMENTED/TESTED product`로 해석하지 않는다.
- `EVD-CROSS-002`는 source interoperability evidence이고 `BUS_SKIPPED` Reforecast 구현 증거가 아니다.
- Bus WAIT의 반복 polling snapshot 수를 독립 sample size로 그대로 사용하지 않는다(`PD-034`).
- Subway multi-line station은 반드시 `subwayId × statnId`로 분리한다(`PD-039`).
- Phase 1 report와 per-item README가 해석이 충돌하면 machine-readable derived artifact와 raw를 다시 확인하고 Decision/Evidence 변경을 기록한다.
