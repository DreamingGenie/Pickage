# deps.dev BigQuery → Parquet 수집계획 v2 (예산 반영 수정판)

작성 2026-09-02 · 대상 OSS Shift 데이터 수집 · 상태 **확정(2026-09-02) · T0·T1 수집 완료(과금 103.2 GiB, 232잡 전부 검증 통과)**
선행 문서 `depsdev_BigQuery_데이터셋_사용계획_260831.md`, `../분석_제공가치_deps.dev_260901.md`, `../설계_마이그레이션쌍_탐지_260831.md`
초안(v1): 2026-09-02 전진님이 제시한 "원천 → BigQuery → GCS Parquet → Spark" 계획

이 문서의 스캔량은 전부 **2026-09-02 `bq --dry_run` 실측**이다(기준 스냅샷 `2026-08-31`, 프로젝트 `oss-shift-a506`). dry-run은 과금이 없다. 실행한 쿼리는 §1-3의 0.95 GiB 1건뿐이다.

---

## 0. 결론

| v1 계획의 질문 | 답 |
|---|---|
| `Dependents`를 그대로 호출해도 되는가 | **불가.** npm 한 스냅샷 **650.66 GiB**. `Name='moment'` 하나로 좁혀도 **똑같이 650.66 GiB**(클러스터 키 없음, 프루닝 0). 스냅샷 177개 백필은 112 TiB ≈ $700 |
| 출력 스키마를 지키면서 다른 방식이 있는가 | **있다.** `NPMRequirements`(17.5 GiB) + `PackageVersions`(24.4 GiB) 한 스냅샷에서 **임의 시점의 dependents를 재구성**한다. 컬럼 구성은 유지, `version`의 의미만 "해결된 버전 → 선언 요구조건에서 파싱한 major"로 바뀐다 |
| 스냅샷마다 반복 반출해야 하는가 | **대부분 아니다.** 한 스냅샷에 16년치 발행 이력이 들어 있어 `dependents`·`trend`·`meta`는 1회 반출로 전 기간이 나온다. 스냅샷마다 받아야 하는 건 **`Projects`(stars·issues) 하나**이고, 228개 백필 합쳐 약 51 GiB(`SnapshotAt` 열 포함 실측) |
| 예산(600 GB 무료 + $100) 안에 드는가 | **든다.** 필수 수집 전체 ≈ **225 GiB**, 무료분의 38%. $100은 손대지 않는다. 선택 항목(폐기 시점 백필 449 GiB)을 넣어도 초과분은 $1 미만 |

**바뀐 것 한 줄**: "스냅샷마다 4테이블 반출"(v1) → **"핵심 3테이블 1회 반출 + Projects 전 스냅샷 백필 + 주간 증분"**(v2).

---

## 1. 실측 — 무엇이 얼마나 드는가

### 1-1. 한 스냅샷(2026-08-31) 스캔량

| # | 원천 | 열 | 스캔 | v1 대비 |
|---|---|---|---:|---|
| D1 | `Dependents` npm 전체, MinimumDepth=1, HighestRelease | 5열 | **650.66 GiB** | v1 Q1 그대로 |
| D1b | 같은 쿼리 + `Name='moment'` | 5열 | **650.66 GiB** | 클러스터 없음 → 필터 무효 |
| D2 | `PackageVersions` v1 Q2 그대로(Description·Licenses·Links 포함) | 10열 | 24.44 GiB | |
| D2b | `PackageVersions` 최소(Name·Version·IsRelease·Ordinal·PublishedAt·Deprecated) | 6열 | 5.24 GiB | Description·Links·Licenses가 19 GiB |
| D2c | `PackageVersions` Name·Version·Deprecated만 | 3열 | 4.05 GiB | 폐기 시점 백필용 |
| D3 | `PackageVersionToProject` npm | 5열 | 10.37 GiB | |
| D4 | `Projects` 전체(GitHub·GitLab·Bitbucket) | 5열 | 0.32 GiB | |
| D5 | `NPMRequirements` Dependencies+Peer+Optional | 5열 | 17.51 GiB | regular만이면 15.49 |
| D6 | `Dependencies` npm MinimumDepth=1 전체 | 5열 | 553.12 GiB | 참고. 단일 패키지는 0.44 GiB(클러스터 有) |

