# 파이프라인 모니터 — "데이터가 잘 흐르고 있는가"

netdata 는 CPU·메모리·디스크·컨테이너 **자원**을 본다 (`deploy/prod/monitoring/README.md`).
이것은 그 다음 질문에 **물을 때 그 자리에서** 답한다.

| 알고 싶은 것 | 어디서 읽나 | 보고서의 절 |
| --- | --- | --- |
| 주간 회차가 어디까지 갔나, 어느 단계에서 멈췄나, BLOCKED 인가 | `pickage-raw/_ops/weekly/<week>/run.json` · `manual-request.json` | `weekly` |
| raw → Curated 전처리가 어느 회차·어느 단계까지 갔나, 실패했으면 언제 재시도하나 (S15P21A506-372) | `pickage-curated/_ops/preprocessing/<날짜>/status.json` · `_dispatcher/status.json` · `curated-bundle/_current.json` · 실행기 `status.json` | `curated` |
| **방금 무엇이 올라왔나**, 어느 실행이 방금 끝났나 | 버킷 **이벤트 구독** (MinIO `ListenBucketNotification`) — 목록 조회 없음 | `minio.events` |
| 모니터가 켜지기 전엔 무엇이 있었나, 경로별 개수·크기 | 버킷 전체 LIST — **사람이 버튼을 누를 때만** | `/api/inventory` |
| 소비자가 지금 어느 실행을 읽나 | `_current.json` 포인터 | `minio.pointers` |
| 로컬 디스크에 무엇이 쌓였나, 단계별 로그는 어떤가 | data: `/srv/pickage/ingest-work` · `logs/<step>.log` — app: RAG 문헌 캐시 `/srv/pickage/docs` (샤드별 개수·크기, 최근/가장 오래된 파일) | `local` |
| 파이프라인 컨테이너의 상태·종료 코드·로그 꼬리 | Docker API (소켓, GET 만) | `docker` |

**HTTP 서버 하나가 노드마다 뜬다.** 요청이 오면 그때 계산해서 JSON 으로 답한다 — 미리 파일로
써 두지 않는다. 사람이 보는 것은 "지금" 이기 때문이다.

```
사람 ──터널──▶ app 노드 :19998  ── /                          화면 (web/index.html)
                                ── /api/nodes                 [app, data]
                                ── /api/report?node=app       이 노드에서 계산
                                ── /api/report?node=data      data 노드 :19998 에 사설망으로 물어 그대로 넘긴다
                                ── /api/inventory?node=data   마지막 전체 목록. &fresh=1 이면 지금 긁는다 (버튼)
```

컨테이너는 `deploy/prod/monitoring/<노드>/compose.yaml` 의 `pipeline-monitor`. 화면은
터널을 열고 `http://127.0.0.1:19998/` — `scripts/open-monitoring.*` 이 netdata(19999) 와 같이 연다.

## MinIO 는 두 층이다

S3 목록 조회는 앞부분(prefix)으로만 거를 수 있다. "최근 것만", "`_SUCCESS` 만" 은 서버가
받아 주지 않아서 버킷을 통째로 나열해야 하고, 객체 1,000개당 요청 하나다. 그래서 자동으로는
**절대 나열하지 않는다.**

| 층 | 언제 | 비용 | 무엇을 |
| --- | --- | --- | --- |
| **이벤트 구독** (`events.py`) | 서버가 켜져 있는 동안 상시. 15초 갱신·지금 확인 버튼이 읽는다 | 버킷당 연결 하나, 유휴 0 | 켜진 뒤 생긴 객체를 24시간 메모리에. 방금 올라온 것, `_SUCCESS` 완료 알림, 경로별 신규 |
| **전체 목록** (`s3inv.py`) | 화면의 **전체 목록 조회** 버튼 → `/api/inventory?fresh=1` | 객체 1,000개당 요청 하나 | 경로별 개수·크기·24시간/7일 신규, `_SUCCESS` 기준 완료된 실행 전부. 결과는 다음에 누를 때까지 메모리에 남는다 |

이벤트는 **구독한 뒤의 것만** 온다(재전송 없음). 서버가 켜지기 전이나 연결이 끊긴 사이는
모른다 — 끊긴 구간(gap)을 기록해 화면이 그렇게 말한다. 그 전 상태가 필요하면 버튼이다.

## 파일

