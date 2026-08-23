# Journey Reliability Evidence Resolution Pack

> 기준일: 2026-08-23 KST · 일요일(`END` service day)  
> 목적: 이미 확정된 기획 정책은 유지하면서, 하루의 API 예산으로 해소 가능한 미확정 요소를 최대한 실제 evidence로 판정한다.  
> 범위: 실험 실행·evidence 정리·기획 문서 고도화. 애플리케이션 개발·배포·인프라 구현은 제외한다.

## 1. 입력 파일

반드시 같은 작업공간에서 다음을 제공한다.

- `SERVICE_PLAN_260822.md`
- `IA_SCREEN_SPEC_260822.md`
- `REQUIREMENTS_SPEC_260822.md`
- `kakao_map_publictraffic_20260822T100523Z.json`
- `kakao_map_walk_20260822T100523Z.json`
- 이 Pack의 `01~07` 문서
- 가능하면 Kakao quota console 캡처 2개
- 기존 handoff/evidence package가 있으면 원래 경로를 보존

Kakao console에서 사용자 확인된 값은 다음과 같다.

- publictraffic: 사용 1, limit 1,000/day
- WALK: 사용 1, limit 1,000/day
- 두 endpoint는 별도 항목으로 집계

초과 billing·결제수단·정확한 reset 시각은 이 화면만으로 확정하지 않는다.

## 2. 실행 순서

1. `01_UNCERTAINTY_RESOLUTION_MATRIX.md`에서 오늘 해소할 항목과 불가능한 항목을 구분한다.
2. `02_API_BUDGET_AND_DAY_SCHEDULE.md`에 각 credential의 실제 remaining을 입력하고 예산을 잠근다.
3. `03_KAKAO_ROUTE_WALK_RUNBOOK.md`를 실행한다.
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
- collector/adapter 신규 개발
- DB migration, Docker, CI/CD, Terraform, 배포 변경
- secret 출력·파일 저장·commit
- key rotation 또는 여러 key로 quota 우회
- quota exhaustion을 확인하기 위한 고의적 소진
- 임의 확률분포·placeholder·SLA·support threshold 생성

필요한 실험이 기존 도구로 불가능하면 개발하지 말고 `BLOCKED_TOOLING`으로 남긴다.

## 4. 하루 종료 시 기대 결과

- Kakao endpoint별 프로젝트 limit 상태 확정
- Kakao raw schema와 provider ID 부재 확정
- publictraffic total/step gap의 범위를 좁힌 판정
- 테스트 OD별 candidate 반복 안정성 판정
- Route A와 Kakao 후보의 구조 차이 확정
- Route A corridor의 canonical crosswalk 가능/불가능 판정
- Bus Prediction→Actual→Residual builder의 실제 event 기준 판정
- Bus WAIT snapshot과 passenger-relevant event unit 구분 재검증
- Subway station×line identity와 Actual interval builder 재검증
- quota·latency·out-of-order 관측값 확보
- 아직 하루로 확정할 수 없는 claim의 범위와 다음 Gate 명확화

## 5. 종료 원칙

모든 성공은 `provider×endpoint×OD/corridor×window×service day×adapter version` 범위로만 기록한다. 전역 지원·성숙한 분포·end-to-end calibration·SLA로 일반화하지 않는다.

