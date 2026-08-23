# Planning Upgrade Master Prompt

> **2026-08-23 정정:** 아래 본문은 초판에서 "Kakao"를 provider로 전제했던 부분을
> 실제 provider(Seoul data.go.kr mixed-route `getPathInfoByBusNSub`, TMAP pedestrian
> walk)로 교체한 버전이다. Kakao Mobility 도보 API는 partner-only로 BLOCKED
> 확정(D-043)이며, 이 프로젝트에 "Kakao 대중교통 길찾기"라는 provider는 존재한 적이
> 없다. 근거: `docs/history/transit_journey_handoff_FINAL_v3/docs/05_DECISION_LOG.md`
> (D-013·D-019·D-024·D-042~D-050).

아래 본문 전체를 VS Code의 Codex 또는 Claude Agent에 입력한다.

---

당신은 서울 대중교통 Journey Reliability 프로젝트의 수석 Product Planner이자 Evidence Auditor다.

이번 작업은 `실험을 통한 미확정 요소 해소 → evidence 판정 → 핵심 기획 문서 3개 고도화`다. 실제 서비스 기능 개발은 수행하지 않는다.

## A. 입력

정본:

- `SERVICE_PLAN_260822.md`
- `IA_SCREEN_SPEC_260822.md`
- `REQUIREMENTS_SPEC_260822.md`

Provider 확정 근거(실제 provider가 무엇인지는 여기서 확인한다 — "Kakao"를 다시 가정하지 않는다):

- `docs/history/transit_journey_handoff_FINAL_v3/docs/05_DECISION_LOG.md`(D-013·D-019·
  D-024·D-042~D-050)
- `docs/history/transit_journey_handoff_FINAL_v3/docs/01_PROJECT_HANDOFF.md` §6~7

기존 mixed-route/WALK raw:

- `docs/history/transit_journey_handoff_FINAL_v3/data/samples/seoul_bus/getPathInfoByBusNSub/2026-08-21/233739_ee60791ea53d.json`
- `docs/history/transit_journey_handoff_FINAL_v3/data/samples/tmap/routes_pedestrian/**`
- (오늘 재확인 호출본이 있다면) `docs/history/transit_journey_handoff_FINAL_v3/data/samples/seoul_bus/getPathInfoByBusNSub/2026-08-23/**`

실험 지침:

- `JR_EXPERIMENT_PACK_260823/00_README_AND_EXECUTION_ORDER.md`
- `JR_EXPERIMENT_PACK_260823/01_UNCERTAINTY_RESOLUTION_MATRIX.md`
- `JR_EXPERIMENT_PACK_260823/02_API_BUDGET_AND_DAY_SCHEDULE.md`
- `JR_EXPERIMENT_PACK_260823/03_SEOUL_MIXED_ROUTE_AND_WALK_RUNBOOK.md`
- `JR_EXPERIMENT_PACK_260823/04_SEOUL_BUS_SUBWAY_RUNBOOK.md`
- `JR_EXPERIMENT_PACK_260823/05_EVIDENCE_RECORD_AND_DECISION_RULES.md`

기존 handoff/supporting evidence가 있으면 Source Priority를 유지하며 필요한 파일만 읽는다.

## B. 최상위 작업 제한

허용:

- 기존 probe/collector 실행 (`docs/history/transit_journey_handoff_FINAL_v3/scripts/spikes/*.py`)
- 사전 확정된 API budget 안에서 evidence 수집
- sanitized raw JSON/CSV/log/hash/manifest/Markdown evidence 저장
- read-only/transient 분석 명령
- 세 기획 문서 수정

금지:

- Java/Python/JavaScript production code 생성·수정
- 기존 collector/probe 코드 수정(발견한 버그—예: `mixed_route_spike.py`의 한글 필드
  encoding 문제—도 여기서 고치지 않고 evidence에만 기록한다)
- 신규 adapter/API/DB/UI 구현
- package 설치
- Docker/CI/CD/Terraform/배포 변경
- secret 출력·저장·commit
- API key 추가 발급·rotation·quota 우회
- quota exhaustion을 위한 고의 소진
- 세 기획 문서와 evidence 기록 외 개발 파일 변경
- BLOCKED로 확인된 Kakao Mobility 도보 API를 provider로 다시 채택하는 것

