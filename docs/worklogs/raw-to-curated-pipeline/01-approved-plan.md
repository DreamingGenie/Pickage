# MinIO raw → Curated 통합 실행기 구현 계획

2026-09-14 사용자 요청에 대한 계획. 구현·배포·실제 데이터 실행은 아직 시작하지 않았다.

## 목표와 범위

MinIO raw의 수집 완료 입력 한 스냅샷을 받아 package/version, snapshot 기준 자료,
package_snapshot, version dependents 및 관리·품질 데이터를 생성하고 검증된 Curated 묶음을 게시한다.
수집·외부 API·BigQuery 감지·DB 접속/적재·Java 구현은 제외한다. 주기 실행은 후속 연결이다.
과거 전체 데이터 재검증은 생략한다. 새로 생성한 스냅샷의 정확성과 파일 검증은 유지한다.

## 현재 재사용 근거

- `pipeline/curated/README.md:14-24`, `build.py:142`: raw → package/version/ID mapping 및 MinIO 게시.
- `pipeline/snapshot/README.md:13-34`: Projects 기준 날짜·정확한 시각·직전 날짜 후보 생성. load 모듈은 호출하지 않는다.
- `pipeline/downloads_interval/README.md`: 다운로드 raw+상태+대상 목록, package population, calendar → 구간 집계.
- `pipeline/repository_metrics/README.md:14-25`, `build.py:158`: 동일 관측 시각의 저장소 지표 생성.
- `pipeline/package_snapshot/build.py:227-302`: 지표 통합과 Curated 게시; DB load는 별도다.
- `pipeline/version_dependents/historical_input.py:300`, `historical_production.py:331`:
  raw/Curated 입력 준비와 계산 구현. 과거 전체 모드 대신 새 S에 한정하는 adapter가 필요하다.
- `pipeline/version_dependents/historical_db_prepare.py:142`: DB 결합된 준비 경로를 이번 runner에서 호출하지 않는다.

## 구현 1 — 입력·출력 계약

`pipeline/orchestration/`를 새 상위 모듈로 제안한다. 초기에는 기존 stage 구현을 작은 adapter로 호출한다.
request에는 run ID, snapshot 날짜/UTC 시각, raw manifest 경로·SHA, 기준 calendar, 이전 ID mapping,
다운로드 대상 목록 및 참조 수 target 목록/정책의 명시적 경로를 받는다. 둘을 무조건 같은 목록으로 취급하지 않는다.
대상 목록을 직접 수집·갱신하지 않는다. 단계마다 latest를 재조회하지 않고 최초 입력을 고정한다.

각 필수 raw의 스키마, 완료 표시, 최소 manifest 필드를 정리한다. 생산자 형식이 기존 Bronze 형식과
다르면 검증 adapter로 변환하되 원본을 덮어쓰거나 수집 완료를 임의 승인하지 않는다.
출력 Parquet의 컬럼·타입·PK·NULL·UTC·JSON 표현을 문서화하여 Java가 동일하게 읽을 수 있게 한다.
ID는 기존 Curated mapping이 발급하는 계약을 우선 유지하고 후속 적재기는 그대로 소비한다.

완료 기준: 작은 정상 raw 요청이 해석되고 파일/시각/필수 컬럼/부모 ID mapping이 잘못된 요청은
전처리 전에 구체적 이유와 함께 거부된다. 필수 raw 미도착은 WAITING_INPUT으로 구분한다.

## 구현 2 — 단일 실행기와 기본 전처리 연결

제안 CLI는 `python -m pipeline.orchestration plan|run|status|resume`이다. 현재 존재하는 명령이 아니다.
plan은 확정 입력·의존 단계·출력 위치를 보여주고 run은 작업을 실행한다.

raw 검증 → package/version·ID mapping → snapshot 기준 자료 → 다운로드/저장소 지표 → package_snapshot을
연결한다. 기존 build의 검증과 게시 기능을 재사용한다. 첫 버전은 메모리·I/O 예측을 위해 단계별 순차 실행을
기본으로 하고, 동시 처리는 이후 실측으로 결정한다. DuckDB/Spark 등 계산 엔진 자체를 교체하지 않는다.

완료 기준: 작은 한 스냅샷의 파일 생성이 단일 명령으로 이어지며 BQ/npm/DB 자격증명이 없어도 실행된다.
각 단계가 사용한 입력·출력 manifest가 같은 snapshot 계보로 연결된다.

## 구현 3 — 새 스냅샷 참조 수와 DB 비의존 출력

8번에서 검증한 계산 경로를 새 S 전용 adapter에 연결한다. 07의 과거 전체 실행기를 추가로
필수 실행하는 구조를 자동 채택하지 않고, 8번 계산에 필요한 원천 입력만 준비한다.
source/target 키, 선정 대상, ID는 Curated에서 가져온다. target 중 실제 참조 관계가 없는 버전의
0을 복원하여 `(package_id, version, snapshot_at, dependents_count)` Parquet로 내보낸다.
계산 완료와 해석 PARTIAL은 분리하며 예전 manifest의 readiness를 변경하지 않는다.

