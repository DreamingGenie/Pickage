# npm registry 버전 이력 수집기 (devDependencies 포함)

계획: `docs/api & data/수집계획_devDependencies_npmRegistry_260909.md` (§3 파이프라인 구현). Jira S15P21A506-280. 데이터는 `/data/registry/`(gitignore)에 쌓인다.
downloads 수집기(`../downloads/`)를 복사해 고친 것이라 파일 구성·재시작 규칙·현황판이 같다. 차이는 "작업 1개 = 패키지 1개 요청"이고 응답 파싱만 다르다.

## 왜 받나

deps.dev 에는 개발용 의존(devDependencies)이 없어 테스트·검사·빌드 도구(enzyme, tslint, mocha 등)의 이동이 이동쌍 결과에 보이지 않는다.
npm 공식 저장소(`registry.npmjs.org/<name>`)는 요청 한 번에 패키지의 **전 버전 선언 문서**를 주므로, 패키지당 1회 요청으로 버전별 dependencies·devDependencies·peer·optional·발행 시각을 확보한다.
**2026-09-16 추가(S15P21A506-366)**: 같은 문서에서 버전별 **패키지 형태 6열**도 같이 남긴다 —
`unpacked_size`·`file_count`(설치 크기), `module_type`·`main`·`types`·`exports`(모듈 형태·진입점·타입 제공).
`license` 는 받지 않는다. deps.dev `PackageVersions.Licenses` 로 이미 가지고 있어서(registry 행의 88.3% 가 매칭) 조인으로 해결한다.
원본 문서를 보존하지 않으므로(§ S15P21A506-340) 열을 덧붙이려면 전량 재수집뿐이고, 그래서 4분할로 다시 받는다.

**이 수집은 X 가 아니라 dependent 를 받는 것이다.** enzyme 문서가 아니라 enzyme 을 쓰던 상위 10만 패키지들의 문서를 받는다. 상위 10만 밖의 패키지가 개발용 의존을 어떻게 바꿨는지는 알 수 없다(범위 한계).

## 파일

| 파일 | 역할 |
|---|---|
| `collect.py` | 대상 CSV → 패키지별 요청(전체 문서) → 버전 행으로 파싱 → jsonl.gz. 요청 간격 토큰버킷(`--interval`, 기본 0.5초), 429 지수 백오프(15%씩 늘려 상한 3초, 연속 5회면 5분 휴식, 같은 패키지에서 8회면 `failed`), 5xx·연결 오류 4회 재시도, SQLite 체크포인트, manifest.json. 원본 문서는 보존하지 않고 200MB(`--max-doc-mb`) 넘는 문서는 `failed` |
| `shard_targets.py` | 대상 CSV → 샤드 N개. 순위로 **돌아가며** 나눠(1→s1, 2→s2, …) 샤드들이 같은 순위 분포를 갖게 한다. 이름 중복은 상위 순위만 남긴다. 실제 배치는 아래 "샤드 배치" 절 |
| `to_parquet.py` | raw → `registry_versions/part-00000.parquet` + `registry_status.parquet`. **`--raw` 에 run 폴더를 여러 개 줄 수 있다**(분할 수집). (Name, Version) 중복은 최근 fetched_at 만 남김. 수집 중에도 실행 가능(쓰고 있는 part 는 건너뜀, 아무도 안 쓰는 잘린 part 는 복구) |
| `status.py` | 진행 상태 한 화면(실행 여부·진행률·성공/미존재/전체삭제/실패·평균/최대 문서 크기·버전 행 수·속도·429·ETA). **`--shards N` 을 주면 샤드를 합산**해 전체 진행률·완료 예상 시각을 함께 낸다. `--watch` 60초 갱신, `--refresh-parquet` 로 DuckDB UI 뷰까지 최신화 |
| `test_collect.py` | 단위 시험. `python -m unittest discover -s pipeline/collectors/registry -v`. 파싱 계약(unpublish 행 NULL·비버전 time 키·deprecated 정규화)과 리뷰에서 나온 함정(쓰기 전 인코딩 확인, cp949 로그, 0바이트·잘린 gzip, 출력 경로 방어)을 고정한다 |
| `start_registry.cmd` | 직렬 1개로 시작·재시작(더블클릭). 이미 돌고 있으면 새로 띄우지 않음. `OSS_SHIFT_UA_CONTACT` 없으면 안내 후 종료. 간격은 파일 머리의 `INTERVAL` |
| `start_registry_sharded.cmd` | **4분할로 시작·재시작(더블클릭).** 대상을 나눈 뒤 `collect.py` 를 샤드 수만큼 띄운다. 실행 검사는 **샤드별**이라, 하나만 죽었을 때 다시 더블클릭하면 그 하나만 이어서 띄운다. 이 RUN 의 샤드가 아닌 수집기가 돌고 있으면 아무것도 띄우지 않는다. 샤드 수·기준 run 이름은 파일 머리의 `SHARDS`·`RUN` |
| `status_watch.cmd` | 현황 창(더블클릭). 60초 갱신, 닫아도 수집기 영향 없음 |
| `status_watch_sharded.cmd` | 4분할 현황 창(더블클릭). 합계 진행률·완료 예상 시각 + 샤드별 상태 |
| `start_registry_additions.cmd` | **확장 목록 추가분 36.9만 4분할 수집(S15P21A506-452).** `start_registry_sharded.cmd` 를 복사해 `RUN`·`TARGETS` 만 바꾼 것이고 로직은 같다. 회차마다 이렇게 사본을 만들고 원본은 건드리지 않는다 |
| `status_watch_additions.cmd` | 위 회차의 현황 창(더블클릭) |