**핵심 묶음(D2+D3+D4+D5) = 52.64 GiB.** `Dependents` 하나가 이 묶음의 12배다.

### 1-2. 전 스냅샷 백필 총량

| 원천 | 스냅샷 수 | 총 스캔 | 스냅샷당 평균 | 판정 |
|---|---:|---:|---:|---|
| `Projects` 5열 | 229 | **44.47 GiB** | 0.19 | **백필한다** — 재구성 불가한 유일한 시계열 |
| `PackageVersions` Deprecated 3열 | 225 | 449.19 GiB | 2.00 | 선택(§3-3) |
| `PackageVersions` 최소 6열 | 225 | 609.15 GiB | 2.71 | 불필요 |
| `PackageVersionToProject` | 228 | 930.08 GiB | 4.08 | 불필요 |
| `Dependents` (D1 기준 환산) | 177 | ≈ 112 TiB | 650 | **금지** |

스냅샷당 크기는 해마다 커진다(PV 3열: 2022-05 1.27 → 2024-06 2.24 → 2025-06 2.76 → 2026-08 4.05 GiB). 백필은 옛 것이 싸다.

### 1-3. 파라미터 정합성 (실행 1건, 0.95 GiB)

`PackageVersions.SnapshotAt` = `2026-08-31 21:01:10` — `Snapshots.Time`과 **초 단위까지 일치**한다. v1의 `SnapshotAt = @snap` 필터는 유효하다. npm 행 수 78,559,731.
단, 파티션 프루닝은 `DATE(SnapshotAt) = DATE '…'`가 확실하므로 쿼리에는 이 형태를 쓴다(§4).

---

## 2. 판정 1 — `Dependents`를 어떻게 대체하나

### 2-1. 재구성 원리

`Dependents`의 한 행은 "스냅샷 시점에 패키지 D의 **최고 릴리스**가 `name@version`을 직접 의존한다"이다. 같은 사실을 우리가 이미 반출하는 두 테이블로 만들 수 있다.

```
PackageVersions(D의 모든 릴리스, 발행시각, Ordinal)
  → 시점 T 이전에 발행된 릴리스 중 Ordinal 최댓값 = T 시점 D의 대표 릴리스
NPMRequirements(D@대표릴리스).Dependencies
  → (name, requirement) 목록 = T 시점 D의 직접 의존
```

`Dependents`는 T = 스냅샷 시점에서 이걸 deps.dev가 미리 계산해 둔 것이다. 우리는 T를 **임의로** 잡을 수 있다. `NPMRequirements`가 35주만 보관되고 `Dependents`가 177주만 있는 것과 무관하게, **한 스냅샷의 발행 이력으로 2010년부터 재구성**된다(09-01 문서 §2-1이 이미 이 방식으로 연도별 신규 채택을 냈다).

**보관기간이 왜 상관없나.** `Dependents`의 행은 "그 주에 계산한 결과"라 과거를 보려면 그 주의 스냅샷이 있어야 한다(백필 필요). 반면 `NPMRequirements`의 행은 "버전 X의 package.json 선언"이고, npm 버전은 **발행 후 불변**이다. 2023년에 발행된 `foo@1.2.0`의 선언은 2023년 스냅샷에서나 2026-08-31 스냅샷에서나 같은 행이다. 35주 보관은 "스냅샷끼리 비교"를 막을 뿐, 한 스냅샷 안에는 2010년부터의 모든 버전 선언이 들어 있다. 그래서 `Dependents` 177개 스냅샷을 백필하는 대신 `NPMRequirements` 1개 + `PackageVersions` 1개로 같은 계산을 어느 시점에 대해서든 다시 한다.

