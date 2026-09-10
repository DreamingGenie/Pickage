# 06. 스냅샷 구간 다운로드 집계 계약

상태: **초도 집계·Curated 게시·동일 입력 재검증·인계 완료**. 실제 수치와 후속 DB 적재에 사용할 입력은 [구간 집계 결과](08-interval-results.md)에 기록했다.
[기존 범위와 결과](05-results.md) · [S15P21A506-269 Projects 스냅샷 시간 정책](../../../pipeline/snapshot/README.md) · [Jira 기록 초안](07-jira-ticket.md)

## 목적과 경계

S15P21A506-278은 다음 두 작업을 하나의 흐름으로 관리한다.

- **다운로드 원본 검증·Bronze 입고**: npm 다운로드 원본을 검증하고 실행 단위로 MinIO `pickage-raw`에 보관한다. 이 작업은 완료했다.
- **스냅샷 구간 다운로드 집계·Curated 게시**: 기준일 사이의 다운로드 데이터를 집계해 검증된 Curated 결과를 게시한다. 초도 실행과 동일 입력 재검증까지 완료했다.

이 문서는 스냅샷 구간 다운로드 집계·Curated 게시의 입력·식별자·구간·누락·게시 계약과 현재 구현을 설명한다.
구현은 `pipeline/downloads_interval`에 두며, PostgreSQL `package_snapshot` 통합 적재는 이 작업의 출력물을 사용하는 후속 작업이다.

manifest는 한 실행의 파일 목록·크기·해시·검증 결과를 담는 명세이고, `_SUCCESS`는 검증 완료 표시다.
승인 모집단은 해당 스냅샷의 검증 완료 Curated 입력에 포함된 전체 패키지 목록을 뜻한다.
P-09 같은 표기는 아래 실행 순서의 단계 ID이며, 날짜 변수 P(이전 기준일)와 구분한다.

다운로드 원본 검증·Bronze 입고 작업에서 승인한 실행은 `downloads-278-20260909-v1`이며, 집계 입력으로 사용할 때에도 완료 manifest와
`_SUCCESS`를 다시 확인한다. 실행 manifest의 SHA-256은 관측값 `0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d`를
사용하되, P-09에서 원격 객체와 해시를 재검증한 뒤 실행 기록에 확정한다.

## 기준 시간과 초도 실행

선행 이슈 S15P21A506-269의 **Projects 스냅샷 기준일·UTC 시간 정책**인 `snapshot-time-v1`에서 기준 달력·UTC·`[P,S)` 시간 경계를 참조한다.
현재 이슈 S15P21A506-278의 합계 게시에는 부분합 규칙을 적용한다. 완전성 판정과 합계 게시 여부를
구분하며, 구현 시 이 집계 규칙의 버전·해시를 시간 정책과 별도로 기록한다.
S15P21A506-269 문서의 누락 시 NULL 규칙은 S15P21A506-278의 부분합 규칙으로 대체한다. 기존 coverage의 `eligible=false`나
`null_reason`을 곧바로 게시 차단·합계 NULL 조건으로 쓰지 않고, 구간 존재 여부와 유효 값 수로 판단한다.

| 항목 | 계약 |
| --- | --- |
| 기준 달력 | Projects에서 검증한 229개 기준일 전체. 현재 확인 범위는 2022-05-08~2026-08-31 |
| 현재 S | 초도 실행 `2026-08-31`. P-09에서 승인 manifest와 `SnapshotAt=2026-08-31T21:01:10.517131Z` 일치 확인 |
| 이전 P | 전체 달력에서 S 바로 앞의 기준일. 초도 S가 2026-08-31이면 P는 2026-08-24 |
| 집계 구간 | UTC calendar 날짜 `[P,S)`. 따라서 2026-08-24→2026-08-31은 8월 24일부터 30일까지 |
| 간격 | 고정 7일을 가정하지 않고 달력에 실제 기록된 `P`와 `S`의 날짜 차이를 사용 |
| 시간 의미 | `snapshot_at` DATE와 Projects 원천 `SnapshotAt` 시각을 구분. 실행 시각이나 파일 경로 날짜로 대체하지 않음 |
| 첫 기준일 | P가 없으면 합계를 만들지 않고 `NO_PREVIOUS_SNAPSHOT`으로 기록 |

