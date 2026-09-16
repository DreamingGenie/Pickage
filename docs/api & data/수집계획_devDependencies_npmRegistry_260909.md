# npm registry 버전 이력 수집계획 — 상위 10만 패키지의 devDependencies 포함 의존 선언

작성 2026-09-09 · Jira **S15P21A506-280** · 대상 `data/registry/` → DuckDB 뷰 `registry_versions`·`registry_status` · 상태 **수집 완료(2026-09-10, §7)·MR !108 리뷰 중**. §2·§3 은 구현 결과를 반영해 갱신함(09-11). 자체 리뷰 2회로 파싱·변환 규칙과 §5-3 검증 기준이 바뀌어 §2·§3·§5·§7 을 다시 갱신함(09-14, 재변환 완료)
선행 `수집계획_downloads_npmAPI_260902.md`(수집기 틀을 그대로 빌려 씀), `../설계_마이그레이션쌍_탐지_260831.md`(왜 개발용 의존이 필요한가), `datasets/migration_pairs_260908/README.md` §4·§5(도구 계열이 안 잡히는 이유)

---

## 0. 결론

| 질문 | 답 |
|---|---|
| 무엇을 받나 | npm 공식 저장소(registry.npmjs.org)에서 **패키지의 전 버전 선언 문서**. 버전마다 실행용 의존(dependencies)·**개발용 의존(devDependencies)**·peer·optional 의존과 발행 시각이 들어 있다 |
| 왜 받나 | deps.dev에는 개발용 의존이 없다. 테스트·검사·빌드 도구(enzyme, tslint, mocha, jest 등)의 이동은 개발용 의존 칸에서 일어나서 지금 이동쌍 결과에 보이지 않는다(`enzyme → @testing-library/react` 미검출). |
| 최신 버전 하나로 되나 | **안 된다.** 이동쌍은 "연속 두 버전의 차이"라 버전별 선언이 필요하다. 다만 이 저장소는 **요청 한 번에 전 버전을 준다**. 패키지당 1회 요청으로 시계열이 확보된다. |
| 누구를 받나 | 다운로드 순위 상위 10만(`datasets/targets/rank_top100k_20260902.csv`). 개발용 의존의 변화는 X가 아니라 **X를 쓰던 쪽(dependent)** 의 문서에 있으므로, "누가 도구를 바꿨나"를 보려면 dependent 집단을 받아야 한다. 전이가 있는 dependent 250만 개는 29일이 걸려 불가능하고, 상위 10만은 활발히 관리되는 라이브러리라 신호가 가장 진한 집단이다. |
| 얼마나 걸리나 | 요청 10만 건. 간격 0.5초면 약 14시간, 1초면 약 28시간. 문서 크기는 패키지마다 수 KB~수십 MB로 편차가 커서 **스모크 20건으로 먼저 잰다**(§3-1). |
| 결과는 어디에 | 원본은 남기지 않고 필요한 열만 `data/registry/raw/run=<날짜>/part-*.jsonl.gz`, 변환 결과는 `data/registry/parquet/`. `data/`는 gitignore. 팀 공유 보존은 downloads(S15P21A506-278)와 같이 서버 MinIO `pickage-raw` Bronze 입고로 하며(별도 티켓), GCS에는 올리지 않는다. |

---

## 1. 원천 — 알아 둘 사실

### 1-1. 요청 형태

- 주소: `https://registry.npmjs.org/<패키지명>`. 스코프 패키지는 `/`를 `%2F`로 바꾼다 (`@babel/core` → `@babel%2Fcore`). downloads 수집기의 `enc()`와 같은 처리.
- 헤더에 **`Accept: application/vnd.npm.install-v1+json`(축약 형식)을 쓰면 안 된다.** 축약 형식은 설치에 필요한 것만 담아 devDependencies가 빠진다. 기본(전체) 문서를 받아야 한다.
- 압축은 라이브러리(`requests`)가 자동으로 요청·해제한다.
- 공식 문서에 속도 한도가 없다. 과거 실측(`검증_keywords_수집가능성_260908.md` §1-2)에서 `/latest` 3~4KB 요청은 문제가 없었다. 전체 문서는 훨씬 크므로 **초당 1~2건을 넘기지 않고**, 429·5xx가 오면 간격을 늘린다. User-Agent에 연락처(환경변수 `OSS_SHIFT_UA_CONTACT`)를 넣는 규칙은 다른 수집기와 같다.

