# Pickage local MinIO

## MinIO를 사용하는 이유

MinIO는 S3 API로 파일을 저장하고 조회하는 객체 저장소다.
Pickage에서는 수집한 원본 Parquet와 이후 전처리·분석 결과를 보관하는 용도로 사용한다.
PostgreSQL의 테이블처럼 행을 직접 조회·수정하는 저장소가 아니라,
Parquet나 모델 파일을 객체 단위로 보관하는 저장소다.

- **원본 보존과 재사용**: 기존에 수집한 deps.dev Parquet를 보관해,
  전처리 규칙이 바뀌어도 BigQuery에서 다시 수집하지 않고 재처리할 수 있다.
- **원본과 결과 분리**: 원본은 그대로 두고 정제 결과·벡터·모델 산출물을 구분해 관리한다.
- **실행 결과 추적**: 데이터셋·스냅샷·실행 ID별 경로와 manifest로
  어떤 원본을 입고했는지, 검증이 완료됐는지 확인한다.
- **후속 처리의 입력 저장소**: 향후 Spark 등이 로컬 파일 경로 대신
  접근 가능한 객체 저장소 경로를 입력으로 사용하도록 준비한다.
  현재는 로컬 구성만 완료했으며, 여러 서버에서의 접근 설정과 Spark 연동은 아직 없다.

PostgreSQL에는 향후 서비스 조회에 필요한 `package`, `version` 등의 데이터를 적재하고,
MinIO에는 그 데이터를 만드는 원본과 중간·최종 파일을 보관할 예정이다.
MinIO를 실행하는 것만으로 전처리나 PostgreSQL 적재가 수행되지는 않는다.

## 버킷의 역할

버킷은 객체를 담는 최상위 저장 단위다. 버킷 안에서는 객체 이름의 경로(prefix)로
데이터셋과 실행 결과를 구분한다. 아래 역할은 Pickage의 저장 용도 구분이며,
현재 버킷별 접근 권한이나 보존 기간이 자동 설정되는 것은 아니다.

| 버킷 | 역할 | 저장 대상 | 현재 상태 |
| --- | --- | --- | --- |
| `pickage-raw` | Bronze 원본 보관 | 수집된 Parquet 원본, 원본·검증 manifest, 완료 표시 | deps.dev 데이터 입고 완료 |
| `pickage-curated` | 정제·가공 데이터 보관 | `package`·`version` 적재용 Parquet, ID 매핑, 품질 검증 결과, 빌더가 만든 파생 데이터셋 | 2026-08-31 스냅샷 전처리·저장·재검증 완료; [Curated 안내](../preprocessing/curated/README.md) 참고. `experiments/` 아래에 실험 산출물도 함께 들어 있다(아래 참고) |
| `pickage-vectors` | 벡터 산출물 보관 | 패키지 임베딩 기반 후보 색인, 패키지·모델 버전 연결 정보 | 후보 색인 1회차 게시(4객체 9.7 MiB). 벡터 검색 엔진 연동은 미구현 |
| `pickage-mlflow-artifacts` | 학습·실험 산출물 보관 | 학습한 모델 파일과 그 manifest | **모델 2벌 265.5 MiB 보관 중**(손 업로드, 경로 규약 밖 — 아래 참고). MLflow 서비스 연동은 미구현 |
| `pickage-quarantine` | 검증 실패 데이터 격리 | 향후 오류 레코드와 실패 사유 등 조사 대상 | 버킷 생성만 완료; 자동 격리 미구현 |

`pickage-vectors`는 벡터 파일 보관용이지 벡터 검색 엔진 자체가 아니다.
`pickage-mlflow-artifacts`도 MLflow 서비스나 실험 메타데이터 DB를 대신하지 않는다.
현재 입고 스크립트는 검증 실패 시 오류로 종료하며, 실패 데이터를
`pickage-quarantine`으로 자동 이동하지 않는다.

## 현재 진행 상황

**2026-09-18 서버 MinIO 전수 점검 기준이다.** 버킷 5개의 객체를 모두 나열해 개수와 바이트를
세었다(`list_objects_v2` 전수). 객체 내용의 해시를 다시 계산한 것은 아니다 — 입고 시 대조한
SHA-256 결과는 각 회차의 `run_manifest.json` 에 있다.

| 버킷 | 객체 | 바이트 |
| --- | ---: | ---: |
| `pickage-raw` | 15,291 | 47,058,739,230 (43.8 GiB) |
| `pickage-curated` | 2,467 | 24,203,130,244 (22.5 GiB) |
| `pickage-mlflow-artifacts` | 10 | 278,392,408 (265.5 MiB) |
| `pickage-vectors` | 4 | 10,148,650 (9.7 MiB) |
| `pickage-quarantine` | 0 | 0 |
| **합계** | **17,772** | **71,550,410,532 (66.6 GiB)** |

- [x] 루트 Compose에서 로컬 MinIO 실행 및 데이터 볼륨 관리
- [x] MinIO 준비 완료 후 없는 버킷만 자동 생성
- [x] 원본 사전 검증, 병렬 업로드, 업로드 후 SHA-256 비교 구현
- [x] 동일 실행 ID 재개 및 기존 객체 내용 불일치 시 실패 처리
- [x] deps.dev Bronze 데이터 입고 완료
- [x] `package`·`version` Curated 전처리 구현 및 로컬 전체 데이터 저장·재검증
- [x] 서버 MinIO 기동 및 로컬에서 터널로 적재하는 경로 (2026-09-09)
- [x] ecosyste.ms keywords 원본 서버 입고 (`keywords-20260909-v1`)
- [x] 파생 데이터셋 입고 경로 (`ingest_derived.py`) — 폐기→대체 데이터셋 서버 입고 (`deprecated-replacement-20260914-v1`)
- [x] `package_text` 서버 입고 (`package-text-20260908-v1`)와 `_current.json` 포인터 게시 —
      유사도 배치의 코퍼스 트리거 (2026-09-14)
