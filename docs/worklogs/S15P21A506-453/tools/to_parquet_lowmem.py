r"""to_parquet.py 의 저메모리 대체 (U5 예비). 같은 SQL·같은 결손 규칙, 차이는 Arrow 로 전부 올리지 않고
DuckDB COPY ... PARTITION_BY(date) 로 바로 쓰고 memory_limit/temp_directory 로 디스크에 흘리는 것.
  python to_parquet_lowmem.py --raw <run dir> --out <root>/parquet [--mem 24GB]
part 파일은 모두 완결(final)이어야 한다(복구 로직 없음).
"""
import argparse, glob, os, sys, duckdb
ap = argparse.ArgumentParser(); ap.add_argument("--raw", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--mem", default="24GB"); ap.add_argument("--threads", type=int, default=6)
a = ap.parse_args()
files = sorted(glob.glob(os.path.join(a.raw, "part-*.jsonl.gz"))); assert files
os.makedirs(a.out, exist_ok=True)
tmp = os.path.join(a.out, "_duckdb_tmp"); os.makedirs(tmp, exist_ok=True)
con = duckdb.connect(os.path.join(a.out, "_work.duckdb"))
con.execute(f"SET memory_limit='{a.mem}'"); con.execute(f"SET threads={a.threads}")
con.execute(f"SET temp_directory='{tmp.replace(os.sep,'/')}'"); con.execute("SET preserve_insertion_order=false")
con.execute(f"""CREATE OR REPLACE TABLE raw AS SELECT * FROM read_json({files!r}, format='newline_delimited',
    columns={{'name':'VARCHAR','rank':'INTEGER','kind':'VARCHAR','start':'DATE','end':'DATE','tier':'VARCHAR',
             'fetched_at':'TIMESTAMP','task_id':'VARCHAR','status':'VARCHAR',
             'downloads':'STRUCT(downloads BIGINT, day DATE)[]'}})""")
print("raw", con.execute("select count(*) from raw").fetchone(), flush=True)
con.execute("""CREATE OR REPLACE TABLE d0 AS
   SELECT u.day AS date, name, u.downloads AS downloads, tier, fetched_at
   FROM (SELECT name, tier, fetched_at, unnest(downloads) AS u FROM raw WHERE status = 'ok')
   QUALIFY row_number() OVER (PARTITION BY u.day, name ORDER BY fetched_at DESC) = 1""")
print("d0", con.execute("select count(*) from d0").fetchone(), flush=True)
con.execute("""CREATE OR REPLACE TABLE d AS
   SELECT date, name,
          CASE WHEN downloads = 0 AND med >= 1000 THEN NULL ELSE downloads END AS downloads,
          (downloads = 0 AND med >= 1000) AS imputed_gap, tier, fetched_at
   FROM (SELECT *, median(downloads) OVER (PARTITION BY name ORDER BY date
                                           ROWS BETWEEN 7 PRECEDING AND 7 FOLLOWING) AS med FROM d0)""")
con.execute("DROP TABLE d0")
outd = os.path.join(a.out, "downloads").replace(os.sep, "/")
con.execute(f"""COPY (SELECT date, name, downloads, imputed_gap, tier, fetched_at FROM d ORDER BY date, name)
   TO '{outd}' (FORMAT PARQUET, PARTITION_BY (date), OVERWRITE_OR_IGNORE, FILENAME_PATTERN 'part-{{i}}')""")
print("downloads written", con.execute("select count(*), count(distinct date) from d").fetchone(), flush=True)
st = os.path.join(a.out, "downloads_status.parquet").replace(os.sep, "/")
con.execute(f"""COPY (SELECT name, any_value(tier) AS tier,
          CASE WHEN bool_or(status = 'ok') THEN 'READY' ELSE 'NOT_FOUND' END AS status,
          min(start) AS first_date, max("end") AS last_date, max(fetched_at) AS last_fetched_at
   FROM raw GROUP BY name) TO '{st}' (FORMAT PARQUET)""")
print("status written", con.execute("select count(*) from raw group by name limit 0").fetchall() or "ok", flush=True)
con.close()
import shutil; os.remove(os.path.join(a.out, "_work.duckdb")); shutil.rmtree(tmp, ignore_errors=True)
for f in glob.glob(os.path.join(a.out, "_work.duckdb*")): os.remove(f)
print("done", flush=True)
