# 05. 결과와 검증

**다운로드 원본 검증·Bronze 입고를 완료했고 `a173015`로 커밋했다(P-00~07·AC-01~09).** 첫 전체 Bronze 입고는 `PUBLISHED`/`LOADED`,
두 번째 동일 입력 실행은 `REVERIFIED`로 끝났고 최종 receipt 상태는
`COMMITTED_AND_REVERIFIED`다.

2026-09-09 스냅샷 구간 다운로드 집계·Curated 게시를 S15P21A506-278 범위에 추가했다.
아래 원본 입고 결과와 구간 집계 결과를 분리해 기록한다. 구간 집계의 초도 실행·동일 입력 재검증·인계를 완료했으며, [구간 집계 결과](08-interval-results.md)에 증거를 연결했다.

## 구현 결과

| 범위 | 구현 / 결과 |
| --- | --- |
| 입력 선택·검증 | `pipeline/downloads/input.py`가 본 실행의 정상 파일만 선택하고 smoke·실패·로그·checkpoint를 제외한다. CSV·상태·일별 Parquet의 스키마, 키, 날짜, 값, 상태 관계를 DuckDB로 검사한다 |
| 계보 검사 | `pipeline/downloads/lineage.py`가 gzip JSONL을 스트리밍 검사하고, 이름 정렬 순서의 최대 8개 패키지에 대해 원본과 일별 Parquet의 시계열 키·값·gap을 대조한다 |
| Bronze 입고 | `pipeline/downloads/bronze.py`가 manifest의 파일 목록·바이트·SHA-256을 고정하고, 조건부 생성·원격 GET 검증·`_SUCCESS` 게시를 수행한다 |
| 실행 경계 | `pipeline/downloads/load.py`가 입력 검증, 실행 보고서, manifest 해시, 계약 해시, 재실행과 실패 상태를 분리한다. 다운로드 run prefix는 `npm-downloads/v1/run_id=<run-id>`다 |
| 기존 코드와의 관계 | 기존 deps.dev MinIO 업로더는 수정하지 않고, 접속·해시·불변 업로드 동작만 다운로드 전용 경로에서 재사용했다 |

## 입력 품질 실측

근거는 [source summary](evidence/source-summary.json)와
[lineage summary](evidence/lineage-summary.json)가 참조하는 최종 manifest의 `quality`와
`lineage.summary`다.
선택 768개 파일의 총 입력 크기는 1,597,476,963바이트다.

| 항목 | 실측 결과 |
| --- | --- |
| 선택 / 제외 파일 | 768개 선택, 742개 제외. 선택 구성은 대상 CSV 1개, source metadata 2개, raw response 34개, 일별 Parquet 730개, 상태 Parquet 1개다 |
| 대상 CSV | 100,000행, 고유 이름 99,996개, 중복 이름 4개. 중복 원본 행은 보존했다 |
| 상태 Parquet | 99,996행·고유 이름 99,996개, `READY` 99,215건, `NOT_FOUND` 781건 |
| 일별 Parquet | 730개 파일, 62,616,750행, 2024-09-01~2026-08-31 |
| 값 상태 | `downloads=NULL` 437,786행, `imputed_gap=true` 437,786행, 실제 `downloads=0` 5,322,058행 |
| READY 기간 coverage | expected 62,616,750일, observed 62,616,750일, missing 0일, missing package 0개, NULL 포함 package 77,618개, complete package 21,597개 |
| 일관성 검사 | `(name,date)` 중복 0, 음수 0, 대상·상태 충돌 0, NULL/gap 불일치 0, 물리 date·partition 불일치 0, 730개 물리 schema 동일 |

상태 Parquet의 각 `first_date`~`last_date`는 **패키지별 개별 요청 범위**다. 위 coverage가
모든 패키지에 730일의 유효한 값을 보장한다는 뜻은 아니다. NULL은 0으로 보정하지 않았고,
스냅샷 구간별 집계에서는 `snapshot-time-v1`의 `[P,S)` 시간 경계를 사용하고, 해당 구간의 유효 날짜 수와 누락 사유를 별도로 검사한다.

## 원본 계보 실측

본 실행의 raw 응답은 34개 파일, 145,504개 응답, `ok` 144,346개, `not_found` 1,158개,
고유 패키지 99,996개다. `not_found` 응답 수와 상태 Parquet의 `NOT_FOUND` 781건은 서로 다른
행 단위의 통계이므로 같은 의미로 합치지 않는다.