- [x] npm registry 원본 입고 — 두 회차 모두 완료 (2026-09-16). `collected_date=2026-09-09`
      (`registry-20260909-v1`, 4,291 파일 · 765 MB) 와 `collected_date=2026-09-16`
      (`registry-20260916-v1`, 4,315 파일 · 988 MB, 샤드 4개). SHA-256 대조 실패 0건
- [x] npm downloads 원본 입고 — 백필(`downloads-278-20260909-v1`)과 주간 1회차(`downloads-weekly-20260914`)
- [x] 주간 갱신 1회차 실행 (`bronze-weekly-20260914`, 상태는 `pickage-raw/_ops/weekly/2026-09-14/run.json`,
      S15P21A506-273). 2026-09-18 01:11 UTC `SUCCEEDED`
- [x] 후보 색인 1회차 게시 (`pickage-vectors/model=v2/corpus=package-text-20260908-v1`, 후보 465,160행)
- [ ] PostgreSQL 적재
- [ ] Spark·벡터 검색 엔진·MLflow 서비스 연동
- [ ] 권한 분리(서비스 계정), 백업 및 자동 스케줄링

서버 MinIO는 루트 자격증명 하나를 함께 쓰는 상태다. 버킷별 권한을 가른 서비스 계정은
아직 없다. 지금은 적재하는 사람이 곧 버킷 전체를 지울 수 있는 사람과 같다.

입고 실행 ID: `bronze-20260907-v1`

| 항목 | 확인 결과 |
| --- | --- |
| 데이터셋 | `projects`, `pkg_project`, `requirements`, `versions_full` |
| 데이터셋별 스냅샷 묶음 | 총 232개 |
| Parquet 파일 | 3,231개 |
| 파일 크기 합계 | 33,443,300,362바이트 (약 33.44GB) |
| 원본 행 수 합계 | 1,098,457,021행 |
| 검증 상태 | 모든 run manifest가 `PASSED`, `GET_SHA256_ALL_FILES` |
| 완료 표시 | `_SUCCESS` 232개 |

행 수 합계는 서로 다른 데이터셋의 행을 합한 값이며, 패키지 수를 의미하지 않는다.
원본 파일과 실제 `.env`는 Git에 포함하지 않는다.

Curated 전처리는 위 Bronze 중 `2026-08-31` 스냅샷의 `versions_full`과
`requirements`를 입력으로 사용한다. 릴리스·배포일 필터, 패키지 ID 유지,
대표 저장소 선정, 표시용 의존성 JSON 변환을 수행한다.
실행 명령과 실제 검증 결과는 [Curated README](../preprocessing/curated/README.md)에 별도로 정리한다.
품질 사유 파일은 해당 Curated 실행의 `quality/`에 기록하며,
Bronze 원본을 변경하거나 `pickage-quarantine`으로 이동하지 않는다.
`curated-20260907-v2`에서 package 11,080,940행과 version 54,188,349행을 생성했고,
관리·품질 파일을 포함해 Parquet 44개(약 4.85GB)를 저장했다.

`package_text` 은 `package-text-20260908-v1` 로 Parquet 1개(86,159,593바이트·922,322행)를
`pickage-curated` 의 `ecosystems-keywords/v1/package-text/collected_date=2026-09-08/` 아래에
넣고, prefix 루트에 `_current.json` 을 게시했다. 로컬 파일명은 `package_text_2026-09-08.parquet`
이지만 **업로드 객체는 `package_text.parquet`** 이다 — 유사도 배치가
`--package-text /work/in/package_text.parquet` 으로 이름을 고정해 받는다. 같은 실행 ID로
재실행해 객체가 늘지 않고 포인터가 `unchanged` 로 유지되는 것을 확인했다.

파생 데이터셋은 `deprecated-replacement-20260914-v1` 로 폐기→대체 데이터셋
Parquet 1개(2,839,460바이트·28,241행)를 서버 `pickage-curated` 에 넣었다. 같은 실행 ID로
재실행해 객체가 늘지 않고 해시 재검증만 통과하는 것을 확인했다. 같은 버킷의
`migration-pairs-20260909-v1`(Parquet 3개)은 이 경로가 생기기 전에 손으로 올린 것이라
`run_manifest.json` 형태가 조금 다르다.

`migration-pairs-dev-20260914-v1` 로 **개발용 의존 기준** 이동쌍 Parquet 3개(5,869,061바이트·
273,777행)를 넣었다(S15P21A506-349). 같은 실행 ID로 재실행해 객체가 늘지 않고 해시 재검증만
통과하는 것을 확인했다. 이것은 deps.dev 가 아니라 npm registry 수집분에서 나왔으므로
`depsdev/v1` 이 아니라 **`npm-registry/v1/migration-pairs-dev/`** 아래에 있고, 경로의
`snapshot=2026-09-09` 는 deps.dev 스냅샷이 아니라 원천이 된 registry 수집 실행 날짜다.
위 `migration-pairs-20260909-v1`(실행용 의존·npm 전수)과는 **모집단이 달라 수치를 더하거나
lift 를 비교하면 안 된다** — `datasets/migration_pairs_dev_260914/README.md` §5.

`peer-similarity-20260914-v1` 로 대체 후보 peer 의존 유사도 Parquet 2개(2,266,490바이트·110,975행)를
`depsdev/v1/peer-similarity/snapshot=2026-08-31/` 에 넣었다(S15P21A506-350). 같은 실행 ID로 재실행해
해시 재검증만 통과하는 것을 확인했다. 비교 대상 쌍에 registry 기반 개발용 이동쌍이 섞여 있지만
peer 열 자체는 deps.dev `requirements` 에서만 오므로 `depsdev/v1` 아래에 둔다.

