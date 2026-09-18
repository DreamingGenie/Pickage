# package_env — 버전별 소비 조건 (기능-11-R01)

확장 보고서 2페이지의 **첫 결과 카드**가 읽는 표다. 기능-12(AI 기능 비교)·기능-13(해설)
앞에 놓여, 생성된 문장이 앉을 검증 가능한 바닥을 깐다. 그래서 여기 들어가는 값은 전부 npm
Registry 원문에서 그대로 읽히거나 원문으로부터 기계적으로 접힌 것이다.

한 행 = 패키지 × 버전.

    pickage-curated/npm-registry/v1/package-env/
      collected_date=2026-09-16/run_id=package-env-20260916-v1/
        data/package_env.parquet
        run_manifest.json

## 열

| 열 | 형 | 뜻 |
|---|---|---|
| `Name` | VARCHAR | 패키지 이름. 적재기가 `package_id` 로 바꾼다 |
| `Version` | VARCHAR | |
| `module_format` | VARCHAR | 어떻게 불러오는가. `CJS` · `ESM_ONLY` · `ESM_CJS` · `UNKNOWN` |
| `types_bundled` | BOOLEAN | 타입 선언이 패키지에 동봉됐는가 |
| `direct_dependencies` | INT | `dependencies` 선언 수. NULL 허용 |
| `peer_dependencies` | INT | `peerDependencies` 선언 수. NULL 허용 |

## 원천

`pickage-raw/npm-registry/v1/collected_date=2026-09-16/`(S15P21A506-366)의 jsonl.gz 를
`pipeline/duckdb/build_package_env.py` 가 직접 읽는다.

    module_type + main + exports  ->  module_format
    types (없으면 typings)         ->  types_bundled
    Dependencies 길이              ->  direct_dependencies
    PeerDependencies 길이          ->  peer_dependencies

**09-16 이후 회차만 쓸 수 있다.** 형태 6열은 그 회차부터 들어갔고, 09-09 raw 에는 키 자체가
없다. 빌더가 `DESCRIBE` 로 확인해 없으면 멈춘다.

## module_format 판정

순서가 곧 규칙이다.

| 순서 | 조건 | 값 |
|---|---|---|
| 1 | 의존 네 배열이 전부 NULL (unpublish) | `UNKNOWN` |
| 2 | `exports` 에 `"import"` 와 `"require"` 가 둘 다 | `ESM_CJS` |
| 3 | `module_type = 'module'` | `ESM_ONLY` |
| 4 | 그 밖 | `CJS` |

**`module_type` 이 NULL 인 것은 모름이 아니라 `commonjs` 기본값이다.** 전수의 74.1% 가
NULL 이라, 모름으로 읽으면 대부분이 `UNKNOWN` 이 되어 표가 아무 말도 못 한다.

듀얼을 `module_type` 보다 먼저 보는 이유는 양쪽을 다 내보내는 패키지가 `type` 을 module 로
적기도 하고 commonjs 로 적기도 해서다. 순서를 바꾸면 그런 것들이 `ESM_ONLY` 로 떨어져
CJS 프로젝트에서 못 쓰는 것처럼 보인다.

판정은 `exports` 를 파싱하지 않고 문자열로 본다. 조건 키는 따옴표째 `"import"` / `"require"`
로 나타나고 서브경로 키는 `"./import"` 처럼 앞에 `./` 가 붙어 따옴표 바로 뒤에 오지 않는다.
최대 2.69 MB 인 JSON 을 800만 번 파싱하지 않으려는 것이다. 09-16 shard 5,000행에서 실제
파싱 결과와 11건으로 일치했다.

### 타입 전용(`@types/*`)을 값으로 두지 않은 이유

**6열만으로는 못 가른다.** `main` 이 없으면 npm 이 `index.js` 를 기본값으로 쓰므로
"main 없음" 이 "JS 없음" 이 아니다.

09-16 shard 5,000행에서 `main` 없음 + `types` 있음 으로 잡으면 1,963행이 걸리는데,
그중 **22행이 `chalk`·`supports-color` 처럼 런타임이 있는 패키지**였다(`chalk@2.2.0` 은
`main` 이 없고 `types: "types/index.d.ts"` 다). 그래서 `@types/*` 도 `CJS` 로 떨어진다.

## 읽을 때 주의

- **`types_bundled = false` 는 "타입이 없다" 가 아니다.** "이 패키지 안에는 없다" 이고,
  `@types/xxx` 를 따로 깔면 된다. 화면 문구는 **"별도 설치 필요"** 여야 한다.
  `types` 만 보면 과소 계상한다 — `ajv` 는 `typings` 만 있는 버전이 127개다. 수집기가 둘 다 본다.
