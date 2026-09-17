# Repository data 2core vs data 2 + app 2core

## 변경 범위와 계획
- 사용자 승인으로 동일 1,000 package의 repository만 baseline local[2]와 EC2 두 대 executor 2core씩 분산 실행하여 비교한다.
- 원본 성공 실험의 고정 입력/변환 코드를 별도 run repository22-20260917-a1로 복사한다. 현재 미커밋 weekly 통합 변경은 섞지 않는다. raw/DB/공식 Curated는 변경하지 않는다.
- baseline은 data CPU 2 / heap4g / container7680MiB. 분산은 data/app executor 각각2core / heap4g / container5632MiB, data driver heap1g / CPU1 / container2048MiB, master CPU0.25 / 512MiB. 추가 코어뿐 아니라 추가 메모리/driver 자원과 MinIO 입출력이 달라진다.
- 양 노드 worker는 낮은 우선순위와 읽기/쓰기 각각32MiB/s, 추가 swap 없음. weekly 단계/진행/부하 guard와 API/DB/web/service guard를 유지한다. 실험 프로세스만 종료 가능.
- 시작 전 app similarity-loader가 자격증명 파일 누락으로 이미 127회 재시작했다. API/DB/web은 healthy. 이 기존 실패를 실험 결과와 분리하고, 해당 정확한 컨테이너와 오류 서명만 좁게 감시 예외로 처리한다. 정상 서비스의 상태/재시작 감시는 유지한다. 기존 서비스 수정/재시작은 하지 않는다.
- barrier4개가 각 EC2에서2개씩 실행되는지 확인하고, 실제 repository task도 양쪽에서 실행됐는지 event log로 검증한다.
- baseline/분산 각각 상세 action 및 event 지표를 저장하고 repository6개 출력의 정확한 행 multiset 일치를 확인한다.

## 검증과 결과
준비 진행 중. 실제 결과는 아래에 후속 기록한다.
### 실행 준비 및 시작 (2026-09-17)
- 로컬 단위 검증: repository22_app/data/entry, repository_profile/summary, weekly_priority 관련 30개 테스트 통과.
- 양쪽 EC2 코드 SHA: `55d71badd7c33e526d3eeb6facb9d83680c5b84a34455ab8850d2467b2873e30`. 배포 ZIP SHA256: `53cc2810585c0c276cc3442d7152525451706a8d89ffcabec64cf5e5bf0c1044`.
- 고정 입력 identity: `99a4ed92c0976834b6178d9979fea4fc7a83cc0bec4786fe1d235aaf02e4648e`. package 1,000, version 40,417, versions_full 106,393, projects 672. 모든 버전 포함, 전역 dependents 성능 실험은 아님.
- app supervisor PID 2267622, data supervisor PID 3235836으로 분리 실행. SSH/대화 종료 후에도 supervisor와 guard가 실행 및 정리를 담당한다.
- data 사전 검사 READY, weekly checkpoint age 3.75초, restart 0, available memory 약13.2GiB. app도 사전 검사 통과.
- 시작 직후 baseline 실행 확인, app worker는 전용 master 시작 대기. 양쪽 service guard issue=null 확인. 기존 similarity-loader 실패는 별도 기록되어 있으며 수정하지 않음.
- 서버 경로(양쪽 동일): `/home/ubuntu/pickage-experiments/repository22-20260917-a1`. 실행 상태 `status.json`, 최종 결과 `result.json`, 서비스 감시 `guard.jsonl`.

### 측정 완료 (2026-09-17 13:39 KST)
- data supervisor `COMPLETE`, baseline/spark/compare exit 0, OOM 없음, cleanup_errors=[]; 양쪽 실험 label 컨테이너가 모두 제거된 것을 확인했다.
- 비교 `VERIFIED`: 출력 6종의 논리 스키마와 정규화된 정확한 행 multiset 일치(파일 바이트 비교 아님). metric 1,000 / selection 1,000 / candidates 40,417 / observations 672 / conflicts 0 / unmapped 0.
- 실제 repository action task: data 220개 + app 145개, 실패 0. 별도 barrier도 data 2 + app 2 동시 실행 확인. worker 등록만으로 분산 실행을 주장하지 않는다.