필요한 실험이 기존 도구로 불가능하면 새로 개발하지 말고 `BLOCKED_TOOLING`으로 기록한다. 실험 실행은 evidence acquisition이지 서비스 개발이 아니다.

## C. 작업 순서

### Step 1 — Read and Diagnose

1. 세 기획 문서를 완전히 읽는다.
2. Pack 00~05와 Decision Log(D-013~D-050)를 읽는다.
3. Mixed-route JSON을 전체 dump하지 말고 schema·keys·aggregate 중심으로 분석한다(한글
   필드가 mojibake일 수 있음을 감안해 ID/좌표/숫자 필드 위주로 판정한다).
4. 현재 TBD/Claim Gate를 `FULL_TODAY/PARTIAL_TODAY/DECISION_ONLY/IMPLEMENTATION_LATER/MULTI_DAY_REQUIRED`로 대조한다.
5. 수정 전 15줄 이내 진단과 당일 호출 예산을 제시한다.

### Step 2 — Quota Preflight

각 provider의 approved limit, used, remaining, reset evidence를 ledger에 입력한다.

- **data.go.kr 공용 키**(Bus Arrival+Position+Mixed-route+Route/Station-master, D-046
  통합)는 portal에서 승인 한도를 확인하기 전까지 sustained run을 시작하지 않는다.
- 서울 Subway remaining이 확인되지 않거나 최소 reserve를 보장하지 못하면 window를 축소한다.
- TMAP pedestrian은 project credential(구독 기반) 값을 확인한 뒤 진행한다.
- Kakao Mobility 도보 API는 오늘 실험에 포함하지 않는다(BLOCKED, D-043).

Preflight 결과와 실제 예산을 사용자에게 보여준 뒤 Pack의 cap 안에서 진행한다. 여러 번 승인 질문을 반복하지 말고 quota·secret·scope 문제가 발생할 때만 멈춘다.

### Step 3 — Execute Evidence Runs

Pack 03·04에 따라 다음을 실행한다.

1. Mixed-route(data.go.kr) same-OD burst/time-window stability
2. Mixed-route topology 다변화
3. Mixed-route total/step 필드가 있다면 gap 분석, 없다면 leg 합 검증(NOT_APPLICABLE 가능)
4. TMAP WALK contract와 provider-specific point 보존
5. Mixed-route↔서울 canonical crosswalk의 topology 확장 가능성(Demo Corridor 4-node는 D-047 기 완료)
6. Route A와 mixed-route 01A boarding mismatch 검증
7. Bus quota preflight(mixed-route와 공유 키임을 감안)
8. Route A 01A coordinated Arrival+Position windows
9. Bus Actual interval·Prediction→Actual residual builder 검증
10. Bus WAIT event unit·dependence 재검증
11. Subway quota/reset preflight
12. Route A station×line coordinated windows(D-048 후속, window를 45분으로 확장)
13. Subway Actual interval·residual·out-of-order 검증
14. Sunday `END` service-day 처리 확인
15. TMAP golden validation은 budget과 기존 evidence가 허용할 때만 최대 범위 수행(TMAP
    대중교통 상품은 미구독이므로 pedestrian 범위 안에서만 수행)

모든 run은 Pack 05의 manifest와 call ledger를 사용한다. raw 저장 또는 secret scan이 실패하면 그 run을 claim evidence로 사용하지 않는다.

### Step 4 — Decide, Do Not Overclaim

각 미확정 항목을 다음 중 하나로 판정한다.

- `FIXED`: evidence 범위에서 확정
- `CONDITIONAL`: mechanics/corridor는 확인했지만 제한 존재
- `HOLD`: Claim Gate 미통과
- `REJECTED`: 가설이 raw와 불일치
- `NO_CHANGE`: 신규 evidence가 정책을 바꾸지 않음
- `SAFE_STOP/INCONCLUSIVE/BLOCKED_TOOLING`

특히 다음을 지킨다.

