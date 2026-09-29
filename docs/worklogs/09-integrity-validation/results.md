# 수행 결과

2026-09-12, 9번 **사전 구현 범위 완료**. 합성 데이터의 24개 검사 항목이 PASS이며,
신규 테스트 30개가 실패·오류·skip 없이 통과했다. 전체 원천/DB 정합성 및 성능 검증은 미실행이다.

## 변경한 내용

- `pipeline/integrity_validation/`: 합성 입력 계약, 19개 의미 검증 SQL과 5개 행 수 검사,
  작은 정답 데이터, CLI, JSON/Markdown 보고서, PostgreSQL catalog/조회 계획 SQL, 테스트.
- `docs/worklogs/09-integrity-validation/`: 범위·계획·실제 이슈·결과·검증 증거.
- 실행 결과는 [보고서](../../../data/integrity-demo-01/report.md),
  [JSON](../../../data/integrity-demo-01/report.json),
  [검증 SQL](../../../data/integrity-demo-01/integrity_checks.sql)에 있다.

## 실제 검증

| 항목 | 측정 결과 |
| --- | --- |
| 정상 fixture | 24개 검사 PASS, 위반 0 |
| 신규 테스트 전체 | 30개, 실패 0, 오류 0, skip 0; 약 5.9초 |
| Python AST·공백 | Python 10개 parse 성공, 후행 공백 문제 0 |
| CLI | 보고서 6개 생성, 잘못된 값은 종료 코드 1, SQL 오류는 ERROR |
| 기존 출력 재시도 | 종료 코드 2, 이전 보고서 바이트 보존 |
| DuckDB 자원 | 메모리 실행, threads 1, 128 MB, 디스크 spill 0 B |
| PostgreSQL·Docker·원격 원천 | 접속/실행 없음 |
| Jira·commit·push | 사용자 요청에 따라 Jira 연결 보류, commit/push 미실행 |

근거: [테스트 전체 로그](evidence/tests.txt), [검증 기록과 파일 SHA](evidence/verification.json).
별도 lint 도구 ruff는 설치되어 있지 않아 새 의존성 설치 없이 AST·공백 검사로 확인했다.
별도 타입 검사기는 실행하지 않았다. PostgreSQL 구문·실행계획·성능 성공으로 해석하지 않는다.

독립 검토에서도 30개 테스트와 CLI를 재실행했으며 이번 사전 구현 범위의 차단 결함은
발견하지 않았다. 다만 입력 target·PVS·edge와 기대 행 수를 모두 일관되게 줄이면 합성
대조는 통과할 수 있다. 이는 공급받은 근거끼리의 일관성을 확인하는 도구의 증명 범위이며,
실제 모집단 완전성은 승인된 독립 native manifest 연결 단계에서 검증해야 한다.
전체 target이 빈 입력도 같은 한계를 가진다. 이 WATCH 항목을 전체 원천 검증 완료로 바꾸지 않는다.

## 작은 정답 데이터의 의미

target은 alpha·gamma의 해당 날짜 유효 버전이고 beta는 source 전용이다.
source의 beta 1.0.0과 beta 1.1.0은 서로 다른 참조 주체로 센다.

| 날짜 | target | 직접 count |
| --- | --- | ---: |
| 2026-01-01 | alpha 1.0.0 | 2 |
| 2026-01-01 | gamma 1.0.0 | 1 |
| 2026-02-01 | alpha 1.0.0 | 3 |
| 2026-02-01 | alpha 1.1.0 | 1 |
| 2026-02-01 | gamma 1.0.0 | 2 |
| 2026-02-01 | gamma 1.1.0 | 0 |

중복 edge를 두 번 세거나, source를 대표 버전으로 줄이거나, 직접 관계를 all-depth로 세면
위 값이 달라진다. 두 값의 합은 같게 두고 각 target의 count만 교환해도 오류를 검출했다.
1월의 계산 COMPLETE·해석 PARTIAL 상태는 그대로 남으며, 이 fixture의 PASS로 게시 승인하지 않는다.

## 진행 중 발견한 이슈와 해결

1. 최초 SQL 초안의 직접 count 검사가 실제 PVS 값과 연결되지 않았다.
   target별 source 복합 식별자 DISTINCT 집계와 PVS 값을 비교하도록 수정하고 잘못된 count 테스트로 검증했다.
2. 최초 정답 데이터의 target 집합과 PVS/edge 대상이 달랐다.
   source 전용 beta와 저장 target alpha·gamma를 구분하고 독립 정답을 다시 대조했다.
3. 초기 테스트가 설치되지 않은 pytest를 사용했다. 저장소의 기존 unittest 방식으로 바꾸고 실제 실행했다.
4. PARTIAL 원천은 미해석 선언이 0이어도 source 품질 누락 때문에 발생할 수 있다.
   기존 `historical_production_quality.py` 계약에 맞춰 상태를 그대로 보존하고 자동 COMPLETE 승격을 막았다.
5. 최종 보호 검사 중 다른 작업이 8번 성능 실험 완료 기록을 갱신했다.
   기존 623개 파일 중 621개는 같은 SHA이며, 달라진 두 파일은 원래 worktree의
   `docs/worklogs/S15P21A506-193/04-work-log.md`와 `36-db-insert-benchmark.md`다.
   두 파일 끝에서 16:00 KST 실험 완료 기록이 추가된 것을 확인했다. 이번 작업에서는 원래
   코드/문서를 쓰지 않았고, 원래 브랜치·HEAD·인덱스 해시는 모두 동일하다.

## 후속 작업

1. Jira 티켓을 만들고 현재 임시 로컬 브랜치와 연결한다.
2. 8번 적재 방식과 입력 계약이 확정된 후 native run validator를 재사용해 승인 근거를 연결한다.
3. 별도 검증 환경에서 실제 schema·manifest 건수·모집단·지표 값을 대조한다.
4. 실제 loader의 실패·rollback·중단/재개·동시 재시도를 검증한다.
5. 대표 API 조회를 데이터 규모·cache·인덱스 조건을 고정해 실측한다.

이 후속 작업은 이번 사전 구현의 통과 결과로 완료 처리하지 않았다.
