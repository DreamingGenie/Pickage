# 대체 후보 peer 의존 유사도

Jira **S15P21A506-350** (에픽 S15P21A506-110) · 계산 2026-09-14 · 원천 deps.dev 2026-08-31 스냅샷

"A 패키지가 B 패키지를 대체할 수 있나"를 판단할 때 쓰는 **호환성 특징**이다.

## 0. 왜 peer 인가

`peerDependencies` 는 패키지가 **자기 것으로 설치하지 않고 사용자 프로젝트에 이미 있어야 한다고 요구하는**
패키지다. 플러그인·컴포넌트·어댑터가 어느 호스트(react, vue, @angular/core, eslint, webpack) 위에서
동작하는지를 선언하므로 사실상 **생태계 소속 표지**다.

description 이 "date picker component" 로 똑같아도 react 용과 vue 용은 서로 대체가 아니다. 이름·설명
임베딩만으로는 이 구분이 안 된다. 근거와 배경은
[`../feature_candidates_260908/README.md`](../feature_candidates_260908/README.md) §1-3 에 있다.

이 폴더는 그 §1-3 의 결론을 **조인해서 쓸 수 있는 전수 표**로 만든 것이다. 기존
`peer_dependencies_100.csv` 는 ①100행 무작위 표본 ②폐기→대체 쌍 기준 ③`match`/`mismatch` 3분류여서
재랭킹 입력으로 쓸 수 없었다.

## 1. 파일

| 파일 | 내용 | 규모 |
|---|---|---|
| `pair_peer_similarity.csv` | 쌍 1행 — 양쪽 peer 목록·교집합·Jaccard·판정 | 53,155행 |
| `package_peers.csv` | 패키지 1행 — 최신 릴리스의 peer 목록 | 57,820행 |
| `stats.json` | 규모·판정 분포 |  |

Parquet(배열이 배열 그대로 살아 있음)은 `data/peer_similarity/`(gitignore)와 서버 MinIO
`pickage-curated/depsdev/v1/peer-similarity/snapshot=2026-08-31/run_id=peer-similarity-20260914-v1/` 에 있다.
CSV 는 배열을 `|` 로 이어 붙였다(엑셀·구글시트 호환).

