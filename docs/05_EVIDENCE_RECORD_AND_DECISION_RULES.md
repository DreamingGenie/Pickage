# Evidence Record and Decision Rules

## 1. Experiment manifest template

```yaml
experimentId:
scenarioId:
purpose:
startedAtUtc:
endedAtUtc:
serviceDateKst: 2026-08-23
serviceDay: END
operator:
environment:
providerKey:
endpoint:
credentialAlias: # secret가 아닌 alias
approvedLimit:
usedBefore:
usedAfter:
remainingAfter:
resetEvidence:
budgetCap:
actualCalls:
probeOrCollectorPath:
probeOrCollectorSha256:
requestParamsSanitized:
coordinateRoles:
rawFiles:
rawSha256:
secretScanResult:
sourceTimestampAvailable:
requestedAtAvailable:
receivedAtAvailable:
status: PASS | PARTIAL | FAIL | SAFE_STOP | INCONCLUSIVE | BLOCKED_TOOLING
scope:
limitations:
```

## 2. Call ledger template

| seq | requestedAt | receivedAt | provider/endpoint | scenario/window | HTTP | business status | counter delta | raw path/hash | retry reason |
|---:|---|---|---|---|---:|---|---:|---|---|

retry도 별도 call row다. 동일 call을 성공·실패 두 건으로 중복 세지 않는다.

## 3. Evidence result template

```markdown
## [Experiment ID] 제목

### Question
무엇을 확인하려 했는가?

### Preconditions
- identity/coordinate/quota/tool version

### Observed facts
- raw에서 직접 관측한 사실만 기록

### Derived metrics
- 산식, unit, sample unit, numerator/denominator

### Inference
- raw fact와 구분한 해석

### Decision
- FIXED / CONDITIONAL / HOLD / REJECTED / NO_CHANGE

### Scope
- provider×endpoint×OD/corridor×window×service day

### Limitations
- 이 evidence가 말하지 못하는 것

### Document impact
- Service Plan:
- IA:
- Requirements:

### Next gate
- 남은 최소 evidence
```

## 4. Fact·Inference·Decision 분리

| 층 | 예시 | 문서 사용 |
|---|---|---|
| Fact | `routes.length=15`, stop key가 name뿐임 | Evidence/요구사항 근거 |
| Derived fact | `totalTime - stepTime = 887s` | 산식과 함께 사용 |
| Inference | distance/time gap이 hidden walk일 가능성 | limitation과 함께 사용 |
| Decision | gap을 WAIT에 배분하지 않음 | 제품 정책 |
| Claim | Kakao가 서울 전체 route를 지원 | 별도 coverage evidence 전 금지 |

Inference를 Fact로, component evidence를 Claim으로 승격하지 않는다.

## 5. 상태 변경 규칙

| 현재 항목 | 변경 가능 조건 | 가능한 상태 | 변경 금지 조건 |
|---|---|---|---|
| Kakao app limit | console endpoint별 limit/counter 캡처 | `APP_LIMIT_CONFIRMED` | 공식 문서만 있고 app 화면 없음 |
| billing/reset | billing/reset 직접 evidence | CONFIRMED 또는 UNCONFIRMED 분리 | limit에서 추론 |
| raw pending | file hash+secret scan+manifest | `RECEIVED_HASH_VERIFIED`; register 등록 시 INGESTED | 파일 경로·hash 누락 |
| time semantics | explicit field/docs 또는 boundary WALK comparison | EXPLICIT/SUPPORTED/PARTIAL/AMBIGUOUS | gap 임의 분배 |
| route mapping | deterministic crosswalk+version | MAPPED | fuzzy name-only |
| repeat stability | identical request raw signatures | tested scope stable/variable | 1회 호출 |
| Bus/Subway Actual | identity+transition+timestamp | valid interval event | rule 완화·target mismatch |
| Residual | Actual 이전 Prediction과 signed interval | component residual | traverse duration 재분류 |
| WAIT support | passenger-relevant event units across independent windows | CONDITIONAL evidence | snapshot rows를 iid로 사용 |
| Recommended Departure | future service re-evaluation+WAIT/residual+replay | AVAILABLE Gate candidate | point times만 존재 |

## 6. No-event와 failure 판정

| 상황 | 판정 | 금지 |
|---|---|---|
| valid 호출이나 target event 없음 | `NO_VALID_EVENT` | residual=0 |
| quota 전 안전 중단 | `SAFE_STOP` | provider unsupported로 번역 |
| business error | provider error code 보존 | HTTP 200 success 처리 |
| mapping ambiguous | `ROUTE_MAPPING_INCOMPLETE/AMBIGUOUS` | 첫 name match 선택 |
| raw 저장 실패 | `INCONCLUSIVE` | terminal summary만으로 schema claim |
| 필요한 도구 부재 | `BLOCKED_TOOLING` | 그 자리에서 production code 개발 |

## 7. 하루 종료 Decision Sheet

| Item | Before | Evidence | Decision | Scope | Service Plan | IA | Requirements | Remaining gate |
|---|---|---|---|---|---|---|---|---|
| Kakao limit | UNCONFIRMED |  |  |  |  |  |  |  |
| Kakao raw | RAW_PENDING |  |  |  |  |  |  |  |
| Kakao time semantics | CONDITIONAL |  |  |  |  |  |  |  |
| Kakao mapping | CONDITIONAL |  |  |  |  |  |  |  |
| Candidate stability | UNVERIFIED |  |  |  |  |  |  |  |
| Bus Actual/Residual | IMMATURE |  |  |  |  |  |  |  |
| Bus WAIT | HOLD |  |  |  |  |  |  |  |
| Subway identity/residual | COMPONENT |  |  |  |  |  |  |  |
| quota operations | PARTIAL |  |  |  |  |  |  |  |
| Recommended Departure | HOLD |  |  |  |  |  |  |  |

## 8. 문서 승격 방지 체크

- [ ] point estimate를 distribution으로 바꾸지 않았다.
- [ ] snapshot row를 independent support로 세지 않았다.
- [ ] `BUS_SKIPPED`를 개인 boarding failure probability로 만들지 않았다.
- [ ] `P90`을 accuracy 또는 guarantee로 설명하지 않았다.
- [ ] Kakao/TMAP/서울시 값을 provenance 변경 없이 유지했다.
- [ ] Kakao candidate와 approved Route A를 혼합하지 않았다.
- [ ] component validation과 Journey calibration을 분리했다.
- [ ] Sunday `END` 결과를 DAY/SAT로 일반화하지 않았다.
- [ ] quota·billing·reset을 별도 사실로 관리했다.
- [ ] no-event와 실패를 0으로 바꾸지 않았다.

