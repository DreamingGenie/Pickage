# 주간 dependents에 기존 CPU 병렬·가중치 집계 연결

## 변경 범위와 계획

현재 단일 snapshot adapter가 과거의 단일 Node/단일 partition SQL 집계를 사용해
4GB 한도에서 실패했다. 기존 128개 물리 입력 묶음, CPU resolver, weighted-events-v2,
coordinator/worker 완료 receipt를 재사용해 정상 파이프라인 기본 경로에 연결한다.

1. 단일 snapshot 입력을 기존 sharded manifest 계약으로 변환한다.
2. 독립 worker 2개에 총 DuckDB 예산을 나눈다. 현재 실험의 2 threads/4GB는 각 1 thread/2GB이며, 기존 CLI 기본 메모리 2GB는 유지한다.
3. 입력 검증·최종 병합·저장에 고정된 16GB가 적용되지 않도록 예산을 전달한다.
4. 서비스 Parquet/NULL/0/해석 품질을 기존 oracle과 대조하고 receipt 재개를 검증한다.
5. Windows 및 Linux 프로세스 종료 시 worker/Node 정리를 검증한다.
6. 상태 heartbeat의 파일 교체 오류를 재시도하고 상태 갱신 스레드가 죽지 않게 한다.

기존 C:/pg914, C:/pg914r2의 코드·실행·입력·완료 SHA는 변경하지 않는다.
이번 작업은 코드 연결과 로컬 검증이며, 기존 실패 결과를 새 코드로 승인하지 않는다.
원천 전체 source/선정 target·적격 버전·미해석 PARTIAL·NULL 제외 정책을 보존한다.
4GB는 DuckDB 총 memory_limit 예산이다. Python/Node/OS까지 포함하는 RSS 하드 상한과
동일하지 않으므로 전체 프로세스 RSS와 임시 디스크도 별도로 감시한다.

## 실제 수행·검증 결과

### 구현

- 정상 `execute_stage`가 기본으로 `dependents_parallel.calculate`를 호출한다. 기존 직렬 함수는 exact oracle 및 명시적인 `dependents_engine=legacy` 비교용으로 남긴다.
- 전체 적격 source를 유지하고 선정 target 이름을 고정 128개 묶음으로 배분한다. CPU resolver와 `weighted-events-v2`, 기존 coordinator의 승인 receipt를 재사용한다.
- 입력 준비는 매 시도 별도 `prep-<id>/working.duckdb`에서 수행한다. 입력 파일 SHA·adapter/runner 코드 계약을 고정하고, 검증한 shard manifest를 `input-ready.json`으로 연결한다. 준비 DB는 연결 종료와 입력 검증 이후 제거한다.
- 준비 연결을 닫은 뒤 worker를 실행한다. worker 종료 후 grouped history 검증·최종 출력 단계가 같은 DuckDB 예산을 사용한다. 기존 daily history의 고정 16GB 경로는 사용하지 않는다.
- `dependents_workers`는 MinIO I/O `workers`와 분리했다. CPU worker는 1·2·4개, 총 threads는 worker 수 이상 8 이하이다. 4GB/2 workers는 2000MB/worker, 100GB spill은 50000MB/worker가 된다.
- 최종 `version_dependents`, `quality`, `resolution_lookup`의 스키마·NULL/0 의미를 유지한다. 원천 누락·추출 상태 미확인 등 전 모집단의 품질 정보를 보존한다. 파일을 정렬해 부분 업로드 후 재시도에도 같은 내용을 게시한다.
- Linux worker process group과 parent-death signal을 추가하고 Windows Job Object를 유지했다. `/proc` 기반 RSS/CPU 관찰을 추가했다. 종료 시 coordinator 자신의 process group을 죽이는 오류를 검토 과정에서 수정하고 회귀 검증했다.
- CPU resolver의 기존 의존성 `numpy==2.2.6`을 Curated runtime requirements에 포함했다. 새로운 로컬 이미지 `pickage-curated:parallel-local`을 만들었다. 서버 배포는 변경하지 않았다.
- 상태 파일은 고유 임시 파일을 사용하며 Windows 공유 위반을 재시도한다. heartbeat 기록 실패가 스레드를 영구 종료하지 않도록 했다.

### 검증 증거

검증 환경: Windows의 기존 `.venv-repository-metrics`(DuckDB 1.5.5, NumPy 2.2.6),
운영 Dockerfile로 빌드한 Python 3.12/Node 24 Linux 이미지.

| 검증 | 결과 |
| --- | --- |
| Windows historical parallel/pool/input/writer | 28개 실행, 25개 통과, Linux 전용 3개 skip |
| 옵션·CLI·runner·상태 파일 재시도 | 27개 통과 |
| 실제 adapter·3개 파일 exact oracle·중단 후 receipt 재개·입력 변경 거부·빈 입력 | Windows 6개, Linux 6개 통과 |
| Linux full → weekly 실제 6단계, 실패 복구 및 완료 bundle replay | 통과, 합성 패키지 3개, 메모리 S3 사용, DB 미적재 |
| Linux pool 정상/오류 종료·worker 및 coordinator 종료 전파 | 3개 통과, Windows 전용 4개 skip |

Linux weekly/pool 합동 실행은 Docker `--cpus 2 --memory 4g`에서 8개 실행(4개 통과·4개 skip), 20.350초였다.
fixture의 DuckDB 예산은 1GB이다. 이는 4GB DuckDB 설정으로 대규모 입력을 처리한 성능 수치가 아니다.
원문 로그는 `C:/pg914r2/parallel-core-tests.log`, `parallel-orchestration-tests.log`,
`parallel-linux-weekly-tests.log`, `parallel-linux-adapter-tests.log`에 별도로 보존했다.
Linux adapter 6개 테스트는 같은 CPU 2개·컨테이너 4GiB 조건에서 43.537초에 통과했다.

검증 중 하위 작업이 기존 `.venv-bq`에 임시로 설치한 NumPy 2.3.3은 제거해 원래 미설치 상태로 돌렸다.
최종 테스트는 위 별도 환경과 새 Docker 이미지에서 수행했다. 기존 실패 실행의 frozen source/manifest는 수정하지 않았다.

### 남은 실데이터 확인

- 기존 `C:/pg914r2` 전체 실행은 재시작하지 않았다. 기존 실패 실행의 code contract를 새 코드로 덮어쓰지 않는다.
- 전체 실데이터의 완료 시간·최대 RSS·디스크 peak와 DB 적재는 아직 미검증이다.
- 4GB는 DuckDB 예산이며 Python/Node 포함 RSS 상한이 아니다. 운영 컨테이너는 4GiB이고 기존 DuckDB 기본값은 2GB로 유지된다. 기존 coordinator의 별도 RSS/scratch 관찰 및 중단 한도는 유지했다.
- worker 계산 재개 진행은 새 실행의 `dependents/parallel-attempt/parallel-run/progress.jsonl`, `execution-*.json`, `partitions/*/complete.json`과 각 receipt에서 확인한다.
- 커밋·배포·서버 데이터 변경은 수행하지 않았다. 원래 develop 작업 폴더의 기존 untracked 2개도 그대로이다.
