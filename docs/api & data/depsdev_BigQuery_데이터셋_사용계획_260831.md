# deps.dev BigQuery — 데이터셋 사용계획 점검·구체화

작성 2026-08-31 · 대상 OSS Shift · 선행 문서 `docs/설계_마이그레이션쌍_탐지_260831.md`, deps.dev 도입 검증 보고서(2026-08-28)

이 문서가 답하는 것: **받아지는가 / 뭐가 들었는가 / 그중 뭘 쓸 것인가 / 하려는 게 되는가 / 뭘로 만들 것인가.**

---

## 1. 결론

| 질문 | 답 |
|---|---|
| 데이터셋을 받을 수 있는가 | **가능.** 단 이 노트북에 gcloud SDK가 없다. 재설치·인증이 선행 조건 |
| 비용이 감당되는가 | **감당된다.** 검증 때 쓴 쿼리 전부를 합쳐도 BigQuery 월 무료 1 TiB의 **4.0%** |
| 속성이 충분한가 | **충분하다.** 게다가 검증 보고서가 확인한 5개 테이블 말고 **16개 테이블·15개 뷰**가 더 있다 (§4) |
| 우리가 하려는 계산이 되는가 | **핵심 3단계는 오늘 실물로 재확인했다** (§6). 신호 밀도만 여전히 미확정 |
| 계획을 고쳐야 하는가 | **세 군데.** 데이터 계약, publisher 판별 경로, lift 임계값 (§7) |

---

## 2. 오늘 실제로 받은 것

BigQuery 인증이 없는 상태에서 검증 가능한 것부터 받았다. 세 경로 모두 실제로 200이 떨어졌다.

| 경로 | 인증 | 받은 것 | 결과 |
|---|---|---|---|
| 기존 Parquet 반출본 | 불필요 | `data/exports/p8_proof/000000000000.parquet` | 1,000행 · 7컬럼 · 로컬 재읽기 성공 |
| npm 레지스트리 packument | 불필요 | 패키지 233개 전체 버전 이력 (30 MB) | 릴리즈 27,153건 · regular dependency 선언 248,163건 |
| deps.dev REST API v3/v3alpha | 불필요 | 버전 메타 · npm requirements · project 메타 | §4-3 |

npm 표본은 인기도 가중(검색 API 상위)이라 설계 문서의 260개 표본(변경 피드 기반)과 **편향 방향이 반대**다. 두 표본이 같은 방향을 가리키면 그 결론은 표본 성격에 안 흔들린다는 뜻이라 일부러 이렇게 뽑았다.

> 산출물 위치: 스크래치패드의 `packuments/`, `pipeline_probe.py`, `publisher_probe.py`, `probe_api.py`, `size_est.py`. 리포에 넣을지는 §11.

---

## 3. 이용 가능한가

### 3-1. 즉시 걸리는 블로커

검증 보고서 `STATUS.md`는 `C:\Users\SSAFY\google-cloud-sdk`에 SDK 582.0.0이 있다고 기록했지만 **지금 그 경로에 없다.** `%APPDATA%\gcloud` 설정 디렉터리도 없다. 즉 이 노트북은 검증을 수행한 그 환경이 아니거나, 그 뒤 지워졌다.

BigQuery를 다시 쓰려면 순서대로:

1. Google Cloud SDK 재설치
2. `gcloud auth login` — 브라우저 로그인이라 **전진님이 직접** 해야 한다
3. 프로젝트 `circular-gist-499204-v6` 결제 활성 상태 확인 (검증 때 활성화됨)
4. `bq query --dry_run` 으로 스모크

### 3-2. 비용은 문제가 아니다

on-demand 무료 한도는 월 1 TiB다. 검증에서 실제로 청구된 바이트:

| 쿼리 | 처리량 | 무료 한도 대비 |
|---|---|---|
| P4 모집단 프로파일링 | 4.44 GB | 0.40% |
| P5 조인 품질 | 21.17 GB | 1.93% |
| P6 후보 support | 16.36 GB | 1.49% |
| P7 샘플 추출 | 0.74 GB | 0.07% |
| P8 Parquet 반출 | 0.74 GB | 0.07% |
| **합계** | **43.5 GB** | **4.0%** |

