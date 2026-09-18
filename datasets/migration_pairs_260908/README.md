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
| `removal_by_period.csv` | **X × 구간 이탈 사유**(§8). 화면이 쓰는 `1y`·`3y`·`5y` 기준. 같은 X 기준 | 87,045 | 3.1 MB |
| `stats.json` | 아래 2·3절 숫자의 원본 | | |
| `data/migration_pairs/migration_events.parquet` (git 미추적) | 제거 이벤트 원시 전부. 모델이 소비하는 최소 단위 | 657,023 | 21 MB |
| `data/migration_pairs/migration_events.csv` (git 미추적) | 같은 내용 CSV | 657,023 | 119 MB |
| `data/migration_pairs/removal_stats.parquet`, `removal_by_year.parquet`, `removal_by_period.parquet` (git 미추적) | 위 세 CSV의 필터 없는 전체 | 203,336 / 351,972 / 273,610 | 4.5 MB / 2.3 MB / 2.5 MB |
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

**09-14 회귀 확인** (S15P21A506-349에서 빌더에 `--source`·`--kind` 를 추가한 뒤): `--source depsdev` 로
다시 돌려 같은 흔들림만 나오는 것을 확인했다. 의존성 변경 전이 +15, 제거·추가 동시 전이 +8, 이벤트 +15,
loose 쌍 +2. **strict 쌍은 (from, to) 집합까지 완전히 같았다** — 이전에만 있는 쌍 0, 새로 생긴 쌍 0, 공통 1,195.
남은 차이는 동률 행의 정렬 순서와 `lift` 끝자리 반올림(예: 653.6 → 653.7)뿐이다. 이 폴더의 파일은
**09-08 실행 결과를 그대로 유지한다** — 위 표들의 근거이기 때문이다.
다만 다음 재계산부터 `stats.json` 의 `reclassified_to_peer_or_optional` 키 이름이
`reclassified_to_other_kinds` 로 바뀐다(세는 대상이 원천·의존 종류에 따라 달라져 옛 이름이 맞지 않는다).

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
| enzyme → @testing-library/react | **✘** 미검출 (이 원천으로는. 아래 참고) | | |

5쌍 중 4쌍 재현. `enzyme`은 제거 이벤트 96건이 있지만 `@testing-library/react`와 같은 전이에 나온 게 표 3 미만이다. 이유는 enzyme이 대개 `devDependencies`에 있고 deps.dev `NPMRequirements`는 dev 의존성을 담지 않기 때문으로 본다. 테스트·린트·빌드 도구 계열(`tslint`, `mocha`, `jest`, `enzyme`)은 이 데이터에서 구조적으로 약하다.

**2026-09-14 추가 — 원인 확인, 다른 원천으로 해결됨(S15P21A506-349).** 위 추정이 맞았다. npm registry 수집분
(S15P21A506-280, 상위 10만)에는 `devDependencies`가 있어 같은 계산을 개발용 의존에 돌리면
`enzyme → @testing-library/react`가 **strict 1위로 잡힌다**(votes 52.5 · publisher_months 110 · a_rate 44.8% · lift 2,010).
`tslint → eslint`, `mocha → jest`/`vitest`, `babel-eslint → @babel/eslint-parser`도 같이 나온다.
결과는 [`../migration_pairs_dev_260914/`](../migration_pairs_dev_260914/)에 따로 있다 — **모집단이 달라 이 폴더의
수치와 더하거나 lift를 비교하면 안 된다.** 정답지 재현은 두 폴더를 합쳐 5/5다.

## 5. 주의

- **양방향 쌍**: `lodash → lodash-es`(1,243표)와 `lodash-es → lodash`(537표)가 둘 다 strict를 통과한다. ESM/CJS 전환처럼 왕복하는 관계다. 라벨로 쓸 때 (X,Y)와 (Y,X)가 모두 있으면 "대체"가 아니라 "변종"으로 따로 다루는 편이 맞다.
- **동반 추가 잡음**: `rxjs → tslib`(lift 729)처럼 X 제거와 무관하게 같은 릴리스에 딸려 들어온 것이 남는다. lift 하한을 높이는 것보다 `dependents`·`publisher_months`가 `co_events`에 비해 작은 쌍(소수 주체의 반복)을 감점하는 쪽이 효과적이다.
- **dev 의존성 부재**: 4절 참고. 도구 계열 마이그레이션은 **이 폴더의 데이터로는** 말할 수 없다.
  개발용 의존 기준 결과는 [`../migration_pairs_dev_260914/`](../migration_pairs_dev_260914/)에 있다(상위 10만 한정).
