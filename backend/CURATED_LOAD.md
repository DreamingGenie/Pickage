# Curated → PostgreSQL 적재

완료된 `pickage-curated/depsdev/v1/curated-bundle`을 읽는 별도 Spring Boot 배치다.
기존 HTTP API와 JVM을 공유하지 않으며 기본값은 비활성이다. 기존 weekly timer는
수집과 Curated 게시까지 담당하고, 이 프로그램은 게시된 bundle을 소비한다.
이 변경만으로 서버 배치가 배포되거나 자동 시작되지는 않는다.

## 처리 순서

1. bundle manifest SHA와 `_SUCCESS`, 6개 단계의 manifest·marker·파일 목록을 검증한다.
2. 서비스에 필요한 Parquet을 읽어 PostgreSQL COPY 파일로 변환한다. DuckDB는
   1 thread, 메모리 한도 256MB를 사용하고 초과 중간 데이터는 작업 디렉터리에 쓴다.
3. 파일별로 durable staging과 receipt를 같은 트랜잭션에 기록한다.
4. DB의 현재 bundle과 입력의 `parent_bundle`이 정확히 같은지 확인한다.
5. package/version을 upsert하고 두 snapshot 테이블, snapshot 날짜, 완료 이력을
   하나의 트랜잭션으로 확정한다. 실패하면 서비스 테이블 변경은 rollback된다.

`dependents_count IS NULL`은 **package_version_snapshot 행만 제외**한다.
계산 결과 0은 저장한다. package/version 마스터와 Curated 원본은 유지하며
제외 건수와 사유를 실행 로그에 남긴다. 다른 nullable 컬럼에 이 규칙을 적용하지 않는다.

## 빌드와 실행

Java 21에서 `./gradlew curatedBootJar`를 실행하면
`build/curated-loader/curated-loader.jar`가 만들어진다. 일반 API jar 출력 경로와 분리되어 있다.
DB 스키마 migration은 기존 배포 절차로 먼저 적용한다. 이 배치는 Flyway를 자동 실행하지 않는다.
API 배포 시 기존 Flyway 경로를 통해 V8 staging/receipt 테이블이 추가될 수 있다.
서비스 테이블의 기존 NULL 제약은 변경하지 않는다.

권한을 제한한 외부 properties 파일을 준비한다. 비밀번호가 있는 파일은 Git에 넣지 않는다.

```properties
pickage.curated-load.enabled=true
pickage.curated-load.mode=once
pickage.curated-load.jdbc-url=jdbc:postgresql://DB_HOST:5432/DB_NAME?currentSchema=public
pickage.curated-load.db-user=LOADER_USER
pickage.curated-load.db-password=SECRET
pickage.curated-load.s3-endpoint=http://MINIO_HOST:9000
pickage.curated-load.s3-access-key=CURATED_READER
pickage.curated-load.s3-secret-key=SECRET
pickage.curated-load.work-dir=/var/lib/pickage-curated-load
pickage.curated-load.bundle-prefix=depsdev/v1/curated-bundle/snapshot=YYYY-MM-DD/run_id=RUN_ID
pickage.curated-load.manifest-sha256=64자리_SHA256
```

```sh
java -Xmx512m -jar build/curated-loader/curated-loader.jar \
  --spring.config.additional-location=file:/보호된경로/curated-load.properties
```

JVM heap 외에 DuckDB native 메모리, COPY 파일 및 spill 디스크 공간이 필요하다.
운영 CPU·전체 메모리·디스크 한도는 실데이터 측정 후 별도 프로세스/컨테이너에 설정한다.
API 컨테이너 안에서 함께 실행하지 않는다.

MinIO 계정은 Curated 버킷의 해당 prefix에 `s3:GetObject`만 허용하면 된다.
raw 수집 계정을 그대로 쓰지 않는다. DB 계정은 서비스 upsert, ETL staging/이력 DML,
날짜 partition 생성에 필요한 권한이 필요하다.

## 초기 연결과 재실행

- 빈 DB: 부모가 없는 full bundle로 `mode=once`를 시작한다.
- 이미 데이터가 있는 DB: 해당 데이터와 일치하는 full bundle을 지정해
  `mode=adopt-baseline`을 실행한다. 실제 DB 값과 비교하고 일치할 때만 기준 이력을 등록한다.
  날짜가 같다는 이유만으로 승인하지 않는다. 불일치 시 기존 데이터를 바꾸지 않고 실패한다.
