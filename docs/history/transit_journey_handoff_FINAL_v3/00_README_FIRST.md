# START HERE — Transit Journey Reliability Handoff FINAL v3

이 폴더는 VS Code의 Claude/Codex에 프로젝트를 넘기기 위한 **자기완결형 handoff package**다.

## 딱 이렇게 사용

1. 이 ZIP을 GitLab monorepo 안에 통째로 압축 해제한다.
2. Agent에게 `docs/02_AGENT_CONTINUATION_PROMPT.md` 내용을 그대로 첫 프롬프트로 준다.
3. Agent가 먼저 이 package의 실제 파일 경로를 검증한 뒤 Phase 0 API/Data Feasibility부터 시작하게 한다.

## 읽는 순서
1. `docs/01_PROJECT_HANDOFF.md`
2. `docs/02_AGENT_CONTINUATION_PROMPT.md`
3. `docs/03_API_SPIKE_CHECKLIST.md`
4. `docs/04_SOURCE_INDEX.md`
5. `docs/05_DECISION_LOG.md`
6. `sources/project/`
7. 필요 시 `sources/reference_quality/`

## 실제 폴더 구조
```text
transit_journey_handoff_FINAL_v3/
├─ 00_README_FIRST.md
├─ FILE_MAP.md
├─ MANIFEST_SHA256.txt
├─ PACKAGE_VALIDATION.txt
├─ docs/
│  ├─ 01_PROJECT_HANDOFF.md
│  ├─ 02_AGENT_CONTINUATION_PROMPT.md
│  ├─ 03_API_SPIKE_CHECKLIST.md
│  ├─ 04_SOURCE_INDEX.md
│  └─ 05_DECISION_LOG.md
├─ sources/
│  ├─ project/
│  │  ├─ 01_bus_eta_reliability.pdf
│  │  ├─ 02_bus_api_scenario.pdf
│  │  ├─ 03_journey_probability_research.pdf
│  │  ├─ 04_journey_probability_ai_design.pdf
│  │  ├─ 05_subway_detail.pdf
│  │  └─ 06_subway_reliability_metric.pdf
│  ├─ reference_quality/
│  │  ├─ 90_oss_shift_proposal.pdf
│  │  └─ 91_service_plan_reference.md
│  └─ text_extracted/
│     ├─ 01_bus_eta_reliability.txt
│     ├─ 02_bus_api_scenario.txt
│     ├─ 03_journey_probability_research.txt
│     ├─ 04_journey_probability_ai_design.txt
│     ├─ 05_subway_detail.txt
│     ├─ 06_subway_reliability_metric.txt
│     └─ 90_oss_shift_proposal.txt
└─ templates/
   └─ .env.example
```

## 현재 상태
- 최종 마감: **2026-09-28**
- 팀: 6명
- 제품: **서울 버스+지하철 Journey Reliability Web App**
- API Keys: **취득 완료**
- Secret 값: **이 package에 없음**
- 현재 단계: **Phase 0 — 실제 API Spike / Data Feasibility / Contract**

## 중요
- 파일명은 Windows/Agent 호환성을 위해 package 내부에서는 영문으로 통일했다.
- 원래 한글 파일명은 `FILE_MAP.md`와 `docs/04_SOURCE_INDEX.md`에 명시했다.
- PDF 텍스트 추출본은 검색 편의용이며 표/그림/레이아웃 해석은 원본 PDF를 기준으로 한다.