## 실측 (run=2026-09-22-additions, 4분할, 2026-09-23 완료)

확장 목록 468,519 중 상위 10만 밖의 **추가분 368,523개**다. 대상은
`datasets/targets/expanded_468k_additions_20260922.csv` 이고, 그 파일의 `rank` 는 468,519
목록의 순번이라 원래 순위는 `source_rank` 열에 있다. 수집기는 `rank` 로 정렬만 하므로
둘 중 어느 것을 순위로 보든 결과가 달라지지 않는다.

샤드 4개로 92,131 / 92,131 / 92,131 / 92,130 건씩 나눴다. 이름 중복은 0건이다.
**상위 10만과 이름이 겹치지 않는다** — 99,996 + 368,523 = 468,519 로 확장 목록과 정확히 맞는다.
그래서 `to_parquet.py` 나 `build_package_env.py` 에 두 회차를 같이 줘도 (Name, Version) 이 겹치지 않는다.

READY 366,793 · NOT_FOUND 1 · UNPUBLISHED 1,729 · FAILED 0. 버전 행 12,771,101,
원본 39.86 GB 전송 → jsonl.gz 521 MB. 샤드당 간격 0.5초(전체 초당 약 7.4건), **429 0건 ·
5xx 0건 · 연결 오류 0건**, 순 수집 **15시간 5분**(09-22 11:58 ~ 09-23 03:03).

| 샤드 | 대상 | 성공 | 미존재 | 전체삭제 | 버전 행 | 전송 | 평균 문서 |
|---|---|---|---|---|---|---|---|
| s1 | 92,131 | 91,709 | 0 | 422 | 3,192,631 | 10.03 GB | 107 KB |
| s2 | 92,131 | 91,685 | 1 | 445 | 3,162,000 | 9.79 GB | 104 KB |
| s3 | 92,131 | 91,717 | 0 | 414 | 3,195,817 | 10.06 GB | 107 KB |
| s4 | 92,130 | 91,682 | 0 | 448 | 3,220,653 | 9.97 GB | 106 KB |
| 합계 | 368,523 | 366,793 | 1 | 1,729 | 12,771,101 | 39.86 GB | 105 KB |

**상위 10만과 성질이 아주 다르다.** 건수는 3.7배인데 버전 행은 오히려 **적다**.

| | 09-16 (상위 10만) | 09-22 (추가분 36.9만) |
|---|---|---|
| 패키지당 문서 | 739 KB | **105 KB** |
| 패키지당 버전 | 215.7 | **34.8** |
| 전송 총량 | 73.9 GB | **39.86 GB** |
| 버전 행 | 21,567,150 | **12,771,101** |

**진행 중 외삽은 크게 빗나갔다.** 14% 시점(rank 9,884~150,000 구간)의 수치로 전체를 추정하면
전송 104 GB · 버전 행 31.5M 이 나왔는데 실측은 그 40% 였다. 순위가 낮아질수록 문서가 작아지는
정도가 선형이 아니다 — 하위권에는 버전 한두 개짜리 패키지가 몰려 있다. **이 수집에서 진행률로
총량을 추정하려면 최소한 절반은 넘겨야 한다.**

