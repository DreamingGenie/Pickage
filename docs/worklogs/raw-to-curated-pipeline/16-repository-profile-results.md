# Repository 1,000개 표본 상세 결과

## 결론
repository 48.080초로 전체 단계 시간 합계의 87.2%였다. 검증·보고 action 합계 18.110초, 최초 지표 생성/쓰기 action 10.578초, Spark 시작/종료 6.085초가 주요 비용이었다. 후보 상세 파일 쓰기 action은 1.284초로, 이번 표본에서 그것만을 주된 병목으로 볼 근거는 없다. 평균 CPU 사용량은 1.94core였으며 OOM/메모리 spill은 없었다.

## 범위와 조건
- run: repository-profile1000-20260917-a1, 2026-09-17 13:06:54~13:07:59 KST.
- 기존 sample1000-ec2-20260916-a2의 고정 입력 재사용. 대상 스냅샷은 2026-08-31, 정확 시각 2026-08-31T21:01:10.517131Z. 현재 weekly가 수집 중인 새 회차를 처리한 실험이 아니다.
- 패키지 1,000, 원천 버전 106,393, Curated 버전 40,417, 저장소 관측 672. 표본의 모든 버전을 포함한다.
- data EC2 한 대, baseline 5단계, repository local Spark local[2], JVM 4GiB, shuffle partitions 16. 이전 단계 결과를 다음 단계에 넘기는 전체 체인이 아니라 고정 단계 입력 실험이다.
- CPU cap 2, cpu shares 128, nice 10, RAM 7680MiB, swap 추가 사용 불가, 읽기/쓰기 각각 32MiB/s. 기존 실험 CPU cap 3에서 변경했고 weekly가 공존한다. 따라서 43.867초였던 이전 repository 대비 이번 48.080초를 코드 성능 회귀/개선으로 판정하지 않는다.
- 기존 로컬 파일 readonly, network none, 공식 MinIO 게시/DB 적재 없음. 변환 코드 변경 없이 진단 wrapper만 추가했다.

## 단계별 시간
| 단계 | 초 |
| --- | ---: |
| package_version | 2.689 |
| downloads | 0.219 |
| repository | 48.080 |
| package_snapshot | 0.543 |
| dependents | 3.603 |
| 합계 | 55.135 |

job_seconds 55.204초는 실행기 부대 비용을 포함한다. host baseline phase 60.971초는 컨테이너 감시와 사후 비교 등 범위가 더 넓다.

## Repository 시간 분해
repository-actions-summary.json의 action을 호출 위치로 분류한 합계다. 추가 Spark action을 수행해 시간을 강제로 분리하지 않았다.

| 구간 | 초 | 의미 |
| --- | ---: | --- |
| Spark 시작/종료 | 6.085 | 시작 5.539, 종료 0.546 |
| 입력 4종 행 수 확인 | 2.988 | 첫 package count 2.134초 포함 |
| 키·중복·참조·스냅샷·원천 매칭 검증 | 9.789 | 필요한 조인 계산도 포함 |
| 최종 metric 최초 생성/쓰기 | 10.578 | URL 정리, 후보 선택, 통계 집계/조인 등 상류 lazy 계산 포함 |
| quality 5종 생성/쓰기 | 5.201 | selection 2.067, candidates 1.284, observations 0.747, conflicts 0.857, unmapped 0.247 |
| 저장된 6종 행 수 재집계 | 0.879 | 파일 다시 열기/계획 구성의 일부는 action 밖 |
| 최종 정합성·사유별 보고 집계 | 4.455 | 최종 키 검사, 선택/NULL/후보 사유 집계 등 |
| action 밖 차이 | 8.105 | 48.080초에서 계측 action 합계 39.975초를 뺀 값. 읽기/스키마 추론/계획 구성/캐시 해제/계측 자체 등 후보가 있으나 각각의 비중은 미측정 |

최초 metric 쓰기 action의 실제 출력 지표는 29,520bytes이고 134 task가 포함된다. 따라서 10.578초를 1,000행 파일의 순수 디스크 쓰기 시간으로 해석할 수 없다.

