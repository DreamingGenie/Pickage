# S15P21A506-278 작업 기록

보유 npm 다운로드 데이터 검증 및 MinIO Bronze 입고 작업의 진행 기록이다.
267·269와 같은 범위·계획·이슈·작업 일지·결과 형식을 사용한다.
입력 조사·검증기·계보 검사·다운로드 전용 Bronze 입고 경로를 구현하고 전체 입력을
`pickage-raw` Bronze에 게시했다. 동일 입력 재검증과 기존 객체 보존 확인까지 완료했다.

| 항목 | 내용 |
| --- | --- |
| 연결 티켓 | S15P21A506-278 — 사용자가 만든 현재 브랜치에서 확인. 원격 Jira 제목·설명·상태는 미확인 |
| 작업명 | 보유 다운로드 데이터 검증 및 MinIO Bronze 입고 |
| 현재 브랜치 | `feat/S15P21A506-278-downloads-bronze-ingest` |
| 분기 기준 | 사용자 설명상 269 브랜치에서 분기. 시작 HEAD에 267·269 구현 커밋 포함 |
| 시작 HEAD | `e3a8a6240b1edd1fb45dedc0d4a9a9cbc3bdf074` |
| 착수 확인 시각 | 2026-09-08 22:49:40 +09:00 |
| 입력 | 로컬 `data/raw/downloads`의 대상 CSV, 본 실행 JSONL·메타데이터, 일별·상태 Parquet |
| 출력 | `pickage-raw`의 다운로드 전용 실행 경로, 입력 manifest와 검증 결과·완료 표시 |
| 현재 상태 | P-00~07·AC-01~09 완료 |
| 관측 근거 | [`bronze-load.json`](evidence/bronze-load.json), [`source-summary.json`](evidence/source-summary.json), [`lineage-summary.json`](evidence/lineage-summary.json), [`tests.json`](evidence/tests.json) |
| 커밋 / MR | 278 작업의 구현·문서 커밋과 MR은 아직 없음. 선행 구현은 278의 신규 작업으로 계산하지 않음 |

| 문서 | 역할 |
| --- | --- |
| [01 범위](01-scope.md) | 목표·입력 역할·행 단위·보존 조건·완료 기준 AC |
| [02 계획](02-plan.md) | 단계 P·선행 조건·산출물·검증 순서 |
| [03 이슈](03-issues.md) | 미확인 사항 ISS·기존 기록의 한계·해결 조건 |
| [04 작업 일지](04-work-log.md) | 실제 수행 W·확인 시각·결과 |
| [05 결과](05-results.md) | 검증 V·AC별 판정·실측과 기존 참고값·후속 인계 |

## 선행 자료와 기록 원칙

- [267 작업 기록](../S15P21A506-267/README.md): package/version 적재 및 공통 실행 이력.
- [269 실행 이력 계약](../S15P21A506-269/06-history-contract.md): 스냅샷 날짜와 실행의 관계.
- [스냅샷 시간 정책](../../../pipeline/snapshot/README.md): 후속 다운로드 구간 집계의 `[P,S)` 기준.
- [기존 MinIO 안내](../../../pipeline/minio/README.md): deps.dev 입고 경로와 불변 객체·검증 규칙. 다운로드 입력 지원 여부와 현재 저장소 상태는 별도로 확인한다.
- [다운로드 검증·입고 모듈](../../../pipeline/downloads/README.md): 선택 파일 계약, 계보 검사,
  `npm-downloads/v1/run_id=<run-id>` Bronze 완료 규칙과 실행 명령.

착수 전 합의한 작업 요구사항은 01·02에 옮겨 적어 이 문서 묶음만으로 이해할 수 있게 한다.
실측값은 확인한 증거 파일과 범위를 함께 기록한다. 입고 완료도 Curated 집계,
PostgreSQL 게시 또는 서비스 준비 완료와 구분한다. 문서의 경로·수치는 확인 범위를 함께 적는다.

착수 시 기존 미추적 항목은 개인 실행 상태, 키 파일, 임시 Jira 문서와 개인 조회 도구였다.
278 작업에서 이 항목들을 수정하거나 커밋 대상으로 추가하지 않는다. 원본 데이터·인증정보는
문서 저장소에 복사하지 않고, 실행 후 검토 가능한 요약 증거만 이 작업 기록에 남긴다.