- **실행용 → 개발용 강등이 '제거'로 섞여 있다** (2026-09-14 측정, S15P21A506-349): deps.dev 원천에 dev 칸이 없어,
  `dependencies`에서 빼고 같은 전이에서 `devDependencies`로 **옮긴** 것을 이 폴더는 전부 제거로 센다.
  설계 문서 §5-1의 peerDependencies 함정과 같은 함정이 dev 칸에도 있었다. 같은 모집단에서 필터만 바꿔 재 보니:
  - **쌍 CSV 3종은 영향이 거의 없다.** strict 143쌍 중 사라진 쌍 0, 하한 언저리에서 기준 미달 4쌍뿐.
    강등은 대체재를 함께 넣지 않아 애초에 쌍 집계에 들어오지 않기 때문이다. **이 폴더의 1,195쌍은 그대로 써도 된다.**
  - **제거 통계(§7)는 12.15% 부풀어 있다.** 제거 전이 220,166 → 193,420. `eslint`는 '제거'의 82.7%,
    `jest`는 77.5%가 칸 이동이다. **"대체 없이 떠남" 비율을 화면에 쓸 때 이 보정을 먼저 볼 것.**
  - 측정 가능 범위: strict 출발 패키지 782개 중 746개(상위 10만 안)만 잴 수 있고 그중 532개에 재분류가 섞여 있다.
    나머지는 '영향 없음'이 아니라 '못 잼'이다.

  수치·보정 파일은 [`../migration_pairs_dev_260914/README.md`](../migration_pairs_dev_260914/README.md) §4.
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

## 8. 구간별 이탈 사유 (2026-09-18 추가, S15P21A506-378)

§7 은 전 기간과 **연도별**로만 집계했다. 화면이 쓰는 구간은 `1y`·`3y`·`5y` 라 그대로 쓸 수 없어 같은 것을 구간 경계로 다시 셌다(`removal_by_period`).

연도별 집계를 잘라 쓸 수 없는 이유는 둘이다. 구간은 **`2026-08-31` 에 끝나는데 달력 연도는 `12-31` 에 끝나서** 한 해를 반으로 나눌 수 없고, `dependents` 는 `COUNT(DISTINCT)` 라 연도끼리 더해지지 않는다.

구간 경계는 `pipeline/duckdb/build_dependent_transitions.py` 에서 가져온다. 여기에 날짜를 다시 적으면 다음 스냅샷에서 한쪽만 고쳐지고, 두 산출물이 서로 다른 구간을 같은 이름(`3y`)으로 부르게 된다.

### 8-1. 구간

| 구간 | `t1` (제외) | `t2` (포함) |
|---|---|---|
| `1y` | 2025-08-31 23:59:59 | 2026-08-31 23:59:59 |
| `3y` | 2023-08-31 23:59:59 | 2026-08-31 23:59:59 |
| `5y` | 2021-08-31 23:59:59 | 2026-08-31 23:59:59 |

**구간은 겹친다.** `1y ⊂ 3y ⊂ 5y` 이고 셋 다 같은 날 끝난다. 연도별 집계처럼 서로 배타적이지 않으므로 **같은 제거 한 건이 세 구간에 모두 들어간다. 구간끼리 더하지 말 것.**

`t2` 를 넘는 전이는 뺀다. 원천의 `snapshot=2026-08-31` 파티션에는 09-01 발행분이 섞여 있어(BigQuery 추출이 UTC 자정을 지나 돌았다), 거르지 않으면 유지·유입·이탈과 기준이 갈린다. 걸러진 전이 수는 `stats.json` 의 `transitions_after_t2` 에 남는다.

### 8-2. 수치

| 구간 | 이탈 전이 | 대체 없이 제거 | 대체 동반 제거 | X 종류 |
|---|---:|---:|---:|---:|
| `1y` | 272,893 | 185,046 (**67.8%**) | 87,847 | 46,229 |
| `3y` | 774,410 | 542,635 (**70.1%**) | 231,775 | 94,695 |
| `5y` | 1,285,648 | 891,664 (**69.4%**) | 393,984 | 132,686 |
| 전 기간(§7) | 2,058,773 | 1,401,798 (68.1%) | 656,975 | 203,336 |

CSV 는 §7 과 같이 `removals_total ≥ 3` 인 X 만 담는다(87,045행). 필터 없는 전체는 parquet 에 있다(273,610행).

**대체 없이 제거되는 비율이 구간과 거의 무관하다** — 67.8% · 70.1% · 69.4% 이고 전 기간 68.1% 와도 같다. 최근 들어 대체 없이 버려지는 경향이 강해졌다거나 약해졌다고 말할 근거가 없다는 뜻이다. 시기를 타는 현상이 아니라 npm 의 구조적 성질로 보인다.

`t2` 를 넘겨 제외된 전이는 721 건이다.

### 8-3. 유지·유입·이탈(`dependent_transitions_260917`)과 **세는 단위가 다르다**

같은 화면에 놓이더라도 **두 수를 더하거나 나누면 안 된다.**

