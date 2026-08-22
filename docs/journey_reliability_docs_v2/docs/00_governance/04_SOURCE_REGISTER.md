---
doc_id: JR-DOC-004
title: Source Register
version: 1.1
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
| SRC-SEOUL-001 | 서울시 | OA-15799 / `realtimeStationArrival` | Subway arrival state/prediction input | CORE | VERIFIED live call | `SEOUL_SUBWAY_REALTIME_KEY` |
| SRC-SEOUL-002 | 서울시 | OA-12601 / `realtimePosition` | train position/join | CORE | VERIFIED live call | `SEOUL_SUBWAY_REALTIME_KEY` |
| SRC-SEOUL-003 | 서울특별시 / data.go.kr | 15000314 / `getArrInfoByRouteAll` | Bus prediction | CORE | VERIFIED live call | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-004 | 서울특별시 / data.go.kr | 15000332 / `getBusPosByRouteSt` | vehicle state / actual | CORE | VERIFIED live call | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-005 | 서울특별시 / data.go.kr | 15000414 / `getPathInfoByBusNSub` | Structural route candidates | CORE | VERIFIED live call | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-006 | 서울특별시 / data.go.kr | 15000193 노선정보 | route master | SUPPORT | VERIFIED resolver use | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-007 | 서울특별시 / data.go.kr | 15000303 정류소정보 | stop master / coordinate | SUPPORT | TO_VERIFY in canonical route mapping | `DATA_GO_BUS_API_KEY` |
| SRC-SEOUL-008 | 서울교통공사 | OA-22718 지하철 알림정보 | current incident context | SUPPORT | TO_VERIFY in product path | `SEOUL_OPEN_API_KEY` |
| SRC-SEOUL-009 | 서울교통공사 | OA-22521 서울 도시철도 환승정보 | from/to line, 빠른 하차/승차 위치, reference transfer time | SUPPORT | 공식 dataset 설명 확인; 교대 3→2 row TO_VERIFY | file/open data |
| SRC-SEOUL-010 | 서울교통공사 | OA-13290 환승역거리 소요시간 | transfer distance/reference time | SUPPORT | 공식 dataset 설명 확인; 교대 row TO_VERIFY | file/open data |
| SRC-SEOUL-011 | 서울교통공사 | OA-22522 서울 도시철도 열차운행시각표 | future SUBWAY_WAIT/service availability 후보 | SUPPORT | 공식 dataset 설명/1~9호선 범위 확인; 실제 ingest/ID join TO_VERIFY | file/open data |
| SRC-SEOUL-012 | 서울시 | OA-21217 노선별 정류장 구간 평균 운행시간 | historical baseline candidate | DROP | intended-use FAILED/DROPPED | — |
| SRC-TMAP-001 | SK Open API | TMAP pedestrian route | ACCESS / street transfer / FINAL WALK point route | EXTERNAL_UTILITY | VERIFIED live call on one generic pair | `TMAP_APP_KEY` |
| SRC-KAKAO-001 | Kakao Mobility | walking directions | WALK candidate | BLOCKED | real 403 | `KAKAO_MAP_REST_API_KEY` |

## 3. Official pages

- OA-15799: `https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do`
- OA-12601: `https://data.seoul.go.kr/dataList/OA-12601/A/1/datasetView.do`
- 버스도착 15000314: `https://www.data.go.kr/data/15000314/openapi.do`
- 버스위치 15000332: `https://www.data.go.kr/data/15000332/openapi.do`
- 환승경로 15000414: `https://www.data.go.kr/data/15000414/openapi.do`
- OA-22521: `https://data.seoul.go.kr/dataList/OA-22521/L/1/datasetView.do`
- OA-13290: `https://data.seoul.go.kr/dataList/OA-13290/F/1/datasetView.do`
- OA-22522: `https://data.seoul.go.kr/dataList/OA-22522/F/1/datasetView.do`
- TMAP: `https://openapi.sk.com/`

## 4. 의미 제한

- TMAP `totalTime`은 보행 소요시간 **point estimate**이며 분포가 아니다.
- OA-22521은 공식 설명상 환승 시작/종료호선, 빠른 하차/승차 위치, 소요시간을 제공하지만 개인 걸음속도 차이가 있으므로 reference다.
- OA-13290은 공식 설명상 환승거리와 보행속도 1.2m/s 기준 소요시간 reference를 제공한다.
- OA-22522는 공식 설명상 1~9호선, 역코드/방향/도착·출발시간 등을 제공하지만 실제 Demo ID crosswalk와 schedule freshness는 별도 검증한다.
- Bus `congetion`은 personal boarding-failure probability가 아니다.