새 S의 계산은 필요한 기존 source 버전도 포함한다. 과거 229일을 다시 계산하지 않는다.
완료 기준: 두 작은 스냅샷에서 신규 target 버전 때문에 기존 source의 관계가 이동하는 예제,
0/NULL/미해석 정책, 신규 패키지 ID 추가와 기존 ID 보존을 확인한다. DB 접근이 없어야 한다.

## 구현 4 — 재개·중복 방지·실행 로그

각 stage의 INPUT_READY/RUNNING/COMPLETE/FAILED 상태, attempt, 시작/종료 시각, 오류,
입력·산출물 SHA를 실행 기록에 저장한다. request와 manifest는 불변, 진행 상태는 별도로 둔다.
초기 운영은 하나의 실행 호스트·하나의 활성 snapshot run을 기본으로 하며 ID 발급도 직렬화한다.
다중 호스트 분산 실행 잠금은 초기 지원 대상으로 선언하지 않는다.

resume은 로그의 COMPLETE만 믿지 않고 저장된 manifest·산출물·입력/코드 계약을 확인한 뒤
완료 단계를 재사용한다. 게시 직후 상태 저장 전 중단되어도 완료 marker로 실제 결과를 확인한다.
실패 단계부터 새 attempt로 재개하며 완료 artifact를 덮어쓰지 않는다. 바뀐 입력은 새 run으로 처리한다.

완료 기준: 같은 run 두 번 실행, 중간 실패, 프로세스 재시작, 게시 직전/직후 중단,
다른 입력으로 resume, 동일 호스트 동시 실행 시험을 통과한다.

## 구현 5 — Curated 묶음 게시와 소비 계약

기존 dataset별 불변 출력 경로를 재사용한다. 상위 bundle manifest에는 모든 파일을 다시 복사하는
대신 각 dataset manifest의 정확한 경로·SHA와 snapshot/품질/ID 부모를 연결한다.
모든 필수 단계가 검증된 뒤 bundle manifest와 그 SHA를 가리키는 완료 marker를 마지막에 쓴다.
중간 산출물은 보존하지만 소비자는 각 dataset의 독립적인 latest 대신 완료 bundle만 선택한다.

bundle 완료는 Curated 생성 완료이며 DB 적재 성공을 의미하지 않는다. Java 인수 문서와
예제 manifest를 제공하고, DB 타입·트랜잭션·적재 이력 구현은 담당자에게 남긴다.
NULL/0·PARTIAL 허용 범위는 기존 지표 정책대로 기록하며 새로운 허용 정책은 명시적으로 결정한다.

완료 기준: 필수 결과 하나가 실패하면 bundle 완료 marker가 없으며, 이전 완료 bundle은 유지된다.
marker의 SHA와 manifest, 참조된 모든 dataset/file이 일치한다. 같은 run 재게시는 멱등적이다.

## 구현 6 — 로컬 통합 검증과 인수 문서

작은 두 개의 연속 raw snapshot을 MinIO에 준비해 실제 객체 읽기/쓰기와 전체 runner를 시험한다.
새 결과 자체의 키/값 비교는 독립적인 작은 정답 예제를 사용한다. DB와 수집기는 실행하지 않는다.
실제 raw 한 스냅샷 실행은 입력 계약과 자원이 준비된 뒤 별도 실행·로그로 확인하고,
작은 시험만 통과한 상태를 실제 규모 완료로 보고하지 않는다.

최종 인수물: runner/adapter, request 예제, raw·Curated 계약, bundle 예제, 단계별 작업 로그,
resume/중단 절차, 테스트 결과와 실측·미실행 목록. 기존 9번 코드/커밋은 보존하고 구현 시 별도
작업 브랜치/worktree와 작업 로그를 사용한다. Jira 연결 정책은 별도 작업 착수 때 기존 승인의
적용 범위와 실제 이슈 상태를 확인하며 임의 키를 만들지 않는다.

## 주요 위험과 대응

- raw 미완료/혼합 snapshot: 명시적 입력 고정·준비 검사·WAITING_INPUT.
- 기존 ID 재발급/동시 부모 변경: 승인 mapping 계보·단일 writer·부모 변경 거부.
- 새 날짜인데 과거 전체 계산: 계획에 단일 S 범위를 표시하고 실제 생성 날짜를 검사.
- 부분 결과를 전체 완료로 오인: dataset marker와 bundle marker 분리·실패 주입.
- DB 의존성 유입: DB credentials 없이 통합 실행하고 호출 경계에서 DB/API 접근을 차단하는 테스트.

자동 감지·운영 스케줄·수집·Java 적재는 이번 계획의 완료 조건에 넣지 않는다.
