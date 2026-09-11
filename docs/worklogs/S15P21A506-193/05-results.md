# 05. 결과와 검증

**현재 결과: 실제 최신 스냅샷의 성공 관계 전체 진단 집계 완료. 280,232,217개 관계에서 6,156,555개 target 버전의 PARTIAL 결과를 저장했으며 별도 파일 검증이 통과했다. 전체 build 약 83초. 정상 입력 승인·전체 target 모집단 검증·DB 적재는 미완료다.** [전체 실행 결과](09-diagnostic-run.md) · [일지](04-work-log.md) · [완료 기준](01-scope.md)

후속 과거 재구성은 H1 입력 준비·H2 기준 구현·H3 구간 계산 핵심·H4 정규화 cache와 날짜별 저장/재개까지 완료했다. 실제 전체
날짜의 count는 아직 미계산이다. [H1 입력 규모](11-historical-input-results.md) · [H2 기준](12-historical-reference-results.md) · [H3 결과](13-historical-optimization-results.md) · [H4 결과](14-historical-artifact-results.md)

## 8번 검증 상태

| ID | 검증 대상 | 실행 여부와 결과 | 증거 |
| --- | --- | --- | --- |
| V-001 | 문서 링크·Markdown 형식·생성 파일 범위·기록 정확성 | 통과 — 7개 문서·로컬 링크 44개, UTF-8/LF·후행 공백·제목·표 경계 확인. 기존 추적 파일 변경 0개, 선행 수치 대조 일치, 독립 검토 CLEAR | 2026-09-10 로컬 문서 점검 및 W-004 |
| V-002 | 실제 7번 입력 파일·manifest·시간·정책·coverage | 최초 일부 조사 완료. 이후 성공 edge 전수 검증은 V-012에서 수행. 전체 source/target 모집단·coverage 및 정상 입력 승인 조건은 미충족 | [최초 입력 조사](evidence/input-assessment.json), [진단 전수 증거](evidence/diagnostic-full-run.json) |
| V-003 | 작은 정답 그래프와 집계 경계·실패 사례 | 전용 테스트 20개 통과(1.187초), AST 3개 통과. 별도 손계산 예제 일치 | [검증 요약](evidence/kernel-validation.json), [테스트 로그](evidence/kernel-tests.log), [예제 결과](evidence/small-graph-result.json) |
| V-004 | 격리 PostgreSQL의 staging·게시·재실행·롤백 | 미실행 | 없음 |
| V-005 | 정상 입력의 전체 target count 계산·품질·독립 대조 | 미실행. 성공 관계만의 진단 집계는 V-012로 구분 | 없음 |
| V-006 | 지정 DB 적재·조회·기존 데이터 보존 | 미실행 | 없음 |
| V-007 | 구현 후 문서·소스/로그 해시·변경 범위·독립 검토 | 통과. 소형 집계 핵심 범위에서 CLEAR. 문서 수정 후 기능 테스트를 불필요하게 재실행하지 않음 | [최종 점검](evidence/final-check.json) |
| V-008 | 스냅샷별 Parquet 저장·manifest·독립 검증·충돌과 실패 보존 | 전체 39개 테스트 통과(기존 20+신규 19, 12.383초), AST 6개. 두 날짜 CLI 합성 예제 저장·별도 프로세스 검증·저장 행 대조 통과. 최종 독립 코드 검토에서 차단 결함 없음 | [검증 요약](evidence/artifact-validation.json), [테스트 로그](evidence/artifact-tests.log), [예제 증거](evidence/artifact-demo.json), [확인 방법](08-artifact-results.md) |
| V-009 | Parquet 단계의 문서·소스/로그 해시·변경 범위 | 문서 10개와 로컬 링크, 최종 소스/로그 해시 및 기존 집계 코드 보존 점검 통과 | [최종 파일 점검](evidence/artifact-final-check.json) |
| V-010 | 실제 edge 표본의 집계 쿼리·실행 자원 비교 | 24,000,000행·680,282 target. 두 SQL×두 설정 각각 2회에서 target별 결과 동일. 현재 SQL의 8스레드/8GB 표본 평균은 1.2130초로 4스레드/2GB의 2.4691초보다 약 51% 감소. 전수 결과가 아니며 코드 변경 없음 | [표본 성능·동일성 증거](evidence/optimization-comparison.json) |

