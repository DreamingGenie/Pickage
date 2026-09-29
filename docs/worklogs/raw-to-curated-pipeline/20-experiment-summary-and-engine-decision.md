# 전처리 성능 실험 정리와 DuckDB 채택 결정

기준일: 2026-09-17 / 관련 작업: S15P21A506-372

## 1. 결정과 현재 구현 상태

사용자 결정에 따라 **repository도 DuckDB로 처리하는 구성을 채택한다.** package/version,
downloads, package_snapshot의 기존 DuckDB 처리와 dependents의 DuckDB + Node semver는 유지한다.
Spark 구현과 실험 결과는 비교·회귀 검증 자료로 보존한다.

이 문서는 커밋 전 실험 기록을 정리하고 채택 결정을 남기는 작업이다. 이번 정리에서는
계산 코드, 서버, 배포 설정을 변경하지 않았으며 커밋도 실행하지 않았다.

| 항목 | 현재 상태 |
| --- | --- |
| DuckDB repository 구현 | `pipeline/spark_experiment/repository_duckdb.py`에 구현됨 |
| 기존 Spark와 결과 동등성 | 실제 1천·1만 패키지 표본에서 검증됨 |
| 선택한 구성 | repository 포함 DuckDB, dependents의 Node 버전 해석 유지 |
| 일반 실행기 전환 | **미반영**. `pipeline/repository_metrics/build.py`는 아직 Spark를 호출함 |
| 새 구성의 MinIO 연속 실행·게시 검증 | 미실행. 이번 성능 실험은 단계마다 고정 입력을 사용함 |
| 새 구성의 전체 스냅샷 성능·메모리 검증 | 미실행 |
| 운영 배포·DB 적재 | 이번 실험에서 수행하지 않음 |

채택 이유는 동일 입력·자원 조건에서 repository 출력 계약을 유지하면서 시간을 줄였고,
1만 개에서는 전체 단계 실행 시간도 약42% 줄었기 때문이다. 모든 규모에서 DuckDB가 더
빠르다는 결론이나 운영 반영 완료를 뜻하지 않는다.

## 2. 무엇을 비교했는가

실험 중 사용한 baseline은 순수 비Spark 방식이 아니었다. **repository에는 원래부터
Spark local[2]가 있었고, 나머지 단계는 DuckDB 또는 DuckDB + Node였다.**

| 비교 | 기존 구성 | 후보 구성 | 질문 |
| --- | --- | --- | --- |
| 전체 단계 Spark 전환 | DuckDB + repository local Spark | 두 EC2의 Spark로 각 단계 계산 | 전체 단계를 분산하면 빨라지는가? |
| repository 분산 | data EC2 local[2] | data 2core + app 2core | repository에 두 EC2를 쓰면 빨라지는가? |
| repository DuckDB 전환 | data EC2 local[2] | 같은 data EC2 DuckDB 2threads | Spark를 제거하면 얼마나 달라지는가? |

표본은 패키지 수 기준이며 선택된 패키지의 모든 버전을 포함했다.

| 패키지 수 | 원천 버전 행 | Curated 버전 행 | 저장소 관측 행 |
| ---: | ---: | ---: | ---: |
| 1,000 | 106,393 | 40,417 | 672 |
| 10,000 | 991,517 | 385,622 | 5,118 |

대상 스냅샷은 2026-08-31, 정확 시각은 `2026-08-31T21:01:10.517131Z`다.
실험 중 실행 중이던 weekly의 새 수집 회차를 처리한 결과가 아니다.

## 3. 실험 흐름과 결과

