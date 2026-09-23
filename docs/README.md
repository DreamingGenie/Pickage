# docs

프로젝트 기획 자료와 회의 내용을 담는 폴더입니다.

## 현재 주제 — Pickage (구 OSS Shift)

오픈소스 생태계에서 **어떤 패키지가 어떤 패키지로 갈아타고 있는지**를 deps.dev 데이터로 계산하는 주제입니다.
최초 제안서는 `history/idea/OSS_Shift_Proposal_2026-08-20.pdf` 입니다. 2026-09-04 기획 세트부터
서비스명이 `Pickage`로 확정되었고, MVP 범위도 함께 조정되었습니다 — 무엇이 바뀌었는지는 아래
`Pickage_0902_to_0904_기획변경_상세분석.md`를 참고하세요.

### 기획 정본 교체 중 (2026-09-23)

0917 기획 문서 5종과 개발이 끝난 GitHub 커뮤니티 구현 기록은 0923 완성 기준 문서로
교체하기 위해 아래 보관 폴더로 옮겼습니다. 새 정본은 현재 코드·데이터·배포 구성을 전수 조사한
뒤 이 위치에 게시합니다.

- [0917 기획 문서와 커뮤니티 기록 보관본](history/0923_0917_pickage_final_set_archive/) — 서비스 기획서·요구사항 명세서·메뉴구조 IA·기능별 개발 구상안·0915→0917 변경 분석과 `for_community/` 전체
- [GitHub 커뮤니티 현황 구현 계획 보관본](history/0923_0917_pickage_final_set_archive/for_community/Pickage_GitHub커뮤니티_구현계획_260908.md) — 2026-09-11 기준 DB·API·수집·요약·화면·운영 실행 계약
- [개발 일정표 0907 보관본](history/0910_260909_pickage_final_set_archive/Pickage_개발_일정표_0907.md) — 당시 MVP 2026-09-13·확장 포함 2026-09-20 목표 일정. 현재 기획 정본이 아니라 0909 세트와 함께 보존
- `분석_제공가치_deps.dev_260901.md` — deps.dev 원천 데이터가 만들 수 있는 사용자 가치 실측 분석. 누적 인기와 신규 채택 분리, 버전 고착 지표를 근거로 제시
- `설계_마이그레이션쌍_탐지_260831.md` — 마이그레이션 쌍 탐지 가능성 검증과 전체 설계. *소규모 실물 검증 완료, 전체 규모 미검증*
- `검증_다운로드수_수집가능성_260831.md` — npm 다운로드 수로 이용량 추이를 만들 수 있는지 실측. *실측 완료*
- `api & data/depsdev_BigQuery_데이터셋_사용계획_260831.md` — deps.dev BigQuery 데이터셋에서 무엇을 쓸지 확정
- `api & data/수집계획_BigQuery_Parquet_v2_260902.md` — deps.dev BigQuery → GCS Parquet 수집계획 v2. *확정, T0·T1 수집 완료*
- `api & data/수집현황_팀공유_260902.md` — 위 수집계획의 팀 공유용 현황 요약
- `api & data/검증_keywords_수집가능성_260908.md` — AI 유사 패키지 학습용 keywords 수집 가능성·속도 실측 (ecosyste.ms vs npm registry). *권고: ecosyste.ms 상위 100만, 단일 PC 2시간*
- `api & data/수집결과_keywords_프로파일_260908.md` — 상위 100만 keywords 수집 결과(104분·429 0건)와 결합 전 프로파일: 구간별 보유율, description 결손, tea 스팸 농장, 결합 규칙
- `api & data/작업계획_이탈률_대체없이제거_260909.md` — 이동쌍 빌더에 "대체 없이 제거" 비율·연도별 이탈 집계·배포주체-월 기준 점유율(`share_pm_pct`)을 추가하는 작업계획과 실측 기록(S15P21A506-281)
- `api & data/수집계획_devDependencies_npmRegistry_260909.md` — npm registry 전 버전 문서로 상위 10만 패키지의 devDependencies 포함 의존 선언 이력을 받는 계획(S15P21A506-280). deps.dev 에 없는 개발용 의존 이동(enzyme → testing-library 등)을 이동쌍에 넣기 위함. *09-10 수집 완료: READY 99,209 · NOT_FOUND 358 · UNPUBLISHED 429 · 실패 0(작업 99,996), 버전 행 2,144만, §7 실측 기록·§5 검증 완료. 09-14 자체 리뷰 2회 반영으로 파싱·변환 규칙과 §5-3 검증 기준을 고치고 재변환*

수집·계산으로 만든 파생 데이터(폐기→대체 쌍, 마이그레이션 이동쌍, 학습 후보 표본, 수집 대상 목록)는 문서 폴더가 아니라 리포 루트 `../datasets/`에 둡니다. 각 폴더의 README가 열 의미와 생성 스크립트를 설명합니다.