- 이후 weekly: 직전 DB bundle이 입력 parent와 같아야 한다. 중간 snapshot을 건너뛰지 않는다.
- 동일 bundle 재실행: 완료된 입력은 `SKIPPED` 처리한다.
- 실패 후 같은 입력 재실행: 검증된 staging receipt를 재사용한다.
  코드 계약이 바뀐 staging을 임의로 승인하거나 SHA를 고쳐 재사용하지 않는다.

## 자동 탐색과 실패 로그

`mode=poll`, `poll-seconds=600`으로 실행하면 `_current.json`에서 부모 연결을 따라가
오래된 미적재 bundle부터 순서대로 처리한다. 새 timer를 등록하는 기능은 없다.
운영 도입 시 별도 상시 프로세스로 실행할지 수동으로 실행할지 배포 설정에서 결정한다.

- 최초 `_current.json`이 아직 없으면 `WAITING_INPUT`; 실패 횟수를 소비하지 않는다.
- pointer가 가리키는 manifest/marker 또는 완료 bundle 내부 파일이 없으면 `BLOCKED`다. 손상된 완료 입력을 새 입력 대기와 구분한다.
- 일시 오류는 10분부터 최대 1시간 간격으로 재시도하고 최대 10회 후 `BLOCKED`다.
- 입력 무결성/계약 오류는 자동 반복하지 않고 `BLOCKED`로 남긴다.
- 작업 디렉터리의 `last-run.json`, `events/*.json`, `poll-state.json`과 표준 로그로 확인한다.
- 게시 단계 실패는 DB `etl_load_attempt`에도 남긴다. 입력 검증 중 실패는 로컬 로그에 남는다.
- 차단 원인을 해결한 뒤 해당 bundle을 `once`로 성공시키면 다음 poll에서 진행한다.
  탐색 자체가 차단된 경우에는 프로세스를 중지하고 `poll-state.json`을 보관한 뒤 제거해
  탐색을 다시 시작한다. DB 완료 이력이 최종 기준이므로 로컬 상태 초기화가 중복 적재를 허용하지 않는다.

실패 입력과 staging은 진단/재시도를 위해 보존한다. 성공 후에도 자동 삭제하지 않으므로
작업 디렉터리와 ETL staging 보관 용량을 관리해야 한다. 운영 보관 주기와 정리 작업은 별도다.

운영 전환 시 기존 수동 Python DB 로더 사용을 중지하고, baseline 채택 이후에는 Spring을
DB 적재의 단일 실행 주체로 사용한다. 공유 advisory lock은 동시 실행만 막으며 두 로더의
순차 교대 실행까지 막지는 않는다. 운영 활성화 전 실제 full bundle의 로컬 디스크,
staging/WAL 최대 사용량을 측정하고 여유 공간 기준과 성공/실패 산출물 보관 주기를 정한다.

## 로컬 검증

단위 시험: `./gradlew test --tests '*curatedload*'`

실제 PostgreSQL 시험은 전용 로컬 DB URL을 `CURATED_TEST_DB_URL`로 지정하고
`CURATED_TEST_DB_USER`, `CURATED_TEST_DB_PASSWORD`를 설정한다.
`./gradlew integrationTest --tests '*CuratedBundlePublisherIntegrationTest'`를 실행한다.

실제 Python producer → MinIO → Java → PostgreSQL 시험은
`pipeline/preprocessing/tests/fixtures/export_spring_load_fixture.py`로 fixture를 만든 후
`CURATED_LOAD_E2E=1`, `CURATED_TEST_FIXTURE`(디렉터리), `CURATED_TEST_S3_ENDPOINT`,
`CURATED_TEST_S3_ACCESS_KEY`, `CURATED_TEST_S3_SECRET_KEY`를 추가하고
`./gradlew integrationTest --tests '*CuratedBundleEndToEndTest'`를 실행한다.
이 시험은 전용 로컬 DB/MinIO 데이터를 초기화한다. 운영 자격증명은 사용하지 않는다.
