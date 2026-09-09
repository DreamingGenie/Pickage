"""마이그레이션 이동쌍 전수 계산 — npm 전체 패키지 대상 (removed X → added Y)

입력  data/raw/requirements (NPMRequirements), data/raw/versions_full (PackageVersions) — 2026-08-31 스냅샷
출력  datasets/migration_pairs_260908/
        migration_pairs_all.csv      lift≥5 AND votes≥3 인 (from, to) 쌍 전부 (UTF-8 BOM)
        migration_pairs_strict.csv   README 필터(lift≥5, votes≥12, publisher_months≥10, A≥3%) 통과 쌍
        migration_pairs_recommended.csv  권고 하한(lift≥5, votes≥8, publisher_months≥5, share≥10%) 통과 쌍
        removal_stats.csv            X별 이탈 요약(제거 총수·대체 없이 제거·대체 동반 제거·dependents). removals_total≥3 만
        removal_by_year.csv          X × 연도 이탈 추이. 같은 X 기준
        stats.json                   규모 통계(패키지 수·전이 수·이벤트 수·파일 크기)
      data/migration_pairs/migration_events.parquet   제거 이벤트 원시 전부(모델 최소 단위)
      data/migration_pairs/removal_stats.parquet, removal_by_year.parquet   위 두 표 필터 없이 전부
실행  .venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py   (중간 결과 data/migration_pairs.duckdb)

계산은 docs/설계_마이그레이션쌍_탐지_260831.md 0~4단계. build_feature_candidates.py 와 같은 로직이되
- TARGETS 제한 없이 모든 removed 패키지를 X 로 본다 (분모 B 도 npm 전수 전이)
- 5-1 반영: 다음 버전의 Peer/OptionalDependencies 로 옮겨진 이름은 제거가 아니라 재분류로 보고 X 후보에서 뺀다
- 7단계(S15P21A506-281): trans 를 지우기 전에 "대체 없이 제거"(X 를 뺐지만 같은 전이에서 아무것도 안 넣음) 와
  연도별 이탈 수를 removal_stats / removal_by_year 로 집계. 점유율은 votes 기준 share 와 함께 (배포주체, 월) 기준 share_pm 도 낸다
"""
import json
import os
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2].as_posix()  # 리포 루트
R = f"{ROOT}/data/raw/requirements/**/*.parquet"
V = f"{ROOT}/data/raw/versions_full/snapshot=2026-08-31/*.parquet"
OUT = f"{ROOT}/datasets/migration_pairs_260908"
EV_DIR = f"{ROOT}/data/migration_pairs"
DB = f"{ROOT}/data/migration_pairs.duckdb"
TMP = f"{ROOT}/data/duckdb_tmp"
for d in (OUT, EV_DIR, TMP):
    os.makedirs(d, exist_ok=True)

t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)


def one(sql):
    return con.execute(sql).fetchone()[0]


con = duckdb.connect(DB)
con.execute(f"SET threads=12; SET memory_limit='40GB'; SET temp_directory='{TMP}'; SET preserve_insertion_order=false")

stats = {}

# 1) 릴리스 + 의존성 (regular / peer+optional 이름 분리)
con.execute(f"""CREATE OR REPLACE TABLE rel AS
SELECT r.Name, r.Version, v.published_at, v.source_repo,
       list_sort(list_transform(r.Dependencies, x -> x.Name)) AS deps,
       coalesce(list_transform(r.PeerDependencies, x -> x.Name), []::VARCHAR[])
         || coalesce(list_transform(r.OptionalDependencies, x -> x.Name), []::VARCHAR[]) AS nonreg
FROM read_parquet('{R}') r JOIN read_parquet('{V}') v ON v.Name=r.Name AND v.Version=r.Version
WHERE v.is_release AND v.published_at IS NOT NULL AND regexp_matches(r.Version,'^\\d+\\.\\d+')""")
stats["releases"] = one("SELECT count(*) FROM rel")
stats["packages_total"] = one("SELECT count(DISTINCT Name) FROM rel")
log("releases", stats["releases"], "packages", stats["packages_total"])

# 2) 라인·배포주체
con.execute(r"""CREATE OR REPLACE TABLE seq AS
SELECT Name, Version, published_at, deps, nonreg,
  CASE WHEN try_cast(regexp_extract(Version,'^(\d+)\.(\d+)',1) AS INT) > 0 THEN regexp_extract(Version,'^(\d+)\.(\d+)',1)
       ELSE '0.' || regexp_extract(Version,'^(\d+)\.(\d+)',2) END AS line,
  CASE WHEN Name LIKE '@%' THEN split_part(Name,'/',1)
       WHEN source_repo IS NOT NULL THEN regexp_replace(lower(source_repo),'\.git$|^git\+|^https?://|^git://|^ssh://git@','','g')
       ELSE Name END AS publisher
FROM rel""")
con.execute("DROP TABLE rel")
log("seq done")

