# 유지·유입·이탈 — 확장 대상 46.9만 회차

작성 2026-09-22 (S15P21A506-454) · 원천 deps.dev BigQuery **2026-08-31 스냅샷** · 생성 스크립트
`pipeline/duckdb/build_dependent_transitions.py` (173초)
대상 목록 `../targets/expanded_468k_20260922.csv` (**468,519개**, 중복 이름 없음)

## 0. 기본 회차와 무엇이 다른가

**대상 목록만 다르다. 계산은 같다.** 범주 정의·열 의미·한계 여섯 가지는 전부
[`../dependent_transitions_260917/README.md`](../dependent_transitions_260917/README.md)를 보고,
이 문서는 차이와 이 회차의 실측만 적는다.

| | 기본 회차 (S15P21A506-195·-421) | 이 회차 |
|---|---|---|
| 대상 | 다운로드 상위 10만 (99,996) | 확장 목록 **468,519** |
| 그중 상위 10만 밖 | 0 | **368,523 (78.7%)** |
| 행 | 899,964 | **4,216,671** (= 468,519 × 3종 × 3구간) |
| parquet | 6,365,780 바이트 | **18,922,201 바이트** |
| 선언 전개 | 37,233,186 | 40,090,346 |
| 빌드 | 167초 | 173초 |

**계산 비용이 대상 수와 거의 무관하다.** 스냅샷 전체를 전개한 뒤 대상으로 거르는 구조라,
대상이 4.7배가 되어도 6초만 늘었다. 좁혀 둘 이유가 없어서 넓혔다.

> **이 회차는 기본 회차 옆에 서는 것이 아니라 그것을 대체한다.** `dependent_transition`
> 표를 전량 교체하고 `etl_dataset_current` 의 `dependent-transitions` 한 행이 이것을 가리킨다.
> 그래서 MinIO 에서도 **prefix 를 나누지 않고 같은 경로에 새 `run_id` 로** 넣는다.
> `package_dependents_candidate_pool_260916` 이 prefix 를 나눈 것과 다른 이유는 §1 에 적었다.

## 1. 파일

| 파일 | 내용 | 행 |
|---|---|---:|
| `data/dependent_transitions_exp460k_260922/dependent_transitions.parquet` (git 미추적) | **본체.** `(period, target, kind)` 1행 · 18,922,201 바이트 | 4,216,671 |
| `transitions_summary.csv` | **상위 5,000 대상만** 담은 표본 (UTF-8 BOM) | 45,000 |
| `stats.json` | 아래 수치의 원본 · 검산 결과 | |

> **CSV 는 전체가 아니다.** 상위 5,000개 대상(= 45,000행)만 담았다. 전체 4,216,671행은 약
> 380 MB 라 `../README.md` 의 "수십 MB 이상, 재생성 가능한 것은 `data/` 에 두고 공유한다"
> 규칙에 걸린다. **CSV 로 합계를 내면 전체가 아니다.** 나머지 463,519개 대상은 parquet
> 에만 있다. 잘린 수는 `stats.json` 의 `csv_targets` 가 말한다.

MinIO 는 기존 prefix 에 회차만 늘린다. 접속은 `pipeline/minio/README.md` 의 터널 절차를 따른다.

```text
pickage-curated/depsdev/v1/dependent-transitions/snapshot=2026-08-31/
  run_id=dependent-transitions-20260917-v1/       상위 10만 · 분해 이전
  run_id=dependent-transitions-20260921-v1/       상위 10만 · 분해 포함
  run_id=dependent-transitions-exp460k-20260922-v1/   ← 이 회차 (확장 46.9만)
    data/dependent_transitions.parquet   18,922,201 바이트 · 4,216,671행 (열 15개)
                                         SHA-256 a1b94b51…
    run_manifest.json                    SHA-256 7ac3cbfd… · dataset "dependent-transitions"
    _SUCCESS
```

**2026-09-22 입고 완료.** 올린 뒤 객체를 통째로 다시 내려받아 해시를 대조했다(MATCH).
입고기 자체도 업로드마다 GET 해 대조하므로 두 번 확인한 셈이다. 옛 회차 둘은 건드리지
않았다. 이 데이터셋은 포인터를 쓰지 않아 `_current.json` 이 없다 — 어느 회차를 게시할지는
`load.py` 에 사람이 명시한다.

