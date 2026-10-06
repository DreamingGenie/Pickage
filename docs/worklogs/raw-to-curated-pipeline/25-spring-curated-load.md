# 25. Spring Boot Curated DB 적재

## 변경 범위와 확정 정책
- app 노드에서 실행할 Java/Spring 전용 적재 경로를 구현한다. 기존 Python 로더와 서비스 DDL 의미는 유지한다.
- dependents_count NULL 행은 version snapshot 적재에서 제외하고 사유/건수를 기록한다. 0은 적재한다. package/version 자체는 제외하지 않는다.
- 완료 bundle 하나의 검증·staging·원자적 게시·중복 방지·실패 복구를 우선 구현한다. 로컬 DB/MinIO로 검증하고 운영 서버에는 연결하지 않는다.
- 기존 API JVM과 분리한 opt-in batch 진입점을 제공한다. 신규 runtime 의존성은 기존 DuckDB 처리 계약을 재사용하는 DuckDB JDBC 1.5.5.1로 제한한다. 기존 PostgreSQL JDBC를 compile 의존성으로 변경한다.

## 작업 계획
1. bundle/S3 입력 검증과 bounded Parquet→COPY 변환
2. PostgreSQL staging·부모 확인·NULL 제외·전체 스냅샷 원자적 반영
3. Spring 수동 실행·자동 탐색 기본 비활성·설정과 운영 문서
4. 합성 full→weekly fixture, 실제 PostgreSQL 및 격리 MinIO, 실패/재개/중복 검증

## 실제 진행·문제·검증
### 구현
- `CuratedBundleReader`: 완료 bundle/단계 manifest/marker/SHA 검증, shard별 Parquet→COPY, JSON 및 키 검증, NULL dependents 제외. dependency SQL NULL은 기존 Python 적재기의 기본 JSON 규칙을 유지하고 품질 JSONL을 기록한다.
- `CuratedBundlePublisher`: 파일별 durable staging/receipt, Python 적재기와 호환되는 advisory lock, parent 일치 검사, 서비스 테이블과 완료 이력의 원자적 게시. 기존 DB baseline은 값 비교 후에만 채택한다.
- `CuratedLoadJob`: 수동 실행, parent 순서 자동 탐색, 로컬 상태/이벤트, 재시도와 BLOCKED 처리.
- 전용 `curated-loader.jar`: API component scan/JPA/HTTP/Flyway 실행 없이 opt-in 실행. 운영 CI/CD와 weekly timer는 수정하지 않았다.
- 실행 방법과 재시도 복구 설명은 `backend/CURATED_LOAD.md`에 기록했다.

### 발견한 문제와 수정
- 실제 request의 ISO timestamp와 PostgreSQL DATE 바인딩 차이를 수정했다.
- role이 같다는 이유로 shard 파일을 덮어쓰거나 staging을 지우던 초기 구현을 수정했다.
- 빈 weekly 변경분을 정상 허용하고, snapshot 날짜/예상 행 수/기존 snapshot 값 충돌을 검사했다.
- Parquet JSON 문자열의 이중 직렬화를 제거하고 기존 dependency 기본값 계약을 유지했다.
- COPY checksum 계산을 전체 파일 메모리 로딩에서 스트리밍으로 변경했다.
- PostgreSQL 실패→재시도 성공 시 active attempt와 오류 상태가 정확히 갱신되도록 했다.
- standalone BootJar의 Java target version을 명시했다.