# 3) 연속 릴리스 전이 (removed / added / 재분류)
con.execute("""CREATE OR REPLACE TABLE trans AS
SELECT Name, publisher, line, from_version, to_version, to_ts,
  list_filter(removed_raw, x -> NOT list_contains(nonreg, x)) AS removed,
  list_filter(removed_raw, x -> list_contains(nonreg, x)) AS reclassified,
  added
FROM (
  SELECT Name, publisher, line, lag(Version) OVER w AS from_version, Version AS to_version, published_at AS to_ts, nonreg,
    list_filter(lag(deps) OVER w, x -> NOT list_contains(deps, x)) AS removed_raw,
    list_filter(deps, x -> NOT list_contains(lag(deps) OVER w, x)) AS added
  FROM seq WINDOW w AS (PARTITION BY Name, line ORDER BY published_at) QUALIFY from_version IS NOT NULL
)""")
con.execute("DROP TABLE seq")
n_trans = one("SELECT count(*) FROM trans")
stats["transitions"] = n_trans
stats["packages_with_transition"] = one("SELECT count(DISTINCT Name) FROM trans")
stats["transitions_with_dep_change"] = one("SELECT count(*) FROM trans WHERE len(removed)>0 OR len(added)>0")
stats["transitions_removed_and_added"] = one("SELECT count(*) FROM trans WHERE len(removed)>0 AND len(added)>0")
stats["reclassified_to_peer_or_optional"] = one("SELECT coalesce(sum(len(reclassified)),0) FROM trans")
log("transitions", stats)

# 4) 제거 이벤트 (추가가 있는 것만) → 표 분배
con.execute("""CREATE OR REPLACE TABLE events AS
SELECT t.Name AS dependent, publisher, line, from_version, to_version, to_ts, x AS removed_pkg, added,
       len(added) AS added_count, 1.0/len(added) AS vote_each
FROM trans t, unnest(removed) AS u(x) WHERE len(added) > 0""")
stats["removal_events"] = one("SELECT count(*) FROM events")
stats["removed_pkgs_distinct"] = one("SELECT count(DISTINCT removed_pkg) FROM events")
stats["dependents_with_event"] = one("SELECT count(DISTINCT dependent) FROM events")
log("events", stats["removal_events"], "distinct removed", stats["removed_pkgs_distinct"])

# 5) 기저율 B (npm 전수 전이 기준)
con.execute(f"""CREATE OR REPLACE TABLE base AS
SELECT y AS to_pkg, count(*)::DOUBLE / {n_trans} AS b_rate FROM trans, unnest(added) AS u(y) GROUP BY y""")

# 5-2) X 별 이탈 요약 / X × 연도 이탈 추이 — 추가 여부 무관하게 X 를 뺀 전이 전부 (trans 가 남아 있을 때만 가능)
#      removals_with_replacement 는 pairs.removal_events 와 같아야 한다. added 가 NULL 인 전이는 "대체 없음" 으로 센다
con.execute("""CREATE OR REPLACE TABLE removal_stats AS
SELECT x AS removed_pkg,
       count(*)                                                AS removals_total,
       count(*) FILTER (WHERE coalesce(len(added), 0) = 0)     AS removals_no_replacement,
       count(*) FILTER (WHERE len(added) > 0)                  AS removals_with_replacement,
       count(DISTINCT Name)                                    AS dependents,
       count(DISTINCT publisher || '|' || strftime(to_ts, '%Y-%m')) AS publisher_months,
       min(to_ts) AS first_seen, max(to_ts) AS last_seen
FROM trans, unnest(removed) AS u(x) GROUP BY 1""")
con.execute("""CREATE OR REPLACE TABLE removal_by_year AS
SELECT x AS removed_pkg, year(to_ts) AS year,
       count(*)                                                AS removals,
       count(*) FILTER (WHERE coalesce(len(added), 0) = 0)     AS removals_no_replacement,
       count(DISTINCT Name)                                    AS dependents
FROM trans, unnest(removed) AS u(x) GROUP BY 1, 2""")
stats["removed_pkgs_any"] = one("SELECT count(*) FROM removal_stats")
stats["removals_total"] = one("SELECT sum(removals_total) FROM removal_stats")
stats["removals_no_replacement_total"] = one("SELECT sum(removals_no_replacement) FROM removal_stats")
log("removal_stats", {k: stats[k] for k in ("removed_pkgs_any", "removals_total", "removals_no_replacement_total")})
con.execute("DROP TABLE trans")

