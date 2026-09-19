"""이미 있는 package_text parquet에 download_rank만 덧붙인다 (S15P21A506-402).

`build_package_text.py`를 raw(`data/keywords/raw/...`)부터 다시 돌리지 않고도
`download_rank`를 추가하고 싶을 때 쓴다. `download_rank`는 `name` 하나에만 의존하는
조인이라(다른 열과 무관) raw를 다시 읽을 필요가 없다 — 이미 게시된 package_text
parquet과 고정 목록(`datasets/targets/rank_top100k_20260902.csv`, git에 이미 있음)만
있으면 된다. 결과값은 raw부터 build_package_text.py로 다시 만든 것과 완전히 같다.

원본은 건드리지 않는다 — `--in`과 `--out`이 같은 경로면 거부한다. 입력에 이미
`download_rank`가 있으면(예: 이미 이 스크립트를 한 번 돌린 파일) `--overwrite-existing-column`
없이는 조용히 덮어쓰지 않고 거부한다.

사용:
  python backfill_download_rank.py --in package_text_2026-09-08.parquet \\
      --out package_text_2026-09-08_with-rank.parquet
"""
import argparse
import json
import os

import duckdb
import pyarrow.parquet as pq

from build_package_text import RANK_LIST


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="input", required=True, help="기존 package_text parquet 경로")
    ap.add_argument("--out", required=True, help="새로 쓸 parquet 경로 (원본과 같을 수 없음)")
    ap.add_argument("--rank-list", default=RANK_LIST,
                     help="download_rank 조인용 고정 목록 CSV. name·rank 열만 있으면 된다 "
                          "(기본: 다운로드 상위 10만)")
    ap.add_argument("--overwrite-existing-column", action="store_true",
                     help="입력에 이미 download_rank가 있어도 다시 계산해 덮어쓴다. 기본은 거부")
    a = ap.parse_args()

    if os.path.abspath(a.input) == os.path.abspath(a.out):
        raise SystemExit("--in과 --out은 같은 파일일 수 없습니다 — 원본을 보존하려고 막아둔다")

    schema_names = pq.read_schema(a.input).names
    if "download_rank" in schema_names and not a.overwrite_existing_column:
        raise SystemExit(
            f"{a.input} 에 이미 download_rank 컬럼이 있습니다. "
            "다시 계산해 덮어쓰려면 --overwrite-existing-column을 주세요."
        )

    con = duckdb.connect()
    con.execute("SET memory_limit='10GB'")

    # build_package_text.py와 완전히 같은 조인 패턴 — 이름 중복은 순위가 낮은(=상위) 쪽만 남긴다.
    con.execute(f"""CREATE TABLE rank_list AS
      SELECT trim(name) AS name, min(rank) AS download_rank
      FROM read_csv_auto('{a.rank_list}') WHERE name IS NOT NULL GROUP BY 1""")

    select_p = "p.* EXCLUDE (download_rank)" if "download_rank" in schema_names else "p.*"
    con.execute(f"""COPY (
      SELECT {select_p}, k.download_rank
      FROM read_parquet('{a.input}') p
      LEFT JOIN rank_list k USING (name)
    ) TO '{a.out}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 100000)""")

    total = con.execute(f"SELECT count(*) FROM read_parquet('{a.out}')").fetchone()[0]
    in_scope = con.execute(
        f"SELECT count(*) FROM read_parquet('{a.out}') WHERE download_rank IS NOT NULL"
    ).fetchone()[0]
    result = {
        "input": a.input, "output": a.out, "rank_list": a.rank_list,
        "rows": total, "download_rank_not_null(리포트 가능)": in_scope,
        "download_rank_null(목록 밖)": total - in_scope,
    }
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
