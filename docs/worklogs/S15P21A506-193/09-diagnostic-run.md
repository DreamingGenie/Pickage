# 09. 최신 스냅샷 진단 집계 실행

상태: **2026-09-10 최신 스냅샷의 성공 관계 전체 집계·Parquet 저장·별도 프로세스 검증 완료. 결과는 PARTIAL이며 DB 적재 불가 상태를 유지한다.**

## 범위와 실행 계획

- 최신 실제 입력 `2026-08-31`, 정확한 시각 `2026-08-31T21:01:10.517131Z`를 사용한다.
- 기존 7번 `requirements-20260831-v1`의 해석된 관계 전체를 입력으로 삼는다. 원본 파일은 이전 worktree에서 읽기만 한다.
- 사용자 D-07 결정에 따라 성공한 관계에서 서로 다른 source 패키지·버전 쌍을 target 버전별로 센다. 결과에 `PARTIAL`과 `ready_for_load=false`를 남긴다.
- 전체 target 모집단에 0을 채우지 않는다. 해석된 관계에 등장한 target만 출력하며 컬럼명은 `resolved_dependents_count`로 구분한다.
- 기존 정상 집계의 COMPLETE guard·7번 resolver·서비스 DDL을 변경하지 않는다. 새 파일 `diagnostic_input.py`, `diagnostic.py`, 전용 테스트와 현재 기록 폴더만 추가·갱신한다.

1. 고정한 recovery candidate SHA와 명시된 edge 파일 목록을 확인한다. 해당 파일의 SHA·크기·footer 행 수·스키마·정확한 snapshot·행별 계보·kind·키/버전·선언 수를 검사한다.
2. 기존 DuckDB에서 8스레드·8GB로 DISTINCT 후 GROUP BY를 실행한다. 결과 전체를 Python 메모리로 모으지 않는다. scratch는 이번 실행 폴더에 둔다.
3. count·lineage·quality Parquet를 저장하고 원본 파일 해시를 재확인한다. 새 완료 manifest는 출력 파일과 내용 검증이 끝난 뒤 작성한다. 정상 게시용 `_SUCCESS`는 만들지 않는다.
4. 별도 프로세스에서 저장 파일을 다시 검증하고 결과 행 수·관계 합계·최대 count·실측 시간과 한계를 기록한다.

원본 recovery candidate는 **정상 승인 manifest가 아니다**. 출처는 고정하되 source/target 전체 모집단,
미해석의 원인별 원본 행, resolver의 의미적 정확성은 이번에 전수 검증하지 않았다는 한계를 유지한다.
DB 적재·원격 게시·commit·push는 수행하지 않는다.

## 실행 환경

Python은 현재 워크스페이스 `.venv-bq`를 사용하고 계산 엔진은 DuckDB다. 이번 8번 집계에서 Spark를 시작하지 않는다.
계산 메모리가 부족하면 새 실행 ID와 명시한 자원 설정으로 재시도하며, 실패 폴더를 덮어쓰지 않는다.
이번 단계 전용 테스트와 입력 조사 후 전체 집계를 시작한다.

## 구현과 사전 검증 결과

- `diagnostic_input.py`: recovery candidate pin 및 정확한 edge 파일 목록, 파일별 SHA/크기/행 수/스키마, 행의 스냅샷·계보·키·일반 dependencies·선언 수 합계를 검증한다. 실제 candidate에 파일별 schema가 없으므로 실제 Parquet 스키마를 직접 검사한다.
- `diagnostic.py`: 중복 제거 집계, PARTIAL Parquet 3개 저장, 입력 SHA 재확인, 저장값 검증 후 마지막 manifest 작성, 별도 프로세스 verify를 제공한다. Spark 실행이나 새 의존성 설치는 없다.
- 기존 39개와 신규 21개, 총 **60개 테스트 통과(17.972초)**. Python AST 9개 통과. [검증 증거](evidence/diagnostic-validation.json), [테스트 로그](evidence/diagnostic-tests.log).
- 날짜를 Python 객체로 읽는 과정의 선택 패키지 `pytz` 요구를 발견했다. 저장된 TIMESTAMPTZ는 유지하고 검증할 때 UTC epoch 마이크로초 정수로 비교하여 추가 설치 없이 해결했다.
- 독립 읽기 전용 검토에서 실제 candidate 구조와 실행 코드의 호환을 확인했으며 실행을 막는 결함은 발견하지 않았다. 전수 결과의 완료 증거는 아래에 별도로 기록한다.

## 선택한 입력

| 항목 | 값 |
| --- | --- |
| candidate | `requirements-20260831-v1/recovery_candidate-20260909T235450Z.json` |
| 최초 고정 SHA-256 | `432d3b59f17a7be883aa6350deefa85362371c99398b91513df4deec590ef618` |
| edge 파일 | 1,152개 |
| candidate가 기록한 edge 행 | 280,232,217개. 실제 파일/행 대조 통과 |
| candidate가 기록한 edge 크기 | 1,987,003,284 bytes |
| 출력 실행 ID | `resolved-20260831-v1` |
| 실행 영수증/로그 | `data/version-dependents/executions/resolved-20260831-v1/` |

## 실제 결과

전체 build 프로세스가 exit code 0으로 종료했다. 별도 verify 프로세스도 exit code 0으로 종료했다.
[실행·검증 증거](evidence/diagnostic-full-run.json)에 실제 명령, 시작·종료 시각, 입력 pin, 파일 해시,
실측 수치와 실행 소스 해시를 보존했다.

