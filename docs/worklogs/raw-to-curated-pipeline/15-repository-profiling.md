# 1,000개 기존 방식 repository 상세 측정 준비

## 변경 범위와 계획
- S15P21A506-372 후속 실험. 기존에 승인한 Jira 연결 보류를 유지한다.
- 기존 성공 표본 sample1000-ec2-20260916-a2의 입력 파일과 manifest를 읽기 전용 재사용한다. 재표집하지 않는다.
- data EC2의 기존 방식 전체 5단계 실행, repository 내부만 상세 계측한다. local[2], JVM 4GiB, 컨테이너 CPU 3 / RAM 7680MiB / swap 0 유지.
- 변환 코드와 출력 계약은 변경하지 않는다. 실험 전용 context에서 기존 count/collect/parquet 작업에 타이머와 Spark job group을 부착한다. 추가 count/cache/최적화는 하지 않는다.
- Spark 시작/종료와 각 action의 경과 시간, Spark task CPU/GC/shuffle/spill/input/output 지표를 기록한다. lazy 연산은 그것을 실행한 action에 비용이 포함된다는 한계를 명시한다.
- 기존 서비스 guard, 컨테이너 모니터, heartbeat, 시간/디스크 제한을 재사용한다. 운영 배포, DB, MinIO 원본/공식 Curated는 변경하지 않는다.
- 이번 요청은 실험 환경 세팅이며 실제 1,000개 재실행은 자동으로 시작하지 않는다. 준비 검증과 실측 결과를 구분한다.

## 검증 계획
- fake Spark API로 기존 작업 호출 횟수/반환/예외/job group 복원 검증.
- 합성 Spark event log로 CPU/GC/shuffle/spill 합산 및 실패 task/공유 stage/불완전 로그 검증.
- 서버 읽기 전용 입력/이미지/환경 확인, 별도 실험 경로에 코드와 실행 명령 준비.
- 재실행 시 repository 6개 결과를 과거 결과와 행 중복을 포함해 비교한다. 실행 코드 identity가 다른 사실을 보존하며 과거 hash를 새 hash로 위장하지 않는다.

## 실제 수행 및 결과
- 로컬 계측/이벤트 집계 테스트 10개와 기존 cluster 검증 테스트 5개, 총 15개 통과. 새 Python 4개 구문 검사 및 git diff --check 통과.
- data EC2에 `/home/ubuntu/pickage-experiments/repository-profile1000-20260917-a1` 준비 완료. 기존 성공 실험의 code를 별도 복사하고 새 진단 모듈 4개만 추가했다. 이전/현재 repository transform SHA256은 `775db1b2001e428eea4b80abeaf854a949678109622f642f149e10995eb830e5`로 일치한다. 주간 통합 작업의 미커밋 변경은 이번 실험에 섞지 않았다.
- source manifest SHA256 `47a2cea179b368577891005102785ca801ee413b3df6e9abf9118c4bd45c11f6`, input identity `99a4ed92c0976834b6178d9979fea4fc7a83cc0bec4786fe1d235aaf02e4648e` 확인. 입력 19개 파일 크기/SHA를 서버에서 검증했다.
- 같은 패키지 1,000개, 원천 버전 106,393개, Curated 버전 40,417개, 저장소 통계 672개. 이번 준비는 재표집/재수집/MinIO 업로드를 하지 않는다.
- 서버 preflight는 `WAITING`: `pickage-weekly-run` 컨테이너가 실행 중이다. 다른 작업 종료 전에는 실행기가 시작을 차단한다. 자동 대기/자동 시작은 설정하지 않았다.
- 새 실험 컨테이너, Spark 작업은 시작하지 않았다. 로컬 Docker도 가동 중이 아니므로 실제 Spark로 새 계측기를 구동하는 smoke 및 새 1,000개 결과 검증은 아직 미실행이다. 현재 완료 범위는 코드/테스트/서버 배치/읽기 전용 사전검사이다.

## 실행과 결과 확인
data EC2에서 실행한다. 최초 명령은 상태 확인만 하며 컨테이너를 생성하지 않는다.

```sh
cd /home/ubuntu/pickage-experiments/repository-profile1000-20260917-a1
./run.sh --check
# READY이고 실행할 때만 다음 명령을 사용한다.
nohup ./run.sh > supervisor.log 2>&1 < /dev/null &
tail -f baseline.log
```

- `status.json`, `result.json`: 실행/종료 상태와 정리 오류.
- `output/profile/baseline/report.json`: 기존 5개 단계 시간. 전체 연결 파이프라인이 아니라 이전과 동일한 고정 단계 입력 실험이다.
- `output/profile/repository-actions.jsonl`: 각 action 시작/끝, 소스 줄, 데이터셋, wall time. 실패 직전 START만 있으면 미완료 작업으로 남는다.
- `output/profile/repository-actions-summary.json`: 느린 action 순 정렬, Spark 시작/종료 시간.
- `output/profile/repository-spark-summary.json`: action ID별 task CPU/GC/입출력/shuffle/spill/실패 시도 지표. 원본 SQL 실행 이벤트와 계획은 `output/profile/telemetry/events`에 남는다.
- `output/profile/repository-comparison.json`: 과거 repository 출력 6개와 정확한 행 multiset 비교. 과거/현재 코드 hash를 각각 기록한다.
- `metrics-baseline/container-metrics.jsonl`, `guard.jsonl`: 컨테이너 자원과 서비스 guard 기록.

