---
doc_id: JR-DOC-004
title: Source Register
version: 1.2
status: REVIEW
owner: PM/Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-002
  - JR-DOC-003
source_of_truth_for:
  - source-policy
  - external-data-registry
supersedes: []
---

# Source Register

## 1. Source Policy

Transit Reliability Core는 `PD-003`을 따른다.

- 기본: 서울시/서울교통공사 제공 + 서울 행정구역
- 외부 utility 예외: WALK/geocoding 등 Transit Reliability 자체가 아닌 보조 기능
- 외부 utility 결과를 버스/지하철 reliability Ground Truth/label로 사용하지 않음

## 2. Registry

| ID | Provider | Source/API | Role | Policy class | Product-use status | Credential |
|---|---|---|---|---|---|---|
| SRC-SEOUL-001 | 서울시 | OA-15799 / `realtimeStationArrival` | Subway arrival state/prediction input | CORE | VERIFIED live call; Phase 1 quota-limited sustained use 확인 | `SEOUL_SUBWAY_REALTIME_KEY` |
| SRC-SEOUL-002 | 서울시 | OA-12601 / `realtimePosition` | train position/join | CORE | VERIFIED live call; Route A 4 node join 재확인 | `SEOUL_SUBWAY_REALTIME_KEY` |
| SRC-SEOUL-003 | 서울특별시 / data.go.kr | 15000314 / `getArrInfoByRouteAll` | Bus prediction + current wait candidate | CORE | VERIFIED live call; 01A/147 1h collection | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-004 | 서울특별시 / data.go.kr | 15000332 / `getBusPosByRouteSt` | vehicle state / actual | CORE | VERIFIED live call; 01A/147 1h collection | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-005 | 서울특별시 / data.go.kr | 15000414 / `getPathInfoByBusNSub` | Structural route candidates | CORE | VERIFIED; Route A/B structural paths | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-006 | 서울특별시 / data.go.kr | 15000193 노선정보 | route master | SUPPORT | VERIFIED resolver use | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-007 | 서울특별시 / data.go.kr | 15000303 정류소정보 | stop master / coordinate | SUPPORT | TO_VERIFY in broader canonical route mapping | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-008 | 서울교통공사 | OA-22718 지하철 알림정보 | current incident context | SUPPORT | TO_VERIFY in product path | `SEOUL_OPEN_API_KEY` |
| SRC-SEOUL-009 | 서울교통공사 | OA-22521 서울 도시철도 환승정보 | from/to line, 빠른 하차/승차 위치, transfer reference | SUPPORT | **교대 3→2 row VERIFIED; PD-031 Tier-0 reference 144 s** | file/open data |
| SRC-SEOUL-010 | 서울교통공사 | OA-13290 환승역거리 소요시간 | transfer distance/1.2m/s reference | SUPPORT | **교대 3→2 75 m / 63 s VERIFIED; sanity reference only** | file/open data |
| SRC-SEOUL-011 | 서울교통공사 | OA-22522 서울 도시철도 열차운행시각표 | future SUBWAY_WAIT/service availability 후보 | SUPPORT | **CONDITIONAL** — 532,832 rows ingest/Route A mapping 가능; file date 2025-09-30 current validity 미검증 | file/open data |
| SRC-SEOUL-012 | 서울시 | OA-21217 노선별 정류장 구간 평균 운행시간 | historical baseline candidate | DROP | intended-use FAILED/DROPPED | — |
| SRC-TMAP-001 | SK Open API | TMAP pedestrian route + geocode | ACCESS / street transfer / FINAL WALK point route | EXTERNAL_UTILITY | VERIFIED on demo ACCESS, BUS→SUBWAY street, FINAL WALK point pairs | `TMAP_APP_KEY` |
| SRC-KAKAO-001 | Kakao Mobility | walking directions | WALK candidate | BLOCKED | real 403 | `KAKAO_MAP_REST_API_KEY` |

## 3. Official pages / acquired files

- OA-15799: `https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do`
- OA-12601: `https://data.seoul.go.kr/dataList/OA-12601/A/1/datasetView.do`
- 버스도착 15000314: `https://www.data.go.kr/data/15000314/openapi.do`
- 버스위치 15000332: `https://www.data.go.kr/data/15000332/openapi.do`
- 환승경로 15000414: `https://www.data.go.kr/data/15000414/openapi.do`
- OA-22521: `https://data.seoul.go.kr/dataList/OA-22521/F/1/datasetView.do`
- OA-13290: `https://data.seoul.go.kr/dataList/OA-13290/F/1/datasetView.do`
- OA-22522: `https://data.seoul.go.kr/dataList/OA-22522/F/1/datasetView.do`
- TMAP: `https://openapi.sk.com/`

Phase 1 acquired raw:
- OA-22521 file dated 2025-03-17, CP949
- OA-13290 file dated 2025-03-31, CP949
- OA-22522 file named/dataset snapshot 2025-09-30, UTF-8-BOM

## 4. 의미 제한

- TMAP `totalTime`은 보행 소요시간 **point estimate**이며 분포가 아니다.
- OA-22521 144 s는 door/direction-specific reference이지만 개인 walking distribution이 아니다.
- OA-13290 63 s는 75 m와 1.2m/s reference에서 나온 station-level 값으로, OA-22521과 평균하지 않는다.
- OA-22522는 parsing/headway feasibility는 확인됐지만 현재 schedule validity가 확인되기 전 user-facing future WAIT authoritative source가 아니다.
- OA-22522 `SI_ID`↔realtime `statnId`를 단순 산술 변환하지 않는다.
- OA-22522는 line에 따라 direction vocabulary가 `UP/DOWN` 또는 `IN/OUT`으로 다르며 `>=24:00:00` rollover row가 존재한다.
- Bus `congetion`은 personal boarding-failure probability가 아니다.
- Realtime subway development quota는 Phase 1에서 `ERROR-337`로 실제 소진되었으므로 shared budget을 운영해야 한다.
