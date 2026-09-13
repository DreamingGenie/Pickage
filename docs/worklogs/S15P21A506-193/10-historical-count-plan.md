# 10. 모든 기준 스냅샷의 버전별 dependents_count 계산 계획

현재 상태(2026-09-13): 승인된 선정 대상의 H1~H7 로컬 계산·적재와 서비스 전환을 완료했다.
[현재 단계와 후속 범위](02-plan.md) · [전체 집계](30-full-selected-run.md) · [전체 적재](42-timed-full-reload.md) · [서비스 전환](44-service-table-cutover.md).
아래는 2026-09-10~11 설계 당시의 제안과 판단을 보존한 기록이며, 미착수/미확인 표시는 당시 상태다.

2026-09-11 적용 변경: [D-22](06-decisions.md)에 따라 저장 target은 다운로드 선정 패키지로
제한하고 count의 source는 전체 패키지/버전을 유지한다. 0 포함 229개 날짜의 selected
target 키는 1,007,084,608개다. 아래 초안의 전체 패키지 69.7억 행 저장 제안 및 미결정
설명보다 D-22를 우선한다. 당시 H5-A 이후 계획은 [02 작업 계획의 이력](02-plan.md)에 보존한다.

작성일: 2026-09-10. 작성 당시 상태: **구현 전 제안 계획**. 당시 요청은 계획 작성·보고였으며 계산 코드 변경, 전체 backfill, DB 접속·적재, Jira, commit·push는 수행하지 않았다.

## 1. 목표와 현재 상태

목표는 기준 스냅샷마다 `(package_id, version, snapshot_at)`의 직접 dependents 수를 계산하여 기존 `package_version_snapshot.dependents_count`에 반영하는 것이다. source 패키지의 여러 버전은 각각 세며, 동일 source 버전이 같은 target 버전을 여러 번 가리키면 한 번만 센다. [E1, E2]

현재 확인한 기준일 목록은 **229개, 2022-05-08~2026-08-31**이다. 최신 requirements·versions 관측 시각은 `2026-08-31T21:01:10.517131Z` 하나다. 7번과 이번 8번은 이 마지막 날짜에 대해서만 실행했다. 다른 날짜의 관계 파일·count가 이미 존재한다고 전제하지 않는다. DB에 229개 날짜와 필요한 package/version이 실제 들어 있는지는 이번에 접속하지 않아 미확인이다. [E3, E4, E5]

기존 코드는 원본 관측 시각과 계산 시각을 하나로 사용한다. 따라서 `--snapshot`을 과거 날짜로 바꿔 반복 실행하는 것만으로 이 목표를 달성할 수 없다. 별도 과거 재구성 입력 계약과 실행 경로를 추가한다. 기존 7번 산출물과 단일 관측일 계산 계약은 보존한다. [E6]

## 2. 계산값의 의미와 정책

### 2.1 권고하는 시간 기준

**최신에 관측한 원본을 고정하고, 각 과거 시각에 이미 배포된 버전만 사용해 다시 계산하는 방식**을 제안한다.

| 필드 | 정의 |
| --- | --- |
| `observed_snapshot_timestamp` | 원본을 실제 관측한 시각. 이번 입력은 2026-08-31T21:01:10.517131Z |
| `snapshot_at`, `snapshot_timestamp` | count를 계산할 기준 날짜·정확한 UTC 시각. 고정한 calendar의 각 원소 |
| `calculation_mode` | 제안: `HISTORICAL_RECONSTRUCTION_FROM_FIXED_INPUT` |
| `metric_definition` | 제안: `DISTINCT_SOURCE_VERSIONS_ON_RESOLVED_DIRECT_REQUIREMENTS` |

원본 Parquet의 `SnapshotAt`은 관측 시각과 일치하는지 검증한다. 배포일 필터와 결과 키에는 계산 시각을 사용한다. 두 시각을 섞거나 원본 날짜를 변경하지 않는다. `T > observed_snapshot_timestamp`인 미래 계산은 거부한다. Projects의 저장소 지표에 적용되는 동일 관측 시각 규칙은 변경하지 않는다. [E6, E7]

이 값은 현재 보유한 자료로 재구성한 값이다. 과거 당시의 전체 패키지·버전·선언 목록이 완전하게 복원된다는 주장을 하지 않는다. 실제 당시 관측 자료가 필요하다면 별도 역사 입력이 필요한 다른 계산 모드로 취급한다.

### 2.2 집계 정의

계산 시각을 `T`, source 버전을 `s`, target 버전을 `v`라고 할 때:

```text
dependents_count(v, T)
  = COUNT DISTINCT (source_package_id, source_version)
    WHERE source가 T의 대상이고,
          일반 dependencies 중 하나 이상이 T에서 v로 해석됨
```

- source: 고정 원본과 Curated에 있는 모든 대상 release 버전 중 `published_at IS NOT NULL AND published_at <= T`. 대표 최신 버전으로 축소하지 않는다.
- target: 같은 고정 입력의 release 버전 중 위 배포일 조건과 기존 valid stable semver 조건을 통과한 버전. source에 target의 prerelease 제외 규칙을 추가로 적용하지 않는다.
- 해석: target의 npm 이름과 요구조건에 대해 T까지 나온 후보 중 semver 최대 만족 버전 하나. `ordinal`이나 배포일이 가장 늦다는 이유만으로 선택하지 않는다.
- 동률: semver 우선순위가 같으면 기존 원문 버전의 UTF-16 오름차순 규칙을 유지한다.
- 일반 dependencies만 포함한다. peer·optional은 계산에서 제외하고 원본 계보·제외 수를 기록한다.
- 직접 관계만 계산한다. self-edge는 기존 동작대로 한 관계로 센다. transitive/all-depth는 제외한다.
- 미해석은 사유별 PARTIAL로 보존한다. alias·prerelease·프로토콜 분류의 기존 한계를 이번 계획에서 조용히 고치지 않는다. 이 정책을 바꾸는 작업은 별도 정책 버전과 재계산 대상으로 분리한다. [E1, E8, E9]