전체 229개 달력에서 P를 결정한 뒤 실행할 S를 선택한다. 2026-08-31만 초도 실행하더라도
P를 임의로 최근 7일로 만들거나 DB의 마지막 성공일로 대체하지 않는다. 2026-08-31의 `SnapshotAt`과
승인 Curated 입력은 현재 `curated-20260907-v2` 실행에서 관측했지만, P-09에서 원격 manifest·`_SUCCESS`·입력 해시를 다시 확인한다.

## 입력과 식별자 계약

| 입력 | 사용 방법 | 고정 조건 |
| --- | --- | --- |
| S15P21A506-269 Projects 스냅샷 기준일 후보 | 전체 기준 달력, P/S, 정책 버전·해시를 읽음 | 관측 SHA `d22099ce22031deb47993f5c66b633d3754fd0625dbb1dcbaafc60070f8afaa7`. 실행 전 원본과 SHA 재검증 |
| S15P21A506-278 다운로드 원본 검증·Bronze 입고 결과 | 완료된 `downloads-278-20260909-v1`의 manifest에 적힌 파일만 읽음 | 진행 중·실패 run과 로컬 디렉터리 전체를 입력으로 사용하지 않음 |
| 승인 Curated package 모집단 | 동일한 `SnapshotAt`에서 승인된 Curated package/data의 전체 모집단과 그 안의 기존 `package_id`를 기준으로 유지 | package/version 적재(S15P21A506-267)가 입력으로 사용한 승인 Curated 실행 `curated-20260907-v2`, S=`2026-08-31` 관측. 해당 SnapshotAt의 원천 근거가 없으면 게시하지 않으며, 원격 manifest와 `_SUCCESS`를 P-09에서 확인 |
| S15P21A506-269 Projects 스냅샷 시간 정책 | `snapshot-time-v1`, 정책 문서와 policy SHA | 원본 정책·해시를 보존하고 시간 경계를 임의로 7일로 축약하지 않음. 합계 게시에는 현재 이슈 S15P21A506-278의 부분합 규칙 적용 |

공식 package ID 대장 전체를 현재 S의 모집단으로 간주하지 않는다. 해당 S에서 승인된 Curated
모집단과 누적 ID 대장은 서로 다른 집합일 수 있다. 과거 S의 모집단이 별도로 확보되지 않은 경우
최신 S의 모집단을 과거 날짜에 소급하지 않는다. 해당 S의 전체 결과를 게시하지 않고 스냅샷 단위의
제외 사유를 기록하며, P-09에서 실제 범위를 확정한다. 게시 대상으로 확정한 S에서는 승인 모집단의
행을 모두 유지한다.

다운로드 Bronze의 `name`은 입력 관측값이고, Curated의 식별자는 승인된 `package_id`다.
집계 전 이름→ID 매핑은 승인된 package 행으로만 해석한다. 승인 모집단 밖의 다운로드 이름은
정상 결과에 새 ID로 추가하지 않고 별도 품질 보고에 남긴다. 하나의 `(package_id, snapshot_at)`에
여러 행이 생기거나 이름·ID 관계가 모순되면 게시를 차단한다.

## 출력 행과 합계 규칙

Curated 출력의 목표 grain은 **하나의 `(package_id, snapshot_at)` 행**이다. 집계 값은 해당 S의
패키지가 P 이상 S 미만의 각 UTC 날짜에서 관측한 다운로드 수를 합산한 값이다.

출력 필드는 다음 의미를 따른다. Parquet 컬럼명과 Curated MinIO prefix·manifest 구조는
현재 구현에서 확정했다. 실제 초도 실행 결과와 파일별 해시는 [결과](08-interval-results.md)에 기록했다.

