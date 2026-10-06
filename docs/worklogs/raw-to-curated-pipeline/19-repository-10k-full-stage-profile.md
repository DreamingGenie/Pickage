# 10,000개 전체 단계 측정 및 repository 엔진 비교

## 변경 범위와 계획
- 사용자 요청: 동일1만개 표본에 대해 전체 pipeline 단계(package_version, downloads, repository, package_snapshot, dependents) 및 repository 내부 구간의 소요시간/원인을 측정하고 실행한다.
- 기존1,000개 실행기/결과와 운영변환은 보존한다. 신규10k 실행기에서 두 구성은 repository만 Spark local[2] / DuckDB로 바꾼다. 나머지 단계는 기존 방식으로 실행한다.
- 전체 단계는 기존처럼 각각 고정된 입력을 사용한다. 앞 단계의 신규 결과를 다음 단계로 연결하는 orchestration 전체 실행과는 다르다.
- 고정sample: sample-ec2-20260916-a1, manifest SHA 2a2a733c505a30023570a67078074acb37ba8ed5659ff703f3e81e87b524f765, identity88c239b0a98fc81fe1ec4cf5e4a1177b0c42813eef6a3794c107d5a89dda05d9. package10,000 version385,622 versions_full991,517 projects5,118. 모든 표본 버전 포함, dependents는 sampled importers이며 전역집계 아님.
- data EC2 단독, CPU2/container7680MiB/엔진4GB 설정/IO32MiB/s/낮은우선순위/networknone, ABBA4회 및 정확한 출력 비교. 원천/DB/운영배포 불변.
- 단계별 wall time·cgroup CPU/메모리/IO, repository Spark action/event(조인·셔플·spill·GC) 및 DuckDB SQL/정규화 구간 측정. 순수 IO와 lazy upstream 계산을 구분하고, 계측으로 확정할 수 없는 대기 원인은 미확정으로 남긴다.
- weekly와서비스감시를 유지하며 실험만 자동중단/정리한다.

## 실제 진행과 결과
- 준비 착수, 서버10k실험 미시작. 준비/시험과 실측 결과를 후속 분리 기록한다.

### 검증 및 실행 시작
- 신규10k host/entry/profiler 관련12개 테스트 통과. 기존1k실데이터에서 계측 DuckDB71개 query 완료, 계측 전 Spark6종과 exact 결과 일치.
- ZIP SHA2640354637bcd7fc3e5f63c5ad1e0e078d8be8c9f19fef076a43822ee37b323b, code347파일을 새run에 고정했다.
- 서버사전검사 READY: weekly restart0, checkpoint age26.6초, 약13.2GiB사용가능, pressure0, 경쟁실험없음, 입력19파일84,298,175bytes SHA확인.
- data `/home/ubuntu/pickage-experiments/repository-duckdb10000-20260917-a1`, supervisor PID3268901로 detached시작. Spark→DuckDB→DuckDB→Spark 각각전체5단계를 실행한 뒤 전체출력exact비교.
- Spark action wall/cgroup CPU·IO, Spark task shuffle/spill/GC/event logs; DuckDB query/fetch/cgroup delta와Python URL정규화별도시간; 전체단계 wall/cgroup와0.25초memory샘플기록.
- 단계 시간에는 진단 부대비용이 포함될 수 있다. repository engine_seconds는 event요약 작성 전 구간으로 별도 기록한다. action 합계 밖의 시간은 미귀속으로 표시하며 임의로네트워크/IO원인으로 단정하지 않는다.

### 전체 단계 원인 분석 보강
- ABBA 실행에서 dependents도 64~75초의 큰 구간으로 확인되어, 기존 실행 코드/결과를 수정하지 않고 별도 `full-stage-diagnostic10000-20260917-a1` 1회 진단을 준비했다.
- 비repository 4단계를 cProfile로 계측하여 함수별 self/cumulative 시간 및 호출 횟수를 저장한다. Node 하위 프로세스의 계산은 Python 대기 시간에 포함되며, 중첩 cumulative 시간을 합산하지 않는다.
- 진단은 같은 자원/weekly guard 아래 ABBA 종료 후 순차 실행하며, 5단계 모든 결과를 완료된 Spark 기준 결과와 다시 exact 비교한다. 진단 오버헤드가 있는 시간을 ABBA 평균에 섞지 않는다.
- 진단 ZIP SHA `9fb7790fde8fba01e207d4a9d44ba69bef942c94d7414f86a7d9c0c3fb578992`, 코드348파일. 프로파일 성공/예외 시 산출물 보존 확인, 관련12테스트 재통과.