`package-peers-20260915-v2` 로 **npm 전수** peer 목록 Parquet 2개(46,894,329바이트·1,345,855행)를
`depsdev/v1/package-peers/snapshot=2026-08-31/` 에 넣었다(S15P21A506-350). 위 `peer-similarity` 가
쌍 단위 비교라면 이쪽은 패키지 단위 재료로, 쌍 목록에 없는 임의 조합을 즉석 비교할 때 쓴다.
`package_peers_all`(814,025행)과 그 부분집합 `package_peers_recent`(531,830행, 최신 릴리스
2023-01-01 이후)이며 열 구성은 같다. **전수를 그대로 쓰지 말 것** — `all` 의 23.9%가 릴리스
1개짜리이고 다운로드 상위 10만 안에 드는 것은 3.6%뿐이다. 하한 판단용으로 `n_releases`·
`last_published_at`·`is_deprecated`·`download_rank` 를 열로 담았다.

**앞선 `package-peers-20260915-v1` 은 쓰지 말 것.** `all` 1,033,323행 중 219,299행(21.2%)이
실제 패키지가 아니라 deps.dev 가 번들 중첩 의존 경로를 담은 노드였다. 지우지 않고 그 prefix 에
`_DEPRECATED.json` 을 두어 사유와 대체 회차를 적었다 — 아래 "폐기한 회차" 를 볼 것.

두 데이터셋은 `data/` 폴더를 나눠 쓴다(`data/peer_similarity` · `data/package_peers`).
이 입고기가 데이터셋 root 의 `*.parquet` 를 통째로 올리므로, 한 폴더에 섞으면 이미 `_SUCCESS`
가 찍힌 실행에 파일이 늘어 `Completed run missing object` 로 막힌다.

수집기 원본은 `keywords-20260909-v1` 로 ecosyste.ms keywords 수집일 `2026-09-08` 을
서버 `pickage-raw` 에 넣었다. gzip JSONL 1,000개(184,154,394바이트)에 관리 파일 3개를
더해 1,003객체이며, 원본 manifest 기준 1,000/1,000페이지·100만 행이다. 같은 실행 ID로
재실행해 객체 수가 늘지 않고 전량 해시 검증만 통과하는 것을 확인했다.

### 입고 회차 목록

**아래 바이트는 prefix 전체다** — 데이터 파일에 관리 파일(`run_manifest.json`·`_SUCCESS`)을 더한
값이다. 이어지는 문단들의 수치는 데이터 파일만 센 것이라 조금 작다. 예를 들어 Bronze 는
데이터 3,231개 33,443,300,362 B 에 관리 파일 696개가 붙어 3,927객체 33,444,184,636 B 가 된다.

`pickage-raw` — 수집기 원본과 Bronze.

| run_id | 객체 | 바이트 | 무엇 |
| --- | ---: | ---: | --- |
| `bronze-20260907-v1` | 3,927 | 33,444,184,636 | deps.dev Bronze 초기 적재(`projects`·`pkg_project`·`requirements`·`versions_full`) |
| `bronze-weekly-20260914` | 931 | 10,033,410,669 | 주간 갱신 1회차(`projects`·`requirements`·`versions_min`) |
| `registry-20260916-v1` | 4,321 | 989,127,592 | npm registry 원본, 수집일 2026-09-16(샤드 4개) |
| `registry-20260909-v1` | 4,294 | 766,251,533 | npm registry 원본, 수집일 2026-09-09 |
| `keywords-20260909-v1` | 1,003 | 184,419,176 | ecosyste.ms keywords, 수집일 2026-09-08 |
| `downloads-278-20260909-v1` | 771 | 1,598,541,546 | npm downloads 백필 원본 |
| `downloads-weekly-20260914` | 42 | 41,720,375 | npm downloads 주간 1회차 |
| (관리) `_ops/weekly/2026-09-14/run.json` | 1 | 3,174 | 주간 실행 상태 (S15P21A506-273) |
| (관리) `experiments/raw-benchmark-20260915/targets` | 1 | 1,080,529 | 벤치마크 대상 목록 |

`pickage-curated` — Curated 와 파생 데이터셋.

| run_id | 객체 | 바이트 | 무엇 |
| --- | ---: | ---: | --- |
| `curated-20260907-v2` | 47 | 4,847,760,032 | `package`·`version` 적재용 Parquet |
| `package-dependents-20260915-v1` | 3 | 104,146,164 | 패키지별 의존 패키지 수. **코드는 develop 미머지**(S15P21A506-354) |
| `package-text-20260908-v1` | 3 | 86,161,332 | 유사도 배치 코퍼스 |
| `package-dependents-candidate-pool-20260916-v1` | 3 | 61,555,594 | 후보 풀 |
| `package-peers-20260915-v1` | 5 | 47,779,985 | **폐기됨** — 아래 "폐기한 회차" |
| `package-peers-20260915-v2` | 4 | 46,896,743 | npm 전수 peer 목록 |
| `migration-pairs-20260909-v1` | 5 | 28,704,431 | 이동쌍(실행용 의존·npm 전수) |
| `migration-pairs-dev-20260914-v1` | 5 | 5,870,873 | 이동쌍(개발용 의존·registry 수집분) |
| `dependent-transitions-20260921-v1` | 3 | 6,368,699 | 유지·유입·이탈 전이 — **운영이 읽는 회차**(관측불가 분해 포함, S15P21A506-421) |
| `dependent-transitions-20260917-v1` | 3 | 5,743,139 | 유지·유입·이탈 전이 — 분해 이전 회차 |
| `deprecated-replacement-20260914-v1` | 3 | 2,840,619 | 폐기→대체 학습쌍 |
| `peer-similarity-20260914-v1` | 4 | 2,268,414 | 대체 후보 peer 유사도 |
| (포인터) `_current.json` 4개 | 4 | 852 | `package-version`·`package-peers`·`peer-similarity`·`package-text` |
| `experiments/` 6개 prefix | 2,378 | 18,963,402,066 | 실험 산출물 — 아래 참고 |