| 필드 | 의미 |
| --- | --- |
| `package_id` | 승인 Curated 모집단의 기존 ID |
| `snapshot_at` | 합계의 현재 기준일 S |
| `previous_snapshot_at` | 달력에서 S 바로 앞의 P |
| `download_sum` | `[P,S)`의 유효한 일별 `downloads` 합계. BIGINT 범위를 검사 |
| `expected_days` | 달력 구간의 기대 날짜 수 |
| `observed_days` | 행이 존재하는 고유 날짜 수. NULL·gap 날짜도 포함 |
| `valid_days` | `downloads`가 NULL이 아니고 `imputed_gap=false`인 고유 날짜 수 |
| `daily_quality.parquet` | 대상 이름별 날짜별 `ROW_MISSING`, `NULL_VALUE`, `IMPUTED_GAP`, `OUTSIDE_AVAILABLE_RANGE` 상세 |
| `data_status` | `COMPLETE`(전체 합계), `PARTIAL`(부분합), `UNAVAILABLE`(계산 가능한 값 없음) 구분 |
| `quality_reasons` / `null_reason` | 부분합의 누락 사유도 품질 정보로 보존. `null_reason`은 합계가 NULL인 경우에만 기록 |
| `input_manifest_sha256`, `policy_sha256`, `aggregation_policy_sha256` | 사용한 불변 입력·시간 정책·부분합 집계 정책 연결 |

`download_sum`은 구간 안에 유효한 날짜가 하나 이상 있으면 그 값들의
합계를 게시한다. 행이 없거나 `downloads=NULL` 또는 `imputed_gap=true`인 날짜는 합산에서 제외한다.
`0 < valid_days < expected_days`이면 부분합(`PARTIAL`), `valid_days == expected_days`이면
전체 합계(`COMPLETE`)로 구분한다. 유효한 날짜가 전혀 없으면 합산할 관측값이 없으므로
`download_sum=NULL`, `UNAVAILABLE`과 사유를 기록한다. 누락 값을 0으로 채우거나 전체 기간으로 환산하지 않는다.
`observed_days`는 존재한 날짜 수이고 `valid_days`는 합산 가능한 날짜 수이므로 두 값을 같은 의미로 쓰지 않는다.
관측된 `downloads=0`은 유효한 실제 0이므로 NULL로 바꾸지 않는다. 대상 목록 밖 이름이나
NOT_FOUND 패키지도 0으로 채우지 않는다.

예를 들어 7일 구간에서 5일의 유효 값 합계가 100이면 `download_sum=100`, `data_status=PARTIAL`,
`expected_days=7`, `valid_days=5`로 게시하고 나머지 2일의 날짜와 누락·NULL·gap 사유를 함께 남긴다.

| 상황 | 결과 |
| --- | --- |
| P가 없음 | `download_sum=NULL`, `UNAVAILABLE`, `NO_PREVIOUS_SNAPSHOT` |
| 입력 보유 날짜 범위가 구간의 일부만 포함하고 구간 안 유효 값이 있음 | 유효 값의 부분합, `PARTIAL`, 품질 사유 `OUTSIDE_AVAILABLE_RANGE` |
| 구간과 입력 보유 날짜 범위가 겹치지 않음 | `download_sum=NULL`, `UNAVAILABLE`, `OUTSIDE_AVAILABLE_RANGE` |
| 구간에 날짜 행 누락·NULL·gap이 있으나 유효 값도 있음 | 유효 값의 부분합, `PARTIAL`, 품질 사유 `MISSING_DAILY_VALUES` |
| 구간과 입력 보유 날짜 범위는 겹치지만 유효 값이 전혀 없음 | `download_sum=NULL`, `UNAVAILABLE`, `MISSING_DAILY_VALUES`. 대상 외·NOT_FOUND 등 해당 사유도 보존 |
| 다운로드 대상 목록 밖이지만 승인 모집단 안에 있음 | 해당 승인 `package_id`의 NULL 행과 `UNAVAILABLE`을 유지하고 품질 사유를 기록 |
| 해당 입력이 승인 대상 모집단에 없음 | 정상 결과에 새 ID를 만들지 않고 별도 품질 보고 |
| 상태가 NOT_FOUND이고 유효한 구간 값이 없음 | `download_sum=NULL`, `UNAVAILABLE`, 입력 상태와 함께 품질 보고 |
| 대상/상태/ID 관계가 모순되거나 중복 grain 발생 | 게시 실패. 원인과 입력을 기록 |
| 전체 기대 날짜가 유효하고 모두 실제 0 | 합계 0, `COMPLETE` |
| 일부 날짜만 유효하고 그 값이 모두 실제 0 | 부분합 0, `PARTIAL`. 누락 날짜와 품질 사유를 유지 |

