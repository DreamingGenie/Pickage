"""버전별 소비 조건 회차를 PostgreSQL `package_env` 에 원자 게시한다 (기능-11-R01).

입력은 `pipeline/minio/ingest_derived.py` 가 Curated 에 올린 완료 실행이다.

    pickage-curated/npm-registry/v1/package-env/
      collected_date={날짜}/run_id={회차}/
        run_manifest.json
        data/package_env.parquet

    PICKAGE_MINIO_ENV=.env.server python -m pipeline.package_env.load \\
      --collected-date 2026-09-16 --run-id package-env-20260916-v1 \\
      --docker-container pickage-local-postgres-1 --database pickage --verify-only

**`_current.json` 을 따라가지 않는다.** 어떤 회차를 게시하는지 사람이 명시한다 —
`pipeline/dependent_transitions/load.py` 가 같은 이유로 같은 규칙을 쓴다. 여기서는 그 이유가
더 구체적이다. 형태 6열은 09-16 수집분부터 들어갔고, 그 전 회차로 만든 산출물은 전 행이
같은 값이 된다. 최신을 자동으로 집었으면 그런 표를 게시하고도 아무도 몰랐을 것이다.

## 흐름은 dependent_transitions 와 같다

advisory lock → staging → 이름 해석 → 전량 교체 → etl 이력. 표 이름과 열 목록만 다르다.
전량 교체를 TRUNCATE 가 아니라 DELETE 로 하는 것도 같다 — 이유는 아래 SQL 주석에 있다.

## 이름 해석이 두 단계다

`dependent_transition` 은 `package` 에 이름만 붙이면 됐지만, 이 표의 FK 는
`version (package_id, version)` 이라 **버전까지 있어야** 붙는다. 그래서 못 붙는 경우가 둘이다.

  - 이름이 `package` 에 없다
  - 이름은 있는데 그 버전이 `version` 에 없다

둘째가 이 데이터셋에서 압도적으로 크다. **원천이 둘이기 때문이다** — `version` 은 deps.dev
스냅샷(2026-08-31)에서 오고 이 산출물은 registry 수집(2026-09-16)에서 온다. registry 는 한
패키지의 **전 버전**을 담고 `version` 은 스냅샷이 알던 것만 담아서, 겹치지 않는 쪽이 절반을
넘는다. 2026-09-16 회차 실측으로 2,156만 행 중 782만 행만 붙었다(36.3%).

**그 손실을 적재 실패로 읽으면 안 된다.** 붙지 못한 행은 `version` 에 없는 버전이고, 그
버전은 화면의 드롭다운(기능-10-R02)에 뜨지도 않는다 — 아무도 고를 수 없는 행이다. 그래서
품질 지표는 staged 대비가 아니라 **`version` 이 제공하는 버전 대비**로 본다. 같은 회차의
실측이 그 기준으로 100.0% 다.

그리고 못 붙은 이유 둘을 따로 세어 quality 에 남긴다. 합쳐 세면 "이름 규칙이 어긋났다" 와
"스냅샷이 오래됐다" 를 구분할 수 없고, 둘은 할 일이 다르다 — 앞은 고쳐야 하고 뒤는 정상이다.
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
PREFIX = "npm-registry/v1/package-env"
DATASET = "package-env"
TABLE = "package_env"
PARQUET = "data/package_env.parquet"
RUN_FILES = (PARQUET, "run_manifest.json")

# 이 데이터셋의 파티션 키. deps.dev 스냅샷이 아니라 registry 수집 실행 날짜다.
PARTITION = "collected_date"

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

# 이름에서 유도해 다른 데이터셋과 겹치지 않는다.
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


def check_manifest(manifest: dict, collected_date: str, run_id: str) -> dict:
    """manifest 가 요청한 회차의 것인지 확인하고 parquet 항목을 돌려준다.

    경로만 믿지 않는다 — 객체를 손으로 옮겨 놓으면 경로와 내용이 어긋날 수 있다.
    """
    if manifest.get("dataset") != DATASET:
        raise SystemExit(f"manifest 의 dataset 이 다르다: {manifest.get('dataset')} (기대 {DATASET})")
    if manifest.get(PARTITION) != collected_date:
        raise SystemExit(f"manifest 의 {PARTITION} 이 다르다: "
                         f"{manifest.get(PARTITION)} (기대 {collected_date})")
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


def pull_run(s3, collected_date: str, run_id: str, target: Path) -> Path:
    """회차를 받는다. 필수 객체가 하나라도 없으면 멈춘다."""
    from pipeline.minio.ingest_raw import exists

    prefix = f"{PREFIX}/{PARTITION}={collected_date}/run_id={run_id}"
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


def write_transport(parquet: Path, target: Path, memory: str) -> int:
    """parquet 을 psql COPY 용 CSV 로 옮기고 행 수를 돌려준다.

    이스케이프·따옴표를 손으로 만들지 않고 DuckDB 에 맡긴다. 패키지 이름에 쉼표나 따옴표가
    들어갈 일은 없지만, 직접 짜 넣으면 그 가정이 깨지는 날 조용히 깨진다.
    열 순서가 아래 COPY 문의 열 목록과 같아야 한다.

    개수 두 열의 NULL 은 빈 칸으로 나가고 Postgres 가 정수 열의 빈 칸을 NULL 로 읽는다.
    0 으로 채우면 unpublish 된 버전이 "의존 없음" 이 되어 거짓이 된다.

    **여기서 정렬하지 않는다.** 빌더가 이미 (Name, Version) 순으로 쓴 parquet 이라 읽으면
    그 순서로 나오고, Postgres 는 입력 순서를 쓰지 않는다. 2,156만 행을 한 번 더 정렬하면
    메모리를 그만큼 잡는데, 실제로 운영 컨테이너에서 OOM 으로 죽었다.
    """
    import duckdb

    con = duckdb.connect()
    # 상한을 넘으면 옆 폴더로 흘린다. 컨테이너 메모리가 좁아도 죽지 않게 한다.
    temp = target.parent / "duckdb-tmp"
    temp.mkdir(exist_ok=True)
    con.execute(f"SET memory_limit='{memory}'")
    con.execute(f"SET temp_directory='{temp.as_posix()}'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"""COPY (
        SELECT Name, Version, module_format, types_bundled,
               direct_dependencies, peer_dependencies
        FROM read_parquet('{parquet.as_posix()}'))
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