### 2.3 0과 PARTIAL의 서비스 저장 기준 — 제안, 아직 미승인

현재 사용자 승인은 성공한 관계의 **진단 집계**까지이며 DB에 PARTIAL 값을 게시하는 승인으로 해석하지 않는다. 기존 규칙은 PARTIAL 정상 게시와 정상 0 채우기를 막는다. [E10]

본 계획의 권고안은 서비스 count의 의미를 **위 정책에서 성공적으로 해석한 직접 관계 수**로 명시하는 것이다. 이 정의 아래에서는:

- 대상 버전에 연결된 성공 관계가 없으면 해당 metric의 값은 0이다. 실제 의존자가 전혀 없다는 판정이 아니다.
- 계산이 끝났다는 상태와 원본 해석 품질을 분리한다. `calculation_status=COMPLETE`, `resolution_status=PARTIAL`이 동시에 가능하다.
- 서비스에 게시하려면 이 의미와 과거 재구성 모드를 명시적으로 채택하고, snapshot별 실행 이력에 정책·미해석 수·입력 계보를 함께 기록한다. 서비스 조회/지표 설명에서도 이 한계를 확인할 수 있어야 한다.
- 게시 조건은 결정 문서에 채택 근거를 기록하고, 서비스 소비자가 `calculation_mode`, `metric_definition`, `resolution_status`, 미해석 선언 수, 관측 시각을 확인할 수 있는 계약을 갖추는 것이다. 저장된 이력에만 한계를 숨긴 채 기존의 완전한 count처럼 제공하지 않는다. 이 계약이 없으면 H6의 합성 데이터 적재 테스트까지만 가능하며 실제 PARTIAL 산출물은 `ready_for_load=false`, H7은 미착수로 둔다.
- 이 변경을 채택하지 않으면 현재 PARTIAL 결과의 DB 게시 게이트를 유지한다. count와 품질 파일까지 계산하되 `ready_for_load=false`로 남긴다. COMPLETE를 위조하거나 기존 DDL의 기본값 0에 맡기지 않는다.

이 결정과 target 제외 정책 밖의 버전 처리 기준을 확정하기 전에는 전체 DB 적재를 실행하지 않는다. 범위 밖 버전은 별도 제외 이유를 기록하며 정상 계산 0을 부여하지 않는다. 계획 작성 자체는 이 새 정책의 승인이나 DB 쓰기 실행이 아니다.

## 3. 입력과 실행 식별자 고정

1. `snapshot-candidate.json`의 SHA, calendar 229개와 각 정확한 timestamp를 고정한다. 주간 간격을 가정하거나 없는 날짜를 생성하지 않는다. 정렬·중복 날짜·중복 시각·미래 기준일을 검사한다. [E3]
2. 최신 requirements·versions_full·Curated package/version의 원본 manifest, 명시 파일 목록, SHA/크기/스키마/행 수를 고정한다. 파일을 매 날짜 다시 검증하지 않고 backfill 입력 검증 한 번과 종료·재시작 시 불변 확인을 수행한다. [E6]
3. source ID/버전, 정확한 npm 이름, 배포일, release 여부, 원본 선언과 오류 플래그를 연결한다. 이름·버전·ID의 충돌과 NULL 처리 규칙은 기존 입력 검사를 이어받는다. [E6, E8]
4. 계산 결과·캐시 식별자는 `(관측 입력 SHA, calendar SHA, 후보 모집단 SHA, resolver/runtime SHA, 계산 정책 SHA)`를 포함한다. 기존 `lookup_id`만으로 날짜 간 target을 재사용하지 않는다. [E8, E9]
5. 7번 recovery candidate와 기존 edge는 최신 날짜 대조 기준으로만 읽는다. recovery candidate를 새 원본 입력의 정상 승인 manifest로 승격하지 않는다. [E4]
6. 배포 시각은 원본 컬럼 타입·값·원천 시간대 계약을 보존한 뒤 UTC epoch microsecond로 정규화한다. timezone-aware 값은 UTC로 변환하고, timezone 없는 BigQuery 유래 값은 원천 계약이 확인된 전용 UTC adapter에서만 허용한다. OS의 로컬 시간대나 날짜 문자열로 해석하지 않는다. 출처를 알 수 없는 naive 시각, 잘못된 timezone, microsecond보다 정밀한 값을 조용히 반올림하지 않고 입력 오류로 거부한다. 기존 `parse_timestamp(..., allow_naive_utc=...)`의 명시적 허용 경계를 재사용한다. [E7]

## 4. 계산 구조: 대상 버전이 바뀌는 구간을 한 번 계산

229번의 원본 전개·전체 edge 저장을 반복하지 않는다. 기존 DuckDB·Python·설치된 Node/npm semver를 사용하고 새 의존성이나 Spark 서비스는 추가하지 않는 방향을 우선한다. 이는 새 경로의 성능이 확인된 결론이 아니라 구현 제안이다. [E8, E9, E11]

### A. source와 고유 요구조건을 한 번 준비

