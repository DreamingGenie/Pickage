# MinIO raw → Curated 통합 실행기 작업 기록

## 변경 범위와 계획 (2026-09-14)

사용자가 승인한 계획을 구현한다. MinIO raw의 명시적 단일 스냅샷 입력을 받아 기존 전처리를
실행하고 검증된 Curated bundle을 게시한다. 수집, BigQuery/API 호출, DB 적재, Java 구현,
운영 스케줄 설정과 과거 전체 데이터 재검증은 제외한다. Jira 연결은 대화에서 승인한 대로
보류하며 임의 이슈 키를 만들지 않는다.

- 기반: 작업 09 커밋 `464c75e`; 별도 `codex/raw-to-curated-pipeline` 브랜치/워크트리.
- 원래 작업 디렉터리와 09의 미커밋 로그는 변경하지 않는다.
- 입력/출력 계약과 단일 실행기 → 기존 단계 adapter → DB 없는 새 S 참조 수 →
  재개/중복 방지 → 완료 bundle → 작은 두 스냅샷 통합 검증 순서로 구현한다.
- 주 담당: request/상태/실행/게시 관리 및 최종 검증. 독립 담당: 기존 단계 adapter,
  새 스냅샷 참조 수 adapter. 공용 파일을 동시에 수정하지 않는다.

## 완료 기준

단일 명령으로 작은 raw를 실제 MinIO에서 읽어 Curated를 게시한다. 기존 ID 유지와 새 ID 추가,
각 결과의 값/스키마/품질, 실패와 재개, 변경 입력 거부, 완료 marker의 마지막 게시를 확인한다.
전체 규모 실행은 별도이며 작은 fixture 통과와 구분한다. 코드·실행 방법·소비 계약을 남긴다.

## 실제 진행한 작업

- 원래 작업 디렉터리는 현재 서비스 데이터 이관 작업 중임을 확인했다. 그 변경은 보존했다.
- 09 커밋에서 별도 워크트리를 생성했다. 기존 MinIO와 PostgreSQL 컨테이너는 유지한다.
- 기존 builder의 불변 manifest, `_SUCCESS`, 검증/ID 계보 구현을 확인했다.
- `pipeline.orchestration`에 plan/run/status/resume 명령, 고정 입력 요청, 단계별 checkpoint,
  로컬·원격 실행 이력과 완료 bundle 게시를 구현했다.
- snapshot → package/version → downloads interval → repository metrics → package_snapshot →
  해당 스냅샷 version dependents를 기존 계산 코드에 연결했다. native manifest 바이트와 완료 표시 형식은 유지했다.
- 참조 수 계산은 8번의 source/target 자격 판정, Node semver resolver, SQL 중복 제거 집계를 재사용한다.
  선택 밖 version 행은 NULL로 유지하며, 계산한 target에 참조가 없으면 0으로 기록한다.
- 요청의 ID 부모 검사를 기존 package/version writer 잠금 안에서도 수행하도록 optional 인자를 추가했다.
  같은 날짜를 새 코드/run ID로 재처리할 수 있도록 ID 부모 날짜와 다운로드의 직전 관측 날짜를 구분했다.
- 수집 담당자의 raw 인수 형식과 후속 Java 적재기의 Parquet 소비 경계를 문서화했다.

## 이슈와 해결 및 검증 결과

측정 결과, 발견한 오류와 해결, 미실행 항목은 [02-validation.md](02-validation.md)에 분리한다.
