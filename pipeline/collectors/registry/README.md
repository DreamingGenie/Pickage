# npm registry 버전 이력 수집기 (devDependencies 포함)

계획: `docs/api & data/수집계획_devDependencies_npmRegistry_260909.md` (§3 파이프라인 구현). Jira S15P21A506-280. 데이터는 `/data/registry/`(gitignore)에 쌓인다.
downloads 수집기(`../downloads/`)를 복사해 고친 것이라 파일 구성·재시작 규칙·현황판이 같다. 차이는 "작업 1개 = 패키지 1개 요청"이고 응답 파싱만 다르다.

## 왜 받나

deps.dev 에는 개발용 의존(devDependencies)이 없어 테스트·검사·빌드 도구(enzyme, tslint, mocha 등)의 이동이 이동쌍 결과에 보이지 않는다.
npm 공식 저장소(`registry.npmjs.org/<name>`)는 요청 한 번에 패키지의 **전 버전 선언 문서**를 주므로, 패키지당 1회 요청으로 버전별 dependencies·devDependencies·peer·optional·발행 시각을 확보한다.
**이 수집은 X 가 아니라 dependent 를 받는 것이다.** enzyme 문서가 아니라 enzyme 을 쓰던 상위 10만 패키지들의 문서를 받는다. 상위 10만 밖의 패키지가 개발용 의존을 어떻게 바꿨는지는 알 수 없다(범위 한계).

## 파일

| 파일 | 역할 |
|---|---|
| `collect.py` | 대상 CSV → 패키지별 요청(전체 문서) → 버전 행으로 파싱 → jsonl.gz. 요청 간격 토큰버킷(`--interval`, 기본 0.5초), 429 지수 백오프(15%씩 늘려 최대 3초, 연속 5회면 5분 휴식), 5xx·연결 오류 4회 재시도, SQLite 체크포인트, manifest.json. 원본 문서는 보존하지 않고 200MB(`--max-doc-mb`) 넘는 문서는 `failed` |
| `to_parquet.py` | raw → `registry_versions/part-00000.parquet` + `registry_status.parquet`. (Name, Version) 중복은 최근 fetched_at 만 남김. 수집 중에도 실행 가능(쓰고 있는 part 는 건너뜀, 잘린 part 복구) |
| `status.py` | 진행 상태 한 화면(실행 여부·진행률·성공/미존재/전체삭제/실패·평균/최대 문서 크기·버전 행 수·속도·429·ETA). `--watch` 60초 갱신, `--refresh-parquet` 로 DuckDB UI 뷰까지 최신화 |
| `start_registry.cmd` | 시작·재시작(더블클릭). 이미 돌고 있으면 새로 띄우지 않음. `OSS_SHIFT_UA_CONTACT` 없으면 안내 후 종료. 간격은 파일 머리의 `INTERVAL` |
| `status_watch.cmd` | 현황 창(더블클릭). 60초 갱신, 닫아도 수집기 영향 없음 |

## 대상 목록

ecosyste.ms 다운로드 순위 상위 10만 `datasets/targets/rank_top100k_20260902.csv`(컬럼 `rank,name,downloads_last_month,dependent_packages_count,status`). downloads 수집과 같은 목록이다(만든 경위는 `../downloads/README.md`).
`collect.py` 는 User-Agent 연락처를 환경변수 `OSS_SHIFT_UA_CONTACT`(이메일 또는 URL)로 받는다. 비어 있으면 시작하지 않는다. 개인 주소를 코드나 `.cmd` 에 적지 않는다.

## 실행

```bash
# 스모크 (순위 1~20). 문서 크기·속도·429 를 재고 간격을 정한다. 결과는 계획 문서 §7 에 적는다
.venv-bq/Scripts/python.exe pipeline/collectors/registry/collect.py --targets datasets/targets/rank_top100k_20260902.csv --run smoke-2026-09-09 --out data/registry/raw --interval 0.5 --limit 20

# 본 실행 (10만 건, 간격 0.5초면 약 14시간·1초면 약 28시간). 중단 후 같은 명령으로 재시작하면 체크포인트부터 이어감
.venv-bq/Scripts/python.exe pipeline/collectors/registry/collect.py --targets datasets/targets/rank_top100k_20260902.csv --run 2026-09-09 --out data/registry/raw --interval 0.5

# 가장 쉬운 시작·재시작: 탐색기에서 더블클릭 (이미 돌고 있으면 새로 띄우지 않음). 밤새 돌릴 때는 PC 절전을 끈다
pipeline\collectors\registry\start_registry.cmd

# failed 만 다시 시도
.venv-bq/Scripts/python.exe pipeline/collectors/registry/collect.py --targets datasets/targets/rank_top100k_20260902.csv --run 2026-09-09 --out data/registry/raw --retry-failed

# Parquet 변환 → DuckDB 뷰 registry_versions / registry_status (pipeline/duckdb/duckdb_ui.py)
.venv-bq/Scripts/python.exe pipeline/collectors/registry/to_parquet.py --raw data/registry/raw/run=2026-09-09 --out data/registry/parquet
.venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py -c "select count(*) from registry_versions"

# GCS 업로드 (계획 §6 경로)
gcloud storage rsync -r data/registry/raw/run=2026-09-09 gs://oss-shift-a506-raw/raw/registry/run=2026-09-09
```