이전 세대였던 0831 서비스 기획 초안 4종(서비스 기획서·요구사항 명세서·메뉴구조 IA·기능별 개발 구상안)은
`history/0901_260831_oss_shift_초안/` 로 보존했습니다. 그 후속이었던 0901 최종 세트 4종과, 그 세트의
최상위 기준이었던 `OSS_Shift_피드백_의견_대응방안_통합설계_0831.md`는 0902 세트로 대체되어
`history/0902_260901_oss_shift_final_set_archive/` 로 이관했습니다. 그 0902 최종 세트 5종(서비스
기획서·요구사항 명세서·메뉴구조 IA·기능별 개발 구상안·상세 변경명세서)도 서비스명이 `Pickage`로
바뀐 0904 세트로 대체되어 `history/0907_260902_oss_shift_final_set_archive/` 로 이관했습니다
(개발 일정표는 당시 교체 대상이 아니었습니다). 그 0904 세트도 GitHub
커뮤니티 패키지 선택 단일화·Spring→GMS 예외(`S15P21A506-284`)와 후보 ranking deprecated 완전
제외·top-K/Recall 20 하향(`S15P21A506-285`)을 반영한 0909 세트로 대체되어
`history/0909_260904_pickage_final_set_archive/` 로 이관했습니다. 0909 세트와 0907 개발 일정표는
0910 최종 세트로 교체되면서 `history/0910_260909_pickage_final_set_archive/`에 함께 보존했습니다.
그 0910 세트는 09-11 이후 누적된 개발현황 반영과 간접·전이 Dependency(확장-04) 프로젝트 범위
제외(`S15P21A506-358`)를 반영한 0915 세트로 대체되어
`history/0915_260910_pickage_final_set_archive/` 로 이관했습니다.
그 0915 세트도 GitHub 커뮤니티·GMS 요약 생성 구현 완료, 유사후보 추천 dependency-overlap
관문의 데이터 기반 마련(관문 로직 자체는 미구현 유지), 주간 배치 자동화 구현 완료, Dependents·
Downloads 그래프 지수·증감·로그축 압축 표시 추가와 Version Share "패키지 탭" 범위 정정
(`S15P21A506-380`)을 반영한 0917 세트로 대체되어 `history/0917_0915_pickage_final_set_archive/`
로 이관했습니다.
그 0917 세트와 개발이 끝난 `for_community/` 기록은 0923 완성 기준 문서로 교체하는 과정에서
`history/0923_0917_pickage_final_set_archive/` 로 이관했습니다.

### 아직 없는 것 (새로 써야 함)

- API Key 발급 가이드 — deps.dev BigQuery(GCP)와 npm registry 기준이라 발급처가 완전히 다릅니다
- 데이터 플랫폼 수집 작업을 나눈 Jira 이슈 초안 (수집계획 자체는 `api & data/수집계획_BigQuery_Parquet_v2_260902.md`로 이미 작성됨)

## 이전 주제 — Journey Reliability (폐기)

서울 대중교통 실시간 데이터 기반 경로 신뢰도 주제는 2026-08-28 폐기했습니다.
기획·API 분석·수집기 코드·기준 CSV까지 전부 `history/0901_journey_reliability_legacy/` 로 이관했으며,
폐기 사유와 폴더 구성은 그 안의 `README.md` 에 있습니다. **현행 검토에 섞지 않습니다.**

`history/` 아래 나머지 폴더도 과거 작업 산출물과 근거 보존용입니다.

## 계속 쓰는 것

- `templates/jira/` — Jira 이슈 템플릿(스토리 · 작업 · 버그). 주제와 무관하게 유지합니다.
- [브랜치 작업 기록 — S15P21A506-267](worklogs/S15P21A506-267/README.md) — PostgreSQL 전체 적재의 범위·계획·이슈 해결·수행 내역·실제 검증 결과입니다.
- [다운로드 원본 입고·스냅샷 구간 집계 — S15P21A506-278](worklogs/S15P21A506-278/README.md) — 원본 검증·Bronze 입고와 스냅샷 구간 다운로드 집계·Curated 초도 게시 결과, 후속 DB 인계 범위를 기록합니다.
- [패키지 스냅샷 지표 통합·PostgreSQL 적재 — S15P21A506-288](worklogs/S15P21A506-288/README.md) — 초도 기준일과 배포일 기준으로 재구성한 전체 229개 기준일의 적재·검증을 완료했습니다. 초도 결과와 전체 기간 완료 근거를 구분해 기록합니다.
- `../AGENTS.md` — 팀 협업 규칙. 주제와 무관하게 유지합니다.

## Secret Hygiene

실제 API key나 credential 값은 docs root에 두지 않습니다. 키 이름만 문서에 적고,
실제 값은 Git이 추적하지 않는 로컬 `.env` 또는 실행 환경 secret으로 관리합니다.