예: `foo@1.2.0`(2023-03-01 발행, `"moment": "^2.29"`). 2023-04 `Dependents` 행은 `(moment, 2.29.4, foo, 1.2.0)`. 재구성은 T=2023-04-01에 foo의 발행된 릴리스 중 Ordinal 최고가 1.2.0임을 `PackageVersions`에서, 그 선언이 `moment ^2.29`임을 `NPMRequirements`에서 얻어 `(moment, ^2.29→major 2, foo, 1.2.0)`을 낸다. `version` 열의 형태만 다르다.

### 2-2. 스키마 유지 방식 — 구간(span) 팩트 + 격자(grid) 뷰

시점마다 행을 찍으면 (시점 수 × 2,000만 행)으로 부풀 뿐 정보는 같다. 대신 **대표 릴리스가 유효한 구간**을 저장한다.

**`dependents_span`** — 키 `(dependent_name, dependent_version, name)` · 파티션 없음(또는 `valid_from` 연도) · 1회 반출 시 overwrite

| 컬럼 | 타입 | 원천 | v1 대비 |
|---|---|---|---|
| dependent_name | string | NPMRequirements.Name | 동일 |
| dependent_version | string | NPMRequirements.Version | 동일 |
| valid_from | timestamp | 이 릴리스가 대표가 된 시각(= 발행시각) | **신규** (snapshot_at 대체) |
| valid_to | timestamp (nullable) | 다음 대표 릴리스 발행시각. NULL = 현재도 대표 | **신규** |
| name | string | Dependencies.Name | 동일 |
| requirement | string | Dependencies.Requirement 원문 | **신규** (version 대체) |
| major | int (nullable) | requirement 파싱 (Spark 파생) | 동일 컬럼, 원천 변경 |
| dep_kind | string | 'regular' / 'peer' / 'optional' | **신규** (08-31 문서 §7-1 재분류 판정용) |

v1의 `dependents(snapshot_at, name, version, major, dependent_name, dependent_version)`는 이 테이블의 **뷰**로 항상 만들 수 있다.

```sql
-- 시점 T의 dependents (v1 스키마 그대로)
SELECT TIMESTAMP 'T' AS snapshot_at, name, requirement AS version, major,
       dependent_name, dependent_version
FROM dependents_span
WHERE dep_kind = 'regular'
  AND valid_from <= TIMESTAMP 'T' AND (valid_to IS NULL OR TIMESTAMP 'T' < valid_to)
```

§6의 파생 지표는 전부 이 뷰 위에서 v1 그대로 동작한다. 마이그레이션(인접 시점 self-join)은 뷰 두 개를 조인하면 되고, 사실 span 테이블에선 더 단순하다 — `(dependent_name, name)`의 구간이 끝나고 같은 `dependent_name`에 다른 `name`의 구간이 같은 `valid_from`으로 시작하면 그게 교체 이벤트다.

**격자 물질화가 필요하면** 시점 목록(예: 매월 1일 2012-01~2026-09, 177개)을 span에 range-join해 `dependents_agg(as_of, name, major, n_dependents)`만 저장한다. 원본 행이 아니라 집계라 크기가 작다.

### 2-3. `Dependents`와 달라지는 의미 3가지 — 화면·문서에 명시할 것

| 항목 | `Dependents`(v1) | 재구성(v2) | 영향 |
|---|---|---|---|
| `version` | 해결된 구체 버전 (`5.3.1`) | 선언 요구조건 (`^5.0.0`) → major 파싱 | major 집계는 동일. 해석불가 비율 실측 **1% 미만**(09-01 §4-2). `>=4 <7`·`*`·git URL 등은 major NULL |
| 대표 릴리스 조건 | `DependentIsHighestReleaseWithResolution` = 의존 해석에 **성공한** 최고 릴리스 | 발행시각 ≤ T인 릴리스 중 Ordinal 최고(`IsRelease`, 발행시각 NOT NULL) | 해석 실패(`DependencyError` 317만 버전)도 포함됨. 플래그로 보존해 필터 가능 |
| 관측 범위 | 스냅샷 177개(2022-05~) | 임의 시점(2010~), 단 **현재 스냅샷에 남아 있는 버전**만 | unpublish된 버전은 과거에 있었어도 안 보임(생존 편향, 09-01 §5와 동일 고지) |