`expected_days`, `observed_days`, `valid_days`를 모든 행에 남겨 부분합·완료 합계를 구분한다.
합산 중 BIGINT overflow, 중복 `(package_id, date)` 또는 이름→ID 다중 매핑이 발생하면 자동 보정하지 않고 실패한다.
부분합은 검증된 입력 안의 날짜·값 누락에 적용한다. manifest에 명시된 파일의 부재·읽기 실패·해시 불일치는
입력 검증 실패로 처리하며 해당 파일을 제외하고 게시하지 않는다.

다운로드 대상 목록 밖이지만 승인 모집단에 포함된 패키지를 구분하기 위한
`OUTSIDE_TARGET_LIST`는 현재 집계 구현의 품질 사유이며, 대상 목록 밖이지만 승인 모집단에 포함된 패키지의 NULL 결과를 설명한다.
`quality_reasons`는 조건별 사유 배열로 저장하며, 대표 `null_reason`과 별도로 여러 조건을 보존한다.
대상 이름의 날짜별 사유는 `daily_quality.parquet`에 기록한다. 승인 모집단 밖 이름은 정상 출력 모집단에
새 `package_id`를 만들지 않고 `unmatched_packages.parquet`에 남긴다.

## 불변 게시 계약

P-09에서 입력을 고정한 뒤 P-10의 집계 결과는 새 실행 디렉터리에서 생성한다. 결과 manifest에는
candidate SHA, Bronze manifest SHA, 승인 Curated manifest SHA, `snapshot-time-v1` 정책 버전·해시,
S15P21A506-278 부분합 집계 정책 버전·해시, S/P, expected/observed/valid 일수와 품질 집계, 코드 계약 해시를 기록한다. 기존 Bronze와 승인 Curated 객체를
덮어쓰지 않으며, 게시 전후 파일 크기·SHA를 검증한다.

Curated 결과 prefix는 `pickage-curated/npm-downloads-interval/v1/snapshot=<S>/run_id=<run-id>/`로 고정한다.
정상 게시에는 `data/interval_downloads.parquet`, `data/daily_quality.parquet`, `data/unmatched_packages.parquet`,
`run_manifest.json`, `_INPUT.json`, `_SUCCESS`가 포함된다. 주 출력은 `(package_id, snapshot_at)` grain이며
`interval_downloads.parquet`의 주요 필드는 `package_id`, `snapshot_at`, `previous_snapshot_at`,
`download_sum`, `expected_days`, `observed_days`, `valid_days`, `data_status`, `null_reason`,
`quality_reasons`, `input_manifest_sha256`, `policy_sha256`, `aggregation_policy_sha256`다.
완료 표시가 없는 결과나 manifest SHA가 일치하지 않는 결과는 후속 DB 입력으로 넘기지 않는다.
집계 실행은 현재 PostgreSQL을 변경하지 않는다. DB 실행 이력 연결이 필요하면 별도 후속 계약으로
manifest와 실행 ID를 연결하며, 로컬 JSON에만 결과를 남기는 상태로 완료 처리하지 않는다.

## 다음 실행 순서