**같은 prefix 를 쓰는 이유.** `pipeline/dependent_transitions/load.py` 가 경로와 manifest 의
`dataset` 을 상수 하나(`"dependent-transitions"`)로 고정하고, 그 이름이 `etl_dataset_current`
의 기본 키이기도 하다. 대체 회차가 다른 이름을 쓰면 포인터가 옮겨갈 자리가 없다.
`ingest_derived.py` 의 항목은 따로 만들되(`root`·`source`·`notes` 가 회차마다 달라야 한다)
`dataset_name` 으로 manifest 의 이름만 빌려 쓴다.

올릴 때는 `PICKAGE_MINIO_ENV=.env.server` 를 주고 아래를 실행한다.

```bash
python -m pipeline.minio.ingest_derived --dataset dependent-transitions-exp460k \
  --run-id dependent-transitions-exp460k-20260922-v1
```

## 2. 열

기본 회차와 **완전히 같다** (15개). 뜻은
[`../dependent_transitions_260917/README.md` §2](../dependent_transitions_260917/README.md)에 있다.

`download_rank` 와 `in_top100k` 는 대상 목록이 무엇이든 언제나
`../targets/rank_top100k_20260902.csv` 에서 조인해 온다. 그래서 넓힌 368,523개는 두 값이
NULL·`false` 이고, **NULL 자체가 "순위 밖"이라는 사실이다.** 값을 못 구한 것이 아니다.

## 3. 검증 — 겹치는 10만의 값이 기본 회차와 같은가

대상 목록만 다르고 계산이 같으므로, 두 회차에 **겹치는 대상의 값은 같아야 한다.**
다르면 둘 중 하나가 잘못된 것이다.

```
겹치는 대상            99,996   (기본 회차 전부. 빠진 것 0)
겹치는 행             899,964
기본 − 이 회차              0   ← 열 15개 그대로 EXCEPT ALL
이 회차 − 기본              0   ← 반대 방향도
```

`t1`·`t2`·`download_rank`·`in_top100k` 를 포함해 **한 자리도 다르지 않다.**

같은 입력으로 두 번 돌려 **바이트까지 같은 것**(18,922,201, SHA-256 `a1b94b51…`)도 확인했다.

### 3-1. 검산 다섯 가지

`stats.json` 에 값이 있다. 다섯 다 통과했다. 각 항목의 뜻은 기본 회차 README §5 에 있다.

| 항목 | 값 |
|---|---:|
| `impossible_change_without_move` | **0** |
| `conservation_t2_mismatch` | **0** |
| `conservation_t1_mismatch` | **0** |
| `inflow_new_exceeds_inflow` | **0** |
| `impossible_freshness` | **0** |

## 4. 수치 — 이 회차(대상 468,519) 기준

> 아래 표는 전부 **확장 대상 468,519개** 기준이다. 기본 회차 README §4 의 같은 표는
> **상위 10만 기준**이라 값이 다르다. 두 표의 수를 섞어 쓰지 말 것.

| 구간 | 유지 | 유입 | 이탈 | 관측 불가 | 관측 불가 비중 |
|---|---:|---:|---:|---:|---:|
| `1y` | 981,355 | 2,340,929 | 140,938 | 11,173,705 | **76.3%** |
| `3y` | 923,487 | 6,702,355 | 201,960 | 6,870,147 | 46.7% |
| `5y` | 723,272 | 9,384,361 | 191,137 | 4,388,356 | 29.9% |

### 4-1. 관측 불가를 유지로 세면 숫자가 거짓이 된다

| 구간 | 유지율 (관측 가능만) | 관측 불가를 유지로 세면 |
|---|---:|---:|
| `1y` | **87.4%** | 98.9% |
| `3y` | **82.1%** | 97.5% |
| `5y` | **79.1%** | 96.4% |

상위 10만 기준(87.2 / 81.8 / 78.9%)과 0.2 %p 안에서 같다. **대상을 넓혀도 결론은 바뀌지
않는다** — 관측 불가의 원인이 대상이 아니라 dependent 쪽 릴리스 주기이기 때문이다.

### 4-2. 유입의 대부분은 채택이 아니라 생태계 성장이다

