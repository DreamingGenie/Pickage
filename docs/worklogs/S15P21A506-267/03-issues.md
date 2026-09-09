# 03. 이슈와 해결 기록

[작업 계획](02-plan.md) · [작업 일지](04-work-log.md) · [문서 안내](README.md)

구현·실험 중 실제 발생한 문제를 기록한다. 예상 위험은 작업 계획에 적는다.

## 이슈 목록

상태: `조사 중 / 원인 확인 / 조치 중 / 재검증 대기 / 해결 / 보류`. 재검증 근거가 있어야 해결로 기록한다.

| ID | 발견 일시 | 문제 / 영향 | 연결 단계 | 상태 | 해결 요약 | 작업·검증 근거 |
| --- | --- | --- | --- | --- | --- | --- |
| ISS-001 | 2026-09-08 +09:00 | Curated dependency invalid 25건과 V1 `NOT NULL DEFAULT` 계약의 처리 충돌 | P-01, P-03, P-06 | 해결 | 초기 NULL 적재안은 폐기. 기본 JSON 대체·품질 이력 기록을 적용했고 25건·10개 package의 품질 이력과 DB 값을 검증했다 | W-002, W-008, W-011~W-013, `evidence/full-data.json`, `evidence/reverification.json` |
| ISS-002 | 2026-09-08 +09:00 | Docker 기본 샌드박스 접근 거부, 기존 PostgreSQL 미실행 | P-01, P-06 | 해결 | 범위 확장 후 분리된 PostgreSQL 16.14 기동·연결 확인 | W-004 |
| ISS-003 | 2026-09-08 +09:00 | COPY 파일 뒤 빈 줄 추가·Windows 전송·실패 이력 누락 | P-04, P-05 | 해결 | 바이트 스트림과 종료 줄 처리 수정, 끊긴 연결의 실패 별도 기록 | V-002 |
| ISS-004 | 2026-09-08 +09:00 | 과거 입력·지연 실패가 현재 상태를 훼손할 수 있는 초기 구현 | P-05 | 해결 | 게시 이력 조회·입력 전용 재검증·attempt 식별자 조건·실제 테이블 잠금 | V-002 |
| ISS-005 | 2026-09-08 +09:00 | 기존 Curated 테스트 fixture의 import 경로 의존 | P-06 | 해결 | 기존 fixture import 구간에만 검색 경로 적용, 실제 생성기→로더 테스트 통과 | V-002 |
| ISS-006 | 2026-09-08 13:37 +09:00 | 사용자 제공 서비스 DDL과 초기 dependency NULL 완화 구현 불일치 | P-03, P-06 | 해결 | 전체 적재를 취소하고 rollback 후 `NOT NULL`·기존 comment를 복원했다. V2는 실행 관리만 유지하며 loader COPY에서 기본 JSON과 품질 JSONL을 적용했고 전체 적재·검증·동일 입력 재검증을 통과했다. | W-008, W-009, W-011~W-013, `evidence/cancelled-load.json` |
| ISS-007 | 2026-09-08 14:32 +09:00 | 빈 DB 전체 서비스 반영 SQL의 긴 실행 시간 | P-06 | 해결·후속 검토 | 최종 적재가 3,529초(58분 49초)에 `PUBLISHED`로 완료됐다. 이번 범위에서는 DDL·검증 계약을 유지하는 성능 최적화를 추가하지 않는다. | W-011~W-012, `evidence/publish-progress.jsonl`, `evidence/full-load.json` |

## ISS-001 — dependency invalid 25건과 V1 제약 처리 정책

- 관측: `V1__init.sql`은 `version.dependency JSON NOT NULL`, `transform.py`는 잘못된 requirements에서 dependency를 NULL로 만든다. 실제 승인 manifest의 `invalid_requirements`는 25다.
- 영향: 현재 V1 계약에서는 SQL NULL을 COPY할 수 없다. Curated 원본의 invalid 25개 행을 버리거나 임의로 바꾸면 원본 ID/version과 품질 추적이 끊긴다.
- 결정: 서비스 DDL은 변경하지 않는다. Curated 원본 25개 행/version은 유지하고 loader COPY 전송 시에만 기본 JSON `{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}`으로 대체한다. 원본 NULL, package/version, 기본 JSON, input run 해시를 품질 JSONL에 기록하고 count/SHA를 `quality_report`와 실행 보고서에 연결한다.
- 검증 계획: 기본 JSON 대체, 품질 JSONL count/SHA, SQL NULL 거부, V1 comment 보존, rollback을 새 contract 테스트로 확인한다.
- 상태: 해결. 기본 정책, 전체 적재, 품질 이력, 읽기 전용 DB 대조, 동일 입력 재검증을 완료했다.