| 순서 | 범위 | 결과와 해석 | 상세 기록 |
| --- | --- | --- | --- |
| 1 | 작은 합성 입력 | 전체 22종 출력 일치. 구현 정확성 확인이며 운영 성능 증거는 아님 | [03](03-spark-experiment.md) |
| 2 | 실제 전체 입력 준비·repository 재시도 | JVM heap4GiB에서 repository 약30분21초 완료, 지표11,080,940행. 전체 파이프라인 완료 시간이 아님 | [08](08-real-reference-run.md), [09](09-repository-heap-retry.md) |
| 3 | 전체 입력 두 EC2 비교 시도 | 서비스 health 감시 실패로 약2시간11분 후 중단. 최종 비교 결과 없음 | [10](10-real-ec2-benchmark.md) |
| 4 | 1만 패키지 두 EC2 시도 | native thread 제한과 종료 보고 오류 발생. 정상 성능 비교에서 제외 | [11](11-sampled-ec2-benchmark.md) |
| 5 | 1천 패키지 전체 단계 비교 | baseline phase56.839초 / 분산 Spark455.899초, 22종 출력 일치 | [12](12-sample1000-ec2-benchmark.md), [13](13-baseline-hostname-fix.md) |
| 6 | 1천 패키지 baseline 상세 계측 | repository48.080초, 단계 시간 합계의87.2%. 병목 위치 확인 | [15](15-repository-profiling.md), [16](16-repository-profile-results.md) |
| 7 | 1천 repository, data2 vs data2+app2 | 55.987초 / 87.981초. 양 EC2 실제 task 실행 및 출력6종 일치 | [17](17-repository-two-node-four-core.md) |
| 8 | 1천 repository, Spark vs DuckDB | 각2회 평균47.699초 / 1.560초, 약30.6배. 출력6종·품질 보고서 일치 | [18](18-repository-duckdb-experiment.md) |
| 9 | 1만 전체 단계, repository 엔진만 변경 | 각2회 평균164.244초 / 95.599초. 전체 출력 일치, 별도 함수별 진단 완료 | [19](19-repository-10k-full-stage-profile.md) |

5번은 로컬 파일과 MinIO 입출력의 차이도 포함한다. 7번은 코어·메모리·driver 자원과
입출력 경로가 모두 달라졌다. 이 수치로 코어 수 하나의 효과를 분리할 수 없다.
서로 다른 행의 수치를 직접 연결해 개선 배율을 계산하지 않는다.

7번의 data 계산·비교는 성공했지만 app supervisor에는 기존 similarity-loader의 자동 재시작을
감시한 경고가 남았다. 원래 `FAILED / GuardIssue` 이력을 보존하며 무경고 성공으로 바꾸지 않는다.

## 4. 채택 근거: 같은 조건의 1만 패키지 비교

두 구성 모두 data EC2 한 대, CPU2, 컨테이너7680MiB, 엔진 메모리 설정4GB,
추가 swap0, 낮은 우선순위, 디스크 읽기·쓰기 각각32MiB/s 제한을 사용했다.
같은 로컬 입력을 읽기 전용으로 제공했고 Spark → DuckDB → DuckDB → Spark 순으로 실행했다.
JVM heap과 DuckDB memory_limit은 같은 종류의 한도가 아니므로 동일 컨테이너 상한과 실측을 함께 본다.

| 단계 | repository Spark 구성 평균(초) | repository DuckDB 구성 평균(초) |
| --- | ---: | ---: |
| package/version | 11.967 | 13.432 |
| downloads | 0.437 | 0.486 |
| repository | **83.910** | **11.742** |
| package_snapshot | 0.961 | 0.937 |
| dependents | 66.950 | 68.982 |
| 전체 단계 실행 | **164.244** | **95.599** |

- repository 약7.15배, 전체 단계 실행 약1.72배 차이. 전체 시간 약42% 단축.
- 반복별 전체: Spark168.791/159.696초, DuckDB104.673/86.525초.
- repository 평균 컨테이너 CPU: Spark163.061 CPU초, DuckDB15.508 CPU초.
- repository 구간 관측 메모리 최대: Spark 약2085MiB, DuckDB 약1061MiB.
  컨테이너 전체 메모리이며 순수 엔진 heap이나 독립 단계의 요구량이 아니다.
- 원천/준비/컨테이너 기동/사후 출력 비교 시간은 위 전체 단계 실행 평균에 포함하지 않는다.
- 다른 단계 코드는 동일하다. 그 단계의 시간 차이는 엔진 변경의 직접 효과로 해석하지 않는다.

## 5. 어디서 시간이 걸렸는가

### Spark repository

1만 표본에서 원천 데이터와 버전의 조인 검증이11.3~15.7초,
최초 지표 생성·저장 action이16.1~16.2초였다. 후자는 상류 조인·집계·URL 처리 등
지연 실행 계산도 포함하므로 순수 파일 쓰기 시간이 아니다.

각 실행에100 jobs/227 stages/548 tasks가 발생했다. 로컬 shuffle read/write는
각각 약117MiB, 원격 read와 메모리/디스크 spill은0이었다. 시작·종료만6.4~7.6초였지만
이를 제외해도 차이가 남는다. 이번 차이를 네트워크나 메모리 부족 하나로 설명할 수 없다.

### DuckDB repository

