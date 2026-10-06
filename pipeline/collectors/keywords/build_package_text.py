"""keywords raw + deps.dev Description → package_text Parquet (AI 학습 데이터).

규칙: docs/api & data/수집결과_keywords_프로파일_260908.md §4
  1) name 기준 중복 제거(최신 fetched_at)
  2) status removed·unpublished 제외
  3) 스팸 표시(행은 남기고 is_spam만): 같은 저장소에 패키지 ≥ 100 · keywords 보유율 < 15% · 저장소 최대 dependents < 20
     · (별 < 10 또는 전 패키지 발행 기간 < 90일) · @types/* 제외. 정상 모노레포는 dependents·별·기간에서 빠진다
  4) description = coalesce(ecosyste.ms, deps.dev 최신 버전 Description, repo.description) + description_source
  5) keywords_source = npm / github_topics(저장소 패키지 ≤ 20일 때만) / none. topics는 소문자·불용어 제거·중복 제거
  6) download_rank = --rank-list(기본 다운로드 상위 10만, datasets/targets/rank_top100k_20260902.csv)에서
     조인한 고정 순위. 목록 밖이면 NULL — registry·downloads 수집 대상이 아니라는 뜻이다(S15P21A506-402).
     기존 `rank` 컬럼(ecosyste.ms 목록 API를 이번 --run 시점에 새로 호출해 얻은 순위)과는 다른 값이다 —
     `rank`는 그날그날 바뀌고, `download_rank`는 실제로 리포트 데이터가 존재하는 고정 범위를 가리킨다.
  7) 출력 Parquet(zstd) + summary.json

사용:
  python build_package_text.py --run 2026-09-08
  python build_package_text.py --run 2026-09-08 --out data/keywords/package_text --no-depsdev   # deps.dev Parquet 없을 때
"""
import argparse
import json
import os
import sys
import time

import duckdb

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO_ROOT = os.path.abspath(os.path.join(ROOT, ".."))
# download_rank 의 고정 출처. pipeline/duckdb/build_package_dependents.py 의 RANK 와 같은 파일 —
# registry·downloads 수집기가 실제로 데이터를 모은 대상 그 자체다(pipeline/weekly/steps.py 의
# TARGETS_SOURCE). 이 스크립트의 --run 마다 새로 계산되는 `rank` 컬럼과 혼동하지 말 것.
RANK_LIST = os.path.join(REPO_ROOT, "datasets", "targets", "rank_top100k_20260902.csv")