# 6) 쌍 집계 + lift
con.execute("""CREATE OR REPLACE TABLE pairs AS
WITH rm AS (SELECT removed_pkg, count(*) AS removal_events FROM events GROUP BY 1),
     ev AS (SELECT removed_pkg AS from_pkg, y AS to_pkg, sum(vote_each) AS votes, count(*) AS co_events,
                   count(DISTINCT publisher || '|' || strftime(to_ts,'%Y-%m')) AS publisher_months,
                   count(DISTINCT dependent) AS dependents,
                   min(to_ts) AS first_seen, max(to_ts) AS last_seen
            FROM events, unnest(added) AS u(y) WHERE y <> removed_pkg GROUP BY 1,2)
SELECT ev.from_pkg, ev.to_pkg, ev.votes, ev.co_events, ev.publisher_months, ev.dependents, rm.removal_events,
       ev.co_events::DOUBLE/rm.removal_events AS a_rate, base.b_rate,
       (ev.co_events::DOUBLE/rm.removal_events)/base.b_rate AS lift, ev.first_seen, ev.last_seen
FROM ev JOIN rm ON rm.removed_pkg = ev.from_pkg JOIN base ON base.to_pkg = ev.to_pkg""")
stats["candidate_pairs_all"] = one("SELECT count(*) FROM pairs")
log("pairs", stats["candidate_pairs_all"])

# share = lift≥5 쌍 안에서 X 전체 표 중 Y 의 비율 / bidirectional = (Y, X) 쌍도 lift≥5·votes≥3 으로 존재
con.execute("""CREATE OR REPLACE TABLE pairs_out AS
SELECT p.*, votes/sum(votes) OVER (PARTITION BY from_pkg) AS share,
       publisher_months/sum(publisher_months) OVER (PARTITION BY from_pkg) AS share_pm,
       EXISTS(SELECT 1 FROM pairs q WHERE q.from_pkg=p.to_pkg AND q.to_pkg=p.from_pkg AND q.lift>=5 AND q.votes>=3) AS bidirectional
FROM pairs p WHERE lift>=5""")

SELECT_COLS = """from_pkg, to_pkg, round(votes,1) AS votes, co_events, removal_events, publisher_months, dependents,
       round(a_rate*100,2) AS a_pct, round(b_rate*100,4) AS b_pct, round(lift,1) AS lift,
       round(share*100,1) AS share_pct, round(share_pm*100,1) AS share_pm_pct, bidirectional,
       strftime(first_seen,'%Y-%m-%d') AS first_seen, strftime(last_seen,'%Y-%m-%d') AS last_seen"""
STRICT = "lift>=5 AND votes>=12 AND publisher_months>=10 AND a_rate>=0.03"
LOOSE = "lift>=5 AND votes>=3"
RECOMMENDED = "lift>=5 AND votes>=8 AND publisher_months>=5 AND share>=0.10"

for name, cond in (("strict", STRICT), ("loose", LOOSE)):
    stats[f"{name}_pairs"] = one(f"SELECT count(*) FROM pairs WHERE {cond}")
    stats[f"{name}_from_pkgs"] = one(f"SELECT count(DISTINCT from_pkg) FROM pairs WHERE {cond}")
    stats[f"{name}_to_pkgs"] = one(f"SELECT count(DISTINCT to_pkg) FROM pairs WHERE {cond}")
    # 이 from_pkg 들을 regular 의존성으로 가진 적 있는 패키지 수 (이동 안내를 받을 수 있는 잠재 대상)
    stats[f"{name}_adopters_of_from_pkgs"] = one(f"""
        SELECT count(DISTINCT r.Name) FROM read_parquet('{R}') r
        WHERE len(list_intersect(list_transform(r.Dependencies, x -> x.Name),
                                 (SELECT list(DISTINCT from_pkg) FROM pairs WHERE {cond}))) > 0""")
    log(name, {k: v for k, v in stats.items() if k.startswith(name)})

# 중간 단계 완화 필터도 참고용으로 카운트
for tag, cond in (("votes5_pm3", "lift>=5 AND votes>=5 AND publisher_months>=3"),
                  ("votes12", "lift>=5 AND votes>=12")):
    stats[f"count_{tag}_pairs"] = one(f"SELECT count(*) FROM pairs WHERE {cond}")
    stats[f"count_{tag}_from_pkgs"] = one(f"SELECT count(DISTINCT from_pkg) FROM pairs WHERE {cond}")

# 7) 출력
for cond, fname in ((STRICT, "migration_pairs_strict.csv"), (LOOSE, "migration_pairs_all.csv"),
                    (RECOMMENDED, "migration_pairs_recommended.csv")):
    con.execute(f"""COPY (SELECT {SELECT_COLS} FROM pairs_out WHERE {cond} ORDER BY from_pkg, votes DESC)
                    TO '{OUT}/{fname}' (HEADER, DELIMITER ',')""")
