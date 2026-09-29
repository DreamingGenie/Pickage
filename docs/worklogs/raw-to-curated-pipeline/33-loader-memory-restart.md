# Spring 적재기 4GB 확대와 적재 재개

## 범위와 계획
- 사용자 요청: 적재기 DuckDB 한도를 4GB로 올리고 재실행하며 상태 확인 방법 제공.
- reader의 256MB를 4GB로 변경한다. JVM heap 및 PostgreSQL 설정은 그대로 둔다.
- 파일 다운로드/Parquet 검증/COPY 변환/DB staging/최종 게시 로그를 추가한다.
- 적재기 테스트 및 jar 빌드 후 이전 jar/실패 로그를 보존하고 새 jar를 별도 경로에 고정한다.
- 이미 게시된 baseline bundle의 SHA·완료 표시를 확인해 전처리를 생략하고 DB 적재부터 재개한다. 이후 기존 실험의 9/14 처리 흐름을 유지한다.
- 운영 서비스·서버 DB는 변경하지 않는다. 기존 전용 로컬 MinIO/PostgreSQL만 사용한다.

## 검증 및 실행
- 아래에 실제 결과를 기록한다. 재시작은 전체 적재 성공을 의미하지 않는다.
- `gradlew.bat test --tests '*curatedload*' curatedBootJar --no-daemon` 성공(25초). Reader 4개/Job 7개 총 11개, 실패 0. DB 재개 경로 테스트 2개 통과: 완료 bundle/marker 검증, jar 변경 거부, baseline 재처리 생략.
- 기존 jar를 보존하고 `C:/pg914r3/curated-loader-4gb-20260921.jar`에 새 jar를 복사했다. SHA와 baseline manifest SHA는 `loader-4gb-build.json`에 고정했다.
- `real_snapshot_db_resume.py`는 원래 baseline manifest와 완료 표시가 같은지 확인한 뒤 전처리를 건너뛰고, 모든 참조 파일 검증은 새 적재기가 수행한다. 이후 weekly 흐름은 기존대로 이어간다.
- 2026-09-21 12:54:27 KST 시작: Python PID 37088, Java PID 32652. RUNNING / baseline:SPRING_DB_LOAD 확인. 실제 로그에 `CURATED_PREPARE memory_limit=4GB threads=1 files=23` 및 package 검증 시작을 확인했다.
- 기존 실패 로그·상태는 `before-loader4gb-20260921-125427-*` 형식으로 보존했다. 기존 준비 파일과 Curated 원본은 삭제하지 않았다.
- 상태: `powershell -ExecutionPolicy Bypass -File C:\pg914r3\status.ps1 -Watch`. 상세 적재 로그: `Get-Content C:\pg914r3\db-baseline.log -Tail 30 -Wait`. 전체 게시 성공과 DB 건수 검증은 아직 미확인이다.