### `pickage-mlflow-artifacts` 는 경로 규약 밖이다

**빈 버킷이 아니다.** 모델 2벌이 들어 있다. 문서만 보고 비어 있다고 판단해 지우거나 덮어쓰지 말 것.

| prefix | 올라간 날 | model_ver | 객체 |
| --- | --- | --- | --- |
| `v7/` | 2026-09-12 | `bge-small-v7-hiconf-batch32-step1310` | `model.onnx`(138,482,077 B) · `tokenizer.json` · `tokenizer_config.json` · `run_manifest.json` · `_SUCCESS.txt` |
| `v7-v5clean/` | 2026-09-15 | `bge-small-v7-v5clean-batch32-step500` | 같은 5개 |

다른 버킷과 규약이 다르다. **입고기(`ingest_*.py`)를 거치지 않고 손으로 올린 것이기 때문이다.**

- 경로가 버킷 root 에 flat 하다(`v7/`). 다른 버킷의 `<source>/v1/<dataset>/<partition>/run_id=…/` 를 따르지 않는다.
- 완료 표시가 `_SUCCESS.txt` 다. 다른 곳은 `_SUCCESS` 다.
- `run_manifest.json` 에 학습 정보(`adapter`·`training`·`eval`·`onnx_export`)는 있지만
  **객체별 sha256 과 검증 상태 필드가 없다.** 입고기가 만든 manifest 와 형태가 다르다.
- 두 모델의 `tokenizer.json`·`tokenizer_config.json` 은 내용이 같다(MD5 대조). 모델별로 자족적이어야
  하므로 이 중복은 정당하다. `model.onnx` 는 크기가 같지만 내용은 다르다 — 크기만 보고 같다고 판단하지 말 것.

규약에 맞출지는 별도 판단이 필요하다. 맞추려면 모델을 다시 올려야 하고, 모델을 읽는 쪽
(추론 서버·후보 색인 배치)의 경로도 함께 바꿔야 한다.

### `pickage-curated/experiments/` — 실험 산출물, 규약 밖이다

`pickage-curated` 의 22.5 GiB 중 **17.7 GiB(2,378객체)가 `experiments/` 아래**다. 정제 데이터가
아니라 Spark 실험의 입력·출력이며, 회차마다 `_CLAIM.json`(`run_id`·`input_identity`)을 둔 별도 규약을 쓴다.

| prefix | 객체 | 바이트 |
| --- | ---: | ---: |
| `raw-freeze-20260915-b1` | 1,962 | 13,769,370,788 |
| `benchmark-ec2-20260916-a1` | 73 | 5,038,734,827 |
| `sample-ec2-20260916-a1` | 137 | 125,178,901 |
| `sample1000-ec2-20260916-a1` | 84 | 14,558,052 |
| `sample1000-ec2-20260916-a2` | 84 | 14,558,067 |
| `repository22-20260917-a1` | 38 | 1,001,431 |

**`raw-freeze-20260915-b1` 은 `pickage-raw` 객체의 사본이다.** 경로가
`inputs/objects/pickage-raw/<원래 경로>` 로 원본 위치를 그대로 담고 있고(Bronze 의 `projects`·
`requirements`·`versions_full` 과 downloads 백필), 표본으로 고른 객체 하나를 원본과 MD5 로
대조해 같은 객체임을 확인했다. 실험 입력을 고정하려는 의도로 보이지만 **이 저장소 어디에도
이 규약을 적은 문서가 없다**(`_CLAIM`·`raw-freeze`·`input_identity` 로 전수 검색).

지우기 전에 만든 사람에게 확인할 것. 13.8 GB 이고, 이 버킷에서 가장 큰 prefix 이며,
**같은 바이트가 `pickage-raw` 에도 그대로 있다.**

### 포인터(`_current.json`)가 없는 파생 데이터셋

읽는 쪽이 "최신 회차"를 이름으로 찾아야 하는 데이터셋이다.

- `depsdev/v1/deprecated-replacement`
- `depsdev/v1/migration-pairs`
- `depsdev/v1/package-dependents`
- `depsdev/v1/package-dependents-candidate-pool`
- `depsdev/v1/dependent-transitions`
- `npm-registry/v1/migration-pairs-dev`

**지금은 급하지 않다.** 여섯 개 모두 서버에 올라간 회차가 하나뿐이라 "최신"을 고를 일이
없기 때문이다. 포인터가 필요해지는 시점은 **둘째 회차가 생길 때**다. 그때 `_current.json`
없이 새 회차를 올리면 읽는 쪽이 조용히 옛 회차를 계속 본다. 포인터 형식은 이미 게시된
`package-text` 의 것을 따른다.

## 로컬 실행

Docker Desktop의 Linux engine을 사용한다. 저장 데이터는 Docker named volume
`pickage-local_minio-data`에 유지된다. API/console은 localhost에만 공개한다.

이 디렉터리의 `.env`에 `.env.example`의 변수와 별도 비밀번호를 설정한다.
`.env`는 Git에서 제외된다.

```powershell
docker compose -f docker-compose.local.yaml up -d
docker compose -f docker-compose.local.yaml ps -a
```

- Console: http://localhost:9001
- S3 API: http://localhost:9000
- 로그인: 로컬 `.env`의 값

