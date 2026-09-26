# 02. 운영 파티션 교체 명령서

`package_version_snapshot` 229개 날짜 파티션을 재정렬 10만 회차로 교체한다.
**데이터를 복사하지 않는다.** 날짜마다 새 파티션을 붙이고 옛 파티션을 떼어 낸 뒤 지운다.

전진님이 터미널에서 그대로 칠 수 있게 쓴다. 세션은 운영 PostgreSQL 에 접촉하지 않는다.
모든 수치는 2026-09-23 로컬 리허설 실측이다([01-rehearsal.md](01-rehearsal.md)).

## 0. 왜 날짜 단위인가

적재 모듈은 원래 **새 부모와 229개 자식을 전부 만든 뒤** 서비스 전환을 따로 한다
(`historical_db_fast_publish` 머리말: "Service cutover is deliberately separate").
그 방식은 전환 직전에 옛 86 GiB 와 새 86 GiB 가 동시에 존재한다.
앱 노드는 86 사용 + 50 여유이므로 **약 36 GB 모자란다.**

날짜 단위로 나누면 순간 최대가 **옛 표 전체 + 하루치 한 개**가 된다.
서비스 부모는 항상 229개 파티션을 온전히 갖고 있고, 실패해도 그 날짜만 되돌린다.

```
날짜 D 반복:  새 파티션 적재  →  교체  →  조회 확인  →  옛 파티션 제거
              +0.63 GB          카탈로그만   읽기만      -0.63 GB
```

## 1. 시작 전 한 번만

### 1.1 고정값

| 이름 | 값 |
| --- | --- |
| 계산 회차 | `data/vd455/h5b/run2-20260923-v1` |
| run manifest SHA | `dd92f148ed308c7960a84070657ce4a333e3204ee93bbd1295b548bf64a1056b` |
| 대상 목록 | `rerank_100k_20260922.csv` · SHA `001d63149f6ca5dfe9af5bc0b92d97a02dd97d31d43da9487debf87a59c549fb` (4,638,724 B) |
| 달력 | `data/vd455/snapshot/projects-v1/snapshot-candidate.json` · SHA `d14a5004d3ecb2d7408ffe02d9cd8b3b506432aea0767ac5e54cef2dd95a63bf` |
| 스테이징 스키마 | `vd193_reload_455_20260922` |
| 백업 스키마 | `vd455_backup_20260922` |
| `minimum_disk_gib` | **20** — 앱 노드 여유 50 GB 기준, 하루 피크 1.27 GB 의 약 15배 여유 |

대상 목록의 줄끝: `!266` 머지 후 새 체크아웃은 LF 다. 그 전에 받은 트리는
`git checkout -- datasets` 로 다시 받아 SHA 를 대조한다(CRLF 본은 4,738,725 B / `0908405d…`).

### 1.2 실행 환경 — 세 가지를 먼저 맞춘다

이 셋이 안 맞으면 한 날짜도 적재되지 않는다. 전부 리허설에서 실제로 걸렸다.

1. **pytz** — DuckDB 1.5.5 가 TIMESTAMPTZ 를 파이썬 값으로 바꿀 때 필요하다.
   없으면 `Required module 'pytz' failed to import` 로 멈춘다.
   2026-09-23 타워가 공유 `.venv-bq` 에 설치했다. 먼저 확인한다.
   ```bash
   .venv-bq/Scripts/python.exe -c "import pytz; print(pytz.__version__)"
   ```
2. **실행 위치와 PYTHONPATH** — `python -m` 은 cwd 가 PYTHONPATH 보다 앞선다. 아래 명령은
   이 브랜치가 체크아웃된 트리 루트에서 실행한다(머지 뒤에는 주 트리 develop). 다른 곳에서
   실행하면 고치기 전 코드가 돌아 `Reload code contract changed: historical_db_fast_publish.py`
   로 거부된다. 그리고 드라이버가 `build_reload_plan.py` 를 파일 경로로 실행하므로
   **저장소 루트를 `PYTHONPATH` 에 얹어야 한다.** 없으면 계획 단계에서
   `No module named 'pipeline'` 로 멈춘다(2026-09-25 운영에서 실제 발생, DB 무영향).
   ```powershell
   $env:PYTHONPATH='C:\git\S15P21A506'
   ```
