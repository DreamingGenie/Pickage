# 마이그레이션 이동쌍 — npm 전수 계산 결과

작성 2026-09-08 · 갱신 2026-09-09(§7 이탈 집계·`share_pm_pct` 추가, S15P21A506-281) · 원천 deps.dev BigQuery 2026-08-31 스냅샷(로컬 Parquet `data/raw/requirements`, `data/raw/versions_full`) · 생성 스크립트 `pipeline/duckdb/build_migration_pairs.py`(약 30분, 12스레드·40GB)
선행 `../feature_candidates_260908/README.md` §1-1(63개 대표 패키지 실측), `../../docs/설계_마이그레이션쌍_탐지_260831.md`(계산 설계)

## 0. 이 폴더가 답하는 질문

`../feature_candidates_260908/migration_pairs_100.csv`는 대표 63개 패키지(X)만 보고 뽑은 100건 표본이었다. 여기서는 **X를 제한하지 않고 npm 전체 릴리스 이력을 돌려** 이동쌍을 전부 뽑고, "이동을 알 수 있는 패키지가 몇 개인지", "데이터가 얼마나 되는지"를 확정했다.

계산은 설계 문서 0~4단계와 같다(라인별 발행시각 정렬 → 연속 릴리스 의존성 차집합 → 제거 1표를 추가 개수로 분배 → lift). 63개 실측과 다른 점은 두 가지다.

1. 분모 B가 209만 개 모집단이 아니라 **npm 전수 전이(3,958만 건)** 다. 그래서 lift 절대값은 63개 실측보다 크게 나온다(`moment→dayjs` 857 → 1,398). 순위는 유지됐다.
2. 설계 5-1 반영: 다음 버전의 `PeerDependencies`/`OptionalDependencies`로 옮겨진 이름(20.3만 건)은 제거가 아니라 재분류로 보고 X 후보에서 뺐다.

## 1. 파일

| 파일 | 내용 | 행 | 크기 |
|---|---|---:|---:|
| `migration_pairs_strict.csv` | 필터 `lift≥5 AND votes≥12 AND publisher_months≥10 AND A≥3%` 통과 쌍. 63개 실측과 같은 기준. **모델 positive 라벨용** | 1,195 | 121 KB |
| `migration_pairs_all.csv` | 필터 `lift≥5 AND votes≥3` 통과 쌍 전부. 열이 같으므로 원하는 기준으로 다시 걸러 쓴다 | 16,835 | 1.7 MB |
| `migration_pairs_recommended.csv` | **권고 하한**(§6) `lift≥5 AND votes≥8 AND publisher_months≥5 AND share≥10%` 통과 쌍. 전처리 없이 바로 라벨로 쓰는 파일 | 1,167 | 122 KB |
| `removal_stats.csv` | **X별 이탈 요약**(§7). X를 뺀 전이 총수와 그중 "대체 없이 제거"·"대체 동반 제거" 건수. `removals_total≥3`인 X만 | 47,250 | 2.6 MB |
| `removal_by_year.csv` | X × 연도 이탈 추이(§7). 같은 X 기준 | 183,403 | 4.9 MB |
| `stats.json` | 아래 2·3절 숫자의 원본 | | |
| `data/migration_pairs/migration_events.parquet` (git 미추적) | 제거 이벤트 원시 전부. 모델이 소비하는 최소 단위 | 657,023 | 21 MB |
| `data/migration_pairs/migration_events.csv` (git 미추적) | 같은 내용 CSV | 657,023 | 119 MB |
| `data/migration_pairs/removal_stats.parquet`, `removal_by_year.parquet` (git 미추적) | 위 두 CSV의 필터 없는 전체(X 203,347종) | 203,347 / 352,009 | 4.4 / 2.3 MB |
| `data/migration_pairs.duckdb` (git 미추적) | 중간 테이블(`events`, `pairs`, `pairs_out`, `base`, `removal_stats`, `removal_by_year`). 다른 필터로 다시 뽑을 때 재계산 없이 여기서 쿼리 | | 11.2 GB |

CSV는 UTF-8 BOM. 배열은 `|`로 이어 붙였다.

