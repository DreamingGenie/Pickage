# 실제 로컬 통합 검증 결과 — 2026-09-14

## 변경 범위와 기준

사용자 요청: “진행해봐. 작업 로그들은 꼭 잘 남겨놓고”. 백엔드는 제외하며 Jira 연결 보류를 유지했다.
계획은 [04-real-integration-plan.md](04-real-integration-plan.md), 기준 HEAD는
`91ccc9690c543b4e1622eba5c49f7df4b43c42c6`이다.
작업은 `C:\Users\SSAFY\workspace\S15P21A506-09-integrity-validation`의
`pipeline/integrity_validation/`와 이 로그 폴더에 한정했다.

실제 검증 대상은 로컬 컨테이너 `pickage-267-validation`, PostgreSQL 16.14,
DB `pickage_267_full_defaulted`, system_identifier `7683005534478250019`다.
실제 DB 쿼리는 세션과 트랜잭션 모두 읽기 전용이며 재적재·DDL·게시 이력 수정을 실행하지 않았다.

## 실제로 진행한 작업

1. 8번 서비스 전환 기록과 live catalog를 확인했다. PVS의 229개 child partition 및
   `vd193_reload_20260912_ready01.reload_partition` receipt를 연결했다.
2. 5개 서비스 테이블의 열 순서·타입·NULL·순서 있는 PK/FK 및 validated 상태를 검사했다.
   PV 1개, snapshot-reference 1개, PS 229개, VD 229개 게시 execution과 current/attempt를 대조했다.
3. candidate·연결 inventory/SQL·VD run manifest·PS 229일 manifest/검증 receipt 등
   명시적 로컬 파일 463개를 읽고 생산자별 SHA 규칙과 DB JSON을 대조했다.
4. 실제 DB의 package/version/PS/PVS 전체를 읽어 COUNT 및 날짜별 품질 집계를 계산했다.
5. PS 첫·중간·마지막 날짜의 실제 Parquet 3개를 읽어 표본 43건의 날짜·downloads·stars·open_issues를
   DB와 대조했다. 파일 SHA를 읽기 전후 확인했고, 보고서에서 DB manifest의 파일 pin과도 연결했다.
6. 별도 PostgreSQL 임시 컨테이너에서 검증 SQL·복합 FK·PK·읽기 전용 위반·rollback을 시험했다.
7. 검사 전후 메타데이터를 다시 수집하여 동일함을 확인하고 통합 JSON 보고서를 생성했다.

## 실측 결과

| 대상 | 직접 읽은 행 수 | 비교 결과 |
| --- | ---: | --- |
| package | 11,080,940 | 게시 counts와 일치, 잘못된 ID·빈 이름 0 |
| version | 54,188,349 | 게시 counts와 일치, 잘못된 ID·빈 버전·음수 ordinal 0 |
| snapshot | 229 | 날짜·reference chain 일치 |
| package_snapshot | 646,219,939 | 229일 건수·지표별 non-NULL 개수·합계 모두 기존 원천 검증 receipt와 일치, 음수 0 |
| package_version_snapshot | 1,007,084,608 | 229일 건수·0/양수 건수·합계·최댓값 모두 게시 quality와 일치, NULL/음수 0 |

version의 `published_at IS NULL`은 7,015,400행이었다. V1에서 허용하는 NULL이며
이 수치만으로 결함 처리하지 않는다. 실제 source/target eligibility의 전수 재계산은 미실행이다.
메타데이터의 UTC microsecond 및 PS `[P,S)` 경계는 reference와 일치했다.
VD의 계산 `COMPLETE`와 해석 `PARTIAL`을 그대로 보존했다.

전체 집계 시작/종료: `2026-09-14T01:23:16.396699Z` → `01:25:48.215032Z`.
쿼리별 약 2.861초(package), 15.611초(version), 50.116초(PS), 83.214초(PVS).
이는 검증 실행 시간이며 성능 benchmark 결과가 아니다.

Parquet 표본 날짜는 `2022-05-08`, `2024-07-01`, `2026-08-31`이다.
43건 모두 일치했고 선택된 파일의 합계 크기는 77,848,500 bytes다.
SHA 전후 확인 때문에 실제 I/O 총량을 이 파일 크기와 동일하다고 보지 않는다.

## 발견한 이슈와 처리

- **로컬 generation 원시 해시 불일치**: prepared plan 검사에서
  `scripts/version-dependents-reload.ps1`만 기대 SHA `4ce2bdf0…`와 실제 `f621183f…`가 달랐다.
  실제 3,700 bytes에서 CRLF를 LF로 정규화하면 3,638 bytes 및 기대 SHA와 정확히 일치한다.
  Git에서도 파일 내용 변경은 없다. 로더의 원시 바이트 계약을 임의로 완화하거나 원본 파일을
  수정하지 않았다. 보고서에는 엄격 검사 FAIL 1개와 `only_script_line_endings_differ=true`를 함께 남겼다.