3. **SQL 은 파일로 넣는다** — PowerShell 파이프로 흘리면 인코딩이 깨져
   `syntax error at or near "WHERE"` 같은 엉뚱한 오류가 난다. `docker cp` 후 `-f` 를 쓴다.

### 1.3 달력 계보 확인 — 여기서 막힐 가능성이 가장 크다

적재기는 DB 에 **이번 달력과 같은 `manifest_sha256`** 을 가진 PUBLISHED 실행이 있어야 진행한다.
이번 달력은 재생성본이고 파일 안에 생성 시각이 들어 있어 **재생성할 때마다 SHA 가 달라진다.**
원본 달력 파일은 로컬에도 서버 MinIO 에도 없다. 그래서 운영에는 다른 SHA 가 등록돼 있을 수 있다.

먼저 확인한다.

```bash
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -t -A -c "SELECT execution_id, status, manifest_sha256 FROM etl_load_execution WHERE dataset='snapshot-reference' ORDER BY updated_at DESC LIMIT 5;"
```

`d14a5004d3ecb2d7408ffe02d9cd8b3b506432aea0767ac5e54cef2dd95a63bf` 가 없으면 등록한다.
날짜는 건드리지 않고 실행만 연결한다(보고서 action 이 `LINKED_EXISTING`).

```bash
python -m pipeline.snapshot.load --candidate data/vd455/snapshot/projects-v1/snapshot-candidate.json --execution-id snapshot-reference-20260923-v455 --docker-container pickage-app-postgres-1 --database pickage --verify-only
```

`--verify-only` 로 내용을 확인한 뒤 그 옵션을 빼고 다시 실행해 등록한다. 운영 DB 사용자는
`pickage` 이므로 `--db-user pickage` 를 붙인다(기본값 `postgres` 로는 접속이 안 된다).
2026-09-25 운영 등록 결과: `LINKED_EXISTING`, 삽입 0, 기존 229일 연결, 7.6초.

### 1.3b package-version 모집단 계보 — 운영에는 없다

키 검증(`historical_db_keys.check_lineage`)은 달력 외에 **모집단 계보**도 본다. `etl_dataset_current`
의 `package-version` 포인터가 계산 회차의 Curated 회차·기준일·매니페스트·타임스탬프
(`curated-20260907-v2` / `2026-08-31` / `a537f84b…` / `2026-08-31T21:01:10.517131Z`)와 정확히
같은 PUBLISHED 실행을 가리켜야 한다. 아니면 `published package-version population lineage does not match`.

운영 DB 에는 이 행이 **없다.** 서비스 표는 S15P21A506-341 에서 로컬 검증 DB 를 pg_dump 로 옮긴 것이고
이관 계획이 "로컬 ETL 이력은 옮기지 않는다"고 정했기 때문이다. 리허설은 로컬 DB(계보 있음)에서 돌아
드러나지 않았다. 2026-09-25 에 로컬 `pickage` DB 의 `load-20260907-v2` 계보 행 3개
(`etl_load_execution`·`etl_load_attempt`·`etl_dataset_current`)를 그대로 운영에 등록했다.
등록 SQL 은 한 트랜잭션에 가드 셋을 둔다 — 운영에 package-version 계보가 없을 것, 운영 `package`·
`version` 의 정확한 행 수가 11,080,940 / 54,188,349 일 것, 등록 뒤 적재기의 계보 질의가 1행일 것.
서비스 표는 읽기만 하고 백엔드는 etl 표를 읽지 않으므로 서비스 영향은 없다. 되돌리기는 그 3행 DELETE.

확인:

```bash
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -A -c "SELECT c.execution_id, c.snapshot_at, e.curated_run_id, e.status FROM etl_dataset_current c JOIN etl_load_execution e ON e.dataset=c.dataset AND e.execution_id=c.execution_id WHERE c.dataset='package-version';"
```

`load-20260907-v2 | 2026-08-31 | curated-20260907-v2 | PUBLISHED` 한 행이 나와야 한다.

### 1.4 다른 적재기가 도는지 확인 — 겹치면 10초 만에 실패한다

적재기는 날짜마다 `package`·`version`·`snapshot`·`etl_snapshot_reference`·`etl_load_execution`·
`etl_dataset_current` 에 **SHARE 락**을 건다. 다른 데이터셋 적재기가 트랜잭션 중이면
`etl_load_execution` 의 RowExclusive 와 충돌해 `canceling statement due to lock timeout` 이 난다.