## 해석 제한
- count/collect/write는 Spark lazy 연산을 실제 실행하는 action이다. 예를 들어 metric 파일 write 시간에는 앞서 아직 계산하지 않은 후보 정렬·통계 조인이 포함될 수 있다. 이를 순수 파일 쓰기 시간으로 해석하지 않는다. 추가 materialization을 넣어 원래 실행 계획을 바꾸지 않았다.
- action wall time과 task 실행/CPU 합계는 다르다. 동시 task의 GC 시간은 겹칠 수 있고 memory spill bytes는 실제 디스크 기록량과 같지 않다. 물리 디스크 I/O는 cgroup 측정과 함께 본다.
- 계측 비용이 포함된 1회 실험이며, 새로운 속도 향상이나 전체 스냅샷 성능을 입증하지 않는다. 상세 구간에 병목 가설을 좁히는 목적이다.
- 반복 실행은 기존 output/결과를 덮어쓰지 않도록 실패한다. 다음 반복에는 새 run ID를 준비한다.

## weekly 우선 병행 실행 승인 및 변경
- 사용자 요청으로 준비-only에서 실행으로 전환한다. 현재 weekly는 data EC2에서 외부 npm 다운로드 API 대기 위주의 downloads_weekly 단계이며 관측 CPU 0~0.13%, 메모리 약 213MiB이다.
- weekly 컨테이너가 있다는 이유만으로 막던 규칙을 교체한다. 수집 단계 유지, checkpoint 120초 이내 갱신, 가용 메모리 5GiB 이상, weekly anon 1GiB 이하, weekly CPU 0.5core 이하, host IO pressure avg10 10% / memory pressure avg10 1% 이하를 읽기 전용 감시한다. 다음 단계/재시작/갱신 중단/부하 기준 초과 시 실험만 종료한다. 기존 서비스 guard도 유지한다.
- 실험 local[2], JVM 4GiB, 컨테이너 7680MiB/swap 0은 유지하되 CPU 상한을 3에서 2로 줄이고 cpu-shares 128, nice 10, 디스크 읽기/쓰기 각각 32MiB/s 제한을 추가한다. 보호를 위해 바뀐 조건과 weekly 공존 때문에 이전 시간과 동등 조건의 속도 비교로 해석하지 않는다.
- 최대 실행 시간 30분. 입력은 기존 표본 파일을 readonly로 읽고 출력은 실험 폴더에만 쓴다. weekly 컨테이너/데이터/설정은 변경하지 않는다.
- 실제 실행 결과는 아래 후속 기록으로 남긴다.
- 2026-09-17 13:06:54 KST, supervisor PID 3225646으로 백그라운드 실행 시작. 새 guard 정책 테스트 3개 포함 관련 테스트 13개 통과 후 실행했다.
- 최초 실행 확인: package_version 2.689초, downloads 0.219초 완료 후 repository 진입. Spark 시작 5.539초와 입력별 count 시간이 action 로그에 실제 기록되었다.
- Docker 실제 설정에서 CPU 2, CPU shares 128, RAM/swap 각 8053063680bytes(추가 swap 0), 디스크 읽기/쓰기 각 33554432bytes/s, network none을 확인했다.
- 시작 직후 weekly CPU 0.32%, 메모리 212.9MiB, restart 0, 다운로드 checkpoint 갱신 확인. weekly guard issue=null, host memory pressure 0. 이 값은 관측 시점의 상태이며 영향 0을 보장하는 근거로 사용하지 않는다.
- 아직 완료 전이며 최종 결과/정확 비교는 미확정이다. `weekly-guard.jsonl`에 weekly 상태·checkpoint 경과·자원 압력·중단 사유가 추가 기록된다.

## 실행 완료 결과
- 2026-09-17 13:07:59 KST supervisor COMPLETE. 컨테이너 exit 0 / OOM false / cleanup_errors=[]이며 실험 컨테이너 제거 확인. baseline phase(비교 및 컨테이너 감시 포함) 60.971초.
- 단계 시간: package_version 2.689초, downloads 0.219초, repository 48.080초, package_snapshot 0.543초, dependents 3.603초.
- repository 6개 출력 그룹 EXACT_CANONICAL_ROW_MULTISET=EQUAL. Spark 이벤트 로그 완전성 통과, profile job 98개, task attempt 368개, 실패 task 0개.
- 가장 긴 action은 metric/data 최초 쓰기 10.578초(상류 후보 선택/통계 조인 lazy 계산 포함), Spark 시작 5.539초, 첫 package count 2.134초, selection 쓰기 2.067초, raw 매칭 누락 검사 1.807초, candidates 쓰기 1.284초 순이다. 파일 쓰기 action을 순수 디스크 쓰기로 해석하지 않는다.
- task metrics 합계: executor run 21.969초, CPU 10.094초, GC 0.530초(동시 task 중복 가능), memory/disk spill 0bytes, shuffle write/read 각각 1,584,742bytes, task input 20,221,882bytes / output 997,159bytes. 이 표본에서는 메모리 부족에 의한 spill은 관측되지 않았다. DISK_ONLY cache IO와 spill은 다른 개념이다.
- weekly guard 22회 샘플에서 기준 위반 0, 서비스 guard 기준 위반 0. weekly 동일 컨테이너 계속 running / restart 0 / 다운로드 checkpoint 갱신 확인. 최소 호스트 가용 메모리 12,166,971,392bytes(약 11.33GiB), 최대 IO pressure avg10 3.63%, memory pressure 0. 모든 요청 지연에 영향이 0이었다는 의미는 아니다.
- 상세 evidence: `evidence/repository-profile/completion-summary.json`, `baseline-report.json`, `repository-actions.jsonl`, `repository-actions-summary.json`, `repository-spark-summary.json`, `repository-comparison.json`. 원본 Spark event log와 자원/서비스/weekly 감시 로그는 서버 run 디렉터리에 보존한다.
