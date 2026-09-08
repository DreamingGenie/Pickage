# Curated `package`·`version` PostgreSQL 적재

`pipeline.postgresql.load`는 MinIO의 승인된 Curated `package-version` 실행을 읽어
PostgreSQL의 `package`와 `version`에 게시한다. 입력을 다시 만들거나 BigQuery를 호출하지
않으며, PostgreSQL 스키마는 Spring Flyway가 적용한다.

현재 구현은 Python 표준 라이브러리 subprocess로 `psql` 한 세션을 열고, DuckDB로
Parquet를 검증한 뒤 생성한 PostgreSQL COPY TEXT 파일을 staging 임시 테이블에 보낸다.
Python PostgreSQL 드라이버를 추가하지 않는다.

> 격리 PostgreSQL 16.14에서 package 11,080,940행·version 54,188,349행의 전체 적재와
> 읽기 전용 DB 대조를 완료했다. 전체 적재는 58분 49초가 걸렸다. 검증 근거와 한계는
> [작업 결과 기록](../../docs/worklogs/S15P21A506-267/05-results.md)을 확인한다.

## 범위와 전제

입력은 다음 경로의 완료 Curated 실행이다.

```text
s3://pickage-curated/depsdev/v1/package-version/
  snapshot={snapshot}/run_id={curated_run_id}/
    run_manifest.json
    _SUCCESS
    attempts/{attempt}/package/data/*.parquet
    attempts/{attempt}/version/data/*.parquet
```

loader는 manifest의 정확한 `package/data`와 `version/data` 목록만 읽는다. `_current.json`을
자동으로 따라가거나 모든 attempt를 glob하지 않는다. 특정 실행을 재현하려면 snapshot과
Curated run ID를 명시한다.

적재 대상은 다음 두 테이블이다.

| 대상 | 행의 의미 | 키·주요 계약 |
| --- | --- | --- |
| `package` | 서비스에 포함할 패키지 하나 | `package_id` PK, `name` UNIQUE, `repo_url` NULL 허용 |
| `version` | 패키지의 릴리스 버전 하나 | `(package_id, version)` PK, `package_id` FK, `dependency JSON NOT NULL DEFAULT` |

`snapshot`, `package_snapshot`, `package_version_snapshot`과 `dependents_count`는 이
loader의 대상이 아니다. 후속 적재 작업에서 별도 계약으로 처리한다.

## 설치

리포 루트에서 기존 `.venv-bq`와 Curated 의존성을 재사용한다. 환경이 없는 팀원은 Python 3.12로 `.venv-bq` 가상환경을 먼저 만들고 아래 설치 명령을 실행한다. 별도 PostgreSQL Python 드라이버는 필요하지 않다.

```powershell
.venv-bq\Scripts\python.exe -m pip install -r pipeline/curated/requirements.txt
.venv-bq\Scripts\python.exe -m pipeline.postgresql.load --help
```

`pipeline/curated/requirements.txt`가 DuckDB와 MinIO 클라이언트 의존성을 제공한다.
MinIO 접속 설정은 기존 `pipeline/minio/.env`와 `pipeline.minio.ingest_raw.client()`를
재사용한다. `.env`, 비밀번호, access key는 Git에 커밋하지 않는다.

PostgreSQL 연결은 두 방법 중 하나를 선택한다.

| 방법 | 사용 조건 | 인증 설정 |
| --- | --- | --- |
| `--docker-container` | 이미 실행 중인 PostgreSQL 컨테이너 | 컨테이너 내부의 libpq/Docker 실행 환경 사용 |
| `--psql` | 호스트의 PostgreSQL 16 `psql` | libpq 환경 변수, 서비스 파일 또는 `.pgpass` 사용 |

CLI에는 비밀번호나 DSN을 넣지 않는다. `--database`에는 단순 DB 이름만 넣으며, loader가
만드는 명령·실행 리포트·stderr 로그에도 인증정보를 기록하지 않는다.