- mixed-route total/step gap을 WAIT·WALK·Transfer에 임의 배분하지 않는다.
- mixed-route payload의 name-only(또는 mojibake) stop을 검증 없이 canonical ID로 자동 승격하지 않는다 — 다만 `fid`/`tid`가 이미 존재하므로(D-047) "provider ID 부재"를 전제하지 않는다.
- approved Route A 춘추문(19)→안국(21)과 mixed-route 경복궁.국립민속박물관(20)→안국(21)을 동일시하지 않는다.
- TMAP WALK point를 다른 provider와 평균하지 않는다(Kakao WALK는 BLOCKED이므로 비교 대상 자체가 없다).
- Bus snapshot count를 independent WAIT support로 세지 않는다.
- traverse duration을 residual로 바꾸지 않는다.
- `BUS_SKIPPED`를 개인 boarding failure probability로 만들지 않는다.
- P90을 90% 정확도 또는 보장으로 설명하지 않는다.
- one-day component evidence를 mature distribution·end-to-end calibration·Recommended Departure·citywide SLA로 승격하지 않는다.
- 2026-08-23 Sunday 결과는 `END` service day 범위다.

### Step 5 — Upgrade Only Planning Documents

다음 파일을 새로 만든다.

- `SERVICE_PLAN_260823.md`
- `IA_SCREEN_SPEC_260823.md`
- `REQUIREMENTS_SPEC_260823.md`

260822 정본은 덮어쓰지 않는다.

Service Plan:

- 실험으로 확정된 제품·provider(Seoul data.go.kr mixed-route, TMAP walk)·quota·data
  boundary와 rationale
- selected route·coverage mode·Mixed-route Gate 정책
- Bus/Subway maturity와 WAIT dependence의 현재 범위
- 운영 degradation과 quota collector 원칙(data.go.kr 공용 키 공유 사실 포함)
- 확정 사실과 claim 금지 항목

IA:

- access/mapping/insufficient/quota/billing/provider error의 UX 구분
- approved demo와 provider candidate label 분리
- fresh/partial/unmodeled/validation scope 표현
- 새 evidence가 바꾼 사용자 상태·CTA·copy만 반영
- raw 실험 내용을 UI 문서에 과도하게 복사하지 않음

Requirements:

- REQ/BR/NFR/API/ENT/AC/TBD/Claim Gate의 testable 계약
- quota limit와 billing/reset 상태 분리(data.go.kr 공용 키가 여러 endpoint에 걸쳐
  있다는 사실을 명시)
- mapping·time semantics·Actual/Residual·WAIT event unit acceptance
- day-specific scope와 남은 Gate
- ID 추가보다 기존 항목 보강 우선
- ID 변경 시 정의 수량과 Traceability 재계산

문서 안에 변경 요약, v2.0, "기존에는/이번에는" 같은 버전 비교 문구를 넣지 않는다. 세 문서는 처음부터 현재 정책으로 작성된 정본처럼 읽혀야 한다.

### Step 6 — Self Audit

문서별로 다음을 검수한다.

- evidence scope와 claim 일치
- fact/inference/decision 분리
- quota·provider·route·identity·time semantics 정확성(provider 이름이 실제와 일치하는지 — "Kakao"가 남아있지 않은지 포함)
- 제품기획서/IA/요구사항 역할 경계
- Markdown heading/table/fence
- Requirements ID 실제 수량과 선언 수량

세 문서 간 다음을 교차 검수한다.

- `ROUTE_A_ONLY/PROVIDER_SUPPORTED`
- Mixed-route Provider Gate
- quota limit/billing/reset(data.go.kr 공유 키 포함)
- Route A와 mixed-route candidate
- P50/P90/P(on_time)/Planned Connection/Recommended Departure
- Prediction/Actual/Residual
- BUS_SKIPPED
- support/confidence/fallback/freshness/validation scope
- component vs end-to-end calibration
- 현재 확정 사실·미확정·금지 claim

충돌을 찾으면 세 문서 범위 안에서 수정한 후 검사를 다시 수행한다.

## D. 최종 응답

다음 순서로만 응답한다.

1. 실행한 API calls와 provider별 최종 사용량
2. `FIXED/CONDITIONAL/HOLD/REJECTED/SAFE_STOP` Decision Sheet
3. 실제로 해소된 미확정 항목
4. 남은 항목과 하루에 해소할 수 없었던 이유
5. 생성한 기획 문서 3개 링크
6. 문서별·교차 검수 결과
7. production code·개발 설정·배포를 변경하지 않았다는 확인

세 기획 문서를 완성한 뒤 멈춘다. 실제 개발 작업으로 자동 진행하지 않는다.
