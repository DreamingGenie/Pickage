# AI 학습 1차 후보 속성 — 마이그레이션 이동쌍 · dependencies · peerDependencies

작성 2026-09-08 · 대상 Pickage 유사 패키지 후보 모델(description + keywords 임베딩)의 **보강 변수** · 원천 deps.dev BigQuery 2026-08-31 스냅샷(로컬 Parquet)
선행 `../deprecated_replacement_260831/README.md`(학습쌍 28,241건), `../../docs/설계_마이그레이션쌍_탐지_260831.md`(이동쌍 계산 설계), `../../docs/Pickage_기능별_개발_구상안_0904.md` §4.2(재랭킹 규칙)

## 0. 왜 이 세 가지인가

폐기→대체 학습쌍 28,241건을 대조하면 description이 완전히 같은 쌍이 34%(9,571건), 이름에 공통 토큰이 있는 쌍이 56%, 소스 저장소가 같은 쌍이 28%다. 절반 이상이 이름 변경(리네임)이라, description만으로 학습하면 모델은 "설명이 거의 같은 패키지를 찾아라"를 배우고 `moment → dayjs`처럼 **설명이 다른 기능적 대체**에서 약해진다. 세 후보는 모두 description과 독립적인 정보원이며, 이미 로컬에 있는 Parquet에서 추가 수집 없이 나온다.

| 후보 | 담고 있는 정보 | 모델에서의 역할 | description과의 독립성 |
|---|---|---|---|
| 마이그레이션 이동쌍 | "X를 뺀 배포 주체가 실제로 무엇을 넣었나" | **정답 라벨**(기능적 대체 positive) + 재랭킹 `move_lift` | 완전 독립. 설명 문구를 전혀 보지 않음 |
| dependencies 목록 | 패키지가 무엇 위에 만들어졌나 | 임베딩 입력 보강(같은 하위 라이브러리 = 같은 문제 영역) | 독립. 복붙 설명·빈 설명에서도 존재 |
| peerDependencies 목록 | 어느 프레임워크·런타임 위에서만 동작하나 | **호환성 필터**(react 대체가 vue면 탈락) | 독립 |

## 1. 후보별 정리

### 1-1. 마이그레이션 이동쌍

**정보**: 어떤 패키지(dependent)가 릴리스 A에서 B로 넘어가며 의존성 X를 **제거**하고 Y를 **추가**했다는 사건. 이것을 X별로 모아 "X를 뺀 전이 중 Y를 넣은 비율"을 전체 평균과 나눈 배수(lift)로 우연을 걸러낸다. 관리자가 폐기 문구에 대체재를 적지 않은 `moment`, `request`류가 여기서만 잡힌다.

**원천**: 저장된 테이블이 아니라 **계산 산출물**이다.

| 입력 | 로컬 위치 | 쓰는 컬럼 |
|---|---|---|
| `deps_dev_v1.NPMRequirements` | `data/raw/requirements` (790 파일, 6.7 GB) | `Name`, `Version`, `Dependencies[].Name` (regular만. peer/optional은 분석에서 제외) |
| `deps_dev_v1.PackageVersions` | `data/raw/versions_full` (4.5 GB) | `Name`, `Version`, `is_release`, `published_at`(=UpstreamPublishedAt), `source_repo`(publisher 판별) |

계산 절차는 설계 문서 0~4단계 그대로다. 라인(major, 0.x는 0.minor) 안에서 발행시각 순으로 세우고, 연속 릴리스의 의존성 차집합을 구해 removed/added를 만든다. 제거 1건이 가진 1표를 추가 개수로 나눈다.

**후보인 이유**: 실측이 설계를 뒷받침한다. 이번 계산(대표 63개 패키지의 채택자 209만 개, 릴리스 1,903만 행, 전이 1,685만 건, 제거 이벤트 55,068건)에서 유명 사례가 전부 나왔다.