`UNPUBLISHED` 1,729건은 패키지 전체가 npm 에서 내려간 것이다. **비율로는 상위 10만과 거의
같다** — 0.47% 대 0.43%. 건수가 4배인 것은 대상이 3.7배이기 때문이지 하위권이 더 잘 사라져서가
아니다. 이 행들은 **0 으로 채우면 안 된다.**

`NOT_FOUND` 는 **단 1건**이다. 상위 10만의 358건과 크게 다른데, 대상 목록을 만든 시점이
달라서다 — 상위 10만 목록은 2026-09-02 ecosyste.ms 순위이고 추가분은 09-22 확장 목록이라
그 사이에 사라진 이름이 이미 걸러져 있다.

## 실측 (run=2026-09-16, 4분할, 2026-09-16 완료)

READY 99,209 · NOT_FOUND 358 · UNPUBLISHED 429 · FAILED 0. 버전 행 21,567,150(unpublish 831,616),
원본 73.9 GB 전송 → jsonl.gz 988 MB → Parquet 453 MB. 샤드당 간격 0.5초(전체 초당 약 8건), **429 0건 · 5xx 0건 ·
연결 오류 0건**, 순 수집 **4시간 52분**(11:22~16:14). 직렬 1개로 받았던 09-09 회차의 17.9시간을 3.7배 줄였다.

09-09 회차와 대조해 **패키지 상태 분포가 한 건도 어긋나지 않았다**(READY·NOT_FOUND·UNPUBLISHED 모두 동일).
공통 행 21,433,794개에서 `published_at`·`rank` 불일치 0. 나머지 불일치는 전부 7일 사이의 실제 변화이거나
순서 차이로 설명된다 — 새로 unpublish 3,588행, 새로 폐기 5,831행(문구 변경 127), 의존 배열 순서만 다름 8,256행.
새로 생긴 버전 133,356행, 사라진 버전 1,792행.

## 실측 (run=2026-09-09, 2026-09-10 완료, 직렬)

READY 99,209 · NOT_FOUND 358 · UNPUBLISHED 429 · FAILED 0. 버전 행 21,435,586(unpublish 827,938), 원본 73.4 GB 전송 → jsonl.gz 765 MB → Parquet 403 MB. 간격 0.5초, 429 0건, 순 수집 약 18시간(최대 문서 115 MB, `rendition`).
deps.dev `requirements`(스냅샷 08-31)와 표본 2,000 대조 100% 일치, enzyme 개발용 의존 제거 전이 536건 / 474 패키지 검출. 상세는 계획 문서 §7.
수치는 2026-09-14 재변환 기준이다. 자체 리뷰 뒤 파싱·변환 규칙 세 가지가 바뀌어 이전 기록과 다르다 — 비버전 `time` 키에서 생긴 가짜 버전 1행 제거, `deprecated`의 불리언·빈 문자열 9,565행을 NULL로 정규화, 전이 계산을 이동쌍 빌더와 같은 라인 분할 규칙으로 교체(옛 규칙 1,999건).

### 6열이 더하는 용량 (실측)

2026-09-16 회차의 실제 행 60,000개에서 6열만 떼어 재면 한 줄당 **평균 +315 B**(중앙값 135 B, p95 1,265 B),
2,157만 행 환산 비압축 **+6.8 GB** 다. 압축 뒤 실적은 `jsonl.gz` 765 MB → **988 MB**(+29%),
Parquet 403 MB → **453 MB**(+12%). 수집 중에 예측했던 960 MB 와 3% 차이다.
착수 전 표본으로 잡았던 +241 B·5.2 GB 는 작게 나왔다(표본이 오래된 패키지에 치우쳤다).

## 샤드 배치 (2026-09-16 회차)

대상 10만(이름 중복 4건을 뺀 99,996)을 **순위 나머지**로 넷에 돌아가며 나눴다. `rank % 4` 가
1→s1 · 2→s2 · 3→s3 · 0→s4 다.