| 구간 | 유입 | 그중 신생 | 신생 비중 | **전환 유입** | 이탈 |
|---|---:|---:|---:|---:|---:|
| `1y` | 2,340,929 | 2,191,355 | **93.6%** | **149,574** | 140,938 |
| `3y` | 6,702,355 | 6,472,586 | **96.6%** | **229,769** | 201,960 |
| `5y` | 9,384,361 | 9,158,070 | **97.6%** | **226,291** | 191,137 |

신생을 빼면 1년 구간에서 149,574 대 140,938 으로 거의 같다. **유입 절대수를 "인기 상승"
으로 읽으면 안 된다.**

### 4-3. 1년 구간 kind 별

| kind | 유지 | 유입 | 그중 신생 | 이탈 | 관측 불가 |
|---|---:|---:|---:|---:|---:|
| `regular` | 797,757 | 1,790,059 | 1,682,483 | 126,273 | 9,934,281 |
| `peer` | 179,164 | 527,907 | 488,019 | 13,774 | 1,216,809 |
| `optional` | 4,434 | 22,963 | 20,853 | 891 | 22,615 |

### 4-4. 관측 불가 분해

| 구간 | 관측 불가 | 3년 안 | 3~5년 전 | **5년 초과** |
|---|---:|---:|---:|---:|
| `1y` | 11,173,705 | 4,303,558 (38.5%) | 2,481,791 (22.2%) | **4,388,356 (39.3%)** |
| `3y` | 6,870,147 | 0 | 2,481,791 (36.1%) | **4,388,356 (63.9%)** |
| `5y` | 4,388,356 | 0 | 0 | **4,388,356 (100%)** |

3년·5년 구간의 빈 칸은 결함이 아니라 정의다 — 근거는 기본 회차 README §4-4.

## 5. 넓혀서 무엇을 얻었나

| | 상위 10만 (99,996) | 넓힌 368,523 |
|---|---:|---:|
| 네 수가 하나라도 0 이 아닌 대상 | 86,015 (86.0%) | **112,661 (30.6%)** |
| 1년 구간 유지 | 917,692 | 63,663 |
| 1년 구간 유입 | 2,293,274 | 47,655 |
| 1년 구간 이탈 | 134,356 | 6,582 |
| 1년 구간 관측 불가 | 10,181,383 | 992,322 |

**넓힌 쪽의 수는 작다.** 1년 구간 전체에서 넓힌 대상이 차지하는 비중은 유지 6.5% ·
유입 2.0% · 이탈 4.7% 다. 그럼에도 넓히는 이유는 합계가 아니라 **개별 조회**다 —
사용자가 순위 밖 패키지를 물었을 때 "범위 밖"이 아니라 수를 돌려줄 수 있는 대상이
112,661개 늘었다.

나머지 255,862개는 행은 있으나 네 수가 전부 0 이다. **이것도 "조회 실패"가 아니라
"dependent 가 없다"는 답이고, 앞 회차에서는 그 구분조차 할 수 없었다.**

> **넓힌 목록에는 스팸·타이포스쿼트 군집이 섞여 있다.** 1년 구간 T2 선언자가 많은 순으로
> 보면 `rylie` 26,854 · `anakjalanan` 26,661 처럼 서로를 대량으로 선언하는 이름들이 위에
> 온다. 이 회차는 그것을 거르지 않는다 — 대상 목록(`../targets/expanded_468k_20260922.csv`)
> 이 정하는 문제이고, 거르려면 그 목록 쪽에서 판정해야 한다.

## 6. 한계

기본 회차 README §6 의 여섯 가지가 **그대로 적용된다** (MVP `delta` 와 다른 지표 ·
devDependencies 없음 · 생존 편향 · 대상 밖은 알 수 없음 · 대표 릴리스 규칙).
"대상 밖" 의 경계만 10만에서 46.9만으로 옮겨갔을 뿐이다.

### 6-1. `package_dependents_exp460k_260922` 와 144행 어긋난다

`retained + inflow + unobserved` 는 T2 에 그 대상을 선언한 dependent 수이므로 저쪽
`n_dependents` 와 같아야 한다. 1,405,557행 중 **144행이 다르다(0.010%).**
**132행은 이쪽이 작고(최대 차 10), 12행은 이쪽이 크다(최대 차 1).**

