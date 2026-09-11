# S15P21A506-193 — 버전별 dependents 계산·적재 작업 기록

7번에서 만든 의존 관계를 이용해 각 target 버전을 직접 의존하는 source 패키지·버전 쌍의 수를 계산하고, 검증된 결과를 `package_version_snapshot`에 적재하는 작업이다.

**현재 상태: H5-B 전체 날짜 계산 코드를 완성하고 실제 target 6개의 229일 표본 계산·정확성 대조를 완료했다. 전체 선정 패키지의 계산과 DB 적재는 아직 수행하지 않았다.** [코드·표본 검증 결과](16-historical-production-code.md)

후속 저장 최적화로 같은 cache의 229일 저장 시간이 29.297초→23.078초로 약 21% 줄었다.
count 파일 229개 SHA 일치, 품질·이력 값 대조와 전체 209개 테스트를 통과했다.
[저장 최적화와 운영 서버 조건](17-historical-write-optimization.md)

후속 병목 진단을 바탕으로 [성능 개선 계획](18-performance-improvement-plan.md)을 작성했다.
반복 JSON 변환·전역 검사·중간 행·날짜별 검증을 줄이는 순서와 정확성/처리량 비교 기준이며,
계획의 구현과 전체 선정 계산은 아직 시작하지 않았다.

최신 2026-08-31 한 날짜의 진단에서는 성공 관계 280,232,217개를 전체 집계하여 target 버전 6,156,555개의 PARTIAL Parquet를 저장했다. 검증·저장 포함 약 83초, 별도 파일 검증 통과. 이 결과는 정상 입력 승인이나 DB 게시 완료를 뜻하지 않는다.

이후 **229개 과거 기준일의 입력 모집단 준비와 파일 검증을 완료**했다. 최신 유효 target은
47,172,771개이며, 모든 날짜의 전체 target 키 수 합은 6,971,338,953개다. 약 14분 21초가
걸렸고 결과 Parquet는 5개·약 2.63GB다. 과거 날짜별 count는 아직 미계산이다.
새 재구성 모드의 로컬 모집단 검증이며 위 기존 정상 입력 승인이나 DB 게시를 뜻하지 않는다.

**H2 기준 구현과 H3 구간·변화량 계산 핵심까지 완료**했다. 전체 121개 테스트가 통과했고,
반복 합성 예제에서 H2와 count·상태·품질이 일치했다. 실행 시간 중간값은 1.859초에서
0.219초로 줄었다. 이후 H4 저장·재개와 H5-A 실제 입력 분석도 완료했다. H5-A에서는
고유 요구조건 11,051,014개와 패키지별 후보 규모를 저장하고 실제 파일 27개 검사를 통과했다.
후속 H5-B 표본은 입력 준비 60.625초, 229일 계산·저장 33.219초였다. 전체 선정 입력의
해석·집계 성능은 아직 미측정이다.
[H2 예제](12-historical-reference-results.md) · [H3 결과](13-historical-optimization-results.md)

D-22에 따라 저장 target은 다운로드 선정 목록의 고유 이름 99,996개로 제한하고,
참조하는 source는 전체 적격 패키지·버전을 유지한다. 선정 target의 0 포함 날짜별 키는
총 1,007,084,608개이며, 이 키 수 측정은 count 계산이나 DB 저장 완료가 아니다.

| 항목 | 착수 시 확인 내용 |
| --- | --- |
| 기록 시작일 | 2026-09-10, 한국 표준시 |
| 연결 이슈 | `S15P21A506-193`. 현재 브랜치에서 확인한 키이며 원격 Jira 제목·설명·상태는 조회하지 않음 |
| 작업 위치 | `C:\Users\SSAFY\workspace\S15P21A506` |
| 작업 브랜치 | `data/feat/S15P21A506-193-dependents-count` |
| 시작 HEAD | `114258e6b9b0689670b2733a9e974af940538747` — 7번 구현을 develop에 병합한 커밋 |
| 현재 요청 범위 | H5-B 코드 완성 및 작은 실제 표본의 정확성·속도 확인 후 보고. 전체 선정 실행·DB·commit·push 미포함 |
| 초도 검토 기준일 | `2026-08-31`. 후보 run과 정확한 시각은 조사했으며 정상 입력 승인·전체 target 모집단 확정은 아직 미충족 |
| 선행 데이터 상태 | 7번의 저장된 결과 기록은 `PARTIAL`, `ready_for_dependents=false` |

## 문서 안내

