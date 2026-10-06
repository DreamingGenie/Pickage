# 0826 260824 v0.2 Planning Set Archive

이 폴더는 2026-08-26 `docs/` root에 260825 v0.3 기획 문서 세트가 도착하면서 대체된 260824 v0.2 정본 세트를 보존한다.

## 포함 파일

- `SERVICE_PLAN_260824_v0.2.md`, `REQUIREMENTS_SPEC_260824_v0.2.md`, `IA_SCREEN_SPEC_260824_v0.2.md`, `DECISION_SHEET_260824_v0.2.md` — 260825 v0.3 세트로 대체되기 직전까지 사용된 root 정본 4종.

## v0.2 → v0.3 핵심 변경

팀 회의에서 도출된 수정점을 반영해 다음을 v0.3에서 새로 확정했다(자세한 내용은 `DECISION_SHEET_260825_v0.3.md`의 "2026-08-25 v0.3 Entry / Milestone / URL Share Superseding Decision" 참고).

- Service Home 진입 화면을 폐기하고 Splash → Shared Input Shell로 진입 구조를 단순화
- selected route의 의미 있는 경유포인트(milestone)별 `보통/여유` 시간 projection을 신규 도입
- 결과 공유를 URL 기반 public read-only Share로 canonical화 (image/카카오톡 직접 전송 배제)
- Departure Recommendation과 Leave-now Forecast(도착 시간 계산)의 기능 독립성(별도 submit/API/result) 계약을 강화
- Leave-now(Arrival) 핵심 계약에서 mandatory `targetArrivalAt`과 user-facing `P(on_time)`을 제거(RETIRED_FROM_MR_V0.3)

## 정본 위치

이 폴더는 과거 상태 보존용이며, **현행 기획 검토는 항상 docs root의 260825 v0.3 세트(`SERVICE_PLAN_260825_v0.3.md`, `REQUIREMENTS_SPEC_260825_v0.3.md`, `IA_SCREEN_SPEC_260825_v0.3.md`, `DECISION_SHEET_260825_v0.3.md`)를 기준으로 시작한다.**