| from | to | 표 | 배포주체·월 | A: X 제거 중 Y 추가 | B: 전체 중 Y 추가 | lift |
|---|---|---:|---:|---:|---:|---:|
| moment | dayjs | 347.5 | 385 | 20.1% | 0.02% | 857 |
| moment | date-fns | 166.7 | 205 | 10.4% | 0.03% | 415 |
| moment | luxon | 91.9 | 98 | 5.2% | 0.01% | 1,013 |
| request | axios | 583.8 | 664 | 25.6% | 0.15% | 172 |
| request | node-fetch | 285.0 | 356 | 13.5% | 0.05% | 300 |
| request | got | 150.2 | 198 | 7.2% | 0.01% | 853 |
| node-sass | sass | 382.1 | 452 | 40.6% | 0.02% | 2,626 |
| jade | pug | 70.9 | 94 | 51.4% | 0.00% | 16,774 |
| gulp-util | plugin-error | 224.0 | 336 | 62.9% | 0.00% | 25,723 |
| @hapi/joi | joi | 214.6 | 197 | 74.0% | 0.01% | 10,285 |
| chalk | picocolors | 242.9 | 248 | 10.9% | 0.01% | 1,858 |
| underscore | lodash | 487.1 | 568 | 56.5% | 0.17% | 335 |

`moment → dayjs`는 관리자가 폐기 문구에 대체재를 적지 않아 폐기쌍 데이터셋에 존재하지 않는다. 두 설명도 "Parse, validate, manipulate, and display dates"와 "2KB immutable date time library alternative to Moment.js…"로 문장이 다르다. 반대로 `axios → lodash`(lift 9.5, A 1.6%)처럼 "요즘 다 넣는 것"은 lift 하한과 A 하한으로 걸러진다.

**주의**: 이번 lift의 분모 B는 npm 전수가 아니라 위 209만 개 모집단의 전이다. 전수 계산 시 절대값은 바뀌지만 순위는 유지될 것으로 본다. 설계 문서 5단계(배포주체 묶기)는 `publisher_months` 열로 근사만 했다.

→ **전수 계산 완료(2026-09-08)**: X 제한 없이 npm 전체를 돌린 결과가 `../migration_pairs_260908/`에 있다(strict 1,195쌍 / X 782개, loose 16,839쌍 / X 7,145개, 이벤트 65.7만 건). 이후 라벨 작업은 그쪽 파일을 쓴다.

### 1-2. dependencies 목록

**정보**: 패키지의 최신 릴리스가 `package.json` `dependencies`에 선언한 하위 패키지 이름과 버전 범위. "무엇으로 만들어졌나"를 드러내며, 같은 문제를 푸는 패키지는 하위 도구를 공유하는 경향이 있다(HTTP 클라이언트끼리 `form-data`, CLI끼리 `commander`·`chalk`).

**원천**: `deps_dev_v1.NPMRequirements` → `data/raw/requirements`

| 컬럼 | 타입 | 뜻 |
|---|---|---|
| `Name`, `Version` | string | 패키지·버전 |
| `Dependencies` | `STRUCT(Name, Requirement)[]` | regular 의존성. `Requirement`는 `^1.2.0` 같은 semver 범위 원문 |
| `OptionalDependencies` | 같은 구조 | 선택 의존성. 1차 후보에서는 제외 |

최신 릴리스 선택은 `versions_full`에서 `is_release AND ordinal 최대`로 한다. 서빙 ERD에는 `version.dependency`(JSON)로 이미 자리가 있다.

**후보인 이유**: 학습쌍 28,024건 중 양쪽 다 의존성이 있는 16,839건에서 의존성 자카드 0.5 초과가 6,745건(40%)이다. description 문자 집합 자카드 0.5 미만인 쌍에서도 절반가량 공유 의존성이 있어, 설명이 비었거나 조직 단위로 복붙된 경우(xyo 계열 316건)를 구분해 준다. 임베딩 입력 텍스트에 의존성 이름을 이어 붙이는 것만으로 쓸 수 있고 별도 모델이 필요 없다.

**주의**: 의존성이 0개인 패키지가 학습쌍 기준 34%(9,583건)다. 결손 시 description으로만 돌아가는 폴백이 필요하다. 유틸리티 계열(`tslib`, `lodash`)은 도메인과 무관하게 흔해 IDF 가중을 권한다.

### 1-3. peerDependencies 목록

**정보**: 패키지가 **자기 것으로 설치하지 않고 사용자 프로젝트에 이미 있어야 한다고 요구하는** 패키지. 플러그인·컴포넌트·어댑터가 어느 호스트(react, vue, @angular/core, eslint, webpack, typescript) 위에서 동작하는지를 선언한다. 사실상 "생태계 소속" 표지다.

