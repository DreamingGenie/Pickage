# 04. 운영 실행 기록 — 합본 Bronze 게시와 105일 UPDATE (2026-09-22 ~ 09-23)

[설계](01-design.md) · [명령서](02-runbook.md) 대로 돌리되 실제로는 아래 여섯 군데가 달랐다. 다음 회차는 이 문서를 먼저 읽는다.
컨트롤 타워 세션이 실행을 지휘했고 운영 명령은 전부 전진님 터미널에서 쳤다.

## 1. 결과

| 항목 | 값 |
|---|---|
| Bronze run | `npm-downloads-468k-20260922-v1` (manifest `e4f80714…`, 09-22 21:46 PUBLISHED) |
| 재적재 run | `downloads-468k-20260922-v2` — **105일 전부 PUBLISHED** (09-22 23:4x ~ 09-23 17:34) |
| 갱신 행 | 09-23 실행 54일 15,235,466 (+ 09-22 51일) · 08-31 채움 97,728 → 459,758 |
| 표 크기 | heap 26.46 → 27.20 GB, index 15.37 → 16.64 GB (VACUUM 생략분 포함) |
| 날짜당 소요 | 5.9 ~ 7.4 분 (원 추정 1~3 분) |

## 2. 명령서와 달랐던 것

### 2-1. 합본 Bronze 는 "하드링크 + 합성 메타" 로 만들었다 → `tools/merge_downloads_runs.py`

`pipeline.downloads.load` 는 source-root 하나에 `<target>.csv` · `raw/run=<run>/{run.json,manifest.json,part-\d+.jsonl.gz}` · `parquet/` 만 있어야 하고 part 이름 정규식이 고정이다.
두 run(09-02 10만 38 part, 09-22-additions 147 part)의 part 를 **하드링크로 연번을 새로 매겨** 한 run 폴더에 넣고, `run.json`·`manifest.json` 은 수집기 산출이 아니라 **합성**했다(final=true, 두 run 의 작업 수 합산, merged_from 기록). 입고기는 두 파일의 존재와 JSON 형식만 본다. 데이터셋 폴더에 검증기가 모르는 파일이 있으면 거부하므로 합본 manifest 같은 부산물을 그 안에 두지 않는다.

### 2-2. `to_parquet.py` 는 3.3억 행에서 못 쓴다 → `tools/to_parquet_lowmem.py`

저장소 `pipeline/collectors/downloads/to_parquet.py` 는 펼친 표(d0)와 결손 처리 표(d)를 함께 들고 마지막에 `to_arrow_table()` 로 전부 Arrow 에 올린다. 10만(7천만 행)에서는 되지만 46.9만(329,632,221 행)에서는 커밋 55 GB 로 페이지파일에 밀려 22 분간 출력 0 이었다.
대체 스크립트는 규칙(0 이고 전후 7일 중앙값 ≥ 1000 이면 NULL+gap)과 출력 형식을 그대로 두고, `memory_limit`·`temp_directory` 를 주고 DuckDB `COPY … PARTITION_BY(date)` 로 직접 쓴다. 27 분, 메모리 16 GB. **주간 갱신이 46.9만으로 넘어가면 저장소 스크립트를 이 방식으로 바꿔야 한다.**

### 2-3. 입고기 검증은 4 GB 고정으로 죽었다 → MR !260

`pipeline/downloads/input.py` 의 DuckDB 가 `memory_limit=4GB` 고정이라 품질 검사 조인이 OOM. 환경 변수 `PICKAGE_DOWNLOADS_DUCKDB_{MEMORY,THREADS,TEMP}` 로 올릴 수 있게 했다(기본 불변). 게시는 `24GB/6/디스크` 로 53 분(검사) + 전송.
같은 검사를 게시가 다시 하므로 **`--verify-only` 를 따로 돌리지 않는다** — 검사 실패는 업로드 전에 멈춘다.

### 2-4. 날짜당 14~23 분의 정체는 플래너였다 → MR !265 + `tools/psql_noseq.cmd`

