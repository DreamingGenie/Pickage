# 패키지별 dependents 목록 — 누가 이 패키지에 의존하는가

작성 2026-09-15 (S15P21A506-354) · 원천 deps.dev BigQuery 2026-08-31 스냅샷(로컬 Parquet `data/raw/requirements`, `data/raw/versions_full`) · 생성 스크립트 `pipeline/duckdb/build_package_dependents.py`(88초, 8스레드·24GB)
쓰는 곳 S15P21A506-173 유사후보 랭커의 **보완재 감점 관문**

## 0. 이 폴더가 답하는 질문

`react`와 `react-dom`은 설명도 비슷하고 벡터 유사도도 높지만 **서로 대체재가 아니라 보완재**다. 같이 쓰는 것이지 골라 쓰는 게 아니다. 이걸 가르는 신호가 dependents 교집합이다 — "A를 쓰는 패키지들"과 "B를 쓰는 패키지들"이 거의 같으면 둘은 함께 설치되는 짝이다.

팀에 이미 있던 dependents 데이터는 전부 **수(count)** 뿐이라 교집합을 잴 수 없었다.

| 기존 | 단위 | 왜 안 되나 |
|---|---|---|
| `../targets/rank_top100k_20260902.csv`의 ecosyste.ms `dependent_packages_count` | 패키지 1행, 수 | 의존자의 신원이 없다 |
| S15P21A506-193 버전별 집계 | (패키지, 버전, 날짜) 1행, 수 | 같음. 산출물도 담당자 로컬·로컬 PostgreSQL에만 있다 |

그래서 **목록**을 낸다.

## 1. 파일

| 파일 | 내용 | 행 | 크기 |
|---|---|---:|---:|
| `data/package_dependents/package_dependents.parquet` (git 미추적) | **본체.** `(name, kind)` 1행 — `dependents[]` 배열 | 299,988 | 104 MB |
| `dependents_summary.csv` | 같은 표에서 **배열만 뺀 것**. 수·순위·대조값만 | 299,988 | 13 MB |
| `stats.json` | 아래 2·3절 숫자의 원본 | | |

**배열은 CSV로 내지 않는다.** `react` 한 행의 `dependents`가 19만 원소라 한 셀에 넣을 수 없다. 목록이 필요하면 parquet을 쓴다.

### 열

| 열 | 뜻 |
|---|---|
| `name` | 대상 패키지. 이 패키지에 **의존하는** 것들이 `dependents`다 |
| `kind` | `regular` · `peer` · `optional`. 대상마다 3행이 항상 있다 |
| `dependents` | 의존자 패키지 이름 배열. 정렬돼 있고 중복이 없다 |
| `n_dependents` | `len(dependents)` |
| `download_rank` | ecosyste.ms 다운로드 순위 (1이 가장 높음) |
| `ecosystems_dependent_count` | **대조용** ecosyste.ms 값. 맞춰야 하는 값이 아니다 (§4) |
| `package_exists` | npm에 최신 릴리스가 있는가. 거짓이면 대상 목록에만 있고 실물이 없다 (2,251개) |

## 2. 규모

모집단은 최신 릴리스가 있는 npm 패키지 **4,065,913개**다. 대상은 다운로드 상위 **99,996개**.

| kind | dependents ≥ 1인 대상 | 엣지 | 최대 | p50 / p90 / p99 |
|---|---:|---:|---:|---:|
| `regular` | 81,780 | 11,465,242 | 192,736 (`react`) | 5 / 90 / 1,696 |
| `peer` | 27,636 | 1,882,181 | 344,357 (`react`) | 0 / 5 / 123 |
| `optional` | 7,946 | 45,094 | 3,399 | 0 / 0 / 7 |

대상 10만 중 **15,050개는 세 종류 모두 dependents가 0**이다. 행을 빼지 않고 빈 배열로 남긴 것은 "조회 실패"와 "의존자가 없음"이 구분돼야 하기 때문이다. `n_dependents = 0`은 결측이 아니라 범주다.

## 3. 이 데이터가 실제로 보완재를 가르는가 (검증)

`regular` 기준 실측이다. **`min분모`**는 교집합 ÷ 작은 쪽 크기(overlap coefficient)다.