교차검증: deps.dev REST API(무과금)에 버전 단위 dependents 조회가 있어 표본 몇 개의 직접 의존자 수를 대조할 수 있다. 전수 대조는 `Dependents` 1회 650 GiB라 하지 않는다.

---

## 3. 판정 2 — 무엇을 1회, 무엇을 매 스냅샷 받나

### 3-1. 재구성 가능성으로 갈라진다

| 출력 컬럼 | 한 스냅샷(T0)으로 과거 복원 | 어디서 채워지나 |
|---|---|---|
| dependents 전부 | **가능** | T0 (span 뷰) |
| trend.latest_release_at | **가능** | T0 — 발행시각 ≤ T 중 최댓값 |
| trend.stars / open_issues | **불가** | **T1** Projects 백필(필수 예산에 포함). 2022-05-08 이후 229개 시점, 그 이전은 NULL |
| trend.latest_is_deprecated | 최신 시점만 정확 | T0 — 현재 폐기 여부. **과거 시점의 값은 T3**(스냅샷별 Deprecated)가 있어야 정확. 없으면 과거 시점은 NULL로 둔다 |
| meta 전부 | 최신값만 필요 | T0, overwrite 설계 그대로 |

`Deprecated`는 "지금 폐기 표시가 있나"만 있고 **언제** 표시됐는지가 없다. 폐기 시점을 아는 유일한 경로는 스냅샷을 모아 플래그가 바뀐 주를 찾는 것(T3)이고, 그것도 2022-05 이후만 가능하다. npm 레지스트리 packument에도 폐기 시각은 없다.

### 3-2. 수집 계층 (Tier)

| Tier | 내용 | 원천 | 주기 | 스캔 |
|---|---|---|---|---:|
| **T0 핵심** | 최신 스냅샷 1회 전수 반출 | D2 PackageVersions 24.44 + D5 NPMRequirements 17.51 + D3 PVTP 10.37 + D4 Projects 0.32 | 1회 (착수 시) | **52.64 GiB** |
| **T1 stars 백필** | `Projects` 전 스냅샷 | D4 × 229 | 1회 | **44.47 GiB** |
| **T2 주간 증분** | 새 스냅샷마다 | D5 NPMRequirements 17.51 + D2b PV 최소 5.24 + D4 Projects 0.32 | 주 1회 (월) | **23.07 GiB/주** |
| **T2m 월간 갱신** | Description·Links·저장소 매핑 | D2 전체 24.44 + D3 PVTP 10.37 | 월 1회 | 34.81 GiB/월 |
| **T3 선택** | 폐기 시점 백필 | D2c × 225 | 1회 | 449.19 GiB |

주간 증분에서 Description(19 GiB)을 빼는 이유: 설명·라이선스·링크는 주 단위로 달라질 일이 거의 없고, 열 스캔 비용이 묶음의 절반이다.

### 3-3. T3(폐기 시점 백필)을 할 것인가 — 전진님 결정 사항

얻는 것: ① `trend.latest_is_deprecated`가 스냅샷마다 정확해진다 ② 옛 스냅샷에 있고 최신에 없는 `(Name, Version)` = unpublish 목록이 나온다(§2-3 생존 편향의 실측 규모).
비용: 449 GiB. 필수 수집과 합치면 674 GiB로 무료분(600 GB 가정)을 74 GiB 넘고, 초과분은 **약 $0.45**다.
절충: 4주마다 1개(월간 격자) 57 스냅샷 ≈ **114 GiB**로 ①②의 월 단위 해상도를 얻는다.

