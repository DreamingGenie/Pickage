# 패키지별 dependents — 확장 대상 46.9만 회차

작성 2026-09-22 (S15P21A506-454) · 원천 deps.dev BigQuery 2026-08-31 스냅샷 · 생성 스크립트
`pipeline/duckdb/build_package_dependents.py` (93초)
대상 목록 `../targets/expanded_468k_20260922.csv` (헤더 제외 **468,519개**)

## 0. 기본 회차와 무엇이 다른가

**대상 목록만 다르다. 계산은 같다.** 열 의미·사용법·한계 10가지는 전부
[`../package_dependents_260915/README.md`](../package_dependents_260915/README.md)를 보고,
이 문서는 차이만 적는다.

| | 기본 회차 (S15P21A506-354) | 이 회차 |
|---|---|---|
| 대상 | 다운로드 상위 10만 (99,996) | 확장 목록 **468,519** |
| 그중 상위 10만 밖 | 0 | **368,523 (78.7%)** |
| 행 | 299,988 | **1,405,557** (= 468,519 × 3종) |
| parquet | 104,143,713 바이트 | **114,695,681 바이트** |
| 엣지 | 13,392,517 | **14,496,162** (+1,103,645 · 8.2%) |
| 빌드 | 94초 | 93초 |

**기본 회차를 지우지 않는다.** 이 회차는 그 옆에 선다 — 같은 티켓의
`dependent_transitions_exp460k_260922` 가 표를 전량 교체하는 **대체** 회차인 것과 다르다.
그래서 MinIO 에서도 prefix 를 나눴다(§1).

## 1. 파일

| 파일 | 내용 | 행 |
|---|---|---:|
| `data/package_dependents_exp460k_260922/package_dependents.parquet` (git 미추적) | **본체.** `(name, kind)` 1행 — `dependents[]` 배열 | 1,405,557 |
| `dependents_summary.csv` (**git 미추적**) | 배열을 뺀 요약 (UTF-8 BOM) · 50,024,699 바이트 | 1,405,557 |
| `stats.json` | 아래 수치의 원본 | |

> **요약 CSV 는 추적하지 않는다.** 50 MB 라 `../README.md` 의 "수십 MB 이상, 재생성 가능한
> 것은 `data/` 에 두고 공유한다" 규칙에 걸린다(현재 추적 중인 가장 큰 CSV 가 기본 회차의
> 13.4 MB). 빌더를 93초 다시 돌리면 나온다 — §5. `.gitignore` 에 이 파일 한 줄이 있다.

열 구성은 기본 회차와 **완전히 같다** (7개).

```text
pickage-curated/depsdev/v1/package-dependents-exp460k/snapshot=2026-08-31/
  run_id=package-dependents-exp460k-20260922-v1/
    data/package_dependents.parquet    114,695,681 바이트 · 1,405,557행
                                       SHA-256 8e6f91f9…
    run_manifest.json                  SHA-256 81b4ba34…
    _SUCCESS
```

**2026-09-22 입고 완료.** 올린 뒤 객체를 통째로 다시 내려받아 해시를 대조했다(MATCH).
이 회차는 PostgreSQL 로 가지 않는다 — 버킷에만 있고 쓰는 쪽이 직접 읽는다.

기본 회차(`depsdev/v1/package-dependents/`)와 **prefix 를 나눴다.** 계산은 같고 대상 모집단만
다른 회차이고 **둘 다 살아 있어** 받는 쪽이 하나를 골라야 하므로,
`package-dependents-candidate-pool` 과 같은 판단이다.

```bash
python -m pipeline.minio.ingest_derived --dataset package-dependents-exp460k \
  --run-id package-dependents-exp460k-20260922-v1
```

## 2. 규모

| kind | dependents ≥ 1인 대상 | 엣지 | 최대 | p50 / p90 / p99 |
|---|---:|---:|---:|---:|
| `regular` | 185,319 | 12,522,208 | 192,736 (`react`) | 0 / 10 / 299 |
| `peer` | 39,444 | 1,923,938 | 344,357 (`react`) | 0 / 0 / 18 |
| `optional` | 11,738 | 50,016 | 3,399 | 0 / 0 / 1 |

- 세 종류 모두 dependents 가 0 인 대상: **272,890** (기본 회차 15,050)
- `package_exists = false`: **8,729** (기본 회차 2,251 — 뜻은 기본 회차 README §4-9)
- ecosyste.ms 대조: **65,307개에서 중앙 비율 0.710** — 기본 회차와 **같은 수**다.
  대조는 `ecosystems_dependent_count` 가 있는 대상만 하는데 그 값이 상위 10만 표에서만
  오므로, 목록을 넓혀도 대조 대상이 늘지 않는다.

**분위수가 기본 회차보다 낮다**(regular p50 5 → 0). 넓힌 대상 대부분이 의존자가 없어서다.
분위수를 두 회차 사이에 비교하지 말 것 — 모집단이 다르다.

## 3. 검증 — 겹치는 값이 기본 회차와 같은가

대상 목록만 다르고 계산이 같으므로, 두 회차에 **겹치는 대상의 값은 같아야 한다.**

```
겹치는 행             299,988   (기본 회차 전부. 빠진 것 0)
개수 불일치                 0
목록 불일치                 0    ← dependents 배열 원소까지 대조
download_rank 불일치         0
ecosystems_dependent_count   0
package_exists 불일치        0
```

일곱 열이 **한 자리도 다르지 않다.** 같은 입력으로 두 번 돌려 **바이트까지 같은 것**
(114,695,681, SHA-256 `8e6f91f9…`)도 확인했다.

## 4. 넓힌 368,523개

| | 상위 10만 (99,996) | 넓힌 368,523 |
|---|---:|---:|
| 의존자가 하나라도 있는 대상 | 84,946 (85.0%) | **110,683 (30.0%)** |

엣지 증가분 1,103,645 는 이 회차 전체 1,449만의 7.6% 다. **순위 밖 패키지의 dependents 는
대체로 작다** — 넓힌 쪽이 대상의 78.7% 를 차지하면서 엣지는 7.6% 다.
수가 아니라 **이름이 필요해서** 넣는 쪽에 가깝다(보완재 감점 관문 S15P21A506-173).

**이 368,523개는 `download_rank` 와 `ecosystems_dependent_count` 가 NULL 이다.** 값을 구하지
못한 것이 아니라 상위 10만 표에 없는 패키지라서이고, NULL 자체가 "순위 밖"이라는 사실이다.
두 열은 대상 목록이 무엇이든 항상 `../targets/rank_top100k_20260902.csv` 에서 조인해 온다.

`package_exists = false` 가 2,251 → 8,729 로 는 것도 넓힌 쪽 때문이다. 이 값은
`dependent_transition` 을 PostgreSQL 에 적재할 때 **이름이 안 붙는 대상 수**를 그대로 정한다
(기본 회차에서 2,251 × 3종 × 3구간 = 20,259행이 빠져 97.7% 였다).

## 5. 다시 만들기

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_package_dependents.py \
  --targets datasets/targets/expanded_468k_20260922.csv --label exp460k_260922
```

93초. 같은 입력으로 두 번 돌려 바이트까지 같은 것(114,695,681, SHA `8e6f91f9…`)을 확인했다.
`ORDER BY` 에 `name` 이 들어 있어 `download_rank` 가 NULL 인 대상이 78.7% 인 이 목록에서도
재현된다 — 근거는 `../package_dependents_candidate_pool_260916/README.md` §5 의 재현성 주의.