1 TiB 안에서 P5급(21 GB) 쿼리를 **51회** 돌릴 수 있다. 초과해도 P5급 1회당 $0.12다. §11 착수 순서의 쿼리 5개는 합쳐서 무료 한도의 10% 언저리다.

**단, 파티션 필터를 빼먹으면 얘기가 다르다.** `PackageVersions`는 12.09 TB / 226 파티션, `NPMRequirements`는 1.18 TB / 34 파티션이다. `Latest` 뷰를 그냥 조회하면 한 방에 무료 한도를 넘긴다. `DATE(SnapshotAt) = DATE '...'` 를 **모든 쿼리에 강제**한다.

### 3-3. BigQuery 없이도 되는 것

deps.dev REST API는 무인증·무과금이다. 오늘 확인한 범위:

- 정답지 5쌍 같은 **특정 패키지 몇 개**의 이력 확인 → API로 충분
- **역방향 의존(누가 X를 쓰는가) 전수 조회** → API로 불가능. BigQuery가 필요한 진짜 이유가 이것이다

---

## 4. 데이터셋에 무엇이 있는가

### 4-1. 검증 범위 밖에 테이블이 더 있다

도입 검증은 `PackageVersions / PackageVersionsLatest / NPMRequirements / NPMRequirementsLatest / Snapshots` 5개만 확인했다. 스모크 쿼리가 이 5개 이름으로 `WHERE ... IN (...)` 필터를 걸었기 때문이지, 이게 전부라서가 아니다.

공식 문서(docs.deps.dev/bigquery/v1) 기준 실제 구성은 **테이블 16개 + Latest 뷰 15개**다. 우리에게 의미 있는 미검증 테이블:

| 테이블 | 왜 중요한가 | 상태 |
|---|---|---|
| **PackageVersionToProject** | 패키지 버전 → GitHub 저장소. 설계 5단계 publisher 판별의 정식 경로 | 스키마 미검증 |
| **Projects** | StarsCount · ForksCount · OpenIssuesCount · Licenses. 군집 속성이자 화면 근거 | 스키마 미검증 |
| **Dependents** | 역방향 의존. `MinimumDepth=1`이 직접 채택자 | 크기 미측정 |
| Advisories | 보안 권고. 이탈 원인 후보 | V1 범위 밖 |
| DependencyGraphEdges | 해석된 전이 의존 그래프 | V1 범위 밖 |

`Dependents`가 있으면 "moment 채택자 42,196개"를 우리가 직접 계산하지 않아도 된다. 다만 이건 **해석된 그래프** 기준이라 우리의 **선언 기준** 계산과 숫자가 다를 수 있다. 섞지 말고 교차검증용으로만 쓴다.

### 4-2. 확정된 스키마 (라이브 검증 완료)

**`PackageVersions`** — 21,076,530,493행 / 12.09 TB / 226 파티션 / `SnapshotAt` DAY 파티션 / `(System, Name)` 클러스터

```
SnapshotAt TIMESTAMP*        System STRING*            Name STRING*
Version STRING*              Licenses STRING[]         Links[{Label, URL}]
Advisories[{Source, SourceID}]                         VersionInfo{IsRelease BOOL*, Ordinal INT*}
Hashes[{Type, Hash}]         DependenciesProcessed BOOL  DependencyError BOOL
UpstreamPublishedAt TIMESTAMP                          Registries STRING[]
SLSAProvenance{SourceRepository, Commit, URL, Verified}
UpstreamIdentifiers[{PackageName, VersionString, Source}]
Purl STRING                  Attestations[{URL, Type, SourceRepository, Commit, Verified}]
Description STRING           Deprecated STRING         ProjectStatus STRING   ProjectStatusReason STRING
```

**`NPMRequirements`** — 2,427,716,519행 / 1.18 TB / 34 파티션 / `SnapshotAt` DAY 파티션 / `(Name, Version)` 클러스터