| 샤드 | 대상 | 순위 | 평균 순위 | 성공 | 미존재 | 전체삭제 | 버전 행 | 전송 | part |
|---|---|---|---|---|---|---|---|---|---|
| s1 | 24,999 | 1, 5, 9, … 99,997 | 49,997.7 | 24,812 | 88 | 99 | 5,389,667 | 18.4 GB | 1,078 |
| s2 | 24,999 | 2, 6, 10, … 99,998 | 49,998.7 | 24,802 | 84 | 113 | 5,377,745 | 18.2 GB | 1,076 |
| s3 | 24,999 | 3, 7, 11, … 99,999 | 49,999.7 | 24,806 | 90 | 103 | 5,415,555 | 18.3 GB | 1,084 |
| s4 | 24,999 | 4, 8, 12, … 100,000 | 50,000.7 | 24,789 | 96 | 114 | 5,384,183 | 19.0 GB | 1,077 |
| 합계 | 99,996 | | | 99,209 | 358 | 429 | 21,567,150 | 73.9 GB | 4,315 |

**샤드는 주제가 아니라 순위 나머지로 갈린다.** 특정 샤드에 "인기 패키지"나 "특정 생태계"가 몰려
있지 않다. 네 샤드의 평균 순위가 1씩만 차이 나고(49,997.7 ~ 50,000.7), 전송량도 18.2~19.0 GB 로
붙어 있다. 그래서 넷이 거의 같은 시각에 끝난다 — 앞에서부터 25,000개씩 끊었다면 상위권 샤드는
문서가 크고 하위권 샤드는 CDN 이 차가워(지연 중앙값 0.18초 대 0.60초) 한참 어긋났을 것이다.

어느 패키지가 어느 샤드에 있는지는 순위로 바로 나온다 — `semver`(1)→s1, `minimatch`(2)→s2,
`ansi-styles`(3)→s3, `debug`(4)→s4, `brace-expansion`(5)→s1, `chalk`(9)→s1 …
가장 큰 문서도 골고루 흩어졌다 — s1 `nocodb-daily`(105 MB), s2 `@tamagui/lucide-icons`(105 MB),
s3 `@octopusdeploy/design-system-components`(105 MB), s4 `rendition`(115 MB).

**읽을 때는 샤드를 신경 쓰지 않아도 된다.** `to_parquet.py` 가 네 샤드를 한 `registry_versions`
로 합치고, Bronze 도 `collected_date=2026-09-16` 하나 아래에 둔다. 샤드는 받는 방식이지
데이터의 성질이 아니다.

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

# ── 확장 목록 추가분 36.9만 (S15P21A506-452). 대상만 다르고 방식은 아래와 같다 ──
pipeline\collectors\registry\start_registry_additions.cmd   # 시작 (더블클릭)
pipeline\collectors\registry\status_watch_additions.cmd     # 현황 창 (더블클릭)

# ── 4분할 수집 (S15P21A506-366). 직렬 17.9시간 → 약 4.5시간 ──
# 대상을 4등분하고 collect.py 를 4개 띄운다. 수집기 자체는 직렬 그대로다(동시성을 넣지 않았다).
pipeline\collectors\registry\start_registry_sharded.cmd       # 시작 (더블클릭)
pipeline\collectors\registry\status_watch_sharded.cmd         # 현황 창 (더블클릭)

# 손으로 돌릴 때
.venv-bq/Scripts/python.exe pipeline/collectors/registry/shard_targets.py --targets datasets/targets/rank_top100k_20260902.csv --shards 4 --out data/registry/targets
.venv-bq/Scripts/python.exe pipeline/collectors/registry/collect.py --targets data/registry/targets/rank_top100k_20260902-s1of4.csv --run 2026-09-16-s1 --out data/registry/raw --interval 0.5   # s2·s3·s4 도 같은 식으로
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-16 --shards 4 --watch
.venv-bq/Scripts/python.exe pipeline/collectors/registry/to_parquet.py --raw data/registry/raw/run=2026-09-16-s1 data/registry/raw/run=2026-09-16-s2 data/registry/raw/run=2026-09-16-s3 data/registry/raw/run=2026-09-16-s4 --out data/registry/parquet --force

# failed 만 다시 시도
.venv-bq/Scripts/python.exe pipeline/collectors/registry/collect.py --targets datasets/targets/rank_top100k_20260902.csv --run 2026-09-09 --out data/registry/raw --retry-failed

# Parquet 변환 → DuckDB 뷰 registry_versions / registry_status (pipeline/duckdb/duckdb_ui.py)
.venv-bq/Scripts/python.exe pipeline/collectors/registry/to_parquet.py --raw data/registry/raw/run=2026-09-09 --out data/registry/parquet
.venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py -c "select count(*) from registry_versions"