프로젝트 루트의 `docker-compose.local.yaml`에서 로컬 서비스를 관리한다.
위 명령은 프로젝트 루트에서 실행한다.
MinIO가 healthy 상태가 되면 `minio-init`이 `init-buckets.sh`를 실행해
위 5개 버킷 중 없는 버킷만 생성한다. 기존 버킷과 객체는 유지한다.
일회성 서비스인 `minio-init`의 `Exited (0)` 상태는 초기화 성공을 뜻한다.
초기화 로그는 `docker compose -f docker-compose.local.yaml logs minio-init`으로 확인한다.
중지는 `docker compose -f docker-compose.local.yaml stop`으로 한다.
`down -v`는 저장 데이터를 삭제하므로 사용하지 않는다.

## 서버 MinIO 로 적재하기

여기까지는 전부 로컬 이야기다. 서버(`data` 노드)의 MinIO에 넣으려면 두 가지가 필요하다 —
SSH 터널과 별도 자격증명 파일이다.

서버 MinIO는 **외부에 열린 포트가 없다.** S3 API 9000·콘솔 9001 모두 루프백에만
묶여 있어 터널로만 닿는다. 서버 구성은 [deploy/prod/data/README.md](../../deploy/prod/data/README.md)를 본다.

### 1. 터널을 연다 — 내 PC 쪽 입구를 19000 으로 낸다

```bash
ssh -i ~/.ssh/J15A506T.pem -N -L 19000:localhost:9000 ubuntu@j15a506a.p.ssafy.io
```

**19000 은 서버 포트가 아니라 내 PC 의 포트다.** `-L` 의 두 번호는 기준점이 다르다.

```text
-L 19000:localhost:9000
   └─┬─┘ └────┬───────┘
     │        └── 서버에서 봤을 때의 목적지. 서버 자신의 9000
     └── 내 PC 에 여는 입구 번호

내 코드 → localhost:19000 ─[SSH 터널]─→ 서버의 localhost:9000 → MinIO
          (내 PC)                        (서버. 여기는 9000 그대로다)
```

**서버 설정은 아무것도 바꾸지 않는다.** 바꾸는 것은 내 PC 안에서 서버로 가는 입구의
번호뿐이고, 그 번호가 로컬 MinIO 의 9000 과 겹치지 않는 것이 이 구성의 핵심이다.

| 내 PC 의 주소 | 실제로 닿는 곳 |
| --- | --- |
| `localhost:9000` | 내 PC 의 Docker MinIO |
| `localhost:19000` | 터널 → 서버 MinIO |

입구도 9000 으로 잡으면 두 가지 일이 생긴다. 로컬 MinIO 가 떠 있으면 포트가 이미
점유되어 **터널이 아예 안 열린다**(`bind [127.0.0.1]:9000: Address already in use`).
꺼져 있으면 터널은 열리지만, 이제 `localhost:9000` 이 터널인지 로컬 MinIO 인지
**구분할 방법이 없다.** 나중에 터널 없이 로컬 MinIO 만 켜고 적재를 돌리면 주소가 같으니
**아무 오류 없이 로컬로 들어간다.** 서버에 넣은 줄 알고 넘어가고 한참 뒤에 드러난다.

19000 으로 갈라 두면 그 애매함이 없다. 로컬 MinIO 가 쓰지 않는 번호라서, 응답이 있으면
터널이 열린 것이고 없으면 그 자리에서 연결이 거부된다. 안전이 사람의 기억이 아니라
포트 번호에 걸려 있게 된다.

숫자 자체는 임의다. 조건은 **로컬에서 쓰지 않는 번호** 하나뿐이다. 다만 사람마다 다른
번호를 쓰면 이 문서와 각자의 `.env.server` 가 갈라지므로 팀에서 19000 으로 통일한다.

터널은 창을 닫으면 끊긴다. 적재가 끝날 때까지 열어 둔다.

### 2. 자격증명 파일을 만든다

```bash
cp pipeline/minio/.env.server.example pipeline/minio/.env.server
```

값은 서버에서 돌고 있는 컨테이너에서 꺼낸다. 따로 발급받을 필요가 없다.

```bash
ssh -i ~/.ssh/J15A506T.pem ubuntu@j15a506a.p.ssafy.io   'docker inspect pickage-data-minio-1 --format "{{range .Config.Env}}{{println .}}{{end}}" | grep MINIO_ROOT'
```

`.env.server` 는 `.gitignore` 가 막는다(`.env.*` 전체를 막고 `.example` 만 예외로 둔다).
**로컬 `.env` 에 서버 값을 넣지 말 것** — 그 파일은 루트 compose 가 로컬 컨테이너를
띄울 때 함께 읽는다.

#### 키 이름 — `PICKAGE_S3_*` 가 쓸 이름이다

`client()` 는 자격증명을 두 이름으로 받는다. **새로 만드는 파일에는 `PICKAGE_S3_*` 를
쓴다.**

| 이름 | 쓰는 곳 |
| --- | --- |
| `PICKAGE_S3_ACCESS_KEY` · `PICKAGE_S3_SECRET_KEY` | 새 파일. 예: `.env.similarity-loader` |
| `MINIO_ROOT_USER` · `MINIO_ROOT_PASSWORD` | 옛 이름. `.env` · `.env.server` · `.env.data` 가 아직 이것이다 |

옛 이름을 한 번에 걷어 내지 않는 이유는 **같은 파일을 다른 모듈도 읽기** 때문이다 —
`pipeline/repository_metrics/build.py` 와 `pipeline/requirements_resolution/build.py` 가
`MINIO_ROOT_*` 로 직접 파싱한다. 여기만 바꾸면 그 둘이 조용히 죽는다.

**권한을 좁힌 계정을 `MINIO_ROOT_*` 라는 이름에 넣지 말 것.** 이름이 ROOT 면 루트 키를
넣어도 어색해 보이지 않고, 그게 계정을 따로 만든 이유를 지운다 (S15P21A506-385).

### 3. 대상을 지정해 실행한다

환경변수로 자격증명 파일을 고른다. 지정하지 않으면 로컬이다.