### 1-2. 문서 구조 (필요한 부분만)

```json
{
  "name": "chalk",
  "dist-tags": {"latest": "5.3.0"},
  "time": {"created": "...", "modified": "...", "4.1.2": "2021-07-28T...", "5.0.0": "..."},
  "versions": {
    "4.1.2": {"dependencies": {"ansi-styles": "^4.1.0", "supports-color": "^7.1.0"},
              "devDependencies": {"ava": "^2.4.0", "xo": "^0.28.2"},
              "peerDependencies": {}, "optionalDependencies": {},
              "deprecated": "..."(있을 때만)}
  }
}
```

- `time[버전]`이 발행 시각(UTC). `time.created`·`time.modified`·`time.unpublished`는 버전이 아니니 걸러야 한다.
- `versions`에 없는데 `time`에만 있는 버전 = 삭제(unpublish)된 버전. 발행 시각은 알지만 선언은 모른다. **버전 행은 남기고 의존 네 열은 NULL(모름)**로 둔다(사라졌다는 사실 자체가 정보). `[]`(의존 없음)로 두면 lag() 비교에서 "의존 전부 제거"로 잘못 잡힌다(§5-3).
- 404 = 저장소에 없는 이름(삭제·이름 오류). downloads 수집의 `not_found` 781건과 대부분 겹칠 것이다.
- `deprecated` 문구가 버전 단위로 있다. 폐기 데이터셋(S15P21A506-272)과 대조 가능.

### 1-3. 크기 편차

버전이 수천 개인 패키지(`@types/node`, `aws-sdk`, `typescript` 등)는 문서가 수십 MB다. 상위 10만 평균은 스모크로 재기 전까지 모른다. 그래서 **원본 문서를 통째로 저장하지 않고** 필요한 열만 남긴다(§2). 메모리도 문서 하나를 다 읽은 뒤 바로 버린다.

---

## 2. 저장 형식

### 2-1. 원본(정제된 원본) — `data/registry/raw/run=<YYYY-MM-DD>/part-NNNNN.jsonl.gz`

한 줄 = 패키지 1개 × 버전 1개. deps.dev `requirements`와 **같은 열 이름·구조**로 맞춰서 나중에 이동쌍 빌더가 두 원천을 그대로 합칠 수 있게 한다.

```json
{"Name":"chalk","Version":"4.1.2","published_at":"2021-07-28T11:02:03.000Z","rank":9,
 "Dependencies":[{"Name":"ansi-styles","Requirement":"^4.1.0"},{"Name":"supports-color","Requirement":"^7.1.0"}],
 "DevDependencies":[{"Name":"ava","Requirement":"^2.4.0"},{"Name":"xo","Requirement":"^0.28.2"}],
 "PeerDependencies":[],"OptionalDependencies":[],
 "deprecated":null,"unpublished":false,
 "fetched_at":"2026-09-09T12:00:00+00:00","modified":"2026-08-30T..."}
```

- `Dependencies`·`PeerDependencies`·`OptionalDependencies`는 deps.dev `NPMRequirements`와 같은 이름. `DevDependencies`만 새 열.
- `modified`는 문서의 `time.modified`. 주간 갱신(S15P21A506-273) 때 이 값이 바뀐 패키지만 다시 받으면 된다.
- **버전 목록은 `time`의 키 중 `^\d+\.\d+` 모양인 것만 받는다.** `created`·`modified`·`unpublished` 말고도 모르는 키가 들어온다(실측: `appdirsjs`의 `undefined`). 블랙리스트로 두면 그런 키가 가짜 unpublish 버전 행이 되어 그 패키지의 `first_published_at`이 6년 반 틀어졌다. 버린 키 수는 manifest의 `session_stats.odd_time_keys`에 센다.
- **`deprecated`는 폐기 문구만 담는다.** 문서에는 문구 대신 불리언이 오기도 해서 정규화한다 — `false`와 `""`(문구를 비운 경우)는 "폐기 아님"이라 `null`, `true`는 "문구 없는 폐기"라 문자열 `"true"`. 정규화 전에는 `deprecated IS NOT NULL`이 폐기되지 않은 9,565행을 세고 있었다.
- 파일은 5,000줄마다 회전(downloads의 `Writer`와 같음). 진행 기록은 SQLite 체크포인트(§3-2).
- **한 패키지의 행은 전부 만들고 utf-8 인코딩까지 확인한 뒤에 쓴다.** 쓰는 도중에 실패하면 체크포인트는 `failed`인데 앞부분 행만 raw에 남고, 그 고아 행은 (Name, Version) 중복 제거로 걸러지지 않는다.

