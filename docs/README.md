# docs

프로젝트 기획 자료와 회의 내용을 담는 폴더입니다.

## Current Planning Set

- `SERVICE_PLAN_260825_v0.3.md`
- `REQUIREMENTS_SPEC_260825_v0.3.md`
- `IA_SCREEN_SPEC_260825_v0.3.md`
- `DECISION_SHEET_260825_v0.3.md`

`history/` 아래 문서는 과거 작업 산출물과 근거 보존용입니다. 현행 기획 검토는 위 root 문서 4개를 기준으로 시작합니다. 직전 세트(260824 v0.2)는 `history/0826_260824_v0.2_planning_set_archive/README.md`로, 그 이전 세트(260823)와 PDF 해설서는 `history/0824_260823_planning_set_archive/README.md`로 이관했습니다.

## API Key 발급

각 provider(서울 열린데이터광장, data.go.kr, Kakao Map, TMAP)의 실제 API key를 어디서 어떻게 받는지는 `api & data/API_KEY_발급_가이드_260823.md`에 정리돼 있습니다.

## Secret Hygiene

실제 API key나 credential 값은 docs root에 두지 않습니다. 필요한 키 이름은 위 API Key 발급 가이드만 참고하고, 실제 값은 Git이 추적하지 않는 로컬 `.env` 또는 실행 환경 secret으로 관리합니다.