| A | B | \|A\| | \|B\| | 교집합 | Jaccard | min분모 | |
|---|---|---:|---:|---:|---:|---:|---|
| `react` | `react-dom` | 192,736 | 158,317 | 155,520 | 0.795 | **0.982** | 보완재 |
| `webpack` | `webpack-cli` | 24,801 | 6,506 | 5,872 | 0.231 | **0.903** | 보완재 |
| `chalk` | `debug` | 148,880 | 47,257 | 6,538 | 0.034 | 0.138 | 보편 유틸끼리 |
| `express` | `koa` | 94,109 | 6,781 | 640 | 0.006 | 0.094 | 대체재 |
| `react` | `lodash` | 192,736 | 150,499 | 11,790 | 0.036 | 0.078 | 무관 |
| `vue` | `svelte` | 80,580 | 1,927 | 109 | 0.001 | 0.057 | 대체재 |
| `moment` | `dayjs` | 51,317 | 20,885 | 1,121 | 0.016 | 0.054 | 대체재(정답지 이동쌍) |
| `react` | `vue` | 192,736 | 80,580 | 590 | 0.002 | 0.007 | 대체재 |

보완재 0.90~0.98, 대체재 0.007~0.094. **그 사이가 비어 있어서 S15P21A506-173의 임계값 0.3이 잘 작동한다.**

### 분모를 무엇으로 하느냐가 결과를 뒤집는다

`-173`에는 "dependents 교집합 `> 0.3`"이라고만 적혀 있는데, **Jaccard로 재면 `webpack`↔`webpack-cli`가 0.231로 관문을 통과해 버린다.** 진짜 보완재인데 못 잡는다. 크기가 크게 차이 나는 짝(우산 패키지 ↔ 부속 CLI/플러그인)에서 Jaccard는 큰 쪽 분모에 희석된다.

**`min분모`(overlap coefficient)를 쓸 것.** 위 표에서 두 방식이 갈리는 유일한 행이 바로 그 사례다.

## 4. 알려진 한계 — 쓰기 전에 반드시 읽을 것

### 4-1. devDependencies가 원천에 없다

deps.dev `NPMRequirements`는 `Dependencies`·`PeerDependencies`·`OptionalDependencies` 세 가지만 담는다. **개발 의존으로 주로 쓰이는 패키지는 구조적으로 과소 계상된다.**

`typescript`가 우리 57,189인데 ecosyste.ms는 488,056이다(0.12배). `eslint`·`jest`·`vitest`·`prettier` 류의 대체 판단에 이 데이터를 그대로 쓰면 안 된다.

반대로 런타임 의존이 주인 패키지는 잘 맞는다 — `express` 1.01 · `fs-extra` 1.00 · `debug` 1.01 · `lodash` 0.95 · `tslib` 0.95 · `moment` 0.95.

### 4-2. 플러그인 생태계는 peer를 봐야 실체가 보인다

`regular`만 보면 틀린 그림이 나온다.

| 패키지 | regular | peer |
|---|---:|---:|
| `react` | 192,736 | **344,357** |
| `eslint` | 21,280 | **25,041** |
| `vue` | 80,580 | 44,082 |

`react`는 peer 의존자가 regular보다 **많다.** 플러그인·컴포넌트가 react를 자기 것으로 설치하지 않고 peer로 요구하기 때문이다. `kind`를 골라 쓸 수 있게 만든 이유가 이것이다.

### 4-3. 직접 의존만 — 전이 의존은 없다

`A → B → C`에서 C의 dependents에 A는 없다. deps.dev `Dependents` 테이블에는 all-depth가 있지만 npm 한 스냅샷이 650 GiB라 쓸 수 없다(`docs/api & data/수집계획_BigQuery_Parquet_v2_260902.md` §1).

### 4-4. 선언 기반이고, 최신 릴리스 1개만 본다

package.json의 **선언**을 셀 뿐 실제 설치 그래프가 아니다. 그리고 패키지마다 최신 릴리스 하나만 본다 — 과거 버전이 무엇에 의존했는지는 세지 않는다. "최신"은 `is_release` 중 `ordinal` 최대이며, `published_at`이 아니다(5.0.0 뒤에 나온 유지보수 릴리스 4.17.3이 최신으로 잡히면 안 되므로).