**권고**: 착수 시점엔 하지 않는다. T0~T2로 화면 데이터가 다 나오고, 폐기 시점은 마감(09-25)까지 화면에 쓸 계획이 없다. 예산은 남기고, 필요해지면 월간 격자(114 GiB)부터.

### 3-4. 예산 시나리오

| 항목 | 스캔 |
|---|---:|
| T0 핵심 1회 | 52.64 GiB |
| T1 Projects 백필 (228 파티션, SnapshotAt 포함 실측) | 51 GiB |
| T2 주간 × 4주 (09-07·14·21·28) | 92.28 GiB |
| T2m 월간 × 1 | 34.81 GiB |
| **필수 합계** | **약 231 GiB** |
| 무료분 600 GB 대비 | **39%** |
| + T3 전체 | 673.39 GiB → 초과 ≈ $0.45 |
| + T3 월간 격자 | 338 GiB → 무료 내 |
| (참고) v1 계획: Dependents 1스냅샷 | 650.66 GiB → 단독으로 무료분 초과 |
| (참고) v1 계획: Dependents 177스냅샷 백필 | ≈ 112 TiB ≈ **$700** |

BigQuery 온디맨드 단가 $6.25/TiB 기준. 무료분은 실제로는 월 1 TiB이나 전진님이 제시한 600 GB를 상한으로 잡았다. 콘솔에서 이달 사용량을 한 번 확인하면 된다.

---

## 4. 수정된 BigQuery 추출

공통 규칙
- 파티션 필터는 **항상** `DATE(SnapshotAt) = DATE '@snap_date'`. `Latest` 뷰 직접 조회 금지.
- 모든 실행에 `--maximum_bytes_billed` 상한. T0 개별 쿼리는 30 GiB(=32,212,254,720), 주간 증분 20 GiB. **`Dependents`·`Dependencies`·`DependencyGraphEdges`는 어떤 쿼리에도 참조하지 않는다.**
- 결과는 **일반 SELECT → 스테이징 테이블(`oss-shift-a506.staging`, 3일 만료) → `extract` 잡 → GCS Parquet** 순으로 쓴다. `EXPORT DATA` 문장은 쓰지 않는다(아래).
- 실행 전 `--dry_run`으로 §1 수치와 대조. 25% 이상 어긋나면 멈춘다.
- **`EXPORT DATA`를 쓰지 않는 이유(09-02 리허설 실측)**: EXPORT 문장의 dry-run은 클러스터 프루닝을 추정에 반영하지 않아 PackageVersions가 24.4 → 43.0 GiB로 부풀고 `Name` 필터도 무시된다. `maximum_bytes_billed`는 이 추정치로 검사되므로 실측 기준 상한을 걸면 잡이 거부되고(43 GiB 요구), 상한을 풀면 과금을 보장할 수 없다. 일반 SELECT → 스테이징은 추정·상한·과금이 전부 프루닝을 반영한다(리허설 dry-run 1.325 GiB = 과금 1.326 GiB).
- 실행 스크립트: `pipeline/bigquery/collect.py` (관문 6개, 매니페스트 멱등성, 원장 `pipeline/bigquery/ledger/ledger.jsonl`). 사용법 `pipeline/bigquery/README.md`. (09-02 `bq_export/`에서 이동)
- T1 Projects 백필의 실측 dry-run 합계는 **약 51 GiB**(228 파티션, `SnapshotAt` 열 포함). §1-2의 44.47 GiB는 `SnapshotAt` 없이 잰 값.

경로: `gs://<bucket>/raw/<table>/snapshot=<YYYY-MM-DD>/*.parquet` (T0·T2), `gs://<bucket>/raw/projects/snapshot=<YYYY-MM-DD>/` (T1은 스냅샷별 폴더)

### Q-V. versions (T0·T2m 전체 / T2 최소)