- **게시 execution의 FAILED attempt**: `2022-06-27` PS의 active attempt는
  `FAILED/ABANDONED`, 오류는 `Previous session ended before completion`이었다.
  `package_snapshot/postgres.py`의 start 처리 및 `postgresql/postgres.py:326`의 fail 처리는
  이미 PUBLISHED인 execution을 보존한다. 따라서 연결 존재 검사는 통과시키되 이 시도를
  성공한 재검증으로 표현하지 않고 보고서 evidence에 남겼다. 추가 읽기 조회에서 이전 시도
  `1a3c6292c16e43e59cc704f8f42ceac2`가 `PUBLISHED/COMMIT`, 1,857,868행으로
  `2026-09-09T07:38:38.096728Z`에 완료되었음을 확인했다. 실패 시도보다 앞서며 현재 기대
  counts와 일치한다. 이 별도 근거는 `prior-attempts.json` 및 보고서의
  `failed_active_prior_publication_evidence`에 남겼다. 데이터나 이력은 수정하지 않았다.
- **초기 검증기 오탐**: history pretty JSON의 raw SHA를 게시 SHA와 비교해 발생한
  228일 불일치는 `history_load.verify_publication`의 canonical bytes 계약 적용으로 해소했다.
  수정 뒤 parsed manifest와 DB JSON, 게시/DB receipt SHA 모두 일치했다.
- **임시 DB fixture 적재 순서**: 최초 준비에서 snapshot보다 PS를 먼저 넣어 FK 오류가 발생했다.
  FK 순서에 맞게 fixture를 넣고 UTF-8 stdin으로 SQL을 전달하도록 고친 뒤 7개 시험을 통과했다.
- PS 과거 manifest의 `build_contract_sha256` 누락은 별도 미검증 항목으로 보존했다.
  기존 `contract_sha256`는 validator 지문이므로 생성 지문으로 대체하지 않았다.

## 검증·보존과 증거 위치

- 실제 PostgreSQL fixture 시험: 7개 PASS, 6.600초. [실행 기록](evidence/postgres-fixture-tests.txt).
  네트워크 없음·호스트 port 없음·tmpfs 전용 `integrity09-fixture-20260914-01`을 사용하고 종료했다.
- portable 전체 테스트: **100개 중 92개 PASS, 8개 skip**, 8.644초.
  skip은 별도로 통과한 PostgreSQL opt-in 시험 7개와 Windows symlink 생성 권한이 없는 1개다.
  [전체 테스트 출력](evidence/real-portable-tests.txt)에 보존했다.
- 독립 리뷰에서 완료되지 않은 source run이 SHA만 맞아 통과하는 문제와 비어 있는 DB identity끼리
  일치하는 문제를 발견했다. 두 조건을 필수화하고 부정 테스트를 추가했다. 실패 active attempt의
  이전 성공을 연결만으로 추정하는 표현도 제거하고 위 실제 이력으로 입증했다. 재검토에서 코드
  수정이 확인되었으며 오래된 중간 보고서와 혼동하지 않도록 최종 보고서를 새 이름으로 생성했다.
- 최종 보고서: **252 PASS / 1 FAIL / 0 NOT_RUN**, 전체 상태 `PARTIAL`.
  1 FAIL은 앞서 기록한 CRLF 원시 generation 지문 차이이며 CLI도 의도대로 종료 코드 2를 반환했다.
  [재현 명령과 출력](evidence/real-report-command.txt)을 보존했다. 명시적 deferred 항목은
  검사 목록과 별도이므로 `0 NOT_RUN`을 전체 미실행 범위가 없다는 뜻으로 해석하지 않는다.
- 원래 worktree의 HEAD는 동일한 `91ccc969…`, tracked 변경과 staged 변경은 없었다.
  기존 untracked 파일을 건드리지 않았다. 이 차례 시작 직전 모든 파일의 해시 기준선을 새로
  저장한 것은 아니므로 원래 worktree 전체 파일의 전후 동일성을 새로 입증했다고 주장하지 않는다.
- 이번 코드·문서는 기존 9번 산출물과 함께 미추적 상태다. 커밋·push·Jira 변경은 실행하지 않았다.
- 상세 결과는 작업 worktree의 `data/real-integration-20260914-01/`에 저장했다.
  `metadata/`, `metadata-after/`, `full-scan/`의 SQL/JSON과 최종 표본 `source-samples-v2.json`,
  **`integrity-report-final.json`**이 최종 근거다. 입력 파일 및 검증 코드 SHA는 보고서에 포함한다.
  앞선 `source-samples.json`, `integrity-report.json`은 중간 결과 보존용이며 최종 판정에 쓰지 않는다.
  저장소에 남길 요약은 [real-integration-summary.json](evidence/real-integration-summary.json)을 따른다.

## 수행하지 않은 작업과 완료 경계

이번 결과는 실제 로컬 부분 정합성 검증이다. 원천 Parquet 전부의 키·값·temporal eligibility,
semver 계산, remote `_SUCCESS` 재승인, 대용량 loader 장애/복구 재실행, 대표 성능 benchmark는
수행하지 않았다. 이전 8번 증거를 재사용한 부분과 새로 읽은 DB 집계를 구분한다.
각 조회는 별도 REPEATABLE READ 트랜잭션이므로 단일 MVCC snapshot을 공유하지 않는다.
전후 메타데이터 일치가 동시 payload 쓰기의 완전한 부재를 입증하지는 않는다.

`ready_for_load=false`, `ready_for_publication=false`, `task_09_complete=false`를 유지한다.
백엔드 작업 없이 남은 핵심 범위는 전체 원천과 DB의 독립 전수 대조 및 실제 loader 복구 검증이다.
