# 07 전체 계산 결과 — 재부팅 후 확인

2026-09-10 08:37 KST 확인. run ID는 `requirements-20260831-v1`이다.

후속 검증: 08:54 KST부터 별도 입력/출력 검증을 실행했다. 입력 전체 재검증과 산출물 footer 대조는 통과했으며, 행별 declaration unique key 전수 검사는 DuckDB 2GB 한도로 중단됐다. 최신 검증 결과는 [08-verification-result.md](08-verification-result.md), 복구 보장 범위는 [07-final-verification.md](07-final-verification.md)를 확인한다.

## 확인된 결과

Spark finalize의 `result.json`은 **2026-09-09 21:43:19 KST**에 저장됐다. 전체 계산 결과와 4종 Parquet 산출물이 남아 있다. 이번 확인에서는 계산을 다시 실행하지 않았다.

| 항목 | 결과 |
|---|---:|
| 대상 source 버전 | 47,172,949개 |
| 일반 dependencies 선언 | 289,214,123건 |
| 해석 성공 | 280,232,217건 (96.8944%) |
| 미해석 | 8,981,906건 (3.1056%) |
| 생성된 직접 관계 | 280,232,217건 |
| 조회된 후보의 잘못된 semver 기록 | 79건 |
| 결과 품질 | **PARTIAL** |
| 후속 dependents 집계 준비 플래그 | **false** |

정책은 일반 dependencies만 계산, 배포일 NULL 제외, 미해석 PARTIAL 보존이다. prepare 기록의 NULL 제외 수는 7,015,400개이며, peer 46,998,761건·optional 1,957,230건은 계산에서 제외됐다. 이는 포함된 source 버전 기준의 선언 수다.

## 미해석 사유

| 사유 | 선언 수 |
|---|---:|
| Curated에 대상 패키지 매핑 없음 | 5,214,487 |
| 조건을 만족하는 후보 버전 없음 | 1,654,836 |
| tag 형식 미지원 | 1,056,575 |
| Git 형식 미지원 | 378,100 |
| alias 형식 미지원 | 238,095 |
| 잘못된 버전 조건 | 233,660 |
| file 형식 미지원 | 116,286 |
| URL 형식 미지원 | 79,190 |
| 잘못된 패키지 이름 | 10,670 |
| 대상 패키지는 있으나 적격 후보 버전 없음 | 7 |

source 상태는 RESOLVED 32,030,084 / OBSERVED_NO_DEPENDENCIES 11,543,289 / DEPENDENCY_EXTRACTION_ERROR 1,952,635 / PARTIAL 1,440,411 / UNRESOLVED 206,530이다. source 상태와 개별 선언 상태는 서로 다른 기준의 집계다. upstream 처리 완료 여부는 여전히 확인되지 않았으며, 이 결과는 관측된 선언을 지정 정책으로 해석한 직접 관계다.

## 이번 검증과 남은 작업

- **검증됨:** 4종 산출물의 Parquet 2,520개를 열어 footer 행 수를 대조했다. 결과 요약과 실제 파일 행 수가 일치하며, 상태별 집계 합계·해석 성공/미해석 합계·준비 플래그의 일관성 검사도 통과했다. 검사 소요 시간은 62.281초다.
- 산출물은 총 5,719,755,195bytes다. declaration_outcomes 1,175개 파일, edges 1,152개, source_outcomes 192개, target_quality 1개다.
- **미완료:** host 제어 프로세스 종료로 최종 `run_manifest.json`과 `_SUCCESS`가 없다. 이번 검사는 원본 재검증, 전체 파일 내용 해시, 행별 lineage/FK 재검증 또는 원래 실행의 초기 코드/런타임 증거 복구를 대신하지 않는다.
- 원래 실행의 초기 code/runtime 증거가 저장되지 않아 표준 완료 기록은 복구하지 않는다. 결과는 로컬에 보존하며 MinIO 게시 및 08 계산/DB 적재는 수행하지 않았다.

실제 결과: [Spark 결과 JSON](../../../data/requirements-resolution/runs/requirements-20260831-v1/attempts/20260909T052957543914Z/finalize/result.json)

단발 검사 기록: [재부팅 후 검사 JSON](../../../data/requirements-resolution/runs/requirements-20260831-v1/verification/reboot-check-20260910T083727.json)