```sql
SELECT
  SnapshotAt, Name, Version,
  VersionInfo.IsRelease AS is_release,
  VersionInfo.Ordinal   AS ordinal,
  UpstreamPublishedAt   AS published_at,
  Deprecated,
  DependencyError       AS dependency_error,     -- 플래그로 보존 (08-31 §5-1)
  Description, Licenses,                          -- ← 주간 증분(T2)에서는 이 두 줄과 아래 source_repo 제거
  (SELECT URL FROM UNNEST(Links) WHERE Label = 'SOURCE_REPO' LIMIT 1) AS source_repo
FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
WHERE System = 'NPM' AND DATE(SnapshotAt) = DATE '2026-08-31';
-- dry-run 24.44 GiB (전체) / 5.24 GiB (최소 + dependency_error)
```

### Q-R. requirements (T0·T2) — `Dependents` 대체 원천

```sql
SELECT SnapshotAt, Name, Version,
       Dependencies, PeerDependencies, OptionalDependencies
FROM `bigquery-public-data.deps_dev_v1.NPMRequirements`
WHERE DATE(SnapshotAt) = DATE '2026-08-31';
-- dry-run 17.51 GiB. 배열은 Parquet에 중첩 그대로 저장, explode는 Spark에서
```

### Q-P. pkg_project (T0·T2m)

```sql
SELECT Name, Version, ProjectType, ProjectName, RelationType
FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject`
WHERE System = 'NPM' AND DATE(SnapshotAt) = DATE '2026-08-31';
-- dry-run 10.37 GiB. RelationType은 출처 등급(UNVERIFIED_METADATA 대부분) 고지용
```

### Q-J. projects (T0·T2 매 스냅샷, T1 백필)

```sql
SELECT SnapshotAt, Type, Name AS project_name,
       StarsCount, ForksCount, OpenIssuesCount
FROM `bigquery-public-data.deps_dev_v1.Projects`
WHERE DATE(SnapshotAt) = DATE '2026-08-31';
-- dry-run 0.32 GiB. T1은 Snapshots.Time 229개를 순회하며 이 쿼리 반복 (총 44.47 GiB)
```

T1 백필은 스냅샷 날짜를 `Snapshots` 테이블에서 받아(10 MB) 루프로 돌린다. 스냅샷당 0.1~0.3 GiB이므로 `--maximum_bytes_billed=1073741824`(1 GiB)로 잠근다.

### 삭제된 쿼리

v1 **Q1(`Dependents`)** — §2로 대체. v1 Q4에서 `SnapshotAt`을 추가한 것 외 Q2·Q3·Q4는 컬럼 소폭 추가(`DependencyError`, `RelationType`, `Peer/OptionalDependencies`).

---

## 5. Spark 변환 — 바뀌는 부분

### 5-1. dependents_span (신규, v1 4.1 대체)

```
rel = raw_versions.filter(is_release & published_at.isNotNull)

# 대표 릴리스: 발행 순으로 봤을 때 Ordinal의 누적 최댓값이 갱신되는 릴리스만
w_time = Window.partitionBy("Name").orderBy("published_at", "ordinal")
rep = rel.withColumn("run_max", max("ordinal").over(w_time.rowsBetween(unboundedPreceding, -1)))
         .filter(col("run_max").isNull() | (col("ordinal") > col("run_max")))
         .withColumn("valid_from", col("published_at"))
         .withColumn("valid_to", lead("published_at").over(Window.partitionBy("Name").orderBy("published_at")))

span = rep.join(raw_requirements, ["Name","Version"], "inner")
   .select(..., explode_outer(arrays_zip(regular, peer, optional)) ...)   # dep_kind 태깅
   .withColumn("major", parse_major(col("requirement")))
   .select("dependent_name","dependent_version","valid_from","valid_to",
           "name","requirement","major","dep_kind")
   .write.mode("overwrite")
