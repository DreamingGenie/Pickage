"""유지·유입·이탈 회차를 PostgreSQL `dependent_transition` 에 원자 게시한다 (S15P21A506-361).

입력은 `pipeline/minio/ingest_derived.py` 가 Curated 에 올린 완료 실행이다.

    pickage-curated/depsdev/v1/dependent-transitions/
      snapshot={snapshot}/run_id={run_id}/
        run_manifest.json
        _SUCCESS
        data/dependent_transitions.parquet

    PICKAGE_MINIO_ENV=.env.server python -m pipeline.dependent_transitions.load \\
      --snapshot 2026-08-31 --run-id dependent-transitions-20260917-v1 \\
      --docker-container pickage-local-postgres-1 --database pickage --verify-only

**`_current.json` 을 따라가지 않는다.** 어떤 회차를 게시하는지 사람이 명시한다 —
`pipeline/postgresql/load.py` 가 같은 이유로 같은 규칙을 쓴다.

## 왜 별도 적재기인가

`pipeline/similar_package/load.py` 와 흐름이 같지만(advisory lock → staging → 이름 해석 →
전량 교체 → etl 이력) 그 파일은 `pickage-vectors` 의 AI 배치 산출물을 읽고 실행 경로가
`model=/corpus=` 다. 공통화하려면 동작 중인 남의 파일을 고쳐야 한다.
`pipeline/postgresql/` 은 같은 Curated 를 읽지만 package·version 5,400만 행 전용으로
특화돼(의존성 JSON 기본값·품질 리포트) 90만 행 전량 교체에는 과하다.
진짜 공용인 `pipeline.minio.ingest_raw` 의 `client`·`exists` 는 그대로 쓴다.

## 이름이 안 붙는 행은 버려진다 — 반드시 보고한다

표의 `package_id` 는 `package` 테이블을 가리키는 FK 다. 산출물은 패키지 **이름**을 담으므로
적재할 때 이름을 id 로 바꾸는데, `package` 에 없는 이름은 붙일 수 없어 빠진다.
빠진 수를 조용히 넘기면 "왜 10만이 아니라 9만이지" 가 된다. 그래서 staged·loaded·
unresolved 를 quality 로 남기고 화면에도 찍는다. 한 건도 못 붙으면 게시하지 않는다.

**목업 시드(`seed_service_full.sql`)를 넣은 로컬 DB 는 `package` 가 322개뿐이라 거의 전부
빠지는 것이 정상이다.** 실데이터(1,100만)에서 돌려야 매칭률이 의미 있다.

## 2026-09-17 실적재 — 2.3% 가 빠지는 것이 정상이다

`package` 11,080,940행(`curated-20260907-v2`)을 넣은 로컬 PostgreSQL 에 게시한 결과다.

    산출물 899,964행 → 적재 879,705행 (97.7%) · 대상 97,745 / 99,996 · **15.5초**

빠진 2,251개 대상은 **원천이 둘이라서** 생긴다. 대상 목록은 ecosyste.ms 다운로드 순위
(2026-09-02)이고 `package` 테이블은 deps.dev 스냅샷(2026-08-31)에서 온다. ecosyste.ms 에는
있는데 deps.dev 에 **적격 릴리스**(`is_release` 이고 배포일이 있는 버전)가 없는 패키지다 —
769개는 이름 자체가 없고 1,482개는 이름만 있다. 그 수를 따로 세어 **미매칭 수와 정확히
같음을 확인했다.**

그러므로 **97~98% 는 정상이고, 그보다 크게 낮으면 다른 원인을 찾아야 한다.** 이름 규칙이
어긋났거나 `package` 가 다른 회차이거나 비어 있는 경우다.

2026-09-18 운영에도 같은 회차를 게시했고 **일곱 열 × 세 구간이 로컬과 한 자리도 다르지
않았다.** 운영 `package` 가 11,062,172행으로 로컬보다 1.9만 적은데도 미매칭이 같은 2,251개인
것은, 그 차이가 대상 목록 밖 패키지이기 때문이다.

## 운영에 게시하기 — PC 에서 돌리고 서버의 psql 만 원격으로 쓴다

**서버에 들어가서 돌리는 길은 막혀 있다.** 2026-09-18 확인.

* app 노드에 `duckdb` 가 없다. 이 적재기가 parquet→CSV 변환에 쓴다 (`boto3` 는 있다)
* 배포가 올려 둔 저장소는 러너의 빌드 디렉터리 안이다 — `/srv/pickage/repo` 는
  `/home/gitlab-runner/builds/...` 로 가는 심볼릭 링크이고 그 부모가 `drwxr-x---` 라
  `ubuntu` 가 들어갈 수 없다. **권한을 고쳐서 뚫지 말 것** — 러너가 쓰는 경로다
* `postgres` 는 호스트에 포트를 열지 않는다. `docker exec` 경유만 가능한데,
  `--psql` 은 실행파일 경로 하나만 받아 `ssh … docker exec` 를 넣을 수 없다

그래서 **`DOCKER_HOST=ssh://` 를 쓴다.** 로컬 도커 CLI 가 원격 데몬을 보게 하는 것이라
`--docker-container` 경로를 그대로 쓸 수 있다. 인자가 셸이 아니라 **Docker API 의 argv
배열**로 가므로 원격 셸이 따옴표를 다시 쪼개는 문제가 없다 — manifest JSON 을 `-v` 로
넘기는 이 적재기에는 그 성질이 필요하다. 적재기 코드도 서버도 바꾸지 않는다.

`~/.ssh/config` 에 별칭을 둔다 (도커의 ssh 전송은 기본 키를 쓰므로 여기서 지정해야 한다).

    Host a506app
        HostName j15a506.p.ssafy.io
        User ubuntu
        IdentityFile ~/.ssh/J15A506T.pem
        IdentitiesOnly yes

**먼저 `--verify-only` 로 돌린다.** 게시 직전까지 전부 실행한 뒤 ROLLBACK 하므로 DB 를
바꾸지 않고 매칭률만 볼 수 있다. 그 수가 위 실측(97.7%)과 비슷하면 그때 게시한다.

PowerShell 에 **한 줄로** 넣는다. 줄을 나누려면 백틱이지 `^` 가 아니다 — 아래를 그대로
쓰는 편이 안전하다. 끝에 `--verify-only` 를 붙이면 검증만 하고 되돌린다.

    cd C:\\git\\S15P21A506; $env:DOCKER_HOST='ssh://a506app'; .\\.venv-bq\\Scripts\\python.exe -m pipeline.dependent_transitions.load --snapshot 2026-08-31 --run-id dependent-transitions-20260917-v1 --run-dir data/dependent_transitions_load/runs/2026-08-31_dependent-transitions-20260917-v1 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage

`$env:DOCKER_HOST` 는 그 창에서만 산다. 새 창에서는 다시 넣어야 하고, 빠뜨리면 로컬 도커를
보게 되어 `pickage-app-postgres-1` 을 못 찾는다.

`--run-dir` 로 이미 받아 둔 회차를 가리키면 MinIO 를 보지 않는다. 새 회차라면 그것을 빼고
`PICKAGE_MINIO_ENV` 를 준다. 전송 CSV 는 73 MB 이고 SSH 로 흘러간다.

⚠ **출력을 파일로 리다이렉트하지 말 것.** Windows 에서 인코딩이 cp949 로 정해져 한글 한
글자에 프로세스가 죽는다. `psql.log` 는 적재기가 UTF-8 로 따로 남긴다.

게시 뒤 확인할 것 — 행 수, `etl_dataset_current` 의 포인터, `etl_load_attempt` 의
`quality_report`. 구간별 합계를 로컬과 대조하면 가장 확실하다.

    DOCKER_HOST=ssh://a506app docker exec -i pickage-app-postgres-1 \\
      psql -U pickage -d pickage -c "SELECT period, count(*), sum(retained), sum(inflow), \\
        sum(inflow_new), sum(outflow), sum(unobserved), sum(unobserved_recent), \\
        sum(unobserved_stale), sum(unobserved_dormant) FROM dependent_transition GROUP BY period"

**분해를 적재하기 전에 V11 이 그 DB 에 가 있어야 한다** (S15P21A506-421). 마이그레이션이
없으면 INSERT 가 열 이름에서 막힌다. 배포와 재적재 사이에는 세 열이 NULL 인 88만 행이
남아 있고, 조회는 그때 "아직 모른다" 로 내려보낸다 — 0 으로 보이지 않는다.

게시 뒤 `quality_report.unobserved_freshness` 로 구간별 분포를 본다. **3y 의 recent 와 5y 의
recent·stale 은 0 이 정상이다** — 관측불가는 구간 안에 대표 릴리스가 없다는 뜻이라 그 칸이
정의상 빈다. 반대로 1y 의 세 칸이 모두 0 이 아니어야 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

try:  # Windows 콘솔 cp949 에서 한글 출력 보장
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
BUCKET = "pickage-curated"
PREFIX = "depsdev/v1/dependent-transitions"
DATASET = "dependent-transitions"
TABLE = "dependent_transition"
PARQUET = "data/dependent_transitions.parquet"
RUN_FILES = (PARQUET, "run_manifest.json")

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
# 구간 끝(t2)의 시각. 빌더의 T2 와 같은 값이어야 한다
# (pipeline/duckdb/build_dependent_transitions.py 의 T2 = "... 23:59:59").
SNAPSHOT_END_TIME = "23:59:59"
SNAPSHOT = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

# 이름에서 유도해 다른 데이터셋과 겹치지 않는다. similar_package 는 상수 5150211 을 쓰는데,
# 그 방식은 새 적재기를 만들 때마다 사람이 겹치지 않는 수를 골라야 한다.
# pipeline/postgresql/postgres.py 가 같은 방식(hashtextextended)을 쓴다.
LOCK_KEY = f"hashtextextended('curated:{DATASET}', 0)"

# 전량 교체가 남긴 dead tuple 정리. 트랜잭션 밖이어야 하고, 실패해도 적재는 유효하다.
VACUUM = f"""
\\set ON_ERROR_STOP off
VACUUM (ANALYZE) public."{TABLE}";
"""


def contract_sha256() -> str:
    """적재기 코드와 DB 마이그레이션을 하나의 해시로 묶는다. 둘 중 하나만 바뀌어도 값이 달라져
    etl 이력에서 "어떤 계약으로 적재했는지" 를 구분할 수 있다."""
    digest = hashlib.sha256()
    paths = sorted(p for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_"))
    paths += sorted((ROOT / "backend/src/main/resources/db/migration").glob("V*.sql"))
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def check_manifest(manifest: dict, snapshot: str, run_id: str) -> dict:
    """manifest 가 요청한 회차의 것인지 확인하고 parquet 항목을 돌려준다.

    경로만 믿지 않는다 — 객체를 손으로 옮겨 놓으면 경로와 내용이 어긋날 수 있다.
    """
    if manifest.get("dataset") != DATASET:
        raise SystemExit(f"manifest 의 dataset 이 다르다: {manifest.get('dataset')} (기대 {DATASET})")
    if manifest.get("snapshot") != snapshot:
        raise SystemExit(f"manifest 의 snapshot 이 다르다: {manifest.get('snapshot')} (기대 {snapshot})")
    if manifest.get("run_id") != run_id:
        raise SystemExit(f"manifest 의 run_id 가 다르다: {manifest.get('run_id')} (기대 {run_id})")

    entries = [f for f in manifest.get("files", []) if f.get("file") == PARQUET]
    if len(entries) != 1:
        raise SystemExit(f"manifest 에 {PARQUET} 항목이 {len(entries)} 개다 (1 개여야 한다)")
    entry = entries[0]
    for key in ("rows", "sha256", "bytes"):
        if not entry.get(key):
            raise SystemExit(f"manifest 의 {PARQUET} 항목에 {key} 가 없다")
    return entry


def check_parquet(path: Path, entry: dict) -> None:
    """받아 온 파일이 manifest 가 말한 그 파일인지 확인한다."""
    size = path.stat().st_size
    if size != entry["bytes"]:
        raise SystemExit(f"크기가 manifest 와 다르다: {size} vs {entry['bytes']}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != entry["sha256"]:
        raise SystemExit(f"SHA-256 이 manifest 와 다르다: {digest.hexdigest()} vs {entry['sha256']}")


def pull_run(s3, snapshot: str, run_id: str, target: Path) -> Path:
    """완료 마커가 있는 실행만 받는다."""
    from pipeline.minio.ingest_raw import exists

    prefix = f"{PREFIX}/snapshot={snapshot}/run_id={run_id}"
    if not exists(s3, BUCKET, f"{prefix}/_SUCCESS"):
        raise SystemExit(f"완료 마커가 없다: s3://{BUCKET}/{prefix}/_SUCCESS\n"
                         "입고가 끝나지 않았거나 회차 이름이 틀렸다")
    target.mkdir(parents=True, exist_ok=True)
    for name in RUN_FILES:
        key = f"{prefix}/{name}"
        if not exists(s3, BUCKET, key):
            raise SystemExit(f"필수 객체가 없다: s3://{BUCKET}/{key}")
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        s3.download_file(BUCKET, key, str(temporary))
        temporary.replace(path)  # 중간에 끊긴 파일을 완성본으로 오인하지 않게 한다
        print(f"  ↓ {name}  ({path.stat().st_size / 1e6:.1f} MB)", flush=True)
    return target


def write_transport(parquet: Path, target: Path) -> int:
    """parquet 을 psql COPY 용 CSV 로 옮기고 행 수를 돌려준다.

    이스케이프·따옴표를 손으로 만들지 않고 DuckDB 에 맡긴다. 패키지 이름에 탭이나 따옴표가
    들어갈 일은 없지만, 직접 짜 넣으면 그 가정이 깨지는 날 조용히 깨진다.
    열 순서가 아래 COPY 문의 열 목록과 같아야 한다.
    """
    import duckdb

    con = duckdb.connect()
    con.execute(f"""COPY (
        SELECT target, period, kind, retained, inflow, inflow_new, outflow, unobserved,
               unobserved_recent, unobserved_stale, unobserved_dormant, t1, t2
        FROM read_parquet('{parquet.as_posix()}')
        ORDER BY period, target, kind)
        TO '{target.as_posix()}' (FORMAT CSV, HEADER false)""")
    rows = con.execute(
        f"SELECT count(*) FROM read_parquet('{parquet.as_posix()}')").fetchone()[0]
    con.close()
    if rows == 0:
        raise SystemExit("parquet 이 비어 있다")
    return rows


def build_sql(verify_only: bool) -> tuple[str, str]:
    """psql 스크립트를 CSV 삽입 지점 앞뒤로 나눠 돌려준다."""
    head = f"""