| | |
| --- | --- |
| `run.py` | 실행기. `Builder` 가 절마다 try/except 로 보고서를 만든다 — 한 절이 죽어도 나머지는 만들고 `errors` 에 남긴다. 전체 목록의 마지막 결과도 든다 |
| `server.py` | HTTP. 라우팅, 보고서 캐시(연타·탭 여러 개를 한 번 계산으로), 다른 노드 중계 |
| `events.py` | 버킷 이벤트 구독. 버킷당 스레드 하나, 끊기면 5→60초 backoff 로 재연결, 24시간 고리 버퍼, 경로별 집계 |
| `s3inv.py` | 버킷 LIST → 경로 집계, `_SUCCESS` → 완료된 실행, `_current.json` 읽기 |
| `config.py` | 노드별 YAML + 자격증명 환경변수(`PICKAGE_S3_*`). 모르는 키는 시작 거부 |
| `weekly.py` | `_ops/weekly` 요약. 우편함 판정은 `pipeline.weekly.schedule.is_manual_pending` 을 그대로 부른다 |
| `curated.py` | `_ops/preprocessing` 요약 — 디스패처 상태(RUNNING·COMPLETE·FAILED·BLOCKED·WAITING_INPUT, 재시도 시각)와 실행기의 6단계 상태. 판정은 디스패처가 적은 것 그대로. 그 모듈을 import 하지 않아 372 브랜치가 없는 체크아웃에서도 뜬다 |
| `localfs.py` | 경로 스캔(크기·파일 수·24시간 신규)과 로그 꼬리 |
| `dockerapi.py` | Docker Engine API 최소 클라이언트. 로그 프레임 demux 포함 |
| `web/index.html` | 화면. 서버가 `/` 로 서빙한다 |
| `fake_pipeline.py` | 리허설용 가짜 회차. 운영에서 쓰지 않는다 (`deploy/prod/monitoring/app/rehearsal.fake-pipeline.yaml`) |
| `Dockerfile` | 런타임만(python + boto3 + minio SDK). 코드는 compose 가 `pipeline/` 을 마운트한다 |

## API

| 경로 | 답 |
| --- | --- |
| `GET /` | 화면 |
| `GET /api/nodes` | `{"self": "app", "nodes": ["app", "data"], "peers": {...}}` |
| `GET /api/report` | 이 노드의 보고서. `?fresh=1` 은 보고서 캐시(3초) 무시 |
| `GET /api/report?node=data` | `peers.data` 에 `/api/report` 를 물어 그대로 넘긴다. 붙지 못하면 **502 + JSON**(`unreachable: true`, 이유) — 화면이 그 노드 자리에 이유를 띄운다. 피어가 500·404 로 **답한** 경우는 그 코드와 본문을 그대로 넘긴다 (`unreachable` 없음) — 방화벽이 아니라 그 노드의 로그를 볼 일이다 |
| `GET /api/inventory` | 마지막 전체 목록. 없으면 `{"available": false}`. **`?fresh=1` 일 때만 긁는다** (동시 요청은 한 번만 긁고 같은 결과) |
| `GET /api/inventory?node=data` | 위를 중계. fresh 는 타임아웃이 길다 (`inventory_timeout_seconds`, 기본 600초) |
| `GET /healthz` | `ok` |

## 실행

서버에서는 compose 가 띄운다. 손으로 한 번 만들어 보려면:

```bash
cd ~/S15P21A506/deploy/prod/monitoring/data          # app 노드는 .../app
docker compose run --rm pipeline-monitor --once | less
```

| 인자 | |
| --- | --- |
| `--once` | 서버 없이 한 번 만들어 stdout 에 찍고 끝낸다 (구독은 걸지 않는다) |
| `--no-s3` | MinIO 를 아예 안 붙는다 (로컬 디스크·docker 절만) |
| `--listen 주소:포트` | 설정의 `listen` 을 덮어쓴다 (여러 번). 리허설용 |
| `--peer 이름=URL` | 설정의 `peers` 에 더한다. 리허설용 |
| `--config` | 기본 `$MONITOR_CONFIG` → `/etc/pipeline-monitor.yaml` |

## 설정 — `pipeline-monitor.yaml`

키와 기본값은 `config.py` 의 dataclass 가 정본이다. 노드별 실제 값은
`deploy/prod/monitoring/{data,app}/pipeline-monitor.yaml` 에 주석과 함께 있다.