이름 정렬 순서로 선택한 최대 8개 패키지의 전체 시계열 5,840행을 원본 응답과 일별 Parquet에서
대조했으며 키 누락·추가 없이 값과 `imputed_gap`이 모두 일치했다. 생성 규칙 후보는 과거
커밋 `33b49adef8ea6f6f01bf1f91048ffcf239c7a73d`의
`pipeline/collectors/downloads/to_parquet.py`(blob `d9562f12af10e62eac98e81f604c9635522ba56a`)다.
이 코드가 현재 입력을 실제로 생성한 버전인지는 확인하지 못했으며 manifest에
`generator_execution_version: UNVERIFIED`로 보존했다. AC-05는 미확인 계보를 명시하는 것을
허용하므로 이 상태로 **완료**로 판정한다.

## 테스트 및 전체 입고

최종 코드 기준 테스트 기록은 31건 통과, 실패 0, 오류 0, skip 0이다. 다운로드 입력·계보·
Bronze·load 테스트, 실제 MinIO fixture 2건, 기존 MinIO 회귀 3건을 포함한다. 테스트 실행 시각은
2026-09-09 09:01:47(+09:00)이며, [tests.json](evidence/tests.json)과
[전체 테스트 로그](evidence/tests.log)에 기록했다. 실패 주입 테스트의 의도된 `FAILED` 출력은
테스트 실패 건수와 구분하며 실제 MinIO 시험 prefix는 종료 후 정리했다.

첫 전체 입고는 2026-09-09 09:02:04(+09:00)에 시작해 09:09:01(+09:00)에
`PUBLISHED`/`LOADED`로 끝났다. 실행 정보는 다음과 같다.

| 항목 | 값 |
| --- | --- |
| Bronze run ID | `downloads-278-20260909-v1` |
| Bucket / prefix | `pickage-raw` / `npm-downloads/v1/run_id=downloads-278-20260909-v1/` |
| 파일 / 바이트 | 768개 / 1,597,476,963바이트 |
| 원격 객체 | 771개: 파일 768개와 `_INPUT.json`, `run_manifest.json`, `_SUCCESS` |
| 완료 시각 / 경과 | 2026-09-09 09:09:01(+09:00) / 416.765초 |
| 2차 재검증 | `REVERIFIED`, 2026-09-09 09:15:08(+09:00), 366.719초 |
| 최종 receipt | `COMMITTED_AND_REVERIFIED`, 2026-09-09 09:15:10(+09:00) |
| manifest SHA-256 | `0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d` |
| 코드 계약 SHA-256 | `cb73c31fdacaa05466164d1925fa872f71b2967018edadada9a2d92b28805648` |

입고 전 `pickage-raw`의 기존 raw 객체 3,927개에 대해 키·크기·ETag·수정 시각 metadata
지문을 캡처했다. 첫 입고 후 완료 객체 771개의 1·2차 metadata 지문이 동일했고, 기존
3,927개 객체의 before/after metadata 지문도 동일했다. 768개 선택 파일은 각 시도마다
전체 GET·SHA-256 검사를 수행했다. 기존 3,927개 객체는 metadata 지문을 비교한 것이며,
모든 기존 객체의 바이트를 새로 재읽은 결과는 아니다. 원본 source data는 변경되지 않았다.

최종 실행 receipt는 [bronze-load.json](evidence/bronze-load.json)에 기록했다.
이 receipt의 `COMMITTED`는 Bronze 완료 표시 게시를 뜻한다. Git 커밋이나 PostgreSQL 변경을
뜻하지 않는다. 원본 검증·입고 코드·문서·증거는 이후 `a173015`로 커밋했다.

## 문서 검증 기록

| ID | 범위 | 결과 / 근거 |
| --- | --- | --- |
| V-001 | 착수 시 브랜치·HEAD·입력 경로·기존 코드 조사 | W-001~002에서 확인. 전체 데이터 검증 전의 제한된 조사 |
| V-002 | 전날 착수 문서·색인 검사 | W-003에서 문서 6개와 내부 링크 20개·색인 링크 확인. 당시 데이터 통과를 의미하지 않음 |
| V-003 | 최종 문서·증거·코드 동일성 검사 | [검사 기록](evidence/documentation-check.json) 통과. 로컬 링크·JSON·파이썬 문법·공백·임시 문서 참조 및 테스트/완료 run 코드 해시 대조 |

## 완료 기준별 판정