\\set ON_ERROR_STOP on
BEGIN;

-- 동시 적재 차단 (트랜잭션 종료 시 자동 해제)
SELECT pg_advisory_xact_lock({LOCK_KEY});

CREATE TEMP TABLE stage_transition (
    target             text      NOT NULL,
    period             text      NOT NULL,
    kind               text      NOT NULL,
    retained           integer   NOT NULL,
    inflow             integer   NOT NULL,
    inflow_new         integer   NOT NULL,
    outflow            integer   NOT NULL,
    unobserved         integer   NOT NULL,
    -- 관측불가 분해는 산출물에 **반드시 있다**(S15P21A506-421). 여기서 NOT NULL 로 받아,
    -- 분해 없는 옛 회차를 이 적재기로 올리면 COPY 에서 바로 멈추게 한다. 본 표의 세 열이
    -- nullable 인 것은 배포~재적재 사이의 창 때문이고, 적재되는 회차에는 해당하지 않는다.
    unobserved_recent  integer   NOT NULL,
    unobserved_stale   integer   NOT NULL,
    unobserved_dormant integer   NOT NULL,
    t1                 timestamp NOT NULL,
    t2                 timestamp NOT NULL
) ON COMMIT DROP;

COPY stage_transition (target, period, kind, retained, inflow, inflow_new, outflow, unobserved,
                       unobserved_recent, unobserved_stale, unobserved_dormant, t1, t2)
