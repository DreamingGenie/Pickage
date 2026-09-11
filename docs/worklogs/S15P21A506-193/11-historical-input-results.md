# 11. 과거 스냅샷 입력 준비와 대상 규모

## 변경 범위와 작업 계획

2026-09-10 사용자가 직전 안내의 입력 준비 작업 진행을 요청했다. 이번 범위는 H1의 원본·calendar 고정, source/target 버전별 최초 포함 스냅샷, 0을 포함할 수 있는 전체 대상 키 수 산출이다. 최신 관측 자료로 과거 계산을 준비하는 의미를 적용하며, PARTIAL 서비스 게시 정책을 채택하거나 실제 DB에 쓰는 작업은 포함하지 않는다.

- `pipeline/version_dependents/historical_input.py`와 전용 테스트를 추가한다. 기존 7번 resolver와 기존 8번 집계/진단 코드는 보존한다.
- 7번 실행의 원본 input manifest를 SHA로 고정한 뒤 현재 main workspace의 Curated package/version 및 raw requirements/versions_full을 읽기 전용 검증한다. 원격 승인 상태를 새로 조회하거나 recovery candidate를 정상 게시 manifest로 승격하지 않는다.
- 229개 정확한 UTC 시각을 연결하고 배포일 NULL을 제외한다. source는 모든 대상 release 버전을 유지하고 target은 기존 npm worker의 valid stable semver 판정을 재사용한다.
- source/target population, 기준일별 source/target 수, 제외 수와 입력 계보를 새 로컬 실행 경로에 저장한다. 버전×229 전체 행이나 날짜별 edge는 만들지 않는다.
- requirements 원본·고유 키·관측 시각과 source별 선언 수/오류 상태까지 확인한다. 2.89억 선언 전개와 고유 요구조건별 해석 구간은 후속 집계 구현 단계에서 준비한다.
- 합성 데이터로 정확한 배포 시각 경계, source 전체 버전, target semver 제외, 키 중복·출처 불일치, manifest 손상·출력 수명주기를 검증한 후 실제 입력 준비를 실행한다.

## 실행 자원과 완료 조건

기존 Python/DuckDB와 설치된 Node/npm 모듈만 사용한다. 초기 DuckDB 8 threads/8GB, Node 768MB heap을 사용한다. 새 실행 디렉터리의 중간 DB·scratch·산출물만 기록한다. 실제 실행 전 디스크 가용량을 확인하고 임시 파일은 지정 상한 안에서 사용한다.

완료 조건은 원본 파일·schema·시각·ID 연결 검증, 전체 source와 stable target 최초 포함 시점 생성, 229개 날짜별 대상 수 및 전체 dense 키 수 산출, 출력 SHA·행 수와 보존식의 독립 검증이다. 이는 dependents_count 계산 완료나 DB 적재 완료를 뜻하지 않는다.

## 실제 결과

**v2 입력 준비와 별도 파일 검증이 완료됐다.** 입력 준비는 2026-09-10 20:56:09 KST에
exit 0으로 끝났고, 자동 후속 검증은 20:56:24 KST에 완료됐다. 입력 준비 소요시간은
861.125초(약 14분 21초)다. 후속 검증은 준비 종료 약 15초 후 끝났으며 이 차이에는
후속 프로세스의 대기 간격도 포함되므로 순수 검증 시간으로 해석하지 않는다.

| 항목 | 실제 값 |
| --- | ---: |
| 기준일 수 | 229 |
| 기간 | 2022-05-08~2026-08-31 |
| 원본 Curated 버전 수 | 54,188,349 |
| 배포일 NULL로 제외 | 7,015,400 |
| 마지막 기준일 이후 배포로 제외 | 0 |
| 최신 기준일의 source 버전 | 47,172,949 |
| 최신 기준일의 유효 target 버전 | 47,172,771 |
| 유효 source 중 invalid semver로 target에서 제외 | 178 |
| 유효 source 중 prerelease로 target에서 제외 | 0 |
| 최신 source의 일반 선언 수 | 289,214,123 |
| 고유 원문 버전 문자열 수 | 844,355 |
| 전체 날짜의 target 키 수 합 | **6,971,338,953** |

