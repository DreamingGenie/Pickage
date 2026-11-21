"""이동쌍 가운데 "도착지가 출발지의 의존"인 쌍이 얼마나 되는지 잰다.

  .venv-bq/Scripts/python.exe pipeline/duckdb/transitive_dependency_axis.py

이동쌍 (X → Y) 는 "어떤 패키지가 릴리스를 내며 X 를 빼고 Y 를 넣었다"를 센 것이다. 그런데 X 가 Y 에
의존하고 있었다면 그 패키지는 Y 를 X 를 통해 이미 쓰고 있었다 — X 를 걷어내면서 Y 를 직접 선언하게
된 것이지 X 대신 Y 를 고른 것이 아닐 수 있다(`rxjs → tslib`). 기본 필터(lift·votes·배포주체-월)는
이 경우를 가르지 못한다(docs/검증_교체흐름_필터일관성_260922.md §4-②).

여기서는 그 축을 **재기만** 한다. 서빙 필터를 바꾸지 않는다.

  ever     X 의 어떤 릴리스든 regular 의존으로 Y 를 선언한 적이 있다
  at_time  이동이 관측된 기간의 끝(last_seen)에 X 의 대표 릴리스가 Y 를 선언하고 있었다
           (대표 = 그날까지 발행된 릴리스 중 ordinal 최고. build_dependent_transitions.py 와 같은 정의)
  reverse  반대로 Y 가 X 에 의존한 적이 있다 (Y 가 X 를 감싼 후속 패키지인 경우)

입력  datasets/migration_pairs_260908/migration_pairs_{all,recommended,strict}.csv  (git 추적)
      data/raw/requirements · data/raw/versions_full  snapshot=2026-08-31           (git 밖, 11 GB)
출력  표준 출력의 요약 표 + --out 을 주면 쌍별 판정 CSV
"""
import argparse
import os
import sys

import duckdb

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace(os.sep, "/")
SNAPSHOT = "2026-08-31"
PAIRS_DIR = f"{ROOT}/datasets/migration_pairs_260908"
TIERS = ("all", "recommended", "strict")

# 판정 SQL 은 상수로 뺀다. 시험이 합성 입력에 같은 문장을 적용한다.
#   입력 표: pairs(tier, from_pkg, to_pkg, last_seen DATE)
#            req(Name, Version, dep)            한 행 = (패키지 릴리스, 그 릴리스의 regular 의존 하나)
#            ver(Name, Version, ordinal, published_at)   릴리스만
EVER_SQL = """CREATE OR REPLACE TABLE ever AS
SELECT DISTINCT Name AS pkg, dep FROM req"""

# 그날의 대표 릴리스 = published_at <= last_seen 중 ordinal 최고.
AT_TIME_SQL = """CREATE OR REPLACE TABLE at_time AS
WITH want AS (SELECT DISTINCT from_pkg, last_seen FROM pairs),
rep AS (
  SELECT w.from_pkg, w.last_seen, arg_max(v.Version, v.ordinal) AS version
  FROM want w JOIN ver v
    ON v.Name = w.from_pkg AND v.published_at < CAST(w.last_seen AS TIMESTAMP) + INTERVAL 1 DAY
  GROUP BY 1, 2)
SELECT DISTINCT r.from_pkg AS pkg, r.last_seen, q.dep
FROM rep r JOIN req q ON q.Name = r.from_pkg AND q.Version = r.version"""

CLASSIFY_SQL = """CREATE OR REPLACE TABLE judged AS
SELECT p.*,
       (e.pkg IS NOT NULL) AS dep_ever,
       (a.pkg IS NOT NULL) AS dep_at_time,
       (r.pkg IS NOT NULL) AS reverse_ever
FROM pairs p
LEFT JOIN ever e    ON e.pkg = p.from_pkg AND e.dep = p.to_pkg
LEFT JOIN at_time a ON a.pkg = p.from_pkg AND a.last_seen = p.last_seen AND a.dep = p.to_pkg
LEFT JOIN ever r    ON r.pkg = p.to_pkg AND r.dep = p.from_pkg"""

