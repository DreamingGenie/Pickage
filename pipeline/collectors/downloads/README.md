# npm downloads 수집기

계획: `docs/api & data/수집계획_downloads_npmAPI_260902.md` (§3 파이프라인 구현). 데이터는 `/data/`(gitignore)에 쌓인다.

## 파일

| 파일 | 역할 |
|---|---|
| `collect.py` | npm downloads API 호출. 초당 1건 토큰버킷, 429 지수 백오프(연속 5회면 5분 휴식), SQLite 체크포인트, 응답 start/end 검증, 원본 jsonl.gz + manifest.json |
| `to_parquet.py` | raw → `downloads/date=…/` Parquet(hive) + `downloads_status.parquet`. §4-1 결손 규칙(0 → NULL + `imputed_gap`) 적용. 수집 중에도 실행 가능(쓰고 있는 part·0바이트 part는 건너뛰고, 잘린 part는 복구). Spark 적재 전까지의 로컬 대체 |
| `status.py` | 진행 상태 한 화면(실행 여부·진행률·속도·429·ETA). `--watch`로 60초 갱신, `--refresh-parquet`로 DuckDB UI 뷰까지 최신화(재변환은 `--refresh-min-interval` 기본 1시간에 한 번). 체크포인트가 없으면 안내만 내고 멈춘다 |
| `start_backfill.cmd` | 백필 재시작(더블클릭). 이미 돌고 있으면 새로 띄우지 않음 |
| `status_watch.cmd` | 현황 창(더블클릭). 60초 갱신, 닫아도 수집기 영향 없음 |

## 대상 목록

ecosyste.ms 다운로드 순위 상위 10만 (`datasets/targets/rank_top100k_20260902.csv`, 컬럼 `rank,name,downloads_last_month,dependent_packages_count,status`).
09-02에 목록 API(`sort=downloads&order=desc`, 1,000개/페이지) 100페이지를 받아 만들었고, 그때 쓴 일회성 스크립트는 남아 있지 않다.
재생성이 필요하면 같은 API를 호출하는 `pipeline/collectors/keywords/collect_keywords.py` 의 raw(`data/keywords/raw/run=*/part-00001~00100`)에서 같은 다섯 열을 뽑으면 된다. 순위는 수집 시점에 따라 달라진다.
실행 시 `collect.py` 는 User-Agent 연락처를 환경변수 `OSS_SHIFT_UA_CONTACT`(이메일 또는 URL)로 받는다. 비어 있으면 시작하지 않는다.

## 실행

```bash
# 백필 (18개월: 벌크 2구간 + 스코프 1구간). 중단 후 같은 명령으로 재시작하면 체크포인트부터 이어감.
# 구간 끝(--end)은 첫 실행 때 run.json에 고정되어 재시작 시 자동으로 같은 값을 쓴다(다른 값을 주면 거부).
.venv-bq/Scripts/python.exe pipeline/collectors/downloads/collect.py --targets data/downloads/targets_top100k_20260902.csv --run 2026-09-02 --end 2026-08-31 --mode backfill --out data/downloads/raw

# 가장 쉬운 재시작: 탐색기에서 더블클릭 (이미 돌고 있으면 새로 띄우지 않음)
pipeline\collectors\downloads\start_backfill.cmd

# 주간 갱신 (직전 14일). 화 10:00 KST 이후 실행. --run 은 실행일
.venv-bq/Scripts/python.exe pipeline/collectors/downloads/collect.py --targets data/downloads/targets_top100k_YYYYMMDD.csv --run 2026-09-09 --mode weekly --out data/downloads/raw

# Parquet 변환
.venv-bq/Scripts/python.exe pipeline/collectors/downloads/to_parquet.py --raw data/downloads/raw/run=2026-09-02 --out data/downloads/parquet

# GCS 업로드 (계획 §3 경로)
gcloud storage rsync -r data/downloads/raw/run=2026-09-02 gs://oss-shift-a506-raw/raw/downloads/run=2026-09-02
```

Windows에서 장시간 실행은 `start_backfill.cmd`(별도 최소화 창)로 띄운다. **Claude Code 세션이 띄운 프로세스는 앱을 닫으면 함께 죽을 수 있으니**, 밤새 돌릴 때는 전진님 터미널이나 더블클릭으로 직접 띄운다. PC 절전 시 멈추고 깨어나면 이어간다.

## 중단과 재시작

같은 명령(또는 `start_backfill.cmd`)으로 다시 띄우면 `checkpoint.sqlite` 의 `pending`·`retry` 작업부터 이어간다.
이미 `done`·`not_found`·`failed` 인 작업은 다시 호출하지 않는다.

**강제 종료돼도 체크포인트와 원본이 어긋나지 않는다.** 체크포인트를 commit 하기 전에 원본(jsonl.gz)을 먼저
flush 하고, 종료 시에도 `Writer.close()` → `db.commit()` 순서를 지킨다. 그래서 "체크포인트는 `done` 인데
raw 에는 행이 없는" 작업이 생기지 않는다 — 그런 작업은 재시작해도 다시 받지 않으므로 그대로 데이터 유실이 된다.
(2026-09-18 이전 판은 commit 이 먼저여서 gzip 버퍼에 남아 있던 행이 유실될 수 있었다. S15P21A506-331)

강제 종료된 시점의 마지막 part 는 gzip 트레일러가 없어 그대로는 읽히지 않는다. 변환기가 세 경우를 나눠 처리한다.

- **마지막 part** 는 수집기가 쓰고 있을 수 있으므로 건너뛴다. 수집 중에도 변환을 돌릴 수 있는 이유다.
- **그 앞의 잘린 part** 는 JSON 으로 읽히는 줄까지 살려 다시 쓰고, 원본을 `.broken` 으로 남긴다.
- **0바이트 part**(part 회전 직후 종료) 는 건너뛴다. 이 경우를 거르지 않으면 변환이 `Input is not a GZIP stream` 으로 죽는다.

## 출력 형식

`raw/run=<run>/part-NNNNN.jsonl.gz` — 한 줄 = 패키지 1개 × 구간 1개 (벌크 응답도 패키지 단위로 풀어서 저장)

```json
{"name":"chalk","rank":9,"kind":"bulk","start":"2025-09-01","end":"2026-08-31","tier":"A",
 "fetched_at":"2026-09-02T03:49:19+00:00","task_id":"bulk-000009-2025-09-01","status":"ok",
 "downloads":[{"downloads":123,"day":"2025-09-01"}, ...]}
```

`status`: `ok` / `not_found`(벌크 null 또는 단일 404). `checkpoint.sqlite`의 `tasks.status`: pending / done / not_found / failed(`error`에 사유, `window_mismatch`는 조용한 절단 감지).

## 진행 확인

```bash
# 현황 창 (더블클릭)
pipeline\collectors\downloads\status_watch.cmd
# 한 화면 요약. --watch 를 붙이면 60초마다 갱신
.venv-bq/Scripts/python.exe pipeline/collectors/downloads/status.py --run 2026-09-02 --watch
# 요약 + Parquet 갱신 → DuckDB UI(pipeline/duckdb/duckdb_ui.py)의 downloads 뷰에 지금까지 받은 패키지가 전부 보임
.venv-bq/Scripts/python.exe pipeline/collectors/downloads/status.py --run 2026-09-02 --refresh-parquet

# 원시 로그
tail -3 data/downloads/raw/backfill_2026-09-02.log
python -c "import sqlite3;print(sqlite3.connect('data/downloads/raw/run=2026-09-02/checkpoint.sqlite').execute('select status,count(*) from tasks group by status').fetchall())"
```