### 2-2. 변환 — `data/registry/parquet/registry_versions/part-*.parquet` + `registry_status.parquet`

- `registry_versions`: 위 열 그대로(배열은 STRUCT 리스트, unpublish 행의 의존 네 열은 NULL). `Name, published_at, Version` 순 정렬, zstd. 같은 (Name, Version)이 여러 번 받혔으면 최근 `fetched_at`만 남긴다. 행은 체크포인트가 `done`·`unpublished`인 패키지만 남겨 쓰다 만 패키지의 고아 행을 뺀다. 위 §2-1의 정규화 두 가지(비버전 키 제거, `deprecated`의 `false`·`""` → NULL)를 변환기도 적용하므로, 옛 규칙으로 쌓인 raw도 같은 결과가 된다.
- `registry_status`: 패키지 1행 — `name, rank, status(READY / NOT_FOUND / UNPUBLISHED / FAILED / PENDING), n_versions, n_versions_unpublished, first_published_at, last_published_at, modified, fetched_at, http, doc_bytes, error`. 화면·통계에서 "자료 없음"을 0과 구분하는 용도(공통-R03). `UNPUBLISHED` = 패키지 전체가 unpublish 되어 `versions`가 없는 문서(09-10 run 429건), `PENDING` = 수집 중 변환했을 때 아직 안 받은 패키지(완료 run 에서는 0). 체크포인트가 정본이다.
- 변환은 임시 폴더에 쓴 뒤 교체한다(도중에 죽어도 이전 Parquet 유지). `checkpoint.sqlite`가 없으면 변환하지 않는다. 출력 폴더에 `registry_source.json`으로 어느 run에서 만들었는지 남기고, 다른 run으로 덮어쓰려 하면 멈춘다(`--force`로 해제). 스모크 run을 가리킨 채 본 결과를 날리는 사고를 막기 위함이다.
- `pipeline/duckdb/duckdb_ui.py`의 `datasets()`에 두 뷰를 추가한다(다른 뷰와 같은 방식).

---

## 3. 파이프라인 구현 — `pipeline/collectors/registry/`

**downloads 수집기(`pipeline/collectors/downloads/`)를 복사해 고치는 것이 가장 빠르다.** 토큰버킷·429 적응형 간격·SQLite 체크포인트·manifest·현황판·더블클릭 `.cmd`가 전부 그대로 필요하다. 차이는 "작업 1개 = 패키지 1개 요청"이고 응답 파싱만 다르다.

| 파일 | 역할 | 복사 원본 |
|---|---|---|
| `collect.py` | 대상 CSV → 패키지별 작업 → 요청 → 파싱 → jsonl.gz + 체크포인트 + manifest | `downloads/collect.py` |
| `to_parquet.py` | raw → `registry_versions` + `registry_status` Parquet. 쓰는 중인 part 건너뛰기, 잘린 gzip 복구 포함 | `downloads/to_parquet.py` |
| `status.py` | 현황 한 화면(실행 여부·진행률·속도·429·ETA·평균 문서 크기·not_found 수). `--watch`로 60초 갱신 | `downloads/status.py` |
| `start_registry.cmd` | 더블클릭 시작·재시작. 이미 돌고 있으면 새로 띄우지 않음. `OSS_SHIFT_UA_CONTACT` 없으면 안내 후 종료 | `downloads/start_backfill.cmd` |
| `status_watch.cmd` | 현황 창(더블클릭, 60초 갱신) | `downloads/status_watch.cmd` |
| `README.md` | 파일 역할·실행 명령·출력 형식·주의 | `downloads/README.md` |
| `test_collect.py` | 파싱 계약과 리뷰에서 나온 함정을 고정하는 단위 시험(`python -m unittest discover -s pipeline/collectors/registry`) | 없음(신규) |

