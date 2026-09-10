"""raw jsonl.gz → registry_versions/part-00000.parquet + registry_status.parquet (수집계획 §2-2).

  python to_parquet.py --raw data/registry/raw/run=2026-09-09 --out data/registry/parquet

registry_versions: 한 행 = 패키지 × 버전. 열 이름은 deps.dev requirements 와 같게(Dependencies·PeerDependencies·OptionalDependencies)
                   + DevDependencies. 배열은 STRUCT(Name, Requirement)[]. Name 순 정렬, zstd.
registry_status  : 패키지 1행. status = READY / NOT_FOUND / UNPUBLISHED / FAILED / PENDING (체크포인트 기준).
                   화면·통계에서 "자료 없음"을 0과 구분하는 용도.
수집 중에도 실행 가능(쓰고 있는 마지막 part 는 건너뜀, 강제 종료로 잘린 옛 part 는 복구).
"""
import argparse
import glob
import gzip
import os
import shutil
import sqlite3

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("--raw", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

files = sorted(glob.glob(os.path.join(a.raw, "part-*.jsonl.gz")))
assert files, "no parts under " + a.raw


def _complete(path):
    """수집기가 아직 쓰고 있는 part는 gzip 끝이 없어 읽다가 깨진다. 끝까지 읽히는 파일만 쓴다."""
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 20):
                pass
        return True
    except (EOFError, OSError):
        return False


def _repair(path):
    """강제 종료로 gzip 끝이 잘린 옛 part: 읽히는 줄까지 살려 다시 쓰고 원본은 .broken으로 보관."""
    lines = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if line.endswith("\n"):
                    lines.append(line)
    except (EOFError, OSError):
        pass
    os.replace(path, path + ".broken")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[to_parquet] repaired {os.path.basename(path)}: {len(lines)} lines salvaged (original kept as .broken)")


def _p(path):
    return path.replace(os.sep, "/")


newest = files[-1]
incomplete = [f for f in files if not _complete(f)]
for f in incomplete:
    if f != newest:          # 최신 part는 수집기가 쓰는 중 → 건너뜀. 그 외 잘린 part는 복구
        _repair(f)
if newest in incomplete:
    print(f"[to_parquet] skipping in-progress part: {os.path.basename(newest)}")
    files = files[:-1]
# 파일 회전 직후 강제 종료되면 gzip 헤더도 없는 0바이트 part 가 남는다. 읽을 줄이 없으니 건너뛴다(DuckDB 는 "not a GZIP stream" 으로 멈춤).
empty = [f for f in files if os.path.getsize(f) == 0]
if empty:
    print(f"[to_parquet] skipping {len(empty)} empty part(s): {', '.join(os.path.basename(f) for f in empty)}")
    files = [f for f in files if f not in empty]
assert files, "no complete parts yet"

DEP = "STRUCT(Name VARCHAR, Requirement VARCHAR)[]"
con = duckdb.connect()
con.execute(
    f"""CREATE TABLE raw AS SELECT * FROM read_json({[_p(f) for f in files]!r}, format='newline_delimited',
    columns={{'Name':'VARCHAR','Version':'VARCHAR','published_at':'VARCHAR','rank':'INTEGER',
             'Dependencies':'{DEP}','DevDependencies':'{DEP}','PeerDependencies':'{DEP}','OptionalDependencies':'{DEP}',
             'deprecated':'VARCHAR','unpublished':'BOOLEAN','fetched_at':'VARCHAR','modified':'VARCHAR'}})"""
)
# 같은 (Name, Version) 이 여러 번 받혔으면(재시작 중복·재시도) 가장 최근 fetched_at 만 남긴다.
# 시각 문자열은 ISO 8601(Z 포함) → TIMESTAMPTZ 로 읽어 UTC 기준 TIMESTAMP 로 저장.
con.execute(
    """CREATE TABLE v AS
       SELECT Name, Version,
              try_cast(published_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS published_at, rank,
              Dependencies, DevDependencies, PeerDependencies, OptionalDependencies, deprecated, unpublished,
              try_cast(fetched_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS fetched_at,
              try_cast(modified AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS modified
       FROM raw
       QUALIFY row_number() OVER (PARTITION BY Name, Version ORDER BY fetched_at DESC) = 1"""
)
outv = os.path.join(a.out, "registry_versions")
if os.path.isdir(outv):
    shutil.rmtree(outv)
os.makedirs(outv)
con.execute(
    f"""COPY (SELECT * FROM v ORDER BY Name, published_at, Version)
        TO '{_p(os.path.join(outv, 'part-00000.parquet'))}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
)

# 패키지 단위 상태는 체크포인트가 정본(요청은 했지만 버전 행이 없는 NOT_FOUND·UNPUBLISHED·FAILED 도 포함).
ck = sqlite3.connect(f"file:{_p(os.path.join(a.raw, 'checkpoint.sqlite'))}?mode=ro", uri=True)
rows = ck.execute("SELECT name, rank, status, http, bytes, modified, fetched_at, error FROM tasks").fetchall()
ck.close()
tasks = pa.table({
    "name": pa.array([r[0] for r in rows], pa.string()), "rank": pa.array([r[1] for r in rows], pa.int32()),
    "ck_status": pa.array([r[2] for r in rows], pa.string()), "http": pa.array([r[3] for r in rows], pa.int32()),
    "doc_bytes": pa.array([r[4] for r in rows], pa.int64()), "modified": pa.array([r[5] for r in rows], pa.string()),
    "fetched_at": pa.array([r[6] for r in rows], pa.string()), "error": pa.array([r[7] for r in rows], pa.string()),
})
con.register("tasks", tasks)
con.execute(
    """CREATE TABLE st AS
       SELECT t.name, t.rank,
              CASE t.ck_status WHEN 'done' THEN 'READY' WHEN 'not_found' THEN 'NOT_FOUND' WHEN 'unpublished' THEN 'UNPUBLISHED'
                               WHEN 'failed' THEN 'FAILED' ELSE 'PENDING' END AS status,
              COALESCE(a.n_versions, 0) AS n_versions, COALESCE(a.n_unpub, 0) AS n_versions_unpublished,
              a.first_published_at, a.last_published_at,
              try_cast(t.modified AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS modified,
              try_cast(t.fetched_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS fetched_at,
              t.http, t.doc_bytes, t.error
       FROM tasks t
       LEFT JOIN (SELECT Name, count(*) AS n_versions, count(*) FILTER (WHERE unpublished) AS n_unpub,
                         min(published_at) AS first_published_at, max(published_at) AS last_published_at
                  FROM v GROUP BY Name) a ON a.Name = t.name
       ORDER BY t.rank"""
)
st = con.execute("SELECT * FROM st").to_arrow_table()
os.makedirs(a.out, exist_ok=True)
pq.write_table(st, os.path.join(a.out, "registry_status.parquet"), compression="zstd")

n_v = con.execute("SELECT count(*) FROM v").fetchone()[0]
n_pkg = con.execute("SELECT count(DISTINCT Name) FROM v").fetchone()[0]
n_unpub = con.execute("SELECT count(*) FROM v WHERE unpublished").fetchone()[0]
n_dev = con.execute("SELECT count(*) FROM v WHERE len(DevDependencies) > 0").fetchone()[0]
by = dict(con.execute("SELECT status, count(*) FROM st GROUP BY status ORDER BY status").fetchall())
print(f"[to_parquet] registry_versions rows={n_v} packages={n_pkg} unpublished_versions={n_unpub} rows_with_devDeps={n_dev} "
      f"| registry_status rows={st.num_rows} {by} -> {a.out}")