- 고정 원본에서 `source_package_id, source_version, source_published_at, lookup_id, declared_name, requirement, declaration_index, kind`를 스트리밍으로 준비한다.
- 원본 선언 grain은 보존한다. 해석 호출은 기존처럼 고유 `(declared_name, requirement)`별로 묶는다. source별 여러 버전을 합쳐 버리지 않는다.
- 각 source·target 버전의 `birth_index`를 calendar에서 `T >= published_at`인 첫 위치로 계산한다. 날짜가 같은지만 비교하지 않고 microsecond 경계를 사용한다. 첫 기준일보다 이전 버전은 index 0, 마지막 기준일보다 이후는 계산 제외다.
- target 패키지 기준으로 분할한다. 같은 target 패키지의 모든 source 선언을 같은 처리 단위로 보내 동일 source→target 중복을 전역적으로 합칠 수 있게 한다. lookup/source 기준 임의 분할 후 단순 합산하지 않는다.

### B. 고유 요구조건별 target 변경 구간 생성

각 target 패키지의 유효 후보를 배포 시각 순으로 추가하면서, 각 고유 요구조건의 semver 최대 만족 후보가 **달라지는 시점**만 기록한다.

```text
lookup Q = package-B, ^1.0.0
[snapshot index 0, 30)   -> NO_ELIGIBLE_TARGET 또는 NO_SATISFYING_VERSION
[snapshot index 30, 70)  -> B@1.2.0
[snapshot index 70, 229) -> B@1.3.0
```

- 위 숫자는 설명용 예시다. 실제 구간은 입력 배포일과 229개 시각에서 산출한다.
- 후보가 나중에 배포됐어도 semver가 더 낮으면 이미 선택된 더 높은 버전을 대체하지 않는다.
- 같은 birth index의 후보는 함께 처리한다. semver 동률에서는 기존 원문 tie 규칙까지 비교한다. 예를 들어 `1.0.0+z`가 먼저 선택됐어도 다음 기준일에 `1.0.0+aa`가 추가되면 원문 UTF-16 정렬에서 앞서는 후자가 winner가 된다. precedence가 더 높은 경우만 변경 이벤트로 기록하는 구현은 허용하지 않는다.
- 선두 미해석 구간도 기록한다. 후보와 상태의 모집단은 아래 표를 따른다. 패키지의 과거 생성일은 현재 자료에서 추정하지 않는다.
- unsupported/invalid 요구조건의 사유는 유지한다. 요구조건 문자열만 같다는 이유로 패키지·관측 입력·정책이 다른 구간을 재사용하지 않는다.
- 구현은 npm semver와 기존 parser의 판정에 대조한다. 별도 정규식으로 `^`, `~`, 비교식, OR, x-range 등을 재구현하지 않는다. 새 과거 resolver는 기존 worker 결과와 동등성 테스트를 갖춘다. [E9]

판정 우선순위는 기존 worker의 이름 검사 → 문자열/파싱 검사 → 지원 타입 검사 → semver range 검사 → 후보 선택 순서다. 파싱 실패한 프로토콜이 현재 `INVALID_SPEC`인 동작도 유지한다. 앞 단계에서 결정된 invalid/unsupported 상태를 후보 부족 상태로 덮어쓰지 않는다.

| 앞 단계 검사를 통과한 요구조건의 상태 | 정확한 판정 기준 |
| --- | --- |
| `RESOLVED` | T까지 배포된 valid stable 후보 중 조건을 만족하는 최대 버전이 있음. target ID 연결도 반드시 성공 |
| `NO_SATISFYING_VERSION` | 같은 패키지의 유효 후보가 하나 이상 있지만 조건을 만족하는 후보가 없음 |
| `NO_ELIGIBLE_TARGET` | 유효 후보가 없고, 이름은 고정 Curated package 목록에 있음 |
| `UNMAPPED_TARGET_PACKAGE` | 기존 `NO_ELIGIBLE_TARGET` 결과에서 이름이 고정 Curated package 목록에도 없음 |

`known_package`는 고정 입력의 매핑 유무이며 날짜별 패키지 존재 증거가 아니다. 유효 후보 집합은 배포 시각·release·NULL·valid semver·stable 조건으로 별도 계산한다. prerelease만 있는 경우, invalid version만 있는 경우, 후보가 모두 미래인 경우는 유효 후보가 0이면 기존 `NO_ELIGIBLE_TARGET`을 유지하고 원인을 별도 제외 수로 기록한다. 후보 원본 수·유효 수·prerelease/invalid/NULL/미래 제외 수는 기준과 우선순위를 고정한 상호 배타적 분류로 기록한다. 따라서 첫 유효 후보 출현으로 `NO_ELIGIBLE_TARGET → NO_SATISFYING_VERSION`, 이후 만족 후보 출현으로 `→ RESOLVED`가 되는 변화도 보존한다. [E8, E9]

후보 품질 분류는 ID 연결·원본 키 검증 후 버전당 `non-release → NULL 배포일 → T 이후 배포 → invalid semver → prerelease → eligible` 순서에서 처음 해당하는 항목 하나를 부여한다. ID 충돌·잘못된 timestamp는 제외 수에 흡수하지 않고 입력 실패다. 날짜별 분류 수 합계는 고정 입력 버전 수와 일치해야 한다. 이는 원인 추적용 분류이며 기존 worker가 공개하는 declaration 상태를 바꾸지 않는다.

### C. source가 실제로 기여하는 구간을 만들고 중복 제거

- 각 source의 `birth_index`와 lookup의 RESOLVED 구간을 교집합하여 `(source ID, source version, target ID, target version, start_index, end_index)`를 만든다. 모든 구간은 `[start, end)`다.
- 같은 source 버전의 다른 선언이 같은 target을 가리키면 구간들의 합집합을 취한다. 겹치는 구간의 길이나 선언 개수만큼 더하지 않는다.
- 구간 합치기는 nested overlap도 처리해야 한다. 단순 이전 행의 끝만 비교하지 않고 이전 구간들의 누적 최대 끝을 사용한다.
- target 패키지 파티션 내부에서 처리하고, 이 구간들은 계산 중 scratch에만 둔다. 날짜마다 source-target Parquet를 영구 저장하지 않는다.

