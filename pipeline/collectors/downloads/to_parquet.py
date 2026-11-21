"""raw jsonl.gz → downloads(date 파티션 Parquet) + downloads_status.parquet.
Spark 적재(계획 §3) 전까지의 로컬 대체. 결손 규칙(§4-1): downloads=0이고 전후 7일 중앙값 ≥ 1000이면 NULL + imputed_gap.

  python to_parquet.py --raw data/downloads/raw/run=2026-09-02 --out data/downloads/parquet
  python to_parquet.py --raw … --out … --low-memory [--mem 24GB] [--threads 6]

--low-memory 는 결과가 같고 쓰는 길만 다르다. 기본 경로는 결과 표를 Arrow 로 전부 메모리에 올려
쓰는데, 46.9만 패키지(329,632,221행)에서는 20분 넘게 출력이 없어 끊었다(2026-09-22,
docs/worklogs/S15P21A506-453/04-production-run.md §2-2). 저메모리 경로는 작업 표를 디스크의
DuckDB 파일에 두고 memory_limit·temp_directory 로 넘치는 것을 흘리며, DuckDB 가 파티션을 바로 쓴다.
두 경로가 같은 파일 내용을 내는지는 test_to_parquet.py 가 본다.
"""
import argparse
import glob
import gzip
import json
import os
import shutil
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


RAW_SQL = """CREATE OR REPLACE TABLE raw AS SELECT * FROM read_json({files!r}, format='newline_delimited',
    columns={{'name':'VARCHAR','rank':'INTEGER','kind':'VARCHAR','start':'DATE','end':'DATE','tier':'VARCHAR',
             'fetched_at':'TIMESTAMP','task_id':'VARCHAR','status':'VARCHAR',
             'downloads':'STRUCT(downloads BIGINT, day DATE)[]'}})"""
D0_SQL = """CREATE OR REPLACE TABLE d0 AS
       SELECT u.day AS date, name, u.downloads AS downloads, tier, fetched_at
       FROM (SELECT name, tier, fetched_at, unnest(downloads) AS u FROM raw WHERE status = 'ok')
       QUALIFY row_number() OVER (PARTITION BY u.day, name ORDER BY fetched_at DESC) = 1"""
D_SQL = """CREATE OR REPLACE TABLE d AS
       SELECT date, name,
              CASE WHEN downloads = 0 AND med >= 1000 THEN NULL ELSE downloads END AS downloads,
              (downloads = 0 AND med >= 1000) AS imputed_gap, tier, fetched_at
       FROM (SELECT *, median(downloads) OVER (PARTITION BY name ORDER BY date
                                               ROWS BETWEEN 7 PRECEDING AND 7 FOLLOWING) AS med FROM d0)"""
STATUS_SQL = """SELECT name, any_value(tier) AS tier,
              CASE WHEN bool_or(status = 'ok') THEN 'READY' ELSE 'NOT_FOUND' END AS status,
              min(start) AS first_date, max("end") AS last_date, max(fetched_at) AS last_fetched_at
       FROM raw GROUP BY name"""


def complete_parts(raw):
    """변환할 part 목록. 잘린 옛 part 는 복구하고, 수집기가 쓰는 중인 최신 part 는 뺀다."""
    files = sorted(glob.glob(os.path.join(raw, "part-*.jsonl.gz")))
    assert files, "no parts under " + raw
    newest = files[-1]
    incomplete = [f for f in files if not _complete(f)]
    for f in incomplete:
        if f != newest:          # 최신 part는 수집기가 쓰는 중 → 건너뜀. 그 외 잘린 part는 복구
            _repair(f)
    if newest in incomplete:
        print(f"[to_parquet] skipping in-progress part: {os.path.basename(newest)}")
        files = files[:-1]
    assert files, "no complete parts yet"
    return files