FROM STDIN WITH (FORMAT csv, ENCODING 'UTF8');
"""
    tail = f"""

-- 이름 → package_id. package 에 없는 이름은 붙일 수 없어 빠진다 (아래 quality 로 보고).
CREATE TEMP TABLE resolved ON COMMIT DROP AS
SELECT p.package_id, s.period, s.kind,
       s.retained, s.inflow, s.inflow_new, s.outflow, s.unobserved,
       s.unobserved_recent, s.unobserved_stale, s.unobserved_dormant, s.t1, s.t2
  FROM stage_transition s
  JOIN "package" p ON p."name" = s.target;

CREATE TEMP TABLE quality ON COMMIT DROP AS
SELECT (SELECT count(*)                  FROM stage_transition)            AS staged_rows,
       (SELECT count(DISTINCT target)    FROM stage_transition)            AS staged_targets,
       (SELECT count(*)                  FROM resolved)                    AS loaded_rows,
       (SELECT count(DISTINCT package_id) FROM resolved)                   AS loaded_targets,
       (SELECT count(DISTINCT s.target)  FROM stage_transition s
          LEFT JOIN "package" p ON p."name" = s.target
         WHERE p.package_id IS NULL)                                       AS unresolved_targets,
       -- 구간별 관측불가 신선도 분포 (S15P21A506-421). 행 수만 보면 분해가 통째로 0 이어도
       -- 정상으로 보인다 — 게시 직후 눈으로 확인할 수 있게 여기 남긴다. 3y 의 recent 와
       -- 5y 의 recent·stale 은 **0 이 정상**이다(정의상 비는 칸, V11 의 PERIOD 제약).
       (SELECT jsonb_object_agg(f.period, jsonb_build_object(
                   'unobserved', f.unobserved, 'recent', f.recent,
                   'stale', f.stale, 'dormant', f.dormant))
          FROM (SELECT period, sum(unobserved) AS unobserved,
                       sum(unobserved_recent)  AS recent,
                       sum(unobserved_stale)   AS stale,
                       sum(unobserved_dormant) AS dormant
                  FROM resolved GROUP BY period) f)                        AS unobserved_freshness;