### D. 변경량을 누적해서 날짜별 count 계산

중복 제거된 source→target 구간 하나가 `[a, b)`에 기여하면 target에 다음 두 이벤트를 만든다.

```text
(target ID, target version, index=a, delta=+1)
(target ID, target version, index=b, delta=-1)
```

같은 target·index의 delta를 합치고 calendar 순서대로 누적하면 각 날짜의 직접 source 버전 수가 된다. b=229는 마지막 기준일 뒤의 종료 이벤트이므로 그 날짜의 출력 행을 만들지 않는다. 음수 누적과 INT 초과는 실패시킨다. 내부 count/delta는 BIGINT로 계산한 후 저장 전에 INT 범위를 확인한다.

target과 관계없는 source에 변화가 생겨도 count를 다시 계산하지 않는다. target 버전의 교체는 이전 버전에서 -1, 새 버전에서 +1로 반영하므로 개별 버전 count가 감소할 수 있다.

예를 들어 A@1.0이 B@^1.0.0을 선언했고, 첫 기준일에는 B@1.2.0만 있으며 다음 기준일 전에 B@1.3.0과 A@2.0이 배포됐다고 하자. A@2.0도 같은 조건을 선언하면:

| 기준일 | B@1.2.0의 성공 관계 count | B@1.3.0의 성공 관계 count |
| --- | ---: | ---: |
| 첫 기준일 | 1: A@1.0 | 대상 아님: 아직 미배포 |
| 다음 기준일 | 0 | 2: A@1.0, A@2.0 |

최신 source 하나만 세는 방식도, 최신 관계를 과거로 복사하는 방식도 이 결과를 만들지 못한다. 이 표는 설명용 합성 예시이며 실제 패키지 데이터가 아니다.

### E. 선언 품질과 source 품질을 별도로 누적

선언 품질은 source birth index와 **모든** lookup 상태 구간을 교차해 계산한다. 원본 선언의 `(source ID, source version, kind, declaration_index)`를 유지하고, 상태 구간 시작에 +1·끝에 -1을 준다. count용 source→target 중복 제거 결과로 선언 수를 계산하지 않는다. unsupported/invalid도 source가 활성화된 시점부터 해당 상태에 기여한다.

source마다 활성 기간의 선언 수와 resolved 선언 수를 누적한 후, 다음 기존 우선순위로 source 상태를 정한다. 앞 조건이 참이면 뒤 조건으로 덮어쓰지 않는다. [E8]

```text
requirements 없음 → MISSING_REQUIREMENTS
선택 dependency 목록 NULL → NULL_DEPENDENCY_LIST
extraction error=true → DEPENDENCY_EXTRACTION_ERROR
extraction error=NULL → DEPENDENCY_EXTRACTION_UNKNOWN
선언 수=0 → OBSERVED_NO_DEPENDENCIES
resolved 선언 수=전체 선언 수 → RESOLVED
resolved 선언 수>0 → PARTIAL
그 외 → UNRESOLVED
```

source birth와 연결된 lookup 상태 변경 시점에서만 source 상태를 다시 결정하고, 그 상태 구간의 delta를 누적한다. 오류 source에 성공 선언이 함께 있는 경우 **성공 관계는 기존처럼 count에 포함**하되 source 품질은 오류로 남긴다. missing/NULL/error를 무의존 source로 바꾸지 않는다. NULL 배포일 등으로 source 대상에서 제외된 행은 활성 source 수에 넣지 않고 별도 제외 항목으로 남긴다.

각 T에서 아래 보존식을 검증한다. 전체 해석 품질은 미해석 선언이 0이고 missing/NULL/extraction error/unknown source가 0일 때만 COMPLETE다. 알고리즘 실행 성공과 이 품질 상태는 별개다.

```text
선언 상태별 수의 합 = 선택 선언 수 = resolved 선언 수 + unresolved 선언 수
source 상태별 수의 합 = T의 대상 source 버전 수
source별 resolved 선언 수의 합 = resolved 선언 수
target count 합 = distinct resolved source-target 수 <= resolved 선언 수
```

마지막 부등식의 차이는 동일 source→target으로 합쳐진 중복 선언 수로 기록한다. source별 전체 선언 수와 실제 전개된 선언 수가 다르면 계산 실패로 처리한다.

## 5. 저장할 결과와 0 처리

### 영구 저장

| 산출물 | 데이터 단위와 내용 |
| --- | --- |
| 입력·정책·calendar manifest | 관측 원본/코드/runtime/후보/정책 SHA 및 229개 기준일 |
| `target_population.parquet` | 유효 target 버전당 한 행. ID, 원문 version, published_at, birth_index. zero 대상 정의의 근거 |
| snapshot별 `counts.parquet` | 성공 관계 count가 양수인 `(package_id, version, snapshot_at, snapshot_timestamp, dependents_count)` |
| snapshot별 `quality.parquet` | source/선언/성공/미해석/제외/유효 target/0대상 수, 계산·해석·게시 상태 |
| snapshot별 `lineage.parquet` 및 manifest | 관측 시각과 계산 시각, 입력·정책·calendar SHA, metric 정의, 파일 SHA/행 수/재개 정보 |
| backfill 완료 목록 | 완료·실패·대기 날짜와 각 결과 manifest SHA. 일부 날짜 성공을 전체 성공으로 표시하지 않음 |

