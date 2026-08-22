# Journey Reliability — Planning & Specification Docs v2 FINAL

이 패키지는 서울 대중교통 Journey Reliability 프로젝트의 최신 Markdown 정본과,
Phase 0에서 실제로 생성된 핵심 문서·샘플·Spike 스크립트의 **baseline archive**를 함께 묶은 작업 패키지다.

## 가장 먼저 읽을 파일

1. `docs/00_governance/00_MASTER_INDEX.md`
2. `docs/00_governance/01_DOCUMENT_CONSTITUTION.md`
3. `docs/00_governance/02_DECISION_LOG.md`
4. `docs/00_governance/03_EVIDENCE_REGISTER.md`
5. `docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md`

## 폴더 역할

```text
journey_reliability_docs_v2/
├─ docs/                 # 현재 기획/설계 정본
├─ baseline/phase0/      # result.zip에서 가져온 Phase 0 evidence baseline
├─ scripts/              # 문서 정합성/manifest 검증
├─ .env.example          # secret 이름만 있는 예시. 실제 값 없음
└─ MANIFEST_SHA256.txt
```

### `docs/`
현재 제품/정책/계약의 Source of Truth.

### `baseline/phase0/`
Phase 0의 원본 산출물 중 이번 정본을 검증/재현하는 데 필요한 자료만 포함한다.
과거 제품 정책의 정본은 아니며, **Raw/Spike/Evidence의 historical baseline**이다.

## 현재 상태

- Phase 0 API/Data Feasibility: **Demo OD/corridor 기준 GO**
- Primary Route A: `01A → 3호선 → 2호선` structural path 실제 응답 확인
- Cross-mode Route B: **동일 OD의 실제 대안 경로에 `SUBWAY→BUS` 구조가 이미 존재함을 Raw에서 확인**
- Cross-mode Route B realtime ID/상태 E2E: **추가 검증 필요**
- Probability Engine: 계약 작성 완료, 실제 결과/validation 미완료
- Web App: 구현 증거 없음
- Distributed Proof: 미실시
- Citywide 일반화: 미검증

## 중요한 사용 규칙

데이터/API 사실은 `실제 Raw/Spike > 현재 공식 문서 > Evidence Register > 과거 조사자료` 순서로 판단한다.
제품 결정은 최신 `docs/00_governance/02_DECISION_LOG.md`가 정본이다.
구현 완료 여부는 실제 코드/테스트가 정본이다.

Evidence 작업을 VS Code Agent에게 맡길 때는 채팅에 긴 프롬프트를 다시 조립하지 말고
`docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md`를 읽고 실행하도록 지시한다.
