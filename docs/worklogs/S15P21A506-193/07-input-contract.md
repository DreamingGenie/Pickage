# 07. 입력 조사와 집계 기준

작성일: 2026-09-10. **입력 위치·기준 조사를 수행했다. 실제 7번 run은 정상 입력 승인 조건을 충족하지 못했다.** [조사 증거](evidence/input-assessment.json) · [이슈](03-issues.md)

## 실제로 확인한 입력

| 항목 | 확인값 |
| --- | --- |
| 조사한 run | `requirements-20260831-v1` |
| 원본 위치 | `C:\Users\SSAFY\workspace\S15P21A506-283-requirements-snapshot\data\requirements-resolution\runs\requirements-20260831-v1` |
| attempt | `20260909T052957543914Z` |
| snapshot | `2026-08-31` |
| 정확한 원천 시각 | `2026-08-31T21:01:10.517131Z` |
| input SHA | `d673d51c73b9245ea897d5b910dc7a90c8e905930a7d05040d07ae9d3e9418e5` |
| policy SHA | `721c9d968f75429497b5e30b86ba0137998ea6a6ab1766bfb274d5661da52ef8` |
| 결과 상태 | `PARTIAL`, `ready_for_dependents=false` |
| 최종 완료 기록 | run 루트의 `run_manifest.json`과 `_SUCCESS` 모두 없음 |
| 이번 사용 방식 | 원본 위치에서 작은 메타데이터·파일 목록·대표 파일 스키마를 읽기 전용 조사. 입력 파일 이동·복사 없음 |

작업 코드와 새 기록은 기존 워크스페이스 `C:\Users\SSAFY\workspace\S15P21A506`에 둔다. 위 경로는 이전 계산 결과의 읽기 전용 참조 위치다.

| 실제 폴더 | 파일 목록에서 확인한 Parquet 수 | stat으로 확인한 바이트 |
| --- | ---: | ---: |
| `prepare/outputs/candidates` | 192 | 973,227,070 |
| `prepare/outputs/sources` | 192 | 1,029,137,212 |
| `finalize/outputs/edges` | 1,152 | 1,987,003,284 |
| `finalize/outputs/source_outcomes` | 192 | 1,116,516,162 |
| `finalize/outputs/target_quality` | 1 | 5,022 |

작은 input manifest·정책·prepare/finalize 결과의 해시를 기록하고, input SHA·policy SHA·기준일의 일치를 확인했다. 기존 정책 검증 함수도 통과했으며 prepare/finalize 결과 바이트는 저장소의 과거 증거와 일치한다.

**이 점검은 전체 데이터 승인 검증이 아니다.** 모든 Parquet의 SHA·footer 행 수·행별 정합성, 원격 manifest, DB 상태는 재검증하지 않았다. 각 그룹의 첫 파일 스키마만 읽었으며 전체 파일 스키마가 같다고 확정하지 않는다.

## source와 전체 target의 구분

- source는 모든 eligible 릴리스 버전이다. 패키지별 대표 버전으로 축소하지 않는다.
- 7번 prepare의 candidates는 릴리스·배포일 조건을 반영한 후보다. 기록된 47,172,949행은 아직 전체 stable-semver 검증을 마친 target 수가 아니다.
- Node의 버전 유효성·prerelease 검사는 요청을 받은 target 패키지에 한해 수행된다. `target_quality`의 범위도 조회한 패키지에 한정된다.
- 이번 작은 품질 파일 조회에서 `INVALID_TARGET_SEMVER=79`를 확인했다. 이 79건을 전체 후보의 모든 제외 대상으로 간주할 수 없다.
- 따라서 candidates에서 이 79건만 빼거나 edge에 나타난 target만 추출해 전체 target 모집단을 확정하지 않는다.
- 실제 집계 전에는 같은 snapshot의 전체 후보에 현재 target 정책을 적용한 버전 목록과 제외 증거를 검증해야 한다. 실제 승인 target 파일·해시·행 수는 아직 미확정이다.

이 경계가 필요한 이유는 관계가 없는 target에 0을 채우기 때문이다. 잘못된 전체 목록이나 부분 입력에 0을 채우면 정상 무관계와 누락 관계를 구분할 수 없다.

## 정상 입력의 조건

| 조건 | 현재 조사한 run |
| --- | --- |
| 식별 가능한 run·snapshot·정책·원천 시각 | 작은 기록에서 확인 |
| 완료 manifest·marker와 전체 파일/내용 검증 | 미충족 |
| `resolution_status=COMPLETE`, `ready_for_dependents=true` | 미충족 |
| 전체 source·target 모집단 및 coverage 검증 | 미충족 |
| 같은 원천·시간·정책의 edge와 모집단 연결 | 전체 행 검증 미실행 |

현재 입력은 위 조건을 만족하지 않으므로 정상 count 계산·게시 입력으로 승인하지 않는다. 임의의 완료 marker 생성, PARTIAL을 COMPLETE로 변경, 누락 관계의 0 대체는 하지 않는다.

## 작은 데이터 집계 핵심의 범위

8번 전용 계산 핵심은 기존 DuckDB를 사용하고, 명시적으로 주어진 source·target 모집단과 edge의 관계를 검사한다. PARTIAL 또는 준비되지 않은 입력은 결과 생성 전에 거부한다. 정상적인 합성 데이터에서만 전체 target별 직접 dependents와 무관계 0을 계산한다.

계산 함수에 전달한 상태값은 파일 승인 증거를 대체하지 않는다. 생산용 입력 어댑터가 manifest·파일·정책·모집단을 검증하는 기능, 전체 결과 Parquet·manifest 게시, PostgreSQL 적재는 후속 구현 범위다. 이번에는 실제 7번 edge를 집계 함수에 넣지 않는다.
