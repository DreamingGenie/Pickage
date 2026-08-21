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

## Status meanings

- `FIXED`: PM/제품 원칙으로 고정
- `VERIFIED`: 실제 데이터/실험으로 확인
- `TO_VERIFY`: 핵심 Spike 필요
- `CONDITIONAL`: 조건 충족 시 채택
- `HOLD`: 아직 결정하지 않음
- `DROP_MVP`: MVP에서 제외
