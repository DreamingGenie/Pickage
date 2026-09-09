# 마이그레이션 이동쌍 — npm 전수 계산 결과

작성 2026-09-08 · 원천 deps.dev BigQuery 2026-08-31 스냅샷(로컬 Parquet `data/raw/requirements`, `data/raw/versions_full`) · 생성 스크립트 `pipeline/duckdb/build_migration_pairs.py`(28분, 12스레드·40GB)
선행 `../feature_candidates_260908/README.md` §1-1(63개 대표 패키지 실측), `../../docs/설계_마이그레이션쌍_탐지_260831.md`(계산 설계)

## 0. 이 폴더가 답하는 질문

`../feature_candidates_260908/migration_pairs_100.csv`는 대표 63개 패키지(X)만 보고 뽑은 100건 표본이었다. 여기서는 **X를 제한하지 않고 npm 전체 릴리스 이력을 돌려** 이동쌍을 전부 뽑고, "이동을 알 수 있는 패키지가 몇 개인지", "데이터가 얼마나 되는지"를 확정했다.

계산은 설계 문서 0~4단계와 같다(라인별 발행시각 정렬 → 연속 릴리스 의존성 차집합 → 제거 1표를 추가 개수로 분배 → lift). 63개 실측과 다른 점은 두 가지다.

1. 분모 B가 209만 개 모집단이 아니라 **npm 전수 전이(3,958만 건)** 다. 그래서 lift 절대값은 63개 실측보다 크게 나온다(`moment→dayjs` 857 → 1,398). 순위는 유지됐다.
2. 설계 5-1 반영: 다음 버전의 `PeerDependencies`/`OptionalDependencies`로 옮겨진 이름(20.3만 건)은 제거가 아니라 재분류로 보고 X 후보에서 뺐다.

## 1. 파일

| 파일 | 내용 | 행 | 크기 |
|---|---|---:|---:|
| `migration_pairs_strict.csv` | 필터 `lift≥5 AND votes≥12 AND publisher_months≥10 AND A≥3%` 통과 쌍. 63개 실측과 같은 기준. **모델 positive 라벨용** | 1,195 | 104 KB |
| `migration_pairs_all.csv` | 필터 `lift≥5 AND votes≥3` 통과 쌍 전부. 열이 같으므로 원하는 기준으로 다시 걸러 쓴다 | 16,839 | 1.6 MB |
| `migration_pairs_recommended.csv` | **권고 하한**(§6) `lift≥5 AND votes≥8 AND publisher_months≥5 AND share≥10%` 통과 쌍. 전처리 없이 바로 라벨로 쓰는 파일 | 1,167 | 117 KB |
| `stats.json` | 아래 2·3절 숫자의 원본 | | |
| `data/migration_pairs/migration_events.parquet` (git 미추적) | 제거 이벤트 원시 전부. 모델이 소비하는 최소 단위 | 657,037 | 21 MB |
| `data/migration_pairs/migration_events.csv` (git 미추적) | 같은 내용 CSV | 657,037 | 119 MB |
| `data/migration_pairs.duckdb` (git 미추적) | 중간 테이블(`events`, `pairs`, `base`). 다른 필터로 다시 뽑을 때 재계산 없이 여기서 쿼리 | | 10.8 GB |

CSV는 UTF-8 BOM. 배열은 `|`로 이어 붙였다.

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
| `bidirectional` | (Y, X) 쌍도 lift≥5·votes≥3으로 존재하면 true. lodash↔lodash-es 같은 변종 관계 표시 |
| `first_seen`, `last_seen` | 이 전환이 관측된 첫·마지막 발행일 |

### 열 (events)

`dependent, publisher, line, from_version, to_version, to_published_at, removed_pkg, added_pkgs, added_count, vote_each` — `feature_candidates_260908/migration_events_100.csv`와 같다.

## 2. 규모

| 단계 | 값 |
|---|---:|
| 릴리스(is_release, 발행시각 있음, `M.m` 형식) | 47,178,483 |
| 패키지 | 4,065,912 |
| 연속 릴리스 전이 | 39,579,244 |
| 전이가 1건 이상 있는 패키지 | 2,494,351 |
| 의존성 변경이 있는 전이 | 1,843,563 (4.7%) |
| 제거·추가가 같은 전이 | 266,915 (0.67%) |
| peer/optional 재분류로 걸러낸 제거 | 202,554 |
| 제거 이벤트(추가 동반) | 657,037 |
| 제거된 적 있는 패키지 종류 | 110,131 |
| 이벤트를 만든 dependent 패키지 | 174,879 |
| 후보 (X, Y) 쌍 전부(필터 전) | 1,900,453 |

설계 문서 2-5가 260개 표본으로 추정한 "교체 이벤트 약 10만 건"은 실측 26.7만 전이 / 65.7만 이벤트로, 예상보다 신호가 많았다.

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

정밀도 근사 60~70%는 하한이며, 오답으로 세어진 상위 사례를 보면 `fs-promise→fs-extra`(선언은 `mz`), `babel-eslint→@babel/core`(선언은 `@babel/eslint-parser`, 함께 설치되는 짝)처럼 실제로는 타당한 이동이 절반쯤 섞여 있다. 남는 진짜 오답은 `@angular/http→tslib`류 동반 추가와 모노레포 내부 재배치다.
