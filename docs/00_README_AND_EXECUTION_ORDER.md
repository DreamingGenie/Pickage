# Journey Reliability Evidence Resolution Pack

> 기준일: 2026-08-23 KST · 일요일(`END` service day)
> 목적: 이미 확정된 기획 정책은 유지하면서, 하루의 API 예산으로 해소 가능한 미확정 요소를 최대한 실제 evidence로 판정한다.
> 범위: 실험 실행·evidence 정리·기획 문서 고도화. 애플리케이션 개발·배포·인프라 구현은 제외한다.

> **2026-08-23 정정:** 이 Pack의 초판(00~06)은 "Kakao publictraffic/WALK"를 실제 provider로
> 전제했으나, 이는 이 프로젝트에 존재한 적 없는 provider다. `docs/history/transit_journey_handoff_FINAL_v3/docs/05_DECISION_LOG.md`
> (D-013·D-019·D-024·D-042~D-050)에 따르면 실제 provider는 다음과 같다.
>
> - **Mixed route(버스+지하철 혼합경로)** = 서울시 data.go.kr `getPathInfoByBusNSub` 서비스
>   (15000414). `DATA_GO_BUS_API_KEY`로 호출하며, 이 키는 Bus Arrival·Position·Route-master·
>   Station-master와 **동일 계정 공용 키**다(D-013 byte-identical 확인, D-046 PM 통합 결정).
>   따라서 mixed-route 호출은 별도 예산이 아니라 **Bus 계열과 같은 쿼터를 공유**한다.
> - **Kakao Mobility 도보 길찾기 API는 BLOCKED**다 — 제휴 계약이 필요한 partner-only
>   API로, 실제 키 호출 결과 `HTTP 403 permission denied`(D-043). 오늘 실험 대상에서 제외한다.
> - **WALK(도보 access/final leg)의 실제 provider는 TMAP(SK Open API) 보행자 경로**다
>   (`TMAP_APP_KEY`, D-045 VERIFIED/GO). "TMAP 대중교통(길찾기)" 상품은 이 프로젝트에서
>   구독·검증된 적이 없으므로 오늘 사용하지 않는다.
>
> 아래 본문은 이 정정을 반영해 다시 쓴 버전이다. "Kakao"가 아니라 **Mixed-route(Seoul
> data.go.kr) + TMAP walk**를 기준으로 읽는다.

## 1. 입력 파일

반드시 같은 작업공간에서 다음을 제공한다.

- `SERVICE_PLAN_260822.md`
- `IA_SCREEN_SPEC_260822.md`
- `REQUIREMENTS_SPEC_260822.md`
- 이 Pack의 `01~07` 문서
- `docs/history/transit_journey_handoff_FINAL_v3/docs/05_DECISION_LOG.md` (D-013~D-050,
  provider 확정 근거 — 이 문서 없이 "Kakao"를 다시 가정하지 않는다)
- `docs/history/transit_journey_handoff_FINAL_v3/docs/01_PROJECT_HANDOFF.md` §6~7
  (API/데이터 레지스트리, credential 상태)
- 기존 raw evidence: `docs/history/transit_journey_handoff_FINAL_v3/data/samples/**`
  (bus/subway/mixed-route/tmap 실제 응답 샘플)
- 가능하면 data.go.kr(서비스 15000314/15000332/15000414)와 서울 열린데이터광장(지하철
  realtime) 마이페이지의 승인 한도/사용량 캡처 2개 이상

data.go.kr 공용 키(`DATA_GO_BUS_API_KEY`, Bus Arrival+Position+Mixed-route+Route-master+
Station-master 공유)와 지하철 realtime 키(`SEOUL_SUBWAY_REALTIME_KEY`)의 **승인 일일
한도·remaining은 아직 포털에서 확인되지 않았다** — `02_API_BUDGET_AND_DAY_SCHEDULE.md`의
ledger를 채우기 전에는 sustained 수집을 시작하지 않는다.

초과 billing·결제수단·정확한 reset 시각도 포털 화면만으로 확정하지 않는다.

## 2. 실행 순서

1. `01_UNCERTAINTY_RESOLUTION_MATRIX.md`에서 오늘 해소할 항목과 불가능한 항목을 구분한다.
2. `02_API_BUDGET_AND_DAY_SCHEDULE.md`에 각 credential의 실제 remaining을 입력하고 예산을 잠근다.
3. `03_SEOUL_MIXED_ROUTE_AND_WALK_RUNBOOK.md`를 실행한다.
4. `04_SEOUL_BUS_SUBWAY_RUNBOOK.md`를 시간대별로 실행한다.
5. 모든 run마다 `05_EVIDENCE_RECORD_AND_DECISION_RULES.md` 템플릿을 채운다.
6. 실험 종료 후 `06_PLANNING_UPGRADE_MASTER_PROMPT.md`를 Agent에 입력한다.
7. 다른 Agent로 `07_INDEPENDENT_PLANNING_QA_PROMPT.md`를 수행한다.

## 3. 허용·금지 경계

허용:

- 기존 probe/collector 실행
- API 호출 예산 안의 evidence 수집
- sanitized JSON/CSV/log/hash/manifest/Markdown evidence 생성
- `jq`, `rg`, `diff`, `sha256sum` 등 분석 명령
- 기획 문서 3개 수정

금지:

- 애플리케이션 기능 구현
- Java/Python/JavaScript production code 추가·수정
- collector/adapter 신규 개발 (기존 `mixed_route_spike.py` 등 encoding 버그 등도 여기서
  수정하지 않는다 — 발견 사실만 evidence에 기록하고 별도 후속 작업으로 남긴다)
- DB migration, Docker, CI/CD, Terraform, 배포 변경
- secret 출력·파일 저장·commit
- key rotation 또는 여러 key로 quota 우회
- quota exhaustion을 확인하기 위한 고의 소진
- 임의 확률분포·placeholder·SLA·support threshold 생성
- BLOCKED로 확인된 Kakao Mobility 도보 API를 오늘 실험에 다시 포함하는 것

필요한 실험이 기존 도구로 불가능하면 개발하지 말고 `BLOCKED_TOOLING`으로 남긴다.

## 4. 하루 종료 시 기대 결과

- data.go.kr 공용 키(Bus+Mixed-route)와 지하철 realtime 키의 승인 한도/사용량 상태 확정
- Mixed-route raw schema(이미 확인된 `routeId/fid/fx/fy/tid/tx/ty` 등 provider ID 존재 여부) 재확인
- mixed-route total/step time gap의 범위를 좁힌 판정
- Demo corridor(삼청동↔역삼역) candidate 반복 안정성 판정
- Route A(01A 춘추문→안국)와 mixed-route 후보의 구조 차이 확정
- Route A corridor의 canonical crosswalk 상태 재확인(D-047 기존 결과의 corridor 확장 가능/불가능 판정)
- Bus Prediction→Actual→Residual builder의 실제 event 기준 판정
- Bus WAIT snapshot과 passenger-relevant event unit 구분 재검증
- Subway station×line identity와 Actual interval builder 재검증(D-048에서 0건이었던 실제
  도착 event를 더 긴 window로 재시도)
- quota·latency·out-of-order 관측값 확보
- 아직 하루로 확정할 수 없는 claim의 범위와 다음 Gate 명확화

## 5. 종료 원칙

모든 성공은 `provider×endpoint×OD/corridor×window×service day×adapter version` 범위로만 기록한다. 전역 지원·성숙한 분포·end-to-end calibration·SLA로 일반화하지 않는다.
