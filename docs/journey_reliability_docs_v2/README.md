# Journey Reliability — Planning & Specification Docs v2.1 FINAL

이 패키지는 서울 대중교통 Journey Reliability 프로젝트의 최신 Markdown 정본과,
Phase 0 baseline 및 2026-08-22 Phase 1 실제 Evidence 산출물을 함께 묶은 작업 패키지다.

## 가장 먼저 읽을 파일

1. `docs/00_governance/00_MASTER_INDEX.md`
2. `docs/00_governance/01_DOCUMENT_CONSTITUTION.md`
3. `docs/00_governance/02_DECISION_LOG.md`
4. `docs/00_governance/03_EVIDENCE_REGISTER.md`
5. `evidence/phase1/PHASE1_EVIDENCE_VALIDATION_REPORT.md`
6. 다음 Evidence 작업이 필요하면 `docs/00_governance/10_PHASE2_EVIDENCE_EXECUTION.md`

## 폴더 역할

```text
journey_reliability_docs_v2/
├─ docs/                 # 현재 기획/설계 정본
├─ baseline/phase0/      # Phase 0 historical evidence baseline
├─ evidence/phase1/      # Phase 1 live API / official-file evidence + report
├─ scripts/              # 문서 정합성/manifest 검증
├─ .env.example          # secret 이름만 있는 예시. 실제 값 없음
└─ MANIFEST_SHA256.txt
```

### `docs/`
현재 제품/정책/계약의 Source of Truth.

### `baseline/phase0/`
Phase 0의 historical Raw/Spike/Evidence baseline. 과거 제품 정책의 정본은 아니다.

### `evidence/phase1/`
2026-08-22 실제 API 및 공식 서울 open-data 파일을 사용한 Phase 1 검증 결과다.
정본 변경은 이 Evidence를 `Decision → impacted docs → Traceability → lint` 순서로 반영한 현재 패키지가 우선한다.

## 현재 상태

- Phase 0 API/Data Feasibility: **Demo OD/corridor 기준 GO**
- Route A structural path: **VERIFIED**
- Route B `SUBWAY→BUS` structural + realtime source interoperability: **VERIFIED, corridor-scoped**
- Route B `BUS_SKIPPED` Reforecast product implementation: **NOT_STARTED**
- Demo ACCESS WALK: **VERIFIED point route** — 297 m / 245 s
- Route A BUS→SUBWAY street component: **VERIFIED**, station-internal component **UNMODELED**
- Demo FINAL WALK: **VERIFIED as STATION_CENTER→POI point route** — 329 m / 300 s; exit-based result 아님
- 교대 3→2 static transfer rows: **VERIFIED**; Tier-0 canonical reference는 OA-22521의 144 s
- Bus future WAIT source feasibility: **VERIFIED**, 단 20초 polling snapshot을 독립표본으로 간주하지 않음
- Subway timetable source: **CONDITIONAL** — 2025-09-30 dated file의 current validity 미검증
- Subway Actual: 실제 interval 발생 확인, 그러나 quota로 22~33분 window + 역삼 0건 → **maturity 부족**
- Bus 01A target leg: 실제 traverse 11건 확보, 그러나 **Prediction→Actual residual artifact는 아직 미생성**
- Probability Engine: 계약 작성 완료, 구현/validation 미완료
- Web App / Kafka/Flink/Spark distributed proof: 미구현/미실시
- Citywide 일반화: 미검증

## 중요한 사용 규칙

데이터/API 사실은 `실제 Raw/Spike > 현재 공식 source > Evidence Register > 과거 조사자료` 순서로 판단한다.
제품 결정은 최신 `docs/00_governance/02_DECISION_LOG.md`가 정본이다.
구현 완료 여부는 실제 코드/테스트가 정본이다.

Phase 1 실행 지시문 `09_PHASE1_EVIDENCE_EXECUTION.md`는 완료된 historical work-order로 `SUPERSEDED` 처리되었다.
다음 검증 라운드는 `10_PHASE2_EVIDENCE_EXECUTION.md`를 사용한다.