-- 한 건도 못 붙으면 중단. 이름 규칙이 어긋났거나 package 가 비어 있다는 뜻이다.
DO $$ BEGIN
  IF (SELECT loaded_rows FROM quality) = 0 THEN
    RAISE EXCEPTION 'package 테이블과 이름이 하나도 맞지 않는다 — 적재 대상 DB 를 확인할 것';
  END IF;
END $$;

-- 실행 이력 등록
INSERT INTO public.etl_load_execution
    (execution_id, dataset, status, snapshot_at, snapshot_timestamp, curated_run_id, run_prefix,
     manifest_sha256, contract_sha256, input_metadata, expected_counts, active_attempt_id)
VALUES (:'execution_id', '{DATASET}', 'PREPARING', :'snapshot_at', :'snapshot_timestamp',
        :'curated_run_id', :'run_prefix', :'manifest_sha256', :'contract_sha256',
        :'manifest'::jsonb, :'expected_counts'::jsonb, :'attempt_id')
-- snapshot_at·snapshot_timestamp 도 함께 갱신한다. 같은 execution_id 면 값이 같으므로
-- 평소에는 무해하고, 적재기가 시각 계약을 고쳤을 때(2026-09-17 t2 기준으로 정정) 재적재로
-- 반영된다. 빼 두면 첫 실행의 값이 굳어 코드와 DB 가 조용히 어긋난다.
ON CONFLICT (execution_id) DO UPDATE
   SET status='PREPARING', active_attempt_id=EXCLUDED.active_attempt_id,
       snapshot_at=EXCLUDED.snapshot_at, snapshot_timestamp=EXCLUDED.snapshot_timestamp,
       manifest_sha256=EXCLUDED.manifest_sha256, contract_sha256=EXCLUDED.contract_sha256,
       input_metadata=EXCLUDED.input_metadata, expected_counts=EXCLUDED.expected_counts,
       error_message=NULL, updated_at=clock_timestamp();