# 원본 보존: 서버 MinIO pickage-raw Bronze 입고 (S15P21A506-340, 2026-09-16 완료 — 계획 §6)
# 터널(19000) 을 올린 뒤 PICKAGE_MINIO_ENV=.env.server 로 돌린다. 회차마다 run-id 를 붙인다
PICKAGE_MINIO_ENV=.env.server .venv-bq/Scripts/python.exe -m pipeline.minio.ingest_collector_raw --source registry --run 2026-09-16 --run-id registry-20260916-v1
# 먼저 --dry-run 으로 대상 파일 수·샤드 완결 판정을 본다. 샤드가 빠지면 여기서 거부한다
```

Windows에서 장시간 실행은 `start_registry.cmd`(별도 최소화 창)로 띄운다. **Claude Code 세션이 띄운 프로세스는 앱을 닫으면 함께 죽을 수 있으니**, 밤새 돌릴 때는 전진님 터미널이나 더블클릭으로 직접 띄운다. PC 절전 시 멈추고 깨어나면 이어간다.
같은 IP 에서 수집기를 예정보다 많이 돌리지 않는다(429 만 늘어남). downloads 주간 갱신과 겹치면 하나가 끝난 뒤 시작한다.
4분할 수집 중에 **429 가 보이면 `INTERVAL` 을 늘린다. `SHARDS` 를 줄이면 안 된다** — 대상 분배가 통째로 바뀌는데
run 이름은 그대로라, 이미 받아 둔 샤드와 대상이 겹쳐 같은 패키지를 두 번 받고 `to_parquet` 의 이름 중복 검사에 걸려
변환이 멈춘다. `SHARDS` 를 바꿔야 하면 `RUN` 도 새 이름으로 잡는다(받아 둔 것을 버리고 처음부터 받는다는 뜻이다).

샤드 하나가 죽으면 `start_registry_sharded.cmd` 를 다시 더블클릭한다. 살아 있는 샤드는 건드리지 않고 죽은 것만 채운다.

## 출력 형식

`raw/run=<run>/part-NNNNN.jsonl.gz` — 한 줄 = 패키지 1개 × 버전 1개. 열 이름·구조는 deps.dev `requirements`(`NPMRequirements`)와 같게 맞췄고 `DevDependencies` 만 새 열이다. 5,000줄마다 파일 회전.

```json
{"Name":"chalk","Version":"4.1.2","published_at":"2021-07-30T12:02:52.839Z","rank":9,
 "Dependencies":[{"Name":"ansi-styles","Requirement":"^4.1.0"},{"Name":"supports-color","Requirement":"^7.1.0"}],
 "DevDependencies":[{"Name":"xo","Requirement":"^0.28.2"},{"Name":"ava","Requirement":"^2.4.0"}],
 "PeerDependencies":[],"OptionalDependencies":[],
 "deprecated":null,"unpublished":false,
 "unpacked_size":35047,"file_count":7,"module_type":null,"main":"source","types":null,"exports":null,
 "fetched_at":"2026-09-09T12:00:00+00:00","modified":"2026-07-26T14:51:07.471Z"}