운영 `package_snapshot` 은 BRIN(snapshot_at) 하나다. 날짜 하나를 고르는 비용 추정이 BRIN 비트맵과 순차 스캔 사이에서 거의 같아, 날짜에 따라 24 GB 전체 스캔으로 기운다(EXPLAIN: 08-31 BRIN 16 s / 08-24 순차 196 s / 2025-03-03 BRIN 4.5 s). 날짜당 다섯 번 훑으므로 그런 날짜는 23 분.
로더 세션에 `SET enable_seqscan=off` 를 걸었다(08-24: 1,370 s → 355 s). 스테이징 전 3 분 공백은 `run()` 의 일회성 count 호출이라 로더 세션 SET 이 닿지 않는데, 그 수정을 넣으면 계약 해시가 바뀌어 이미 게시된 날짜와 충돌한다(`published input has a different load contract`). 그래서 운영에서는 **`--psql tools/psql_noseq.cmd`** (docker exec 에 `PGOPTIONS=-c enable_seqscan=off`) 로 모든 psql 세션에 같은 설정을 줬다. 코드 수정분은 다음 회차(새 Bronze)부터 유효하다.
근본 해결은 `(snapshot_at, package_id)` B-tree 인덱스(약 15~20 GB)다. 별도 판단.

### 2-5. VACUUM 은 컨테이너 공유 메모리에서 죽는다 → `--no-vacuum`

첫 날짜 COMMIT 뒤 `VACUUM public.package_snapshot` 이 `could not resize shared memory segment … No space left on device` 로 실패했다. Docker 기본 `/dev/shm` 64 MB 에서 병렬 VACUUM 이 67 MB DSM 을 요구한다. COMMIT 은 끝난 뒤라 그 날짜는 PUBLISHED 다. 이후 `--no-vacuum` 으로 돌렸고 죽은 행 약 2 GB 가 남았다.
**후속**: `VACUUM (PARALLEL 0) public.package_snapshot` 1 회(DSM 불필요), compose `shm_size` 상향 검토.

### 2-6. SSH 가 끊기면 서버는 3 시간 뒤에야 안다 → ssh keepalive

09-23 05:39 PUBLISH 도중 `client_loop: send disconnect: Connection reset`. 로더는 죽은 연결을 3 시간 기다린 뒤 실패했고, 서버 트랜잭션은 COMMIT 전이라 롤백됐다(채움 수 옛 값 그대로 확인). `--skip-published` 로 재개해 나머지 54일을 끝냈다.
`~/.ssh/config` 에 `ServerAliveInterval 30` / `ServerAliveCountMax 3` 을 두면 90 초 안에 감지한다. 재개 전에 **활동 프로브로 옛 세션이 남아 있는지 확인**한다 — 서버가 INSERT 에 몰두해 있으면 끊긴 걸 모르고 새 세션이 advisory lock 에서 기다린다. 그때는 `pg_terminate_backend(<옛 pid>)`.

## 3. 프로브 (`tools/prod_probe_*.sql`)

따옴표가 PowerShell → ssh → docker 를 거치며 벗겨지므로 SQL 은 파일로 두고 `Get-Content … -Raw | ssh a506app "docker exec -i <컨테이너> psql … -X -At"` 로 흘린다.

| 파일 | 무엇 |
|---|---|
| `prod_probe_activity.sql` | 활성 세션·대기 종류·트랜잭션 나이 — 잠금 대기인지 일하는 중인지 |
| `prod_probe_size.sql` | 표·인덱스 크기 — 커밋 전 INSERT 진척을 크기 증가로 어림 |
| `prod_probe_brin.sql` | snapshot_at 상관·인덱스·날짜별 EXPLAIN — 플래너 판단 확인 |

## 4. 시간표

| 시각 | 일 |
|---|---|
| 09-22 16:44 | downloads 추가분 수집 종료(13,840 작업, 실패 0) |
| 17:08 ~ 17:35 | 합본 parquet(lowmem) |
| 17:39 / 17:41 | 검증기 OOM → 수정 후 재검증(중단, 게시가 대신) |
| 19:46 / 20:44 | 게시 1차(.env.server 위치 실수) / 2차 → 21:46 PUBLISHED |
| 22:29 | verify-only 2일 통과, 826 s·1,370 s → 플래너 조사 |
| 23:2x ~ 23:4x | seqscan 수정·v2 계약 고정·래퍼 |
| 09-23 00:2x ~ 05:39 | 51일 게시 (VACUUM 실패 1회, --no-vacuum) |
| 05:39 ~ 08:41 | SSH 리셋 → 3 h 대기 후 실패 |
| 08:53 ~ 17:34 | 54일 재개 게시 → 105/105 |

## 5. 남은 것

- `VACUUM (PARALLEL 0) public.package_snapshot` (한산한 시간, 수 분~수십 분)
- 리허설 DB `pickage_453_rehearsal` DROP
- 후속 판단: `to_parquet.py` 저메모리화, B-tree 인덱스, compose `shm_size`