`counts.parquet`의 sparse 형식은 반드시 manifest의 `zero_fill_policy`, 고정한 `target_population`과 함께 소비한다. **대상 집합에 있고 해당 날짜의 계산·파일 검증이 완료된 키**에서만 count 행 부재를 metric의 0으로 해석한다. 파일 손실·실행 중·실패·target 대상 밖 키의 부재를 0으로 바꾸지 않는다. PARTIAL에서 이 metric의 0을 서비스에 넣는 것은 2.3의 별도 제안을 채택한 경우만 가능하다.

관계 구간·정렬·delta 중간 파일은 scratch이며, 성공한 출력 검증 후 해당 실행이 소유한 경로만 정리한다. 실패한 실행의 진단 자료는 정책에 따라 보존한다. 기존 7번 파일은 삭제하지 않는다. 고유 요구조건 구간의 재개 체크포인트를 디스크에 남길 수 있으나 서비스 산출물이나 날짜별 edge로 취급하지 않는다.

### 출력·DB 규모를 먼저 측정

기존 **6,156,555개**는 최신 날짜의 성공 관계에 등장한 target 수다. 모든 유효 버전의 0까지 포함한 행 수가 아니다. [E5]

```text
모든 대상·0을 날짜별 물리행으로 저장할 때의 키 수 = SUM_T 유효 target 중 published_at <= T인 버전 수
```

현재 source/candidate 47,172,949개를 그대로 229번 곱한 값은 약 108억 행의 거친 상한일 뿐이다. 실제 target의 stable-semver 제외와 각 배포 시각을 반영해야 한다. 이 계획에서는 그 수를 입력 준비 단계에서 계산한다. 숫자만 저장하더라도 DB의 키·행·인덱스 비용은 남는다. [E4, E8]

Parquet는 양수 count와 한 번의 target 목록으로 압축하되, 기존 DB에 모든 유효 키를 물리적으로 넣는 경우 0 행도 필요하다. 전체 적재 전 실제 키 수와 격리 DB의 측정 행/인덱스 크기, 대상 DB 여유 용량·적재 시간을 대조한다. 기존 표의 14.4MB나 83초를 전체 version×229 날짜의 저장·해석 비용으로 외삽하지 않는다.

H1 이후 이 합은 6,971,338,953으로 실측됐다. 사용자가 저장량을 문제로 제기했으며,
69.7억은 DB 스키마 자체의 필수 행 수가 아니다. 아래 전체 대상·0 물리행 적재안은 아직
채택하지 않은 제안이다. DB에도 양수 결과만 저장할지, 누락·미계산·0을 어떻게 조회할지
서비스 계약을 정리한 뒤 H6/H7의 적재 계획을 확정한다. H3 계산 핵심은 이 선택과 독립적이다.

## 6. package_version_snapshot 반영

서비스 DDL은 `(package_id, version, snapshot_at)` PK와 `dependents_count INT NOT NULL DEFAULT 0`을 사용한다. 현재 저장소에는 이 테이블 전용 loader가 없으므로, 기존 package/version loader의 패턴을 재사용하되 새 metric loader를 만든다. 기존 loader는 `package-version` dataset에 묶여 있어 그대로 호출하지 않는다. [E2, E12]

1. 격리 DB에서 `version`·`snapshot` FK와 실제 대상 행 유무를 확인한다. 없는 service version ID를 새로 만들지 않는다. 날짜 등록은 기존 snapshot-reference 절차로 수행한다.
2. 한 날짜의 sparse count와 해당 날짜까지 유효한 target population을 합쳐 staging의 **모든 대상 키에 명시적 count(0 포함)**를 만든다. 해당 의미의 0이 승인되지 않았다면 이 단계를 서비스 게시에 사용하지 않는다.
3. staging의 `(package_id, version, snapshot_at)` 유일성, count의 0 이상·INT 범위, FK, 전체 target 행 수·양수 행 수·count 합계를 확인한다.
4. `(dataset, snapshot)` 단위 잠금과 하나의 날짜 트랜잭션으로 반영한다. 기존 행은 count를 변경하고 없는 행은 삽입한다. 현재 DDL의 4개 컬럼만 다루며 다른 날짜나 `package_snapshot`의 다운로드·별점을 건드리지 않는다.
5. 서비스 반영과 `etl_load_execution`/`etl_load_attempt`의 게시 기록을 같은 트랜잭션으로 완료한다. 관측/계산 시각·metric 정의·PARTIAL 품질·허용 근거는 `input_metadata`와 manifest로 연결한다. DB 실행의 `PUBLISHED`는 원본 품질 COMPLETE를 뜻하지 않는다.
   제안 dataset 식별자는 `version-dependents-reconstructed`다. 동일 dataset·snapshot에 이미 게시된 입력이 있으면 manifest/정책 identity를 대조한다. 잠금 아래에서 동일 입력은 재검증하고 다른 입력은 충돌 처리하여, 해당 snapshot의 서비스 값이 어느 품질 이력에 속하는지 모호해지지 않게 한다.
6. `etl_dataset_current`는 dataset별 한 행이므로 229개 날짜 완료 목록으로 쓰지 않는다. 역사 날짜별 실행은 execution 기록과 backfill 완료 목록으로 조회한다. 과거 날짜 적재가 최신 포인터를 뒤로 옮기지 않도록 한다. [E12]
7. 동일 입력/정책/calendar/manifest 재실행은 재검증하고 중복 삽입하지 않는다. 같은 키의 다른 입력·정책 결과는 충돌로 거부한다. 향후 교체가 필요하면 대상 snapshot과 이전 게시 SHA를 명시한 별도 교체 절차로 수행한다.
8. 해당 날짜 기존 게시 결과 중 새 대상에서 빠지는 키가 있으면 자동 삭제하지 않고 차이를 보고한다. 실패하면 그 날짜 트랜잭션만 롤백하며 기존 성공 날짜는 유지한다.