CREATE TEMP TABLE stage_env (
    name                text    NOT NULL,
    version             text    NOT NULL,
    module_format       text    NOT NULL,
    types_bundled       boolean NOT NULL,
    direct_dependencies integer,
    peer_dependencies   integer
) ON COMMIT DROP;

COPY stage_env (name, version, module_format, types_bundled, direct_dependencies, peer_dependencies)
FROM STDIN WITH (FORMAT csv, ENCODING 'UTF8');
"""
    tail = f"""

-- (이름, 버전) → (package_id, version). FK 가 version 을 가리키므로 버전까지 있어야 붙는다.
CREATE TEMP TABLE resolved ON COMMIT DROP AS
SELECT v.package_id, v."version",
       s.module_format, s.types_bundled, s.direct_dependencies, s.peer_dependencies
  FROM stage_env s
  JOIN "package" p ON p."name" = s.name
  JOIN "version" v ON v.package_id = p.package_id AND v."version" = s.version;

-- 못 붙은 이유를 둘로 나눠 센다. 이름이 없는 것과, 이름은 있는데 그 버전이 없는 것은
-- 할 일이 다르다 — 앞은 이름 규칙이나 적재 대상 DB 를 의심해야 하고, 뒤는 version 이
-- 더 오래된 스냅샷이라는 뜻이라 정상이다.
--
-- selectable_rows 가 이 표의 **진짜 분모**다. 적재한 패키지들에 대해 version 이 제공하는
-- 버전 수이고, 화면이 고를 수 있는 것이 딱 그만큼이다. staged 대비 비율은 registry 가 전
-- 버전을 담는 탓에 항상 낮게 나와서, 그것만 보면 정상 적재가 사고처럼 보인다.
CREATE TEMP TABLE quality ON COMMIT DROP AS
SELECT (SELECT count(*)                   FROM stage_env)                  AS staged_rows,
       (SELECT count(DISTINCT name)       FROM stage_env)                  AS staged_packages,
       (SELECT count(*)                   FROM resolved)                   AS loaded_rows,
       (SELECT count(DISTINCT package_id) FROM resolved)                   AS loaded_packages,
       (SELECT count(*)                   FROM stage_env s
          LEFT JOIN "package" p ON p."name" = s.name
         WHERE p.package_id IS NULL)                                       AS unknown_name_rows,
       (SELECT count(*)                   FROM stage_env s
          JOIN "package" p ON p."name" = s.name
          LEFT JOIN "version" v
            ON v.package_id = p.package_id AND v."version" = s.version
         WHERE v.package_id IS NULL)                                       AS unknown_version_rows,
       (SELECT count(*)                   FROM "version" v
         WHERE EXISTS (SELECT 1 FROM resolved r WHERE r.package_id = v.package_id))
                                                                           AS selectable_rows;