### 3-1. 순서

1. **스모크(필수, 먼저).** 순위 1~20 패키지만 받아 (a) 평균·최대 문서 크기, (b) 요청당 시간, (c) 429 여부를 잰다. 결과를 이 문서 §7에 적고 간격(`--interval`)을 정한다. 기본 0.5초, 429가 보이면 1.0초.
2. 본 실행. `start_registry.cmd` 더블클릭(밤새). PC 절전 끄기.
3. 중간에 `status_watch.cmd`로 확인. 멈추면 같은 `.cmd`로 재시작(체크포인트부터 이어감).
4. 끝나면 `to_parquet.py` → `duckdb_ui.py -c "select count(*) from registry_versions"`.
5. 검증(§5) → README·이 문서 §7 갱신 → 커밋·MR.

### 3-2. 체크포인트·재시작 규칙

- `checkpoint.sqlite`의 `tasks` 표: `name, rank, status(pending/done/not_found/unpublished/failed), http, attempts, fetched_at, bytes, n_versions, n_unpublished, modified, error`. 시작 시 대상 CSV를 `INSERT OR IGNORE`로 넣고 `pending`만 처리한다. `unpublished` = 패키지 전체 unpublish 문서(`versions` 없음 + `time.unpublished`), `modified`는 이 경우에도 기록한다(주간 갱신 비교용).
- 404 → `not_found`(재시도 없음). 5xx·연결 오류 → 10초 후 재시도, 4회 넘으면 `failed`. 429 → 연속 횟수에 따라 2^n초(최대 60초), 5회 연속이면 5분 휴식, 간격 15% 증가(상한 3초, `--interval`이 그보다 크면 `--interval`). 같은 패키지에서 429가 8회면 `failed`(`http429:`)로 내린다. 상한이 없으면 영구 스로틀에 걸린 패키지가 `pending`으로 남아 `--retry-failed`로도 못 건지고, 현황판은 계속 RUNNING으로 보인다.
- **인터넷 끊김**은 실패로 세지 않는다. 연결 오류가 나면 `/-/ping`으로 끊김인지 확인하고, 끊김이면 시도 횟수를 소모하지 않은 채 30초마다 재확인해 복구 후 같은 패키지부터 이어간다(09-09 실행 중 1.6시간 끊김으로 186건이 실패 처리된 뒤 추가). 따라서 `conn:` 실패는 온라인 상태의 전송 오류 4회를 뜻하며 조사 대상이다.
- 응답 파싱·행 쓰기 실패(JSON 깨짐·객체 아님·`versions` 없음·인코딩 불가 문자 등 **모든 예외**) → `failed`에 `parse:<예외>` 사유 기록. 예외를 밖으로 흘리면 작업이 `pending`으로 남아 재시작마다 같은 패키지에서 죽으므로 반드시 잡는다. `failed`는 종류를 가리지 않고 다음 실행에서 `--retry-failed`로만 다시 시도.
- 문서는 스트리밍으로 받아 압축 해제 기준 200 MB(`--max-doc-mb`)를 넘으면 `failed`(`too_large:>NB`). 09-10 run 최대는 115 MB(`rendition`)로 상한에 걸린 패키지는 없었다. 스트리밍 파싱은 구현하지 않았다.
- 체크포인트 commit 직전에 항상 gzip을 flush한다(오프라인 대기 진입·종료 시 포함). 강제 종료돼도 "체크포인트는 done인데 행이 없는" 패키지가 생기지 않게 하기 위함. 종료 시에는 파일을 먼저 닫고 commit한다.
- **변환기는 확실할 때만 마지막 part를 복구한다.** 복구는 원본을 `.broken`으로 rename하는 동작이라, 살아 있는 파일에 하면 수집기가 고아 inode에 계속 쓰고 그 뒤 행이 전부 사라진다(리눅스). 수집기 프로세스 수가 정확히 0이고 파일이 120초 이상 조용할 때만 손대고, 알 수 없으면(`alive()`가 -1) 건너뛴다. 프로세스를 확인할 수 없는 환경에서 죽은 수집기의 잘린 part를 살리려면 `--repair-newest`를 명시한다.
- 로그를 파일로 리다이렉트하면 파이썬 stdout 인코딩이 로캘(cp949)로 정해진다. `start_registry.cmd`가 그렇게 띄우므로 수집기는 시작할 때 stdout·stderr를 utf-8로 고정한다. `chcp 65001`은 콘솔 코드페이지만 바꿔 도움이 되지 않는다.

