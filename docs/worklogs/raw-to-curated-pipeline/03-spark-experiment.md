# 기존 방식과 Spark 방식 비교 준비 (2026-09-14)

## 범위와 작업 계획

사용자 요청: 기존 전처리를 보존하고 Spark 전처리를 추가하여 같은 데이터의 결과와 성능을 비교한다.
현재 `pipeline.orchestration`과 기존 계산 모듈을 baseline으로 유지한다. baseline은 DuckDB + Node이며
repository 단계는 이미 local Spark이므로 보고서에 순수 비-Spark 방식이라고 표시하지 않는다.

- 별도 실험 모듈에서 baseline/Spark를 명시적으로 선택한다. 일반 실행의 기본값은 바꾸지 않는다.
- 입력 목록·SHA·스냅샷 시각·ID 부모·대상 목록을 고정한다. 두 엔진의 출력과 실행 경로는 분리한다.
- 실제 Spark 계산을 추가한다. package/version, 다운로드, 저장소 지표, package snapshot, dependents를 비교한다.
- 정합성 비교를 먼저 통과해야 성능 비교를 유효하다고 표시한다. Parquet 파일 해시 대신 행·타입·NULL·JSON 의미를 비교한다.
- 실행 시작/종료, 엔진/런타임/자원 설정, 단계별 소요시간과 전체 시간을 기록한다. 캐시 상태와 미측정 지표를 명시한다.
- 로컬 작은 입력으로 두 엔진을 검증한다. 운영 두 노드 실험은 명령·설정·입출력 계약까지 준비하며 서버 부하 작업은 이번에 실행하지 않는다.
- 실험은 운영 Curated의 ID current 포인터나 전체 완료 bundle을 갱신하지 않는다. DB와 수집 API를 호출하지 않는다.

## 역할 분담

주 담당은 실험 입력/실행/비교/증거 기록과 최종 통합 검증을 맡는다. 독립 구현은 Spark package/version,
다운로드·package snapshot, dependents 계산으로 분리한다. 기존 파일은 보존하고 새 파일별 소유권을 나눈다.

## 검증 기준 및 미실행 경계

작은 데이터에서 기존 결과와 Spark 결과가 일치하고, 두 실행의 측정값이 독립적으로 남아야 한다.
Spark 자체 기동 시간과 계산 시간은 구분한다. 작은 fixture의 속도를 전체 운영 데이터 성능으로 일반화하지 않는다.
운영 `.env`, 방화벽, 실제 executor 배치·메모리·셔플·입출력 부하는 운영 실험 전까지 미확인이다.

## 진행 및 이슈

착수: 기존 구현과 운영 Spark 3.5.3 / Hadoop 3.3.4 문서를 기준으로 비교 경계를 확인했다.
세부 실행 결과는 아래에 실제 측정 후 추가한다.

### 기존 버전 보존

사용자 승인에 따라 기존 실행기·테스트·기록 24개 파일을 `df775b8`에 커밋했다.
제목: `feat: raw 데이터를 Curated로 처리하는 실행기 추가`.
이번 Spark 변경은 `pipeline/spark_experiment/`와 전용 테스트/문서에 추가한다.
`codex/raw-to-curated-pipeline` 작업 공간을 계속 사용하고 원래 작업 공간은 수정하지 않았다.
Jira 연결은 앞선 사용자 승인대로 보류했다.

### 실제 구현

1. `prepare`: 기존 입력 검증과 기준 계산을 로컬 Curated 저장소로 우회하여 실행하고 입력을 고정한다.
2. Spark package/version, 다운로드, repository, package snapshot, dependents 계산 구현을 추가했다.
3. `benchmark`: 코드/입력을 고정하고 같은 Docker 이미지 ID·CPU·메모리 상한으로 순차 실행한다.
4. Parquet 22개 그룹을 정규화한 후 `EXCEPT ALL` 양방향 비교로 행·중복·NULL·스키마를 대조한다.
5. 단계/프로세스 시간, 실행 로그, 비교 결과, 미측정 지표와 실패 원인을 기록한다.
6. `cluster-bundle`: 입력과 코드, S3A 경로의 manifest, 운영 client-mode 실행 스크립트를 로컬에 만든다.
   두 worker의 동일한 코드·Python·Node 경로 및 기존 S3A 설정이 사전 조건이다.
   실제 운영 MinIO 업로드나 Spark 작업 제출은 하지 않았다.

### 발견한 문제와 수정

- 기존 Spark 이미지 Python 3.8에서는 이번 비교의 DuckDB 1.5.5 런타임을 설치할 수 없어,
  Spark 배포본을 Python 3.11/Java 17 이미지에 복사한 별도 실험 이미지를 만들었다.
  두 엔진 모두 이 이미지를 사용하며 운영 Spark 이미지에는 적용하지 않는다.
- 입력 준비에 다운로드 aggregation policy 해시가 빠진 것을 기존 집계기 검증에서 발견하여 추가했다.
- Spark 배열 NULL 제거 함수 사용 오류, 집계에 필요한 열을 너무 일찍 제거한 문제를 실제 실행으로 수정했다.
- `description`이 열 값 대신 문자열 `Description`이 된 문제를 행 비교로 발견하여 수정했다.
- dependents의 join 키 형태, 모호한 열, 조건식 괄호, 조회 출력 스키마를 수정했다.
- Node 응답에 제한 시간/프레임 크기 제한과 종료 시 kill fallback을 추가했다.
- 비교기의 CSV 기본 버퍼가 1 GiB를 요구하는 문제를 제한된 버퍼로 수정했다.
  timezone timestamp는 SQL에서 UTC timestamp로 변환하여 별도 pytz 설치 없이 비교한다.