```bash
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -t -A -c "SELECT count(*) FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE c.relname IN ('etl_load_execution','etl_dataset_current','etl_snapshot_reference','package','version','snapshot') AND l.mode IN ('RowExclusiveLock','ShareRowExclusiveLock','ExclusiveLock','AccessExclusiveLock') AND l.pid <> pg_backend_pid();"
```

**0 이 아니면 시작하지 않는다.** 타워가 정한 적재 순번(U3 → U4 → U2 → U1)은 편의가 아니라
이 제약 때문이다.

### 1.5 교체 전 상태를 적어 둔다

```bash
docker cp docs/worklogs/S15P21A506-455/sql/partition-swap-setup.sql pickage-app-postgres-1:/tmp/setup.sql && docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -v ON_ERROR_STOP=1 -v bak=vd455_backup_20260922 -v parent=public.package_version_snapshot -f /tmp/setup.sql
```

기대 출력 — 마지막 한 줄.

```
 partitions | total_size | first_day  |  last_day
------------+------------+------------+------------
        229 | 86 GB      | 2022-05-08 | 2026-08-31
```

**`partitions` 가 229 가 아니면 멈춘다.** 이 명령서가 가정한 상태가 아니다.

### 1.6 디스크 여유

```bash
docker exec pickage-app-postgres-1 df -Pk /var/lib/postgresql/data | tail -1
```

여유가 **20 GiB 미만이면 시작하지 않는다.** 하루 피크는 1.27 GB 지만 적재 중 WAL 과
임시 파일이 함께 늘기 때문에 여유를 크게 둔다.

## 2. 한 묶음 (10일씩, 23회 반복)

최근 날짜부터 내려간다. 첫 묶음은 2026-08-31 부터 10일이다.
적재는 묶음 단위, **교체·확인·제거는 그 안에서 날짜 하나씩** 한다.

### 2.0 드라이버로 한 줄에 — 아래 2.1~2.5 를 손으로 치지 않아도 된다

날짜마다 세 명령이면 229일에 약 690개다. `swap_batch.py` 가 그 순서를 대신 친다.
새 SQL 을 만들지 않고 아래 2.1~2.5 와 **같은 docker/psql 호출**만 쓴다.

```bash
python docs/worklogs/S15P21A506-455/sql/swap_batch.py --batch 1 --batch-size 10 --run-dir data/vd455/h5b/run2-20260923-v1 --run-manifest-sha256 dd92f148ed308c7960a84070657ce4a333e3204ee93bbd1295b548bf64a1056b --schema vd193_reload_455_b01 --bak vd455_backup_20260922 --parent public.package_version_snapshot --container pickage-app-postgres-1 --user pickage --database pickage --output data/vd455/reload/prod
```

(2026-09-25 운영 실행은 산출물이 주 트리에 있어 `--run-dir`·`--output` 을 절대 경로로 줬다.
`--batch N` 과 `--schema …_bNN` 두 곳만 바꿔 반복한다.)

- 묶음 1 이 가장 최근 10일이다. 끝나면 `--batch 2`, `--batch 3` 으로 이어 간다.
- **묶음마다 `--schema` 를 다르게 준다** (`vd193_reload_455_b01`, `_b02`, …). 적재기 `inspect_target` 이
  스키마에 저장된 계획과 새 묶음의 계획(날짜가 다름)을 비교해 같은 스키마로는
  `Stored reload plan/code/input/service contract differs` 로 거부하고, 교체로 자식이 빠져나간 뒤에는
  `Partition and receipt coverage differ` 에도 걸린다. 백업 스키마와 `--output` 은 그대로 둔다.
  새 파티션은 그 스키마 안에 남으므로 완료 뒤 파티션 229개가 `_b01`..`_b23` 에 10개씩 보인다.
  근본 수정은 S15P21A506-481.
- 첫 묶음 전에 세션 기본값을 올리면 FK 검증·PK 생성이 빨라진다(운영 기본 64MB). 끝나면 되돌린다.
  ```sql
  ALTER ROLE pickage SET maintenance_work_mem='256MB';   -- 끝난 뒤: ALTER ROLE pickage RESET maintenance_work_mem;
  ```