URL 매핑8,097개를 임시 테이블에 `executemany INSERT` 하는 데6.5~8.6초가 걸렸다.
SQL 프로파일의 자동 분류명은 candidates_selection이지만 원문 SQL로 확인한 실제 작업은
URL 매핑 삽입이다. URL 문자열 정규화 자체와 구분해야 한다. 묶음 적재가 후속 개선 후보다.

### 나머지 단계와 dependents

별도 진단 실행은 cProfile 부대비용이 있으므로 위 ABBA 평균에 합치지 않았다.

| 단계 | 별도 진단 시간 | 원인 계측 |
| --- | ---: | --- |
| package/version | 10.012초 | DuckDB execute self8.342초/69회, URL정규화 cumulative1.328초 |
| downloads | 0.380초 | DuckDB execute self0.337초/59회 |
| package_snapshot | 0.816초 | _build cumulative0.446초, 최초 import 약0.33초 |
| dependents | 55.612초 | population2.987초, 버전 조건 해석49.964초, 최종 집계0.628초 |

dependents는 대상5,000개에 대한 후보 조회와 요청 준비를 반복한다. 전체 단계에서
SQL execute10,783회/self29.154초, JSON encoder self9.046초,
Node request722회/cumulative6.067초를 관측했다. 후보 조건 비교는4,937,676회였다.
**현재 다음 병목은 최종 집계보다 반복 조회·요청 준비·버전 조건 해석이다.**

self와 cumulative, 부모·자식 함수 시간은 중복될 수 있어 단순 합산하지 않는다.
Node request는 통신·대기·Node 계산을 포함하며 Node 내부 함수별 CPU는 미계측이다.

## 6. 실패와 수정 이력

| 현상 | 확인한 원인·조치 | 결과 해석 |
| --- | --- | --- |
| 초기 출력 PermissionError | cap-drop 환경에서 출력 디렉터리 쓰기 권한 부족. 새 실험 출력만 수정 | 데이터 계산 전 실패 |
| 전체 repository heap 부족 | JVM heap4GiB로 새 실행 | repository 재시도 성공, 전체 파이프라인 성공 아님 |
| 분산 입력·실행 환경 문제 | 런타임·공유 경로·입력 hash 고정 및 별도 실행기 보완 | [04~10 기록](04-real-raw-benchmark.md) 참조 |
| 1만 Spark native thread 생성 실패 | app pids.max256 도달 확인, 후속 실험512로 맞춤 | 컨테이너 RAM OOM과 구분 |
| 계산 후 summary 생성 실패 | 종료된 SparkContext의 applicationId 접근. 종료 전 저장하도록 수정 | 계산 로그만으로 성공 판정하지 않음 |
| baseline Java hostname 실패 | network none에서 hostname 해석 실패. loopback hosts 매핑 추가 | 격리·자원 제한 유지 |
| DuckDB 출력 schema 차이 | Projects의 ForksCount 등 추가 열 누락. 원래 열 유지 | 실제 출력 비교로 검출·수정 |
| 최신 1만 비교기 지연 | JSON을 행별 재삽입하는 검증 병목. compare만 중단 후 SQL 전체 행 비교 우선 적용 | 4회 계산 결과 보존, 별도 run에서 검증 완료 |

실패 실행의 상태를 성공으로 덮어쓰지 않았다. 특히 최신 원 run
`repository-duckdb10000-20260917-a1`의 FAILED는 비교기 중단 이력이다.
후속 `full-stage-diagnostic10000-20260917-a2`가 COMPLETE/VERIFIED로
기존4회와 진단1회의22종 출력, 총110그룹(기준 자기비교 포함)을 검증했다.

## 7. 검증 범위와 자료

- 행 수만 확인한 것이 아니라 논리 스키마와 중복을 포함한 전체 행 다중집합을 비교했다.
  최신 비교는 SQL 양방향 EXCEPT ALL을 우선 사용하고 JSON 표현 차이가 있을 때만 정규화한다.
- repository 품질 보고서도 ABBA4회 일치했다. dependents의 원천 결측과 미해결 조건에 따른
  resolution_status=PARTIAL은 남아 있으며, 결과 일치는 데이터 결측 해소를 뜻하지 않는다.
- 최신 두 run의 서비스/weekly guard에서 issue0, cleanup 오류0, 실험 컨테이너 잔존0을 확인했다.
  관측한 health와 checkpoint로 모든 사용자 요청에 대한 영향0을 보장하지는 않는다.
