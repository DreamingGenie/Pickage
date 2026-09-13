# S15P21A506-193 — 버전별 dependents 계산·적재 작업 기록

최신 상태(2026-09-13): **229일/1,007,084,608행의 로컬 서비스 테이블 전환 완료**.
`public.package_version_snapshot`은 새 날짜별 파티션을 연결하고 이전 데이터·이력은 백업으로 보존했다.
[44 서비스 전환·복구 기록](44-service-table-cutover.md)이 현재 상태의 기준이다.
전환 전 전체 적재·검증에는 2시간 30분 28초가 걸렸다. [42 전체 시간 측정](42-timed-full-reload.md).
[43 패키지·버전별 조회 측정](43-package-version-query-probe.md): 16패키지/48버전 읽기 전용 측정 완료.
229일을 모두 반환한 19버전의 반복 DB 중앙값13.274ms, 일반 SELECT 결과 수신 중앙값15.482ms.
최초 조회·캐시 영향과 API/EC2/동시 부하 미검증 범위는 결과 문서를 따른다.

## 완료 범위와 남은 작업

- H1~H4: 입력 준비, 기준 계산, 구간·변화량 집계, Parquet 저장·검증·재개 구현 완료.
- H5: 선정 99,996개 이름·229일 전체 집계 완료. CPU 작업자 4개로 입력 준비부터 최종 검증까지
  1시간 26분 55초가 걸렸다. 양수 count Parquet는 296,325,102행이다. [30 전체 집계](30-full-selected-run.md).
- H6: 작은 실제 데이터의 키 연결·0 보완·격리 DB 대조와 전체 DB 키 전수 확인 완료.
  [31 소규모 검증](31-db-preparation-pilot.md), [32 전체 적재기](32-full-db-loader.md).
- H7: DB 키가 연결된 97,745개 패키지의 유효 버전·날짜, 0 포함 1,007,084,608행 적재·검증과
  로컬 서비스 전환 완료. 기존 43일 테이블과 이력은 백업으로 보존했다.
- 다음 협업 단계: 이번 전환·복구와 문서 정리를 커밋하고 develop 비교 및 MR을 준비한다.
- 후속 운영 범위: EC2 데이터 이관·서버 적용, 백엔드 버전별 조회 수정, API/동시 부하 검증,
  새 날짜 적재·자동화. 전환 전 Check/Start/Resume은 현재 서비스 대상에 재실행하지 않는다.

## 계산 의미와 근거

저장 target은 다운로드 선정 패키지이며 참조 source는 전체 적격 패키지·버전이다.
regular dependencies만 계산하고 배포일 NULL은 제외한다. 성공적으로 해석된 관계만 세며
미해석 품질은 PARTIAL로 남긴다. 0은 이 계산 범위에서 참조가 없는 경우이며 미해석 해소를 뜻하지 않는다.
원본 산출물의 품질·생성 지문을 현재 상태로 덮어쓰지 않았다.

실행 기본값은 CPU 작업자 4개다. 동일한 32개 표본의 전체 계산·저장 비교에서 CPU 43.995초,
GPU 50.291초였기 때문이다. GPU 코드와 실험 기록은 보존했다. [28 비교](28-cpu-gpu-overlap.md).
과거 개별 실험의 시간·현재 상태 표시는 작성 당시 기준이며 최신 완료 판정은
[02 H단계 표](02-plan.md), [05 결과 요약](05-results.md), [44 서비스 전환](44-service-table-cutover.md)을 따른다.

## 착수와 정책 이력