기본 회차의 136행과 **같은 원인**이다 — `versions_full` 의 `snapshot=2026-08-31` 파티션에
2026-09-01 발행분이 섞여 있고, `build_package_dependents.py` 는 컷오프 없이 전체 ordinal
최대를 대표로 쓰는데 이 빌더는 `published_at <= T2` 를 건다. 자세한 실측은 기본 회차
README §6-5 에 있다. **스냅샷 경계를 지키는 쪽은 이 데이터셋이다.**

`react` 가 그 예다.

| kind | 이 데이터셋 T2 선언자 | `package_dependents_exp460k` |
|---|---:|---:|
| `regular` | 192,736 | 192,736 |
| `peer` | 344,347 | **344,357** |
| `optional` | 467 | 467 |

### 6-2. 이 회차를 적재하면 `dependent_removal_reason` 의 범위가 낡는다

`pipeline/removal_reasons/load.py` 는 **적재 범위를 `dependent_transition` 에서 조인해
가져온다**(`SCOPE_TABLE`). 유지·유입·이탈만 46.9만으로 바꾸면 같은 패키지에서 한 패널은
수를 말하고 이탈 사유 패널은 "범위 밖"을 말한다.

**이 회차를 게시한 뒤 `removal-reasons` 를 재적재한다.** 순서가 있다 — 그쪽 적재기는
`dependent_transition` 이 비어 있으면 중단하고, 범위를 그 표에서 읽으므로 먼저 이쪽이
새 회차여야 한다. 원천 parquet 은 이미 X 13.2만 종을 담고 있어 **다시 계산할 필요는 없고
재적재만 하면 된다.**

## 7. 다시 만들기

```bash
.venv-bq/Scripts/python.exe pipeline/duckdb/build_dependent_transitions.py \
  --targets datasets/targets/expanded_468k_20260922.csv --label exp460k_260922
```

8스레드·40GB 로 173초. `--targets` 를 바꿀 때는 `--label` 을 함께 준다 — `--label` 없이
`--targets` 만 주면 빌더가 거부한다(기본 회차 산출물을 조용히 덮어쓰는 사고를 막는다).

같은 입력으로 두 번 돌려 바이트까지 같았다(18,922,201, SHA-256 `a1b94b51…`).
`ORDER BY` 에 `target` 이 들어 있어, 순위 밖 대상이 78.7% 인 이 목록에서도 재현된다 —
`download_rank` 만으로는 전부 NULL 이라 동순위가 생긴다(2026-09-16 -359 실측).

> **같은 출력 경로에 두 실행을 겹치지 말 것.** 빌더는 고정된 이름으로 `COPY` 하므로
> 두 프로세스가 동시에 돌면 끝에서 같은 파일에 쓴다. 회차를 나누려면 `--label` 을 준다.

## 8. 운영 적재 — 실행 묶음 (2026-09-22)

MinIO 입고는 끝났다(§1 의 경로, 원격 GET SHA `a1b94b51…` MATCH). 남은 것은 PostgreSQL 이다.

**PC 에서 돌리고 서버의 psql 만 원격으로 쓴다.** 왜 서버에 들어가서 못 도는지는
`pipeline/dependent_transitions/load.py` 의 "운영에 게시하기" 절에 있다.

> **회차를 이미 받아 뒀으므로 19000 터널이 필요 없다.** 아래 네 명령 모두 `--run-dir` 로
> 로컬 디렉터리를 가리킨다. 필요한 것은 `DOCKER_HOST='ssh://a506app'` 뿐이다.
>
> **이 브랜치가 있는 트리에서 돌린다** (작업 당시 worktree `C:\git\S15P21A506-454`).
> 적재기가 `contract_sha256` 에 `db/migration/V*.sql` 목록을 넣으므로, 낡은 트리에서
> 돌리면 그 시점 develop 에 없던 마이그레이션이 빠져 etl 이력의 계약 해시가 달라진다.
> 이 회차를 준비할 때의 트리는 `V12` 까지였다.
>
> **네 단계를 도는 중에는 그 트리를 rebase 하지 말 것.** `contract_sha256()` 이 적재기
> 디렉터리의 `*.py` 와 `backend/src/main/resources/db/migration/V*.sql` **전체**를 해시하므로,
> 도중에 새 마이그레이션이 들어오면 검증과 게시가 서로 다른 계약 해시로 남는다. 동작은
> 바뀌지 않지만 etl 이력에서 "같은 것을 검증하고 게시했다" 를 말할 수 없게 된다.
>
> ⚠ **출력을 파일로 리다이렉트하지 말 것.** Windows 에서 인코딩이 cp949 로 정해져 한글 한
> 글자에 프로세스가 죽는다. `psql.log` 는 적재기가 UTF-8 로 따로 남긴다.