git 미추적 parquet 3종(`migration_events`, `removal_stats`, `removal_by_year`)은 2026-09-09 서버 MinIO에도 올렸다: `pickage-curated/depsdev/v1/migration-pairs/snapshot=2026-08-31/run_id=migration-pairs-20260909-v1/` (`data/*.parquet`, `run_manifest.json`에 SHA-256·행 수, `_SUCCESS`). 접속은 `pipeline/minio/README.md`의 서버 터널 절차를 따른다. 중간 DB(`data/migration_pairs.duckdb`)는 30분에 재생성되는 중간물이라 올리지 않았다.

### 열 (pairs)

| 열 | 뜻 |
|---|---|
| `from_pkg`, `to_pkg` | 제거된 X, 같은 전이에서 추가된 Y |
| `votes` | 표 합계. 제거 1건 = 1표를 그 전이의 추가 개수로 나눠 배분 |
| `co_events` | X 제거와 Y 추가가 같은 전이에서 일어난 횟수 |
| `removal_events` | X 제거 이벤트 총수(추가가 1개 이상 있는 것만) |
| `publisher_months` | (배포주체, 월) 고유 조합 수. 한 조직의 일괄 변경을 눌러 주는 근사 |
| `dependents` | 이 전환을 한 고유 패키지 수 |
| `a_pct` | A: X 제거 전이 중 Y 추가 비율(%) |
| `b_pct` | B: npm 전수 전이 중 Y 추가 비율(%) |
| `lift` | A / B |
| `share_pct` | X의 전체 표(lift≥5 쌍 합) 중 이 Y가 가진 비율(%). X 하나에 Y가 수십 개 붙는 대형 정리 릴리스 부산물을 거르는 열 |
| `share_pm_pct` | 같은 비율을 표 대신 `publisher_months`로 계산한 것(%). 한 조직의 일괄 변경이 표를 부풀리는 경우를 누른다. **화면 점유율은 이 열 권고**(§7-3) |
| `bidirectional` | (Y, X) 쌍도 lift≥5·votes≥3으로 존재하면 true. lodash↔lodash-es 같은 변종 관계 표시 |
| `first_seen`, `last_seen` | 이 전환이 관측된 첫·마지막 발행일 |

### 열 (removal_stats)

| 열 | 뜻 |
|---|---|
| `removed_pkg` | X |
| `removals_total` | X를 regular 의존성에서 뺀 연속 릴리스 전이 수. **추가 여부 무관** |
| `removals_no_replacement` | 그중 같은 전이에서 새 의존성을 하나도 넣지 않은 수 = "대체 없이 제거" |
| `removals_with_replacement` | 그중 하나 이상 넣은 수. pairs의 `removal_events`와 같다 |
| `no_replacement_pct` | `removals_no_replacement / removals_total` (%) |
| `dependents`, `publisher_months` | X를 뺀 고유 패키지 수, (배포주체, 월) 고유 조합 수 |
| `first_seen`, `last_seen` | 첫·마지막 제거 발행일 |

`removal_by_year`는 `removed_pkg, year, removals, removals_no_replacement, dependents`. 연도는 제거가 일어난 릴리스의 발행 연도.

### 열 (events)

`dependent, publisher, line, from_version, to_version, to_published_at, removed_pkg, added_pkgs, added_count, vote_each` — `feature_candidates_260908/migration_events_100.csv`와 같다.

## 2. 규모

| 단계 | 값 |
|---|---:|
| 릴리스(is_release, 발행시각 있음, `M.m` 형식) | 47,178,483 |
| 패키지 | 4,065,912 |
| 연속 릴리스 전이 | 39,579,244 |
| 전이가 1건 이상 있는 패키지 | 2,494,351 |
| 의존성 변경이 있는 전이 | 1,843,567 (4.7%) |
| 제거·추가가 같은 전이 | 266,905 (0.67%) |
| peer/optional 재분류로 걸러낸 제거 | 202,554 |
| 제거 전이(추가 여부 무관, X 기준 펼침) | 2,058,952 |
| 제거된 적 있는 패키지 종류(추가 여부 무관) | 203,347 |
| 제거 이벤트(추가 동반) | 657,023 |
| 제거된 적 있는 패키지 종류(추가 동반) | 110,130 |
| 이벤트를 만든 dependent 패키지 | 174,879 |
| 후보 (X, Y) 쌍 전부(필터 전) | 1,900,453 |