### 로컬 검증 진행
- 격리 PostgreSQL 16: localhost:15439, 전용 `curated_load_test` DB, 임시 데이터.
- 격리 MinIO: 운영과 같은 RELEASE.2025-04-22T22-12-26Z, localhost:19039.
- PostgreSQL 통합 11개 시나리오 통과: NULL 거부, 0 보존, 중복, 부모 불일치, baseline 채택/불일치, 기존 월 partition, shard 누적, 중간 FK 실패 rollback, 빈 weekly, 기존 Python lock, 실패 후 receipt 재사용.
- Python producer로 full→weekly 2개 snapshot, 139개 객체와 Parquet 기반 기대값 fixture를 생성했다.
- 기본 비활성 standalone jar는 외부 연결 전에 의도한 오류로 종료됨을 확인했다.
- 실제 MinIO E2E 통과: 최종 master package 4행/version 6행, weekly package_snapshot 3행, version_snapshot 4행을 producer Parquet과 행/값 단위로 비교했다. dependents 원본 5행 중 NULL 1행 제외, 계산된 0은 3행 유지했다.
- 전체 백엔드 단위 시험 300개 통과(실패/skip 0). 마지막 완료 입력 조기 SKIP 수정 후 관련 단위 9개와 실제 DB/MinIO 통합 12개를 다시 실행해 모두 통과했다.
- `curatedBootJar` 빌드 성공. 실제 jar로 baseline `PUBLISHED` → weekly `PUBLISHED` → 동일 weekly `SKIPPED`를 확인했다. jar 내부 클래스/SQL fingerprint도 정상 동작했다.
- jar `last-run.json`에 `NOT_SELECTED_TARGET=1`, version_snapshot source=5/loaded=4/excluded=1을 확인했다.
- 이미 PUBLISHED된 입력은 staging 코드 계약이 바뀌어도 재사용 없이 SKIPPED 처리한다. 미완료 staging만 계약 일치를 요구한다.
- 원천 stage manifest가 상대 `path`를 쓰는 downloads/package_snapshot은 producer와 같은 `prefix/data/path` 규칙으로 파일 목록을 대조하도록 보완했다.
- fixture export CLI 확인과 `git diff --check` 완료. 기존 주 작업 디렉터리의 미추적 파일 2개는 그대로 보존했다.

재현 명령(backend 작업 디렉터리):
```text
gradlew.bat test
gradlew.bat test --tests '*curatedload*' integrationTest --tests '*curatedload*' curatedBootJar --no-daemon
```
두 번째 명령은 문서에 적은 전용 DB/MinIO 환경 변수를 지정했다. 테스트 보고서는
`backend/build/reports/tests/test`, `backend/build/reports/tests/integrationTest`에 생성된다.
로컬 fixture는 `C:/tmp/pickage-curated-load-fixture-20260918`, jar 실행 상태는
`C:/tmp/pickage-loader-jar-smoke`에 보존했다. 생성한 전용 DB/MinIO 컨테이너는 검증 후 종료했다.

### 미실행 및 운영 경계
- 운영 서버/DB/MinIO에는 접속하거나 배포하지 않았다.
- 실제 대규모 데이터의 Spring 적재 시간·최대 메모리·디스크/WAL 영향은 미측정이다.
- 운영 프로세스 등록, 자원 상한, baseline 채택, staging/로컬 파일 보관·정리 정책은 배포 단계에서 적용해야 한다.
- 커밋/push는 하지 않았다.

## 코드리뷰 후 수정 (2026-09-18)
- 범위: 완료 입력 404 분류와 JVM timezone에 따른 적재 이력 timestamp 이동 결함 2건. 운영 배포는 범위 밖이다.
- 계획: 최초 `_current.json` 부재만 대기 상태로 분리하고 참조 파일 404는 차단한다. timestamp는 UTC LocalDateTime/원천 timezone 없는 LocalDateTime으로 바인딩한다. 누락 파일 및 UTC/KST 성공·실패 이력 회귀를 검증한다.
- 구현: 최초 pointer 조회의 404에만 별도 예외를 사용한다. 이후 manifest/marker/Parquet 404는 기존 영구 오류 분류로 BLOCKED가 된다. 성공/실패 양쪽 DB 이력은 `setObject(LocalDateTime)`을 사용한다.
- 검증 결과: 관련 단위 11개, 실제 PostgreSQL 통합 15개 모두 통과(실패/skip 0), `curatedBootJar` 빌드 성공. 최초 pointer 부재는 WAITING_INPUT/실패 0회, 참조 manifest·marker·Parquet 누락은 BLOCKED/실패 1회를 확인했다. UTC/KST × Z timestamp/timezone 없는 timestamp 조합에서 성공·실패 이력의 날짜·시각·마이크로초 보존을 검증했다.
- 명령: `gradlew.bat test --tests '*curatedload*' integrationTest --tests '*CuratedBundlePublisherIntegrationTest' curatedBootJar --no-daemon`. 전용 localhost:15439 PostgreSQL 16만 사용했고 검증 후 컨테이너를 종료했다. 이 수정에서는 MinIO E2E 전체를 재실행하지 않았으며 S3 404는 실제 SDK 예외를 발생시키는 fake S3로 검증했다.
- 배포 문서에 Python→Spring 단일 writer 전환과 대용량 디스크/staging/WAL 측정·보관 정책을 운영 활성화 조건으로 명시했다. 자동 배포나 DB fence 구현으로 범위를 확대하지 않았다.
- `git diff --check` 통과. 기존 주 작업 디렉터리 미추적 파일 2개는 그대로 보존했다. 운영 변경과 커밋/push는 하지 않았다.