### 4-5. 생존 편향

2026-08-31 스냅샷에 남아 있는 버전만 보인다. unpublish된 패키지는 과거에 의존했더라도 나타나지 않는다.

### 4-6. ecosyste.ms 값과 일치하지 않는다 — 일치하면 안 된다

`ecosystems_dependent_count`를 같은 행에 둔 것은 **대조하라는 뜻이지 맞추라는 뜻이 아니다.** 집계 기준(시점·모집단·의존 종류·dev 포함 여부)이 서로 다르다. 65,307개 대상에서 중앙 비율이 **0.710**이고, 자릿수가 맞으면 정상으로 본다.

크게 벌어지는 쪽이 꼭 우리 잘못은 아니다. `zod`(18.05배)·`next`(7.16배)·`@modelcontextprotocol/sdk`(ecosyste.ms가 0)는 최근 급성장한 패키지라 ecosyste.ms 쪽 값이 낡았을 가능성이 크다.

### 4-7. 자기참조 62건

`@realtek/core-theme@0.0.341`이 `@realtek/core-theme@^0.0.203`을 의존으로 선언한 것 같은 사례가 62건 있다(전체의 0.06%). 원천의 실제 선언이고 canary·모노레포 빌드에서 나온다. 걸러내지 않았으니 교집합 계산에 자기 이름이 끼는 게 곤란하면 쓰는 쪽에서 뺀다.

### 4-8. 번들 경로 노드를 걸러냈다 (스크립트를 고칠 때 주의)

`versions_full`의 고유 이름 **1,138만 중 705만(61.9%)** 이 `@winglang/sdk>0.76.19>cdktf>safe-buffer` 형태의 **번들된 중첩 의존성 경로**다. npm 이름에 `>`는 쓸 수 없으니 실제 패키지가 아니다. 이걸 빼지 않으면 `tslib`이 116,820 대신 **972,523**으로 나온다.

실측상 이 노드들은 **7,052,193행 전부 `published_at`이 NULL**이고 정상 패키지는 430행만 NULL이다. 그래서 스크립트는 `published_at IS NOT NULL`을 정본 조건으로 쓴다 — S15P21A506-283의 `unknown_published_at=exclude` 정책과 같은 기준이다. **이 조건을 지우면 의존자 수가 통째로 부푼다.**

## 5. 쓰는 법

### DuckDB — 쌍의 교집합 재기

```sql
WITH a AS (SELECT dependents d FROM read_parquet('data/package_dependents/package_dependents.parquet')
           WHERE name = 'react' AND kind = 'regular'),
     b AS (SELECT dependents d FROM read_parquet('data/package_dependents/package_dependents.parquet')
           WHERE name = 'vue' AND kind = 'regular')
SELECT len(list_intersect(a.d, b.d))::DOUBLE
       / nullif(least(len(a.d), len(b.d)), 0) AS overlap_min   -- §3의 min분모
FROM a, b;
```

`regular`와 `peer`를 합쳐 보려면 두 행의 배열을 `list_distinct(list_concat(...))`로 잇는다.

### 파이썬 — 필요한 이름만 걸러 읽기

**전체를 `dict[str, set]`으로 만들지 말 것.** 배열이 총 1,340만 원소라 파이썬 문자열 객체 오버헤드만으로 수 GB다.

```python
import pyarrow.parquet as pq

names = ["react", "vue", "preact"]          # 랭커가 검색해 온 후보 30개
t = pq.read_table(
    "data/package_dependents/package_dependents.parquet",
    filters=[("kind", "=", "regular"), ("name", "in", names)],
)
dep = {r["name"]: set(r["dependents"]) for r in t.to_pylist()}

def overlap(a, b):                           # §3의 min분모
    x, y = dep.get(a, set()), dep.get(b, set())
    return len(x & y) / min(len(x), len(y)) if x and y else 0.0
```

## 6. 다시 만들기

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_package_dependents.py
```

88초. 입력은 `data/raw/requirements`(6.7 GB)·`data/raw/versions_full`(4.5 GB)·`../targets/rank_top100k_20260902.csv`다. 다른 스냅샷으로 돌리려면 스크립트 상단의 `V` 경로와 출력 폴더 날짜를 함께 바꾼다.