SUMMARY_SQL = """SELECT tier, count(*) AS pairs,
       count(*) FILTER (WHERE dep_ever)     AS dep_ever,
       count(*) FILTER (WHERE dep_at_time)  AS dep_at_time,
       count(*) FILTER (WHERE reverse_ever) AS reverse_ever,
       count(*) FILTER (WHERE dep_ever AND reverse_ever) AS both
FROM judged GROUP BY tier ORDER BY pairs DESC"""

# 각 X 에서 votes 가 가장 큰 도착지(화면이 1위로 세우는 것)만 보면 얼마나 되는가.
TOP1_SQL = """SELECT tier, count(*) AS from_pkgs,
       count(*) FILTER (WHERE dep_ever)    AS top1_dep_ever,
       count(*) FILTER (WHERE dep_at_time) AS top1_dep_at_time
FROM (SELECT *, row_number() OVER (PARTITION BY tier, from_pkg ORDER BY votes DESC, to_pkg) AS rn FROM judged)
WHERE rn = 1 GROUP BY tier ORDER BY from_pkgs DESC"""


def load_inputs(con, threads, memory):
    con.execute(f"SET threads={int(threads)}")
    con.execute(f"SET memory_limit='{memory}'")
    os.makedirs(f"{ROOT}/data/duckdb_tmp", exist_ok=True)
    con.execute(f"SET temp_directory='{ROOT}/data/duckdb_tmp'")
    con.execute("CREATE TABLE pairs(tier VARCHAR, from_pkg VARCHAR, to_pkg VARCHAR, votes DOUBLE, last_seen DATE)")
    for tier in TIERS:
        con.execute(
            f"""INSERT INTO pairs SELECT '{tier}', from_pkg, to_pkg, votes, last_seen
                FROM read_csv('{PAIRS_DIR}/migration_pairs_{tier}.csv', header=true)""")
    # 출발·도착 어느 쪽으로든 나오는 이름만 읽는다. 원천은 7,856만 릴리스다.
    con.execute("CREATE TABLE names AS SELECT from_pkg AS name FROM pairs UNION SELECT to_pkg FROM pairs")
    req = f"{ROOT}/data/raw/requirements/snapshot={SNAPSHOT}/*.parquet"
    ver = f"{ROOT}/data/raw/versions_full/snapshot={SNAPSHOT}/*.parquet"
    con.execute(f"""CREATE TABLE req AS
SELECT r.Name, r.Version, d.Name AS dep
FROM (SELECT Name, Version, unnest(Dependencies) AS d FROM read_parquet('{req}')
      WHERE Name IN (SELECT name FROM names)) r""")
    con.execute(f"""CREATE TABLE ver AS
SELECT Name, Version, ordinal, published_at FROM read_parquet('{ver}')
WHERE is_release AND published_at IS NOT NULL AND Name IN (SELECT name FROM names)""")


def judge(con):
    con.execute(EVER_SQL)
    con.execute(AT_TIME_SQL)
    con.execute(CLASSIFY_SQL)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="쌍별 판정을 쓸 CSV 경로")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--memory", default="24GB")
    a = ap.parse_args(argv)

    con = duckdb.connect()
    load_inputs(con, a.threads, a.memory)
    judge(con)
    print("tier          pairs  dep_ever  dep_at_time  reverse_ever  both")
    for row in con.execute(SUMMARY_SQL).fetchall():
        tier, n, ever, at, rev, both = row
        print(f"{tier:<12}{n:>7}{ever:>8} ({ever / n:5.1%}){at:>8} ({at / n:5.1%}){rev:>8} ({rev / n:5.1%}){both:>6}")
    print("\ntier       from_pkgs  top1_dep_ever  top1_dep_at_time")
    for tier, n, ever, at in con.execute(TOP1_SQL).fetchall():
        print(f"{tier:<12}{n:>8}{ever:>9} ({ever / n:5.1%}){at:>9} ({at / n:5.1%})")
    if a.out:
        con.execute(f"""COPY (SELECT tier, from_pkg, to_pkg, votes, last_seen, dep_ever, dep_at_time, reverse_ever
                              FROM judged ORDER BY tier, from_pkg, votes DESC, to_pkg)
                        TO '{a.out.replace(os.sep, "/")}' (HEADER, DELIMITER ',')""")
        print(f"\n쌍별 판정 → {a.out}")


if __name__ == "__main__":
    main()