설계 문서 2-5가 260개 표본으로 추정한 "교체 이벤트 약 10만 건"은 실측 26.7만 전이 / 65.7만 이벤트로, 예상보다 신호가 많았다.

09-09 재실행에서 전이 수는 같았으나 의존성 변경 전이 4건, 제거·추가 동시 전이 10건, 이벤트 14건이 09-08 결과와 달랐다. 같은 라인 안에 발행시각이 같은 릴리스가 있으면 `lag()` 순서가 실행마다 바뀌기 때문이다(`preserve_insertion_order=false`). strict·recommended 쌍 수는 변하지 않았고, 아래 §3·§6 표는 09-08 값이다(차이는 loose 쌍 4건 수준).

## 3. 이동을 알 수 있는 패키지 수

"X를 뺀 사람들이 무엇을 넣었나"를 말할 수 있는 X의 수는 **필터 기준에 따라 800개에서 7,000개 사이**다.

| 필터 | (X, Y) 쌍 | X(출발 패키지) 수 | Y(도착 패키지) 수 |
|---|---:|---:|---:|
| strict: lift≥5, votes≥12, publisher_months≥10, A≥3% | 1,195 | **782** | 554 |
| lift≥5, votes≥12 | 2,491 | 1,172 | |
| lift≥5, votes≥5, publisher_months≥3 | 5,921 | 2,449 | |
| loose: lift≥5, votes≥3 | 16,839 | **7,145** | 5,927 |

X 782개는 절대 수로는 적지만, 채택자 기준으로 보면 크다. `requirements`에서 regular 의존성이 1개 이상인 패키지 6,477,509개(고유 이름 기준) 중 strict X 중 하나라도 의존한 적 있는 패키지가 3,565,925개(55%), loose 기준은 5,182,675개(80%)다. `lodash`, `request`, `moment`, `babel-runtime`처럼 X 자체가 대형 패키지인 까닭이다. 즉 **서비스에서 "당신 프로젝트의 의존성 중 이동 이력이 있는 것"을 보여줄 때, 대부분의 프로젝트가 한 건 이상은 걸린다.**

## 4. 정답지 재현 (설계 문서 6절)

| 정답 쌍 | strict 통과 | votes | lift |
|---|---|---:|---:|
| request → axios / got | ✔ / ✔ | 583.8 / 150.2 | 403 / 2,003 |
| node-sass → sass | ✔ | 382.1 | 4,601 |
| tslint → eslint | ✔ (votes 13.0, 하한 12에 근접) | 13.0 | 1,087 |
| moment → dayjs / date-fns | ✔ / ✔ | 347.4 / 166.5 | 1,398 / 720 |
| enzyme → @testing-library/react | **✘** 미검출 | | |

5쌍 중 4쌍 재현. `enzyme`은 제거 이벤트 96건이 있지만 `@testing-library/react`와 같은 전이에 나온 게 표 3 미만이다. 이유는 enzyme이 대개 `devDependencies`에 있고 deps.dev `NPMRequirements`는 dev 의존성을 담지 않기 때문으로 본다. 테스트·린트·빌드 도구 계열(`tslint`, `mocha`, `jest`, `enzyme`)은 이 데이터에서 구조적으로 약하다.

## 5. 주의

- **양방향 쌍**: `lodash → lodash-es`(1,243표)와 `lodash-es → lodash`(537표)가 둘 다 strict를 통과한다. ESM/CJS 전환처럼 왕복하는 관계다. 라벨로 쓸 때 (X,Y)와 (Y,X)가 모두 있으면 "대체"가 아니라 "변종"으로 따로 다루는 편이 맞다.
- **동반 추가 잡음**: `rxjs → tslib`(lift 729)처럼 X 제거와 무관하게 같은 릴리스에 딸려 들어온 것이 남는다. lift 하한을 높이는 것보다 `dependents`·`publisher_months`가 `co_events`에 비해 작은 쌍(소수 주체의 반복)을 감점하는 쪽이 효과적이다.
- **dev 의존성 부재**: 4절 참고. 도구 계열 마이그레이션은 이 데이터로 말할 수 없다.
- **B의 분모는 전이 수**: 한 전이에서 Y가 여러 번 추가될 수는 없으므로 B는 "전이 중 Y 추가 비율"이다. 63개 실측의 B와 직접 비교하지 말고 lift 순위만 비교한다.
- 설계 5단계(배포주체 묶기)는 여전히 `publisher_months` 열로 근사만 했다. 5·7단계(share 계산, "대체 없이 제거" 비율)는 `data/migration_pairs.duckdb`의 `events` 테이블에서 바로 뽑을 수 있다.

