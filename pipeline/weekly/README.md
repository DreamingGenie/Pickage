# 주간 수집 회차 실행기

매주 한 번, deps.dev 주간 증분과 npm 다운로드 직전 14일을 받아 MinIO Bronze 까지 넣는다.
수집 로직은 여기 없다 — 기존 CLI 를 정해진 인자로 순서대로 부를 뿐이다.
계획과 결정은 [S15P21A506-273](https://ssafy.atlassian.net/browse/S15P21A506-273).

**Curated → PostgreSQL 게시는 이 실행기의 책임이 아니다.** 다음 단계가 읽는 완료 신호는
지금도 MinIO 의 `_SUCCESS` 와 `_current.json` 이다. `_ops/weekly/` 의 상태 객체는
인계 채널이 아니라 사람이 보는 창이다.

## 어디서 도나

**data 노드(j15a506a)의 일회성 컨테이너**다. app 노드에는 서비스가 직접 쓰는 것만 둔다 —
프런트, 백엔드, 서비스 PostgreSQL. DB 적재 전 전처리용 Parquet 은 거기 속하지 않는다.

```
[systemd timer 10분]
  └─ run-weekly-ingest.sh        (호스트: 잠금 + 컨테이너 정리만. 판단하지 않는다)
       └─ docker compose run --rm --name pickage-weekly-run ingest-weekly
            └─ python -m pipeline.weekly.run
```

운영 절차(설치·확인·문제 대응)는 [`deploy/prod/data/README.md`](../../deploy/prod/data/README.md)
의 "주간 수집" 절에 있다. 이 문서는 실행기 자체를 설명한다.

## 실행

```bash
# 평소 (systemd timer 가 10분마다 이것을 부른다)
python -m pipeline.weekly.run

# 단계를 돌리지 않고 판정만 흉내 낸다. 상태 객체에는 쓰지 않는다
python -m pipeline.weekly.run --dry-run

# 한 단계만 (진단용)
python -m pipeline.weekly.run --only gcs_sync

# 수집 창·직전 상태를 무시하고 전부 다시
python -m pipeline.weekly.run --force
```

⚠ `--force` 는 **다시 돌릴 단계의 기록을 먼저 지운다.** 안 지우면 중간에 실패했을 때 뒤
단계의 옛 `SUCCEEDED` 가 남고, 다음 발화가 그것을 건너뛴다 — 새로 받은 상류 산출물 위에
이전 회차의 입고 결과가 최신인 척 남는다. 지우는 범위는 **이번에 돌릴 단계뿐**이라
`--force --only <step>` 은 다른 단계의 기록을 건드리지 않는다.

종료 코드가 스케줄러가 보는 값이다. **0 = 할 일이 없었거나 끝까지 갔다, 1 = 단계가 실패했다.**

## 할 일이 없으면 아무것도 안 한다

10분마다 깨워도 헛돌지 않는다. 판정 순서가 곧 비용 순서다.

1. 로컬 달력으로 `week_of` = 가장 최근 월요일
2. **MinIO 객체를 한 번만 읽는다** — 그 주가 `SUCCEEDED` 면 끝 (BigQuery 를 건드리지 않는다.
   `Snapshots` 조회는 쿼리당 최소 과금 10 MB라 10분마다 부르면 낭비다)
3. `RUNNING` 이고 26시간이 안 지났으면 끝
4. `BLOCKED` 이고 수동 요청이 없으면 끝
5. 화요일 10:00 KST 전이고 수동 요청도 없으면 끝

그 뒤에야 단계를 돈다. 단계별 이어받기는 각 CLI 가 이미 한다 — BigQuery 는 GCS 의
`_MANIFEST.json`, downloads 는 `checkpoint.sqlite`, 입고기는 `_SUCCESS` 와 객체 해시 대조.
그래서 실패한 회차는 같은 명령을 다시 부르기만 하면 된다.

## 단계

| 단계 | 부르는 것 |
| --- | --- |
| `depsdev_t2` | `collectors/bigquery/collect.py --tier t2 --snap <week_of>` |
| `gcs_sync` | 그 스냅샷 산출물만 `gcloud storage rsync` 로 `data/raw/<table>/snapshot=<week_of>/` 에 |
| `downloads_weekly` | `collectors/downloads/collect.py --mode weekly` (14일 창) |
| `downloads_parquet` | `collectors/downloads/to_parquet.py` |
| `bronze_depsdev` | `minio/ingest_raw.py --snapshot <week_of>` |
| `bronze_downloads` | `python -m pipeline.downloads.load` |

### 종료 코드 0 이 "다 받았다" 는 뜻은 아니다

수집기 둘은 **덜 받고도 0 으로 끝난다.** 종료 코드만 보면 성공으로 보이는 자리다.

| 어디 | 무슨 일 | 지금 |
| --- | --- | --- |
| BigQuery | 누적 예산(`TIERS['t2']` 26 GiB)을 넘기면 남은 테이블을 포기하고 정상 종료 (`stopped_budget`) | **`depsdev_t2` 가 막는다** — GCS 매니페스트를 `T2_TABLES` 와 대조해 모자라면 그 단계를 실패로 올린다 |
| npm downloads | 요청 실패를 manifest 에 적고 정상 종료. 다시 실행해도 `failed` 작업은 **다시 고르지 않는다**(`status IN ('pending','retry')`) | 보이게만 해 뒀다 — 단계 detail 의 `tasks_by_status`·`failed_tasks`. 재수집 경로는 [S15P21A506-367](https://ssafy.atlassian.net/browse/S15P21A506-367) |

**대조를 `depsdev_t2` 안에 두는 것이 핵심이다.** 뒤 단계(`gcs_sync`)로 미루면 `depsdev_t2`
가 `SUCCEEDED` 로 남아 다음 발화가 수집기를 건너뛰고, 같은 실패만 열 번 반복해 `BLOCKED`
로 간다. 지금 자리에서는 다음 발화가 수집기를 다시 부르고, 이미 매니페스트가 있는 테이블은
예산을 쓰기 전에 건너뛰므로(`skipped_manifest_exists`) 남은 것에 예산이 온전히 간다 —
**재시도가 수렴한다.**

## 상태는 MinIO 에 있다

```
pickage-raw/_ops/weekly/<week_of>/run.json             러너만 쓴다
pickage-raw/_ops/weekly/<week_of>/manual-request.json  백엔드만 쓴다 (우편함)
```

**객체마다 필자가 하나라 경쟁이 없다.** 러너는 한 번에 하나만 돌고(호스트 잠금 + 고정
컨테이너 이름), 백엔드는 우편함만 쓴다. 그래서 읽고-고쳐-쓰기를 잠금 없이 해도 된다.

`pickage-raw` 안에 두는 이유는 이 저장소의 관례가 **"실행 메타데이터는 데이터 옆, 같은
버킷"** 이기 때문이다(`run_manifest.json`·`_SUCCESS`, curated 의 `_current.json`).
주간 회차 6단계의 산출물이 전부 이 한 버킷에 떨어지므로, 운영용 버킷을 따로 파면
데이터와 그 입고 이력이 갈린다.

목록 조회용 `_index.json` 은 두지 않는다. 주 단위라 1년치가 객체 52개뿐이고, 인덱스를
두면 `run.json` 과 어긋날 수 있는 **두 번째 진실**이 생긴다.

### `coverage` — "언제 데이터까지 들어왔나"

```json
"coverage": {
  "depsdev_snapshot": "2026-09-21",
  "downloads_through": "2026-09-20",
  "downloads_window": ["2026-09-07", "2026-09-20"]
}
```

전부 `week_of` 에서 유도되므로 계산해서 넣어도 되지만, 그러면 **읽는 쪽이 규칙을 알아야
한다.** 이 값이 없으면 "어느 날짜 데이터까지 들어왔나" 에 답하려고 코드를 봐야 한다.
가장 최근 `SUCCEEDED` 회차의 이 값이 지금 서비스가 가진 데이터의 끝이다.

## 날짜와 이름을 회차에서 유도하는 이유

전부 `week_of`(그 주 월요일, deps.dev 스냅샷 날짜) 하나에서 나온다. 실행한 날짜를 쓰면
수요일에 재시작했을 때 값이 달라져 **처음부터 다시 받는다.**

| 값 | 규칙 | 예 (`week_of` = 2026-09-21) |
| --- | --- | --- |
| downloads `--run` | 그 주 화요일 | `2026-09-22` |
| downloads `--end` | 직전 일요일 | `2026-09-20` |
| 14일 창 | `[end-13, end]` | `2026-09-07` ~ `2026-09-20` |
| deps.dev Bronze `--run-id` | | `bronze-weekly-20260921` |
| downloads Bronze `--run-id` | | `downloads-weekly-20260921` |

`--run-id` 를 생략하면 입고기가 타임스탬프와 uuid 로 새 값을 만들어 **매번 다른 경로에 같은
데이터를 또 올린다.** 회차마다 7일이 새로 들어오고 7일이 직전 회차와 겹친다.

`--snap` 을 회차 날짜로 못 박는 이유도 같다. 생략하면 "Snapshots 최신"이라, 수요일에
재시작했는데 그 사이 새 스냅샷이 나오면 조용히 다른 주를 받는다. 없는 스냅샷을 지정하면
수집기가 "파티션이 없다"로 멈추는데 — 그게 낫다.

## 회차마다 downloads 루트를 가르는 이유

산출물이 `data/downloads-weekly/<week_of>/` 아래로 간다. 백필과 같은 루트를 쓰지 않는다.

입고기의 `pipeline/downloads/input.py::_select()` 는 `root/parquet/downloads` **전체**를
대상으로 잡는다 — `--source-run` 으로 좁히는 것은 `raw/run=…` 뿐이다. 백필과 루트를
공유하면 주간 갱신마다 6,200만 행을 통째로 다시 올리게 된다.

대상 CSV(`datasets/targets/rank_top100k_20260902.csv`)는 회차 루트로 **복사**한다.
입고기가 루트 레벨 CSV 를 요구하고 심링크를 거부한다(`_assert_no_symlink`).

**입고 실행 보고서는 회차 루트 밖**(`data/downloads-weekly/_executions/<week_of>/`)에 둔다.
`load.py` 가 `--work-dir` 를 `--source-root` 안에 두는 것을 거부하는데 그럴 만한 이유가 있다 —
보고서를 먼저 쓴 뒤 `_select()` 가 `source_root` 전체를 훑고, 분류 규칙에 없는 파일을 만나면
`unknown regular file must be classified` 로 멈춘다. `.log` 에는 규칙이 있지만
`execution_report.json` 에는 없다. 로그만 회차 루트 안에 두는 이유가 그것이다.
`test_steps.py` 가 이 배치를 못 박는다.

## 실패와 수동 실행

단계가 실패하면 회차가 `FAILED` 가 되고 연속 실패 횟수가 1 오른다. 10회에 닿으면 `BLOCKED`
가 되어 **자동 재시도를 멈춘다.** 같은 실패를 10분마다 영원히 반복하지 않기 위한 것이다.

푸는 방법은 하나 — 수동 실행 요청이다. 백엔드가
`POST /api/v1/ops/weekly/runs/{weekOf}/manual-request` 로 `manual-request.json` 을 쓰면,
다음 발화에서 실행기가 그것을 집어 가며 연속 실패 횟수를 0으로 되돌린다. 지연은 최대
10분이고, 23시간짜리 회차에 그 정도는 의미가 없다. 백엔드는 호스트를 조종하지 않고
우편함에 넣을 뿐이다 — 노드를 넘는 실행 권한(SSH 키·Docker 소켓) 위임은 이 저장소가
이미 거부한 선택이다.

**회차 객체가 아직 없어도 우편함만으로 회차가 선다.** 한 번도 돌지 않은 주에 건 수동
요청이 수집 창이 열릴 때까지 묻히면 안 되기 때문이다.

**지난 회차의 요청도 집어 간다.** 실행기는 이번 주를 먼저 보고, 이번 주에 할 일이 없으면
우편함이 걸린 지난 회차를 훑어 **오래된 것부터** 고른다(`state.pending_manual_weeks()`).
이게 없으면 주가 넘어간 `BLOCKED` 회차를 되살릴 방법이 아예 없어진다 — 타이머가 이번 주만
보는 동안 백엔드는 200 과 `manual_pending: true` 를 계속 돌려주므로 **요청한 사람은
처리되는 줄 안다.** 훑는 비용은 `manual-request.json` 키만 거르는 LIST 한 번이고, 평소에는
결과가 비어 있어 뒤따르는 GET 이 없다.

이번 주가 우선인 이유는 러너가 한 번에 한 회차만 돌기 때문이다(같은 체크포인트, 같은 IP).
그래서 화요일 창이 열려 회차가 도는 동안은 지난 회차가 기다린다.

### "아직" 은 실패가 아니다

**공급자 지연은 실패로 세지 않는다.** deps.dev 가 그 주 스냅샷을 아직 안 올렸으면 수집기가
전용 종료 코드(`EXIT_SNAPSHOT_NOT_READY = 3`)로 알려 주고, 실행기는 그 단계를 `SKIPPED`
(`detail.reason = source_not_ready`)로 남긴 뒤 **연속 실패 횟수를 올리지 않고** 회차를
`PENDING` 으로 되돌린다. 다음 발화가 같은 자리에서 다시 본다.

이렇게 하지 않으면 **공급자가 두 시간 늦는 것만으로 회차가 `BLOCKED` 가 되어 사람을 부른다**
— 10분 타이머 기준 10회면 100분이다. 게다가 `BLOCKED` 를 알려 주는 알림이 없어서, 한 주를
통째로 놓친 것을 다음 주 화요일까지 아무도 모르게 된다.

무한정 기다리지는 않는다. **창이 열린 뒤 `SNAPSHOT_GRACE`(12시간, 화 22:00 KST)를 넘기면
그때는 실패로 올린다** — 그쯤이면 공급자 지연이 아니라 사람이 볼 일이다. 유예를 실행기가
처음 시도한 시각이 아니라 **창이 열린 시각**부터 재는 이유는, 타이머가 멈춰 있다가 늦게
깨어났다고 해서 유예가 늘어나면 안 되기 때문이다.

기다리는 동안 10분마다 BigQuery `Snapshots` 를 한 번씩 본다(쿼리당 최소 과금 10 MB).
유예 12시간을 꽉 채워도 720 MB 로, 월 무료 1 TiB 의 0.07% 다.

> 실패로 올라가는 다른 중단(예산 초과·행 수 불일치·기대치 편차)은 전부 종료 코드 1 이라
> 그대로 `FAILED` 로 센다. 그쪽은 기다린다고 해결되지 않는다.

`RUNNING` 인 채로 26시간이 지나면 죽은 실행으로 보고 회수한다. downloads 한 바퀴가 약
23시간이라(상위 10만 중 스코프 54.6%는 벌크를 못 써서 개별 호출, IP 지속 한도 분당 약 40건)
그보다 넉넉해야 정상 실행을 죽이지 않는다.

## 지난 회차 정리

회차가 **성공한 뒤에만**, 지난 회차의 로컬 산출물을 지운다. 남기는 개수는 `--keep-weeks`
(기본 2)이고, 음수를 주면 정리하지 않는다.

| 지우는 것 | |
| --- | --- |
| `data/downloads-weekly/<week>/` | raw·parquet·체크포인트·로그 |
| `data/downloads-weekly/_executions/<week>/` | 입고 실행 보고서 |
| `data/raw/<table>/snapshot=<week>/` | 그 주차 deps.dev 산출물 |

MinIO 에 `_SUCCESS` 가 붙은 뒤로 로컬 사본은 사본일 뿐인데, 두면 주당 약 10 GB 씩 쌓인다.
**data 노드에서는 MinIO 데이터와 같은 파티션**이라, 채우면 수집만 멈추는 게 아니라
저장소가 통째로 선다.

안전장치가 셋이다.

- **`SUCCEEDED` 회차만 고른다.** 실패했거나 도는 중인 회차를 지우면 체크포인트가 사라져
  그 주를 처음부터 다시 받는다(약 23시간).
- **`data/raw` 에서는 그 주차 스냅샷만 건드린다.** 거기에는 T0·T1 백필(projects 229 스냅샷,
  2022년부터)이 같이 들어 있고, 그건 BigQuery 50 GiB 를 다시 스캔해야 복구된다.
  지우기 직전에 경로 이름에 그 날짜가 박혀 있는지 다시 본다.
- **실패해도 회차 성공을 되돌리지 않는다.** 청소가 안 됐다고 수집을 실패로 표시하면 다음
  발화가 23시간짜리 잡을 또 돌린다. 로그에만 남는다.

`--dry-run` 에서는 지우지 않고 대상만 찍는다.

## 확인

```bash
# 빠른 층 — DB·네트워크 불필요 (실측 100개 0.20초)
python -m unittest discover -s pipeline/weekly -t . -p 'test_*.py'

# 느린 층 — 실제 MinIO 가 필요하다. 지정하지 않으면 skip 이다 (실측 6개 13.3초)
#   가짜 S3 가 흉내 낼 수 없는 계약만 본다 — 없는 객체 GET 의 예외 모양,
#   Delimiter 를 준 list_objects_v2 의 CommonPrefixes, Delimiter 없는 같은 호출의
#   Contents(지난 회차 우편함 찾기), 한글 JSON 왕복
docker compose --profile data up -d minio
WEEKLY_MINIO_TEST=1 python -m unittest pipeline.weekly.test_integration -v
```

지금 상태를 보는 법은 [`deploy/prod/data/README.md`](../../deploy/prod/data/README.md) 의
"주간 수집" 절에 있다(`mc cat` 한 줄이다).

단계별 출력 전문은 `data/downloads-weekly/<week_of>/logs/<step>.log` 에 이어 쌓인다.
실패 메시지에는 그 꼬리 4 KB 만 싣는다.

## 환경

| 변수 | 쓰는 곳 |
| --- | --- |
| `PICKAGE_MINIO_ENV` | 입고기와 상태 계층이 읽을 자격증명 **파일 이름**. data 노드는 `.env.data` |
| `OSS_SHIFT_UA_CONTACT` | downloads 수집기. 비어 있으면 시작하지 않는다 |
| `GOOGLE_APPLICATION_CREDENTIALS` | BigQuery·GCS **파이썬 클라이언트** |
| `CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE` | **gcloud CLI.** 위와 별개 경로다 — 둘 다 세워야 한다 |

자격증명이 환경변수가 아니라 파일인 것에 주의한다. `pipeline/minio/ingest_raw.py` 의
`client()` 가 `pipeline/minio/<PICKAGE_MINIO_ENV>` 를 직접 열어 파싱한다.

자식 프로세스에는 `PYTHONIOENCODING=utf-8` 을 넣어 준다. Windows 에서 출력을 파일로 돌리면
기본 인코딩이 cp949 가 되어 em dash 한 글자에 프로세스가 죽는다.
