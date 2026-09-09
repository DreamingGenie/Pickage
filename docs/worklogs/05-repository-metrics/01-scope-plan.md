# 05 저장소 지표 작업 범위와 계획

작성일: 2026-09-09. 사용자 요청으로 구현을 시작한다.

## 목표와 변경 범위

승인된 package/version의 기존 ID를 유지하면서 같은 SnapshotAt의 versions_full 저장소 후보를 선정하고 Projects stars/open_issues를 연결한다. `pipeline/repository_metrics/`에 전용 구현·테스트·실행 문서를 추가한다. 코드와 산출물은 05 worktree에만 쓴다. 03 코드, 공통 모듈, DB DDL, package/version current 포인터는 수정하지 않는다. PostgreSQL 통합 적재는 06 범위다.

## 사용자 확정 사항

- 유효 URL 선택 후 같은 시각 Projects 관측이 없으면 선택 저장소를 유지하고 지표 NULL과 사유를 남긴다. 관측값을 얻기 위해 다른 버전 저장소로 바꾸지 않는다.
- 후보 정렬은 `ordinal DESC, published_at DESC NULLS LAST, version ASC`를 사용한다.
- 동일 `(SnapshotAt, provider, project_path)`의 서로 다른 지표값은 충돌로 기록하고 해당 저장소의 두 지표를 NULL로 둔다. 동일 지표 중복은 하나로 합친다.
- 05 전용 환경에 PySpark를 추가해 구현·검증한다. 기존 03 환경은 변경하지 않는다.
- Projects는 정확히 같은 시각만 사용한다. 다른 snapshot의 package/version 원천을 과거 모집단으로 소급하지 않는다.
- 전체 실행 표본 검토 후 추가 확정: GitHub의 비교용 경로만 소문자로 통일한다. 선택 URL과 원래 경로는 보존하고 GitLab은 정확한 경로 비교를 유지한다. 이 결정은 `repository-metrics-v2`에 기록한다.

## 입력 계약과 출력 계획

입력: 명시한 완료 Curated run의 manifest/_SUCCESS, 같은 Bronze versions_full run 및 파일 SHA, 승인된 snapshot candidate와 Projects inventory, 각 로컬 원본 파일 목록과 SHA. 저장소 API 재호출은 없다.

출력: package/snapshot당 한 행의 지표, 버전별 후보와 선정 근거, 저장소별 관측값과 충돌 근거, 품질 요약, 원천/정책/코드 해시를 담은 manifest. 성공 marker는 출력 재검증과 입력 불변성 확인 뒤 마지막에 작성한다. 로컬 검증 완료와 MinIO 게시 완료는 따로 기록한다.

## 순서

1. 입력 승인 증거와 SnapshotAt 일치, 실행 환경, 자원·출력 위치 확인.
2. 별도 입력 어댑터와 Spark 변환기를 독립 구현. 공통 순수 URL 정규화·시간 정책을 읽기 전용 재사용.
3. 작은 실제 Parquet fixture로 후보 fallback, 시점, provider, subgroup, NULL/0, 중복·상충, ID/행 수, 잘못된 입력 차단 검증.
4. fresh output에 쓰고 재독해 key/count/schema/hash 검증. 재실행과 실패 시 marker 미게시 검증.
5. 승인 실데이터에 입력 검증·계산을 수행하고 새 측정값과 제약 기록. 과거 원천 부재는 완료로 표시하지 않음.
6. 독립 코드 검토 후 문제 수정, 결과 기록 및 후속 06 소비 계약 안내.

## 완료 판단과 검증 범위

- 승인된 각 package가 출력에 정확히 한 번 존재하고 ID가 유지된다.
- 저장소 후보는 승인된 동일 시점 버전에만 속하며 ordinal fallback과 동률 정렬이 재현된다.
- 지표 관측 시각이 정확히 일치하고 provider/path로 연결한다. NULL, 실제 0, 부재, 충돌을 구분한다.
- 여러 package가 같은 저장소를 공유해도 관측값을 더하지 않으며 행이 증식하지 않는다.
- 완성된 입력/출력 해시와 건수, 후보/매핑/NULL/충돌 요약이 일치한다.
- 실패/불일치/다른 입력의 동일 run 덮어쓰기를 차단한다.
- 원래 worktree와 공통 파일을 변경하지 않는다. 실제 서버/DB 미실행은 별도 한계로 남긴다.

## 구현 선택

처리는 Spark DataFrame을 사용하고, 기존 DuckDB는 입력 Parquet 메타데이터 및 독립 표본 검증에 재사용한다. 대량 입력을 Python list로 수집하지 않는다. package/version 생성 파이프라인 자체의 Spark 전환은 범위 밖이다.

공식 근거: https://spark.apache.org/docs/3.5.7/api/python/getting_started/install.html , https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrameReader.parquet.html , https://spark.apache.org/docs/3.5.7/configuration.html . Spark 파일 쓰기 성공 marker와 Pickage 실행 승인 marker를 구분한다.