**순서는 하나만 지키면 된다 — 적재에 쓸 트리를 먼저 정하고, 그 뒤에 다른 것을 움직인다.**
MR push·rebase·머지는 그 트리를 고정한 뒤라면 언제 해도 상관없다. 반대로 1단계를 돌린 뒤
rebase 하고 2단계를 돌리면 위의 계약 해시가 어긋난다. 네 단계를 먼저 끝내고 나머지를
움직이는 쪽이 가장 헷갈리지 않는다.

각 명령은 PowerShell 에 **한 줄로** 넣는다. 경로에 `--run-dir` 은 Windows 경로로 준다 —
Git Bash 에서 `MSYS_NO_PATHCONV=1` 과 POSIX 경로를 같이 주면 `C:\c\git\…` 로 해석된다
(2026-09-22 실측).

### 1단계 — 유지·유입·이탈 검증 (DB 를 바꾸지 않는다)

```powershell
cd C:\git\S15P21A506-454; $env:DOCKER_HOST='ssh://a506app'; C:\git\S15P21A506\.venv-bq\Scripts\python.exe -m pipeline.dependent_transitions.load --snapshot 2026-08-31 --run-id dependent-transitions-exp460k-20260922-v1 --run-dir C:\git\S15P21A506\data\dependent_transitions_load\runs\2026-08-31_dependent-transitions-exp460k-20260922-v1 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage --verify-only
```

기대 출력 — 끝에 `검증만 하고 되돌렸다` 가 찍힌다.

기대값은 추정이 아니다. 운영 `package` 의 원천인 Curated 회차(`curated-20260907-v2`,
11,080,940행)가 로컬에 있어 **이름 조인을 미리 돌려 세었다.** 같은 방법으로 기존 10만 회차를
재면 미매칭 대상 2,251 · 적재 879,705행이 나오는데, 그것이 2026-09-17·18 실적재에 남은
값과 정확히 같다. 그래서 아래는 "약" 이 아니다.

| 항목 | 기대값 | 근거 |
|---|---:|---|
| `staged_rows` | 4,216,671 | 산출물 전량 |
| `loaded_rows` | **4,138,029** | 이름 조인 실측 |
| 빠질 행 | **78,642** | = 8,738 × 3종 × 3구간 |
| `unresolved_targets` | **8,738** | `package` 에 이름이 없는 대상 |
| 매칭률 | **98.13%** | 기존 회차 97.7% 보다 높다 |

> **`package_dependents_exp460k` 의 `package_exists=false` 8,729 는 이 값이 아니다.**
> 같은 것을 재는 두 방법이 9 개 어긋난다 — 최신 릴리스가 있는데 Curated `package` 에는
> 없는 이름이 12 개(`@antora/assembler`·`easy-spec-mcp` 류의 최근·소형 패키지), 반대가
> 3 개다. 12 − 3 = 9. **적재에서 빠지는 수를 정하는 것은 `package` 쪽 8,738 이다.**
> 버킷 manifest 의 notes 에는 8,729 로 적혀 있는데, `notes` 를 고치면 manifest 바이트가
> 달라져 **이미 올라간 이 회차가 다시는 재검증으로 통과하지 못한다**(`put_once` 가 바이트를
> 비교한다). 그래서 버킷은 그대로 두고 정정을 이 문서에 둔다.

> **운영 `package` 는 로컬보다 조금 적다** — 2026-09-18 기록으로 11,062,172행(로컬 −18,768).
> 기존 회차에서는 그 차이가 대상 목록 밖이라 미매칭이 같았지만, 대상이 46.9만으로 넓어진
> 이 회차에서는 **그 차이의 일부가 대상 안에 들어올 수 있다.** 실제 `unresolved_targets` 가
> 8,738 보다 조금 클 수 있고, 그 방향이면 정상이다.