초기 dense backfill에서 날짜 하나의 staging/트랜잭션이 감당하기 어려우면 대상 DB 용량과 운영 요구를 먼저 재검토한다. 서비스 테이블을 몰래 sparse로 바꾸거나 부분 날짜를 성공으로 표시하는 우회는 하지 않는다.

## 7. 구현 순서와 완료 산출물

| 단계 | 작업과 예상 변경 경계 | 해당 단계의 종료 조건 |
| --- | --- | --- |
| H0 | 본 계획의 과거 재구성 모드·metric 정의·PARTIAL/0/게시 정책과 소비자 품질 표시 계약을 결정 문서에 명시. 서비스 DDL은 유지 | 진단 계산과 실제 게시의 허용 근거 분리. 새 게시 계약 미채택이면 실제 결과는 ready_for_load=false, H7 미착수 |
| H1 | 제안 `pipeline/version_dependents/historical_input.py`: calendar·고정 원본·ID 연결·birth index·source/target/고유조건 준비 | 229개 날짜와 입력 pin 검증, target별 eligibility·NULL/semver 제외 및 총 DB 키 수 보고 |
| H2 | 작은 기준 구현과 손계산 테스트: 매 T 후보를 직접 선택하여 DISTINCT 후 count. 전수 운영 경로로 사용하지 않음 | 경계 사례에서 기대값과 일치하는 독립 비교 기준 확보 |
| H3 | 제안 `historical_semver_worker.cjs`, `historical.py`: 패키지별 고유조건의 target 구간, source 교집합/구간 합집합, delta 누적 | H2와 전체 키·count·상태 일치, 동일 입력의 파티션·순서 변화에도 동일 결과 |
| H4 | 제안 `historical_artifact.py`와 CLI: sparse count·population·quality·lineage·재개 목록·파일 검증 | 여러 날짜 파일 분리, 원본/정책/cache 변경 감지, 실패·재개·manifest 마지막 작성 검증 |
| H5 | 실제 입력 층화 표본 성능 측정, 계산 자원 예산 확인 후 최신 날짜 전체 대조와 229개 backfill | 최신 양수 count 6,156,555키와 합계 280,232,217을 기존 진단 결과와 양방향 EXCEPT ALL로 대조; 229개 모두 계산 완료. 예산 미확정/초과 시 표본까지만 수행 |
| H6 | 제안 `historical_load.py`: 격리 PostgreSQL의 합성 데이터로 staging·0 생성·FK·원자 게시·재실행 구현 및 행/인덱스/WAL 비용 측정 | rollback/충돌/누락 파일/0 의미/기존 날짜 보존·게시 이력 테스트 통과. 실제 PARTIAL 입력 게시 허용을 뜻하지 않음 |
| H7 | 대상 DB 실제 상태·용량·H0의 게시 계약·적재 시간 예산 확인 후 snapshot별 적재 및 독립 대조 | 모든 게이트 통과 후 목표 229개 날짜별 전체 대상 키·count·게시 이력 일치, 실패·미계산 날짜 0개. 미완료 목록이 있으면 전체 완료로 판정하지 않음 |

새 파일명은 구현 전 제안이다. 기존 `aggregate.py`, `artifact.py`, `diagnostic.py`, 7번 resolver는 비교 기준으로 보존한다. 공통 순수 유틸리티의 재사용은 허용하되 기존 단일 snapshot/COMPLETE guard를 낮추지 않는다. 기존 alias/prerelease 의미 변경은 이 단계들에 포함하지 않는다.

## 8. 검증과 수락 기준

| ID | 검증 항목 | 통과 기준 |
| --- | --- | --- |
| AC-H01 | calendar/입력 고정 | 229개 날짜, 정확한 시각·원본/정책 SHA 일치. 뒤섞인 관측일·변조·새 파일·future T 거부 |
| AC-H02 | 시간 경계 | source/target의 배포 시각=T 포함, T+1 microsecond 제외, NULL 제외. UTC-aware와 계약 있는 naive-UTC 값의 결과 동일, OS 시간대 변경에도 동일. 계약 없는 naive/잘못된 timezone/정밀도 손실 거부. 불규칙 calendar와 첫/마지막 경계 통과 |
| AC-H03 | 버전 선택 | exact, ^, ~, 비교식, OR, x-range, 공백/invalid/unsupported, 동일 precedence tie를 기존 npm worker와 일치시킴 |
| AC-H04 | 시간 구간 | 신규 높은 버전이 target을 교체, 나중 발행한 낮은 버전은 기존 높은 winner 유지. 같은 precedence의 1.0.0+z 다음 1.0.0+aa 배포 시 후자로 교체. 같은 birth index 후보 순서 독립 |
| AC-H05 | 중복 | 반복 선언·다른 조건의 동일 target·겹치는/중첩/인접 구간은 source 버전당 1. 다른 source 버전은 각각 1 |
| AC-H06 | 집계 | 손계산 그래프·무의존·미해석→해석 전환·self-edge·체인에 대해 H2와 모든 target/date count 일치. 간접 의존자는 더하지 않음 |
| AC-H07 | 보존 법칙·품질 | 4-E의 모든 보존식과 source 상태 우선순위 통과. prerelease-only/invalid-only/future-only/미매핑 구분 및 NO_ELIGIBLE→NO_SATISFYING→RESOLVED 전환 검증. 오류 source의 성공 관계는 count에 남음. delta 누적 음수 없음, 범위 밖 버전에 count 없음 |
| AC-H08 | 실제 최신값 대조 | 기존 양수 target 키와 count가 양방향 EXCEPT ALL 0행, 선언 성공/미해석 수 일치. 기존 진단이 과거 정답의 증거라는 주장은 하지 않음 |
| AC-H09 | 0와 파일 부재 | 유효 population+완료 manifest가 있을 때만 zero 계약 적용. 누락·실패·대상 제외를 0으로 만드는 테스트 모두 거부 |
| AC-H10 | 재시작 | 중단된 파티션/날짜 재개 후 clean run과 결과 hash/값 일치. 다른 입력·정책 캐시 재사용 거부 |
| AC-H11 | DB | sparse→dense staging의 전체키/FK/0/INT/합계 일치, 중복 재실행 무변경, 오류 주입 rollback, 다른 날짜 보존 |
| AC-H12 | 완료 판정 | 계산완료·PARTIAL 품질·DB 게시를 각각 기록. 229개 전부 성공을 증명하기 전 전체 완료로 표시하지 않음 |
| AC-H13 | 자원·게시 게이트 | 예산 누락/초과에서는 대규모 단계 시작 거부. 소비자 계약·채택 근거가 없으면 실제 PARTIAL manifest 게시 거부. 합성 데이터 테스트 성공으로 게이트를 우회하지 않음 |