|  | 유지·유입·이탈 | 이 표 (§8) |
|---|---|---|
| 계산 방식 | 시점 두 개의 선언 집합을 비교 | 연속한 두 릴리스를 처음부터 훑음 |
| 세는 단위 | **패키지 수** (한 패키지는 1) | **전이 건수** (넣었다 뺐다를 반복하면 여러 건) |
| 중간 변화 | 안 보임 | 전부 보임 |
| 모집단 | 대상 상위 10만 × 의존자 npm 전수 | npm 전수 |

그래서 **`유지·유입·이탈의 outflow ≠ removals`** 다. `outflow` 는 "T1 엔 쓰고 T2 엔 안 쓰는 패키지가 몇 개인가" 이고, `removals` 는 "그 사이 빼는 행위가 몇 번 있었나" 이다. 한 패키지가 뺐다 넣었다 다시 뺐으면 `outflow` 에는 1, 여기에는 2로 잡힌다.

`removals = removals_no_replacement + removals_with_replacement` 는 이 표 **안에서만** 성립한다.

### 8-4. 검증

1. **구간 포함관계** — 구간이 겹치므로 X마다 `1y ≤ 3y ≤ 5y ≤ removals_total` 이 반드시 성립한다. 빌더가 산출물을 쓰기 전에 확인하고, 어긋나면 멈춘다(`require_monotonic`). `removals = 대체동반 + 대체없음` 은 두 `FILTER` 가 같은 조건을 갈라 쓰므로 언제나 참이라 검산이 되지 못한다.
2. **합성 입력 시험** — `pipeline/duckdb/test_removal_periods.py` 13개. 구간 겹침·경계(`t1` 제외 `t2` 포함)·`t2` 컷오프·대체 판정·`added` 가 NULL 인 경우·`dependents` 중복 접기·검산이 실제로 멈추는지.

### 8-5. 이 회차에서 정렬 결함을 고쳤다 — 이전 숫자와 미세하게 다르다

`trans` 를 만드는 창 함수가 `ORDER BY published_at` 뿐이라 **같은 시각에 발행된 릴리스 사이에서 앞 버전이 정해지지 않았다.** 같은 입력을 두 번 돌려 `removals_total` 이 `2,058,952` / `2,058,928` 로 갈리는 것을 실측했다(2026-09-18).

| 항목 | 값 |
|---|---:|
| `(Name, line, published_at)` 그룹 | 47,176,041 |
| 그중 동순위 그룹 | 1,142 (0.002%) |
| 거기 묶인 릴리스 | 3,584 |
| 해당 패키지 | 703 |
| 한 그룹 최대 | 38 |

정렬에 버전 숫자를 더해 깼다 — `published_at`, major, minor, patch, `Version` 순이다. `ordinal`(deps.dev 의 semver 순번, `semver_rule.py` 에서 node-semver 와 27,763건 전부 일치 확인)을 쓰지 않은 것은 `--source registry` 경로에 그 열이 없기 때문이다. 두 원천에 다른 규칙을 쓰면 언젠가 한쪽만 고쳐진다. `is_release`(registry 는 `-` 없음) 조건에 prerelease 가 이미 걸러져 있어 `(major, minor, patch)` 로 충분하다.

**그래서 §2·§7 의 수치가 09-08·09-09 판과 0.001% 안에서 다르다.** 결론은 바뀌지 않는다(대체 없이 제거 68.1%는 그대로). 이전 판을 인용한 문서가 있으면 이 절을 함께 가리키면 된다.

#### 어디까지 재현되는가 — 두 번 돌려 확인했다

고친 뒤 같은 입력으로 두 번 돌려 산출물 해시를 대조했다.

| 파일 | 두 실행이 같은가 |
|---|---|
| `removal_stats.csv` · `removal_by_year.csv` · `removal_by_period.csv` | **같다** (SHA-256 일치) |
| `migration_pairs_all.csv` · `_strict.csv` · `_recommended.csv` | **다르다** |

**이동쌍 쪽에는 원인이 따로 있고, 이 회차에서 고치지 않았다.** `votes` 가
`sum(1.0/len(added))` 라 **부동소수점 덧셈 순서에 따라 마지막 자리가 흔들리고**, `votes ≥ 3`
경계에 걸친 쌍이 실행마다 들락날락한다. 같은 `events` 표에 같은 질의를 세 번 돌려
`16,833 / 16,833 / 16,834` 가 나오는 것을 확인했다 — 입력이 한 행도 다르지 않은데 결과가
갈린다.

폭은 1만 6천 쌍 중 서넛이다(`loose_pairs` 16,835 ↔ 16,832). 라벨 품질을 좌우하는 수준은
아니지만 **이동쌍 CSV 는 아직 "돌릴 때마다 같은 파일" 이 아니다.** 고치려면 `votes` 를
정수 합으로 바꾸거나 비교 전에 자리를 끊어야 하는데, 그 열은 `share` 필터와 AI 라벨
기준에 걸려 있어 별도로 다룬다.

§7·§8 의 이탈 수치는 이 문제와 무관하다. 그쪽은 `votes` 를 쓰지 않는다.