# 저장소 topics 중 패키지 변별력이 없는 것 (검증문서 §4-3)
TOPIC_STOP = ["hacktoberfest", "javascript", "typescript", "nodejs", "node", "npm", "npm-package", "js", "ts",
              "library", "open-source", "opensource", "package", "module", "framework", "frontend", "backend",
              "web", "awesome", "good-first-issue", "help-wanted", "hacktoberfest2020", "hacktoberfest2021",
              "hacktoberfest2022", "hacktoberfest2023", "hacktoberfest-accepted", "first-timers-only"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--raw", default=os.path.join(ROOT, "data", "keywords", "raw"))
    ap.add_argument("--depsdev", default=os.path.join(ROOT, "data", "raw", "versions_full"))
    ap.add_argument("--no-depsdev", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "keywords", "package_text"))
    ap.add_argument("--rank-list", default=RANK_LIST,
                     help="download_rank 조인용 고정 목록 CSV. name·rank 열만 있으면 된다 "
                          "(기본: 다운로드 상위 10만)")
    ap.add_argument("--spam-min-pkgs", type=int, default=100)
    ap.add_argument("--spam-max-kw-rate", type=float, default=0.15)
    ap.add_argument("--spam-max-dependents", type=int, default=20, help="저장소 내 최대 dependents가 이 값 이상이면 스팸 아님")
    ap.add_argument("--spam-max-stars", type=int, default=10)
    ap.add_argument("--spam-max-span-days", type=int, default=90, help="전 패키지 발행이 이 기간 안이면 대량 생성 의심")
    ap.add_argument("--monorepo-max", type=int, default=20, help="저장소 패키지 수가 이보다 크면 topics를 쓰지 않음")
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    raw_glob = os.path.join(a.raw, f"run={a.run}", "part-*.jsonl.gz").replace("\\", "/")
    dd_glob = os.path.join(a.depsdev, "snapshot=*", "part-*.parquet").replace("\\", "/")
    out_parquet = os.path.join(a.out, f"package_text_{a.run}.parquet")
    t0 = time.time()
    con = duckdb.connect()
    con.execute(f"SET threads={a.threads}; SET memory_limit='10GB'")

    con.execute(f"""
    CREATE TABLE raw AS
    SELECT name, rank, page, fetched_at, description, keywords, downloads_last_month, dependent_packages_count,
           latest_release_number, latest_release_published_at, licenses, status, repository_url, last_synced_at,
           repo.full_name AS repo_full_name, repo.description AS repo_description, repo.topics AS repo_topics,
           repo.language AS repo_language, repo.stargazers_count AS repo_stars, repo.archived AS repo_archived
    FROM read_json('{raw_glob}', format='newline_delimited', union_by_name=true, maximum_object_size=10000000)""")
    n_raw = con.sql("SELECT count(*) FROM raw").fetchone()[0]
    # 1) 중복 제거
    con.execute("""CREATE TABLE dedup AS
      SELECT * EXCLUDE rn FROM (SELECT *, row_number() OVER (PARTITION BY name ORDER BY fetched_at DESC, rank) rn FROM raw) WHERE rn = 1""")
    n_dedup = con.sql("SELECT count(*) FROM dedup").fetchone()[0]
    # 2) removed·unpublished 제외
    con.execute("CREATE TABLE alive AS SELECT * FROM dedup WHERE status IS NULL OR status NOT IN ('removed','unpublished')")
    n_alive = con.sql("SELECT count(*) FROM alive").fetchone()[0]
    # 3) 저장소 집계 → 스팸·모노레포
    # 스팸 농장 신호(09-08 실측): keywords 거의 없음 + 아무도 의존하지 않음 + (별 거의 없음 또는 전 패키지가 90일 안에 발행)
    # 정상 모노레포(aws-sdk-js-v3·expo/google-fonts·DefinitelyTyped)는 dependents·별·발행 기간 중 하나 이상에서 걸러진다
    con.execute(f"""CREATE TABLE repo_stat AS
      SELECT repo_full_name, count(*) AS repo_pkg_count,
             avg(CASE WHEN len(keywords) > 0 THEN 1.0 ELSE 0.0 END) AS repo_kw_rate,
             max(coalesce(dependent_packages_count, 0)) AS repo_max_dependents,
             max(coalesce(repo_stars, 0)) AS repo_max_stars,
             date_diff('day', min(latest_release_published_at), max(latest_release_published_at)) AS repo_release_span_days
      FROM alive WHERE repo_full_name IS NOT NULL GROUP BY 1""")
    # 4) deps.dev Description
    if a.no_depsdev:
        con.execute("CREATE TABLE dd AS SELECT NULL::VARCHAR AS name, NULL::VARCHAR AS description_depsdev WHERE false")
    else:
        con.execute(f"""CREATE TABLE dd AS
          SELECT Name AS name, arg_max(Description, ordinal) AS description_depsdev
          FROM read_parquet('{dd_glob}', hive_partitioning=true) GROUP BY Name""")
    # 5) download_rank — 고정 목록 조인 (S15P21A506-402).
    #    이름이 겹치는 행은 순위가 낮은(=상위) 쪽만 남긴다(build_package_dependents.py와 같은 이유 —
    #    실측상 상위 10만 CSV에 이름 중복이 몇 건 있다).
    con.execute(f"""CREATE TABLE rank_list AS
      SELECT trim(name) AS name, min(rank) AS download_rank
      FROM read_csv_auto('{a.rank_list}') WHERE name IS NOT NULL GROUP BY 1""")
    stop_sql = ",".join(f"'{s}'" for s in TOPIC_STOP)
    con.execute(f"""
    CREATE TABLE package_text AS
    WITH j AS (
      SELECT a.*, r.repo_pkg_count, r.repo_kw_rate, r.repo_max_dependents, r.repo_max_stars, r.repo_release_span_days,
             d.description_depsdev, k.download_rank,
             nullif(trim(a.description), '') AS desc_eco,
             nullif(trim(d.description_depsdev), '') AS desc_dd,
             nullif(trim(a.repo_description), '') AS desc_repo,
             list_distinct(list_filter(list_transform(coalesce(a.repo_topics, []), t -> lower(trim(t))),
                                       t -> t <> '' AND t NOT IN ({stop_sql}))) AS topics_clean
      FROM alive a
      LEFT JOIN repo_stat r USING (repo_full_name)
      LEFT JOIN dd d USING (name)
      LEFT JOIN rank_list k USING (name)
    )
    SELECT
      name, rank, download_rank, downloads_last_month, dependent_packages_count, status,
      coalesce(desc_eco, desc_dd, desc_repo) AS description,
      CASE WHEN desc_eco IS NOT NULL THEN 'npm' WHEN desc_dd IS NOT NULL THEN 'depsdev'
           WHEN desc_repo IS NOT NULL THEN 'repo' ELSE 'none' END AS description_source,
      coalesce(keywords, []) AS keywords,
      CASE WHEN coalesce(repo_pkg_count, 1) <= {a.monorepo_max} THEN topics_clean ELSE [] END AS topics,
      CASE WHEN len(coalesce(keywords, [])) > 0 THEN 'npm'
           WHEN coalesce(repo_pkg_count, 1) <= {a.monorepo_max} AND len(topics_clean) > 0 THEN 'github_topics'
           ELSE 'none' END AS keywords_source,
      repo_full_name, coalesce(repo_pkg_count, 0) AS repo_pkg_count, repo_language, repo_stars, repo_archived,
      (repo_pkg_count >= {a.spam_min_pkgs} AND repo_kw_rate < {a.spam_max_kw_rate}
       AND repo_max_dependents < {a.spam_max_dependents}
       AND (repo_max_stars < {a.spam_max_stars} OR repo_release_span_days < {a.spam_max_span_days})
       AND name NOT LIKE '@types/%') IS TRUE AS is_spam,
      latest_release_number, latest_release_published_at, licenses, repository_url, last_synced_at, fetched_at
    FROM j
    ORDER BY rank""")
    con.execute(f"COPY package_text TO '{out_parquet.replace(chr(92), '/')}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 100000)")

    s = {}
    s["rows"] = {"raw": n_raw, "dedup": n_dedup, "alive(removed·unpublished 제외)": n_alive}
    s["download_rank"] = {
        "in_scope(리포트 가능)": con.sql("SELECT count(*) FROM package_text WHERE download_rank IS NOT NULL").fetchone()[0],
        "out_of_scope(목록 밖)": con.sql("SELECT count(*) FROM package_text WHERE download_rank IS NULL").fetchone()[0],
        "rank_list": a.rank_list,
    }
    s["by_keywords_source"] = dict(con.sql("SELECT keywords_source, count(*) FROM package_text GROUP BY 1 ORDER BY 1").fetchall())
    s["by_description_source"] = dict(con.sql("SELECT description_source, count(*) FROM package_text GROUP BY 1 ORDER BY 1").fetchall())
    s["is_spam"] = con.sql("SELECT count(*) FROM package_text WHERE is_spam").fetchone()[0]
    s["spam_repos_top"] = con.sql("SELECT repo_full_name, count(*) n FROM package_text WHERE is_spam GROUP BY 1 ORDER BY n DESC LIMIT 10").fetchall()
    s["train_ready"] = {
        "keywords∧description (not spam)": con.sql("SELECT count(*) FROM package_text WHERE NOT is_spam AND keywords_source='npm' AND description IS NOT NULL").fetchone()[0],
        "(keywords∨topics)∧description (not spam)": con.sql("SELECT count(*) FROM package_text WHERE NOT is_spam AND keywords_source<>'none' AND description IS NOT NULL").fetchone()[0],
        "description only (eval layer, not spam)": con.sql("SELECT count(*) FROM package_text WHERE NOT is_spam AND keywords_source='none' AND description IS NOT NULL").fetchone()[0],
        "no text at all": con.sql("SELECT count(*) FROM package_text WHERE description IS NULL AND keywords_source='none'").fetchone()[0],
    }
    s["file"] = {"path": out_parquet, "bytes": os.path.getsize(out_parquet), "mb": round(os.path.getsize(out_parquet) / 1e6, 1)}
    s["params"] = {"spam_min_pkgs": a.spam_min_pkgs, "spam_max_kw_rate": a.spam_max_kw_rate,
                   "spam_max_dependents": a.spam_max_dependents, "spam_max_stars": a.spam_max_stars,
                   "spam_max_span_days": a.spam_max_span_days, "monorepo_max": a.monorepo_max,
                   "depsdev": not a.no_depsdev, "topic_stop": TOPIC_STOP}
    s["elapsed_s"] = round(time.time() - t0)
    with open(os.path.join(a.out, f"summary_{a.run}.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(s, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