| 문서 | 기록할 내용 |
| --- | --- |
| [01 작업 범위](01-scope.md) | 목표, 집계 단위, 변경·보존 경계, 완료 기준 |
| [02 작업 계획](02-plan.md) | 단계별 순서, 선행 조건, 완료 증거, 진행 상태 |
| [03 이슈](03-issues.md) | 발견한 문제, 영향, 해결 방향, 실제 해결 결과 |
| [04 작업 일지](04-work-log.md) | 실제 수행한 작업과 근거를 날짜순으로 기록 |
| [05 결과와 검증](05-results.md) | 검증 상태, 실제 계산·적재 결과, 미실행 항목 |
| [06 기준과 결정 기록](06-decisions.md) | 기존 계약, 제안, 미확정 사항과 이후 결정 근거 |
| [07 입력 조사와 집계 기준](07-input-contract.md) | 실제 입력 위치·검사 범위·승인 미충족 사유·전체 target 모집단의 한계 |
| [08 Parquet 저장 결과와 확인 방법](08-artifact-results.md) | 세 파일의 역할, 두 snapshot 합성 예제, 실행 경로·재검증 방법, 생산 입력 승인과의 차이 |
| [09 최신 스냅샷 진단 집계](09-diagnostic-run.md) | 실제 전체 집계 수치·시간·입출력 파일·검증 증거·조회 방법·남은 한계 |
| [10 전체 스냅샷 count 계산 계획](10-historical-count-plan.md) | 229개 기준일의 과거 재구성, target 변경 구간·delta 집계, sparse 결과·0·PARTIAL·DB 반영 계획. 현재 단계는 02 문서와 D-22를 우선 |
| [11 과거 스냅샷 입력 준비](11-historical-input-results.md) | 관측 원본·calendar 고정, 버전별 최초 포함 시각, source/target 전체 대상 규모와 실행 증거 |
| [12 날짜별 기준 구현 결과](12-historical-reference-results.md) | 작은 정답 데이터의 날짜별 count 표, 중복·버전 교체·품질 검증과 재현 방법 |
| [13 날짜별 계산 최적화 결과](13-historical-optimization-results.md) | 구간 합집합·증감 누적, 기준 구현 대조, 반복 예제 성능 및 실제 데이터 연결의 남은 범위 |
| [14 날짜별 저장과 재개](14-historical-artifact-results.md) | 공통 count 구간 cache·양수 Parquet·완료 기록·재개와 변조 검사, 3일 예제·157개 회귀 테스트 |
| [15 H5 실제 입력 연결과 실행](15-historical-production-run.md) | 입력 workload 프로필·독립 자원 감시·상태 파일·실행 기록과 전체 계산의 남은 범위 |
| [16 전체 날짜 코드와 실제 표본](16-historical-production-code.md) | 선정 target·전체 source 입력 연결, 파티션 집계·재개, 6개 target×229일 정확성·속도와 남은 범위 |
| [17 날짜별 저장 최적화](17-historical-write-optimization.md) | 새 날짜의 중복 전수 검증 제거, SHA 재확인·재개 검증 보존, 동일 cache 성능·값 비교와 EC2 두 대 조건 |
| [18 성능 개선 계획](18-performance-improvement-plan.md) | 실측 병목, 요청 구성·전역 검사·중간 행·날짜별 검증 개선 순서, 결과 동일성·처리량 평가와 DB 직전 시간의 남은 범위 |
| [19 가중치 이벤트 집계](19-weighted-event-aggregation.md) | A0~A3 구현, 원본 중복·미해석 품질 보존, lodash 집계·품질 58.54% 감소와 작은 입력 회귀, v2 재개·229일 독립 검증 |
| [20 날짜별 검증과 처리량](20-daily-verification-throughput.md) | O-4 누적 합계 검증, 기존 파일 전수 대조, O-5 8·16·32개 전체 source 표본의 단계별 시간과 자원 기록 |
| [21 RTX 4070 GPU 해석 실험](21-gpu-resolver-experiment.md) | CPU 기준 커밋, 기존 PyTorch CUDA 활용, npm rank 구간·CPU 범위 인덱스·GPU 묶음 계산의 정확성 및 속도 비교 |
| [22 전체 32개 CPU/GPU 비교](22-gpu-32-package-comparison.md) | 40,701개 전체 요구조건·229일 정답 대조, 공통 준비와 해석 비용 분리, 5회 전체 합계 및 패키지별 비교 |
| [23 실제 계산값 미리보기](23-calculated-result-examples.md) | 요구조건별 선택 버전·날짜 구간과 이전 CPU 집계의 실제 dependents_count 값, 원본 조회 위치 |

계획 단계는 `P`, 이슈는 `ISS`, 실제 수행 기록은 `W`, 검증은 `V`, 결정은 `D` 식별자로 연결한다. 문서 파일의 숫자는 읽는 순서이며 상위 작업 번호와 구분한다.

## 기록 원칙

- 계획과 실제 수행 결과를 분리한다. 실행하지 않은 테스트·계산·적재를 완료로 표시하지 않는다.
- 7번의 과거 실측값은 선행 참고값으로 표시한다. 8번에서 다시 검증한 값이나 8번 산출물로 바꿔 적지 않는다.
- 해결 방향을 정한 것과 문제를 해결한 것을 구분한다. 결정에는 날짜·근거·영향 범위를 남긴다.
- 코드 병합, 파일 생성, 검증 통과, 데이터 게시를 각각 기록한다.
- 로그·manifest·해시 등 실행 증거가 생기면 이 폴더 아래 `evidence/`에 필요한 작은 증거만 추가하고 문서에서 연결한다. 원본 대용량 데이터와 인증정보는 복사하지 않는다.
- 현재 작업은 이 워크스페이스에서 진행하며, 7번 worktree의 코드·기록·산출물을 변경하지 않는다.

## 기준 자료

- [8번 작업 문서](../../jira/db-loading/08-version-dependents-load.md)
- [7번 구현과 소비 계약](../../../pipeline/requirements_resolution/README.md)
- [7번 사용자 정책 결정](../S15P21A506-283/03-policy-decision.md)
- [7번 계산 결과 기록](../S15P21A506-283/06-computation-results.md), [추가 검증 중단 기록](../S15P21A506-283/08-verification-result.md)
- [기존 PostgreSQL 적재 기반](../../../pipeline/postgresql/README.md), [스냅샷 계약](../../../pipeline/snapshot/README.md)
- [서비스 테이블 DDL](../../../backend/src/main/resources/db/migration/V1__init.sql)
- [집계 모듈](../../../pipeline/version_dependents/README.md), [커밋 전 전체 테스트 증거](evidence/commit-checkpoint-validation.json), [초기 손계산 예제 결과](evidence/small-graph-result.json)
