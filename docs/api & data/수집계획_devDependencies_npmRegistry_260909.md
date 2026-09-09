# npm registry 버전 이력 수집계획 — 상위 10만 패키지의 devDependencies 포함 의존 선언

작성 2026-09-09 · Jira **S15P21A506-280** · 대상 `data/registry/` → DuckDB 뷰 `registry_versions` · 상태 **계획 확정, 다른 세션에서 실행**
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
| 결과는 어디에 | 원본은 남기지 않고 필요한 열만 `data/registry/raw/run=<날짜>/part-*.jsonl.gz`, 변환 결과는 `data/registry/parquet/`. `data/`는 gitignore, 팀 공유는 GCS. |

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
- `versions`에 없는데 `time`에만 있는 버전 = 삭제(unpublish)된 버전. 발행 시각은 알지만 선언은 모른다. **버전 행은 남기고 의존은 빈 값**으로 둔다(사라졌다는 사실 자체가 정보).
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
- 파일은 5,000줄마다 회전(downloads의 `Writer`와 같음). 진행 기록은 SQLite 체크포인트(§3-2).

### 2-2. 변환 — `data/registry/parquet/registry_versions/part-*.parquet` + `registry_status.parquet`

- `registry_versions`: 위 열 그대로(배열은 STRUCT 리스트). `name`으로 정렬, zstd.
- `registry_status`: 패키지 1행 — `name, rank, status(READY / NOT_FOUND / FAILED), n_versions, n_versions_unpublished, first_published_at, last_published_at, modified, fetched_at`. 화면·통계에서 "자료 없음"을 0과 구분하는 용도(공통-R03).
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

### 3-1. 순서

1. **스모크(필수, 먼저).** 순위 1~20 패키지만 받아 (a) 평균·최대 문서 크기, (b) 요청당 시간, (c) 429 여부를 잰다. 결과를 이 문서 §7에 적고 간격(`--interval`)을 정한다. 기본 0.5초, 429가 보이면 1.0초.
2. 본 실행. `start_registry.cmd` 더블클릭(밤새). PC 절전 끄기.
3. 중간에 `status_watch.cmd`로 확인. 멈추면 같은 `.cmd`로 재시작(체크포인트부터 이어감).
4. 끝나면 `to_parquet.py` → `duckdb_ui.py -c "select count(*) from registry_versions"`.
5. 검증(§5) → README·이 문서 §7 갱신 → 커밋·MR.

### 3-2. 체크포인트·재시작 규칙

- `checkpoint.sqlite`의 `tasks` 표: `name, rank, status(pending/done/not_found/failed), http, attempts, fetched_at, bytes, n_versions, error`. 시작 시 대상 CSV를 `INSERT OR IGNORE`로 넣고 `pending`만 처리한다.
- 404 → `not_found`(재시도 없음). 5xx·연결 오류 → 10초 후 재시도, 4회 넘으면 `failed`. 429 → 연속 횟수에 따라 2^n초(최대 60초), 5회 연속이면 5분 휴식, 간격 15% 증가(최대 3초).
- 응답 파싱 실패(JSON 깨짐·`versions` 없음) → `failed`에 사유 기록. 다음 실행에서 `--retry-failed`로만 다시 시도.
- 문서가 50MB를 넘으면 스트리밍으로 읽되, 그래도 실패하면 `failed`로 두고 사유에 크기를 적는다. 그런 패키지는 손으로 확인한다.

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
3. **이동 검출 확인** — 아래 쿼리가 0이 아니어야 한다.
   ```sql
   -- enzyme 을 개발용 의존에서 뺀 연속 버전 전이 수
   WITH v AS (
     SELECT Name, Version, published_at,
            list_transform(DevDependencies, d -> d.Name) AS dev,
            lag(list_transform(DevDependencies, d -> d.Name)) OVER (PARTITION BY Name ORDER BY published_at) AS prev_dev
     FROM registry_versions)
   SELECT count(*) FROM v WHERE list_contains(prev_dev, 'enzyme') AND NOT list_contains(dev, 'enzyme');
   ```
4. `registry_status`의 NOT_FOUND 목록이 downloads의 `NOT_FOUND` 781개와 대부분 겹치는지.

---

## 6. 주의

- **개인 이메일을 코드에 넣지 않는다.** UA 연락처는 환경변수. `.cmd`도 변수 없으면 시작하지 않게 한다(downloads와 동일).
- **원본 문서를 통째로 보존하지 않는다.** 크기 편차 때문. 다시 필요하면 다시 받는다(패키지당 1회라 비용이 작다).
- **이 수집은 X가 아니라 dependent를 받는 것이다.** "enzyme의 이동"을 보려고 enzyme 문서를 받는 게 아니라, enzyme을 쓰던 상위 10만 패키지들의 문서를 받는다. 결과적으로 상위 10만 밖의 패키지가 개발용 의존을 어떻게 바꿨는지는 알 수 없다(범위 한계, 문서에 적어 둘 것).
- **이동쌍 빌더 반영은 S15P21A506-136 착수 때.** 이 수집만으로 결과가 바로 바뀌지 않는다. 빌더에 "의존 종류(kind: regular/dev)" 열을 넣어 개발용 의존 제거·추가를 같은 절차로 세는 확장이 필요하다.
- **브랜치.** 이 수집기는 develop에서 새 브랜치(`feat/S15P21A506-280-registry-collector`)로 작업한다. !81(이동쌍) 브랜치와 파일이 겹치지 않는다. `pipeline/README.md`의 폴더 표와 `docs/README.md` 목록에 한 줄씩 추가한다(둘 다 develop 기준 최신본을 수정).
- **GCS 업로드**는 수집 완료 후 `gs://oss-shift-a506-raw/raw/registry/run=<날짜>/`. S15P21A506-142에 남은 downloads·keywords 업로드와 함께 한 번에 올리면 된다.

---

## 7. 실측 기록 (실행 세션이 채움)

| 항목 | 값 | 비고 |
|---|---|---|
| 스모크 20건 평균 문서 크기 | | |
| 스모크 20건 최대 문서 크기 | | 패키지명 |
| 요청당 평균 시간 | | |
| 429 발생 | | |
| 확정 간격 | | |
| 본 실행 시작·종료 | | |
| 결과 READY / NOT_FOUND / FAILED | | |
| 버전 행 수 | | |
| enzyme 개발용 의존 제거 전이 수(§5-3) | | |