```powershell
$env:PICKAGE_MINIO_ENV=".env.server"
```

```bash
export PICKAGE_MINIO_ENV=.env.server
```

이제 이 문서의 입고·적재 명령이 그대로 서버를 향한다. `pipeline/preprocessing/curated/build.py`와
`pipeline/postgresql/load.py`도 같은 `client()` 를 쓰므로 함께 바뀐다.

실행할 때마다 첫 줄에 붙은 곳이 찍힌다. **로그에서 이 줄을 먼저 볼 것.**

```text
PICKAGE_S3_ENDPOINT=http://localhost:19000 (.env.server)
```

로컬로 돌아가려면 변수를 지운다 (`Remove-Item Env:PICKAGE_MINIO_ENV` / `unset PICKAGE_MINIO_ENV`).

## Bronze 입고 실행

원본 Parquet는 MinIO 기동과 별개의 입고 작업으로 `pickage-raw`에 복사한다.
로컬 `data/raw`에 원본 Parquet와 `_MANIFEST.json`이 있어야 한다.
아래 명령도 프로젝트 루트에서 실행한다.

```powershell
.venv-bq/Scripts/python.exe -m pip install -r pipeline/minio/requirements.txt
.venv-bq/Scripts/python.exe pipeline/minio/ingest_raw.py --dry-run
.venv-bq/Scripts/python.exe pipeline/minio/ingest_raw.py --run-id bronze-20260907-v1 --workers 8
```

위 실행 ID는 기존 입고를 검증·재개할 때 사용한다.
별도 입고 이력을 만들려면 새로운 실행 ID를 지정한다.
`--run-id`를 생략하면 자동 생성되므로 새 실행 경로에 복사본이 저장된다.
`--dry-run`으로 원본 manifest와 파일 수/크기/Parquet 행 수를 먼저 검증한다.
`--dataset projects --snapshot 2022-05-08`로 범위를 좁힐 수 있다.
대상은 `data/raw`의 deps.dev 데이터이며 다운로드 API 데이터는 포함하지 않는다.

`boto3`는 로컬 MinIO의 S3 API 호출에, `duckdb`는 입고 전 Parquet 메타데이터의
행 수 확인에 사용한다. DuckDB 서버를 별도로 띄우거나 MinIO 컨테이너에 설치하지 않는다.

## 파생 데이터셋 입고 실행

빌더가 원본에서 계산해 낸 작은 데이터셋은 `pickage-raw` 가 아니라 `pickage-curated` 에 넣는다.
원본이 아니라 원본을 가공한 결과이기 때문이다. `pipeline/duckdb/build_*.py` 와 수집기 자신의
빌더(`collectors/keywords/build_package_text.py`)가 여기로 온다.

```powershell
$env:PICKAGE_MINIO_ENV=".env.server"
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset deprecated-replacement --dry-run
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset deprecated-replacement --run-id deprecated-replacement-20260914-v1
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v1
```

`--dataset` 에 넣을 수 있는 값과 각 데이터셋의 로컬 경로·설명·Jira 키는
`ingest_derived.py` 의 `DATASETS` 에 있다. 빌더를 먼저 돌려 Parquet 을 만들어 둬야 한다.

**회차 선택.** 데이터셋에 `glob` 이 있으면 그 패턴에 맞는 파일만 고른다(`{date}` 는 파티션
날짜로 채운다). 없으면 폴더의 `*.parquet` 전부다. `package_text` 는 수집일마다 파일이 하나씩
쌓이는 폴더를 쓰므로, 패턴이 없으면 다음 수집일 것이 같은 실행에 섞여 행 수가 두 수집일의
합이 된다.

**업로드 객체명.** `object_name` 이 있으면 `data/` 아래 이름을 그것으로 고정한다. 로컬
파일명은 그대로 두고 올릴 때만 바꾸며, 개명한 경우 `run_manifest.json` 의 파일 항목에
`source_file` 로 원래 이름을 남긴다. 쓰는 쪽이 이름을 고정해 받을 때만 쓴다 — `package_text`
가 그렇다. 파일이 둘 이상이면 같은 이름으로 겹쳐 올라가므로 거부한다.

**`_current.json`.** `pointer` 가 켜진 데이터셋은 prefix 루트에 "지금 읽어야 할 실행" 을
가리키는 포인터를 게시한다. **manifest → `_SUCCESS` → 포인터** 순서라 포인터는 온전한 실행만
가리킨다. 갱신은 조건부 PUT(CAS)이고, 값이 같으면 아무것도 쓰지 않으며, 현재 포인터가 더 나중
수집일을 가리키면 **거부한다** — 과거 실행을 재검증했을 뿐인데 소비자가 옛 코퍼스로 돌아가는
일을 막는다. 같은 수집일의 새 실행 ID 는 통과시킨다(잘못 올린 회차를 고칠 길).

포인터가 켜진 데이터셋은 `package-text`·`peer-similarity`·`package-peers` 다. 뒤의 둘은
**회차가 둘 이상 생길 수 있어서** 켰다 — 실제로 `package-peers` 는 v1 을 버리고 v2 를 쓴다.
포인터가 없으면 경로만 보고는 어느 회차가 정본인지 알 길이 없다.

**폐기한 회차.** 잘못 만든 회차는 지우지 않고 그 prefix 에 `_DEPRECATED.json` 을 둔다.
`run_id` · `status: DEPRECATED` · `reason` · `superseded_by{run_id, run_path, manifest_sha256}`
를 싣는다. **입고기는 이 파일을 만들지도 읽지도 않는다 — 사람이 올리고 사람이 읽는다.**
기계적으로 정본을 고르는 것은 위의 `_current.json` 이 하는 일이고, 이 파일은 포인터가 가리키지
않는 쪽을 열어 본 사람에게 "왜 이게 남아 있는지" 를 알려 준다. 두 가지가 필요한 이유는
`run_manifest.json` 의 `status: PASSED` 가 **업로드 해시 검증**만 뜻하고 내용의 정합성을
보증하지 않기 때문이다 — 오염된 회차도 `PASSED` 로 남는다.