| 절 | 무엇을 정하나 |
| --- | --- |
| `listen` | 듣는 주소들. **0.0.0.0 을 쓰지 않는다** — 주소마다 서버를 하나씩 띄운다. app 은 127.0.0.1 뿐, data 는 사설 IP 도 |
| `peers` | 중계할 다른 노드 `{이름: URL}`. app 에만 있다 |
| `cache_seconds` | 보고서 캐시(3초). 탭 둘이 동시에 물어도 한 번 계산 |
| `inventory_timeout_seconds` | 전체 목록 중계의 타임아웃 (600초) |
| `minio.events` · `events_retention_hours` · `events_max` | 이벤트 구독. **한 노드에서만 켠다** (data) |
| `minio.inventory` | 전체 목록 조회 버튼을 받는가. data 만 |
| `minio.buckets` | 비우면 계정이 보는 전부. 구독과 목록에 같이 쓴다 |
| `minio.depth` · `depth_overrides` | 경로 집계 깊이. raw·curated 는 4 (스냅샷·수집일까지). 이벤트 집계도 같은 규칙 |
| `minio.max_objects` | 전체 목록이 넘기면 멈추고 `truncated` 를 켠다 — 화면이 "잘렸다" 고 말한다 |
| `minio.pointers` | 읽을 `_current.json` 들 (`bucket/key`) |
| `minio.curated` · `curated_bucket` · `curated_max_runs` | Curated 전처리 회차 절. data 만. 회차당 GET 2 (디스패처 상태 + 실행기 상태) |
| `local.paths` · `log_globs` | 훑을 호스트 경로(컨테이너 안 경로 + 사람용 라벨)와 로그 패턴. 경로마다 `refresh_seconds`(0 = 보고서마다. 파일이 수십만 개인 캐시는 600 처럼 주기를 준다 — 그 사이는 마지막 결과를 `cached: true` 로 낸다. "지금 확인" 은 바로 훑는다)와 `note`(화면 머리 한 줄) |
| `docker.name_pattern` | 어느 컨테이너를 보나. 멈춘 것도 포함한다 — 종료 코드가 정보다. 모니터링 스택 자신은 뺀다 |
| `docker.error_pattern` | 로그 꼬리에서 "에러 줄" 로 셀 정규식. 로컬 로그에도 같은 것을 쓴다 |

## 보고서 형식 (`schema: 3`)

```jsonc
{
  "schema": 3, "node": "data", "hostname": "j15a506a-data",
  "generated_at": "2026-09-21T03:00:00+00:00", "took_seconds": 0.2,
  "cached": true,                       // 보고서 캐시에서 왔을 때만
  "errors": [ {"section": "docker", "message": "PermissionError: …"} ],   // 비어 있어야 정상
  "timings": {"minio": 0.01, "weekly": 0.1, "local": 0.05, "docker": 0.1},
  "weekly": {"listed_at": …, "weeks_total": 3,
      // 이번 주 회차가 "아예 시작 안 한" 것을 잡는다 — 창(화요일 10:00 KST)이 열렸는데 그 주 객체가 하나도 없으면 missing.
      // 판정 규칙은 pipeline.weekly.schedule 의 current_week_of · window_open 을 그대로 쓴다.
      "expected": {"week_of": "2026-09-21", "window_open_at": "2026-09-22T01:00:00+00:00", "window_open": true, "present": true, "missing": false},
      "stale_running_hours": 26,    // schedule.STALE_RUNNING — 화면이 이 값으로 오래된 RUNNING 을 올린다
      "runs": [
      {"week_of": "2026-09-21", "status": "RUNNING", "consecutive_failures": 0,
       "coverage": {"downloads_through": "2026-09-20", …}, "last_error": null,
       "manual": {"requested_at": null, "claimed_at": null, "pending": false},
       "steps": [{"step": "depsdev_t2", "status": "SUCCEEDED", "attempt_count": 1, …}, …]} ]},
  "curated": {"listed_at": …, "bucket": "pickage-curated", "snapshots_total": 3,
      "current": {"snapshot": "2026-09-14", "run_prefix": "depsdev/v1/curated-bundle/snapshot=…/run_id=…"},   // 완료된 최신 bundle. 없으면 null
      "dispatcher": {"status": "TICK_FINISHED", "exit_code": 0, "error": null, "updated_at": …},              // TICK_FINISHED 가 아니면 회차를 고르기 전에 멈춘 것
      "runs": [{"snapshot": "2026-09-21", "run_id": "curated-weekly-20260921", "status": "FAILED", "attempt": 2,
                "consecutive_failures": 2, "started_at": …, "finished_at": …, "next_retry_at": …, "updated_at": …,
                "error": {"type": "RuntimeError", "message": "…"}, "is_current": false, "phase": "downloads",
                "stages": [{"stage": "snapshot", "status": "COMPLETE", "attempt": 1, "action": "REVERIFIED", …},
                           {"stage": "downloads", "status": "FAILED", "attempt": 2, "error": {…}}]}]},
  "minio": {
      "pointers": [{"bucket": "pickage-curated", "key": "…/_current.json", "modified": …, "value": {…}}],
      "events": {"listening_since": …, "retention_hours": 24, "held": 312, "max_events": 20000,
                 "discovery": {"pending": false, "error": null, "attempts": 1},   // pending 이면 버킷 목록을 아직 못 받아 구독이 하나도 없다 (MinIO 가 늦게 뜨는 중). 받을 때까지 5→60초로 재시도한다
                 "buckets": {"pickage-raw": {"connected": true, "since": …, "last_event": …, "error": null, "reconnects": 0, "events": 300}},
                 "gaps": [{"bucket": "pickage-raw", "from": …, "to": …, "error": "…"}],    // 끊겼던 구간
                 "recent": [{"time": …, "bucket": …, "key": …, "size": …, "event": "s3:ObjectCreated:Put", "principal": "pickage-ingest", "source": "172.26.8.249"}],
                 "completed": [{"time": …, "bucket": …, "key": "…/_SUCCESS", "prefix": "…/run_id=…", …}],
                 "prefixes": [{"bucket": …, "prefix": "depsdev/v1/projects/snapshot=…", "objects": 14, "bytes": …, "latest": …, "recent": [...]}],
                 "totals": {"created": 300, "removed": 0, "bytes": …}},
      "inventory": {"available": true, "listed_at": …, "took_seconds": 4.1},   // 마지막 전체 목록의 요약. 본문은 /api/inventory
      "inventory_enabled": true},
  "local": {"paths": [{"label": "/srv/pickage/ingest-work", "note": "", "bytes": …, "files": …, "latest": …,
                       "scanned_at": …, "scan_seconds": 0.4, "refresh_seconds": 0,           // cached: true 면 refresh 주기 안의 마지막 결과
                       "entries": [{"name": "downloads-weekly", "bytes": …, "files": …, "latest": …, "oldest": …}],   // 바로 아래 항목별. 문헌 캐시면 샤드별
                       "new": {"window_hours": 24, "files": 120, "bytes": …, "list": [{"path": …, "bytes": …, "modified": …}]},
                       "oldest": [{"path": …, "bytes": …, "modified": …}],                    // 가장 오래된 max_new_files 개
                       "disk": {"total": …, "used": …, "free": …}}],
            "logs": [{"path": "/srv/pickage/ingest-work/downloads-weekly/2026-09-21/logs/downloads_weekly.log",
                      "size": …, "modified": …, "tail": ["…"], "error_lines": 0}]},
  "docker": {"matched": 6, "containers": [{"name": "pickage-data-minio-1", "image": …, "state": "running",
             "status": "Up 3 days", "exit_code": 0, "oom_killed": false, "started_at": …, "finished_at": null,
             "restart_count": 0, "health": "healthy", "log": {"lines": ["…"], "error_lines": 0, "since_hours": 6, "tail": 40}}]}
}
```