첫 날짜의 source는 18,341,585개, target은 18,341,407개다. 모든 날짜의 유효 target에 대해
`(package_id, version, snapshot_at)` 행을 물리적으로 저장하면 약 **69.7억 키**가 필요하다.
이는 0을 포함할 전체 대상 수이며, 양수 count 수나 이미 DB에 적재한 행 수가 아니다.
69.7억 행을 실제로 펼쳐 저장하지 않았고 버전별 birth index와 날짜별 대상 수로 계산했다.

위 prerelease 제외 0은 **이번 Curated 기반 source 모집단에서 관측한 수**다. 전체 raw의
prerelease 수가 0이라는 의미나 prerelease 해석 정책이 개선됐다는 의미가 아니다.

| 출력 파일 | 행 수 | 크기(bytes) |
| --- | ---: | ---: |
| calendar.parquet | 229 | 4,938 |
| source_population.parquet | 47,172,949 | 1,712,119,540 |
| target_population.parquet | 47,172,771 | 917,893,768 |
| snapshot_population.parquet | 229 | 9,051 |
| semver_classification.parquet | 844,355 | 4,368,948 |

Parquet 5개 합계는 2,634,396,245 bytes(약 2.63GB)다. 작업 중간 DB/JSONL 등은 별도로
보존되어 있으며 위 산출물 합계에 포함하지 않는다. 이번 결과는 `count_status=NOT_COMPUTED`,
`ready_for_load=false`다. 실제 날짜별 dependents_count 해석·집계와 DB 적재는 남아 있다.

- [계산 실행 영수증](evidence/historical-input-run.json)
- [자동 후속 검증 결과](evidence/historical-input-postcheck.json): `COMPLETE`.
  229개 날짜의 대상 수를 독립 birth histogram으로 대조했다. 날짜별 수치도 저장되어 있다.
- 출력: `data/version-dependents/historical-inputs/observed=2026-08-31/run_id=population-20260831-v2`.
- 후속 실행 스크립트: `data/version-dependents/historical-inputs/finish_population_v2.py`.

결과 확인 요청 때 최초 반환 SHA와 현재 manifest SHA
`572c5585bfdbec0b2b9ca1fd0bbf53b9241f4b742d36963120cb78c628a66762`의 일치, 출력 파일 존재·크기,
두 영수증과 manifest의 통계 일치, 229개 날짜 합계와 모집단 보존식을 다시 확인했다.
별도 agent의 작은 JSON 대조도 PASS다. 대규모 계산·전수 파일 검증을 다시 실행하지 않았다.

## 구현과 검증 기록

- 입력 준비 API와 CLI, 별도 `verify_historical_inputs`를 구현했다. 원본 입력 계약 및 기존
  npm worker를 재사용하며 7번 코드를 변경하지 않았다.
- 합성 데이터의 source 전체 버전·prerelease/invalid target 제외·정확한 UTC 배포 경계와
  불규칙 3개 날짜, `Asia/Seoul` 세션에서도 동일한 epoch·birth index를 검증했다.
- 실제와 같은 4종 Parquet schema로 pin·파일 저장/재검증·손상·누락·실패 재시도를 시험했다.
- 기존 집계/진단을 포함한 **80개 테스트 통과, 28.641초**, Python AST 12개 통과.
  [검증 기록](evidence/historical-input-validation.json), [테스트 로그](evidence/historical-input-tests.log).
- [독립 검토](evidence/historical-input-review.md)는 보완 후 PASS다. 실제 대상 규모/성능 검증을
  대체하지 않는다. v1은 검토 보완을 위해 중단했고 v2는 새 디렉터리에서 완료됐다.