| V-011 | PARTIAL 전용 입력·Parquet·독립 CLI 검증 및 기존 회귀 | 전체 60개 테스트 통과(17.972초), AST 9개. 로그 표시 보완 후 전용 22개 테스트 통과(4.780초, 전용 테스트 담당 실행) | [전체 회귀 증거](evidence/diagnostic-validation.json), [실행과 로그 보완](09-diagnostic-run.md) |
| V-012 | 최신 성공 관계 전체 집계·입력/출력 검증 | 1,152파일·280,232,217행. 중복 0, target 6,156,555개. build 82.577초, 별도 verify exit 0. PARTIAL·DB 적재 불가 유지 | [전수 실행 증거](evidence/diagnostic-full-run.json), [결과 확인 방법](09-diagnostic-run.md) |
| V-013 | H1 입력 모집단·calendar·출력 파일 | 전체 80개 테스트 및 실제 229일 파일 검증 통과. target/date 키 합 6,971,338,953개. count 미계산 | [입력 준비 결과](11-historical-input-results.md) |
| V-014 | H2 날짜별 재선택·DISTINCT·상태·실행 상한 | 기존 80+신규 16, 전체 96개 테스트 30.953초 통과. 3일 예제 전체 키/count/품질과 저장 SHA 별도 대조. 독립 검토 PASS | [기준 결과](12-historical-reference-results.md), [검증 영수증](evidence/historical-reference-validation.json) |
| V-015 | H3 구간·delta·품질·동률 순서·입력 계약 | 기존 96+신규 25, 전체 121개 테스트 31.985초 통과. H2와 합성 예제 전체 결과 일치, 16일 반복 예제 3회 중간값 1.859초→0.219초. 독립 검토 PASS. 실제 데이터 성능 미측정 | [H3 결과](13-historical-optimization-results.md), [테스트 증거](evidence/historical-optimization-validation.json), [비교 측정](evidence/historical-optimization-comparison.json) |

| V-016 | H4 cache·날짜 Parquet·완료 anchor·재개·변조·입력 identity | 기존 121+신규 36, 전체 157개 테스트 45.686초·AST 24개 통과. 3일 예제에서 1일 완료 후 나머지 2일 재개·별도 CLI 검증. 독립 검토 PASS. 실제 229일 미실행 | [14 결과](14-historical-artifact-results.md), [검증 증거](evidence/historical-artifact-validation.json), [예제·별도 검증](evidence/historical-artifact-run.json) |

| V-017 | H5-A 실제 입력 형식·프로필·독립 프로세스·자원/강제 종료 | 전체 177개 테스트 57.357초, AST 30개 통과. 실제 프로필은 별도 실행 영수증으로 추적, 전체 count는 NOT_COMPUTED | [15 실행 기록](15-historical-production-run.md), [테스트 증거](evidence/historical-profile-validation.json) |

V-001은 최초 문서 준비 단계의 점검 기록이다. 이후 작은 데이터 집계 테스트는 V-003에 별도로 기록한다. 문서 점검이나 작은 데이터 테스트를 실제 전체 파일 검증·DB 적재 완료로 해석하지 않는다.

## 작은 정답 그래프의 실제 결과

아래는 실제 패키지 데이터가 아닌 합성 예제다. 원본 관계 6개 중 중복 하나를 제거하여 고유 직접 관계 5개를 계산했다.

| target package_id | target version | 손계산 기대값 | 집계 결과 |
| ---: | --- | ---: | ---: |
| 10 | 3.0.0 | 3 | 3 |
| 10 | 4.0.0 | 1 | 1 |
| 20 | 1.0.0 | 1 | 1 |
| 30 | 1.0.0 | 0 | 0 |

