# 0823 Policy Decisions Handoff

이 폴더는 2026-08-23 도착한 정책 확정 지시서(`JR_POLICY_DECISIONS_AGENT_HANDOFF_260823.md`)를 root 정본 3종(Service Plan/IA/Requirements)에 반영하기 **직전** 상태의 스냅샷과, 반영을 지시한 원본 문서를 보존한다.

## 포함 파일

- `JR_POLICY_DECISIONS_AGENT_HANDOFF_260823.md` — 반영을 지시한 정책 확정 지시서 원본. 3개 핵심 결정(A: 서울 임의 OD MVP, B: 계획 지점 사용자 도착 확인, C: provider 데이터 정책)을 확정한다.
- `JR_FINAL_SET_EXPERT_REVIEW_260823.md` — 이보다 앞서 도착했던 외부 전문가 검토 보고서 원본(별도 작업 S15P21A506-54에서 이미 반영 완료됨). 감사 이력 보존을 위해 함께 이관.
- `SERVICE_PLAN_260823_past.md`, `IA_SCREEN_SPEC_260823_past.md`, `REQUIREMENTS_SPEC_260823_past.md`, `DECISION_SHEET_260823_past.md` — 이번 반영 작업(S15P21A506-55) 착수 직전 root 정본의 스냅샷. 파일명 뒤 `_past`는 같은 이름의 현재 정본과 혼동되지 않도록 붙였다.

## 반영 내용 요약

지시서의 3개 결정과 PM 결정에 따라 root 문서를 다음과 같이 갱신했다.

1. Kakao publictraffic을 서울 임의 OD의 discovery-only runtime route provider로 활성화(REQ-104 강화, budget 0 제거)
2. canonicalization crosswalk를 REQ-105/BR-085로 신설, Cuttable Expansion으로 WBS·Scope Cut에 명시
3. ACCESS_WALK 자동완료(ST-023)를 사용자 CTA(정류장/역 도착)로 전환
4. `ProviderPolicyRegistry`(ENT-024)와 default-deny 원칙(NFR-094, BR-086)을 도입해 Kakao raw retention을 `UNVERIFIED`로 정정
5. Coverage 필드명(5축 + `routeCoverageMode`/`walkProviderMode`/`modelCoverage`)은 기존 구조 유지

## 정본 위치

이 폴더는 과거 상태 보존용이며, **현행 기획 검토는 항상 docs root의 정본 4개(`SERVICE_PLAN_260823.md`, `IA_SCREEN_SPEC_260823.md`, `REQUIREMENTS_SPEC_260823.md`, `DECISION_SHEET_260823.md`)를 기준으로 시작한다.**