## 검증 전용 실행

`--verify-only`는 PostgreSQL에 연결하지 않는다. MinIO에서 승인된 manifest와 Parquet를
다운로드하고 파일 해시·스키마·키·JSON·행 수를 검증한다. 실행 결과는 work directory의
`execution_report.json`에 기록된다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.postgresql.load `
  --snapshot 2026-08-31 `
  --curated-run-id curated-20260907-v2 `
  --execution-id verify-20260907-v2 `
  --verify-only
```

이 명령에는 MinIO 접속이 필요하며 DB 연결 옵션은 필요하지 않다. 성공 상태는 DB의
`PUBLISHED`가 아니라 로컬 리포트의 `VERIFIED`다.

## 실제 적재

### Docker 컨테이너의 `psql` 사용

PostgreSQL 컨테이너 이름은 `docker ps --format "{{.Names}}"`로 확인한다. Compose 로컬
구성에서는 보통 `pickage-local-postgres-1`이지만 이름을 추측해 실행하지 않는다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.postgresql.load `
  --snapshot 2026-08-31 `
  --curated-run-id curated-20260907-v2 `
  --execution-id load-20260907-v2 `
  --docker-container <postgres-container> `
  --database pickage
```

### 호스트 `psql` 사용

`psql` 경로와 libpq 인증·접속 설정을 호스트에 준비한 뒤 실행한다. 비밀번호는 명령행에
직접 쓰지 않는다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.postgresql.load `
  --snapshot 2026-08-31 `
  --curated-run-id curated-20260907-v2 `
  --execution-id load-20260907-v2 `
  --psql <path-to-psql.exe> `
  --database pickage