**95% 아래면 멈춘다.** 이름 규칙이 어긋났거나 `package` 가 다른 회차인 경우다.
`unobserved_freshness` 는 1y 세 칸이 모두 0 이 아니고 3y 의 recent, 5y 의 recent·stale 이
0 이어야 한다 — 정의상 그렇다(§4-4).

### 2단계 — 유지·유입·이탈 게시 (전량 교체)

1단계 명령에서 `--verify-only` 만 뺀다.

```powershell
cd C:\git\S15P21A506-454; $env:DOCKER_HOST='ssh://a506app'; C:\git\S15P21A506\.venv-bq\Scripts\python.exe -m pipeline.dependent_transitions.load --snapshot 2026-08-31 --run-id dependent-transitions-exp460k-20260922-v1 --run-dir C:\git\S15P21A506\data\dependent_transitions_load\runs\2026-08-31_dependent-transitions-exp460k-20260922-v1 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage
```

끝에 `게시 완료` 가 찍힌다. 수는 1단계와 같아야 한다.

**교체 전 상태 (되돌릴 때 필요하다)**

```
etl_dataset_current.dependent-transitions
  = dependent-transitions-2026-08-31-dependent-transitions-20260921-v1   manifest 0f4a5a1c…
etl_dataset_current.removal-reasons
  = removal-reasons-2026-08-31-migration-pairs-20260920-v1
dependent_transition 879,705행 · 242 MB → 약 414만 행 · 약 1.2 GB
```

전송 CSV 는 SSH 로 흘러가고 행이 4.7배라 기존 73 MB 의 4~5배(약 340 MB)다. 시간이 걸린다.

### 3단계 — 이탈 사유 검증 (**빼먹지 말 것**)

`pipeline/removal_reasons/load.py` 는 적재 범위를 `dependent_transition` 에서 조인해
가져온다(`SCOPE_TABLE`). 2단계만 하고 멈추면 같은 패키지에서 유지·유입·이탈 패널은 수를
말하고 이탈 사유 패널은 "범위 밖"을 말한다. **원천은 그대로 쓰고 재적재만 한다** —
원천 `removal_by_period` 가 이미 X 13.2만 종을 담고 있다.

```powershell
cd C:\git\S15P21A506-454; $env:DOCKER_HOST='ssh://a506app'; C:\git\S15P21A506\.venv-bq\Scripts\python.exe -m pipeline.removal_reasons.load --snapshot 2026-08-31 --run-id migration-pairs-20260920-v1 --run-dir C:\git\S15P21A506\data\removal_reasons_load\runs\2026-08-31_migration-pairs-20260920-v1 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage --verify-only
```

기대 — `scope_targets` 가 기존 4.3만에서 **크게 늘고** `out_of_scope_rows` 가 줄어든다.
적재 행은 기존 9.9만보다 **많아야 한다.** 줄어들면 2단계가 반영되지 않은 것이다.

### 4단계 — 이탈 사유 게시

3단계 명령에서 `--verify-only` 만 뺀다.

### 되돌리기

전량 교체라 옛 회차는 표에 남지 않는다. 되돌리려면 **옛 `run_id` 로 다시 적재한다.**
회차는 MinIO 에 그대로 있고 로컬에도 받아 둔 것이 있다.

```powershell
cd C:\git\S15P21A506-454; $env:DOCKER_HOST='ssh://a506app'; C:\git\S15P21A506\.venv-bq\Scripts\python.exe -m pipeline.dependent_transitions.load --snapshot 2026-08-31 --run-id dependent-transitions-20260921-v1 --run-dir C:\git\S15P21A506\data\dependent_transitions_load\runs\2026-08-31_dependent-transitions-20260921-v1 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage
```

그 뒤 3·4단계를 같은 `run_id` 로 한 번 더 돌려 이탈 사유의 범위도 되돌린다 — 범위를
`dependent_transition` 에서 읽으므로 전이를 되돌리면 자동으로 옛 범위가 나온다.

`execution_id` 는 `dataset-snapshot-run_id` 로 정해지므로 되돌린 적재는 옛 행을 갱신한다.
`etl_load_attempt` 에는 시도가 쌓여 남는다.
