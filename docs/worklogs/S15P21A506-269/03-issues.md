# 03. 이슈와 해결 기록

| ID | 현상 / 근거 | 처리 / 상태 |
| --- | --- | --- |
| ISS-001 | 267 공통 loader·V2가 같은 작업 트리에서 진행 중 | 새 경로만 소유, 기존 loader·마이그레이션·DB 연동은 합류 대상으로 유지 |
| ISS-002 | 처음에는 별도 Snapshots.Time 목록을 정본으로 계획 | 사용자 Projects 기준 지시로 해결. 실제 Projects 파일의 SnapshotAt으로 확인한 목록을 고정 |
| ISS-003 | package/version·requirements·pkg_project의 로컬 원천은 2026-08-31 한 날짜 | 과거 전체 모집단·의존성 집계를 미지원으로 기록 |
| ISS-004 | 기존 로컬 `_MANIFEST.json`에는 snapshot DATE와 실행 시각만 있고 원천 SnapshotAt이 없음 | 실제 시각을 폴더·started_at으로 대체하지 않음. 승인 Curated report/원천 timestamp 대조 필요 |
| ISS-005 | Jira 연결 도구 없음 | 사용자 지정 S15P21A506-269로 로컬 기록. 원격 검색·댓글·상태 변경 미실행 |

## ISS-006 — footer 통계의 exactness 플래그가 없음

현재 BigQuery Parquet에서 `min_is_exact`/`max_is_exact`가 NULL이다. 이를 true로 취급하지 않는다.
Apache Parquet 명세에서 min_value/max_value는 하한·상한이므로 둘이 같은 timestamp이고
명시적 null_count가 0, scalar value 수가 row 수와 같으면 상·하한 사이의 유일한 값으로 확인한다.
이는 정상적인 footer 통계에 대한 검증이며 모든 파일 바이트나 지표 값의 무결성 검증은 아니다.

구현 검토에서 전체 파일을 읽는 footer 해시 계산, 없는 null_count를 0으로 바꾸는 처리를 발견해
실제 데이터 실행 전에 수정 요청했다. 수정과 테스트 결과는 05에 기록한다.

## ISS-007 — 최종 독립 검토

- DuckDB 파일 손상/IO 오류까지 SnapshotAt 누락이라고 표시하던 메시지: 원래 오류 내용을 보존하도록 수정.
- 허용한 TIMESTAMPTZ가 footer에서는 `+00`으로 표시되어 parser가 거부: 입력 어댑터에서 `+00:00`으로 정규화하고 실제 timestamp-with-timezone Parquet fixture로 검증.
- footer 해시 회귀 테스트가 Path.read_bytes만 금지: 실제 read 크기를 trailer 8 bytes + footer 길이로 검증하도록 강화.
- 환경 없는 PostgreSQL unittest는 skip: 의도한 선택 테스트이며 이번 실행 러너는 skip이 하나라도 있으면 실패하도록 확인했다. 실제 결과는 3개 실행, skip 0.

최종 단위 검사 17개 및 실제 PostgreSQL 검사 3개가 통과했다. [결과·증거](05-results.md) 참조.

문제를 발견하면 증상·근거·조치·재검증을 추가한다. 승인·완료를 추측으로 채우지 않는다.

## ISS-008 — 공통 실행 한 행과 여러 기준 날짜의 관계

기존 실행 이력의 단일 snapshot 컬럼에 229개 날짜 중 하나를 대표로 넣으면 실제 입력 범위를
표현할 수 없다. V3에서 snapshot-reference 부모의 단일 날짜/시각/Curated run만 NULL로 두고,
실행별 날짜·원천 TIMESTAMPTZ·직전 날짜를 연결 테이블에 기록했다. 다른 dataset의 필수값 제약은
유지했다. 정확한 목록·시각·직전 날짜, 원자성, 기존 날짜 보존 검증은 V-005~006에서 통과했다.

## ISS-009 — V3 추가로 기존 package/version 계약 해시가 달라짐

기존 계약 해시가 모든 마이그레이션과 loader 코드를 포함하므로 V3만 추가해도 재실행이 거부됐다.
동일 ID·동일 입력의 기존 PUBLISHED 실행만 새 계약으로 재검증하도록 허용하고, 새 hash는
attempt의 `validation_contract_sha256`에 남긴다. 부모의 최초 계약 해시는 변경하지 않는다.
다른 입력·미완료 실행·새 ID를 이용한 우회 거부와 기존 성공 보존 회귀 테스트가 통과했다.