### 3-3. 주간 갱신 연결 (S15P21A506-273 에서)

`--mode weekly`: 체크포인트의 `modified`와 새 응답의 `time.modified`가 같으면 파싱 없이 건너뛴다. 갱신 대상은 `registry_status`에서 `last_published_at`이 최근 90일인 패키지로 좁힐 수 있다.

---

## 4. 규모 견적 (스모크 후 갱신)

| 항목 | 가정 | 값 |
|---|---|---|
| 요청 수 | 상위 10만 | 100,000 |
| 시간 | 간격 0.5초, 평균 응답 0.3초 | ≈ 14~22시간 |
| 전송량 | 평균 문서 200KB(압축 전) 가정 | ≈ 20GB (압축 전) |
| 저장량 | 필요한 열만, 버전당 ~300B, 패키지당 평균 40버전 | ≈ 1.2GB(비압축) → jsonl.gz 약 200MB, Parquet 약 150MB |
| 버전 행 | 평균 40 | ≈ 4,000,000 |

---

## 5. 검증

1. **실행용 의존은 deps.dev와 같아야 한다.** `registry_versions.Dependencies`와 deps.dev `requirements.Dependencies`를 (name, version) 100건 무작위 대조. 다르면 원인(발행 후 수정·unpublish)을 적는다.
2. **개발용 의존 눈검사** — `enzyme`을 DevDependencies에 가진 패키지 20개를 뽑아 실제 npm 페이지와 대조.
3. **이동 검출 확인** — 아래 쿼리가 0이 아니어야 한다. 두 가지를 지킨다.

   **unpublish 행을 뺀다.** 의존을 모르므로(NULL) 비교에 넣으면 "enzyme 있던 버전 → unpublish 버전"이 제거 전이로 잡힌다. 09-10 run에서 2,620건(31% 과대)이 실제로 나왔다.

   **라인을 나눈다.** 패키지를 한 줄로 세워 시각 순 인접쌍을 비교하면 유지보수 릴리스(5.0.0 뒤에 나온 4.17.3)가 다른 라인의 버전과 짝지어져 가짜 전이가 생긴다. 실측으로 정렬 방식에 따라 결과가 981~2,345건까지 흔들렸다. 이동쌍 빌더(`pipeline/duckdb/build_migration_pairs.py`)가 이미 `PARTITION BY Name, line ORDER BY published_at` 으로 라인을 나누고 릴리스만 보므로 같은 규칙을 쓴다. 그래야 그 빌더에 개발용 의존(`kind: dev`)을 넣었을 때 나올 값과 일치한다.

   ```sql
   -- enzyme 을 개발용 의존에서 뺀 연속 릴리스 전이 수 (09-09 run: 536건 / 474 패키지)
   WITH rel AS (
     SELECT Name, Version, published_at,
            CASE WHEN try_cast(regexp_extract(Version, '^(\d+)\.(\d+)', 1) AS INT) > 0
                 THEN regexp_extract(Version, '^(\d+)\.(\d+)', 1)
                 ELSE '0.' || regexp_extract(Version, '^(\d+)\.(\d+)', 2) END AS line,
            list_transform(DevDependencies, d -> d.Name) AS dev
     FROM registry_versions
     WHERE NOT unpublished AND published_at IS NOT NULL
       AND regexp_matches(Version, '^\d+\.\d+') AND NOT contains(Version, '-')),
   v AS (SELECT Name, dev, lag(dev) OVER (PARTITION BY Name, line ORDER BY published_at, Version) AS prev_dev FROM rel)
   SELECT count(*) AS transitions, count(DISTINCT Name) AS packages
   FROM v WHERE list_contains(prev_dev, 'enzyme') AND NOT list_contains(dev, 'enzyme');
   ```

   전이 수는 정렬 정의에 민감하므로 **정렬에 무관한 보조 지표**를 같이 본다 — "enzyme을 쓴 적 있고 최신 버전에는 없는 패키지 수"(09-09 run: 827개). '최신'을 시각 기준으로 잡든 semver 기준으로 잡든 1,419개 중 20개만 달라진다. 쿼리는 `pipeline/collectors/registry/README.md` 의 검증 절에 있다.

   deps.dev 대조(1번)는 `registry_versions`를 먼저 표본 추출한 뒤 조인한다. 조인 뒤에 `USING SAMPLE`을 붙이면 전체 조인이 먼저 실행돼 메모리 19 GB를 넘긴다(§7). `requirements`는 `snapshot`을 하나로 고정한다.