지운 적이 없어 되돌릴 일도 없다. 버킷에서 실제로 지우는 것은 별도 판단이고, 지울 때는
`_DEPRECATED.json` 이 가리키는 대체 회차가 온전한지 먼저 본다.

**재생성할 수 있는데 왜 올리나.** 빌더는 `data/raw` 의 수십 GB Parquet 을 그대로 들고 있는
PC 에서만 돈다. 그 PC 가 사라지면 git 의 CSV 만 남고, 그것을 만든 계산은 복원할 수 없다.

`run_manifest.json` 에는 업로드 시각을 넣지 않는다. 같은 실행 ID 로 다시 돌리면 만들어지는
manifest 가 이미 올라간 것과 한 바이트도 다르지 않아야, 덮어쓰기 대신 **전량 해시 재검증**으로
통과한다. 시각이 들어가면 재검증 자체가 실패한다.

## 수집기 원본 입고 실행

deps.dev 스냅샷은 위의 `ingest_raw.py` 가 맡는다. API 수집기(ecosyste.ms keywords,
npm registry)의 원본은 `ingest_collector_raw.py` 로 넣는다. 둘을 가른 이유는 원본의
형태가 다르기 때문이다 — 수집기 쪽은 `data/<소스>/raw/run=<날짜>/` 에 gzip JSONL 조각과
수집기가 직접 쓴 `manifest.json` 이 함께 있다. 업로드·검증 규칙은 같은 것을 쓴다.

```powershell
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_collector_raw --source keywords --dry-run
.venv-bq/Scripts/python.exe -m pipeline.minio.ingest_collector_raw --source keywords --run 2026-09-08 --run-id keywords-20260909-v1 --workers 8
```

`--source` 는 `keywords` 와 `registry` 를 받는다. `--run` 으로 수집일을 지정하고,
생략하면 **날짜 형태의 run 만** 쓸어 담는다.

### 미완료 수집은 입고되지 않는다

수집기의 `manifest.json` 을 읽어 **수집이 끝났는지 먼저 판정한다.** 끝나지 않았으면
그 자리에서 실패한다.

| 소스 | 완료 조건 |
| --- | --- |
| `keywords` | `final: true` 이고 `pages_done == pages_planned` |
| `registry` | `final: true` 이고 `tasks_by_status.pending == 0` |

`final` 만으로는 부족하다. 수집기가 체크포인트마다 manifest 를 다시 쓰기 때문에
진행 중에도 파일은 늘 존재한다. 진행 카운터가 **없는** manifest 도 완료로 보지 않는다 —
형태가 다른 manifest 를 "빠진 값 = 문제 없음" 으로 읽으면 부분 수집이 그대로 통과한다.

부분 수집을 올리면 `_SUCCESS` 가 함께 기록되어 **나중에 검증된 완전한 원본으로 읽힌다.**
그 뒤로는 아무도 의심하지 않는다. 그래서 여기서 막는다.

### 스모크 런은 쓸어 담지 않는다

시험 실행(`run=smoke-2026-09-08`)이 실제 수집 폴더와 같은 자리에 남는다.
`--run` 없이 돌리면 날짜 형태만 고르므로 시험 데이터가 섞여 들어가지 않는다.
굳이 올리려면 `--run smoke-2026-09-08` 처럼 이름을 대야 한다.

`pickage-raw` 는 수집 원본이 사는 버킷이다. 시험 데이터가 한 번 들어가면
나중에 그것이 무엇이었는지 아무도 기억하지 못한다.

## 저장 경로와 검증 규칙

목적지 버킷은 `pickage-raw`이며, 실행별 객체 이름은 다음과 같다.

```text
depsdev/v1/{table}/snapshot={date}/run_id={run}/
  data/*.parquet        # 수집된 Parquet 원본
  source_manifest.json # 원본 _MANIFEST.json 보존
  run_manifest.json    # 파일별 크기·SHA-256 및 입고 검증 결과
  _SUCCESS             # 해당 데이터셋·스냅샷·실행의 검증 완료 표시
```

빌더가 만든 파생 데이터셋은 `pickage-curated` 의 다음 경로에 넣는다. 관리 파일에
`source_manifest.json` 이 없는 것은 원본 manifest 를 물려받을 원본이 없기 때문이고,
대신 `run_manifest.json` 에 빌더 경로·원천·Jira 키·주의사항을 적는다.

날짜 파티션의 키 이름은 **그 데이터셋의 원천이 쓰는 말을 따른다** — deps.dev 에서 나온 것은
`snapshot=`, 수집기에서 나온 것은 `collected_date=` 다.

> **예외 하나: `migration-pairs-dev`.** registry 수집분에서 나왔으니 이 규칙대로면
> `collected_date=` 여야 하는데 `snapshot=2026-09-09` 에 있다. 파티션 키 이름이 데이터셋마다
> 갈리기 전에 입고된 것이라(`migration-pairs-dev-20260914-v1`, S15P21A506-349) 그대로 둔다.
> 지금 키를 고치면 입고기가 없는 경로를 보게 되고, 재실행이 같은 데이터를 한 벌 더 올린다.
> **이 예외를 새 데이터셋의 선례로 삼지 않는다.**

```text
depsdev/v1/{dataset}/snapshot={date}/run_id={run}/
  data/*.parquet        # 빌더 산출물
  run_manifest.json     # 파일별 크기·행 수·SHA-256, 빌더·원천·README 위치, notes
  _SUCCESS              # 해당 데이터셋·스냅샷·실행의 검증 완료 표시

ecosystems-keywords/v1/package-text/
  _current.json                     # 지금 읽어야 할 실행. 유사도 배치의 코퍼스 트리거
  collected_date={date}/run_id={run}/
    data/package_text.parquet       # 로컬 package_text_{date}.parquet 을 개명해 올린 것
    run_manifest.json               # files[].source_file 에 개명 전 이름이 남는다
    _SUCCESS
```