### 검증 범위

실행 로그/실험 데이터는 git에서 제외되는 `data/orchestration-verification/` 및
`C:/Users/SSAFY/AppData/Local/Temp/px-y31l6gk0/`에 보관한다.
원본 실행기 모듈에 대한 `git diff df775b8` 결과는 변경 없음이다.
실험은 개별 단계의 고정 입력 비교이며, 운영에서 Spark 결과를 다음 단계로 연속 전달하고 게시하는
전체 실행기·장애 복구·서버 성능 검증은 완료 범위에 포함하지 않는다.

### 실제 동일 입력 비교 결과

합성 데이터(패키지/버전 각 3개, 2026-08-28~2026-08-31 구간)를 사용했다.
3회 모두 5개 단계와 서비스·품질 출력 22개 그룹이 행/스키마 비교를 통과했다.
결과: `VERIFIED`, 비교 방식: `EXACT_CANONICAL_ROW_MULTISET`.

| 반복 | 실행 순서 | baseline 프로세스 시간 | Spark 프로세스 시간 | 결과 |
| --- | --- | ---: | ---: | --- |
| 1 | baseline → Spark | 28.523초 | 59.294초 | 22/22 일치 |
| 2 | Spark → baseline | 27.739초 | 60.628초 | 22/22 일치 |
| 3 | baseline → Spark | 28.946초 | 59.960초 | 22/22 일치 |

중앙값은 baseline 28.523초, Spark 59.960초다. 작은 입력에서는 Spark 초기화와 작업 분배 비용으로
Spark가 약 2.10배 오래 걸렸다. 이는 운영 데이터 성능 예측이 아니다. 기존 repository 단계도
Spark를 사용하므로 baseline은 DuckDB + Node + local Spark 혼합 방식이다.

- 자원: 두 엔진 모두 2 CPU, 컨테이너 메모리/메모리+swap 상한 6g, 엔진 메모리 설정 2GB.
- 이미지 ID: `sha256:c0d3c108c929c9b675c15d4526c055e88d44dae457e40d5aa98286668655af7c`
- Python 3.11 / Java 17 / Spark 3.5.7 / DuckDB 1.5.5. 운영 Spark 3.5.3과는 별도다.
- 코드 SHA-256: `010fa3294839e24fdd0189b7cf870cdd5246c7e94ba28a231489a138eae54d7f`
- 입력 identity: `029cbaa8fd92822c2223164fc8e85767e1f761797bbed96506f06a6bd7f40de1`
- 상세 결과: `C:/Users/SSAFY/AppData/Local/Temp/px-y31l6gk0/i/b-c943fa3e/summary.json`
- 요약 복사본: `data/orchestration-verification/experiment-result.json`
- 운영용 묶음 생성만 검증: `C:/Users/SSAFY/AppData/Local/Temp/px-y31l6gk0/bundles/cluster-c30b9e4b1191487994733c4d75981a04`

측정 제외/미실행: raw 수집, 실제 MinIO 전송의 전체 소요시간, 운영 두 호스트 실행,
전체 데이터 스캔, DB 적재, 최고 메모리/CPU 사용량/네트워크·셔플 바이트.

### 경계 테스트와 최종 확인

- 기존 실행기 회귀 테스트 31개 통과.
- 새 호스트 테스트 10개 통과. 호스트에 PySpark가 없는 실제 Spark 테스트 3종은 컨테이너에서 실행했다.
- package/version oracle: 부모 ID 유지, 저장소 선택, 설명 NUL, 미래/비-release 제외,
  중복/충돌 의존성의 7개 출력 그룹이 DuckDB와 일치했다.
- downloads: 첫 스냅샷의 전체 모집단 유지 및 다운로드 NULL/UNAVAILABLE 동작을 확인했다.
- dependents oracle: 사전 출시 source 포함, stable target만 계산, 중복 선언 중복 집계 방지,
  0/NULL, NULL requirement, alias, 알 수 없는 target을 기존 계산과 비교했다.
  이 과정에서 unresolved lookup에 대상 ID를 남기는 차이를 발견해 기존처럼 NULL로 수정했다.
  조회 결과의 행 수 역시 선언 수가 아니라 고유 lookup 수로 기록하도록 고쳤다.
- unresolved 수정 후 전체 재실행 결과도 `VERIFIED`, 22/22 그룹 일치:
  `C:/Users/SSAFY/AppData/Local/Temp/px-y31l6gk0/i/b-6773fed6/summary.json`.
  3회 성능 표는 앞서 명시한 코드 SHA의 측정값으로 유지하며 후속 수정 결과로 덮어쓰지 않았다.
- 마지막 lookup 행 수 기록 수정은 dependents oracle의 4개 lookup/5개 version 기대값으로 재검증했고 통과했다.
- 최종 코드가 포함된 운영 준비 묶음:
  `C:/Users/SSAFY/AppData/Local/Temp/px-y31l6gk0/bundles/cluster-af9d7317a2c5472f830d9ef6fc56f82e`.
- CLI 도움말, Python compile, 생성된 운영 스크립트의 `bash -n`, `git diff --check` 통과.

재현 방법과 측정 한계는 `pipeline/spark_experiment/README.md`에 기록했다.
운영 전처리 전환이나 운영 성능 검증 완료로 표시하지 않는다.