`/api/inventory` 의 본문은 `s3inv.collect` 의 결과 그대로다 — `buckets[].prefixes[]`(경로별 개수·크기·
24시간/7일 신규·최근 객체), `completed_runs[]`, `listed_at`, `took_seconds`, `requested_at`, `truncated`.

중계된 보고서에는 `fetched_via` · `fetched_at` 이 더 붙는다. 닿지 못한 노드는
`{"node": …, "unreachable": true, "errors": [{"section": "fetch", "message": …}]}` 다.

## 권한

| 무엇 | 왜 |
| --- | --- |
| MinIO 계정 `pickage-monitor` (`pipeline/minio/policies/monitor.json`) | **읽기 전용.** 목록·이벤트 구독은 전 버킷, 읽기는 raw·curated 의 `_ops/`, `curated-bundle/**/status.json`, `_current.json` 뿐. 데이터 본문은 읽지 않는다 |
| Docker 소켓 (읽기 전용 마운트, GET 만 호출) | 컨테이너 이름·종료 코드·로그. 소켓의 의미와 근거는 `deploy/prod/monitoring/README.md` 4절 — netdata 가 같은 근거로 이미 마운트한다 |
| `/srv/pickage/ingest-work` 읽기 전용 | 로컬 산출물·단계 로그 |
| 듣는 주소 | 인증이 없다 — netdata 와 같은 자세. 127.0.0.1(터널) 과 data 노드의 사설 IP(app 의 중계) 뿐이고, 사설 IP 의 문은 호스트 방화벽이 app 노드에만 연다 |

## 시험

```bash
python -m unittest discover -s pipeline/monitor -t .     # 실제 MinIO·Docker 없이 돈다 (서버 시험은 127.0.0.1 빈 포트)
```

가짜 S3·Docker 는 `test_support.py` 에, 가짜 이벤트 스트림은 `test_events.py` 에 있다
(`pipeline/weekly/test_state.py` 와 같은 태도). 실제 서비스가 있어야 보이는 것 — 소켓 권한,
사설망 중계, 실제 MinIO 의 이벤트 — 는 `deploy/prod/monitoring/README.md` 11절의 리허설로 본다.