REMOVAL_MIN = 3  # 이 아래는 통계로 의미가 없고 행이 10만 개 넘게 늘어난다
REMOVAL_COLS = """removed_pkg, removals_total, removals_no_replacement, removals_with_replacement,
       round(removals_no_replacement*100.0/removals_total, 1) AS no_replacement_pct,
       dependents, publisher_months, strftime(first_seen,'%Y-%m-%d') AS first_seen, strftime(last_seen,'%Y-%m-%d') AS last_seen"""
con.execute(f"""COPY (SELECT {REMOVAL_COLS} FROM removal_stats WHERE removals_total >= {REMOVAL_MIN}
                      ORDER BY removals_total DESC, removed_pkg)
                TO '{OUT}/removal_stats.csv' (HEADER, DELIMITER ',')""")
con.execute(f"""COPY (SELECT y.removed_pkg, y.year, y.removals, y.removals_no_replacement, y.dependents
                      FROM removal_by_year y JOIN removal_stats s USING (removed_pkg)
                      WHERE s.removals_total >= {REMOVAL_MIN} ORDER BY y.removed_pkg, y.year)
                TO '{OUT}/removal_by_year.csv' (HEADER, DELIMITER ',')""")
con.execute(f"COPY (SELECT * FROM removal_stats ORDER BY removals_total DESC) TO '{EV_DIR}/removal_stats.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)")
con.execute(f"COPY (SELECT * FROM removal_by_year ORDER BY removed_pkg, year) TO '{EV_DIR}/removal_by_year.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)")
stats["removal_stats_rows_csv"] = one(f"SELECT count(*) FROM removal_stats WHERE removals_total >= {REMOVAL_MIN}")
stats["recommended_pairs"] = one(f"SELECT count(*) FROM pairs_out WHERE {RECOMMENDED}")
stats["recommended_from_pkgs"] = one(f"SELECT count(DISTINCT from_pkg) FROM pairs_out WHERE {RECOMMENDED}")
con.execute(f"""COPY (SELECT dependent, publisher, line, from_version, to_version, to_ts AS to_published_at,
                             removed_pkg, added AS added_pkgs, added_count, vote_each
                      FROM events ORDER BY removed_pkg, to_ts)
                TO '{EV_DIR}/migration_events.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")
con.execute(f"""COPY (SELECT dependent, publisher, line, from_version, to_version,
                             strftime(to_ts,'%Y-%m-%d %H:%M:%S') AS to_published_at,
                             removed_pkg, array_to_string(added,'|') AS added_pkgs, added_count, round(vote_each,4) AS vote_each
                      FROM events ORDER BY removed_pkg, to_ts)
                TO '{EV_DIR}/migration_events.csv' (HEADER, DELIMITER ',')""")

# UTF-8 BOM (팀 공유 CSV 관례)
for f in ("migration_pairs_strict.csv", "migration_pairs_all.csv", "migration_pairs_recommended.csv",
          "removal_stats.csv", "removal_by_year.csv"):
    p = f"{OUT}/{f}"
    with open(p, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\xef\xbb\xbf"):
        with open(p, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + data)

def sz(p):
    return os.path.getsize(p)

stats["file_bytes"] = {
    "migration_pairs_strict.csv": sz(f"{OUT}/migration_pairs_strict.csv"),
    "migration_pairs_all.csv": sz(f"{OUT}/migration_pairs_all.csv"),
    "migration_pairs_recommended.csv": sz(f"{OUT}/migration_pairs_recommended.csv"),
    "removal_stats.csv": sz(f"{OUT}/removal_stats.csv"),
    "removal_by_year.csv": sz(f"{OUT}/removal_by_year.csv"),
    "removal_stats.parquet": sz(f"{EV_DIR}/removal_stats.parquet"),
    "removal_by_year.parquet": sz(f"{EV_DIR}/removal_by_year.parquet"),
    "migration_events.parquet": sz(f"{EV_DIR}/migration_events.parquet"),
    "migration_events.csv": sz(f"{EV_DIR}/migration_events.csv"),
    "migration_pairs.duckdb": sz(DB),
}
stats["input_bytes"] = {
    "requirements_parquet": sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(f"{ROOT}/data/raw/requirements") for f in fs),
    "versions_full_parquet": sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(f"{ROOT}/data/raw/versions_full") for f in fs),
}
stats["elapsed_sec"] = round(time.time() - t0)
with open(f"{OUT}/stats.json", "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2)
log("done", json.dumps(stats, ensure_ascii=False))