## 자원과 Spark 이벤트
- repository cgroup CPU 93.222 CPU초 / wall 48.080초 = 평균 1.939core. 2core 상한의 약 97%에 해당한다. container 전체의 CPU로, task/JVM JIT/driver/Python 등을 포함한다. CPU throttling 시간 자체는 이 요약으로 확정하지 않는다.
- 전체 전처리 구간 container CPU 101.441 CPU초, 관측 peak memory 2,001,317,888bytes(1.864GiB). Spark heap 사용량과 같은 지표가 아니며 container page cache 등을 포함한다.
- repository 물리 cgroup IO: 읽기 29,323,264bytes(27.965MiB), 쓰기 8,048,640bytes(7.676MiB). OS cache 및 비동기 writeback의 영향을 받으므로 논리 파일 크기/총 스캔량과 다르다.
- 전체 event log TaskEnd 368개 중 profile action에 귀속된 task 357개. 나머지 11개는 action 태그 밖이다. profile job 98개, 이벤트 로그 완료/파싱 정상.
- 아래는 **태그가 연결된 357개 task 합계**다. 전체 container 수치나 wall time으로 해석하지 않는다: executor run 21.969초, executor CPU 10.094초, GC 0.530초(동시 task 간 중복 가능), shuffle write/read 각각 1,584,742bytes, task input 20,221,882bytes / output 997,159bytes. memory/disk spill 0, 귀속 task 실패 0.
- container CPU 93.222초와 task CPU 10.094초는 측정 범위가 달라 차이를 모두 대기 시간으로 볼 수 없다. driver/JIT/Python/기타 비-task CPU 비중을 나누는 별도 profiler는 사용하지 않았다.

## 결과 정합성과 weekly 보호
| repository 출력 | 행 수 |
| --- | ---: |
| metric/data | 1,000 |
| quality/selection | 1,000 |
| quality/candidates | 40,417 |
| quality/project_observations | 672 |
| quality/project_conflicts | 0 |
| quality/unmapped_projects | 0 |

6종 모두 과거 결과와 행 중복을 포함한 EXACT_CANONICAL_ROW_MULTISET=EQUAL. 다른 4단계의 출력 전체까지 이번 비교에서 재검증했다고 주장하지 않는다.

- 지표 연결 성공 715 package. 유효 저장소 없음 166, 같은 스냅샷의 관측 없음 119로 NULL 285개. 실패 실행/유실이 아니라 기존 정책과 일치하는 결과다.
- weekly guard 22회, 기준 위반 0. 기존 서비스 guard 기준 위반 0. weekly 동일 컨테이너 running, restart 0, checkpoint 갱신 유지.
- 호스트 최소 가용 메모리 약 11.33GiB, IO pressure avg10 최대 3.63%, memory pressure 0. weekly 요청 지연을 대조군과 측정하지 않았으므로 영향이 완전히 0이었다고 보장하지 않는다.
- 실험 컨테이너 exit 0 / OOM false / cleanup_errors=[]; 제거 완료.

## 개선 우선순위와 미확인 사항
1. 검증을 유지하며 같은 입력의 여러 검사를 묶는 방안을 먼저 비교한다. 검증·보고 action 18.110초 전체가 제거 가능한 낭비라는 뜻은 아니다.
2. 최초 지표 생성의 계획/조인/후보 선택을 살펴 불필요한 작업을 줄인다. 10.578초 안의 연산별 독립 시간은 이번 측정으로 확정하지 못했다.
3. 작은 표본에서 큰 비중인 Spark 시작/계획 구성 비용을 확인한다. 전체 스냅샷에서도 같은 비중일 것이라고 일반화하지 않는다.
4. 정상 후보 기록 축소는 보존 정책 변경이므로 별도로 판단한다. 이번 candidates 쓰기 1.284초만으로 큰 성능 향상을 약속할 수 없다.
5. 이 표본에서는 메모리 증설 우선의 근거가 없다. 다만 과거 전체 입력의 OOM이나 대규모 DISK_ONLY 캐시 IO 문제를 부정하는 결과는 아니다.

## 근거
- evidence/repository-profile/baseline-report.json
- evidence/repository-profile/repository-actions-summary.json
- evidence/repository-profile/repository-spark-summary.json
- evidence/repository-profile/repository-comparison.json
- evidence/repository-profile/completion-summary.json
- 원본 event log 및 guard/resource 로그는 서버 run 디렉터리에 보존되어 있다.