```

두 방식 모두 `--database`와 `--docker-container` 또는 `--psql` 중 하나가 필요하다.
`--workers`(1–16), `--threads`(1–32), `--memory-limit`으로 MinIO 다운로드와 DuckDB
검증 자원을 조정할 수 있다. 기본값은 각각 4, 4, `4GB`다.

## 처리 순서와 파일

한 실행은 다음 순서로 진행한다.

1. `snapshot`, `curated_run_id`, `_SUCCESS`, `run_manifest.json`을 확인하고 manifest 해시를 검증한다.
2. 적재 모드에서는 dataset 잠금을 획득하고 PREPARING 실행·attempt를 먼저 기록한다. manifest에 지정된 Parquet만 캐시에 내려받고 크기·SHA-256을 확인한다.
3. Parquet 컬럼 순서·타입, `package_id`·이름·버전·ordinal·JSON·중복·FK·manifest 행 수를 DuckDB로 검증한다.
4. 최초 적재에서는 각 Parquet를 `.copy.tsv`로 변환한다. 백슬래시·탭·개행·CR을 PostgreSQL COPY TEXT 규칙으로 이스케이프한다. dependency의 SQL NULL은 COPY 전송 시 기본 JSON `{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}`으로 대체하고 원본 NULL·package/version·input run 해시를 품질 JSONL에 기록한다. 현재 승인 입력의 대체 대상은 25개다. 원본 Parquet와 SQL NULL이 아닌 JSON 값은 그대로 유지한다. 이미 게시된 동일 입력의 재검증에서는 COPY 파일을 만들지 않는다.
5. 한 `psql` 세션에서 임시 staging 테이블을 만들고 COPY한다. staging의 유일성·FK·행 수를 다시 확인한다.
6. 서비스 테이블 충돌과 snapshot 순서를 확인한 뒤 `package`, `version`, `etl_dataset_current`, 실행 이력을 하나의 트랜잭션으로 게시한다.

기본 작업 디렉터리는 `data/postgresql`이다. 실행별 파일은 다음 위치에 남는다.

```text
data/postgresql/{execution_id}/{attempt_id}/
  execution_report.json  # 실행 상태·입력·계약 해시·단계·오류
  psql.stderr.log        # psql stderr 최근 내용 및 진단
  cache/package/*.parquet
  cache/version/*.parquet
  input.duckdb
  quality/dependency_defaulted.jsonl  # 원본 SQL NULL과 대체 값·행 식별자·입력 출처
  csv/package-*.copy.tsv
  csv/version-*.copy.tsv
```

작업 디렉터리는 로컬 입력·진단 산출물이다. 자격증명과 비밀번호를 이 위치에 저장하지
않으며, 보존 정책에 따라 용량을 정리할 때도 현재 실행 중인 디렉터리는 삭제하지 않는다.

## 실행 이력과 재실행 계약

Flyway V2가 만든 실행 이력은 `etl_load_execution`, `etl_load_attempt`,
`etl_dataset_current`에 기록된다.

| 이력 | 허용 상태 | 의미 |
| --- | --- | --- |
| `etl_load_execution` | `PREPARING` → `PUBLISHED` 또는 `FAILED` | 하나의 `execution_id`에 대한 적재 계약과 최종 상태 |
| `etl_load_attempt` | `PREPARING` → `PUBLISHED`, `FAILED`, `REVERIFIED` | 실제 psql 세션 시도와 단계·오류·건수 |
| `etl_dataset_current` | 현재 한 행 | DB에 원자적으로 게시된 dataset 입력 포인터. MinIO `_current.json`과 별도 |

`execution_id`는 입력·적재 계약을 식별하고 `attempt_id`는 각 재시도를 식별한다. 다음 규칙을 지킨다.

- 같은 `execution_id`는 dataset, snapshot, Curated run/prefix, manifest SHA-256, 기대 건수,
  입력 metadata, contract SHA-256이 모두 같아야 재시도할 수 있다. 하나라도 다르면 거부한다.
- 동일한 manifest를 다른 contract로 재사용할 수 없다. 이미 게시된 입력의 contract가 다르면
  새 승인 입력 run을 사용한다.
- 이전 세션이 `PREPARING`으로 남아 있으면 새 세션이 attempt 상태를 `FAILED`, phase를
  `ABANDONED`로 남긴 뒤 새 attempt를 등록한다. 실제 프로세스가 살아 있는 동안에는
  advisory lock 때문에 동시에 시작할 수 없다.
- 동일 입력·동일 contract가 이미 `PUBLISHED`이면 데이터를 다시 반영하지 않고
  `REVERIFIED` attempt를 만든다. 이 검증의 범위는 `INPUT_ONLY`이며, 실제 재적재가 아니다.
- 현재 DB에 게시된 snapshot보다 오래된 입력은 새로 게시하지 않는다. 같은 snapshot의 다른 manifest는 현재
  manifest의 SHA-256을 `manifest.request.parent.manifest_sha256`으로 명시한 경우에만
  lineage를 이어갈 수 있다. 연결되지 않은 같은 snapshot은 보수적으로 거부한다.
- 과거 입력을 다시 검증해도 현재 DB 데이터나 `etl_dataset_current`를 과거로 되돌리지
  않는다. `is_current_input`으로 현재 포인터 일치 여부만 확인한다.

`REVERIFIED` attempt의 `actual_counts`는 다시 검증한 **입력 행 수**다. `PUBLISHED` attempt에서는 staging에서 직접 센 입력 행 수이며, 서비스 테이블 전체 건수는 적재 실행 보고서의 `service_before_counts`·`service_after_counts`로 구분한다. 입력 전용 재검증은 현재 DB의 모든 필드가 입력과 같다는 판정이 아니다.

`contract_sha256`은 loader 코드, Flyway `V*.sql`, COPY 포맷과 DuckDB 버전을 묶은 해시다.
manifest SHA-256은 Curated `run_manifest.json`의 바이트를, 원본 파일 SHA-256은 다운로드한
Parquet 바이트를 확인한다. 생성된 `.copy.tsv`는 PostgreSQL 전송 형식이며 현재 별도의
manifest SHA를 게시하지 않는다. 따라서 해시 일치는 입력·실행 계약의 무결성 근거이지
변환 의미가 모두 옳다는 증명은 아니다. 행 수·스키마·키·필드 검증을 함께 확인한다.

## 필드와 시간 보존

- `package_id`는 Curated의 내부 ID를 그대로 유지한다. loader가 새 ID를 부여하지 않는다.
- `version`의 기본키는 `(package_id, version)`이며, `package_id`만으로 버전을 식별하지 않는다.
- `published_at`은 timezone 없는 Curated TIMESTAMP를 PostgreSQL `timestamp`로 보낸다.
  값은 마이크로초까지 `YYYY-MM-DD HH:MM:SS.ffffff` 형식으로 포맷하며 timezone을
  추정하거나 보정하지 않는다.
- `dependency`는 서비스 V1의 `NOT NULL DEFAULT` 계약을 유지한다. 기존 DDL comment는
  `유저에게 의존성 보여주는 용도, 따로 계산할때 쓰진 않음`이다. `curated-20260907-v2`의
  invalid dependency 25개는 원본 version을 유지하되 COPY 전송에서만 기본 JSON
  `{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}`으로 대체한다.
  원본 SQL NULL, package/version, 기본 JSON, input run 해시는 품질 JSONL로 기록하고 count/SHA를
  실행 report와 `quality_report` JSONB에 연결한다. 원본 Parquet와 Curated run은 변경하지 않는다.
- `licenses`의 SQL NULL, JSON `null`, 빈 배열·객체를 임의로 합치지 않는다.
- 설명·폐기 안내·저장소 주소는 COPY TEXT 이스케이프를 거쳐 원문 개행과 백슬래시를
  보존한다. NUL은 입력 검증에서 허용하지 않는다.

## 실패, 복구, 재실행

실패하면 서비스 테이블에 대한 트랜잭션을 rollback하고, `etl_load_execution`과 현재
attempt에 오류 단계·메시지를 남긴다. `after_package_insert` 같은 중간 실패에서도 package
일부만 게시된 상태를 남기지 않는 것이 계약이다.

`execution_report.json`이 `FAILED`이면 먼저 `error`, `phase`, `psql.stderr.log`, manifest
해시를 확인한다. 같은 입력과 contract로 새 attempt를 실행한다. 작업 디렉터리를 지우기
전에 report와 stderr를 보존해 원인을 기록한다.

프로세스가 죽어 DB가 `PREPARING`으로 남은 경우에는 다음 순서로 복구한다.

1. 같은 `execution_id`의 loader/psql 프로세스가 실제로 끝났는지 확인한다.
2. 새 실행을 같은 입력·contract로 시작한다. loader가 이전 PREPARING 이력과 attempt를
   실패로 표시하고 새 attempt를 등록한다.
3. 새 attempt가 `PUBLISHED`인지, 서비스 테이블과 `etl_dataset_current`가 함께 갱신됐는지 확인한다.

commit 직후 클라이언트가 응답을 잃은 경우에는 바로 다른 입력을 실행하지 않는다. 같은
manifest와 contract로 재실행해 `PUBLISHED` 입력이면 `REVERIFIED`로 확인한다. 실행 리포트가
없어도 DB의 `etl_load_execution`, `etl_load_attempt`, `etl_dataset_current`를 조회해
commit 여부를 확인한다. 확인할 수 없는 동안 수동으로 상태를 `PUBLISHED`로 바꾸거나
서비스 테이블을 TRUNCATE하지 않는다.

실행 중인 다른 적재가 있으면 PostgreSQL advisory lock으로 시작이 거부된다. 해당 프로세스가
끝나기를 기다린 후 재시도한다. lock이 남았다는 이유만으로 DB를 재시작하거나 이력 행을
삭제하지 않는다.

## 스키마 적용과 테스트 경계

일반 로컬·운영 DB의 스키마는 다음 Flyway 마이그레이션을 애플리케이션 기동 시 적용한다.

- `backend/src/main/resources/db/migration/V1__init.sql`
- `backend/src/main/resources/db/migration/V2__add_curated_load_execution.sql` — 실행/attempt/current 이력만 추가하며 V1 서비스 5개 테이블과 `dependency` DDL은 변경하지 않는다.

이미 적용한 `V*.sql`을 수정하지 말고 새 버전 migration을 추가한다. 통합 테스트의
`pipeline/postgresql/test_integration.py`는 격리된 테스트 데이터베이스를 만들고 V1·V2를
직접 적용할 수 있지만, 이 방식은 테스트 harness에만 해당한다. 실제 사용자 DB에 SQL을
직접 붙여넣어 migration을 우회하지 않는다.

단위 테스트와 CLI 도움말은 DB 없이 실행할 수 있다.

```powershell
.venv-bq\Scripts\python.exe -m unittest `
  pipeline.postgresql.test_input `
  pipeline.postgresql.test_load `
  pipeline.postgresql.test_postgres `
  pipeline.postgresql.test_integration -v
.venv-bq\Scripts\python.exe -m pipeline.postgresql.load --help
```

실제 PostgreSQL 통합 테스트는 격리된 컨테이너를 가리키는 `PICKAGE_TEST_CONTAINER`가
있을 때만 실행한다. 애플리케이션 `pickage` DB에 연결하지 않고 테스트 DB를 만들며,
seed 파일도 실행하지 않는다. 이 테스트 통과만으로 Curated 전체 데이터 적재 성공을
주장할 수 없다.

## 빈 DB 전체 적재 결과 대조

첫 전체 적재가 `PUBLISHED`로 끝난 뒤 다음 읽기 전용 도구로 입력과 DB를 비교한다. 원래 적재 attempt의 `execution_report.json`을 사용한다.

```powershell
.venv-bq\Scripts\python.exe scripts/verify_package_version_load.py `
  --report data/postgresql/<execution-id>/<attempt-id>/execution_report.json `
  --docker-container <postgres-container> `
  --database <validation-database> `
  --output data/postgresql/verification/full-data.json
```

이 도구는 manifest에 기록된 캐시 파일의 크기·해시를 재검증하고, 전체 건수·NULL 통계·ordinal 범위·DB 제약 상태를 대조한다. 기본 JSON으로 대체한 quality JSONL의 행 목록·count·SHA와 DB attempt의 quality report 연결도 확인한다. 각 version 파일에서 추출한 표본과 NULL·개행 경계 표본의 모든 필드, 이 표본에 연결되는 package 필드도 비교한다. 필드 값 대조는 표본 검사이며 전체 행의 모든 필드를 전수 비교한 결과는 아니다. DB current가 이미 다른 입력으로 바뀌었다면 검증을 거부한다.

## 안전한 로컬 운영

`deploy/local/seed/seed_sample.sql`은 화면·쿼리 확인용 샘플 DB에만 사용한다. 실제 Curated
적재 DB에서 seed를 실행하거나 `TRUNCATE`로 데이터를 비우지 않는다. seed 실행은 명시적인
샘플 데이터 재설정 작업이며, loader의 복구 방법이 아니다.

`docker compose down -v`는 MinIO 원본과 PostgreSQL 볼륨을 함께 지울 수 있으므로 이 적재의
복구 절차로 사용하지 않는다. 로컬 샘플 DB를 정말 폐기해야 하는 경우에만
`deploy/local/README.md`의 소유 볼륨 확인 절차를 따른다.

## 참고

- [PostgreSQL 16 COPY](https://www.postgresql.org/docs/16/sql-copy.html)
- [PostgreSQL 16 psql](https://www.postgresql.org/docs/16/app-psql.html)
- [PostgreSQL 16 관리자 함수와 advisory lock](https://www.postgresql.org/docs/16/functions-admin.html)
- [DuckDB COPY](https://duckdb.org/docs/stable/sql/statements/copy)