```
SnapshotAt TIMESTAMP*   Name STRING*   Version STRING*
Dependencies[{Name*, Requirement*}]          ← V1 분석 대상
DevDependencies[...]     OptionalDependencies[...]     PeerDependencies[...]
BundledDependencies STRING[]                 PeerDependencyMetadata[{Name, Optional}]
Bundles[{Path, Name, Version, Dependencies[...], ...}]
OS STRING[]              CPU STRING[]
```

### 4-3. REST API에만 있는 것

BigQuery `Projects` 테이블에는 **OSSF Scorecard 컬럼이 없다**(문서 기준). REST API에는 있다 — 오늘 `moment` 조회 결과:

```
starsCount 47914 · forksCount 6974 · openIssuesCount 106 · license MIT
scorecard.checks[] → Security-Policy 10, Code-Review 3, Maintained ...
```

Scorecard를 군집 속성으로 쓰려면 **비교군 패키지 수십 개에 한해 API로 별도 수집**해야 한다. 전수는 불가능하다.

---

## 5. 어떤 속성을 쓸 것인가

### 5-1. 파이프라인 단계별 매핑

| 단계 | 테이블 | 쓰는 컬럼 | 용도 |
|---|---|---|---|
| **0. 입력 고정** | PackageVersions | `System`, `SnapshotAt` | `'NPM'` · 스냅샷 1일 고정 |
| | | `VersionInfo.IsRelease` | prerelease 제외 |
| | | `UpstreamPublishedAt` | NULL 6,944,086행 제외 |
| | | `DependencyError` | TRUE 1,985,157행 — 제외 아닌 **플래그**로 보존 |
| | | `Deprecated` | 폐기 패키지 표시 |
| **1. 라인별 시퀀스** ★ | PackageVersions | `Name`, `Version` | 정규식으로 major/minor 파싱 → 라인 |
| | | `UpstreamPublishedAt` | **정렬 키.** Ordinal 아님 |
| | | `VersionInfo.Ordinal` | 정렬엔 안 씀. **시간역전 측정용 검증 컬럼** |
| **2. 의존성 차이** | NPMRequirements | `Dependencies.Name` | removed/added 계산 |
| | | `Dependencies.Requirement` | 원문 보존. 파싱은 후속 |
| | | `PeerDependencies.Name` ★ | **재분류 판정용** (§7-1) |
| | | `OptionalDependencies.Name` ★ | 동일 |
| **3~4. 표 분배·lift** | — | 계산값 | — |
| **5. publisher 묶기** | PackageVersionToProject | `ProjectName`, `ProjectType`, `RelationType` | 1순위 판별 |
| | PackageVersions | `Links[].URL` | 2순위 (위가 비었을 때) |
| | — | `Name` 의 `@scope` | 3순위 |
| **6~7. 후보군·집계** | — | 계산값 | — |
| **화면 근거** | Projects | `StarsCount`, `ForksCount`, `OpenIssuesCount`, `Licenses` | 군집 속성 · 표시용 |

★ = 급소. 여기가 틀리면 뒤가 전부 오염된다.

### 5-2. 반출 스키마 (Spark 입력)

P8에서 검증된 7컬럼에 3개를 더한다.

```
package_name  package_version  upstream_published_at  version_ordinal
dependency_name  dependency_requirement  source_snapshot_date        ← 기존 7 (검증됨)
dep_kind        ← 'regular' | 'peer' | 'optional'   (§7-1 때문에 추가)
project_name    ← publisher 판별용                   (미검증)
dependency_error ← 품질 플래그
```

경로: `oss_shift/snapshot_date=YYYY-MM-DD/system=NPM/*.parquet`

### 5-3. 안 쓰는 것과 이유

| 컬럼 | 왜 안 쓰나 |
|---|---|
| `DevDependencies` | 개발 도구 선택은 런타임 채택과 다른 질문. V1 범위 밖 |
| `BundledDependencies`, `Bundles` | 번들 내부 선언은 채택 의사로 못 본다 |
| `Hashes`, `Purl`, `Attestations`, `SLSAProvenance` | 공급망 신뢰 신호. 우리 질문과 무관 |
| `OS`, `CPU` | 플랫폼 제약. 무관 |
| `Advisories` | 이탈 원인 후보지만 인과 주장으로 번지기 쉽다. V2 |
| `VersionInfo.Ordinal` (정렬 용도) | **의도적 배제.** semver 순서라 시간 역전이 생긴다 (§6-1) |