INSERT INTO public.etl_load_attempt
    (attempt_id, execution_id, status, phase, validation_contract_sha256)
VALUES (:'attempt_id', :'execution_id', 'PREPARING', 'VALIDATE_INPUT', :'contract_sha256');

-- 전량 교체. 한 회차가 표 전체를 대신하므로 부분 갱신이 없다 — 섞이면 구간마다 기준일이
-- 어긋난다.
--
-- **TRUNCATE 가 아니라 DELETE 다.** TRUNCATE 가 90만 행에서 더 빠르지만 ACCESS EXCLUSIVE
-- 락을 잡고 트랜잭션 끝까지 유지해, 적재가 도는 내내(실측 15.5초) 이 표의 모든 조회가
-- 멈춰 선다. DELETE 는 SHARE ROW EXCLUSIVE 에서 끝나 MVCC 로 조회가 그대로 나간다.
-- advisory lock 은 적재끼리만 막을 뿐 조회는 모른다. 몇 초 느린 것보다 API 가 안 멈추는
-- 쪽이 낫다 — similar_package/load.py 가 같은 전량 교체를 DELETE 로 하는 이유다.
-- 남는 dead tuple 은 아래 VACUUM 이 정리한다.
LOCK TABLE public."{TABLE}", public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM public."{TABLE}";
INSERT INTO public."{TABLE}"
    (package_id, period, kind, retained, inflow, inflow_new, outflow, unobserved,
     unobserved_recent, unobserved_stale, unobserved_dormant, t1, t2)