- 교체 SQL 은 ATTACH 전에 **서비스 부모의 CHECK 제약을 새 파티션에 복사**한다. V7 이 넣은
  `ck_package_version_snapshot_dependents_nonnegative` 가 자식에 없으면 PostgreSQL 이
  `child table is missing constraint` 로 거부한다(2026-09-25 운영 첫 교체에서 발생, 롤백으로 무영향).
  리허설의 로컬 부모 표에는 그 CHECK 가 없어 드러나지 않았다.

**2026-09-25 운영 묶음 1 실측** (10일, 7,336,106~7,829,660 행/일): 적재 1,908초 = 날짜당 167초
(스테이징 52 · COPY 27 · FK 42 · PK 12 · 값 검증 9 · 커밋 전 4.5), 교체·확인·제거 날짜당 약 23초(CHECK 추가 포함).
리허설 76초의 2.2배 — 운영 컨테이너 2 GiB 에서 version PK 가 캐시에 남지 않고 SSH 전송이 더해진다.
229일 예상 약 13시간. 실패 뒤 같은 명령을 다시 치면 끝난 날짜를 다시 값 대조하느라 적재 단계에 약 17분이 붙는다.
스테이징 중복 제거는 S15P21A506-480.
- 어느 단계든 실패하거나 값이 어긋나면 **즉시 멈춘다.** 뒤 날짜는 손대지 않는다.
  마지막 날짜·단계·출력이 `<output>/driver-status.json` 에 남는다.
- 이미 끝난 날짜는 건너뛴다. 같은 명령을 다시 쳐도 안전하다.
- 1.5 절 설정도 드라이버가 직접 친다(`CREATE ... IF NOT EXISTS` 뿐이라 반복해도 무해).

2026-09-24 로컬에서 2일 묶음으로 검증했다. 적재 117.5초, 날짜당 교체·확인·제거 약 4초,
`delta_bytes` 0, 84.7 바이트/행. 재실행은 1초 만에 전부 건너뛰었다.

아래 2.1~2.5 는 드라이버가 무엇을 치는지와, 한 날짜만 손으로 다룰 때의 절차다.

### 2.1 적재 계획 만들기

`--date` 를 날짜 수만큼 반복한다(아래는 2일 예시, 실제로는 10개).

```bash
python docs/worklogs/S15P21A506-455/sql/build_reload_plan.py --run-dir data/vd455/h5b/run2-20260923-v1 --run-manifest-sha256 dd92f148ed308c7960a84070657ce4a333e3204ee93bbd1295b548bf64a1056b --schema vd193_reload_455_20260922 --container pickage-app-postgres-1 --user pickage --database pickage --date 2026-08-31 --date 2026-08-24 --minimum-disk-gib 20 --output data/vd455/reload/prod-batch-01
```

출력의 `expected_rows`(묶음 합계)와 `db_identity` 를 적어 둔다.
`scope` 가 `SELECTED_DATES` 인지 확인한다. 날짜 하나의 기대 행 수는
2026-08-31 이 **7,829,660** 이고 과거로 갈수록 줄어든다.

### 2.2 적재

```bash
python -m pipeline.version_dependents.historical_db_reload --config data/vd455/reload/prod-batch-01/config.json --publish
```

끝나면 `status=PILOT_VERIFIED` 다. 리허설 실측은 날짜당 75.7초
(COPY 7.5 · PK 5.1 · FK 24.2 · 값 검증 6.0 · ATTACH 0.009)이고, 여기에 묶음마다
키 검증 한 번(versions.tsv 112 MB 전송)이 더해진다. 운영은 회선·부하가 달라 더 걸린다.

중간에 멈추고 싶으면 `--stop`, 이어서 하려면 `--publish --resume` 이다.
완료한 날짜는 다시 넣지 않고 DB 값을 재검증한다.

### 2.3 교체

```bash
docker cp docs/worklogs/S15P21A506-455/sql/partition-swap.sql pickage-app-postgres-1:/tmp/swap.sql && docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -v ON_ERROR_STOP=1 -v sch=vd193_reload_455_20260922 -v bak=vd455_backup_20260922 -v day=2026-08-31 -v cmp=full -v parent=public.package_version_snapshot -f /tmp/swap.sql
```

한 트랜잭션이 하는 일 — 순서대로다.