- OS cache를 비우지 않았고 반복은 각2회다. 표본 dependents는 sampled importers 기준이며 전역 그래프가 아니다.
- 최신 관련12테스트, 프로파일 성공/예외 보존 확인 및 서버 실제 비교를 통과했다.
  이전 테스트 수와 합산해 현재 전체 테스트 통과 수로 표시하지 않는다.

| 자료 | 내용 |
| --- | --- |
| [repository-profile](evidence/repository-profile/) | 1천 기존 구성의 action·event·자원·출력 비교 |
| [repository22](evidence/repository22/) | data/app 양쪽 실행·실제 task·guard 경고 |
| [repository-duckdb-ec2.json](evidence/repository-duckdb-ec2.json) | 1천 Spark/DuckDB ABBA 비교 |
| [full-stage-10k-ec2.json](evidence/full-stage-10k-ec2.json) | 1만4회+진단, 프로파일·정확 비교·종료 상태의 정본 |

서버 원본 로그/Parquet/event/pstats는 `/home/ubuntu/pickage-experiments/<run_id>`에 보존한다.
저장소에는 코드·테스트·요약·선별 증거를 남긴다. 런타임 이미지, raw/Curated Parquet,
배포 ZIP, 비밀키·자격증명은 커밋 대상이 아니다.

## 8. 커밋 구분과 후속 작업

현재 미커밋 변경에는 실험과 별도로 **14번 주간 수집 형식 연결 작업**이 포함되어 있다.
한 변경으로 설명하지 않고 아래처럼 구분해 커밋하는 것이 적절하다.

| 구분 | 파일 범위 | 커밋 제목 제안(훅이 Jira 키 추가) |
| --- | --- | --- |
| 주간 raw 인수·Curated 연결 | `pipeline/orchestration`, 관련 curated/downloads/repository input/bridge/weekly_metadata와 weekly 테스트,14번 로그 | `feat: 주간 원천 데이터와 Curated 전처리 연결` |
| 실험·채택 근거 | `pipeline/spark_experiment` 신규 변환·runtime, repository 실험 테스트·weekly_priority 테스트,15~20번 로그·선별 evidence·README | `test: 전처리 엔진 성능 비교와 DuckDB 채택 기록` |

실험 bundle은 당시 작업트리 코드를 고정했으므로, 서로 완전히 독립적인 변경이라고 가정하지 않는다.
커밋 단계에서 diff와 테스트 의존성을 확인하고 명시적 파일 목록으로 stage한다.
`docs/jira`, 임시 산출물, 다른 작업트리의 변경은 포함하지 않는다.

후속 구현 순서:

1. 검증된 DuckDB repository 구현을 일반 pipeline에서 사용할 위치로 연결하고 기존 출력·품질 계약을 유지한다.
2. 기존 실행기에서 raw → package/version → repository 등 직전 단계 결과를 실제로 이어 검증하고 Curated 게시까지 확인한다.
3. 재개·중복 실행·신규 스냅샷·이전 메타데이터 보존을 회귀 검증한다.
4. 더 큰 실제 입력에서 자원 적합성을 확인한다. URL 매핑 묶음 적재 및 dependents 반복 조회 개선은 별도 측정·변경으로 진행한다.

수집 담당자의 원천 입고 구현과 DB 적재 구현은 기존 합의대로 별도 범위다.

## 커밋 전 확인 (2026-09-17)

- 신규 관련 테스트21개 모듈/89개 실행:88개 통과,1개 환경 오류.
- `tests.test_weekly_integration`은 로컬 Python의 PySpark 미설치로 repository 실행 단계에서 중단됐다. 이번 로컬 실행을 전체 통합 통과로 표시하지 않는다. 이전 격리 런타임 검증과 서버 실험 증거는 각 작업 로그에 보존했다.
- 문서 링크·diff 검사 통과. 증거 파일의 비밀키/토큰 패턴을 점검했으며 검출되지 않았다. 원천 Parquet/배포 ZIP/자격증명은 포함하지 않는다.
- 사용자 요청에 따라 주간 raw 연결과 실험·채택 기록을 두 커밋으로 분리한다. 이 문서의 앞선 '커밋 미실행'은 정리 당시 상태이며, 이번 후속 작업에서 커밋한다.

- 커밋 정리에서 Python 파일 끝의 여분 빈 줄만 제거했다. 서버 frozen bundle/해시는 변경하지 않았다. 원본 증거 로그의 공백·제어문자는 그대로 보존하고 코드·문서는 별도로 공백 검사를 통과했다.