---

## 6. 하려는 게 가능한가 — 오늘 실측

227개 패키지 · 릴리즈 27,149건에 파이프라인 1~4단계를 그대로 돌렸다.

### 6-1. 정렬 방식이 결과를 바꾸는가 → **바꾼다**

| 정렬 | 전이 | 시간역전 | 변경 있는 전이 | 제거+추가 |
|---|---|---|---|---|
| 순진 (semver 순) | 26,922 | 304 (1.13%) | 1,683 | 401 |
| 라인별 + 발행시각 순 | 24,495 | 0 | 1,250 | 249 |

**순진 정렬이 변경을 34.6% 더 만든다.** 설계 문서의 260개 표본에선 52%였다. 편향 방향이 반대인 두 표본이 같은 방향·같은 자릿수를 냈다. 1단계 설계는 **표본 성격과 무관하게 필요하다**로 봐도 된다.

### 6-2. peer/optional 함정의 규모 → **제거의 5.5%**

제거로 판정된 960건 중 **53건**이 다음 버전의 `peerDependencies`/`optionalDependencies`에 그대로 있었다. 버려진 게 아니라 자리를 옮긴 것이다.

18건 중 1건이 가짜 제거다. 그리고 이건 무작위로 흩어지지 않는다 — 라이브러리가 성숙할 때 하는 정리라 **인기 패키지에 몰린다.** 화면에 크게 나오는 쪽이 정확히 오염되는 위치다.

### 6-3. 신호 밀도 → **여전히 미확정**

| 표본 | 변경 있는 전이 | 제거+추가 |
|---|---|---|
| 설계 문서 (변경 피드, 260개) | 1.7% | 0.22% |
| 오늘 (인기도 가중, 227개) | **5.10%** | **1.02%** |

**5배 차이 난다.** 두 표본 모두 편향돼 있고 진짜 값은 그 사이 어딘가다. 전체 규모로 환산하면 교체 이벤트가 10만~50만 건인데, 이 폭으로는 화면을 설계할 수 없다. **BigQuery 쿼리 1회로 확정해야 한다.**

### 6-4. lift 필터가 작동하는가 → **임계값을 정해야 작동한다**

표 ≥ 1.0 으로 후보를 뽑았더니 **상위 15개가 전부 lift 451배 동률**이었다. 전부 "X 제거 1회, Y 추가 1회"인 단발 쌍이라 A = 1/1 로 계산되고 B만 남기 때문이다.

```
lift 451.0  yargs → meow                       표 1.0  (X제거 1회)
lift 451.0  xregexp → array.prototype.flatmap  표 1.0  (X제거 1회)
lift 451.0  tslint → tslib                     표 1.0  (X제거 1회)
```

**lift 하나로는 못 거른다.** `제거 이벤트 ≥ k` 를 먼저 통과시킨 다음 lift를 재는 순서여야 한다. k는 §11의 밀도 쿼리 결과를 보고 정한다.

### 6-5. 정답지가 나왔는가 → **표본 부족, 예상대로**

`moment` 제거 0회 / `request` 제거 3회 / `node-sass`·`enzyme` 0회. 설계 문서 2-4의 진단이 맞다. 227개로는 안 나오는 게 정상이고, 전체 규모에선 표본이 아니라 전수라 이 문제가 사라진다.

### 6-6. publisher 판별 커버리지

233개 표본 기준:

| 판별 키 | 커버리지 | 묶은 결과 |
|---|---|---|
| `@scope` 이름 | 52% | — |
| 저장소 URL | 98% | 173곳 (상위: DefinitelyTyped 8, react 7) |
| maintainer | 100% | 176곳 |

설계 문서는 `@scope` 78%(변경 피드 기준)라 했는데 여기선 52%다. **표본에 따라 26%p 흔들린다.** 저장소 URL이 98%로 훨씬 안정적이다.