## 6. 전처리 하한 실측 (2026-09-08 추가)

정답지: 폐기→대체 학습쌍 28,241건(관리자가 폐기 문구에 직접 적은 대체재). 이동쌍 X 중 폐기셋에 있는 X는 3,477개.
- **정밀도 근사** = X가 폐기셋에 있는 쌍 중 Y가 선언된 대체재와 같은 비율. 폐기셋은 X당 대체재 1개만 있어 `moment→dayjs`류 기능 대체는 전부 "오답"으로 세어지므로 **하한값**이다.
- **top-1 재현율** = 폐기셋에 있는 X 중, 표 1위 Y가 선언 대체재와 같은 비율.

| 필터 | 쌍 | X | 정밀도 근사(하한) | top-1 재현율 |
|---|---:|---:|---:|---:|
| lift≥5, votes≥3 | 16,839 | 7,145 | 36.6% | 77.0% |
| lift≥5, votes≥5 | 7,708 | 3,470 | 32.4% | 75.9% |
| lift≥5, votes≥12 (publisher_months 없이) | 2,491 | 1,172 | **21.6%** | 69.1% |
| lift≥5, votes≥5, publisher_months≥3 | 5,921 | 2,449 | 50.9% | 78.2% |
| lift≥5, votes≥8, publisher_months≥5 | 2,786 | 1,273 | 61.8% | 82.0% |
| lift≥5, votes≥10, publisher_months≥5 | 2,077 | 1,008 | 63.8% | 82.5% |
| strict (votes≥12, pm≥10, A≥3%) | 1,195 | 782 | 72.7% | 85.4% |
| lift≥5, votes≥30, publisher_months≥15 | 458 | 325 | 80.6% | 86.2% |

**표(votes)만 올리는 것은 효과가 없다.** votes≥12를 걸어도 publisher_months를 안 걸면 정밀도가 21.6%로 가장 나쁘다. 한 조직(`@xylabs`, `@xyo-network`, `material-ui` 모노레포)이 수십 패키지를 한 달에 일괄 변경하면 표는 수백이 되지만 배포주체-월은 5 안팎이다. 하한은 **배포주체-월 기준**으로 잡아야 한다.

`votes≥8, publisher_months≥5, lift≥5`를 기준으로 추가 필터를 얹은 결과(share는 이 필터 안에서의 비율로 계산):

| 추가 필터 | 쌍 | X | 정밀도 근사 | top-1 재현율 | X당 Y 개수 중앙값/최대 |
|---|---:|---:|---:|---:|---:|
| 없음 | 2,786 | 1,273 | 61.8% | 81.2% | 1 / 87 |
| share ≥ 10% (Y가 X 전체 표의 10% 이상) | 1,866 | 1,270 | 69.5% | 81.2% | 1 / 7 |
| share ≥ 20% | 1,546 | 1,248 | 74.3% | 81.2% | 1 / 4 |
| 양방향 쌍 제거 | 1,870 | 1,085 | 65.1% | 80.2% | 1 / 27 |
| share ≥ 10% + 양방향 제거 | 1,354 | 1,039 | 70.7% | 81.5% | 1 / 6 |

`share`는 재현율을 거의 깎지 않고 X당 Y 최대 87개(`aws-sdk` 등 대형 정리 릴리스의 부산물)를 7개로 줄인다. 양방향 제거는 X를 200개 가까이 잃으므로(lodash↔lodash-es 같은 변종 쌍) 삭제보다 `bidirectional` 열로 표시만 하고 라벨 단계에서 "변종"으로 따로 다룬다.

### 권고 하한