1. 새 파티션의 기본키·검증된 외래키 2개·`date_bound` CHECK 를 본다.
   `date_bound` 가 없으면 ATTACH 가 수백만 행을 스캔하므로 **없으면 중단한다.**
2. 행 수가 적재 영수증과 같은지 세고, 영수증의 `child_oid` 와 실제 OID 가 같은지 본다.
3. 옛 파티션을 **이름이 아니라 경계값으로** 찾는다.
4. 두 회차에 공통으로 있는 대상의 `dependents_count` 를 전부 대조한다.
   선정 목록은 target 만 고르고 source 는 생태계 전체이므로, 살아남은 대상의 값은
   회차가 바뀌어도 같아야 한다. **한 건이라도 다르면 중단한다.** 리허설에서 3.5초 걸렸다.
5. 새 파티션을 붙이고 옛 파티션을 백업 스키마로 옮긴다. 전부 카탈로그 변경이다.
6. 경계·파티션 개수·기본키·상속된 외래키를 다시 확인한다.
7. 영수증을 남긴다.

기대 출력 — 마지막 한 줄. `delta_bytes` 는 0 근처다.

```
 snapshot_at | old_rows | old_size | new_rows | new_size | delta_bytes | bytes_per_row | compared_rows | compare_scope
-------------+----------+----------+----------+----------+-------------+---------------+---------------+---------------
 2026-08-31  |  7823980 | 717 MB   |  7829660 | 633 MB   |         ... |          84.7 |       ...     | full
```

**멈춤 기준** — 하나라도 해당하면 그 날짜에서 멈추고 컨트롤 타워에 알린다.

- `ERROR` 로 끝났다 (트랜잭션이 통째로 취소됐으므로 서비스는 손대기 전 그대로다)
- `bytes_per_row` 가 **84.7 에서 20% 넘게** 벗어났다 (67.8 미만 또는 101.6 초과)
- `compared_rows` 가 0 이다 (입력이 의심스럽다)
- `delta_bytes` 가 +0.3 GB 를 넘는다 (누적되면 장부를 넘긴다)

### 2.4 서비스 조회 확인

지우기 전에 실제 조회가 되는지 본다.

```bash
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -t -A -c "SELECT count(*), sum(dependents_count) FROM package_version_snapshot WHERE snapshot_at='2026-08-31';"
```

### 2.5 옛 파티션 제거 — 디스크가 줄어드는 유일한 단계

```bash
docker cp docs/worklogs/S15P21A506-455/sql/partition-swap-drop-old.sql pickage-app-postgres-1:/tmp/dropold.sql && docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -v ON_ERROR_STOP=1 -v bak=vd455_backup_20260922 -v day=2026-08-31 -v parent=public.package_version_snapshot -f /tmp/dropold.sql
```

지우기 전에 **새 회차가 실제로 서비스 중인지** 다시 확인하므로, 되돌린 상태에서 실수로
지우는 일은 막힌다. 지운 뒤에는 그 날짜를 되돌릴 수 없다.

## 3. 실패했을 때

### 3.1 교체 트랜잭션이 ERROR 로 끝났다

**아무것도 하지 않아도 된다.** 한 트랜잭션이라 통째로 취소됐고 서비스 파티션은 그대로다.
리허설에서 값 불일치를 일부러 만들어 확인했다 — 부모의 파티션·백업 스키마·영수증이
손대기 전 그대로였다. 오류 문구를 그대로 컨트롤 타워에 전달한다.

### 3.2 교체는 됐는데 뒤에서 문제를 발견했다 (아직 제거 전)

```bash
docker cp docs/worklogs/S15P21A506-455/sql/partition-swap-rollback.sql pickage-app-postgres-1:/tmp/rollback.sql && docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -v ON_ERROR_STOP=1 -v sch=vd193_reload_455_20260922 -v bak=vd455_backup_20260922 -v day=2026-08-31 -v parent=public.package_version_snapshot -f /tmp/rollback.sql
```

옛 파티션이 서비스로 돌아온다. 리허설 실측 0.17초. 데이터 복사는 없다.
`old_dropped_at` 이 이미 찍혀 있으면 거부한다 — 그때는 되돌릴 수 없고 재적재해야 한다.

되돌린 뒤 새 파티션은 떼어진 채 남는다. 원인을 고친 뒤 2.3 을 다시 실행하면 된다
(교체 스크립트가 떼어진 상태를 받아들인다).

