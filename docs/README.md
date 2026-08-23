# docs

프로젝트 기획 자료와 회의 내용을 담는 폴더입니다.

## Current Planning Set

- `SERVICE_PLAN_260823.md`
- `REQUIREMENTS_SPEC_260823.md`
- `IA_SCREEN_SPEC_260823.md`
- `DECISION_SHEET_260823.md`

`history/` 아래 문서는 과거 작업 산출물과 근거 보존용입니다. 현행 기획 검토는 위 root 문서 4개를 기준으로 시작합니다.

## Secret Hygiene

실제 API key나 credential 값은 docs root에 두지 않습니다. 필요한 키 이름은 `docs/.env.example`만 참고하고, 실제 값은 Git이 추적하지 않는 로컬 `.env` 또는 실행 환경 secret으로 관리합니다.