CSV의 `share_pct`는 재현 가능하도록 **lift≥5 쌍 전체**(`migration_pairs_all.csv` 모집단) 안에서 계산했다. 위 표의 필터 내 share보다 값이 작게 나오므로 같은 10% 하한에서 쌍이 더 적게 남는다.

| 용도 | 기준 | 규모 | 정밀도 근사 / top-1 재현율 |
|---|---|---:|---:|
| **학습 positive 라벨(기본)** — `migration_pairs_recommended.csv` | lift≥5 · votes≥8 · publisher_months≥5 · share_pct≥10 | 쌍 1,167 / X 1,022 | 73.5% / 81.0% |
| 서비스 노출·발표용(보수) — `migration_pairs_strict.csv` | lift≥5 · votes≥12 · publisher_months≥10 · A≥3% | 쌍 1,195 / X 782 | 72.7% / 85.4% |
| 탐색·hard negative 채굴 — `migration_pairs_all.csv` | lift≥5 · votes≥3 | 쌍 16,839 / X 7,145 | 36.6% / 76.8% |

기본 기준에서 X당 Y는 최대 6개다. 결론: **"일정 횟수"는 표 8회가 아니라 서로 다른 (배포주체, 월) 5개 이상으로 잡는다.** 표 하한은 그 다음 보조 조건이다.

화면에 "X를 떠난 사람의 몇 %가 Y로 갔나"를 보여줄 때는 `share_pct`(표 기준)가 아니라 **`share_pm_pct`(배포주체·월 기준)를 쓰기를 권고**한다. 이유와 실측은 §7-3.

정밀도 근사 60~70%는 하한이며, 오답으로 세어진 상위 사례를 보면 `fs-promise→fs-extra`(선언은 `mz`), `babel-eslint→@babel/core`(선언은 `@babel/eslint-parser`, 함께 설치되는 짝)처럼 실제로는 타당한 이동이 절반쯤 섞여 있다. 남는 진짜 오답은 `@angular/http→tslib`류 동반 추가와 모노레포 내부 재배치다.

## 7. 이탈 — 대체 없이 제거 (2026-09-09 추가, S15P21A506-281)

목표 화면 "X를 떠난 사람들은 어디로 갔나"의 첫 막대는 **대체 없이 떠남**(X를 뺐지만 같은 버전에서 아무것도 새로 넣지 않음)이다. 기존 `pairs`의 `removal_events`는 "다른 것을 넣은 전이"만 세므로 이 막대를 그릴 수 없었다. 빌더가 `trans`를 지우기 전에 `removal_stats`(X별)·`removal_by_year`(X × 연도)를 집계해 채웠다.

### 7-1. 전체

| 항목 | 값 |
|---|---:|
| X를 뺀 전이(추가 여부 무관, X 기준 펼침) | 2,058,952 |
| 그중 대체 없이 제거 | 1,401,929 (**68.1%**) |
| 그중 대체 동반 제거 (= 기존 `removal_events`) | 657,023 (31.9%) |
| 제거된 적 있는 X 종류 | 203,347 (기존 110,130은 대체 동반만) |
| `removals_total ≥ 3`인 X (CSV 수록) | 47,250 |

**npm 전체로 보면 의존성 제거 셋 중 둘은 대체 없이 일어난다.** "X를 버렸다"는 신호의 대부분이 "Y로 갈아탔다"가 아니라는 뜻이다.

### 7-2. 상위 1천 패키지

다운로드 순위(`data/downloads/targets_top100k_20260902.csv`) 상위 1,000개 중 제거 이력이 있는 X는 985개, `removals_total≥3`은 962개다. 이 962개의 `no_replacement_pct` 분포:

| 사분위 | 값 |
|---|---:|
| Q1 | 71.1% |
| **중앙값** | **80.4%** |
| Q3 | 84.9% |
| 평균 | 76.8% |

상위 패키지는 전체 평균(68%)보다 대체 없이 빠지는 비율이 더 높다. 대형 패키지일수록 "기능이 내장되어 필요가 없어진" 경우와 대청소에 섞여 빠지는 경우가 많기 때문이다.

예시 (제거 전이 수 / 대체 없이 제거 비율):