## ISS-006 — 사용자 DDL 계약 정정과 전체 적재 취소

- 관측: 초기 구현은 V2에서 `version.dependency`의 `NOT NULL`을 해제하고 Curated invalid 결과를 SQL NULL로 보내도록 했다. 사용자는 V1 서비스 DDL과 `dependency` comment가 정본이며, 서비스 테이블을 완전히 보존해야 한다고 정정했다.
- 조치: 진행 중이던 `load-267-full-v1`을 취소했다. `psql`은 PUBLISH 단계에서 `canceling statement due to user request`로 실패했고, service package/version/current가 각각 0인지 확인했다. 검증 DB의 `NOT NULL`과 comment를 원래 값으로 복원했다.
- 최종 정책: 원본 Curated 25개 NULL 행과 version은 유지한다. loader COPY 전송 시 기본 JSON `{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}`으로만 대체하고, 원본 NULL·ID/version·기본 JSON·input run 해시를 품질 JSONL로 기록한다. 품질 JSONL의 count/SHA는 `quality_report` JSONB와 실행 보고서에 연결한다.
- 상태: 해결. 기본 JSON contract 31개 테스트, 전체 PUBLISHED, verifier 12개 검사와 동일 입력 재검증 11개 검사를 통과했다.
- 근거: [취소·rollback 증거](evidence/cancelled-load.json), [최종 적재 증거](evidence/full-load.json), [최종 데이터 검증](evidence/full-data.json), [동일 입력 재검증](evidence/reverification.json), W-008~W-013.

## ISS-002 — 검증 DB 준비와 Docker 접근

- 관측: 기본 샌드박스에서는 Docker 설정 파일·named pipe 접근이 거부됐다. 범위 확장 후 읽기 전용 조회는 성공했다. 실행 중인 컨테이너는 MinIO뿐이며 `postgres:16` 이미지는 없다.
- 대안: 이미 보유한 `postgres:16-alpine` 이미지로 이번 작업 전용 컨테이너·볼륨을 생성한다. 기존 중지된 프로젝트 컨테이너나 볼륨은 변경하지 않는다.
- 결과: `pickage-267-validation` 컨테이너에서 PostgreSQL 16.14 기동·연결 성공. 외부 포트 없는 `--network none`, 전용 볼륨 `pickage_267_validation_pgdata` 사용. 테스트마다 생성한 별도 DB만 정리하고, 전체 검증 DB `pickage_267_full`은 보존한다.

## ISS-003 — COPY 빈 줄과 연결 종료 후 실패 기록

- 재현: 초기 실제 DB 테스트 10개 중 9개 실패. 첫 COPY에서 `invalid input syntax for type integer: ""`, 이어 실패 기록 시 `OSError: [Errno 22] Invalid argument`가 발생했다.
- 원인: 파일 읽기 루프 종료 후 빈 `data` 변수로 마지막 줄바꿈을 판단해 각 파일 끝에 빈 행이 추가됐다. psql 오류 종료 후 이미 닫힌 stdin에 ROLLBACK을 쓰는 예외도 누락됐다.
- 조치: 파일은 LF 종료를 확인한 뒤 binary pipe로 1 MiB씩 그대로 전송한다. PostgreSQL COPY TEXT의 이스케이프를 사용해 문자열 내부 개행과 `\\.`가 실제 제어행이 되지 않게 했다. 연결이 종료된 경우 별도 psql 호출로 실패 이력을 남기며 모든 파이프를 닫는다.
- 결과: 정상 문자열·NULL·JSON 복원, 잘못된 JSON의 DB COPY 실패 기록, package 반영 직후 오류 주입의 전체 롤백과 재시도 테스트 통과.

## ISS-004 — 게시·재검증·재시도 상태 경계

- 발견: 초기 구현은 current와 같은 입력만 이미 게시된 것으로 보거나, 입력 재검증이 끝나기 전에 REVERIFIED 상태를 기록했다. 최초 active attempt 저장과 실패 기록 조건도 보강이 필요했다.
- 조치: 모든 성공 실행 이력에서 입력 해시를 찾고, 이미 게시한 입력은 입력만 재검증한다. 검증에 성공한 뒤 REVERIFIED를 기록하며 서비스 속성·current는 변경하지 않는다. 실패 기록은 자신의 attempt와 일치하는 PREPARING execution에만 반영한다. active attempt의 소유 관계는 복합 FK로 보장한다.
- 추가 보호: dataset 세션 잠금은 충돌 시 즉시 실패한다. 실제 서비스·current 테이블 쓰기 잠금을 잡은 뒤 최신 snapshot·parent와 기존 ID 대응을 다시 검사한다. 동일 입력의 다른 적재 계약은 보수적으로 거부한다.
- 결과: 과거 입력을 같은 실행 ID와 새 실행 ID로 각각 재검증해도 최신 속성·current 유지, 이전 실패가 새 재시도의 상태를 바꾸지 않음, 재검증 실패가 원래 PUBLISHED를 취소하지 않음 확인.