4. `registry_status`의 NOT_FOUND 목록이 downloads의 `NOT_FOUND` 781개와 대부분 겹치는지.

---

## 6. 주의

- **개인 이메일을 코드에 넣지 않는다.** UA 연락처는 환경변수. `.cmd`도 변수 없으면 시작하지 않게 한다(downloads와 동일).
- **원본 문서를 통째로 보존하지 않는다.** 크기 편차 때문. 다시 필요하면 다시 받는다(패키지당 1회라 비용이 작다).
- **이 수집은 X가 아니라 dependent를 받는 것이다.** "enzyme의 이동"을 보려고 enzyme 문서를 받는 게 아니라, enzyme을 쓰던 상위 10만 패키지들의 문서를 받는다. 결과적으로 상위 10만 밖의 패키지가 개발용 의존을 어떻게 바꿨는지는 알 수 없다(범위 한계, 문서에 적어 둘 것).
- **이동쌍 빌더 반영은 S15P21A506-136 착수 때.** 이 수집만으로 결과가 바로 바뀌지 않는다. 빌더에 "의존 종류(kind: regular/dev)" 열을 넣어 개발용 의존 제거·추가를 같은 절차로 세는 확장이 필요하다.
- **브랜치.** 이 수집기는 origin/develop에서 딴 `data/feat/S15P21A506-280-registry-collector`(팀 규칙 `<part>/<type>/<이슈키>-작업내용`, AGENTS.md §4.2)로 작업한다 → MR !108. `pipeline/README.md`의 폴더 표와 `docs/README.md` 목록에 한 줄씩 추가한다(둘 다 develop 기준 최신본을 수정).
- **원본 보존은 GCS가 아니라 서버 MinIO.** 처음 계획은 `gs://oss-shift-a506-raw/raw/registry/`였지만, downloads·keywords가 GCS에 올라가지 않고 서버 MinIO `pickage-raw` Bronze로 입고된 뒤라(S15P21A506-278, `pipeline/downloads/`) registry도 같은 경로를 따른다(2026-09-10 결정). 입고는 검증 절차(압축·JSON 구조·체크포인트 대조)를 포함하므로 이 이슈가 아니라 별도 티켓에서 downloads 입고 모듈을 본떠 만든다. 그때까지 정본은 전진님 PC `data/registry/raw/run=2026-09-09/`(765 MB) + `checkpoint.sqlite`·`manifest.json`.

---

## 7. 실측 기록 (2026-09-09 ~ 09-10 실행)