### 1차 실측과 비교기 문제
- ABBA 4회 전처리는 모두 exit0/OOM없음으로 완료했다. 다만 전체 출력 비교 중 JSON 385,622행씩 양쪽을 `executemany`로 다시 넣는 기존 비교기의 병목을 확인했다.
- 해당 run 라벨을 확인한 뒤 **compare 컨테이너만** 중단했다. 원 run은 의도적으로 `FAILED / Phase failed: compare` 상태를 보존하며, 이를 전처리 실패로 해석하면 안 된다. 완료된 4회 산출물은 불변이다.
- 신규 비교기는 우선 SQL `EXCEPT ALL` 양방향으로 전체 행을 비교한다. 동일 baseline 변환의 JSON 문자열도 정확히 같으면 정규화가 불필요하다. 실제 차이가 있을 때만 기존 JSON 정규화 비교로 후퇴한다. 표본 검사/해시만 비교로 약화하지 않는다.
- 미실행 a1 진단 준비본을 보존하고, a2 진단 새 ZIP `b001998876de1d26a75f792799bfdb24b994ac7b5be19ea2db264c20a6116197`을 배치했다. READY 재확인 후 PID3294085로 시작. 기존 4회와 신규 진단 1회의 모든 결과를 함께 검증한다.

| 단계 | Spark repository 구성 평균(초) | DuckDB repository 구성 평균(초) |
| --- | ---: | ---: |
| package/version | 11.967 | 13.432 |
| downloads | 0.437 | 0.486 |
| repository | 83.910 | 11.742 |
| package_snapshot | 0.961 | 0.937 |
| dependents | 66.950 | 68.982 |
| 전체 단계 실행 | 164.244 | 95.599 |

- 반복별 전체: Spark168.791/159.696초, DuckDB104.673/86.525초. 엔진 외 단계 변동도 있으므로 2회 평균을 일반적 성능 보장으로 확대하지 않는다. 전체는 약1.72배, repository는 약7.15배 차이.
- Spark repository: 초기화/종료6.446~7.644초, 입력 count3.323~3.488초, 검증/보고 action35.133~38.745초, 출력 action24.805~25.238초, 출력 재조회1.148~0.955초. action 외 시간 및 진단 요약 작성 시간은 별도다.
- 주요 Spark action: raw join 유효성 확인11.297/15.727초, metric 저장 action16.143/16.202초. 후자는 lazy upstream 계산을 포함하므로 순수 파일 쓰기 시간이 아니다.
- 각 Spark 실행100 jobs/227 stages/548 tasks, shuffle local read/write 각각122,576,602bytes, remote read0, memory/disk spill0. GC task합1.631/1.507초(동시 task 중복 가능). 단순히 네트워크나 spill 때문이라는 설명은 이번 증거와 맞지 않는다.
- DuckDB의 가장 큰 실제 SQL은 URL 매핑8,097개를 `executemany INSERT INTO url_map` 하는 구간: 8.578/6.527초. 현재 profiler의 자동 category는 candidates_selection으로 분류하지만, 원 SQL로 보면 URL 매핑 적재다. URL 문자열 정규화 자체와 구분한다.
- Spark repository cgroup CPU평균163.061초/벽시간83.910초(평균1.94코어); DuckDB15.508/11.742초(1.32코어). task CPU와 전체 JVM/driver CPU는 동일 지표가 아니다.
- 단계별 memory는 해당 시간대 컨테이너 전체 관측 최대치로, SparkContext.stop 뒤 남아 있는 JVM/allocator 메모리가 후속 단계에도 포함될 수 있다. 각 단계 독립 메모리 요구량으로 해석하지 않는다. package_version 시작 시 io.stat 미생성으로 IO delta는 null이며 0으로 간주하지 않는다.

### 완료 증거 및 전체 단계 원인 진단
- 추가 진단 a2 `COMPLETE`, 비교 `VERIFIED`: 22종 출력 × 5회(기준 자기비교 포함) = 110개 그룹의 전체 행 다중집합/논리 스키마 일치. repository 품질 보고서도 ABBA4회 모두 정확히 일치한다.
- 개선 비교 단계는 컨테이너 생애 기준39.534초. 중단한 기존 비교는233.902초까지 완료하지 못했다. 비교 시간이 전처리 평균에 포함되지 않는다.
- ABBA guard375/weekly255개 및 진단 guard59/weekly42개 관측에서 issue0. 두 run 모두 cleanup_errors=[], 남은 소유 컨테이너0. 운영 배포/설정/DB/MinIO 정식게시 변경없음.
- 원 run의 FAILED 표시는 비교기만 수동 중단한 이력이다. 이후 별도 run에서 **동일 보존 결과의 검증을 완료**했으며 원 결과 JSON 상태를 소급 수정하지 않았다.
- 증거 정본: [전체 실행·프로파일·검증 결과](evidence/full-stage-10k-ec2.json). 개별 pstats 원본은 data EC2 진단 run `output/duckdb-1/*-python-profile.pstats`에 보존. 저장한 JSON에는 함수 전체 목록/호출횟수/self/cumulative 시간이 들어 있다.

