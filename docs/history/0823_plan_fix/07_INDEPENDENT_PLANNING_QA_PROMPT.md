# Independent Planning QA Prompt

첫 Agent가 완료한 뒤 다른 Agent에 아래 본문을 입력한다.

---

당신은 Journey Reliability 최종 기획 세트의 독립 Reviewer다.

검수 대상:

- `SERVICE_PLAN_260823.md`
- `IA_SCREEN_SPEC_260823.md`
- `REQUIREMENTS_SPEC_260823.md`
- 2026-08-23 experiment manifests, call ledger, raw evidence, Decision Sheet
- `JR_EXPERIMENT_PACK_260823/01_UNCERTAINTY_RESOLUTION_MATRIX.md`
- `JR_EXPERIMENT_PACK_260823/05_EVIDENCE_RECORD_AND_DECISION_RULES.md`

기준 정본:

- `SERVICE_PLAN_260822.md`
- `IA_SCREEN_SPEC_260822.md`
- `REQUIREMENTS_SPEC_260822.md`

이번 작업은 문서·evidence QA다. API를 추가 호출하지 않고 production code·collector·test code·DB·infra·deployment를 생성하거나 수정하지 않는다.

## 1. Evidence audit

각 claim에 대해 다음을 검사한다.

- raw file과 SHA-256이 존재하는가
- request params·coordinate role·timestamps·provider version이 있는가
- secret scan이 통과했는가
- 호출 수와 quota counter delta가 일치하는가
- Fact·Derived fact·Inference·Decision이 분리됐는가
- provider×endpoint×OD/corridor×window×service day scope가 있는가
- no-event·failure·safe stop을 0이나 success로 바꾸지 않았는가

## 2. 핵심 정책 audit

다음 오류가 하나라도 있으면 `BLOCKER`다.

- Kakao/TMAP point에 임의 분포 부여
- publictraffic gap을 근거 없이 WAIT/WALK/Transfer로 확정
- name-only Kakao stop을 canonical ID로 자동 승격
- Kakao 경복궁.국립민속박물관→안국 후보와 승인 Route A 춘추문→안국을 동일시
- Kakao first candidate를 Route A Demo로 사용
- snapshot row를 independent Bus WAIT sample로 계산
- traverse duration을 residual로 재분류
- BUS_SKIPPED를 개인 boarding failure probability로 모델링
- P90을 accuracy/guarantee로 설명
- component evidence를 end-to-end calibration으로 표현
- Sunday END 결과를 DAY/SAT/전체 service day로 일반화
- one-day evidence로 mature distribution·Recommended Departure·citywide SLA claim
- fixture/recorded 결과를 live/real로 표현

## 3. Quota audit

- Kakao publictraffic/WALK app limit 각각 1,000/day가 동일하게 표현됐는가
- daily limit와 overage billing/reset 상태가 분리됐는가
- 서울 Bus approved limit가 실제 evidence 없이 숫자로 채워지지 않았는가
- 서울 Subway counter·reserve·business error가 trace되는가
- TMAP public transit 10/day를 runtime budget으로 일반화하지 않았는가
- quota exhaustion을 고의로 유발하거나 key rotation한 evidence가 없는가

## 4. Data semantics audit

- station×line·route×stop×vehicle/train identity가 보존되는가
- Prediction은 Actual 이전에 존재하는가
- Actual은 polling interval uncertainty를 보존하는가
- Residual은 signed L/M/U이며 duration과 다른 value type인가
- out-of-order는 receive order에서 측정되는가
- latency는 request boundary이고 provider internal latency로 과장되지 않는가
- WAIT·TRANSFER·WALK·RIDE 경계가 중복되지 않는가
- coordinate role/source/mappingVersion이 있는가

## 5. Document-role audit

Service Plan:

- 사용자 문제·가치·범위·정책·운영·성공·리스크를 설명하는가
- raw 기술 dump가 아닌 rationale로 evidence를 사용하는가

IA:

- 화면·상태·guard·CTA·copy·recovery에 집중하는가
- Backend/Data 내부 수치를 불필요하게 복제하지 않는가

Requirements:

- REQ/BR/NFR/API/ENT/AC/TBD/Claim Gate가 구현·QA 가능한가
- 실제 ID 수량과 문서 선언 수량이 일치하는가
- Traceability가 끊기지 않는가

## 6. Cross-document audit

다음 개념의 상태·숫자·의미가 세 문서에서 같은지 확인한다.

- selected route와 coverageMode
- Route A/B 역할
- Kakao Provider Gate
- quota/billing/reset
- provider mapping status
- P50/P90/P(on_time)/connection/Recommended Departure
- support/confidence/fallback/freshness/validation
- Prediction/Actual/Residual
- BUS_SKIPPED와 Reforecast
- WALK/WAIT/Transfer domain boundary
- 확정 사실·미확정·금지 claim

## 7. Severity와 수정

| Severity | 의미 |
|---|---|
| BLOCKER | evidence 위반·제품 의미 충돌·거짓 claim 가능 |
| MAJOR | 구현/QA/UX가 다른 정책으로 해석될 위험 |
| MINOR | 추적성·용어·형식 문제 |

먼저 문제 목록을 severity 순으로 제시한다. BLOCKER 또는 MAJOR가 있으면 세 기획 문서만 수정하고 전체 검사를 다시 수행한다. evidence raw·실험 코드·개발 파일은 수정하지 않는다. 문제가 없으면 불필요하게 문서를 재작성하지 않는다.

## 8. 최종 응답

- 발견 문제와 수정 결과
- 문서별 PASS/FAIL
- 교차 정합성 PASS/FAIL
- 아직 남은 실제 미확정 항목
- 추가 API 호출을 수행하지 않았다는 확인
- production code·개발 설정·배포를 변경하지 않았다는 확인

