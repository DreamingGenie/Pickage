"""로컬 Parquet(data/)를 DuckDB 뷰로 묶어 SQL 편집기(DuckDB UI)로 조회한다.

사용:
  .venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py            # 카탈로그 갱신 + UI(localhost:4213) 실행
  .venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py --no-ui    # 카탈로그(data/oss_shift.duckdb)만 갱신
  .venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py -c "select count(*) from downloads"   # 1회성 쿼리

뷰 이름 = 데이터셋 폴더명 (projects / pkg_project / requirements / versions_full / downloads / downloads_status / package_text).
package_text 는 data/keywords/package_text/ 의 가장 최근 run 파일 하나만 가리킨다(run 간 행이 겹치므로 합치지 않음).
파티션 컬럼(snapshot, date)은 hive 파티션으로 노출되므로 WHERE 로 걸면 해당 폴더만 읽는다.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB_PATH = DATA / "oss_shift.duckdb"  # /data/ 는 gitignore


def _downloads_dir() -> Path:
    real = DATA / "downloads" / "parquet"
    return real if real.exists() else DATA / "downloads" / "parquet_smoke"


def datasets() -> dict[str, tuple[str, bool]]:
    """뷰이름 -> (parquet glob, hive_partitioning)"""
    dl = _downloads_dir()
    out: dict[str, tuple[str, bool]] = {}
    for name in ("projects", "pkg_project", "requirements", "versions_full"):
        d = DATA / "raw" / name
        if d.exists():
            out[name] = (str(d / "snapshot=*" / "*.parquet"), True)
    if (dl / "downloads").exists():
        out["downloads"] = (str(dl / "downloads" / "date=*" / "*.parquet"), True)
    if (dl / "downloads_status.parquet").exists():
        out["downloads_status"] = (str(dl / "downloads_status.parquet"), False)
    pt = sorted((DATA / "keywords" / "package_text").glob("package_text_*.parquet"))
    if pt:  # keywords 결합 결과(pipeline/collectors/keywords/build_package_text.py). 파일명 뒤 run 날짜순 → 마지막이 최신
        out["package_text"] = (str(pt[-1]), False)
    return out


def build_catalog(con: duckdb.DuckDBPyConnection) -> None:
    for name, (glob, hive) in datasets().items():
        path = glob.replace("\\", "/")
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{path}', hive_partitioning={'true' if hive else 'false'})"
        )
        print(f"  view {name:<17} <- {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-ui", action="store_true", help="뷰만 갱신하고 종료")
    ap.add_argument("-c", "--command", help="SQL 1개 실행 후 종료")
    args = ap.parse_args()

    con = duckdb.connect(str(DB_PATH))
    print(f"catalog: {DB_PATH}")
    build_catalog(con)

    if args.command:
        con.sql(args.command).show(max_rows=100)
        return 0
    if args.no_ui:
        return 0

    con.execute("INSTALL ui; LOAD ui;")
    url = con.execute("CALL start_ui()").fetchone()[0]
    print(f"\nDuckDB UI: {url}  (Ctrl+C 로 종료)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
