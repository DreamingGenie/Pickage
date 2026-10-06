# 7번 작업 결과 보기

아래 표는 전체 실행 전 사용자에게 보여준 검증 결과다. 이후 실제 전체 계산이 완료됐으며, 최종 상태와 실제 데이터 결과는 [05 전체 실행 기록](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/docs/worklogs/S15P21A506-283/05-full-run.md)에서 확인한다.

이 문서는 실제 저장된 검증 기록과 Parquet를 사람이 읽기 쉬운 표로 정리한 것이다. 이 문서는 전체 계산 전 preview이며, 실제 전체 계산 결과는 [06 계산 결과](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/docs/worklogs/S15P21A506-283/06-computation-results.md)에 기록했다.

확정 정책은 일반 dependencies만 계산, 배포일 NULL 제외, 미해석 PARTIAL 보존이다. [정책 결정 기록](03-policy-decision.md). 이 문서는 전체 계산 전 시점의 preview이며, 실제 전체 결과는 [06 계산 결과](06-computation-results.md)에 기록했다.

## 1. 실제 데이터의 입력 검증

승인 manifest에 적힌 파일과 로컬 파일의 목록·SHA256·바이트·스키마·행 수를 대조했다. 원본의 정확한 snapshot 시각 일치도 검사했다.

| 데이터 | 검증한 파일 수 | 확인한 행 수 |
| --- | ---: | ---: |
| 패키지 목록 | 4 | 11,080,940 |
| Curated 버전 목록 | 20 | 54,188,349 |
| 원본 전체 버전 | 362 | 78,559,731 |
| 원본 의존성 선언 목록 | 790 | 78,559,731 |
| 합계 | 1,176 | 데이터 종류가 다르므로 행 수를 합산하지 않음 |

Curated 버전 54,188,349개는 NULL 제외 전 입력 행 수다. 확정 정책을 적용한 source 수와 최종 관계 수는 아직 계산하지 않았다.

정확한 기준시각: `2026-08-31T21:01:10.517131Z`. 기존 전체 파일 검증은 68.843초에 통과했다. [입력 검증 원본 JSON](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/data/requirements-resolution/preflight-20260909/input-manifest.json).

## 2. 실제 생성된 테스트 데이터

합성 데이터 run `integration-dbf68cf2`의 저장된 Parquet 4개를 다시 읽고 파일 해시와 행 수를 재검증했다. 아래는 새로 만든 예시가 아니라 해당 파일에 들어 있는 행이다. `a`는 테스트용 이름이며 실제 npm 패키지의 분석 결과가 아니다.

### 원본 선언을 해석한 결과

| 의존성을 선언한 버전 | 종류 | 요구한 패키지 | 요구 조건 | 선택된 버전 | 상태 |
| --- | --- | --- | --- | --- | --- |
| a@1.0.0 | dependencies | a | `^1` | a@1.0.0 | RESOLVED |

이 테스트는 연결 과정을 검증하기 위해 자기 자신을 요구하도록 구성했다. semver로 정규화된 조건은 `>=1.0.0 <2.0.0-0`이다. 정상적으로 해석한 선언과 특정 target 버전이 별도 필드로 보존된다.

### source 버전별 처리 결과

| 버전 | 일반 선언 수 | 해석 성공 | 미해석 | 제외한 peer | 제외한 optional | 배포일 누락 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| a@1.0.0 | 1 | 1 | 0 | 1 | 0 | 없음 |

requirements 입력 행은 존재하고 배열도 NULL이 아니며, source 상태는 `RESOLVED`다. peer 선언 1개가 계산에서 제외되었다는 사실도 결과에 남아 있다.

### 최종 관계

| snapshot 날짜 | source 패키지 ID | source 버전 | target 패키지 ID | target 버전 | 관계를 만든 선언 수 |
| --- | ---: | --- | ---: | --- | ---: |
| 2026-08-31 | 1 | 1.0.0 | 1 | 1.0.0 | 1 |

저장 그룹별 행 수는 선언 해석 1, source 처리 1, 최종 관계 1, target 품질 문제 0이다. 품질 문제가 0행이어도 스키마를 가진 Parquet 파일이 존재한다.

이 통합 검증은 당시 `NULL 포함 + PARTIAL 보존` fixture 정책으로 실행했다. 테스트 버전에 배포일 누락은 없지만, 기존 결과를 새 정책으로 실행한 결과라고 표시하지 않는다. [통합 검증 요약 JSON](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/data/requirements-resolution/verification/integration-dbf68cf2/verification.json), [실행 manifest](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/data/requirements-resolution/verification/integration-dbf68cf2/run_manifest.json).

## 3. 어디까지 검증했는가

| 확인한 항목 | 기존 검증 결과 |
| --- | --- |
| 원본 파일·정책·npm 해석·실행 관리 | 호스트 테스트 28개 통과 |
| 여러 source 버전·미래 배포·NULL·입력 오류·중복 관계 | 실제 Spark 테스트 3개 통과 |
| NULL 배포일 제외 | 합성 데이터에서 source와 target이 함께 8개에서 7개로 줄어드는 것을 확인 |
| 실제 Spark → Node → Spark 전체 연결 | 통과 |
| 완료 결과 재검증 및 중단 후 완료 표시 복구 | 로컬·메모리 S3에서 통과 |
| 현재 저장된 테스트 Parquet | 이번 결과 조회에서 4개 파일의 SHA·행 수·결과 상태를 다시 확인 |

실제 Spark 경계 검사에는 해석 성공 선언 3개, 미해석 선언 1개, 중복을 합친 관계 2개의 fixture도 포함한다. 해당 fixture의 임시 데이터는 검사 후 제거했으며 현재 다시 볼 수 있는 것은 [검사 로그](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/data/requirements-resolution/verification/spark-tests-01/tests.log)와 테스트 코드다.

## 4. 아직 없는 결과

- 확정 정책을 적용한 전체 데이터의 source 수, NULL 배포일 제외 수, 관계 수, 미해석 비율.
- 실제 MinIO에 게시된 07 산출물.
- 08 dependents_count와 PostgreSQL 반영 결과.

## 5. 더 자세히 보기

- [전체 작업 기록: 변경 내용·실제 검증·문제와 해결](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/docs/worklogs/S15P21A506-283/02-progress-results.md)
- [구현 및 실행 설명](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/pipeline/requirements_resolution/README.md)
- [npm 버전 해석 코드](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/pipeline/requirements_resolution/semver_worker.cjs)
- [Spark 선언·관계 처리 코드](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/pipeline/requirements_resolution/transform.py)

별도 프로그램을 설치하거나 전체 계산을 돌리지 않고 이 문서의 표와 연결된 기록으로 지금까지의 결과를 확인할 수 있다.