```

`parse_major` 규칙(정규식, UDF 금지): `^[\^~]?v?(\d+)` → major; `^(\d+)\.x`·`^(\d+)$` 동일; `>=`·`||`·`*`·`latest`·`npm:`·URL은 NULL. 해석불가는 NULL 유지하고 비율을 매 실행 로그에 남긴다(실측 기대치 1% 미만).

발행시각 역전(axios 0.33.0이 1.0.0보다 뒤에 발행)이 여기서 자연스럽게 처리된다 — 누적 최댓값을 못 넘는 릴리스는 대표가 되지 않는다. `Dependents`의 "최고 릴리스" 의미와 같다.

### 5-2. trend — `latest_release_at` 정의 수정 (v1 오류 가능성)

v1은 "IsRelease 중 Ordinal 최댓값의 UpstreamPublishedAt"으로 정의했다. 그러면 express처럼 5.x가 나온 뒤에도 4.x 유지보수 릴리스를 내는 패키지가 **"마지막 릴리스 = 5.0.0 발행일"**로 오래된 것처럼 보인다. "살아있나"의 신호로는 **모든 릴리스 중 발행시각 최댓값**이 맞다.

| 컬럼 | v2 정의 |
|---|---|
| latest_release_at | `MAX(published_at)` over IsRelease (라인 무관) |
| latest_is_deprecated | Ordinal 최고 릴리스의 `Deprecated IS NOT NULL` (v1 유지 — "지금 받게 되는 버전이 폐기됐나") |
| stars / open_issues | 스냅샷별 `Projects` 조인 (T1로 시계열) |

`trend`는 `dependents_agg`와 **같은 월간 격자**(매월 1일)로 물질화한다. stars·open_issues는 격자 날짜 이전 가장 가까운 Projects 스냅샷(월요일, 최대 6일 전) 값을 붙이고, `projects_snapshot_at` 컬럼으로 그 날짜를 남긴다. Projects가 없는 2022-05 이전은 NULL. `latest_is_deprecated`는 최신 격자점만 값을 채우고 과거 격자점은 NULL(T3 채택 시 채움).

### 5-3. meta, downloads

v1 그대로. `source_repo`는 **`PackageVersionToProject.ProjectName` 1순위, `Links` 2순위**(08-31 문서 §7-2). `deprecated_replacement` 정규식은 유지.

downloads는 v1의 "일별 last-day 호출"을 **주 1회 `last-week` range 호출**로 바꾼다. npm API 지속 속도가 초당 1.5건(08-31 실측)이라 일별은 대상이 수천 개만 돼도 매일 수십 분을 쓴다. 대상은 비교 후보군으로 한정(스코프 패키지는 개별 호출).

---

## 6. 그 외 취약점 점검

| # | 취약점 | 실측·근거 | 조치 |
|---|---|---|---|
| 1 | **상한 없는 실수 한 번이 예산 전부** | `Dependents` 1쿼리 650 GiB, `DependencyGraphEdges` 파티션 `SELECT *` 2 TiB | 콘솔 `QueryUsagePerDay` 커스텀 할당량 1 TiB/일(미설정 상태, 08-31 메모) + 모든 실행에 `--maximum_bytes_billed` |
| 2 | `SnapshotAt = @snap` 불일치 시 0행 반환(무증상) | 이번 확인: 초 단위 일치 | `DATE()` 필터로 통일. 반출 후 행 수 검증(npm PV 78,559,731) |
| 3 | 쿼리 결과 10 GB 상한 | PV 반출은 수 GB Parquet | `EXPORT DATA` 사용. 임시 테이블 경유 안 함 |
| 4 | Description 열이 스캔의 절반 | 19 GiB / 24.4 GiB | 주간 증분에서 제외, 월간만 |
| 5 | `Dependencies`(설치 발자국)도 전수는 553 GiB | D6 | 후보군 단위로만(`Name IN` 시 클러스터 프루닝 됨, 패키지당 0.44 GiB). 수집계획 밖, 화면 단계에서 |
| 6 | 발행시각 NULL 705만 버전 | 09-01 §2-2 | span에서 제외됨. "관측 계약" 고지 유지 |
| 7 | 스팸성 신규 패키지 급증(2024년 66.7만) | 09-01 §4-1 | 원값·비중 병기 규칙 유지. 수집 단계 조치 없음 |
| 8 | GCS·전송 비용 | Parquet 총 20~30 GB 추정. 저장 $0.02/GB·월, 노트북 다운로드 ≈ $0.12/GB(무료 100 GB/월 있음) | 무시 가능. 버킷은 US 리전, 프로젝트 종료 후 삭제 |
| 9 | 주간 스냅샷 지연·결손 | Snapshots 225개, 월요일 21:01 UTC 고정 | 증분 잡은 화요일 실행. `Snapshots`에 새 Time이 없으면 스킵 |
| 10 | 팀 2인 공유 계약 | GCS 버킷 경로 + Parquet 스키마 | 이 문서 §4 경로·§2-2 스키마가 계약. `manifest.json`(스냅샷·행수·dry-run 바이트) 폴더마다 기록 |

---

## 7. 적재 아키텍처 — 현 시점 권고

수집 형태가 바뀌어도 결론은 같다. **팩트는 Parquet에 두고, PostgreSQL에는 화면이 읽는 집계만 넣는다.**

| 계층 | 저장 | 규모(추정) | 이유 |
|---|---|---|---|
| raw | GCS Parquet (스냅샷 폴더) | 스냅샷당 5~8 GB | BigQuery 재과금 없이 재처리. 팀 공유 계약 |
| fact | `dependents_span`, `versions`, `projects` Parquet | span 1.5~2.5억 행 / 5~10 GB | Spark·DuckDB가 직접 읽음. RDB에 넣을 이유 없음 |
| serving | PostgreSQL | `dependents_agg(as_of,name,major,n)`·`trend`·`meta`·`downloads`·마이그레이션 쌍 | 수천만 행 이하, 인덱스 조회, FastAPI와 결합 단순 |

PostgreSQL을 바꿀 이유는 아직 없다. 바꿀 조건은 하나 — **팩트 테이블을 사용자가 임의 시점·임의 패키지로 즉석 조회**해야 할 때다. 그 경우 span 팩트를 DuckDB 파일(단일, 읽기 전용)이나 ClickHouse로 서빙하는 쪽이 맞고, 이건 화면 요구가 확정된 뒤 결정하면 된다. 지금 수집 형태(span + 격자 집계)는 어느 쪽으로도 갈 수 있게 열려 있다.

---

## 8. 확정 사항 (2026-09-02 전진님 확정)

| # | 결정 | 확정 |
|---|---|---|
| 1 | `Dependents` 제거, span 재구성 채택 | **채택** |
| 2 | 대표 릴리스 정의 | **Ordinal 누적 최댓값**(deps.dev와 동일) |
| 3 | T3 폐기 시점 백필 | **보류** — 과거 시점 `latest_is_deprecated`는 NULL. 필요 시 월간 격자 114 GiB부터 |
| 4 | `dependents_agg`·`trend` 격자 주기 | **월 1일, 2012-01~** (177점) |
| 5 | downloads | **BigQuery 범위 밖. 별도 대화에서 병렬 수집.** 이 문서의 §5-3 downloads 항목은 참고용 |
| 6 | GCS 버킷 이름·리전 | `oss-shift-a506-raw`, `US` |

확정되면 순서: 콘솔 할당량 설정(전진님) → T0 4쿼리 dry-run 대조 → T0 실행(52.64 GiB) → 행 수·manifest 검증 → T1 백필 루프(44.47 GiB) → Spark span 빌드 → REST API 표본 대조.

---

## 부록 — dry-run 재현

`docs/api & data/dryrun_260902/q*.sql` 11개. 재현 명령(해당 폴더에서):

```bash
bq query --dry_run --use_legacy_sql=false "$(cat q1_dependents.sql)"
```

모든 dry-run은 2026-09-02, 프로젝트 `oss-shift-a506`, 기준 파티션 `DATE(SnapshotAt) = DATE '2026-08-31'`. 실행(과금)한 쿼리는 §1-3 1건(0.95 GiB)과 `Snapshots` 조회 2건(각 10 MB 최소 과금)이다.