실제 표본은 lookup ID의 고정 해시 표본과 후보 버전이 많은 상위 패키지를 함께 포함한다. 선택한 target 패키지의 전체 후보·선택 source의 전체 관련 선언을 유지해 표본 절단으로 winner나 중복이 바뀌지 않게 한다. 계산 기준일은 첫날·중간·마지막과 표본의 실제 버전 교체 경계를 포함한다.

H5에서 기존 8/31과 일치하지 않으면 차이가 parser/후보/관측입력/중복/시간 정책 어디에서 생겼는지 확인한다. 기존 수치에 맞추기 위해 새 검증 실패를 무시하지 않는다.

## 9. 성능·복구 계획과 위험

- 초기 실행 설정 제안: DuckDB 8 threads/8GB, 기존 Node 1개 프로세스의 768MB heap 설정을 출발점으로 사용한다. 전체 source·구간·target×date를 Python 리스트로 반입하지 않는다. 큰 패키지는 batch API와 외부 정렬/분할 처리를 사용한다. [E9, E11]
- 측정값: 입력 준비 시간, 고유 lookup 수, query-candidate 비교 수, lookup 구간 수, source 구간 합집합 후 수, delta 수, scratch 최고 사용량, 프로세스 메모리, 날짜별 양수/0대상 행 수, COPY/인덱스 비용.
- 구간 방식의 시간·공간 이득은 아직 미측정이다. 서로 다른 원문 제약식이 많거나 버전 교체가 잦으면 구간 수가 커질 수 있다. H3 표본에서 단순 T별 기준 구현과 값·시간·중간 크기를 비교하고, 특정 큰 패키지는 날짜 batch 방식으로 처리하는 fallback을 둔다. fallback도 날짜별 edge를 영구 보존하지 않는다.
- 전체 실행은 입력 준비→패키지 파티션→snapshot 출력의 완료 지점을 기록한다. 실패한 파티션만 재개하고, 완료된 count 파일만 가지고 DB 재시도를 할 수 있게 한다.
- 단계 시작 전에 아래 자원 예산 파일을 작성한다. 대상 장치의 여유 공간·운영 시간 창은 현재 미확인이다. 아래 한도를 만족하는 실측/예측 자료가 없으면 해당 대규모 단계는 시작하지 않는다. 이는 계획 작성 후 바로 실행한다는 의미가 아니다.
- 과거 당시 데이터 완전성, PARTIAL 서비스 의미, target 제외 정책은 기술적 성공과 별개다. 관측 당시 실제 설치 그래프 또는 완전한 역사 count라는 문구를 사용하지 않는다.
- 아직 전체 기간의 신뢰할 만한 소요시간은 없다. 기존 82.577초는 이미 해석된 최신 관계의 검증·집계·저장 시간이며, 새 과거 해석·전체 대상 0 생성·DB 적재 시간은 포함하지 않는다. H1/H3 표본 후 단계별 예상치를 새로 보고한다. [E11]

제안 `resource-budget.json`에는 측정 시각·장치, 날짜별/전체 dense 키 수, 양수 출력 예상 수, 파티션 최대 크기, 예상 시간과 아래 한도를 기록한다. 서버 용량이나 운영 예산을 임의의 수치로 채우지 않는다.

| 게이트 | 반드시 채울 값·시작 조건 | 초과/미확정 시 |
| --- | --- | --- |
| H5 전체 계산 전 | `max_scratch_bytes`는 시작 시 작업 디스크 가용 공간의 50% 이하. scratch와 출력 합계가 가용 공간을 넘지 않음. `max_process_rss_bytes`, `max_backfill_seconds`를 실행 장치/시간 창에 맞게 명시하고 큰 패키지를 포함한 표본 예측치가 모두 이내 | 표본 결과까지만 보고. target 패키지 분할·batch 크기를 줄여 재측정하거나 실행 장치/시간 창을 조정 |
| H6 격리 DB 시험 전 | `max_fixture_rows`, `max_fixture_disk_bytes`, `max_fixture_seconds`를 정해 합성 표본을 제한. heap·인덱스·staging·WAL·재시도 시 동시 점유량과 COPY/commit 시간 측정 | 표본 크기를 낮추고 다시 측정. 운영 전체 행 수를 격리 DB에 무조건 적재하지 않음 |
| H7 실제 적재 전 | `dense_keys_by_snapshot`, `dense_keys_total` 실측 확보. `max_target_rows`, `max_db_growth_bytes`, `max_snapshot_load_seconds`, `max_total_load_seconds` 명시. heap+인덱스+최대 staging+WAL/롤백 여유까지 합친 예상 증가량이 허용 예산과 실제 가용 공간 모두 이내 | 적재 미착수. 용량/운영 창 재협의 또는 별도 저장 계약 설계. sparse 서비스 전환·날짜 부분 게시를 자동 선택하지 않음 |