### 3.3 제거까지 한 뒤에 문제를 발견했다

되돌릴 수 없다. 그 날짜를 다시 적재한다. 서비스에는 새 회차 값이 이미 들어가 있으므로
데이터가 비는 것은 아니다.

## 4. 장부

| | 값 |
| --- | ---: |
| 기존 229일 총 행 수 | 1,007,079,260 |
| 새 229일 총 행 수 | **1,094,936,926** (+8.7%) |
| 실측 바이트/행 | **84.69** |
| 새 총 크기 추정 | 약 86.4 GiB |
| 기존 총 크기 | 86 GiB |
| **최종 순증 추정** | **약 +0.4 GiB** |
| 날짜당 순간 최대(가장 큰 날짜) | 약 1.27 GB |
| 날짜당 정착 후 | 약 0.63 GB |

날짜마다 `bytes_per_row` 와 `delta_bytes` 를 타워에 보고하고 장부를 갱신한다.

## 5. 어디서 실행하는가 — 파일을 서버로 옮기지 않는다

다른 로더(`downloads_reload`·`dependent_transitions`)와 같은 방식으로 돈다.
**전진님 PC 에서 `DOCKER_HOST=ssh://a506app` 를 걸고 실행한다.**

```bash
export DOCKER_HOST=ssh://a506app
```

성립하는 이유를 코드에서 확인했다.

- 적재기는 `COPY <table> FROM STDIN` 으로 넣는다(`historical_db_fast_publish.copy_counts_to`).
  로컬 파일을 1 MiB 씩 읽어 psql 의 **표준입력으로 흘린다.** 서버에 파일을 두지 않는다.
- Parquet 은 DuckDB 가 **로컬에서** 읽는다. 86 GiB 는 PostgreSQL 안에서만 생긴다.
- 디스크 점검 `inspect_resources` 는 `command[0]` 이 `docker` 일 때만 동작하는데
  이 방식이 바로 그 경우다. `docker exec <컨테이너> df -Pk /var/lib/postgresql/data` 가
  **서버 컨테이너에서** 실행되므로 올바른 파일시스템을 잰다.
- SQL 은 `docker cp` 로 넣는다. 같은 `DOCKER_HOST` 를 쓰므로 원격에도 그대로 들어간다.

### 5.1 전송량 — 날짜를 묶어서 처리한다

리허설에서 잰 전송 파일 크기(2026-08-31 기준, 가장 큰 날짜)다.

| 파일 | 크기 | 언제 보내나 |
| --- | ---: | --- |
| `counts.tsv` | 210.2 MB | **날짜마다** |
| `versions.tsv` | 112.3 MB | **적재기 실행마다 1회** (키 검증) |
| `identities.tsv` | 2.7 MB | 적재기 실행마다 1회 |

키 검증은 날짜 반복 **앞에서 한 번** 수행된다. 그래서 날짜 하나마다 적재기를 따로 띄우면
115 MB 를 229번 다시 보내게 된다(약 26 GB 낭비).

**날짜를 묶어서 한 번에 계획에 넣는다.** `--date` 를 여러 번 주면 된다.

| 묶음 크기 | 스테이징 피크 | 키 검증 재전송 |
| ---: | ---: | ---: |
| 1 | 0.63 GB | 26 GB |
| **10** | **약 6.3 GB** | **약 2.6 GB** |
| 20 | 약 12.6 GB | 약 1.3 GB |

**10 을 권한다.** 앱 노드 여유 50 GB 에서 스테이징 6.3 GB 를 써도 `minimum_disk_gib=20` 에
걸리지 않는다. 묶음을 적재한 뒤 그 안의 날짜를 하나씩 교체·확인·제거하고 다음 묶음으로 간다.

날짜별 `counts.tsv` 평균은 약 135 MB 다(229일 총 1,094,936,926행 / 날짜당 평균 4.78 M행).
전체 전송량은 약 31 GB + 키 검증 2.6 GB 다. SSH 압축(`Compression yes`)을 켜면
counts 는 약 11% 로 줄어든다(실측 표본 기준).

## 6. 이 문서가 다루지 않는 것

- 백엔드 코드·API 변경. 이 교체는 값만 바꾸고 스키마 계약은 그대로다.
- 229일을 마친 뒤 스테이징·백업 스키마 정리. 전부 끝나고 따로 한다.