## ISS-005 — 기존 테스트 fixture 검색 경로

- 원인: 기존 Curated 테스트는 unittest discovery가 추가하는 디렉터리를 전제로 `storage`를 import한다. 새 통합 테스트에서 패키지 경로로 바로 가져오면 `ModuleNotFoundError`가 발생했다.
- 조치: 해당 fixture를 import하는 구간에만 기존 테스트 디렉터리를 검색 경로에 넣고 즉시 복원했다. 제품 코드는 변경하지 않았다.
- 결과: 실제 Curated 생성기로 만든 package 2행·version 2행이 승인 manifest 검증부터 PostgreSQL PUBLISHED까지 연결되는 테스트 통과.

## ISS-007 — 첫 전체 적재의 서비스 반영 시간

- 관측: 새 실행은 13:45:30 +09:00에 시작했다. 14:32:02 확인 시 전체 경과 약 46분, 서비스 version 반영 SQL만 약 27분이었다. DB CPU는 약 1코어, 메모리는 13/16 GiB였고 오류 로그는 비어 있었다.
- 확인한 실행 경로: staging은 COPY로 적재하지만 서비스 반영은 `INSERT ... SELECT ... ON CONFLICT`를 사용한다. 빈 DB 첫 적재에도 동일한 경로를 사용하며 서비스 PK·UNIQUE·FK를 유지한다. 원천 입력·staging 검증이 끝난 후 이 구간이 오래 걸리는 것은 실제 SQL 상태로 확인했다.
- 원인 판단의 한계: 인덱스 유지와 참조 제약 처리 비용이 포함되지만 각 내부 연산의 소요 시간은 개별 계측하지 않았다. 단일 실행 SQL의 상세 행 진행률도 수집하지 못했다.
- 진척 확인: [publish-progress.jsonl](evidence/publish-progress.jsonl)에 실행 상태와 WAL 위치를 기록했다. 14:33:07~14:35:27 사이 PostgreSQL 전체 WAL이 249,978,880 bytes 증가했고 현재 반영 세션의 WALWrite도 관측했다. WAL은 인스턴스 공용 지표이므로 이 값만으로 반영 행 수를 계산하지 않는다.
- 현재 조치: 전체 적재는 3,529초(58분 49초)에 PUBLISHED로 완료됐고 실제 소요 시간을 기록했다. 빈 DB 전용 반영 경로의 성능 최적화는 이번 범위에 포함하지 않았으며, 최종 DDL·검증 계약을 유지하는 별도 후속 검토로 남긴다.

## 이슈 상세 양식

### ISS-XXX — [문제 제목]

- 발견 일시 / 담당자: `[작성 필요]`
- 상태 / 연결 단계·완료 기준: `[작성 필요]`
- 환경 / 코드 커밋 / 입력 run·적재 실행 ID: `[작성 필요]`
- 증상·정확한 오류 / 기대 동작과 실제 동작: `[작성 필요]`
- 재현 조건·명령 또는 쿼리 / 로그 위치: `[작성 필요]`
- 영향 범위 / 서비스 데이터 반영 여부: `[작성 필요 — 확인하지 못했다면 미확인]`

#### 원인 조사

| 가설 | 확인 방법 | 관측 결과·근거 | 판정 |
| --- | --- | --- | --- |
| `[작성 필요]` | `[작성 필요]` | `[작성 필요]` | `[미확인 / 배제 / 원인 확인]` |

확정 원인: `[작성 필요 — 증상과 원인을 구분하고 근거 연결]`

#### 해결 시도

| 일시 | 실제 시도한 조치 | 선택 이유 | 실제 결과·근거 | 유지 / 되돌림 및 이유 |
| --- | --- | --- | --- | --- |
| `[작성 필요]` | `[작성 필요]` | `[작성 필요]` | `[작성 필요]` | `[작성 필요]` |

#### 최종 해결과 재검증

- 채택한 해결 방법 / 변경 파일·커밋: `[작성 필요]`
- 데이터 정리·복구·재실행 내역: `[작성 필요 또는 해당 없음 — 사유]`
- 재검증 환경·명령 / 기대값 / 실제값: `[작성 필요]`
- 원래 재현 조건과 관련 경계값의 검증 근거: `[V-XXX 및 로그 링크]`
- 결과 / 해결 일시: `[해결 / 재검증 대기 / 보류 및 이유]`
- 남은 영향·한계 / 재발 방지 / 후속 작업: `[작성 필요]`