-- 한 건도 못 붙으면 중단. 이름 규칙이 어긋났거나 version 이 비어 있다는 뜻이다.
DO $$ BEGIN
  IF (SELECT loaded_rows FROM quality) = 0 THEN
    RAISE EXCEPTION 'version 테이블과 (이름, 버전) 이 하나도 맞지 않는다 — 적재 대상 DB 를 확인할 것';
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

-- 전량 교체. 한 회차가 표 전체를 대신한다 — 두 회차가 섞이면 같은 화면에서 어떤 행은
-- 09-16 판정이고 어떤 행은 그 전 판정이 되는데, 그 차이를 표에서 구분할 방법이 없다.
--
-- **TRUNCATE 가 아니라 DELETE 다.** TRUNCATE 는 ACCESS EXCLUSIVE 락을 잡고 트랜잭션 끝까지
-- 유지해, 적재가 도는 내내 이 표의 모든 조회가 멈춰 선다. DELETE 는 SHARE ROW EXCLUSIVE 에서
-- 끝나 MVCC 로 조회가 그대로 나간다. advisory lock 은 적재끼리만 막을 뿐 조회는 모른다.
-- dependent_transition·similar_package 가 같은 이유로 같은 방식을 쓴다.
-- 남는 dead tuple 은 아래 VACUUM 이 정리한다.
LOCK TABLE public."{TABLE}", public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM public."{TABLE}";
INSERT INTO public."{TABLE}"
    (package_id, "version", module_format, types_bundled, direct_dependencies, peer_dependencies)
SELECT package_id, "version", module_format, types_bundled, direct_dependencies, peer_dependencies
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
    parser.add_argument("--collected-date", required=True, help="registry 수집 실행 날짜 (2026-09-16)")
    parser.add_argument("--run-id", required=True, help="입고 회차 (package-env-20260916-v1)")
    parser.add_argument("--run-dir", type=Path, help="이미 받아 둔 디렉터리. 주면 MinIO 를 안 본다")
    parser.add_argument("--execution-id", help="이 게시의 식별자. 재실행 시 같은 값을 준다")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/package_env_load")
    parser.add_argument("--memory", default="2GB",
                        help="DuckDB 상한. 넘으면 작업 폴더의 duckdb-tmp 로 흘린다")
    parser.add_argument("--verify-only", action="store_true",
                        help="게시 직전까지 전부 실행한 뒤 ROLLBACK. DB 는 그대로 둔다")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--docker-container", help="PostgreSQL 컨테이너 이름")
    target.add_argument("--psql", help="psql 실행 파일 경로")
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-user", default="postgres")
    args = parser.parse_args(argv)

    if not DATE.fullmatch(args.collected_date):
        parser.error("--collected-date 는 YYYY-MM-DD 형태여야 한다")
    if not SAFE_ID.fullmatch(args.run_id):
        parser.error("--run-id 는 영문·숫자·밑줄·하이픈 1~200자")
    args.execution_id = args.execution_id or f"{DATASET}-{args.collected_date}-{args.run_id}"
    if not SAFE_ID.fullmatch(args.execution_id):
        parser.error("--execution-id 는 영문·숫자·밑줄·하이픈 1~200자")
    return args