**원천**: `deps_dev_v1.NPMRequirements` → `data/raw/requirements`, 컬럼 `PeerDependencies` (`STRUCT(Name, Requirement)[]`). 최신 릴리스 선택 방식은 1-2와 같다.

전체 `req` 표본에서 peer로 가장 많이 등장하는 이름: react 4,511 · react-dom 2,429 · @angular/core 729 · zod 686 · eslint 661 · typescript 582 · @angular/common 574 · vue 519 · @opentelemetry/api 479 · react-native 455.

**후보인 이유**: 폐기 패키지에 peer가 있는 학습쌍 7,283건 중 대체재와 peer가 겹치는 것이 5,827건(80%), 겹치지 않는 것이 436건(6%), 대체재에 peer가 없는 것이 1,020건(14%)이다. 즉 대체재는 거의 항상 같은 호스트 위에 있다. description이 "date picker component"로 같아도 react용과 vue용은 서로 대체가 아니므로, 유사도 점수와 별개로 **hard filter 또는 강한 감점**으로 쓰는 것이 맞다. 설계 문서 5-1이 지적한 "peerDependencies 함정"(이동 분석에서 peer를 regular와 섞으면 오탐)과도 일관된다.

**주의**: peer가 없는 패키지가 다수라 필터는 "양쪽 다 peer가 있을 때만" 적용한다. `Requirement` 범위(`react@>=15` vs `react@^18`)까지 맞출지는 2차 문제다.

## 2. 예시 CSV (AI 팀원 공유용)

전부 UTF-8 BOM, 배열은 `|`로 이어 붙임. 생성 스크립트 `pipeline/duckdb/build_feature_candidates.py`(약 8분, `data/feature_candidates.duckdb`에 중간 결과 저장). 난수 시드 고정(0.42)이라 재생성 시 같은 행이 나온다.

### 2-1. `migration_pairs_100.csv` — 이동쌍 집계 100건

필터 `lift ≥ 5 AND votes ≥ 12 AND publisher_months ≥ 10 AND A ≥ 3%`를 통과한 118쌍 중 표 순 상위 100. 각 행에 대표 이벤트 1건을 붙였다.

| 열 | 뜻 |
|---|---|
| `from_pkg`, `to_pkg` | 제거된 X, 추가된 Y |
| `votes` | 표 합계. 제거 1건 = 1표를 추가 개수로 나눠 배분 |
| `co_events` | X 제거와 Y 추가가 같은 전이에서 일어난 횟수 |
| `removal_events` | X 제거 이벤트 총수(추가가 있는 것만) |
| `publisher_months` | (배포주체, 월) 고유 조합 수. 한 조직의 대량 일괄 변경을 눌러 주는 근사 |
| `a_pct` | A: X 제거 전이 중 Y 추가 비율(%) |
| `b_pct` | B: 모집단 전체 전이 중 Y 추가 비율(%) |
| `lift` | A / B |
| `example_*` | 그 쌍을 만든 실제 전이 하나(dependent, 버전 전후, 발행일) |

### 2-2. `migration_events_100.csv` — 이동 이벤트 원시 100건

대표 20개 X에 대해 각 5건, 추가 개수가 적은 깔끔한 전이 우선. 모델이 실제로 소비하는 최소 단위의 형태를 보여 주기 위한 파일이다.

| 열 | 뜻 |
|---|---|
| `dependent` | 의존성을 바꾼 패키지 |
| `publisher` | 배포 주체. `@scope` → 스코프명, 아니면 저장소 URL, 둘 다 없으면 패키지명 |
| `line` | 릴리스 라인(`2`, `0.3` 등). 이 안에서만 전후를 비교 |
| `from_version` → `to_version`, `to_published_at` | 전이 전후 버전과 후 버전 발행시각(UTC) |
| `removed_pkg` | 제거된 X |
| `added_pkgs`, `added_count` | 같은 전이에서 추가된 것 전부와 개수 |
| `vote_each` | 1 / added_count |

### 2-3a. `dependencies_per_package_100.csv` — 패키지 1개당 1행, 학습 입력 형태 100건

모델이 실제로 받는 형태다. 열 6개.