DuckDB 8GB/Node 768MB는 엔진 설정의 출발점이며 전체 프로세스 RSS 한도를 보장하지 않는다. 측정 예산을 실행 중에도 검사하고 초과 시 완료 manifest 작성 전 중단한다. 전체 229일 계산 파일 생성에 필요한 H5 예산과 DB 게시에 필요한 H7 예산을 분리하여, DB 예산 미확정이 소규모 계산 검증까지 막지는 않게 한다.

## 10. 대안과 선택 이유

| 대안 | 판단 |
| --- | --- |
| 매 날짜 7번 전체 관계 Parquet를 생성한 뒤 8번 집계 | source 전개/관계 쓰기·읽기·검증을 229번 반복하므로 채택하지 않음. 작은 독립 기준 구현에만 유사 방식을 사용 |
| 최신 edge 파일의 날짜만 바꾸거나 배포일로 필터 | 과거에는 선택 대상 버전이 달랐던 관계를 복원하지 못하므로 제외 |
| source를 대표 최신 버전 하나로 축소 | 기존 source-version별 count 정의를 바꾸므로 제외 |
| 고유 요구조건의 target 변경 구간 + source 구간 합집합 + delta 누적 | 권고. 날짜별 영구 edge를 생략하고 동일한 의미의 날짜별 count 생성. 구간 크기·성능은 검증 필요 |
| 각 과거 날짜의 실제 관측 원본 확보 | 당시 관측값이 목표라면 필요할 수 있는 별도 수집 계획. 현재 고정 최신 입력으로 재구성하는 본 제안과 구분 |

## 11. 근거와 확인 범위

| ID | 확인한 코드/기록 | 이 계획에 사용하는 사실 |
| --- | --- | --- |
| E1 | [08 티켓](../../jira/db-loading/08-version-dependents-load.md), [집계 정의](../../../pipeline/version_dependents/aggregate.py) | source 버전 distinct, target/date grain, 전체 target과 0, 직접 관계 |
| E2 | [서비스 DDL](../../../backend/src/main/resources/db/migration/V1__init.sql) 48~53, 78~80행 및 FK 절 | PVS 4컬럼, INT/NOT NULL/default, 복합 PK/FK |
| E3 | [calendar 정본](../../../data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json) | 229개, 2022-05-08~2026-08-31, SHA `d22099ce22031deb47993f5c66b633d3754fd0625dbb1dcbaafc60070f8afaa7` |
| E4 | [7번 실제 실행](../S15P21A506-283/05-full-run.md), [7번 결과](../S15P21A506-283/06-computation-results.md) | 최신 한 날짜, source/candidate 47,172,949, 선언 289,214,123, PARTIAL |
| E5 | [8번 진단 실행 증거](evidence/diagnostic-full-run.json) | 최신 양수 target 6,156,555, 관계 280,232,217, 중복 0 |
| E6 | [input.py](../../../pipeline/requirements_resolution/input.py) 77~117행, [transform.py](../../../pipeline/requirements_resolution/transform.py) 48~89행, [build.py](../../../pipeline/requirements_resolution/build.py) 234행·CLI | 단일 관측/계산 시각, source/target 배포일 필터, 단일 snapshot 실행 |
| E7 | [snapshot 정책](../../../pipeline/snapshot/policy.py) 27~62행, [snapshot 안내](../../../pipeline/snapshot/README.md) 93~123행 | 원천 시각·calendar·Projects 관측 계약과 지표 계산 범위 구분 |
| E8 | [transform.py](../../../pipeline/requirements_resolution/transform.py) 93~110·154~166·187~218행, [정책](../../../pipeline/requirements_resolution/policy.py) | 고유 source/선언, lookup ID, source-target 중복, policy 정의 |
| E9 | [bridge.py](../../../pipeline/requirements_resolution/bridge.py) 139~168행, [semver worker](../../../pipeline/requirements_resolution/semver_worker.cjs) 80~145행 | 고유조건, Node/npm 사용, 후보 정렬, valid/stable, unsupported, tie |
| E10 | [현재 결정](06-decisions.md) D-04·D-07·D-09 | PARTIAL 진단 승인 범위, 정상 0/DB 게시 미승인, resolver 개선 범위 미정 |
| E11 | [진단 결과](09-diagnostic-run.md), [측정 증거](evidence/diagnostic-full-run.json) | 8 threads/8GB, 82.577초의 측정 범위 |
| E12 | [기존 적재 패턴](../../../pipeline/postgresql/README.md) 121~180행, [postgres.py](../../../pipeline/postgresql/postgres.py) 141~142·257~292행, [실행 이력 DDL](../../../backend/src/main/resources/db/migration/V2__add_curated_load_execution.sql) | staging/transaction/execution, package-version 전용 코드, dataset별 단일 current |

이번에는 코드·작은 메타데이터·기존 측정 증거만 조사했다. 위 새 알고리즘의 실행, 전체 target stable-semver 분류, 총 dense DB 키 수 측정, 대상 DB 상태·용량 확인은 수행하지 않았다.
