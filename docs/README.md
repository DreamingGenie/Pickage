# docs

프로젝트 기획 자료와 회의 내용을 담는 폴더입니다.

## 현재 주제 — OSS Shift

오픈소스 생태계에서 **어떤 패키지가 어떤 패키지로 갈아타고 있는지**를 deps.dev 데이터로 계산하는 주제입니다.
최초 제안서는 `history/idea/OSS_Shift_Proposal_2026-08-20.pdf` 입니다.

### 현행 문서 (2026-08-31)

- `설계_마이그레이션쌍_탐지_260831.md` — 마이그레이션 쌍 탐지 가능성 검증과 전체 설계. *소규모 실물 검증 완료, 전체 규모 미검증*
- `검증_다운로드수_수집가능성_260831.md` — npm 다운로드 수로 이용량 추이를 만들 수 있는지 실측. *실측 완료*
- `api & data/depsdev_BigQuery_데이터셋_사용계획_260831.md` — deps.dev BigQuery 데이터셋에서 무엇을 쓸지 확정

### 아직 없는 것 (새로 써야 함)

이전 주제 기준으로만 존재하던 문서들은 전부 아카이브로 보냈습니다. OSS Shift 기준으로 다시 써야 합니다.

- 서비스 기획 4종 — SERVICE_PLAN · REQUIREMENTS_SPEC · IA_SCREEN_SPEC · DECISION_SHEET
- 데이터 플랫폼 계획서와 그에 딸린 Jira 이슈 초안
- API Key 발급 가이드 — 새 주제는 deps.dev BigQuery(GCP)와 npm registry 기준이라 발급처가 완전히 다릅니다

## 이전 주제 — Journey Reliability (폐기)

서울 대중교통 실시간 데이터 기반 경로 신뢰도 주제는 2026-08-28 폐기했습니다.
기획·API 분석·수집기 코드·기준 CSV까지 전부 `history/0901_journey_reliability_legacy/` 로 이관했으며,
폐기 사유와 폴더 구성은 그 안의 `README.md` 에 있습니다. **현행 검토에 섞지 않습니다.**

`history/` 아래 나머지 폴더도 과거 작업 산출물과 근거 보존용입니다.

## 계속 쓰는 것

- `templates/jira/` — Jira 이슈 템플릿(스토리 · 작업 · 버그). 주제와 무관하게 유지합니다.
- `../.agents/AGENTS.md` — 팀 협업 규칙. 주제와 무관하게 유지합니다.

## Secret Hygiene

실제 API key나 credential 값은 docs root에 두지 않습니다. 키 이름만 문서에 적고,
실제 값은 Git이 추적하지 않는 로컬 `.env` 또는 실행 환경 secret으로 관리합니다.