| 열 | 뜻 |
|---|---|
| `package`, `version` | 패키지와 최신 릴리스 버전 |
| `description` | 설명 원문 (기존 변수) |
| `dependencies` | **의존성 정보.** regular dependencies 패키지 이름을 `\|`로 이어 붙임. 임베딩 입력에 description 뒤로 이어 붙이면 됨 |
| `dependency_count` | 개수 |
| `peer_dependencies` | peer 이름. 비어 있으면 호스트 요구 없음 |

### 2-3b. `dependencies_100.csv` — 폐기·대체 쌍의 의존성 목록 100건 (평가·검증용)

2-3a의 행 두 개(폐기 패키지, 대체 패키지)를 한 줄에 나란히 놓고 겹침을 계산한 **비교용** 파일이다. 학습 입력이 아니라 "의존성이 정답쌍을 얼마나 설명하나"를 눈으로 확인하는 용도. 의존성 정보는 `deprecated_dependencies`·`replacement_dependencies` 두 열이고 나머지는 비교 지표다.

양쪽 다 의존성 2개 이상, 대체재 생존. **description 문자 집합 자카드 0.5 미만 50건 + 0.5 이상 50건**으로 층화했다. 앞쪽 50건이 "설명은 다른데 의존성이 말해 주는" 사례다(50건 중 공유 의존성 있음 35건, 의존성 자카드 0.3 초과 16건).

| 열 | 뜻 |
|---|---|
| `deprecated_pkg`, `deprecated_version` / `replacement_pkg`, `replacement_version` | 쌍과 각 최신 릴리스 |
| `deprecated_dependencies`, `replacement_dependencies` | `이름@범위`를 `\|`로 이어 붙임 |
| `n_dep_a`, `n_dep_b` | 각 의존성 개수 |
| `shared_dependencies`, `dep_jaccard` | 공유 의존성과 자카드 |
| `desc_jaccard` | description **문자 집합** 자카드(DuckDB `jaccard`). 단어가 아니라 쓰인 문자의 집합을 비교하므로 거친 근사이며 완전 동일이면 1. 빈 설명은 0. 층화 기준으로만 쓰고 모델 지표로는 쓰지 말 것 |
| `deprecated_description`, `replacement_description` | 비교용 원문 |

### 2-4. `peer_dependencies_100.csv` — 폐기·대체 쌍의 peer 목록 100건

폐기 패키지에 peer 1개 이상, 대체재 생존, 무작위 100건. 표본 분포: match 83 · replacement_has_no_peer 9 · mismatch 8.

| 열 | 뜻 |
|---|---|
| `deprecated_peer_dependencies`, `replacement_peer_dependencies` | `이름@범위`를 `\|`로 이어 붙임 |
| `shared_peers`, `n_peer_a`, `n_peer_b` | 공유 peer와 개수 |
| `peer_match` | `match` 겹침 / `mismatch` 양쪽 다 있는데 안 겹침 / `replacement_has_no_peer` |
| 나머지 | 2-3과 동일 |

`mismatch` 사례를 보면 대체재가 상위 패키지로 흡수되며 peer가 바뀐 경우(`@volter-ai-dev/twin-github` → 대체재 peer 없음)가 섞여 있어, mismatch를 무조건 탈락시키기보다 감점으로 두는 편이 안전하다.

## 3. 학습에 넣을 때의 권고

1. **positive 라벨을 두 출처로 구성**: 폐기쌍(리네임 편향) + 이동쌍(기능 대체). 평가는 이동쌍 출처와 description 자카드 0.5 미만 쌍에서 따로 보고한다.
2. **임베딩 입력 텍스트** = description + keywords(ecosyste.ms 수집 후) + regular dependencies 이름 상위 N + peer 이름. 이 순서로 이어 붙이면 모델 교체 없이 변수가 늘어난다.
3. **peer는 임베딩이 아니라 재랭킹 규칙**으로: 양쪽 다 peer가 있고 하나도 안 겹치면 감점. 구상안 §4.2의 감점 항목에 추가하는 형태.
4. **hard negative**: 같은 스코프의 형제 패키지, dependents 교집합 0.3 초과인 보완재, 그리고 이동쌍에서 lift가 5 미만인 (X, Y) 조합.
5. **폐기 문구(`Deprecated`)는 피처에서 제외**. 정답을 뽑아낸 원문이라 라벨이 누출된다.
