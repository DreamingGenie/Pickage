"""raw jsonl.gz → downloads(date 파티션 Parquet) + downloads_status.parquet.
Spark 적재(계획 §3) 전까지의 로컬 대체. 결손 규칙(§4-1): downloads=0이고 전후 7일 중앙값 ≥ 1000이면 NULL + imputed_gap.

  python to_parquet.py --raw data/downloads/raw/run=2026-09-02 --out data/downloads/parquet
"""
import argparse
import glob
import gzip
import json
import os
import sys
import zlib

import duckdb
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

try:
    # status.py --refresh-parquet 는 이 스크립트의 stdout 을 그대로 물려받는다. 콘솔이 아니면
    # 인코딩이 로캘(cp949)로 정해져 cp949 에 없는 글자 하나에 UnicodeEncodeError 로 죽는다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ap = argparse.ArgumentParser()
ap.add_argument("--raw", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

files = sorted(glob.glob(os.path.join(a.raw, "part-*.jsonl.gz")))
assert files, "no parts under " + a.raw


GZ_ERRORS = (EOFError, OSError, zlib.error)  # 절단=EOFError, 헤더/CRC 손상=BadGzipFile(OSError), deflate 블록 손상=zlib.error


def _complete(path):
    """끝까지 정상으로 읽히는 gzip 인가. 수집기가 아직 쓰고 있는 part 는 gzip 끝이 없어 읽다가 깨진다.
    0바이트(회전 직후 강제 종료로 gzip 헤더조차 없는 part)는 읽을 게 없으니 불완전으로 본다."""
    if os.path.getsize(path) == 0:
        return False
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 20):
                pass
        return True
    except GZ_ERRORS:
        return False


def _repair(path):
    """강제 종료로 gzip 끝이 잘린 옛 part: JSON 으로 읽히는 온전한 줄까지 살려 다시 쓰고 원본은 .broken 으로 보관.
    CRC 손상 스트림은 예외가 나기 전에 쓰레기 줄을 내놓을 수 있어 줄마다 JSON 파싱으로 확인한다.
    원본을 rename 하므로 수집기가 그 파일을 쓰고 있지 않다는 것이 확실할 때만 부른다."""
    lines = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    break
                try:
                    json.loads(line)
                except ValueError:
                    break
                lines.append(line)
    except GZ_ERRORS:
        pass
    os.replace(path, path + ".broken")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[to_parquet] repaired {os.path.basename(path)}: {len(lines)} lines salvaged (original kept as .broken)")


newest = files[-1]
incomplete = [f for f in files if not _complete(f)]
for f in incomplete:
    if f != newest:          # 최신 part는 수집기가 쓰는 중 → 건너뜀. 그 외 잘린 part는 복구
        _repair(f)
if newest in incomplete:
    print(f"[to_parquet] skipping in-progress part: {os.path.basename(newest)}")
    files = files[:-1]
assert files, "no complete parts yet"
con = duckdb.connect()
con.execute(
    f"""CREATE TABLE raw AS SELECT * FROM read_json({files!r}, format='newline_delimited',
    columns={{'name':'VARCHAR','rank':'INTEGER','kind':'VARCHAR','start':'DATE','end':'DATE','tier':'VARCHAR',
             'fetched_at':'TIMESTAMP','task_id':'VARCHAR','status':'VARCHAR',
             'downloads':'STRUCT(downloads BIGINT, day DATE)[]'}})"""
)
con.execute(
    """CREATE TABLE d0 AS
       SELECT u.day AS date, name, u.downloads AS downloads, tier, fetched_at
       FROM (SELECT name, tier, fetched_at, unnest(downloads) AS u FROM raw WHERE status = 'ok')
       QUALIFY row_number() OVER (PARTITION BY u.day, name ORDER BY fetched_at DESC) = 1"""
)
con.execute(
    """CREATE TABLE d AS
       SELECT date, name,
              CASE WHEN downloads = 0 AND med >= 1000 THEN NULL ELSE downloads END AS downloads,
              (downloads = 0 AND med >= 1000) AS imputed_gap, tier, fetched_at
       FROM (SELECT *, median(downloads) OVER (PARTITION BY name ORDER BY date
                                               ROWS BETWEEN 7 PRECEDING AND 7 FOLLOWING) AS med FROM d0)"""
)
tbl = con.execute("SELECT * FROM d ORDER BY date, name").to_arrow_table()
outd = os.path.join(a.out, "downloads")
ds.write_dataset(
    tbl, outd, format="parquet",
    partitioning=ds.partitioning(pa.schema([("date", pa.date32())]), flavor="hive"),
    existing_data_behavior="delete_matching", basename_template="part-{i}.parquet",
)
st = con.execute(
    """SELECT name, any_value(tier) AS tier,
              CASE WHEN bool_or(status = 'ok') THEN 'READY' ELSE 'NOT_FOUND' END AS status,
              min(start) AS first_date, max("end") AS last_date, max(fetched_at) AS last_fetched_at
       FROM raw GROUP BY name"""
).to_arrow_table()
os.makedirs(a.out, exist_ok=True)
pq.write_table(st, os.path.join(a.out, "downloads_status.parquet"))

n_gap = con.execute("SELECT count(*) FROM d WHERE imputed_gap").fetchone()[0]
n_ok = con.execute("SELECT count(*) FROM raw WHERE status = 'ok'").fetchone()[0]
n_nf = con.execute("SELECT count(*) FROM raw WHERE status = 'not_found'").fetchone()[0]
n_dates = con.execute("SELECT count(DISTINCT date) FROM d").fetchone()[0]
print(f"[to_parquet] downloads rows={tbl.num_rows} dates={n_dates} imputed_gap={n_gap} "
      f"status rows={st.num_rows} ok={n_ok} not_found={n_nf} -> {a.out}")