| 단계 | 작업 | 산출물 / 중지 조건 | 상태 |
| --- | --- | --- | --- |
| P-08 | 작업 범위와 집계·게시 계약 문서화 | 본 문서·Jira 본문 초안 | 완료 |
| P-09 | Bronze·Projects 기준일·승인 Curated 입력 재검증 | 입력 manifest, 선택 파일 목록, SHA 고정 | 완료 |
| P-10 | `[P,S)` 집계와 품질 판정 구현 | `pipeline/downloads_interval/aggregate.py`, 부분합·NULL·실제 0·품질 배열 | 구현 완료, 보강 검증 중 |
| P-11 | Curated 출력 검증과 MinIO 게시 구현 | 고정 prefix/schema, 전체 GET·SHA 검증, 재실행 보호 | 구현 완료, 실제 게시 전 |
| P-12 | 격리된 소형 입력으로 단위·집계·게시·회귀 테스트 | 실패·중복·부분합·유효 값 없음·실제 0·범위 일부 겹침·overflow·불변 재실행 | 완료 (86개 전체 통과) |
| P-13 | S=2026-08-31 초도 실제 실행·게시·동일 입력 재검증 | 전체 모집단·행 수·품질·manifest·원격 객체 및 재실행 보존 | 완료 |
| P-14 | 인계 문서 작성 | 실행 ID·manifest·policy SHA·NULL 사유·제한사항 전달 | 완료 — [인계](08-interval-results.md) |

스냅샷 구간 다운로드 집계·Curated 게시의 새 구현은 기존 `pipeline/downloads` Bronze 계약 해시를 불필요하게 바꾸지 않도록
`pipeline/downloads_interval`에 둔다. 다운로드 원본 검증·Bronze 입고 작업의 현재 31개 테스트는 구간 집계 테스트가 아니며,
스냅샷 구간 다운로드 집계·Curated 게시 구현 후 새 테스트 수와 실제 실행 결과를 별도로 기록한다. 다운로드 원본 검증·Bronze 입고 작업에서 확인하지 못한 원본 Parquet 생성 버전은
`UNVERIFIED`로 계속 보존하고, 이를 이유로 임의 재수집·원본 수정·전체 재생성을 수행하지 않는다.

PostgreSQL `package_snapshot` 통합 적재는 이 티켓의 집계·게시 결과를 사용하는 후속 작업이다. 해당 작업에서는 Curated 결과의
`(package_id, snapshot_at)` 데이터를 DB 테이블에 적재하고 실행 이력과 결과 manifest를 연결한다. 이 문서의 현재 범위에는
스키마 변경이나 DB 적재 실행이 포함되지 않는다.

## 완료 기준

| ID | 완료 조건 |
| --- | --- |
| AC-10 | 다운로드 원본 검증·Bronze 입고 결과, S15P21A506-269 기준일 후보, 승인 Curated 입력의 파일 목록·바이트·SHA·완료 상태를 재검증하고 run ID로 연결한다 |
| AC-11 | 전체 달력에서 P를 결정하고 선택한 S의 `[P,S)` 날짜 범위를 정확히 계산한다 |
| AC-12 | 해당 S에서 승인된 전체 package 모집단의 `(package_id, snapshot_at)` grain을 보존한다 |
| AC-13 | 누락·NULL·gap을 제외한 유효 값의 부분합과 품질 사유를 게시한다. 전체 합계·부분합·유효 값 없음을 구분하고 실제 0을 유지한다 |
| AC-14 | 이름→기존 package ID 정합성·중복·모순을 검사하고 승인 밖 이름은 별도 보고한다 |
| AC-15 | 합계 범위·expected/observed days·BIGINT overflow·중복 키를 검증한다 |
| AC-16 | 입력·정책·코드 해시와 manifest를 포함한 Curated 결과를 불변 방식으로 게시한다 |
| AC-17 | 작은 격리 입력에서 단위·회귀·실패·재실행·게시 검증을 통과한다 |
| AC-18 | 초도 S 실행의 실제 output·품질·원격 객체를 전체 검증하고 완료 표시를 게시한 뒤, 동일 입력 재실행으로 기존 결과 보존을 확인한다 |
| AC-19 | 후속 DB/분석 소비자가 사용할 실행 ID·manifest·정책·제한사항·재실행 방법을 인계한다 |

AC-10~19는 [실제 실행·재검증·인계](08-interval-results.md)로 충족했다. 다운로드 원본 검증·Bronze 입고의
AC-01~09와 구간 집계 검증 증거를 구분해 보관한다. PostgreSQL 적재 실행은 이 완료 기준에 포함하지 않는다.
