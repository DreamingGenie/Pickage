# 실제 로컬 입력·DB 정합성 검사

이 경로는 8번 완료 후 사용자가 승인한 9번 실제 검증을 구현한다. 기존 합성/native CLI의
작은 입력 제한은 유지한다. 실제 DB에서는 SELECT만 수행하며 loader를 호출하지 않는다.
백엔드/API, 재적재, 게시, 성능 실험을 실행하지 않는다.

## 구성과 실행

- `real_db.collect`: 명시한 Docker 컨테이너·DB에서 identity, 5개 테이블 계약, snapshot,
  execution/attempt/current, partition/receipt 메타데이터 수집. 출력 폴더는 새 경로여야 한다.
- `real_scan`: package/version 전체 COUNT, PS/PVS 날짜별 전체 집계. SELECT별 최대 1,200초,
  lock 2초, parallel worker 0, work_mem 32 MB. SQL과 단계별 결과·실패·시간을 보존한다.
- `real_sources`: 명시한 원래 저장소의 작은 JSON 및 candidate SQL/inventory 연결.
  파일당 8 MiB 이하, symlink/reparse·경로 이탈·JSON 중복 키를 거부한다.
  현재 수집 배치의 PS receipt 위치를 지원하므로 다른 배치는 경로 adapter가 필요하다.
- `real_samples.sample_sources`: 첫·중간·마지막 날짜의 PS Parquet를 해시 검증한 뒤
  날짜당 최대 20개 결정적 표본을 실제 DB와 NULL-safe 비교한다. 파일당 128 MiB,
  전체 256 MiB, DuckDB 512 MB·1 thread·spill 0이다.
- `real_report`: 수집 전후 메타데이터, 전수 DB 집계, 로컬 원천 receipt, 표본 파일 pin을
  통합한다. 입력 및 검증 코드 SHA를 저장하며 기존 출력 파일은 덮어쓰지 않는다.

```powershell
python -B -m pipeline.integrity_validation.real_scan `
  --container pickage-267-validation --database pickage_267_full_defaulted `
  --output data/<new-run>/full-scan

python -B -m pipeline.integrity_validation.real_report `
  --original-root C:/Users/SSAFY/workspace/S15P21A506 `
  --plan C:/Users/SSAFY/workspace/S15P21A506/data/vd-db-reload-timed-20260912-2354/prepared-plan.json `
  --evidence-dir data/<run> --output data/<run>/integrity-report.json
```

보고서는 `metadata/`, `metadata-after/`, `full-scan/`, `source-samples.json`이 모두 준비된
evidence 디렉터리를 받는다. 메타데이터는 `real_db.collect(container, database, receipt_schema,
output_path)`를 검사 전후 각각 호출하고, 표본은 `sample_sources(original_root, plan, container,
database)` 반환 JSON을 저장한다. 기존 조사 결과를 보고서로 묶을 때 DB 전체 검사를 재실행하지 않는다.
보고서 CLI는 FAIL/NOT_RUN이 있으면 종료 코드 2를 반환한다. 모든 부분 검사 통과도
9번 전체 완료를 의미하지 않으므로 readiness 세 값은 항상 false다.

다른 이름의 표본 결과는 `--samples <JSON>`으로 지정한다. 실패 active attempt가 있으면
해당 execution의 과거 시도를 별도 읽기 조회하여 `prior-attempts.json`으로 제공한다.
보고서는 같은 execution의 성공 상태·이전 완료 시각·기대 counts가 맞는지 검증하고,
이 근거가 없으면 해당 이전 성공 검사를 NOT_RUN으로 남긴다.

## 해석할 때 지킬 경계

- 각 SQL은 **서로 다른** REPEATABLE READ READ ONLY 트랜잭션이다. 검사 전후 metadata가
  같아도 모든 조회가 하나의 MVCC snapshot을 공유했다거나 다른 세션의 payload 쓰기가
  전혀 없었다는 증거는 아니다.
- 전체 COUNT·NULL 개수·합계 일치는 새로 읽은 DB 집계와 과거 원천 검증 기록의 일치다.
  모든 원천 키·값의 전수 일치 또는 semver 재계산을 독립 입증하지 않는다.
- PS history 로컬 manifest는 pretty JSON이다. 게시용 SHA는 생산 코드의
  `package_snapshot.policy.canonical_bytes`로 계산한다. base observed/candidate는 raw bytes,
  VD DB manifest는 `requirements_resolution.policy.sha256` 규칙을 사용한다.
- `COMPLETE` 계산과 `PARTIAL` 해석 품질을 함께 유지한다. 과거 manifest의 누락된
  `build_contract_sha256`를 현재 해시로 채우지 않는다.
- 카탈로그 PK/FK 검증은 DB가 유효한 제약을 선언·검증한 증거다. 별도 전수 anti-join 실행을
  했다는 뜻은 아니다. 임시 PostgreSQL의 rollback 시험도 실제 대용량 loader 복구와 구분한다.

이번 실측과 미실행 항목은 [결과 로그](../../docs/worklogs/09-integrity-validation/05-real-integration-results.md)에 있다.