Windows에서 장시간 실행은 `start_registry.cmd`(별도 최소화 창)로 띄운다. **Claude Code 세션이 띄운 프로세스는 앱을 닫으면 함께 죽을 수 있으니**, 밤새 돌릴 때는 전진님 터미널이나 더블클릭으로 직접 띄운다. PC 절전 시 멈추고 깨어나면 이어간다.
같은 IP 에서 수집기 두 개를 동시에 돌리지 않는다(429 만 늘어남). downloads 주간 갱신과 겹치면 하나가 끝난 뒤 시작한다.

## 출력 형식

`raw/run=<run>/part-NNNNN.jsonl.gz` — 한 줄 = 패키지 1개 × 버전 1개. 열 이름·구조는 deps.dev `requirements`(`NPMRequirements`)와 같게 맞췄고 `DevDependencies` 만 새 열이다. 5,000줄마다 파일 회전.

```json
{"Name":"chalk","Version":"4.1.2","published_at":"2021-07-30T12:02:52.839Z","rank":9,
 "Dependencies":[{"Name":"ansi-styles","Requirement":"^4.1.0"},{"Name":"supports-color","Requirement":"^7.1.0"}],
 "DevDependencies":[{"Name":"xo","Requirement":"^0.28.2"},{"Name":"ava","Requirement":"^2.4.0"}],
 "PeerDependencies":[],"OptionalDependencies":[],
 "deprecated":null,"unpublished":false,
 "fetched_at":"2026-09-09T12:00:00+00:00","modified":"2026-07-26T14:51:07.471Z"}
```

- `time[버전]` 이 발행 시각(UTC). `time.created`·`modified`·`unpublished` 는 버전이 아니라 건너뛴다.
- `versions` 에 없고 `time` 에만 있는 버전 = unpublish 된 버전(예: chalk 5.6.1). **행은 남기고 의존은 빈 값, `unpublished=true`**.
- `deprecated` 는 버전 단위 문구(없으면 null). 폐기 데이터셋(S15P21A506-272)과 대조 가능.
- `modified` 는 문서의 `time.modified`. 주간 갱신(S15P21A506-273)에서 이 값이 바뀐 패키지만 다시 받는 근거로 쓴다(이번 수집기에는 주간 모드가 없다).
- 축약 응답(`Accept: application/vnd.npm.install-v1+json`)은 devDependencies 가 빠지므로 쓰지 않는다.

`checkpoint.sqlite` 의 `tasks.status`: `pending` / `done` / `not_found`(404) / `unpublished`(패키지 전체가 unpublish 되어 `versions` 없음) / `failed`(`error` 에 사유: `too_large:>NB`, `parse:…`, `conn:…`, 5xx 본문). `--retry-failed` 로만 다시 시도한다.

### Parquet (`data/registry/parquet/`)

- `registry_versions/part-00000.parquet` — 위 열 그대로. 시각은 UTC TIMESTAMP, 배열은 `STRUCT(Name, Requirement)[]`. Name 순 정렬, zstd.
- `registry_status.parquet` — 패키지 1행: `name, rank, status(READY / NOT_FOUND / UNPUBLISHED / FAILED / PENDING), n_versions, n_versions_unpublished, first_published_at, last_published_at, modified, fetched_at, http, doc_bytes, error`. 화면·통계에서 "자료 없음"을 0 과 구분하는 용도. 체크포인트가 정본이라 수집 중이면 PENDING 이 남는다.

## 진행 확인

```bash
# 현황 창 (더블클릭)
pipeline\collectors\registry\status_watch.cmd
# 한 화면 요약. --watch 를 붙이면 60초마다 갱신
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-09 --watch
# 요약 + Parquet 갱신 → DuckDB UI 의 registry_versions 뷰에 지금까지 받은 패키지가 전부 보임
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-09 --refresh-parquet

# 원시 로그
tail -3 data/registry/raw/registry_2026-09-09.log
python -c "import sqlite3;print(sqlite3.connect('data/registry/raw/run=2026-09-09/checkpoint.sqlite').execute('select status,count(*) from tasks group by status').fetchall())"
```

## 검증 (계획 §5)

```sql
-- enzyme 을 개발용 의존에서 뺀 연속 버전 전이 수 (0 이 아니어야 함)
WITH v AS (
  SELECT Name, Version, published_at,
         list_transform(DevDependencies, d -> d.Name) AS dev,
         lag(list_transform(DevDependencies, d -> d.Name)) OVER (PARTITION BY Name ORDER BY published_at) AS prev_dev
  FROM registry_versions)
SELECT count(*) FROM v WHERE list_contains(prev_dev, 'enzyme') AND NOT list_contains(dev, 'enzyme');

-- 실행용 의존은 deps.dev 와 같아야 한다 (표본 대조)
SELECT r.Name, r.Version, r.Dependencies AS registry, q.Dependencies AS depsdev
FROM registry_versions r JOIN requirements q ON q.Name = r.Name AND q.Version = r.Version
USING SAMPLE 100;
```