- **의존 개수의 NULL 은 0 이 아니다.** unpublish 된 버전은 의존 배열이 통째로 NULL(모름)이다.
  0 으로 읽으면 "의존 없음" 이 되고, 같은 실수가 이동쌍 검증에서 641건 과대 계상으로 실제로 났다.
- **전이 의존이 아니다.** `express` 가 31개라고 나와도 실제로 깔리는 것은 수백 개다.
  MVP 는 직접 의존만 다룬다(요구사항 명세서 33·76행). 화면 라벨에 **"직접"** 을 반드시 붙인다.
- **`direct` 와 `peer` 를 더하지 않는다.** `dependencies` 는 깔면 따라오고
  `peerDependencies` 는 사용자가 이미 갖고 있어야 하는 조건이다. 버전이 안 맞으면 설치가
  막히거나 경고가 난다. 합치면 "따라오는 것" 과 "내가 맞춰야 하는 것" 이 섞여 둘 다 못 읽는다.

## 담지 않은 것

- **실행 조건(`engines`)** — 기능-11-R01 의 항목이지만 수집에 없다. 원본 문서를 보존하지 않아
  재수집 외에 방법이 없다(상위 10만 약 4시간·73GB). 그 행은 화면에 내지 않는다 —
  완료 판단이 "확인된 정보만 표시" 이므로 빈 칸보다 없는 편이 맞다.
- **설치 크기(`unpacked_size`)·파일 수** — 기능-11-R01 의 항목이 아니다. 그 값은 패키지
  자신의 tarball 만 푼 크기라 의존성이 빠진다. 65 KB 짜리가 직접 의존 8개를 끌고 오면 실제
  `node_modules` 는 수 MB 다. "설치 크기" 로 부르면 정반대를 말하게 된다.
  또한 2018년 절벽이 있다 — npm 이 2018년부터 계산해 2017년 이하 발행분은 존재율 0.0% 다.
- **`exports` 원문** — 판정에만 쓴다. 전수 중앙값 179 B 인데 최대 2.69 MB
  (`@dnb/eufemia@10.94.0`) 라 그대로 싣고 다닐 수 없다. 규칙을 고쳐 다시 판정해야 하면
  raw 가 MinIO 에 그대로 있으므로 빌더부터 다시 돌린다.
- **라이선스** — 기능-11-R01 의 항목이 아니고, registry 수집 대상도 아니다. 필요하면
  `version.licenses`(deps.dev)와 조인한다.

## 못 보는 것

`.mjs`/`.cjs` 확장자로 형식이 갈리는 패키지는 여기서 안 잡힌다. 파일 목록이 없어 `type` 과
`exports` 만 보기 때문이고, 오판이 아니라 **관측 밖**이다.

## 적재

`pipeline/package_env/load.py` 가 Curated 회차를 받아 `package_env` 에 전량 교체한다.
advisory lock → staging → 이름 해석 → DELETE + INSERT → `etl_load_execution` 이력.

이름 해석이 **두 단계**다. FK 가 `version (package_id, version)` 이라 버전까지 있어야 붙는다.
못 붙는 경우가 둘이고 적재기가 따로 센다.

| | 뜻 | 할 일 |
|---|---|---|
| `unknown_name_rows` | `package` 에 이름이 없다 | 이름 규칙이나 적재 대상 DB 를 의심 |
| `unknown_version_rows` | 이름은 있는데 그 버전이 `version` 에 없다 | 정상일 수 있다 |

둘째는 **원천이 둘이라서** 생긴다. `version` 은 deps.dev 스냅샷(2026-08-31)에서 오고 이
산출물은 registry 수집(2026-09-16)에서 온다. 그 사이에 나온 버전은 registry 에만 있다.
registry README 실측으로 두 원천의 `(Name, Version)` 매칭률이 95.1% 이므로
**4.9% 가 빠지는 것이 정상이고, 그보다 크게 낮으면 다른 원인을 찾아야 한다.**

## 실측

전수 실적재 전이다. 아래는 09-16 회차의 첫 shard(`shard=s1/part-00000.jsonl.gz`, 5,000행)로
빌더를 돌린 결과이며, `@types/node` 가 2,369행이라 **전체 분포를 대표하지 않는다.**

| | |
|---|---|
| `CJS` | 4,944 (98.9%) |
| `ESM_ONLY` | 41 (0.8%) |
| `ESM_CJS` | 11 (0.2%) |
| `UNKNOWN` | 4 (0.1%) |
| `types_bundled` | 2,179 (43.6%) |
| 직접 의존 1개 이상 | 1,121 (22.4%) |
| peer 1개 이상 | 9 (0.2%) |

전수로 돌린 뒤 이 표를 교체한다.