| X | removals_total | 대체 없이 제거 | 비율 | 읽는 법 |
|---|---:|---:|---:|---|
| `lodash` | 15,914 | 9,469 | 59.5% | 개별 함수 내장·`lodash.*` 분할로 필요가 없어진 경우가 많음 |
| `chalk` | 7,934 | 5,090 | 64.2% | CLI 색상 제거·자체 구현 |
| `moment` | 5,360 | 3,391 | 63.3% | 나머지 1,969건이 §4의 dayjs·date-fns·luxon 이동 |
| `node-fetch` | 5,425 | 3,036 | 56.0% | Node 18+ 내장 fetch로 필요가 없어짐 |
| `request` | 5,056 | 2,312 | **45.7%** | 표본 중 유일하게 대체 동반이 다수. 폐기 공지 후 axios·got·node-fetch로 옮긴 흐름 |
| `tslint` | 939 | 721 | 76.8% | eslint 이동은 devDependencies라 잡히지 않음(§4) |
| `left-pad` | 100 | 72 | 72.0% | `String.prototype.padStart` 내장 |

상위 1천 안에서 `removals_total≥50`인 X 중 비율이 가장 높은 것은 `@aws-sdk/*`·`@smithy/*` 내부 패키지(94~98%, 모노레포 재배치)이고 가장 낮은 것은 `@smithy/types`(22.8%), `date-fns`(47.2%)다.

**해석 주의.** "대체 없이 제거"에는 세 가지가 섞여 있고 데이터로는 구분되지 않는다. ① 기능이 언어·런타임에 내장되어 필요가 없어진 경우(`left-pad`, `node-fetch`), ② dependent가 그 기능 자체를 버린 경우, ③ 대청소·모노레포 재배치. 따라서 이 값을 "X가 버려졌다"로 읽으면 안 되고, **"X를 뺀 사람 중 뚜렷한 후속 선택을 남기지 않은 비율"** 로 읽어야 한다.

연도별 추이 예 — `moment` (`removal_by_year`): 2017 419 → 2018 558 → 2019 572 → 2020 672(정점) → 2021 633 → 2022 601 → 2023 513 → 2024 463 → 2025 324. 대체 없이 제거 비율은 매년 60~70%로 일정하다.

### 7-3. 점유율: 표 기준 vs 배포주체·월 기준

`share_pct`는 표(votes) 기준이라 한 조직의 일괄 변경이 1위를 차지할 수 있다. `node-fetch`가 그 예다.

| Y | votes | publisher_months | `share_pct` | `share_pm_pct` |
|---|---:|---:|---:|---:|
| `form-data` | 358.2 | **8** | 15.0 (1위) | 0.2 |
| `axios` | 357.8 | 409 | 15.0 | **9.1 (1위)** |
| `cross-fetch` | 166.6 | 180 | 7.0 | 4.0 |
| `undici` | 97.2 | 101 | 4.1 | 2.3 |

`form-data`는 서로 다른 (배포주체, 월)이 8개뿐인데 표가 358이다. 한 조직의 대청소가 표를 만든 것이다. `share_pm_pct`로는 `axios`가 1위가 되어 실제 이동과 맞는다. recommended 1,022개 X 중 두 열의 1위 Y가 다른 X는 36개(3.5%)다. **화면 점유율은 `share_pm_pct`를 쓴다.** 라벨용 필터(`share≥10%`)는 기존대로 `share_pct` 기준을 유지해 09-08에 배포한 파일과 호환한다.

### 7-4. 검증 (작업계획 §3)

1. `removal_stats.removals_with_replacement` = `pairs.removal_events`: X별 불일치 0건, moment 1,969.
2. `removals_total = removals_no_replacement + removals_with_replacement`: 전 행 성립.
3. `removal_by_year` X별 합 = `removals_total`: 불일치 0건.
4. `left-pad` 72.0%(내장 대체 → 높음), `request` 45.7%(대체 동반 다수 → 낮음).
5. `node-fetch` 1위: `share_pct` form-data → `share_pm_pct` axios.

알려진 잡음: 의존성 이름이 빈 문자열(`""`)인 X가 `removal_stats.csv`에 1행, `removal_by_year.csv`에 4행 들어 있다. 원천 `Dependencies` 배열의 빈 이름이다. 소비 쪽에서 `removed_pkg <> ''`로 거른다.
