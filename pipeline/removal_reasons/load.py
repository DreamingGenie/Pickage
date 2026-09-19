"""구간별 이탈 사유를 MinIO 회차에서 받아 PostgreSQL 에 게시한다 (S15P21A506-396).

입력  s3://pickage-curated/depsdev/v1/migration-pairs/
      snapshot={snapshot}/run_id={run_id}/data/removal_by_period.parquet
출력  public.dependent_removal_reason (전량 교체) + etl_* 이력

    .venv-bq/Scripts/python.exe -m pipeline.removal_reasons.load \\
      --snapshot 2026-08-31 --run-id migration-pairs-20260918-v1 \\
      --docker-container pickage-app-postgres-1 --database pickage --db-user pickage \\
      --verify-only

## 왜 별도 적재기인가

산출물은 migration-pairs 회차 안에 있지만 **적재 단위는 따로다.** 한 빌더 실행이 이동쌍과
이탈 사유를 함께 내는데, DB 로 가는 것은 이탈 사유뿐이다. etl 이력·advisory lock·
_current 포인터를 migration-pairs 와 공유하면 "무엇이 게시됐는가" 가 흐려진다.

그래서 이름이 둘이다.

    SOURCE_DATASET = 'migration-pairs'   회차 manifest 가 자기를 부르는 이름
    DATASET        = 'removal-reasons'   이 적재기가 etl 표에 남기는 이름

## 범위와 t1·t2 를 dependent_transition 에서 가져온다 (이 적재기의 핵심)

원천 parquet 은 X 13.2만 종 27.4만 행을 담지만 **그대로 넣지 않는다.**

화면은 유지·유입·이탈 패널과 이탈 사유 패널을 나란히 띄운다. 두 패널의 대상 범위가
다르면 같은 패키지에서 한쪽은 숫자를, 다른 쪽은 "범위 밖"을 말한다 — 2026-09-18
@opentiny/vue-theme-mobile 로 실제로 확인했다(이탈 사유 601건, 유지·유입·이탈
OUT_OF_SCOPE). 그래서 dependent_transition 에 있는 대상만 넣는다.

**그 목록을 여기에 복사해 두지 않는다.** 조인으로 얻는다. 목록을 들고 있으면 한쪽만
다시 적재했을 때 커버리지가 조용히 어긋난다.

t1·t2 도 같은 곳에서 온다. 원천 parquet 에 두 열이 없는데, 여기에 날짜를 다시 적으면
다음 스냅샷에서 한쪽만 고쳐지고 두 지표가 서로 다른 구간을 같은 이름(3y)으로 부르게
된다. 그 어긋남은 검산에 걸리지 않는다 — 각자 내부적으로는 앞뒤가 맞기 때문이다.
**이 에픽에서 같은 종류를 이미 두 번 고쳤다**(T1 드리프트 · 스냅샷 파티션 드리프트).

따라서 **dependent_transition 을 먼저 적재해야 한다.** 비어 있으면 중단한다.

## 여기서는 "빠진 행" 이 경고가 아니다

dependent_transitions/load.py 는 빠진 행이 곧 문제였다 — 그쪽은 적재 대상 목록과 산출물의
대상이 같아서, 안 붙는 이름은 이름 규칙이 어긋났다는 뜻이었다. 여기서는 다르다.

2026-09-18 로컬 실측(패키지 1,108만 · 전이 87.9만)에서 27.4만 행이 이렇게 갈렸다.

    범위 밖   이름은 package 에 있는데 대상이 아니다     138,559행 (50.6%)
    미해결    이름이 package 에 아예 없다                 37,198행 (17,433종)
    적재                                                  97,853행 (42,382종)

**미해결도 경고가 아니다.** dependent_transition 은 package 를 FK 로 참조하므로, package 에
없는 이름은 범위 안에 있을 수가 없다 — 이름이 붙었더라도 어차피 범위 밖에서 빠졌을 행이다.
즉 조치할 수 있는 항목이 아니다. 처음에는 저쪽 적재기를 그대로 본떠 경고로 냈는데, 실제로
돌려 보니 매 실행이 경고가 되어 그만뒀다.

그래서 이 적재기가 실제로 끊는 자리는 둘뿐이다.

    dependent_transition 이 비어 있다   → 범위가 없다. 순서가 틀렸다
    적재 행이 0 이다                     → 대상 DB 가 다르다

나머지는 숫자로만 남긴다. 대신 **범위를 얼마나 덮었는지**(scope_targets 대비)를 함께 내어,
회차끼리 비교할 수 있게 한다.

## 운영에 게시하기

dependent_transitions/load.py 의 "운영에 게시하기" 절이 그대로 적용된다 — app 노드에
duckdb 가 없고, 배포가 올려 둔 저장소는 러너 빌드 디렉터리 안이라 읽을 수 없으며,
postgres 가 호스트에 포트를 열지 않는다. PC 에서 돌리고 서버의 psql 만 원격으로 쓴다.

    $env:DOCKER_HOST='ssh://a506app'

--verify-only 를 먼저 돌려 매칭률을 확인한 뒤 게시한다.
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
PREFIX = "depsdev/v1/migration-pairs"
# manifest 가 자기를 부르는 이름과 etl 이력에 남기는 이름이 다르다 (모듈 docstring 참고).
SOURCE_DATASET = "migration-pairs"
DATASET = "removal-reasons"
TABLE = "dependent_removal_reason"
SCOPE_TABLE = "dependent_transition"
# 회차 안은 평평하다 — ingest_derived.py 가 key = prefix + '/data/' + 파일명 으로 올린다.
# 로컬 경로(data/migration_pairs/…)를 그대로 적으면 받아 오지 못한다.
PARQUET = "data/removal_by_period.parquet"
RUN_FILES = (PARQUET, "run_manifest.json")

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
# 이 데이터셋의 시각 기준은 구간 끝(t2)이고 그것이 곧 스냅샷 날짜다.
# dependent_transitions/load.py 와 같은 값이어야 한다 — 두 표의 t2 가 같은 시각이다.
SNAPSHOT_END_TIME = "23:59:59"
SNAPSHOT = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

LOCK_KEY = f"hashtextextended('curated:{DATASET}', 0)"

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
    if manifest.get("dataset") != SOURCE_DATASET:
        raise SystemExit(
            f"manifest 의 dataset 이 다르다: {manifest.get('dataset')} (기대 {SOURCE_DATASET})")
    if manifest.get("snapshot") != snapshot:
        raise SystemExit(f"manifest 의 snapshot 이 다르다: {manifest.get('snapshot')} (기대 {snapshot})")
    if manifest.get("run_id") != run_id:
        raise SystemExit(f"manifest 의 run_id 가 다르다: {manifest.get('run_id')} (기대 {run_id})")

    # 이 회차 manifest 에는 이동쌍 산출물도 함께 들어 있다. 그중 우리 것 하나만 고른다.
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

    t1·t2 는 싣지 않는다 — 원천에 없고, DB 쪽에서 dependent_transition 을 조인해 얻는다.
    """
    import duckdb

    con = duckdb.connect()
    con.execute(f"""COPY (
        SELECT removed_pkg AS target, period,
               removals, removals_no_replacement, removals_with_replacement, dependents
        FROM read_parquet('{parquet.as_posix()}')
        ORDER BY period, removed_pkg)
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

-- 범위와 기준일을 여기서 얻는다. 비어 있으면 전부 범위 밖이 되어 0 행이 적재되므로,
-- 그 상태를 "이름이 안 맞는다" 로 오해하지 않게 먼저 끊는다.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM public."{SCOPE_TABLE}" LIMIT 1) THEN
    RAISE EXCEPTION '{SCOPE_TABLE} 이 비어 있다 — 유지·유입·이탈을 먼저 적재할 것 '
                    '(pipeline.dependent_transitions.load). 이 표가 적재 범위와 t1·t2 를 정한다';
  END IF;
END $$;

CREATE TEMP TABLE stage_removal (
    target           text    NOT NULL,
    period           text    NOT NULL,
    removals         integer NOT NULL,
    no_replacement   integer NOT NULL,
    with_replacement integer NOT NULL,
    dependents       integer NOT NULL
) ON COMMIT DROP;

COPY stage_removal (target, period, removals, no_replacement, with_replacement, dependents)
FROM STDIN WITH (FORMAT csv, ENCODING 'UTF8');
"""
    tail = f"""

-- 구간별 기준일. (package_id, period) 당 한 행이어야 조인이 행을 부풀리지 않는다.
-- {SCOPE_TABLE} 의 PK 는 (package_id, period, kind) 라 kind 만큼 행이 있고 t1·t2 는
-- period 로 정해지는 상수다. GROUP BY 로 접어 **구조적으로** 한 행을 보장한다 —
-- DISTINCT 로 접으면 t1 이 어쩌다 갈렸을 때 조인이 조용히 두 배가 된다.
CREATE TEMP TABLE scope ON COMMIT DROP AS
SELECT package_id, period, min(t1) AS t1, min(t2) AS t2,
       count(DISTINCT t1) AS t1_variants, count(DISTINCT t2) AS t2_variants
  FROM public."{SCOPE_TABLE}"
 GROUP BY package_id, period;

-- 같은 (대상, 구간)에 기준일이 둘이면 유지·유입·이탈 쪽이 이미 섞인 것이다.
-- 그걸 이 표로 옮기지 않는다.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM scope WHERE t1_variants > 1 OR t2_variants > 1) THEN
    RAISE EXCEPTION '{SCOPE_TABLE} 의 한 (package_id, period) 에 기준일이 여럿이다 — '
                    '그쪽 적재가 여러 회차를 섞었다';
  END IF;
END $$;

-- 이름 → package_id → 범위·기준일. 조인을 둘로 나눈 것은 아래 quality 에서
-- **이름이 없어서 빠진 것**과 **범위 밖이라 빠진 것**을 갈라 세기 위해서다.
CREATE TEMP TABLE named ON COMMIT DROP AS
SELECT p.package_id, s.target, s.period,
       s.removals, s.no_replacement, s.with_replacement, s.dependents
  FROM stage_removal s
  JOIN "package" p ON p."name" = s.target;

CREATE TEMP TABLE resolved ON COMMIT DROP AS
SELECT n.package_id, n.period, n.removals, n.no_replacement, n.with_replacement, n.dependents,
       c.t1, c.t2
  FROM named n
  JOIN scope c ON c.package_id = n.package_id AND c.period = n.period;

CREATE TEMP TABLE quality ON COMMIT DROP AS
SELECT (SELECT count(*)                   FROM stage_removal)  AS staged_rows,
       (SELECT count(DISTINCT target)     FROM stage_removal)  AS staged_targets,
       (SELECT count(*)                   FROM named)          AS named_rows,
       (SELECT count(DISTINCT target)     FROM named)          AS named_targets,
       (SELECT count(*)                   FROM resolved)       AS loaded_rows,
       (SELECT count(DISTINCT package_id) FROM resolved)       AS loaded_targets,
       -- 이름이 package 에 아예 없다. package 를 FK 로 참조하는 {SCOPE_TABLE} 에도 있을 수
       -- 없으므로 **이 행들은 어차피 범위 밖이다** — 경고가 아니라 원천과 DB 의 이름
       -- 겹침을 보는 수치다.
       (SELECT count(DISTINCT s.target)   FROM stage_removal s
          LEFT JOIN "package" p ON p."name" = s.target
         WHERE p.package_id IS NULL)                           AS unresolved_targets,
       -- 범위 자체의 크기. 적재가 그중 얼마를 덮었는지 보려면 이 수가 있어야 한다.
       -- 나머지는 "한 번도 안 빠진 대상" 이라 정상이다.
       (SELECT count(DISTINCT package_id) FROM scope)          AS scope_targets,
       -- 이름은 있는데 유지·유입·이탈 대상이 아니다. 설계대로 빠지는 쪽이다
       (SELECT count(*)                   FROM named)
         - (SELECT count(*)               FROM resolved)       AS out_of_scope_rows,
       (SELECT count(DISTINCT n.target)   FROM named n
         WHERE NOT EXISTS (SELECT 1 FROM scope c WHERE c.package_id = n.package_id))
                                                               AS out_of_scope_targets;

-- 한 건도 못 붙으면 중단. 이름 규칙이 어긋났거나 대상 DB 가 다르다는 뜻이다
-- (범위가 비어서 0 이 되는 경우는 위에서 이미 걸렀다).
DO $$ BEGIN
  IF (SELECT loaded_rows FROM quality) = 0 THEN
    RAISE EXCEPTION 'package·{SCOPE_TABLE} 과 하나도 맞지 않는다 — 적재 대상 DB 를 확인할 것';
  END IF;
END $$;

-- 실행 이력 등록
INSERT INTO public.etl_load_execution
    (execution_id, dataset, status, snapshot_at, snapshot_timestamp, curated_run_id, run_prefix,
     manifest_sha256, contract_sha256, input_metadata, expected_counts, active_attempt_id)
VALUES (:'execution_id', '{DATASET}', 'PREPARING', :'snapshot_at', :'snapshot_timestamp',
        :'curated_run_id', :'run_prefix', :'manifest_sha256', :'contract_sha256',
        :'manifest'::jsonb, :'expected_counts'::jsonb, :'attempt_id')
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
-- 어긋난다. TRUNCATE 가 아니라 DELETE 인 이유는 dependent_transitions/load.py 와 같다:
-- TRUNCATE 는 ACCESS EXCLUSIVE 락을 트랜잭션 끝까지 잡아 적재가 도는 내내 이 표의 조회가
-- 멈춰 선다. DELETE 는 SHARE ROW EXCLUSIVE 에서 끝나 MVCC 로 조회가 그대로 나간다.
LOCK TABLE public."{TABLE}", public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM public."{TABLE}";
INSERT INTO public."{TABLE}"
    (package_id, period, removals, no_replacement, with_replacement, dependents, t1, t2)
SELECT package_id, period, removals, no_replacement, with_replacement, dependents, t1, t2
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
                        help="입고 회차 (migration-pairs-20260918-v1)")
    parser.add_argument("--run-dir", type=Path, help="이미 받아 둔 디렉터리. 주면 MinIO 를 안 본다")
    parser.add_argument("--execution-id", help="이 게시의 식별자. 재실행 시 같은 값을 준다")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/removal_reasons_load")
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


def report_quality(quality: dict) -> None:
    """무엇이 얼마나 걸러졌는지 한눈에 보이게 낸다. **경고를 붙이지 않는다.**

    빠진 행은 두 종류인데 둘 다 조치할 수 있는 항목이 아니다 — 범위 밖은 설계대로 빠지는
    쪽이고, 이름 미해결은 {SCOPE_TABLE} 이 package 를 FK 로 참조하는 이상 어차피 범위
    밖이다. 경고로 내면 매 실행이 경고가 되어 아무도 읽지 않게 된다. 실제로 끊어야 할
    상황은 SQL 쪽에서 예외로 막는다.

    대신 **범위를 얼마나 덮었는지**를 낸다. 회차끼리 비교해 커버리지가 갑자기 줄면
    한쪽 적재가 어긋난 것이다.
    """
    if not quality:
        return
    staged = quality["staged_rows"]
    print(f"  원천        {staged:>9,}행 · 대상 {quality['staged_targets']:,}종", flush=True)
    print(f"  범위 밖    -{quality['out_of_scope_rows']:>9,}행 · 대상 "
          f"{quality['out_of_scope_targets']:,}종 ({SCOPE_TABLE} 대상이 아니다)", flush=True)
    print(f"  이름 없음  -{staged - quality['named_rows']:>9,}행 · 대상 "
          f"{quality['unresolved_targets']:,}종 (package 에 없다 = 어차피 범위 밖)", flush=True)
    print(f"  적재        {quality['loaded_rows']:>9,}행 · 대상 "
          f"{quality['loaded_targets']:,}종", flush=True)
    scope_targets = quality.get("scope_targets") or 0
    if scope_targets:
        share = quality["loaded_targets"] / scope_targets * 100
        print(f"  범위 커버리지 {quality['loaded_targets']:,} / {scope_targets:,} "
              f"({share:.1f}%) — 나머지는 한 번도 안 빠진 대상이다", flush=True)


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
    transport = work / "removal_reasons.copy.csv"
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
    report_quality(quality)
    print(("검증만 하고 되돌렸다" if args.verify_only else "게시 완료") + f" — {work}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