별도 진단 1회(성능 평균에 미포함):

| 단계 | 전체 초 | 계측된 주요 내부 시간 |
| --- | ---: | --- |
| package/version | 10.012 | DuckDB execute self8.342초/69회, URL정규화 cumulative1.328초/8,097회, export cumulative0.682초/7회 |
| downloads | 0.380 | DuckDB execute self0.337초/59회. 검증 reject cumulative0.070초(13회), schema0.030초(10회) |
| repository | 8.018 | 별도 SQL 프로파일 사용; 비교용 평균에는 이 진단을 합치지 않음 |
| package_snapshot | 0.816 | 실제 _build cumulative0.446초, 내부 execute self0.395초/62회. 최초 모듈 import 약0.33초 |
| dependents | 55.612 | population2.987초, _resolve_partition49.964초, aggregate_partition0.628초. 나머지는 출력/검증/import/계측 등 |

- 표의 self와 cumulative는 서로 더할 수 있는 별도 항목이 아니다. export/reject/SQL처럼 호출 관계가 겹치는 구간은 중복된다.
- dependents의 주요 병목은 `_resolve_partition`(약90%)이다. target5,000개에 대해 후보 버전 및 요구사항을 반복 조회하고 요청 크기 제한에 맞춰 Node 메시지를 만든다. 전체 단계에서 DuckDB execute10,783회/self29.154초, JSON encoder iterencode self9.046초, Node request722회/cumulative6.067초가 관측됐다. 이는 해석 구간의 하위 비용을 이해하는 증거이지 서로 독립적인 전체 단계 분할표는 아니다.
- Node request 시간에는 통신/응답 대기 및 Node 계산이 함께 포함된다. Node 내부 semver 함수별 CPU 시간은 이번 Python 프로파일로 분리되지 않는다.
- 처리량: 원천버전991,517 → Curated385,622; 적격 source382,430, 전체 선택 선언2,880,249, 대상 연결 선언126,755, 후보 조건 비교4,937,676. 최종 SQL 집계0.628초보다 패키지별 조회/요청 준비/조건 해석49.964초가 훨씬 크다.
- 원천에 extraction_error17,480개와 unresolved declaration5,744개가 있어 dependents resolution_status=PARTIAL이다. 계산은 완료됐으며 양쪽 출력이 같은 것이다. 품질 결측이 해소됐다는 의미는 아니다.

### 해석과 다음 개선 후보
1. 이번1만개/CPU2/로컬파일 조건에서는 repository DuckDB가 유리하다. 전체 단계 실행 평균164.244→95.599초(약42%단축), repository83.910→11.742초(약86%단축).
2. DuckDB repository URL mapping의 행별 executemany를 묶음 적재로 바꾸는 것이 관측 기반 후보다. 아직 최적화하지 않았다.
3. dependents는 패키지별 반복 SQL과 요청 크기를 확인할 때 반복되는 JSON 직렬화를 먼저 검토한다. 최종 집계 분산은 이 표본에서 우선순위가 낮다. 아직 알고리즘/정책을 변경하지 않았다.
4. 전체 단계별 고정 입력 실험이며 MinIO 입출력, 새 raw 입고 트리거, DB적재, 결과를 다음 단계에 연결하는 전체 orchestration 성능은 포함하지 않는다. sampled importers만 사용했으므로 실제 전체 그래프 성능으로 일반화하지 않는다.
5. JVM heap4g와 DuckDB memory_limit4GB는 동일 RSS 한도가 아니다. 컨테이너 상한은 동일7680MiB이다. OS cache를 비우지 않았으며 운영 동시부하/실행 순서 영향을 포함한2회 결과다.

### 검증
- 관련12개 테스트 통과(비교기 수정 후 재실행 포함), cProfile 성공/예외 시 결과·예외·진단파일 보존 smoke 통과.
- 서버4회 원본 전처리 exit0, 별도 진단 exit0, 전체 결과 exact 비교110그룹 통과. 실제 서버 실행으로 Spark/Python/Node 통합을 확인했다.
- 커밋/운영반영은 하지 않았다. 기존 주간 수집 통합 변경과 이전 실험은 보존했다.
