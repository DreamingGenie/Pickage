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

## 6. 참고

- 배경·후보 선정 근거: `../feature_candidates_260908/README.md` §1-3
- 비교 대상 쌍: `../migration_pairs_260908/`, `../migration_pairs_dev_260914/`, `../deprecated_replacement_260831/`
- 빌더: `pipeline/duckdb/build_peer_similarity.py`
- MinIO 입고: `pipeline/minio/ingest_derived.py --dataset peer-similarity`