| 기준 | 현재 판정 | 근거 / 남은 확인 |
| --- | --- | --- |
| AC-01 입력 목록·역할·제외 자료 | 통과 | 768개 선택·742개 제외 목록과 사유를 manifest에 고정 |
| AC-02 대상·상태 건수 | 통과 | CSV·상태 Parquet의 행 수, 고유 이름, 중복과 상태별 건수 실측 |
| AC-03 키·스키마·값·상태 관계 | 통과 | 일별 730개 물리 schema와 키·날짜·음수·상태 관계 검사 |
| AC-04 NULL·0·gap·상태 의미 보존 | 통과 | NULL/gap/실제 0 별도 보존, READY 개별 요청 범위 coverage 기록 |
| AC-05 생성 계보와 표본 대조 | 통과 | 표본 대조 일치. 실제 생성 버전 미확인 상태를 manifest에 보존 |
| AC-06 manifest와 원격 전체 파일 일치 | 통과 | 768개 선택 파일을 각 시도마다 GET·SHA-256 검사하고, manifest·`_SUCCESS`·771개 완료 객체를 확인 |
| AC-07 재실행·동시 실행 보호 | 통과 | fixture와 최종 테스트, 동일 manifest의 2차 `REVERIFIED`, 완료 객체 지문 동일성 확인 |
| AC-08 실패와 기존 성공 보존 | 통과 | 실패·재개·완료 표시 fixture와 실제 기존 3,927개 객체 metadata 지문 보존 확인 |
| AC-09 후속 인계 | 통과 | run ID·prefix·manifest SHA·품질·계보·정확한 manifest URI·재실행 경계를 기록 |

## 후속 인계와 한계

`actual-load.json`의 최종 상태와 원격 객체 검증 결과를 [bronze receipt](evidence/bronze-load.json)에
연결했다. 후속 집계는 다음 URI의 `run_manifest.json`과 `_SUCCESS`를 먼저 확인한 뒤 manifest가
명시한 정확한 파일만 읽는다.
재실행 명령과 실패 복구 경계는 [다운로드 실행 안내](../../../pipeline/downloads/README.md)를 따른다.

```text
s3://pickage-raw/npm-downloads/v1/run_id=downloads-278-20260909-v1/run_manifest.json
s3://pickage-raw/npm-downloads/v1/run_id=downloads-278-20260909-v1/_SUCCESS
```

위 결과는 원본 다운로드의 검증·Bronze 보존을 설명한다. 이어서 완료한 스냅샷 구간 합계·Curated
게시 결과는 [구간 집계 결과](08-interval-results.md)에 정리했다. PostgreSQL 적재·서비스 준비 상태 판단은 별도 후속 작업이다.

생성 계보의 실제 실행 버전은 미확인이다. 표본 대조는 선택된 패키지에 대한 검증이며 전체
원본으로 Parquet를 재생성해 모든 행의 변환 의미를 확인한 결과가 아니다. 생성 코드의 실제
실행 버전은 `UNVERIFIED`다. READY coverage의 expected/observed는 각 상태 행의 개별 요청
범위를 기준으로 하며, 다음 `[P,S)` 구간은 별도 검사가 필요하다. 원격 Jira 제목·상태·댓글은
조회하지 않았다.

## 스냅샷 구간 다운로드 집계·게시 상태 — 초도 실행 완료

- 동일 티켓·브랜치의 범위·계획·이슈 및 [구간 계약](06-interval-contract.md)·[Jira 기재안](07-jira-ticket.md)을 준비했다.
- 입력 고정·집계·Curated 게시 구현과 55개 신규 테스트를 완료했다. 기존 31개 회귀 테스트까지 총 86개가 통과했고 skip/error/failure는 0건이다.
- 초도 S=`2026-08-31`, P=`2026-08-24`, 기대 7일이며 승인 `package/data` 11,080,940행을 `(package_id,snapshot_at)`으로 보존했다.
- 실제 결과는 COMPLETE 97,091행, PARTIAL 637행, UNAVAILABLE 10,983,212행이다. 독립 대조 8개 조건이 모두 통과했고 값·coverage 불일치는 0건이다. 근거는 [interval reconciliation](evidence/interval-reconciliation.json)이다.
- 입력 manifest SHA는 `a0b80537f35e000a471ed95ce4e10c5f25264b587b6c433b0aed9561a777a9d7`, 집계 정책 SHA는 `d037ae76e351c6b8b1613a1e9e724c5b375350967620d7a133fa7a4b47037427`이다. 코드 계약 SHA는 `6174089`로 시작한다.
- `OUTSIDE_TARGET_LIST` 대상은 승인 모집단의 기존 ID 행을 NULL로 유지했고, 승인 모집단 밖 2,251개 이름은 unmatched 결과에 기록했다. daily quality는 6,759행이다. [재검증 receipt](evidence/interval-load.json)와 [최종 인계](08-interval-results.md)를 완료했으며 PostgreSQL 적재는 후속 작업이다.
