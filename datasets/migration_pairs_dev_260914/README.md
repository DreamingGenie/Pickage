# 마이그레이션 이동쌍 — 개발용 의존(devDependencies) 기준

Jira **S15P21A506-349** (상위 스토리 S15P21A506-136) · 계산 2026-09-14 · 원천 npm registry 수집분(S15P21A506-280, run 2026-09-09)

실행용 의존 기준 결과는 [`../migration_pairs_260908/`](../migration_pairs_260908/) 다. **두 폴더의 수치를 더하거나
lift 를 직접 비교하지 말 것** — 모집단이 다르다(§5).

## 0. 이 폴더가 답하는 질문

"테스트·린트·빌드 도구 X 를 쓰던 사람들이 그걸 빼면서 무엇을 넣었나."

기존 결과는 deps.dev `NPMRequirements` 를 원천으로 쓰는데 거기에는 **devDependencies 칸이 없다.** 그래서
`enzyme`·`tslint`·`mocha`·`jest` 같은 도구 계열의 이동이 구조적으로 안 보였다
([`../migration_pairs_260908/README.md`](../migration_pairs_260908/README.md) §4·§5). 이 폴더가 그 빈칸을 채운다.

**정답지 5쌍 중 유일하게 미검출이던 `enzyme → @testing-library/react` 가 여기서는 strict 1위로 잡힌다.**

| from | to | votes | co_events | publisher_months | a_pct | lift |
|---|---|---:|---:|---:|---:|---:|
| enzyme | @testing-library/react | 52.5 | 125 | 110 | 44.8% | 2,010 |
| enzyme | @testing-library/jest-dom | 24.3 | 73 | 70 | 26.2% | 1,634 |
| enzyme | @testing-library/user-event | 13.0 | 32 | 24 | 11.5% | 778 |

## 1. 파일

실행용 의존 결과와 **열 구성이 같다.** 열 의미는 [`../migration_pairs_260908/README.md`](../migration_pairs_260908/README.md) §1 을 그대로 본다.

| 파일 | 내용 |
|---|---|
| `migration_pairs_strict.csv` | lift≥5, votes≥12, publisher_months≥10, A≥3% — 766쌍 / 출발 305개 |
| `migration_pairs_recommended.csv` | lift≥5, votes≥8, publisher_months≥5, share≥10% — 506쌍 / 출발 376개 |
| `migration_pairs_all.csv` | lift≥5, votes≥3 — 6,770쌍 / 출발 1,603개 |
| `removal_stats.csv` | X별 이탈 요약 (제거 3건 이상 8,959개) |
| `removal_by_year.csv` | X × 연도 이탈 추이 |
| `stats.json` | 규모 통계. `source`·`kind`·`reclassify_columns` 로 어떤 조건의 실행인지 확인 |
| `reclassify_effect_*.csv`, `reclassify_effect.json` | §4 — 기존 실행용 의존 결과의 과대 계상 측정 |

원시 이벤트는 `data/migration_pairs_dev/migration_events.parquet` (gitignore).

재현:

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py --source registry --kind dev
```

## 2. 규모

| 단계 | 개발용 의존 | (참고) 실행용 의존 npm 전수 |
|---|---:|---:|
| 릴리스 | 7,908,122 | 47,178,483 |
| 패키지 | 97,733 | 4,065,912 |
| 연속 릴리스 전이 | 7,256,168 | 39,579,244 |
| 전이가 1건 이상 있는 패키지 | 93,288 | 2,494,351 |
| 의존성 변경이 있는 전이 | 254,037 (3.5%) | 1,843,567 (4.7%) |
| 제거·추가가 같은 전이 | 62,845 (0.87%) | 266,905 (0.67%) |
| 다른 의존 칸으로 재분류되어 걸러낸 제거 | 27,732 | 202,554 |
| 제거 전이(추가 여부 무관) | 357,434 | 2,058,952 |
| 제거 이벤트(추가 동반) | 190,665 | 657,023 |
| 이벤트를 만든 dependent | 25,498 | 174,879 |
| 후보 (X, Y) 쌍 (필터 전) | 403,612 | 1,900,453 |

**모집단이 40배 작은데 제거 이벤트는 3.4배밖에 차이 나지 않는다.** 상위 10만은 활발히 관리되는
라이브러리 집단이라 릴리스당 의존 변경이 잦고, 도구 교체 자체가 실행용 의존 교체보다 빈번하다.

## 3. 도구는 버려지는 게 아니라 갈아탄다

X 를 뺀 전이 중 **같은 전이에서 아무것도 넣지 않은 비율**:

| | 대체 없이 제거 |
|---|---:|
| 개발용 의존 (이 폴더) | **46.7%** (166,769 / 357,434) |
| 실행용 의존 (npm 전수) | 68.1% (1,401,929 / 2,058,952) |

실행용 의존은 "언어·런타임에 내장돼 필요가 없어진" 경우(left-pad, node-fetch)가 많아 대체 없이 사라지는 쪽이
다수다. 개발용 의존은 그렇지 않다 — 테스트 프레임워크를 지우면 대개 다른 것을 넣는다. **라벨 데이터로서
신호가 더 진하다는 뜻이다.**

## 4. 부수 소득 — 기존 실행용 의존 결과의 과대 계상

deps.dev 원천에는 dev 칸이 없어, `dependencies`에서 빼고 같은 전이에서 `devDependencies`로 **옮긴** 것을
기존 계산은 전부 '제거'로 센다. registry 수집분에는 두 칸이 다 있으므로 **같은 모집단에서 필터만 바꿔**
두 번 돌려 그 크기를 분리해 쟀다(`pipeline/duckdb/compare_reclassify_effect.py`).

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py --source registry --kind regular --reclassify-legacy
.venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py --source registry --kind regular
.venv-bq/Scripts/python.exe pipeline/duckdb/compare_reclassify_effect.py
```