```

- `time[버전]` 이 발행 시각(UTC). `time` 의 키 중 **`^\d+\.\d+` 모양인 것만 버전으로 받는다**. `created`·`modified`·`unpublished` 말고도 모르는 키가 들어오고(실측: `appdirsjs` 의 `undefined`), 블랙리스트로 두면 그런 키가 전부 가짜 unpublish 버전 행이 되어 `first_published_at` 이 6년 반 틀어졌다. 버린 키 수는 manifest 의 `session_stats.odd_time_keys` 에 센다.
- `versions` 에 없고 `time` 에만 있는 버전 = unpublish 된 버전(예: chalk 5.6.1). **행은 남기고 의존 네 열은 NULL(모름), `unpublished=true`**. `[]`(의존 없음)로 쓰면 lag() 비교에서 "의존 전부 제거"로 잘못 잡힌다(09-10 §5-3 검증에서 641건 과대 계상이 실제로 났다). 09-09 run 의 raw 는 `[]` 로 수집됐고 `to_parquet.py` 가 NULL 로 바꿔 준다.
- `deprecated` 는 버전 단위 **폐기 문구**, 없으면 null. 폐기 데이터셋(S15P21A506-272)과 대조 가능. 문서에는 문구 대신 불리언이 오기도 해서 정규화한다 — `false` 와 `""`(npm deprecate 로 문구를 비운 경우)는 "폐기 아님"이라 **null**, `true` 는 "문구 없는 폐기"라 문자열 `"true"` 로 남긴다. 그래서 `deprecated IS NOT NULL` 이 그대로 "폐기된 버전"이다(정규화 전에는 9,565행이 잘못 포함됐다). 09-09 run 의 raw 도 `to_parquet.py` 가 같은 규칙으로 맞춘다.
- **형태 6열**(2026-09-16 추가). unpublish 된 버전은 선언을 모르므로 의존 네 열과 같이 **전부 NULL** 이다.
  존재율은 2026-09-16 회차 **전수**(살아 있는 행 20,735,534개) 기준이다. 착수 전 표본(패키지 20개·2,787 버전)도
  같이 적어 둔다 — 그 표본이 얼마나 못 믿을 것이었는지가 이 열들을 쓸 때 참고가 된다. `unpacked_size` 가 78.8% 대
  **97.4%** 로 19%p 벌어졌다. 표본이 `semver`(2011년부터 119 버전)·`ajv`(359 버전) 같은 오래된 대형 패키지에
  치우쳤고, 전수는 2024~2026년 발행분이 1,210만 행(58%)이라 최신 쪽이 압도한다.
  (수집 35% 시점에 "끝나면 두 값 사이로 내려온다"고 적었던 것은 **틀렸다.** 더 올라갔다.)

  | 열 | 원문 | 착수 전 표본 | **전수(최종)** | 읽을 때 주의 |
  |---|---|---|---|---|
  | `unpacked_size` | `versions[v].dist.unpackedSize` | 78.8% | **97.4%** | top level 이 아니라 **`dist` 안**이다. npm 이 2018년부터 계산해 **그 이전 발행 버전에는 아예 없다** — 결측은 "작다"가 아니라 "모른다"이고, 무작위가 아니라 연도로 갈린다 |
  | `file_count` | `versions[v].dist.fileCount` | 78.8% | **97.4%** | 위와 같이 붙어 다닌다 |
  | `module_type` | `versions[v].type` | 7.0% | **25.9%** | **없음 = `commonjs` 기본값**이다. NULL 을 "모름"으로 읽으면 안 된다 |
  | `main` | `versions[v].main` | 51.8% | **81.1%** | 원문 문자열 그대로. 최신 패키지는 `main` 없이 `exports` 만 쓰므로 **없다고 진입점이 없는 게 아니다** |
  | `types` | `versions[v].types`, 없으면 `typings` | 56.2% | **68.2%** | `types` 만 보면 과소 계상한다(실측: `ajv` 는 `typings` 만 있는 버전이 127개) |
  | `exports` | `versions[v].exports` | 29.2% | **39.5%** | 중첩 객체라 **JSON 문자열**로 적는다. 읽을 때 `json()`/`from_json` 으로 판다. **아주 클 수 있다** — 전수 기준 중앙값 179 B·평균 573 B·p95 1,296 B 인데 **최대 2.69 MB**(`@dnb/eufemia` 10.94.0, 다음이 `@iconify-icons/material-symbols` 2.35 MB)다. 이 열을 그대로 프런트로 내보내지 말 것 |
  `license` 는 여기 없다 — deps.dev 와 `(Name, Version)` 으로 조인한다.
  **2018년 절벽은 전수로 확인됐다.** 발행 연도별 `unpacked_size` 존재율 —
  2014년 0.0%(46,327행) · 2015년 0.0%(79,452) · 2016년 0.0%(136,079) · 2017년 0.0%(213,394) →
  **2018년 92.2%**(369,044) → 2019년 이후 **전부 100.0%**. 2017년 이하는 한 건도 없다.
  크기·파일 수를 시계열로 보려면 2018년 이전 구간이 통째로 비어 있다는 것을 전제해야 한다.
- **의존 배열의 순서는 회차마다 다를 수 있다.** 09-09 와 09-16 을 대조하니 공통 2,143만 행 중 8,256행에서
  `Dependencies` 가 달랐는데 **전부 순서만 다르고 집합은 같았다**(registry 가 응답의 키 순서를 보장하지 않는다).
  이동쌍 빌더와 아래 검증 쿼리는 `list_sort`·`list_contains` 로 집합 비교를 하므로 영향이 없지만,
  두 회차를 바이트로 비교하거나 배열을 그대로 `=` 로 견주면 가짜 차이가 나온다.
- `modified` 는 문서의 `time.modified`. 주간 갱신(S15P21A506-273)에서 이 값이 바뀐 패키지만 다시 받는 근거로 쓴다(이번 수집기에는 주간 모드가 없다).
- 축약 응답(`Accept: application/vnd.npm.install-v1+json`)은 devDependencies 가 빠지므로 쓰지 않는다.

`checkpoint.sqlite` 의 `tasks.status`: `pending` / `done` / `not_found`(404) / `unpublished`(패키지 전체가 unpublish 되어 `versions` 없음) / `failed`(`error` 에 사유: `too_large:>NB`, `parse:…`, `conn:…`, `http429:…`, 5xx 본문). `--retry-failed` 로만 다시 시도한다.

### Parquet (`data/registry/parquet/`)

- `registry_versions/part-00000.parquet` — 위 열 그대로. 형태 6열은 `unpacked_size`·`file_count` BIGINT, 나머지 넷 VARCHAR.
  시각은 UTC TIMESTAMP, 배열은 `STRUCT(Name, Requirement)[]`(unpublish 행은 NULL). Name 순 정렬, zstd. 임시 폴더에 쓴 뒤 교체하므로 변환이 도중에 죽어도 이전 결과가 남는다. `checkpoint.sqlite` 가 없으면 변환하지 않는다. 행은 체크포인트가 `done`·`unpublished` 인 패키지만 남긴다(쓰다 만 패키지의 고아 행 제거).
- `registry_source.json` — 이 출력 폴더를 어느 `--raw` 로 만들었는지(분할 수집이면 run 폴더들을 `;` 로 이어 적는다). 다른 run 으로 덮어쓰려 하면 변환기가 멈춘다. 스모크 run 으로 `--refresh-parquet` 를 돌려 본 결과를 날리는 사고를 막기 위한 것이고, 정말 바꿔 쓰려면 `--force` 를 준다.
- `registry_status.parquet` — 패키지 1행: `name, rank, status(READY / NOT_FOUND / UNPUBLISHED / FAILED / PENDING), n_versions, n_versions_unpublished, first_published_at, last_published_at, modified, fetched_at, http, doc_bytes, error`. 화면·통계에서 "자료 없음"을 0 과 구분하는 용도. 체크포인트가 정본이라 수집 중이면 PENDING 이 남는다.

## license 는 여기서 받지 않는다 — deps.dev 와 조인

`license` 도 registry 문서에 있지만(존재율 95.5%) 이미 deps.dev BigQuery `PackageVersions.Licenses` 로
가지고 있다(`data/raw/versions_full`, 열 이름 `Licenses`). 재수집 대상에서 뺀 이유는 셋이다 —
①이미 있다 ②거기 값은 SPDX 배열로 **정규화까지 끝나 있다**(registry 원문은 문자열 95.5% · 객체 2.0% ·
구형 `licenses` 배열 0.5% 가 섞여 있어 `deprecated` 처럼 손으로 맞춰야 한다) ③열이 하나 줄면 raw 도 그만큼 작다.

```sql
-- registry 버전 행에 라이선스를 붙인다. 2026-09-16 실측: 2,143만 행 중 2,039만(95.1%) 매칭 · 1,893만(88.3%) 에 값이 있다.
-- 안 붙는 4.9% 는 deps.dev 스냅샷(2026-08-31) 이후에 나온 버전이다. 스냅샷을 새로 받으면 줄어든다.
SELECT r.Name, r.Version, r.unpacked_size, r.module_type, v.Licenses
FROM registry_versions r
LEFT JOIN versions_full v ON v.Name = r.Name AND v.Version = r.Version;
```

## 진행 확인

```bash
# 4분할 수집 현황 창 (더블클릭). 합계 진행률·완료 예상 시각 + 샤드별 상태
pipeline\collectors\registry\status_watch_sharded.cmd
# 4분할을 한 화면 요약. --shards 를 주면 <run>-s1 … <run>-sN 으로 펼쳐 합산한다
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-16 --shards 4 --watch