SELECT package_id, period, kind, retained, inflow, inflow_new, outflow, unobserved,
       unobserved_recent, unobserved_stale, unobserved_dormant, t1, t2
  FROM resolved;

UPDATE public.etl_load_attempt
   SET status='PUBLISHED', phase='COMMIT', completed_at=clock_timestamp(),
       actual_counts=jsonb_build_object('{TABLE}', (SELECT loaded_rows FROM quality)),
       quality_report=(SELECT to_jsonb(q) FROM quality q)
 WHERE attempt_id=:'attempt_id';

UPDATE public.etl_load_execution
   SET status='PUBLISHED', updated_at=clock_timestamp(), error_message=NULL,
       actual_counts=jsonb_build_object('{TABLE}', (SELECT loaded_rows FROM quality))
 WHERE execution_id=:'execution_id' AND active_attempt_id=:'attempt_id';

-- 현재 게시된 실행을 가리키는 포인터 갱신
INSERT INTO public.etl_dataset_current (dataset, execution_id, snapshot_at, manifest_sha256, manifest)
VALUES ('{DATASET}', :'execution_id', :'snapshot_at', :'manifest_sha256', :'manifest'::jsonb)
ON CONFLICT (dataset) DO UPDATE
   SET execution_id=EXCLUDED.execution_id, snapshot_at=EXCLUDED.snapshot_at,
       manifest_sha256=EXCLUDED.manifest_sha256, manifest=EXCLUDED.manifest,
       published_at=clock_timestamp();

SELECT to_jsonb(q) FROM quality q;