### 4-1. 제거 통계는 12% 부풀어 있다

| | legacy (현재 방식) | full (dev 칸까지 봄) | 차이 |
|---|---:|---:|---:|
| 제거 전이 | 220,166 | 193,420 | **-26,746 (-12.15%)** |
| 제거된 적 있는 패키지 종류 | 34,960 | 31,602 | -3,358 |
| 제거 이벤트(추가 동반) | 99,157 | 94,719 | -4,438 |

**3,359개 패키지는 '제거'가 전부 dev 이동이었다** — 즉 한 번도 버려진 적이 없는데 이탈 목록에 올라 있었다.

비율이 큰 쪽은 예상대로 도구다. 린터를 `dependencies`에 두었다가 `devDependencies`로 옮기는 건
버리는 게 아니라 **제자리를 찾아 주는 것**인데, 지금 결과는 그걸 이탈로 센다.

| X | legacy 제거 | full 제거 | 재분류 비율 |
|---|---:|---:|---:|
| `eslint` | 231 | 40 | **82.7%** |
| `@types/jest` | 112 | 22 | 80.4% |
| `eslint-config-prettier` | 79 | 16 | 79.7% |
| `jest` | 151 | 34 | 77.5% |
| `@types/react-dom` | 113 | 26 | 77.0% |
| `babel-preset-es2015` | 123 | 47 | 61.8% |
| `vue` | 141 | 54 | 61.7% |

전체 목록은 `reclassify_effect_removals.csv`.

### 4-2. 그런데 쌍 라벨은 거의 안 흔들린다

| | 값 |
|---|---:|
| legacy strict 쌍 | 143 |
| full 에서 **사라진** 쌍 | **0** |
| full 에서 기준 미달로 떨어진 쌍 | **4** |
| 유지 | 139 |

떨어진 4쌍도 하한 언저리에서 1~3표 빠진 것뿐이다.

| 쌍 | votes |
|---|---|
| `@angular/router → tslib` | 14.0 → 11.0 |
| `@angular/http → tslib` | 13.0 → 11.0 |
| `@babel/polyfill → core-js` | 12.9 → 11.9 |
| `mysql → mysql2` | 13.1 → 12.1 |

**이유**: strict 는 "X 를 뺀 **그 전이에서** 다른 패키지 Y 를 넣었다"를 요구한다. `dependencies` →
`devDependencies` 강등은 대개 대체재를 함께 넣지 않으므로 애초에 쌍 집계에 거의 들어오지 않는다.
제거 수(분모)가 줄어 `a_rate`가 오히려 오르는 쌍도 있다.

### 4-3. 그래서 무엇을 고쳐야 하나

**이동쌍 CSV 3종은 그대로 써도 된다.** 팀에 공유된 `../migration_pairs_260908/migration_pairs_*.csv` 의
1,195 strict 쌍은 이 문제로 바뀌지 않는다.

**고쳐야 할 것은 `removal_stats.csv` · `removal_by_year.csv` 와 거기서 나오는 "대체 없이 떠남" 비율이다.**
그 화면(S15P21A506-281 산출물, S15P21A506-136 §2)은 "X 를 뺀 전이 중 아무것도 안 넣은 비율"을 보여 주는데,
`eslint` 처럼 그 '제거'의 83%가 칸 이동인 패키지가 있다. 화면에 그대로 쓰면 **"eslint 를 떠났다"로 읽힌다.**