재현:

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_peer_similarity.py   # 약 10초
```

## 2. 열

### `pair_peer_similarity`

| 열 | 타입 | 뜻 |
|---|---|---|
| `source` | VARCHAR | 쌍 출처 — `migration` / `migration_dev` / `deprecated` |
| `tier` | VARCHAR | 필터 등급 — `strict` / `recommended` / `all` (등급은 포개져 있다) |
| `from_pkg`, `from_version` | VARCHAR | A (대체당하는 쪽)와 그 최신 릴리스 |
| `to_pkg`, `to_version` | VARCHAR | B (대체하는 쪽)와 그 최신 릴리스 |
| `from_peers`, `to_peers` | VARCHAR[] | **각자의 peerDependencies 이름** |
| `from_peers_req`, `to_peers_req` | VARCHAR[] | 버전 범위 포함 (`react@^17.0.0 \|\| ^18.0.0`) |
| `n_peer_from`, `n_peer_to` | BIGINT | 개수 |
| `shared_peers`, `n_shared` | VARCHAR[], BIGINT | 교집합 |
| `peer_jaccard` | DOUBLE | 자카드 유사도. **한쪽이라도 peer 가 없으면 NULL** |
| `peer_verdict` | VARCHAR | `match` / `mismatch` / `one_side_only` / `no_peer_either` |
| `missing_release` | BOOLEAN | 최신 릴리스를 못 찾은 쪽이 있음(695 패키지). 대개 unpublish |

### `package_peers`

| 열 | 타입 | 뜻 |
|---|---|---|
| `name`, `version` | VARCHAR | 패키지명(조인 키)과 최신 릴리스 |
| `peers`, `peers_req` | VARCHAR[] | peer 이름 / 버전 범위 포함 |
| `n_peers` | BIGINT | 개수 |

쌍 표에 없는 조합을 새로 비교하고 싶으면 이 표를 두 번 조인하면 된다.

## 3. 쓰는 법 — 두 가지를 꼭 지킬 것

### 3-1. `peer_jaccard` 의 NULL 을 0 으로 채우지 않는다

peer 는 희소한 속성이다. 쌍의 **60%가 양쪽 다 peer 를 갖고 있지 않다**(31,971행, `no_peer_either`).
이것은 "유사도 0"이 아니라 **"비교 불가"** 다. 0 으로 채우면 모델이 결측 60%를 "대체 불가"로 배운다.

범주는 `peer_verdict` 로 받고, 연속값은 NULL 을 유지하거나 별도 결측 플래그를 쓴다.

### 3-2. hard filter 가 아니라 감점 입력이다

```
tslint  peer = [typescript]
eslint  peer = [jiti]         → 겹침 0, peer_verdict = mismatch
```

`tslint → eslint` 는 **정답지에 있는 진짜 대체쌍**이다. peer 불일치만으로 탈락시키면 이런 쌍을 잃는다.
`feature_candidates` README §1-3 의 권고("유사도 점수와 별개로 hard filter 또는 강한 감점")에서,
이 데이터는 **감점 쪽**을 택할 근거를 준다.

## 4. 판정 분포

`tier='all'` 기준. 등급이 포개져 있으므로 `strict`·`recommended` 를 함께 세지 않는다.

| source | 쌍 | `no_peer_either` | `one_side_only` | `match` | `mismatch` |
|---|---:|---:|---:|---:|---:|
| `deprecated` | 25,916 | 66.9% | 10.9% | 20.6% | 1.6% |
| `migration` | 16,835 | 62.3% | 23.2% | 10.9% | 3.5% |
| `migration_dev` | 6,770 | **33.3%** | 40.6% | 11.8% | **14.3%** |

**개발용 의존 이동쌍에서 peer 가 가장 잘 듣는다.** 도구·플러그인 계열이라 peer 선언 비율이 높아
비교 불가가 절반으로 줄고, `mismatch` 는 다른 원천의 4~9배다. 그 불일치에는

```
style-loader              → @swc/core      (webpack vs @swc/helpers)
style-loader              → react-dom      (webpack vs react)
eslint-plugin-react-hooks → react-scripts  (eslint vs react·typescript)
```

처럼 **동반 추가 잡음**이 몰려 있다(이동쌍 README §5 의 두 번째 주의). peer 감점의 효과가 여기서 가장 크다.

양쪽 peer 가 있는 10,777쌍의 Jaccard 분포는 완전일치 4,314(40%) · 0.5~1 1,952(18%) ·
0~0.5 2,300(21%) · 겹침없음 2,211(21%) 로, 양 끝이 두꺼워 판별력이 있다.

## 5. 한계

- **버전 기준은 최신 릴리스다.** "A 가 B 를 대체할 수 있나"는 지금 시점 판단이라 최신을 썼다.
  다만 A 가 폐기·방치된 패키지면 그 최신은 몇 년 전 선언이라 **그 시절 생태계를 반영한다** —
  `moment` 의 peer 는 2020년 기준이다. 이동이 실제로 일어난 시점 기준이 필요하면
  `migration_events.to_published_at` 에 맞춰 당시 버전을 고르는 별도 작업이 된다.
- **peer 값의 원천은 deps.dev 전수다.** 비교 대상 쌍 목록에 registry 기반 개발용 이동쌍이 섞여 있지만,
  peer 열 자체는 `requirements`(npm 전수, 2026-08-31)에서만 온다. 모집단 문제가 없다.
- **버전 범위는 맞추지 않았다.** `react@>=15` 와 `react@^18` 은 이름이 같으므로 `match` 다.
  범위까지 볼지는 2차 문제다(`*_peers_req` 열에 원문을 남겨 두었다).
- `missing_release` 인 695 패키지는 양쪽 peer 가 빈 배열로 들어가 `no_peer_either` 로 분류된다.
  비교 불가인 것은 맞지만 사유가 다르므로, 엄밀히 보려면 이 플래그로 걸러 낸다.

## 6. npm 전수 peer 목록 (`--scope all`, 2026-09-15 추가)

위 §1~§5 는 **쌍 목록에 등장한 패키지**(57,820개)만 다룬다. 쌍 목록에 없는 임의의 조합을 즉석에서
비교하려면 전수가 필요해서 따로 냈다. 이 폴더에는 집계 `package_peers_scope_all_stats.json` 만
있고, Parquet 은 `data/package_peers/`(gitignore)와 서버 MinIO
`pickage-curated/depsdev/v1/package-peers/snapshot=2026-08-31/run_id=package-peers-20260915-v1/` 에 있다.

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_peer_similarity.py --scope all   # 약 50초
```

| 파일 | 행 | 크기 |
|---|---:|---:|
| `package_peers_all.parquet` | 814,025 | 27.9MB |
| `package_peers_recent.parquet` | 531,830 | 18.9MB |

열은 §2 의 `package_peers` 에 품질 열 4개를 더한 것이다 — `n_releases`, `last_published_at`,
`is_deprecated`, `download_rank`(상위 10만 밖이면 NULL). `recent` 는 `all` 의 부분집합이고 열이 같다.

**peer 가 없는 패키지는 행 자체를 넣지 않았다.** 최신 릴리스가 있는 패키지 4,065,913개 중
peer 보유는 814,025개(20.0%)뿐이다. "peer 가 없다"는 사실은 이 표에 행이 없다는 것으로 똑같이
표현되고, 빈 배열 325만 행은 파일만 키운다.

