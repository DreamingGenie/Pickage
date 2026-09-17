# Repository Spark local[2] vs DuckDB 실험 준비

## 변경 범위와 작업 계획
- 기존 repository Spark 변환/운영 실행기는 보존한다. 실험 전용 DuckDB 구현과 비교 실행기를 추가한다.
- 입력 검증, 후보 정렬/URL 정규화, GitHub/GitLab 비교 규칙, NULL·충돌, 6종 출력과 보고 계약을 유지한다.
- 양쪽 모두 동일 로컬 Parquet 입력 및 출력, CPU 2, 컨테이너 7680MiB, 엔진 메모리 설정 4GB(엔진별 의미 차이 기록), 낮은 우선순위/IO 제한으로 비교한다. MinIO 통신을 측정 구간에서 제외한다.
- 신규 프로세스/컨테이너에서 Spark→DuckDB→DuckDB→Spark 순서로 실행해 순서 영향을 노출한다. OS cache는 비우지 않는다. 시작 포함 시간과 변환 시간, cgroup CPU·메모리, 정확한 결과 비교를 별도 기록한다.
- 이번 범위는 로컬 구현·검증·실행 준비이다. 운영 배포 변경, 서버 실험 시작, DB 적재, 공식 Curated 게시 없음.

## 검증 계획
- 예외·NULL·충돌·동률 선택·시점/스키마 오류 테스트.
- 6종 결과의 논리 스키마와 exact row multiset 대조. 비교 실패 시 성능 우위로 판정하지 않는다.
- 동일 frozen 1,000 package manifest 및 파일 SHA를 실행 전/후 검증한다.

## 진행 및 결과
- 준비 착수. 실제 서버 성능 수치는 미측정이다.

### 구현 및 검증 결과
- 신규 `pipeline/spark_experiment/repository_duckdb.py`: Spark 없는 DuckDB 변환. SQL 임시 테이블·조인·집계와 distinct URL 4,096개 단위 정규화를 사용한다. 기존 Spark 변환은 변경하지 않았다.
- 신규 runtime `repository_duckdb_entry.py`, `repository_duckdb_host.py`, `repository_duckdb_prepare.py`: 단일 trial/정확 비교, data EC2 ABBA supervisor, 로컬 배포 번들 생성.
- 기존 frozen 1,000개 표본의 repository 입력 4파일(약3.6MB)과 이전 Spark 출력만 서버에서 읽어 로컬로 복사했다. 입력은 원래 manifest SHA/파일 SHA, 출력은 서버에서 읽은 파일 SHA로 확인했다. 원래 manifest/report는 덮어쓰거나 현재 코드 해시로 재표기하지 않았다.
- 로컬 DuckDB 1.5.5 실행: 입력 package 1,000 / version 40,417 / versions_full 106,393 / projects 672. 출력 6종의 논리 스키마와 정확 행 multiset 일치, 품질 report 완전 일치. `evidence/repository-duckdb-local.json`에 서로 다른 기준/후보 코드 해시와 비교 결과를 보존했다.
- 타임존 정규화 보완 중 추가 Projects 열 `ForksCount`가 빠지는 것을 실데이터 exact schema 비교가 검출했다. 원래 열 전체를 유지하도록 수정하고 6종 비교를 다시 통과했다. UDF 등록/출력 테이블명 문제도 로컬 fixture 단계에서 수정했다.
- 단위 테스트 19개 통과: 변환 8개(UTC annotated Parquet 및 +09:00 동일 시각 포함), entry input hash/비교 gate 7개, host 스케줄·격리·CLI 4개. DuckDB 실행 환경은 원래 저장소 `.venv-bq/Scripts/python.exe`를 재사용했으며 새 의존성을 설치하지 않았다.
- entry의 DuckDB 전체 경로도 로컬에서 COMPUTED 및 report/telemetry 파일 생성 확인. Windows에는 cgroup가 없어 이 로컬 telemetry를 서버 메모리 측정으로 해석하지 않는다.
- 로컬 PySpark 미설치: 신규 Spark trial은 로컬에서 실행하지 않았다. 이번 exact 비교는 이전 서버 Spark 결과를 기준으로 했으며, 실제 성능 실험은 새 Spark trial 2회와 DuckDB 2회를 같은 서버에서 다시 측정한다.

### 실행 준비물과 후속 실행 절차
- 최종 로컬 번들: `C:/Users/SSAFY/AppData/Local/Temp/repository-duckdb1000-20260917-ready.zip`
- ZIP SHA256: `bc0ebacbf44e5a423eefd810e356859ef131eb6c23f55cbc59b7ea3431d2bc32`, pipeline code 344파일 및 prepared.json 해시 목록 포함. 앞서 생성한 `repository-duckdb1000-20260917-a1.zip`은 수정 전 번들이므로 사용하지 않는다.
- 서버 예상 경로: `/home/ubuntu/pickage-experiments/repository-duckdb1000-20260917-a1`. 아직 생성/업로드/실행하지 않았다.
- 후속 실행 시 새 디렉터리에 최종 ZIP을 풀고 `jars`를 기존 `sample1000-ec2-20260916-a2/jars`에 연결한다. 기존 pinned Docker image를 사용한다. 원천 입력은 기존 frozen 디렉터리를 읽기 전용 mount한다.
- 새 디렉터리의 `code`에서 아래 사전검사 후 통과 시 detached supervisor로 실행한다. 실행 코드는 원격으로 준비한 snapshot 안에서 호출해야 한다.