측정 가능 범위는 이렇다. 기존 depsdev strict 의 출발 패키지 782개 중 746개가 registry 모집단(상위 10만)에
있어 잴 수 있고, 그중 **532개에 재분류가 섞여 있다**(관련 쌍 909개). 나머지 36개와 상위 10만 밖 패키지는
deps.dev 원천에 dev 칸이 없어 **여전히 잴 수 없다** — '영향 없음'이 아니라 '못 잼'이다.

권고: 이탈 관련 화면·API 는 상위 10만에 한해 `reclassify_effect_removals.csv` 의 `full_removals` 를 쓰거나,
최소한 `reclassified_pct` 가 높은 X 에 "상당수가 개발용 의존으로 이동" 표시를 붙인다. 판단은 S15P21A506-211
(근거충분성 필터 기본값)에서 함께 정한다.

## 5. 주의 — 실행용 의존 결과와 섞지 말 것

- **모집단이 다르다.** 이 폴더는 다운로드 순위 **상위 10만**(`datasets/targets/rank_top100k_20260902.csv`),
  실행용 의존 결과는 **npm 전수 406만**이다. 상위 10만 밖의 패키지가 도구를 어떻게 바꿨는지는 알 수 없다.
  화면·발표에서 개발용 의존 기준 수치에는 반드시 "상위 10만 기준"을 붙인다.
- **lift 의 분모(B)가 다르다.** B 는 그 실행의 모집단 전이 중 Y 를 추가한 비율이다. 여기는 726만 전이,
  실행용 의존 결과는 3,958만 전이 기준이다. **두 폴더의 lift 절댓값을 비교하면 안 된다.** 순위·점유율만 비교한다.
- **votes 를 더하지 않는다.** 같은 X 가 양쪽에 있어도(`typescript` 등) 다른 모집단의 다른 사건이다.
  서빙에서는 실행용/개발용을 나눠 보여 주고 합산하지 않는다.
- **스냅샷 시점이 9일 다르다.** registry 는 2026-09-09 수집, deps.dev 는 2026-08-31 스냅샷이다.
- 실행용 의존 결과의 주의사항(양방향 쌍, 동반 추가 잡음, B 의 분모)은 여기에도 그대로 적용된다.
  [`../migration_pairs_260908/README.md`](../migration_pairs_260908/README.md) §5 를 볼 것.

## 6. 계산 규칙에서 달라진 것

실행용 의존 결과와 계산 절차는 같다([`docs/설계_마이그레이션쌍_탐지_260831.md`](../../docs/설계_마이그레이션쌍_탐지_260831.md) 0~4단계). 두 가지만 다르다.

1. **분석 대상 칸이 `DevDependencies` 다.**
2. **재분류 판정이 4방향으로 넓어졌다.** 설계 문서 §5-1 은 "제거로 보이지만 실은 `PeerDependencies`·
   `OptionalDependencies` 로 옮긴 것"을 거르라고 했다. registry 원천에는 dev 칸이 있으므로 여기서는
   **반대쪽 의존 칸도 함께 본다** — 개발용 의존에서 빠졌지만 같은 전이에서 `Dependencies`·`Peer`·`Optional`
   에 나타나면 제거가 아니라 재분류다. 실측 27,732건.

원천 차이에서 오는 구현 차이 두 가지:

- `is_release` 를 쓰지 않고 `NOT contains(Version,'-')` 로 판정한다. 조인 적중 2,039만 행에서 두 규칙의
  **불일치가 0건**이라 동치임을 확인했다(2026-09-14). 조인을 하나 줄인다.
- `source_repo`(publisher 판정용)는 `versions_full` 에서 **패키지 단위**로 붙인다. 버전 단위로 조인하면
  08-31 스냅샷 이후 발행된 20.1만 행(2만 패키지)이 비어 publisher 가 패키지 이름으로 떨어진다.
  저장소 주소는 버전마다 바뀌지 않으므로 `any_value` 로 패키지에 한 번 붙인다(91,582 / 97,733 패키지 적중).
- unpublish 된 버전은 의존을 모르므로(NULL) 제외한다. 넣으면 "의존 전부 제거"로 잡힌다
  ([`docs/api & data/수집계획_devDependencies_npmRegistry_260909.md`](../../docs/api%20&%20data/수집계획_devDependencies_npmRegistry_260909.md) §5-3).

## 7. 참고

- 원천 수집: `pipeline/collectors/registry/README.md`, 계획 `docs/api & data/수집계획_devDependencies_npmRegistry_260909.md`
- 계산 설계: `docs/설계_마이그레이션쌍_탐지_260831.md`
- 실행용 의존 결과·해설: `../migration_pairs_260908/README.md`
- 빌더: `pipeline/duckdb/build_migration_pairs.py`, 대조 분석 `pipeline/duckdb/compare_reclassify_effect.py`