{"ROLLBACK;" if verify_only else "COMMIT;"}
{VACUUM if not verify_only else ""}"""
    return head, tail


def psql_command(args) -> list[str]:
    if not SAFE_ID.fullmatch(args.database) or not SAFE_ID.fullmatch(args.db_user):
        raise SystemExit("database·user 는 단순 이름만 쓴다. 인증은 libpq 환경변수로 준다")
    if args.docker_container:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.docker_container):
            raise SystemExit("컨테이너 이름이 올바르지 않다")
        command = ["docker", "exec", "-i", args.docker_container, "psql"]
    else:
        command = [args.psql]
    return command + ["-U", args.db_user, "-d", args.database]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="원천 스냅샷 날짜 (2026-08-31)")
    parser.add_argument("--run-id", required=True,
                        help="입고 회차 (dependent-transitions-20260917-v1)")
    parser.add_argument("--run-dir", type=Path, help="이미 받아 둔 디렉터리. 주면 MinIO 를 안 본다")
    parser.add_argument("--execution-id", help="이 게시의 식별자. 재실행 시 같은 값을 준다")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/dependent_transitions_load")
    parser.add_argument("--verify-only", action="store_true",
                        help="게시 직전까지 전부 실행한 뒤 ROLLBACK. DB 는 그대로 둔다")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--docker-container", help="PostgreSQL 컨테이너 이름")
    target.add_argument("--psql", help="psql 실행 파일 경로")
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-user", default="postgres")
    args = parser.parse_args(argv)

    if not SNAPSHOT.fullmatch(args.snapshot):
        parser.error("--snapshot 은 YYYY-MM-DD 형태여야 한다")
    if not SAFE_ID.fullmatch(args.run_id):
        parser.error("--run-id 는 영문·숫자·밑줄·하이픈 1~200자")
    args.execution_id = args.execution_id or f"{DATASET}-{args.snapshot}-{args.run_id}"
    if not SAFE_ID.fullmatch(args.execution_id):
        parser.error("--execution-id 는 영문·숫자·밑줄·하이픈 1~200자")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    attempt_id = uuid.uuid4().hex
    prefix = f"{PREFIX}/snapshot={args.snapshot}/run_id={args.run_id}"

    if args.run_dir:
        run_dir = args.run_dir.resolve()
    else:
        from pipeline.minio.ingest_raw import client
        run_dir = (args.work_dir / "runs" / f"{args.snapshot}_{args.run_id}").resolve()
        print(f"산출물 받기: s3://{BUCKET}/{prefix}/", flush=True)
        pull_run(client(), args.snapshot, args.run_id, run_dir)

    manifest_path = run_dir / "run_manifest.json"
    parquet = run_dir / PARQUET
    for path in (manifest_path, parquet):
        if not path.exists():
            raise SystemExit(f"필수 파일이 없다: {path}")

    body = manifest_path.read_bytes()
    manifest = json.loads(body)
    entry = check_manifest(manifest, args.snapshot, args.run_id)
    check_parquet(parquet, entry)
    print(f"manifest 대조 통과: {entry['rows']:,}행 · {entry['sha256'][:12]}…", flush=True)

    work = (args.work_dir / args.execution_id / attempt_id).resolve()
    work.mkdir(parents=True, exist_ok=False)
    transport = work / "transitions.copy.csv"
    staged = write_transport(parquet, transport)
    if staged != entry["rows"]:
        raise SystemExit(f"manifest 의 행 수와 실제가 다르다: {entry['rows']} vs {staged}")
    print(f"전송 파일 준비: {staged:,}행 ({transport.name})", flush=True)

    # psql 이 docker exec 로 컨테이너 안에서 돌 수 있다. 그쪽에서는 호스트 경로를 못 보므로
    # 스크립트와 COPY 데이터를 모두 표준입력으로 흘려보낸다.
    head, tail = build_sql(args.verify_only)
    script = work / "publish.sql"
    with script.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(head)
        with transport.open("r", encoding="utf-8") as data:
            for chunk in iter(lambda: data.read(1 << 20), ""):
                stream.write(chunk)
        stream.write("\\.\n")
        stream.write(tail)

    command = psql_command(args) + [
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-q",
        "-v", f"execution_id={args.execution_id}",
        "-v", f"attempt_id={attempt_id}",
        "-v", f"snapshot_at={args.snapshot}",
        # 이 데이터셋의 시각 기준은 구간 끝(t2)이고 그것이 곧 스냅샷 날짜다. 표의 t2 와
        # **같은 값**을 쓴다 — 00:00:00 을 넣으면 그날 자정부터 23:59:59 까지의 발행분이
        # 들어 있는데도 시점을 하루치 적게 잡아, 다른 데이터셋과 대조할 때 경계가 어긋난다.
        "-v", f"snapshot_timestamp={args.snapshot}T{SNAPSHOT_END_TIME}",
        "-v", f"curated_run_id={args.run_id}",
        "-v", f"run_prefix={prefix}",
        "-v", f"manifest_sha256={hashlib.sha256(body).hexdigest()}",
        "-v", f"contract_sha256={contract_sha256()}",
        "-v", "manifest=" + json.dumps(manifest, ensure_ascii=False),
        "-v", "expected_counts=" + json.dumps({TABLE: staged}),
    ]
    with script.open("rb") as stream:
        completed = subprocess.run(command, stdin=stream, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
    log = work / "psql.log"
    log.write_text((completed.stdout or "") + "\n---- stderr ----\n" + (completed.stderr or ""),
                   encoding="utf-8")
    if completed.returncode != 0:
        print(f"게시 실패 — {log}", flush=True)
        print((completed.stderr or "").strip()[-2000:], flush=True)
        return 1

    lines = [line for line in (completed.stdout or "").splitlines() if line.strip().startswith("{")]
    quality = json.loads(lines[-1]) if lines else {}
    report = {"execution_id": args.execution_id, "attempt_id": attempt_id,
              "mode": "VERIFY_ONLY" if args.verify_only else "PUBLISH",
              "snapshot": args.snapshot, "run_id": args.run_id, "quality": quality}
    (work / "execution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    if quality:
        lost = quality["staged_rows"] - quality["loaded_rows"]
        if lost:
            share = lost / quality["staged_rows"] * 100
            print(f"경고: {lost:,}행({share:.1f}%)이 이름 매칭에 실패해 빠졌다 — "
                  f"package 에 없는 대상 {quality['unresolved_targets']:,}개", flush=True)
    print(("검증만 하고 되돌렸다" if args.verify_only else "게시 완료") + f" — {work}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