`1@1.0.0`, `1@2.0.0`, `2@1.0.0`이 `10@3.0.0`을 직접 의존하므로 3이다. 이 중 같은 관계를 한 번 더 넣어도 늘지 않는다. `10@3.0.0 → 20@1.0.0`이 있어도 20의 count에 10의 상위 의존자를 더하지 않는다. 관계가 없는 30은 정상 합성 입력에서만 0을 받는다.

20개 테스트는 PARTIAL/준비 상태, source 버전 구분, 복합 키, 잘못된 타입·키·버전, 모집단 누락·중복·공백, 날짜·마이크로초 경계, 결과 보존과 오류 시 롤백 등을 검증했다. 안정 버전 선별과 파일 진위·전체 모집단 검증은 아직 이 함수의 책임이 아니며 생산 어댑터에서 수행해야 한다.

현재 워크스페이스에서 재현:

```powershell
& 'C:\Users\SSAFY\workspace\S15P21A506\.venv-bq\Scripts\python.exe' -B -m unittest pipeline.version_dependents.test_aggregate -v
```

## 선행 7번 실측 참고값

아래 값은 저장소에 보존된 [7번 finalize 결과 JSON](../S15P21A506-283/evidence/full-run-finalize.json)에서 읽은 과거 결과다. 이번에 원본 Parquet를 다시 세거나 8번 count를 계산한 값이 아니다.

| 항목 | 기록된 값 |
| --- | --- |
| run ID | `requirements-20260831-v1` |
| snapshot | `2026-08-31` |
| source 버전 | 47,172,949 |
| 의존성 선언 | 289,214,123 |
| 해석된 선언 | 280,232,217 |
| 미해석 선언 | 8,981,906 |
| edge | 280,232,217 |
| 결과 상태 | `PARTIAL` |
| `ready_for_dependents` | `false` |

이 수치를 8번 전체 target 수나 DB 적재 행 수로 사용하지 않는다. 7번 추가 전체 검증은 [메모리 부족으로 중단된 기록](../S15P21A506-283/08-verification-result.md)이 있으며 전체 검증 완료로 표시하지 않는다.

## 실제 결과와 남은 정상 집계 범위

| 기록 항목 | 현재 값 |
| --- | --- |
| 승인 입력 run·manifest SHA·정책 SHA | 후보 run·작은 기록의 SHA는 조사 완료. 정상 완료 manifest 부재로 승인 입력은 아직 없음 |
| 전체 target 버전 집합·정확한 snapshot 시각 | 시각 `2026-08-31T21:01:10.517131Z` 확인. 전체 승인 target 집합은 미확정 |
| count 출력 run·파일 수·행 수·크기 | 진단 `resolved-20260831-v1`, Parquet 3개. count 6,156,555행·14,445,935 bytes. 상세는 09 문서 |
| count 합계·최댓값·0인 target 수 | 진단 합계 280,232,217·최대 2,606,910. 전체 target의 0은 계산하지 않음 |
| 품질 상태·제외/미해석 영향·게시 가능 여부 | PARTIAL·ready_for_load=false. 원본 미해석 8,981,906개와 복구 검증 공백 보존 |
| 계산 시간·최대 메모리·임시 디스크 사용량 | 순수 집계 48.518초, build 전체 82.577초. 8스레드·8GB 설정. 메모리·임시 디스크 최고 사용량은 미측정 |
| PostgreSQL 대상·실행 ID·적재/검증 행 수 | 미선정·미실행 |
| 완료 기준 AC-01~08 | AC-02와 키·시각·0 처리 등 계산 핵심은 소형 테스트로 검증. 실제 입력·전체 출력·DB 기준은 미검증 |

실행할 때 정확한 명령·시작/종료 시각·코드 기준·입력과 출력 식별자·검증 결과를 기록한다. 수치가 아직 없으면 `미계산`으로 두며 0을 채우지 않는다.