# 직렬 run 하나만 볼 때 (예: 09-09)
pipeline\collectors\registry\status_watch.cmd
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-09 --watch
# 요약 + Parquet 갱신 → DuckDB UI 의 registry_versions 뷰에 지금까지 받은 패키지가 전부 보임
# --watch 와 같이 쓰면 --refresh-min-interval(기본 3600초)마다, 그리고 수집이 끝날 때 한 번 더 돈다
# 스모크 run 을 볼 때는 --parquet-out 도 같이 바꾼다. 안 바꾸면 변환기가 본 결과를 덮어쓰지 않으려고 멈춘다
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-09 --refresh-parquet
# 분할 수집은 run 이름이 바뀌어 같은 출력 폴더의 출처 검사에 막힌다.
# 수집 중에 보고 싶으면 --parquet-force 가 아니라 --parquet-out 으로 폴더를 따로 준다.
# 같은 폴더에 --force 로 덮으면 완성된 09-09 결과(403 MB)가 지워지고 절반짜리로 바뀐다 —
# raw 가 남아 있어 다시 만들 수는 있지만 변환에 30분 걸리고, 그동안 팀의 registry_versions 뷰가 절반만 보인다.
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-16 --shards 4 --refresh-parquet --parquet-out data/registry/parquet_2026-09-16
# 수집이 끝나고 검증까지 마친 뒤, 본 폴더를 이번 회차로 갈아탈 때만 --parquet-force
.venv-bq/Scripts/python.exe pipeline/collectors/registry/status.py --run 2026-09-16 --shards 4 --refresh-parquet --parquet-force