def _write_in_memory(con, out):
    tbl = con.execute("SELECT * FROM d ORDER BY date, name").to_arrow_table()
    ds.write_dataset(
        tbl, os.path.join(out, "downloads"), format="parquet",
        partitioning=ds.partitioning(pa.schema([("date", pa.date32())]), flavor="hive"),
        existing_data_behavior="delete_matching", basename_template="part-{i}.parquet",
    )
    st = con.execute(STATUS_SQL).to_arrow_table()
    os.makedirs(out, exist_ok=True)
    pq.write_table(st, os.path.join(out, "downloads_status.parquet"))


def _write_low_memory(con, out):
    outd = os.path.join(out, "downloads")
    # 기본 경로의 existing_data_behavior="delete_matching" 과 같게 맞춘다 — 이번에 쓰는 날짜의
    # 폴더만 비우고 다른 날짜는 둔다. DuckDB 는 스레드마다 파일을 나눠 쓸 수 있어, 비우지 않으면
    # 지난 변환이 남긴 part 가 같은 날짜에 겹쳐 행이 두 번 읽힌다.
    for (day,) in con.execute("SELECT DISTINCT date FROM d").fetchall():
        shutil.rmtree(os.path.join(outd, f"date={day}"), ignore_errors=True)
    con.execute(f"""COPY (SELECT date, name, downloads, imputed_gap, tier, fetched_at FROM d ORDER BY date, name)
       TO '{outd.replace(os.sep, "/")}'
       (FORMAT PARQUET, PARTITION_BY (date), OVERWRITE_OR_IGNORE, FILENAME_PATTERN 'part-{{i}}')""")
    st = os.path.join(out, "downloads_status.parquet").replace(os.sep, "/")
    con.execute(f"COPY ({STATUS_SQL}) TO '{st}' (FORMAT PARQUET)")


def convert(raw, out, low_memory=False, mem="24GB", threads=6):
    files = complete_parts(raw)
    os.makedirs(out, exist_ok=True)
    work = tmp = None
    if low_memory:
        work = os.path.join(out, "_work.duckdb")
        tmp = os.path.join(out, "_duckdb_tmp")
        os.makedirs(tmp, exist_ok=True)
        con = duckdb.connect(work)
        con.execute(f"SET memory_limit='{mem}'")
        con.execute(f"SET threads={int(threads)}")
        con.execute(f"SET temp_directory='{tmp.replace(os.sep, '/')}'")
        con.execute("SET preserve_insertion_order=false")
    else:
        con = duckdb.connect()
    try:
        con.execute(RAW_SQL.format(files=files))
        con.execute(D0_SQL)
        con.execute(D_SQL)
        if low_memory:
            con.execute("DROP TABLE d0")
            _write_low_memory(con, out)
        else:
            _write_in_memory(con, out)
        n_rows, n_dates, n_gap = con.execute(
            "SELECT count(*), count(DISTINCT date), count(*) FILTER (WHERE imputed_gap) FROM d").fetchone()
        n_status = con.execute("SELECT count(DISTINCT name) FROM raw").fetchone()[0]
        n_ok = con.execute("SELECT count(*) FROM raw WHERE status = 'ok'").fetchone()[0]
        n_nf = con.execute("SELECT count(*) FROM raw WHERE status = 'not_found'").fetchone()[0]
    finally:
        con.close()
        if low_memory:
            for f in glob.glob(work + "*"):
                os.remove(f)
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"[to_parquet] downloads rows={n_rows} dates={n_dates} imputed_gap={n_gap} "
          f"status rows={n_status} ok={n_ok} not_found={n_nf} -> {out}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--low-memory", action="store_true",
                    help="결과 표를 메모리에 올리지 않고 DuckDB 가 디스크로 흘리며 쓴다 (수억 행용)")
    ap.add_argument("--mem", default="24GB", help="--low-memory 일 때 DuckDB memory_limit")
    ap.add_argument("--threads", type=int, default=6, help="--low-memory 일 때 DuckDB threads")
    a = ap.parse_args(argv)
    convert(a.raw, a.out, low_memory=a.low_memory, mem=a.mem, threads=a.threads)


if __name__ == "__main__":
    main()