```sh
python3 -m pipeline.spark_experiment.runtime.repository_duckdb_host --check
python3 -m pipeline.spark_experiment.runtime.repository_duckdb_host
```

- `--check`는 frozen manifest/전체 입력 SHA/코드 목록 SHA/image/weekly/service·디스크 여유를 검사한다. `WAITING`이면 실행하지 않는다.
- 4개 trial 및 비교는 별도 fresh container, network none, CPU2, memory/memswap 7680MiB, nice10, CPU shares128, 디스크 read/write 각32MiB/s. 낮은 CPU 우선순위는 CPU 예약/서비스 무영향 보증이 아니다.
- JVM heap4g와 DuckDB4GB는 같은 총 메모리 상한이 아니다. 컨테이너 상한을 동일하게 하고 실제 사용량을 별도로 측정한다.
- 출력: `output/<trial>/report.json`, `telemetry.json`, `output/comparison.json`, `metrics-<trial>/container-summary.json`, `weekly-guard.jsonl`, `guard.jsonl`, 최종 `result.json`.
- exact 비교 또는 report가 다르면 VERIFIED/COMPLETE로 처리하지 않는다. 실행 중 오류 시 해당 run의 로그를 보존하고 실험 label 컨테이너만 정리한다.
- 서버 실험·상태 사전검사는 이번에 미실행. 실제 속도 개선 수치, 운영 교체 가능 여부, 서버 성능 검증은 아직 미확정이다.

### 서버 실험 시작 (사용자 후속 승인)
- 2026-09-17 data EC2 새 run `repository-duckdb1000-20260917-a1`에 최종 번들 SHA를 검증하고 준비했다.
- 사전검사 READY: weekly 동일 container/restart0, checkpoint age13.2초, 사용 가능 메모리 약13.2GiB, IO/memory pressure0, 다른 실험 없음.
- supervisor PID3258081로 detached 시작. ABBA 4회 및 exact 비교를 자동 실행하며 SSH 연결 종료와 무관하게 감시/정리를 수행한다.
- 기존 배포/서비스 설정은 변경하지 않았다. 결과는 후속 확인 후 기록한다.

### 서버 실험 완료 (2026-09-17)
- run `repository-duckdb1000-20260917-a1`: 최종 COMPLETE, 비교 VERIFIED, 4개 trial 및 compare 정상 종료. 새 Spark 결과를 기준으로 DuckDB 2회와 Spark 재실행의 6종 logical schema / exact row multiset 및 품질 report가 모두 일치했다.
- 동일 data EC2 / CPU2 / container7680MiB / network none / 로컬 고정 입력·출력 / 낮은 우선순위·IO 제한. 기존 배포 구성은 변경하지 않았다.

| 순서 | 엔진 | 시작·종료 포함 engine seconds | transform seconds | container peak MiB |
| --- | --- | ---: | ---: | ---: |
| 1 | Spark local[2] | 47.824 | 42.502 | 2085.3 |
| 2 | DuckDB | 1.488 | 1.354 | 138.7 |
| 3 | DuckDB | 1.631 | 1.479 | 153.7 |
| 4 | Spark local[2] | 47.574 | 42.680 | 1909.3 |

- engine seconds 평균: Spark47.699초 / DuckDB1.560초, 이번 표본에서 약30.6배, 시간 약96.7% 감소. transform 평균42.591초 / 1.417초이므로 JVM 시작 비용을 제외해도 큰 차이가 남았다.
- engine seconds는 입력 SHA 검사/사후 exact 비교/컨테이너 생성·감시 시간과 구분된다. 메모리는 새 컨테이너 전체 수명의 cgroup peak이고 Python/JVM뿐 아니라 파일 cache 등도 포함하므로 순수 heap 사용량이 아니다.
- ABBA 순서로 각2회이며 OS cache를 비우지 않았다. 전체 스냅샷 처리량/메모리 한도에서도 같은 배율인지는 미검증. 현 결과는 repository 단계의 1,000개 입력에 한정하며 운영 엔진 교체는 수행하지 않았다.
- service guard59개 관측, weekly guard47개 관측 모두 issue0. weekly restart0, checkpoint 갱신 지속. 종료 후 weekly 실행 중 및 MinIO/MLflow healthy. API peer health는 실행 동안 guard에서 확인했다. 모든 요청의 성능 영향0을 보장하는 측정은 아니다.
- 실험 label 컨테이너 잔존 없음, cleanup 오류 없음. 로그/Parquet/telemetry는 서버 run 디렉터리에 보존했다.
- 상세 증거: `evidence/repository-duckdb-ec2.json` (4회 보고, 정확 비교, 컨테이너 자원, guard 요약, 종료 상태).