문제는 **maintainer는 BigQuery에 없다는 것**이다 (§4-2 스키마에 없음). 저장소 URL은 `PackageVersionToProject.ProjectName` 또는 `Links[].URL`로 가야 하는데 둘 다 미검증이다. → §11 쿼리 6번으로 추가.

---

## 7. 계획을 고쳐야 하는 세 군데

### 7-1. 데이터 계약 V1 수정 (필수)

현재 `docs/data_contract_v1.md`는 non-regular 배열을 **아예 제외**한다. 그러면 §6-2의 5.5%를 구분할 방법이 없다.

```diff
  ## Excluded
- - [DESIGN] PeerDependencies.
- - [DESIGN] OptionalDependencies.
+ ## Read-for-adjudication (not analyzed)
+ - [DESIGN] PeerDependencies / OptionalDependencies 는 분석 대상이 아니지만,
+   제거(REMOVED) 판정을 뒤집기 위해 다음 버전에 한해 읽는다.
+ - [OBSERVED] 260831 표본 실측: 제거 판정 960건 중 53건(5.5%)이 재분류였다.
```

반출 스키마에 `dep_kind` 컬럼이 필요한 이유가 이것이다.

### 7-2. publisher 판별 1순위 교체

`@scope → Links` 가 아니라 **`PackageVersionToProject.ProjectName` → `Links[].URL` → `@scope`** 순으로 바꾼다. 근거는 §6-6. 단 1순위가 미검증이라 §11 쿼리 6으로 커버리지를 먼저 잰다.

### 7-3. lift 필터에 최소 제거 이벤트 선행 조건

`lift ≥ 5` 단독으로는 단발 쌍이 전부 통과한다. 순서를 바꾼다.

```
제거 이벤트 ≥ k  →  표 ≥ m  →  lift ≥ 5
```

k·m은 밀도 쿼리 뒤에 확정한다. **결과를 보고 임계값을 조정하는 건 금지**(데이터 계약)이므로, 밀도 쿼리 결과만 보고 정한 뒤 봉인한다.

---

## 8. 추출 규모

| 릴리즈당 평균 의존성 | dependency 행 | Parquet (30~60 B/행) |
|---|---|---|
| 4개 | 142 M | 4.3 ~ 8.5 GB |
| 6.5개 | 230 M | 6.9 ~ 13.8 GB |
| 9개 (오늘 표본 실측 9.14) | 319 M | 9.6 ~ 19.1 GB |

기준: 검증 보고서 실측 `Dependencies` 비어있지 않은 릴리즈 35,440,207건. 표본 평균 9.14는 인기도 가중이라 과대추정 쪽이고, 전체 p50이 2인 걸 감안하면 **실제는 4~6.5 구간**일 가능성이 높다.

**5~15 GB면 노트북 한 대에서도 돌아간다.** 분산이 필요한 건 데이터가 안 들어가서가 아니라 셔플·스큐를 실증해야 해서다. 그건 과제 요건이지 규모 요건이 아니다 — 발표에서 그렇게 말하면 안 된다. 대신 **hot key 스큐**(패키지 하나가 릴리즈 37,328건, 의존성 하나가 채택자 수만 개)가 진짜 분산 문제이고, 이건 실제로 존재한다.

---

## 9. 라이브러리