| 항목 | 값 | 비고 |
|---|---|---|
| 스모크 20건 평균 문서 크기 | 725 KB (중앙값 약 120 KB) | 2026-09-09 10:47 KST, 순위 1~20. 상위 20은 버전이 많아 평균이 위로 치우침. 버전 행 3,798개(패키지당 평균 190) |
| 스모크 20건 최대 문서 크기 | 10.6 MB | `@types/node` (2,360버전). 그 다음 type-fest 556 KB, glob 458 KB. 200 MB 상한(`--max-doc-mb`)에 여유 |
| 요청당 평균 시간 | 0.5초 미만 | 20요청에 9초. 응답 시간이 간격 0.5초 안에 끝나 간격이 속도를 결정 |
| 429 발생 | 0건 | 404·5xx·연결 오류도 0건 |
| 확정 간격 | **0.5초** | 10만 건 ≈ 14시간. `start_registry.cmd` INTERVAL=0.5. 본 실행 중 429가 보이면 수집기가 스스로 늘림 |
| 본 실행 시작·종료 | 2026-09-09 10:53 KST → 2026-09-10 15:14 KST | 벽시계 약 28시간, 순 수집 약 18시간(인터넷 끊김 약 1.6시간 + 밤 절전 약 9시간 제외). 끊김 구간(순위 40,900~41,085) 186건이 conn 실패로 기록돼 수집기를 보강(끊김이면 복구 대기, §3-2)한 뒤 재수집. 그때 넣었던 "재시작 시 conn: 실패 자동 재시도"는 리뷰(09-11)에서 제거 — 온라인 상태의 전송 오류까지 매 재시작마다 다시 받게 되고 사유가 지워지기 때문. 429는 끝까지 0건, 간격 0.5초 유지 |
| 결과 READY / NOT_FOUND / FAILED | **99,209 / 358 / 0** (+ UNPUBLISHED 429) | 대상 CSV에 이름 중복 4건이 있어 작업 수는 99,996. UNPUBLISHED = 패키지 전체가 unpublish 되어 `versions` 가 없는 문서 |
| 전송·저장량 | 원본 문서 73.4 GB(압축 해제 기준), 평균 723 KB, 최대 115 MB | jsonl.gz 765 MB(4,291 part) → `registry_versions` Parquet 403 MB + `registry_status` 5 MB. 견적(§4)보다 문서가 3.6배 컸지만 200 MB 상한 안 |
| 버전 행 수 | **21,435,586** (패키지당 평균 216) | unpublish 버전 827,938 · DevDependencies 가 있는 행 14,577,460. 체크포인트 `n_versions` 합계와 일치(행 유실 0, 비버전 `time` 키에서 생긴 가짜 버전 1행 제외). 가장 이른 발행 2010-11-09 |
| enzyme 개발용 의존 제거 전이 수(§5-3) | **536건 / 474 패키지** | 이동쌍 빌더와 같은 규칙(라인 분할·릴리스만). 그중 126건은 같은 전이에서 `@testing-library/react` 를 새로 넣음. 연도별 2016 2 → 2019 75 → 2022 97(정점) → 2026 27. 참고: tslint 제거 1,630건(그중 eslint 추가 642). **옛 규칙(패키지를 한 줄로 세워 시각 순 비교)에서는 1,999건 / 871 패키지였다** — 유지보수 릴리스가 다른 라인의 버전과 짝지어져 부풀었다 |
| 정렬 무관 보조 지표(§5-3) | **827 패키지** | enzyme 을 쓴 적 있고 최신 버전에는 없는 패키지. '최신'을 시각 기준으로 잡든 semver 기준으로 잡든 1,419개 중 20개만 달라져 전이 수보다 안정적이다 |
| `deprecated` 정규화(2026-09-14) | 1,026,126행 → **1,016,561행** | 불리언 `false` 9,561행 · `true` 1,145행 · `""` 4행이 문자열로 저장돼 있었다. `false`·`""` 를 NULL 로 바꿔 `deprecated IS NOT NULL` 이 그대로 "폐기된 버전"이 되게 했다 |
| 본 실행 deps.dev 대조(§5-1) | 표본 2,000 중 1,985 매칭, **1,985 / 1,985 일치** | 스냅샷 2026-08-31 `requirements` 기준. 미매칭 15 = 스냅샷 이후 발행 13 + `@dais/sdk-minimal`(버전 수만 개) 2. 전체 조인은 메모리 19 GB 를 넘겨 표본 방식으로 대체 |
| 미존재 대조(§5-4) | downloads NOT_FOUND 781 중 744 겹침 | 나머지 37은 `@diotoborg/…`류 스팸 패키지로 registry 에는 있고 downloads API 만 값이 없음. registry NOT_FOUND 인데 downloads 가 있는 것 2 |
| 개발용 의존 눈검사(§5-2) | 최신 버전에 enzyme 을 개발용 의존으로 둔 상위 20: react-select · react-quill · rc-* 계열 등 | 실제 npm 페이지 대조는 팀 리뷰 때 표본 확인 |
