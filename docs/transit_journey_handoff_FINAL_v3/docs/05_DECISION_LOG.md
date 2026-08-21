# Decision Log

> 실제 Spike/PM 승인 결과를 시간순으로 기록한다. 기존 row를 조용히 덮어쓰지 않는다.

| Date | ID | Status | Decision / Question | Evidence | Impact | Owner |
|---|---|---|---|---|---|---|
| 2026-08-21 | D-001 | FIXED | 핵심 제품은 버스+지하철 전체 Journey의 도착확률/권장 출발시각/Reforecast Web App | PM Main Use Case | 모든 기능/데이터 우선순위의 기준 | PM |
| 2026-08-21 | D-002 | FIXED | 서울시 데이터만 사용 | PM 원칙 | TAGO는 최종 데이터에서 제외 | PM |
| 2026-08-21 | D-003 | FIXED | Web App | PM 원칙 | Responsive mobile UX 중요 | PM |
| 2026-08-21 | D-004 | VERIFIED | 서울 버스는 Prediction→Actual→Residual PoC가 성립 | `sources/project/01_bus_eta_reliability.pdf` | Bus reliability Phase 0 PASS | Data |
| 2026-08-21 | D-005 | HOLD | LightGBM을 core로 확정하지 않음 | 팀 문서 간 관점 차이 | empirical baseline과 비교 후 승격 | PM/Data |
| 2026-08-21 | D-006 | DROP_MVP | 미래 희귀 사고 발생확률 예측 | 장기 incident history 부족 | 현재 incident만 context | PM/Data |
| 2026-08-21 | D-007 | HOLD | 버스 혼잡 기반 탑승실패 probability | user-level Ground Truth 부족 | 실제 user event 기반 Reforecast 우선 | PM |
| 2026-08-21 | D-008 | TO_VERIFY | Subway Actual Ground Truth rule | 실제 dual API Spike 미완료 | Critical path | BE-Subway |
| 2026-08-21 | D-009 | TO_VERIFY | Mixed route API를 route provider로 사용 | 공식 서비스 존재, 실제 ID interoperability 미검증 | Critical path | Backend/PM |
| 2026-08-21 | D-010 | FIXED | API keys 취득 완료. 실제 secret은 repo/package에 저장하지 않음 | PM 보고 | Secret management 시작 가능 | Infra |
| 2026-08-21 | D-011 | VERIFIED | Bus Position 실제 endpoint는 `getBusPosByRouteSt` (busRouteId+startOrd+endOrd 필요), 팀 문서가 가정한 `getBusPosByRtid` 계열이 아님 | data.go.kr 15000332 공식 spec 페이지 | scripts/spikes/bus_position_spike.py를 실제 endpoint로 작성. checklist B의 `실제 endpoint 명` 항목 해소 | Data |
| 2026-08-21 | D-012 | TO_VERIFY | Subway realtime arrival/position의 `swopenAPI.seoul.go.kr` URL 패턴은 공개적으로 통용되는 관례이나 이 세션에서 실제 응답으로 검증하지 못함 (data.seoul.go.kr 카탈로그 페이지는 기술 스펙 비공개) | WebFetch 시도 실패 (HTTPS 강제 업그레이드로 연결 거부) | 실제 key로 첫 실행이 검증 단계. scripts/spikes/subway_*_spike.py는 HYPOTHESIS로 표시됨 | BE-Subway |
| 2026-08-21 | D-013 | VERIFIED | Bus Arrival(`getArrInfoByRouteAll`)·Position(`getBusPosByRouteSt`) 실제 키로 성공 호출. Route 753 기준 arrival 104 stop 항목, position 13대 실차량 확인. Arrival `vehId1`(111033105)이 Position `vehId` 집합에 direct match — 753 PoC의 vehId join 재현 성공 | `data/samples/seoul_bus/getArrInfoByRouteAll/2026-08-21/144628_*.json`, `.../getBusPosByRouteSt/2026-08-21/144750_*.json` | Spike A의 핵심 join 가설 1개 스냅샷으로 재현. 지속 수집으로 join rate% 확정 필요 | Data |
| 2026-08-21 | D-014 | VERIFIED | Position 응답 실제 필드: `busType,congetion(원문 오탈자),dataTm,isFullFlag,lastStnId,plainNo,posX,posY,routeId,sectDist,sectOrd,sectionId,stopFlag,tmX,tmY,vehId`. Checklist가 가정한 `nextStId`/`nextStTm`/`rtDist`는 응답에 없음 | `data/samples/seoul_bus/getBusPosByRouteSt/2026-08-21/144750_*.json` (raw item 직접 확인) | checklist B `nextStTm 실제 포함 여부` 항목 해소 → 미포함으로 확정. 혼잡도 필드명 오탈자(`congetion`) 그대로 파싱해야 함 | Data |
| 2026-08-21 | D-015 | VERIFIED | Arrival(`getArrInfoByRouteAll`)의 `mkTm`은 per-stop이 아니라 **호출 단위**로 전체 104개 item이 동일 값 공유 (단일 스냅샷에서 unique mkTm=1). Position `dataTm`은 vehicle별로 다름(수 초 단위 차이) | 같은 샘플 파일, item별 mkTm/dataTm 비교 | Bronze 계약의 `source_generated_at` 해석: bus arrival은 route-level 시각, position은 vehicle-level 시각으로 별도 처리 필요 | Data |
| 2026-08-21 | D-016 | VERIFIED | Subway realtime arrival(`realtimeStationArrival`)·position(`realtimePosition`) 둘 다 실제 키로 성공 (HTTP 200, `code=INFO-000`). D-012의 HYPOTHESIS를 대체 | `data/samples/seoul_subway/realtimeStationArrival/2026-08-21/144847_*.json`, `144945_*.json`, `.../realtimePosition/2026-08-21/144915_*.json` | Subway harness 전체가 실제 동작 확인됨. subway_*_spike.py 문서의 HYPOTHESIS 표기 제거 필요 | BE-Subway |
| 2026-08-21 | D-017 | VERIFIED | Arrival `btrainNo`와 Position `trainNo`가 같은 값(0224, 0823, 0825 등)으로 같은 역/방향에서 direct 매칭됨 (시청역, 1호선 기준) | 위 두 샘플 파일 cross-reference (수동 비교, 스크립트화는 TO_DO) | **가장 중요한 미해결 리스크였던 Subway Ground Truth join이 최초 스냅샷에서 성공.** 다만 1개 역·1개 시점 샘플이므로 열차번호 재사용/충돌, 시간대별 안정성은 아직 CONDITIONAL | BE-Subway |
| 2026-08-21 | D-018 | VERIFIED | Arrival `arvlCd` 관측값: `0`=진입, `1`=도착, `2`=출발, `99`=아직 도착 전(카운트다운/역 수 메시지). Checklist는 `arvlCd=1`만 언급했으나 실제로는 4단계 상태 전이 | 시청역 arrival 샘플 (`144945_*.json`) 10개 item 비교 | checklist F `Actual 후보`의 "전역출발→진입→도착→출발" 시퀀스가 `arvlCd` 값으로 직접 표현됨 확인 → subway actual rule 후보 1순위로 승격 가능(단, 지속 관측으로 안정성 확인 필요) | BE-Subway |
| 2026-08-21 | D-019 | BLOCKED | Mixed route(`getPathInfoByBusNSubList`, `getLocationInfoList`) 둘 다 401 `등록되지 않은 서비스키` | 동일 `DATA_GO_TRANSIT_PATH_KEY`로 두 operation 모두 재현 (코드/파라미터 문제 아님, 키 등록 문제로 판단) | Spike C 보류. **다음 행동: data.go.kr에서 서비스 15000414(대중교통환승경로 조회)에 대해 별도 활용신청/승인 필요** — 다른 서비스와 계정은 같아도 서비스별 승인이 분리되는 data.go.kr 특성 | PM/Infra |
| 2026-08-21 | D-020 | VERIFIED | Route 753, ~30s 폴링 약 10분 지속 수집(최종): position 257 관측 중 51건이 vehId별 `dataTm` 중복(~19.8%). `stopFlag` 0→1 전이 49건 관측, 대부분 폭 20~40초. vehId join rate 2026/2026 (100%) | `scripts/spikes/analyze_samples.py bus 100100118` 실행 결과, 원본 샘플 `data/samples/seoul_bus/**` | Spike A의 "raw→normalized→actual interval→residual 재현" 완료 기준 충족. 다만 야간 1개 노선 데이터라 일반화 금지 (CONDITIONAL 유지) | Data |
| 2026-08-21 | D-021 | VERIFIED | 시청역 지속 수집에서 `arvlCd` 실제 관측값이 D-018의 `{0,1,2,99}`보다 많은 `{0,1,2,3,4,5,99}`로 확인됨. 열차 0704/0825가 `99→5→3→1→2` 형태의 정연한 순서로 전이하는 것을 관측 | `scripts/spikes/analyze_samples.py subway 1001000132` 실행 결과 | D-018의 4단계 rule을 대체: 실제로는 최소 6~7단계 상태 코드 존재. `SUBWAY_ACTUAL_RULE_V0.md` 작성 시 이 전체 코드 집합 기준으로 설계해야 함 | BE-Subway |
| 2026-08-21 | D-022 | SUPERSEDED | (최초 판단) 시청역 지속 수집에서 trainNo join rate 6/8 (75%) — 원인 불명으로 기록했었음 | 같은 analyze_samples.py 실행 결과 | D-023에서 원인 규명 완료로 대체됨 | BE-Subway |
| 2026-08-22 | D-023 | VERIFIED | D-022의 join 실패 원인 규명: 코드 결함이 아니라 **우리 쿼리의 페이지네이션 한계**. `realtimePosition`을 `0/20` 고정 범위로 요청했으나 실제 1호선 응답의 `totalCount`는 46~53(변동) — 상위 20개만 받아서 나머지 재차가 누락됨. 미매칭 열차 5166/0226도 subwayId=1001(같은 노선) 확인, 다른 노선 열차가 아니었음. **수정 후 재검증: `0/100`으로 재호출하니 `selectedCount=totalCount=42`로 전량 수신 확인** | position 샘플 전수의 `totalCount` 값 집계(`{46,47,48,49,50,51,52,53}`), arrival 샘플에서 5166/0226의 subwayId 확인, 수정 후 샘플 `data/samples/seoul_subway/realtimePosition/2026-08-21/150158_*.json` | **subway_position_spike.py를 `0/100` 기본값 + `--end-ord` 옵션으로 수정, 수정 확인 완료.** 실제 collector는 응답의 `totalCount`를 읽어 범위를 동적으로 넓혀야 함 — 고정 페이지 크기로는 join rate가 인위적으로 낮게 나옴. Join rate 재측정(지속 수집)은 다음 세션 항목 | Data |

## Status meanings

- `FIXED`: PM/제품 원칙으로 고정
- `VERIFIED`: 실제 데이터/실험으로 확인
- `TO_VERIFY`: 핵심 Spike 필요
- `CONDITIONAL`: 조건 충족 시 채택
- `HOLD`: 아직 결정하지 않음
- `DROP_MVP`: MVP에서 제외
- `BLOCKED`: 외부 요인(승인/등록 등)으로 진행 불가, 코드 문제 아님