# 적재 품질을 사람이 읽는 두 줄로 요약한다.
def report_quality(quality: dict) -> None:
    staged, loaded = quality["staged_rows"], quality["loaded_rows"]
    selectable = quality.get("selectable_rows") or 0
    lost = staged - loaded
    if lost:
        print(f"참고: staged {staged:,}행 중 {lost:,}행이 version 에 없어 빠졌다 — "
              f"이름 없음 {quality['unknown_name_rows']:,}행 · "
              f"버전 없음 {quality['unknown_version_rows']:,}행", flush=True)
        print("  registry 는 전 버전을 담고 version 은 스냅샷이 알던 것만 담는다. "
              "빠진 행은 화면에서 고를 수 없는 버전이라 손실이 아니다", flush=True)
    if not selectable:
        return
    # 이 값이 품질 판정이다. 화면이 고를 수 있는 버전 중 소비 조건이 붙은 비율.
    coverage = loaded / selectable * 100
    line = f"커버리지 {coverage:.1f}% ({loaded:,}/{selectable:,}) — version 이 제공하는 버전 기준"
    if coverage < 99:
        # 이름이 안 붙었거나 적재가 중간에 잘렸다. 스냅샷 시차로는 이 값이 떨어지지 않는다.
        print(f"경고: {line}. 1% 넘게 비었으면 이름 해석을 의심할 것", flush=True)
    else:
        print(line, flush=True)


def main(argv=None) -> int:
    args = parse_args(argv)
    attempt_id = uuid.uuid4().hex
    prefix = f"{PREFIX}/{PARTITION}={args.collected_date}/run_id={args.run_id}"

    if args.run_dir:
        run_dir = args.run_dir.resolve()
    else:
        from pipeline.minio.ingest_raw import client
        run_dir = (args.work_dir / "runs" / f"{args.collected_date}_{args.run_id}").resolve()
        print(f"산출물 받기: s3://{BUCKET}/{prefix}/", flush=True)
        pull_run(client(), args.collected_date, args.run_id, run_dir)

    manifest_path = run_dir / "run_manifest.json"
    parquet = run_dir / PARQUET
    for path in (manifest_path, parquet):
        if not path.exists():
            raise SystemExit(f"필수 파일이 없다: {path}")

    body = manifest_path.read_bytes()
    manifest = json.loads(body)
    entry = check_manifest(manifest, args.collected_date, args.run_id)
    check_parquet(parquet, entry)
    print(f"manifest 대조 통과: {entry['rows']:,}행 · {entry['sha256'][:12]}…", flush=True)

    work = (args.work_dir / args.execution_id / attempt_id).resolve()
    work.mkdir(parents=True, exist_ok=False)
    transport = work / "package_env.copy.csv"
    staged = write_transport(parquet, transport, args.memory)
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
        "-v", f"snapshot_at={args.collected_date}",
        # 수집이 하루에 걸쳐 돌아 회차 안에서 시각이 흩어진다. 그 안의 어느 순간을 고를
        # 근거가 없으므로 날짜 시작으로 둔다. dependent_transition 이 23:59:59 를 쓰는 것은
        # 그쪽 값이 구간 끝이라 표의 t2 와 같아야 하기 때문이고, 여기는 그런 기준이 없다.
        "-v", f"snapshot_timestamp={args.collected_date}T00:00:00",
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
              PARTITION: args.collected_date, "run_id": args.run_id, "quality": quality}
    (work / "execution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    if quality:
        report_quality(quality)
    print(("검증만 하고 되돌렸다" if args.verify_only else "게시 완료") + f" — {work}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