# 원시 로그 (분할 수집은 샤드마다 따로 쌓인다)
tail -3 data/registry/raw/registry_2026-09-16-s1.log
tail -3 data/registry/raw/registry_2026-09-09.log
python -c "import sqlite3;print(sqlite3.connect('data/registry/raw/run=2026-09-09/checkpoint.sqlite').execute('select status,count(*) from tasks group by status').fetchall())"
```

## 검증 (계획 §5)

**연속 버전 전이는 이동쌍 빌더와 같은 규칙으로 센다.** 패키지를 한 줄로 세워 시각 순 인접쌍을 비교하면, 유지보수 릴리스(5.0.0 뒤에 나온 4.17.3)가 서로 다른 라인의 버전과 짝지어져 가짜 전이가 생긴다. 실측으로 정렬 방식에 따라 enzyme 제거 전이 수가 981~2,345건까지 흔들렸다. `pipeline/duckdb/build_migration_pairs.py` 는 이미 `PARTITION BY Name, line ORDER BY published_at` 으로 라인을 나누고 릴리스만 보므로, 검증도 그 규칙을 그대로 쓴다. 그래야 -136 빌더에 개발용 의존(`kind: dev`)을 넣었을 때 실제로 나올 값과 같아진다.

```sql
-- enzyme 을 개발용 의존에서 뺀 연속 릴리스 전이 수 (09-09 run: 536건 / 474 패키지)
-- unpublish 행은 의존을 모르므로(NULL) 뺀다. 라인 정의·릴리스 조건은 build_migration_pairs.py 와 같다.
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

-- 정렬에 무관한 보조 지표: enzyme 을 쓴 적 있고 최신 버전에는 없는 패키지 수 (09-09 run: 827개)
-- '최신'을 시각 기준으로 잡든 semver 기준으로 잡든 1,419개 중 20개만 달라진다. 전이 수보다 훨씬 안정적이다.
WITH d AS (SELECT Name, Version, published_at, list_transform(DevDependencies, x -> x.Name) AS dev
           FROM registry_versions WHERE NOT unpublished),
last AS (SELECT Name, argmax(dev, (published_at, Version)) AS dev FROM d GROUP BY Name)
SELECT count(*) FROM last
WHERE NOT list_contains(dev, 'enzyme')
  AND Name IN (SELECT Name FROM d WHERE list_contains(dev, 'enzyme'));

-- 실행용 의존은 deps.dev 와 같아야 한다 (표본 대조). registry 쪽을 먼저 표본 추출한 뒤 조인한다 —
-- 조인 뒤에 USING SAMPLE 을 붙이면 2,144만 × 7,856만 행 전체 조인이 먼저 실행돼 메모리 19 GB 를 넘긴다(09-10 실측).
-- requirements 는 snapshot 파티션이 쌓이므로 스냅샷을 하나로 고정한다.
SELECT r.Name, r.Version, r.Dependencies AS registry, q.Dependencies AS depsdev
FROM (SELECT * FROM registry_versions WHERE NOT unpublished USING SAMPLE 100) r
JOIN requirements q ON q.Name = r.Name AND q.Version = r.Version AND q.snapshot = DATE '2026-08-31';
```