| 구간 | 선택 | 이유 |
|---|---|---|
| 추출 | **google-cloud-sdk** (`bq`, `gcloud storage`) | 검증 때 쓴 경로 그대로. dry-run·`maximum_bytes_billed`가 CLI 플래그로 있다 |
| 추출(코드화 시) | `google-cloud-bigquery` + `google-cloud-bigquery-storage` | GCS 버킷 없이 직접 스트림 다운로드. 반복 자동화 단계에서 검토 |
| 저장 포맷 | **Parquet (snappy)** | P8/P9에서 타입·행수 보존 검증 완료 |
| 분산 계산 | **PySpark 4.0.x** | 이 노트북 Java 21 확인됨. Spark 3.5는 Java 8/11/17까지라 JDK 17을 따로 깔아야 한다 |
| semver 파싱 | **Spark SQL `regexp_extract`** | UDF 금지. 라인 계산은 정규식 3개로 끝나고, UDF는 직렬화 비용만 낸다 |
| 로컬 검증 | **DuckDB** + **pyarrow** | 오늘 설치·동작 확인. Parquet 반출본 즉시 질의 |
| requirement range 해석 | 지금은 불필요 | V1은 원문 보존. 필요해지면 `node-semver`(PyPI) 또는 `semver4j`(JVM) |
| 서빙 | PostgreSQL + FastAPI | 기획서 8절 그대로. 요약값만 적재 |
| 수집(보조) | `requests` + `ThreadPoolExecutor` | 오늘 233개 packument를 이걸로 받았다. 정답지 검증엔 이 경로면 충분 |
| 검증 하네스 | `pytest` + 골든셋 5쌍 | §6-5 정답지를 회귀 테스트로 고정 |
| AI (선택) | `anthropic` SDK · `claude-opus-5` | 결과 해석 문장 생성용. 설계 6단계로 코호트 자동구성 의존도는 이미 낮아졌다 |

**넣지 않는 것**: FP-Growth 등 장바구니 분석. 설계 문서 4단계 주석대로 "X를 뺀 사람이 뭘 넣었나"는 X를 이미 아는 질문이라 조건부 비율이 더 단순하고 통제 가능하다. 모르는 쌍 발굴이 필요해지면 그때 별도로 붙인다.

---

## 10. 착수 순서 (갱신)

설계 문서 8절의 5개에 1개를 더하고 순서를 조정했다.

| 순 | 할 일 | 왜 | 상태 |
|---|---|---|---|
| 0 | gcloud SDK 재설치 + `gcloud auth login` | **전진님 직접 필요** | 블로커 |
| 1 | 연속 버전 쌍 시간 역전 비율 | 1단계 설계 근거 | 표본 2개로 방향 확인됨 → 확정만 |
| 2 | **신호 밀도 실측** | 5배 폭. 여기부터 화면이 정해진다 | **최우선** |
| 3 | peer/optional 재분류 비율 | §6-2를 전수로 확정 | 표본 5.5% |
| 4 | **publisher 커버리지** (신규) | `PackageVersionToProject` 조인률 | 미검증 |
| 5 | 정답지 5쌍 재현 | 파이프라인 검증 | — |
| 6 | 주체 묶기 전후 비교 | 부풀림 규모 | — |

쿼리 6개 합계는 무료 1 TiB의 10% 안팎으로 예상된다.

**2번 전에 임계값(k·m)을 정하지 않는다.** 밀도를 모르는 채로 정하면 결과를 보고 맞춘 셈이 된다.

---

## 11. 아직 모르는 것

- `PackageVersionToProject` · `Projects` · `Dependents` 의 실제 스키마·크기·조인 커버리지. 문서만 봤고 라이브 확인 안 했다
- 전체 규모 반출의 실제 시간과 GCS 비용
- 신호 밀도 (§6-3)
- lift 임계값 k·m
- 오늘 만든 표본 데이터·스크립트를 리포에 넣을지 — `.gitignore`가 `/data/`를 통째로 제외하므로, 넣는다면 스크립트만 별도 경로로

---

## 부록 — 근거

- BigQuery 스키마·행수·파티션: 도입 검증 보고서 evidence (`P3_11`, `P3_12`, 2026-08-24 스냅샷)
- 테이블 16 + 뷰 15 구성: docs.deps.dev/bigquery/v1 (2026-08-31 확인)
- 쿼리 처리 바이트: 검증 보고서 job metadata 실측
- §6 전체 수치: 2026-08-31 npm 레지스트리 233패키지 표본 실행 결과. 인증 없음, 재현 가능
- Spark/Java 호환: Spark 4.0은 Java 17/21, Spark 3.5는 Java 8/11/17
- §6-4 lift 451배는 **실측**이다 (설계 문서의 78배·1.1배는 설명용 가상 수치)
