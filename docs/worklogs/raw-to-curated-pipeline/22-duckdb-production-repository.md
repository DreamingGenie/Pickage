# Repository 기본 실행 엔진 DuckDB 전환

## 변경 범위와 계획
- 실험에서 결과 일치·성능을 확인한 DuckDB 변환을 정식 repository_metrics 모듈로 승격한다.
- 일반/weekly 실행기와 직접 CLI의 기본값을 DuckDB로 바꾼다. native/docker는 명시적 Spark 비교 경로로 유지한다.
- 입력 검증 → 변환 → Parquet 재검증 → 불변 manifest/MinIO 게시 흐름은 유지한다.
- 엔진·자원 설정을 실행 계약에 기록하고, 같은 run ID로 다른 엔진 재개를 거부한다.
- PySpark 없는 로컬 경로, 실제 합성 입력의 전체 실행·재개·게시, 기존 Spark 계약을 검증한다.
- 서버 배포·실제 MinIO/DB 접속·전체 원천 재처리는 하지 않는다.

## 실제 작업과 검증 결과
- 실험의 DuckDB SQL/검증 구현을 `repository_metrics/duckdb_transform.py`로 승격했다. 원래 실험 구현은 비교용으로 보존했다.
- 일반 run, weekly 요청 생성, repository 직접 CLI의 기본값을 duckdb로 통일했다. 기존 요청에 명시된 native/docker 선택은 유지한다.
- DuckDB 연결은 threads/memory_limit을 적용하고 attempt별 working DB/scratch를 사용한다. spill 상한은10GB다. 이 상한은 전체 프로세스 메모리/디스크 사용량 상한을 뜻하지 않는다.
- Spark import를 Spark 분기 안으로 옮겼다. 기본 requirements에서 PySpark를 빼고 기존 버전은 requirements-spark.txt로 분리했다. 새로운 의존성은 추가하지 않았다.
- 실행 identity에 엔진/자원/DuckDB 버전을 기록한다. 엔진 또는 자원 설정을 바꿀 때 같은 run ID 재사용은 거부한다. 이전 결과의 manifest를 새 코드 해시로 바꾸지 않는다.
- 실험 출력의 naive TIMESTAMP가 다음 package_snapshot 단계의 UTC-adjusted Parquet schema와 불일치했다. 정식 출력 경계에서 모든 timestamp 열을 UTC TIMESTAMP WITH TIME ZONE으로 명시해 기존 Spark 출력 계약에 맞췄다. 빈 결과에도 같은 타입을 적용한다. 값과 NULL 정책은 유지했다.
- 품질 5종 + metric 1종, 파일별 행수/schema/SHA 재검증과 MinIO immutable publication 절차는 기존 실행기를 그대로 사용한다.

## 검증 결과
- PySpark 미설치 Windows Python에서 **40개 통과**: 정식 DuckDB 의미/물리 스키마, 실제6종 출력과 in-memory S3 게시/재검증, 엔진·메모리 변경 거부, 업로드 실패 후 재개, 일반 전체 단계와 weekly full→min 갱신/실패 복구/완료 재실행.
- 별도 network-none 로컬 컨테이너에서 **25개 통과**: 기존 native lifecycle(주입 Spark fixture), 기존 실험 DuckDB 의미검증, 레이아웃 회귀. 이 검증은 서버 Spark 성능 재측정이 아니다.
- 일반 전체 단계의 테스트 입력은 producer 형태의 합성 Parquet, 저장소는 메모리 S3 대역이다. 실제 MinIO 서버에 게시하지 않았다. 테스트 로그의 PUBLISHED는 이 대역에 대한 것이다.
- compileall, git diff --check, repository CLI --help, 예제 요청의 orchestration plan 통과.
- 독립 코드 검토에서 추가 production 회귀를 발견하지 못했다. 검토 중 지적된 weekly fixture의 native 강제값은 DuckDB로 수정하고 재검증했다.
- 앞선 실패(다음 단계 timestamp schema 불일치, fixture의 native 강제)는 위 수정 후 재실행으로 해소했다.

## 남은 운영 범위
- 서버 배포, 실제 원천 스냅샷 전체 처리, 실제 MinIO 게시, DB 적재는 실행하지 않았다.
- 사용자 요청에 따라 위 구현·테스트·문서를 함께 커밋한다. 기존 서버 weekly 배치/배포 구성은 변경하지 않았다.