| 지표 | data local[2] | data 2 + app 2 |
| --- | ---: | ---: |
| report repository seconds | 55.987 | 87.981 |
| supervisor phase seconds | 61.581 | 126.711 |
| 최초 metric 계산+쓰기 action | 12.688 | 20.597 |
| package 입력 count action | 2.629 | 6.672 |
| action task disk spill | 0 | 0 |

- 표본 1회에서 분산 repository 시간이 약57.1% 더 길었다. baseline repository 시간에는 Spark local startup 5.363초가 포함된다. 분산은 별도 session 시작 및 barrier 확인 25.097초가 repository 시간 밖에 있으며, master/worker 준비는 phase 시간 밖에도 있다. 따라서 위 두 시간 기준을 전체 운영 지연으로 오인하면 안 된다.
- baseline 컨테이너 peak 2.269GiB; 분산 data worker 1.257GiB, app worker 1.482GiB, driver 0.667GiB, master 0.178GiB. 서로 다른 시점의 peak이므로 합계를 동시 최대 사용량으로 표현하지 않는다. 새 컨테이너의 전체 수명 기준이다.
- 분산은 코어/메모리와 driver 자원뿐 아니라 로컬 파일 대신 MinIO 입출력도 달라졌다. 코어 수만의 인과효과나 전체 스냅샷 성능을 입증하는 실험이 아니다. action 시간에는 lazy upstream 조인/집계도 포함되어 순수 파일 쓰기 속도가 아니다. 세부 병목 비교 자료는 evidence에 보존했다.

### 서비스 감시 결과와 판정 제한
- weekly 85개 관측 issue 없음, 동일 container / restart 0, checkpoint 갱신 지속. data service guard 123개 관측 issue 없음. 종료 후 weekly 실행 중, data MinIO/MLflow healthy 확인.
- app API/web/PostgreSQL 종료 후 healthy. app guard 129개 중 기존 similarity-loader 자동 재시작 순간 4회 `Known failed loader recovered or stopped`가 기록됐다(약60초 주기). 연속 3회 중단 조건에는 해당하지 않았으며 작업은 완료됐다.
- app supervisor는 실제 종료 원인 `EXPECTED_MASTER_STOP`, cleanup_errors=[]이나 단 한 번의 guard issue도 실패로 유지하는 정책 때문에 최종 `FAILED / GuardIssue`로 기록됐다. 이를 성공으로 덮어쓰지 않았다. Spark 처리 실패/결과 불일치와 구분해야 한다.
- 기존 loader는 실험 전부터 자격증명 파일 누락으로 실패했으며 종료 후에도 같은 상태다. 운영 설정을 변경하지 않았다. 알려진 실패를 검사하는 코드가 재시작 중 잠깐의 running 상태를 회복으로 판정하는 문제가 있어, 다음 실행 전 전이 상태와 지속 회복을 구분하는 보완이 필요하다. 현재 실험을 무경고 운영 검증 통과로 선언하지 않는다.
- health/checkpoint 관측은 모든 사용자 요청에 대한 영향 0을 보증하지 않는다.

### 보존 자료
- `evidence/repository22/data.json`: 정확 비교, action/event 요약, data/weekly guard 요약, 결과 상태.
- `evidence/repository22/app.json`: app 결과, guard 경고 원문, worker 자원 요약.
- `evidence/repository22/data-tasks-resources.json`: repository 실제 task 호스트별 집계, 실패 수, data 컨테이너 자원 요약.
- 원본 상세 로그·event·행동별 JSONL은 각 서버의 실험 디렉터리에 보존했다. 공식 Curated 게시/DB 적재/운영 배포 변경은 수행하지 않았다.
