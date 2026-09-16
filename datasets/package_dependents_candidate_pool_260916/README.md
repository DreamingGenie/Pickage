# 패키지별 dependents — AI 후보 풀 회차

작성 2026-09-16 (S15P21A506-359) · 원천 deps.dev BigQuery 2026-08-31 스냅샷 · 생성 스크립트 `pipeline/duckdb/build_package_dependents.py` (86초)
대상 목록 `../targets/candidate_pool_260916.csv` (AI 파트 제공, 헤더 제외 29,310개)

## 0. 기본 회차와 무엇이 다른가

**대상 목록만 다르다. 계산은 같다.** 열 의미·사용법·한계 10가지는 전부
[`../package_dependents_260915/README.md`](../package_dependents_260915/README.md)를 보고, 이 문서는 차이만 적는다.

| | 기본 회차 (S15P21A506-354) | 이 회차 |
|---|---|---|
| 대상 | 다운로드 상위 10만 (99,996) | AI 후보 풀 **29,310** |
| 그중 상위 10만 밖 | 0 | **11,297 (38.5%)** |
| 행 | 299,988 | **87,930** (= 29,310 × 3종) |
| parquet | 104 MB | **61,553,105 바이트** |

기본 회차로는 이 요청에 답할 수 없어서 따로 낸다 — 후보 풀의 38.5%가 그 대상 밖이었다.

## 1. 파일

| 파일 | 내용 | 행 |
|---|---|---:|
| `data/package_dependents_candidate_pool_260916/package_dependents.parquet` (git 미추적) | **본체.** `(name, kind)` 1행 — `dependents[]` 배열 | 87,930 |
| `dependents_summary.csv` | 배열을 뺀 요약 (UTF-8 BOM) | 87,930 |
| `stats.json` | 아래 수치의 원본 | |

열 구성은 기본 회차와 **완전히 같다.**

parquet 은 2026-09-16 서버 MinIO 에 올렸다. 접속은 `pipeline/minio/README.md` 의 터널 절차를 따른다.

```text
pickage-curated/depsdev/v1/package-dependents-candidate-pool/snapshot=2026-08-31/
  run_id=package-dependents-candidate-pool-20260916-v1/
    data/package_dependents.parquet    61,553,105 바이트 · 87,930행
    run_manifest.json                  SHA-256 dcced741… · 행 수
    _SUCCESS
```

기본 회차(`depsdev/v1/package-dependents/`)와 **prefix 를 나눴다.** 계산은 같고 대상 모집단만
다른 회차라, 같은 prefix 에 `run_id` 로만 구분해 두면 받는 쪽이 어느 것이 무엇인지 알 수 없다.

## 2. 규모

| kind | dependents ≥ 1인 대상 | 엣지 | 최대 | p50 / p90 / p99 |
|---|---:|---:|---:|---:|
| `regular` | 26,884 | 6,363,644 | 192,736 (`react`) | 9 / 145 / 3,444 |
| `peer` | 11,155 | 1,475,824 | 344,357 (`react`) | 0 / 14 / 349 |
| `optional` | 2,487 | 21,431 | 777 | 0 / 0 / 12 |

- 세 종류 모두 dependents 가 0 인 대상: **2,036**
- `package_exists = false`: **151** (뜻은 기본 회차 README §4-9 — "npm 에 없다"가 아니다)
- ecosyste.ms 대조: 17,538개에서 중앙 비율 **0.833**

## 3. 검증 — 겹치는 값이 기본 회차와 같은가

대상 목록만 다르고 계산이 같으므로, 두 회차에 **겹치는 패키지의 값은 같아야 한다.**
다르면 둘 중 하나가 잘못된 것이다.

```
겹치는 행      54,039   (= 18,013 패키지 × 3종)
개수 불일치         0
목록 불일치         0    ← dependents 배열 원소까지 대조
```

요청 목록 29,310개 중 **빠진 것 0**이다.

## 4. 상위 10만 밖 11,297개

이 회차를 따로 낸 이유다. 실제로 값이 나온다.

```
의존자가 있는 것   9,655 / 11,297
엣지 합              96,543
최대                  2,326  (insta-fetcher)
```

**이 11,297개는 `download_rank` 와 `ecosystems_dependent_count` 가 NULL 이다.** 값을 구하지
못한 것이 아니라 상위 10만 표에 없는 패키지라서이고, NULL 자체가 "순위 밖"이라는 사실이다.
두 열은 대상 목록이 무엇이든 항상 그 표에서 조인해 온다.

순위 밖 패키지의 dependents 는 대체로 작다 — 엣지 합 96,543 은 이 회차 전체 786만의 1.2% 다.
후보 풀에서 이들이 차지하는 비중이 38.5% 인 것과 견주면, **수가 아니라 이름이 필요해서**
넣는 쪽에 가깝다.

## 5. 다시 만들기

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_package_dependents.py \
  --targets datasets/targets/candidate_pool_260916.csv --label candidate_pool_260916
```

86초. 같은 입력으로 두 번 돌려 **바이트까지 같은 것**(61,553,105, SHA `dcced741…`)을 확인했다.

> **재현성 주의** — 이 회차를 만들면서 `ORDER BY` 에 `name` 을 넣었다. 그 전에는
> `download_rank, kind` 로만 정렬했는데, 순위 밖 33,891행의 `download_rank` 가 전부 NULL 이라
> 동순위가 되어 **실행마다 행 순서가 달라졌다**(같은 입력으로 61,674,812 / 61,674,384 /
> 61,673,694 바이트). 내용은 같았지만 파일이 재현되지 않았다. 상위 10만 대상만 쓸 때는
> 순위가 유일해서 드러나지 않던 문제다.