`_current.json` 은 `{collected_date, manifest_sha256, run_id, run_path}` 네 값을 싣는다.
`run_path` 는 **prefix 상대** 경로이고(소비자가 prefix 를 자기 설정에 이미 들고 있다),
`run_id` 는 **평평한 이름**이다 — 소비자가 산출물 경로에 그대로 박기 때문에 `/` 가 들어가면
디렉터리 깊이가 달라진다.

> **`_SUCCESS` 본문이 두 가지다.** 이 폴더의 입고기(`ingest_*.py`)는 빈 본문을 쓰고,
> `pipeline/preprocessing/curated/build.py` 는 `{"manifest_sha256": …}` 를 쓴다. 한 버킷에 둘이 있으므로
> 읽는 쪽은 한 형태를 가정하면 안 된다. 입고기 쪽을 맞추지 않는 이유는 이미 올라간 객체와의
> 바이트 호환이다 — 본문이 달라지면 기존 실행이 재검증으로 통과하지 못한다.

수집기 원본은 소스별로 다음 경로에 넣는다. 검증 규칙과 관리 파일은 위와 같다.

```text
ecosystems-keywords/v1/collected_date={date}/run_id={run}/
npm-registry/v1/collected_date={date}/run_id={run}/
  data/part-*.jsonl.gz  # 수집된 gzip JSONL 원본
  source_manifest.json  # 수집기 manifest.json 보존
  run_manifest.json     # 파일별 크기·SHA-256 및 입고 검증 결과
  _SUCCESS              # 해당 수집일·실행의 검증 완료 표시
```

**분할 수집(샤드)은 경로가 한 단계 깊다.** registry 는 2026-09-16 회차부터 대상을 넷으로 나눠
`run=<date>-s1 … -s4` 네 폴더로 받는다(S15P21A506-366). 그것은 **한 수집**이므로 `collected_date`
하나 아래에 넣되, 샤드를 경로에 남긴다.

```text
npm-registry/v1/collected_date=2026-09-16/run_id=registry-20260916-v1/
  data/shard=s1/part-*.jsonl.gz   # 샤드마다 part-00000 부터 다시 센다
  data/shard=s2/part-*.jsonl.gz
  data/shard=s3/part-*.jsonl.gz
  data/shard=s4/part-*.jsonl.gz
  source_manifest/shard=s1.json   # 수집기 manifest 를 샤드별로 원본 그대로
  …
  run_manifest.json               # shards 수와 샤드별 source_manifest_sha256 포함
  _SUCCESS
```

**파일명을 합치면 안 된다.** 샤드는 각자 `part-00000.jsonl.gz` 부터 번호를 매기므로 이름이 겹친다 —
2026-09-16 회차는 4,315 파일 중 1,078개 이름이 네 샤드에 중복되고 내용은 전부 다르다. 한 `data/` 에
합쳐 올리면 3,231개가 조용히 덮어써진 뒤 그 위에 `_SUCCESS` 가 찍힌다. 읽는 쪽은 `data/**/part-*` 로
훑으면 단일 run 과 샤드 run 을 함께 다룰 수 있다.

입고기는 샤드가 하나라도 빠지면 거부한다. 개수는 폴더 수가 아니라 수집기 manifest 의 `targets`
파일명(`…-s1of4.csv`)에서 읽는다 — 폴더를 세면 s3 를 빠뜨린 채 올려도 통과해서 원본의 1/4 이
없는 데이터에 완료 표시가 찍힌다.

수집기의 체크포인트 DB(`checkpoint.sqlite`)와 로그는 올리지 않는다. 수집기가 도는 동안
계속 바뀌는 작업 상태이지 원본이 아니다. `npm-downloads/v1/` 은 별도 입고 경로가 맡는다
([pipeline/downloads](../downloads)).

Projects는 여러 provider의 데이터이므로 `system=npm` prefix를 사용하지 않는다.
모든 업로드 객체는 GET으로 읽어 로컬 SHA-256과 비교한다.
원본 manifest를 보존하고 검증 결과 manifest 이후 `_SUCCESS`를 기록한다.
`_SUCCESS`는 이 입고 단계의 파일 무결성 검증 완료를 뜻하며,
원본의 의미적 품질이나 후속 전처리·PostgreSQL 적재 완료를 보장하지 않는다.
실패 시 같은 run ID로 재개하면 기존 파일은 해시 검증하고 빠진 파일만 전송한다.
단, 이미 `_SUCCESS`가 있는 실행에서 파일이 누락돼 있으면 자동 복구하지 않고 실패한다.
기존 객체의 내용이 다르면 덮어쓰지 않고 실패한다. 같은 run은 동시에 실행하지 않는다.
향후 Spark 연동 시 여러 run을 한꺼번에 읽는 glob 대신 검증된 특정 run 경로를 넘긴다.

## 테스트와 운영 주의사항

```powershell
.venv-bq/Scripts/python.exe -m unittest discover -s pipeline/minio -p "test_*.py" -v
```

단위 테스트는 스트림 해시 계산, 동일 manifest 재사용,
내용이 다른 manifest의 덮어쓰기 거부를 검증한다.
실제 MinIO 업로드·버킷 생성 검증은 별도의 로컬 실행 확인이 필요하다.

named volume은 컨테이너 교체 시 데이터를 유지하기 위한 장치이지 별도 백업이 아니다.
이 구성은 로컬 단일 노드 개발용이며 서버 백업/권한 구성을 대신하지 않는다.