| 항목 | 실제 값 |
| --- | ---: |
| 해시·스키마·행별 검증한 edge 파일 | 1,152개 |
| 읽은 성공 관계 | 280,232,217개 |
| 서로 다른 source/target 버전 관계 | 280,232,217개 |
| 제거한 중복 관계 | 0개 |
| 결과 target 버전 | 6,156,555개 |
| count 합계 | 280,232,217 |
| 최대 count | 2,606,910 |
| 원본 보고서의 미해석 선언 | 8,981,906개 |

| 단계 | 실제 소요시간 |
| --- | ---: |
| 입력 파일 및 전체 edge 행 검증 | 23.835초 |
| 중복 제거·target별 집계 | 48.518초 |
| Parquet 저장 | 1.120초 |
| 입력 SHA 재확인 | 2.817초 |
| 저장 결과 검증 | 0.954초 |
| build 함수 전체 | 82.577초 |
| build 프로세스 전체 | 82.878초 |
| 별도 verify 프로세스 | 1.048초 |

설정은 DuckDB 1.5.5, 8스레드·메모리 한도 8GB다.
최대 실제 메모리 사용량과 scratch 최고 사용량은 별도로 측정하지 않았다. 사전 예상인 3~10분보다
빠르게 완료되었으며, 준비·구현 시간은 위 build 시간에 포함되지 않는다.

| 출력 파일 | 행 수 | bytes |
| --- | ---: | ---: |
| `resolved_counts.parquet` | 6,156,555 | 14,445,935 |
| `lineage.parquet` | 1 | 3,491 |
| `quality.parquet` | 1 | 3,404 |

출력 폴더:
`data/version-dependents/diagnostic-runs/snapshot=2026-08-31/run_id=resolved-20260831-v1/outputs/`

최초 결과 manifest SHA-256:
`c4f977469045b80003767f9de02981383251d1f2b4720d3e7aa17736958732ec`

## 결과 확인 방법

[결과 Parquet](../../../data/version-dependents/diagnostic-runs/snapshot=2026-08-31/run_id=resolved-20260831-v1/outputs/resolved_counts.parquet),
[품질 Parquet](../../../data/version-dependents/diagnostic-runs/snapshot=2026-08-31/run_id=resolved-20260831-v1/outputs/quality.parquet),
[실행 manifest](../../../data/version-dependents/diagnostic-runs/snapshot=2026-08-31/run_id=resolved-20260831-v1/outputs/diagnostic_manifest.json).

DuckDB에서 상위 20개 결과를 조회할 수 있다. `package_id`는 기존 패키지 식별자다.

```sql
SELECT package_id, version, snapshot_at, resolved_dependents_count, dataset_status
FROM read_parquet('data/version-dependents/diagnostic-runs/snapshot=2026-08-31/run_id=resolved-20260831-v1/outputs/resolved_counts.parquet', hive_partitioning=false)
ORDER BY resolved_dependents_count DESC, package_id, version
LIMIT 20;
```

PowerShell에서 저장 파일을 재검증하려면 아래 명령을 현재 워크스페이스에서 실행한다.

```powershell
& '.\.venv-bq\Scripts\python.exe' -B -m pipeline.version_dependents.diagnostic verify --output-dir 'data/version-dependents/diagnostic-runs/snapshot=2026-08-31/run_id=resolved-20260831-v1/outputs' --manifest-sha256 'c4f977469045b80003767f9de02981383251d1f2b4720d3e7aa17736958732ec'
```

## 해석과 남은 범위

- 이 count는 성공한 관계만을 대상으로 계산한 직접 의존자 수다. 미해석 선언을 0으로 계산하거나 전체 의존 관계가 완전하다고 판단하지 않는다.
- 출력에 없는 target은 의존자 0이 확정된 버전이 아니다. 전체 target 모집단은 이번 결과에 포함하지 않았다.
- 원본의 NULL 배포일 제외 정책과 미해석 PARTIAL 정책, 복구 과정의 검증 공백을 보존했다. 원본 미해석의 상세 원인 및 전체 source/target 모집단은 전수 재검증하지 않았다.
- 데이터 상태는 PARTIAL이고 `ready_for_load=false`다. 정상 게시용 `_SUCCESS` 생성, DB 적재, 원격 게시, commit·push는 수행하지 않았다.

## 종료 후 로그 표시 보완

실제 build의 DuckDB 진행 표시가 stdout JSON 앞에 붙어, 계산이 끝난 후 상위 실행기의 cp949
콘솔 표시와 JSON 전체 파싱이 실패했다. 원래 UTF-8 로그의 JSON 결과를 추출해 최초 manifest
SHA로 별도 verify를 수행했고 통과했다. build 자체와 저장 파일은 정상 종료·생성 상태였다.

이후 build connection의 진행 표시를 끄는 설정 한 줄을 추가했다. 집계 SQL이나 결과 파일은
변경하지 않았으며 전체 재계산도 하지 않았다. 실행 당시 5개 소스는 manifest 해시와 대조 후
`data/version-dependents/executions/resolved-20260831-v1/executed-code/`에 보존했다.
보완 후 CLI JSON 출력 테스트를 포함한 전용 22개 테스트가 통과했다(4.780초, 전용 테스트 담당 실행).

[최종 파일 점검](evidence/diagnostic-final-check.json)에서 Python AST 9개, 문서 형식과 로컬 링크,
기존 7번·스냅샷·집계 핵심의 변경 없음 및 기존 저장 계층의 이전 검증 해시 일치를 확인했다.