### 6-1. 전수를 그대로 쓰지 말 것

| 지표 | `all` | `recent` | 남는 비율 |
|---|---:|---:|---:|
| 패키지 | 814,025 | 531,830 | 65.3% |
| peer 선언 건수 | 2,075,257 | 1,381,645 | 66.6% |
| **릴리스 1개짜리** | **194,580 (23.9%)** | **121,017 (22.8%)** | 62.2% |
| deprecated | 28,668 | 14,983 | 52.3% |
| **다운로드 상위 10만 안** | **29,193 (3.6%)** | **25,061** | **85.8%** |
| 서로 다른 배포 주체 | 520,455 | 319,711 | 61.4% |

`all` 의 23.9%가 릴리스 1개짜리다 — `package.json` 에 peer 한 줄 써서 한 번 올리고 버려진 것들이라
대체 후보로서 의미가 없다. 실제로 쓰이는 것(상위 10만)은 **3.6%뿐**이다.

`recent` 하한이 잘 듣는다. 65.3%를 남기면서 **상위 10만 패키지는 85.8%를 지킨다.**
3년 넘게 방치된 것은 `all` 의 41.1% 인데 `recent` 에서는 9.8% 로 줄어든다.

그래도 `recent` 안에 릴리스 1개짜리가 121,017개(22.8%) 남는다. 더 끊으려면 `n_releases >= 2` 를
추가로 걸면 된다. 어디서 끊을지는 용도마다 다르므로 여기서 하나로 정하지 않고 열로 줬다.

### 6-2. 2026-09-15 정정 — 가짜 패키지 219,299행을 뺐다

**첫 판(`package-peers-20260915-v1`)의 `all` 1,033,323행 중 219,299행(21.2%)은 실제 패키지가
아니었다.** `@winglang/sdk>0.76.19>cdktf>safe-buffer` 처럼 deps.dev 가 번들된 중첩 의존성의
**경로**를 노드로 담은 것들이다. npm 이름에 `>` 는 쓸 수 없다.

`versions_full` 고유 이름 1,138만 중 705만(61.9%)이 이 형태이고, 그 7,052,193행은 **전부**
`published_at` 이 NULL 이다(정상 패키지는 430행만 NULL). 그래서 최신 릴리스 판정에
`published_at IS NOT NULL` 을 더해 걸러냈다 — S15P21A506-283 의 `unknown_published_at=exclude`
와 같은 기준이다. 모집단이 1,108만에서 406만으로 줄어든 것이 이 때문이고, 406만이 npm 실제
패키지 수와 맞는다.

이 문서는 전에 그 219,299행을 **"릴리스 1개짜리 방치 패키지"** 로 설명했다. 틀린 해석이었다.
`recent` 파일만 깨끗했던 것은 `--recent-since` 하한이 NULL 을 함께 떨궜기 때문이지 설계가
막은 것이 아니다 — **하한을 끄거나 낮췄으면 그대로 들어왔다.**

`pairs` 모드(§1~5)는 영향이 없다. 쌍 목록에 이런 이름이 없어 대상 필터가 이미 걸렀고,
재계산해도 패키지 57,820 · 쌍 53,155 · parquet 886,041바이트로 **모두 동일**했다.

### 6-3. 넓혀도 변하지 않는 것

비교 가능 비율은 올라가지 않는다. peer 보유율이 20.0%이므로 **임의의 두 패키지가 양쪽 다 peer 를
가질 확률은 0.20² ≈ 4%** 다. §4 에서 쌍 단위 비교 불가가 60%였던 것은 이동쌍이 이미 관련
패키지끼리 묶인 덕에 오히려 좋은 편이었다는 뜻이다.

(이 보유율은 2026-09-15 정정 후 값이다. 가짜 노드가 섞여 있던 첫 판에서는 모집단이 부풀어
9.3%로 보였다. 분자·분모가 함께 바뀌어 비율이 오른 것이지 peer 를 쓰는 패키지가 늘어난 것이 아니다.)

전수로 넓혀서 얻는 것은 "미리 만든 쌍 목록에 없는 조합도 대응된다"는 점이지, 판정 가능한 비율이
높아지는 것이 아니다.

## 7. 참고

- 배경·후보 선정 근거: `../feature_candidates_260908/README.md` §1-3
- 비교 대상 쌍: `../migration_pairs_260908/`, `../migration_pairs_dev_260914/`, `../deprecated_replacement_260831/`
- 빌더: `pipeline/duckdb/build_peer_similarity.py`
- MinIO 입고: `pipeline/minio/ingest_derived.py --dataset peer-similarity`