| 항목 | 착수 시 확인 내용 |
| --- | --- |
| 기록 시작일 | 2026-09-10, 한국 표준시 |
| 연결 이슈 | `S15P21A506-193`. 현재 브랜치에서 확인한 키이며 원격 Jira 제목·설명·상태는 조회하지 않음 |
| 작업 위치 | `C:\Users\SSAFY\workspace\S15P21A506` |
| 작업 브랜치 | `data/feat/S15P21A506-193-dependents-count` |
| 시작 HEAD | `114258e6b9b0689670b2733a9e974af940538747` — 7번 구현을 develop에 병합한 커밋 |
| 과거 H5-B 승인 범위 | 코드 완성 및 작은 실제 표본 검증까지였으며, 이후 별도 사용자 요청으로 전체 계산·DB 적재·서비스 전환을 진행함 |
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
| [24 CPU/GPU 실제 집계 연결](24-cpu-gpu-production-integration.md) | 선택형 버전 해석·집계 연결, 재개 계약·정확성 검사, 32개×229일 준비부터 저장·검증까지 비교 |
| [25 병렬 계산 구조 계획](25-parallel-execution-plan.md) | 패키지 묶음별 입출력·CPU worker·GPU 요청 큐·재개·검증·실측과 EC2 확장 경계. 계획만 작성 |
| [26 입력 분할·CPU 병렬 실행](26-parallel-input-cpu-execution.md) | P0~P2 구현, Windows 프로세스 종료·재개·의미 대조와 실제 32개 표본의 1/2/4 worker 측정 |
| [27 입력·검증·날짜 저장 개선](27-input-verification-storage-optimization.md) | 반복 입력 스캔·빈 파일·metadata 검사 감소, P3 묶음 저장·0 조회·중단 재개와 교대 반복 측정 |
| [28 CPU·GPU 작업 중첩](28-cpu-gpu-overlap.md) | 단일 GPU 전담 프로세스·후보 재사용·CPU 준비/집계 중첩, 오류/재개 검사 및 같은 32개 표본 비교 |

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

- [32 전체 DB 키 검증과 날짜별 원자적 적재기](32-full-db-loader.md): 전수 키/원천 일치, 0 복원 및 실패·재개 검증. 실제 전체 DB 적재는 미실행.

- [33 전체 DB 적재 실행](33-full-db-load.md): 사용자 승인 후 229일 전체 백그라운드 적재 시작. 완료 여부는 실행 상태 파일 기준.

- [34 DB 적재 중단과 재개 준비](34-db-pause-and-resume.md): 43일/106,346,692행 보존, 2023-03-06 취소, 체크포인트와 재개 검사 준비.

- [35 DB 적재 성능 개선 계획](35-db-load-optimization-plan.md): 공식 문서 조사, BRIN/검증/COPY 비교, 필요 시 partition 구조 실험, 기존 43일을 보존하는 호환 재개.

- [36 삽입·외래키 실험과 이동 전 중단](36-db-insert-benchmark.md): 10만 행 진단 완료, 하루 전체 실험 취소·정리, 입력/체크포인트·실험 재개 도구 보존.

- [37 날짜 partition 연결·재개 검증](37-db-partition-attach-probe.md): 실제 282만 행 일괄 검증 후 약 3.3ms 연결, 제약 재사용·값 전수 일치·실패/재개 검사. 실제 기존 테이블 전환은 미실행.

- [38 최대 하루치와 전체 재적재 예상](38-largest-day-full-reload-estimate.md): 최대 782만 행 입력 생성+DB 흐름 49~53초, 전체 229일/10억 행 중심 약 2시간 30분·일정 예산 3~4시간. 실제 전체 재적재 미실행.

- [39 빠른 전체 재적재 실행 준비](39-fast-reload-ready.md): 실제 실행 이력·검증·중단/재개 연결, 최대 날짜 통합 검증과 전체 설정 점검. 전체 재적재는 시작하지 않음.
- [40 실행 안내](40-fast-reload-runbook.md): 나중에 사용할 Check/Start/Status/Stop/Resume 명령과 서비스 전환 경계.

- [41 빠른 전체 재적재 실행·중단](41-fast-full-reload-run.md): 19일/43,616,976행 보존 후 정상 중단. 다음 날짜 2022-09-19, 자동 재개 없음. 서비스 조회 구조 검토는 남아 있다.
- [44 로컬 서비스 테이블 전환](44-service-table-cutover.md): 전환·복구 예행연습, 원자적 전환과 실제 반환값 확인 완료.
  이전 단계의 전환 미실행/재개 안내는 해당 시점의 기록이다.
