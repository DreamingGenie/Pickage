"""AI 학습 1차 후보 속성 예시 CSV 생성 — 마이그레이션 이동쌍 · dependencies · peerDependencies

입력  data/raw/requirements, data/raw/versions_full (2026-08-31 스냅샷),
      datasets/deprecated_replacement_260831/deprecated_replacement_20260831.jsonl
출력  datasets/feature_candidates_260908/*.csv (5개, 각 100건, UTF-8 BOM)
실행  .venv-bq/Scripts/python.exe pipeline/duckdb/build_feature_candidates.py   (약 8분, 중간 결과 data/feature_candidates.duckdb)

이동쌍 계산은 docs/설계_마이그레이션쌍_탐지_260831.md 의 0~4단계를 그대로 따른다.
- 모집단: 아래 TARGETS 63개 중 하나라도 regular Dependencies 에 가진 적이 있는 패키지(약 209만 개)의 릴리스 이력(약 1,900만 행)
- 라인 = major>0 이면 major, 0.x 는 0.minor · 라인 안에서 발행시각 순 정렬
- 전이마다 removed/added 계산 → removed ∈ TARGETS 인 이벤트 → 표 1/len(added)
- lift = (X 제거 전이 중 Y 추가 비율) / (이 모집단의 전체 전이 중 Y 추가 비율)  ※ 분모가 전수가 아니라 이 모집단이다
"""
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2].as_posix()  # 리포 루트
R = f"{ROOT}/data/raw/requirements/**/*.parquet"
V = f"{ROOT}/data/raw/versions_full/snapshot=2026-08-31/*.parquet"
J = f"{ROOT}/datasets/deprecated_replacement_260831/deprecated_replacement_20260831.jsonl"
OUT = f"{ROOT}/datasets/feature_candidates_260908"
DB = f"{ROOT}/data/feature_candidates.duckdb"

TARGETS = ['moment', 'request', 'node-sass', 'tslint', 'left-pad', 'node-uuid', '@hapi/joi', 'babel-eslint', 'gulp-util',
           'coffee-script', 'jade', 'request-promise', 'istanbul', 'mkdirp', 'rimraf', 'querystring', 'uuid', 'lodash',
           'underscore', 'bluebird', 'q', 'chalk', 'colors', 'faker', 'tslib', 'core-js', 'node-fetch', 'axios', 'got',
           'superagent', 'moment-timezone', 'crypto-js', 'md5', 'bcrypt', 'bcryptjs', 'jsonwebtoken', 'body-parser',
           'express', 'koa', 'webpack', 'gulp', 'grunt', 'mocha', 'jest', 'tape', 'enzyme', 'react-addons-test-utils',
           'react-router', 'flow-bin', 'babel-core', '@babel/polyfill', 'prop-types', 'create-react-class', 'vue-cli',
           'nodemon', 'forever', 'pm2', 'jshint', 'eslint', 'tsc', 'typescript', 'babel-preset-es2015', 'babel-preset-env']
EVENT_SAMPLE_TARGETS = ['moment', 'request', 'node-sass', 'jade', 'gulp-util', 'bcrypt', '@hapi/joi', 'underscore',
                        'node-uuid', 'chalk', 'faker', 'q', 'querystring', 'coffee-script', 'jsonwebtoken', 'node-fetch',
                        'uuid', 'mkdirp', 'colors', 'babel-eslint']

t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:6.0f}s]", *a)


con = duckdb.connect(DB)
con.execute("SET threads=8; SET memory_limit='12GB'; SELECT setseed(0.42)")


def save(df, name):
    df.to_csv(f"{OUT}/{name}", index=False, encoding="utf-8-sig")
    log(name, len(df))


def quoted(xs):
    return ",".join("'" + x + "'" for x in xs)


con.execute(f"CREATE OR REPLACE TABLE targets AS SELECT unnest([{quoted(TARGETS)}]) AS t")

# ---------- 마이그레이션 이동쌍 ----------
con.execute(f"""CREATE OR REPLACE TABLE dep_pkgs AS
SELECT DISTINCT Name FROM read_parquet('{R}')
WHERE len(list_intersect(list_transform(Dependencies, x -> x.Name), (SELECT list(t) FROM targets))) > 0""")
log("dependents", con.execute("SELECT count(*) FROM dep_pkgs").fetchone())

con.execute(f"""CREATE OR REPLACE TABLE rel AS
SELECT r.Name, r.Version, v.published_at, v.source_repo,
       list_sort(list_transform(r.Dependencies, x -> x.Name)) AS deps
FROM read_parquet('{R}') r JOIN read_parquet('{V}') v ON v.Name=r.Name AND v.Version=r.Version
WHERE r.Name IN (SELECT Name FROM dep_pkgs) AND v.is_release AND v.published_at IS NOT NULL""")
log("releases", con.execute("SELECT count(*) FROM rel").fetchone())

con.execute(r"""CREATE OR REPLACE TABLE seq AS
SELECT Name, Version, published_at, deps,
  CASE WHEN try_cast(regexp_extract(Version,'^(\d+)\.(\d+)',1) AS INT) > 0 THEN regexp_extract(Version,'^(\d+)\.(\d+)',1)
       ELSE '0.' || regexp_extract(Version,'^(\d+)\.(\d+)',2) END AS line,
  CASE WHEN Name LIKE '@%' THEN split_part(Name,'/',1)
       WHEN source_repo IS NOT NULL THEN regexp_replace(lower(source_repo),'\.git$|^git\+|^https?://|^git://|^ssh://git@','','g')
       ELSE Name END AS publisher
FROM rel WHERE regexp_matches(Version,'^\d+\.\d+')""")

con.execute("""CREATE OR REPLACE TABLE trans AS
SELECT Name, publisher, line, lag(Version) OVER w AS from_version, Version AS to_version, published_at AS to_ts,
  list_filter(lag(deps) OVER w, x -> NOT list_contains(deps, x)) AS removed,
  list_filter(deps, x -> NOT list_contains(lag(deps) OVER w, x)) AS added
FROM seq WINDOW w AS (PARTITION BY Name, line ORDER BY published_at) QUALIFY from_version IS NOT NULL""")
n_trans = con.execute("SELECT count(*) FROM trans").fetchone()[0]
log("transitions", n_trans)

con.execute("""CREATE OR REPLACE TABLE events AS
SELECT t.Name AS dependent, publisher, line, from_version, to_version, to_ts, x AS removed_pkg, added,
       len(added) AS added_count, 1.0/len(added) AS vote_each
FROM trans t, unnest(removed) AS u(x) WHERE x IN (SELECT t FROM targets) AND len(added) > 0""")
log("events", con.execute("SELECT count(*) FROM events").fetchone())

con.execute(f"""CREATE OR REPLACE TABLE base AS
SELECT y AS to_pkg, count(*)::DOUBLE / {n_trans} AS b_rate FROM trans, unnest(added) AS u(y) GROUP BY y""")

con.execute("""CREATE OR REPLACE TABLE pairs AS
WITH rm AS (SELECT removed_pkg, count(*) AS removal_events FROM events GROUP BY 1),
     ev AS (SELECT removed_pkg AS from_pkg, y AS to_pkg, sum(vote_each) AS votes, count(*) AS co_events,
                   count(DISTINCT publisher || '|' || strftime(to_ts,'%Y-%m')) AS publisher_months
            FROM events, unnest(added) AS u(y) WHERE y <> removed_pkg GROUP BY 1,2)
SELECT ev.from_pkg, ev.to_pkg, ev.votes, ev.co_events, ev.publisher_months, rm.removal_events,
       ev.co_events::DOUBLE/rm.removal_events AS a_rate, base.b_rate,
       (ev.co_events::DOUBLE/rm.removal_events)/base.b_rate AS lift
FROM ev JOIN rm ON rm.removed_pkg = ev.from_pkg JOIN base ON base.to_pkg = ev.to_pkg""")

save(con.execute("""
WITH ex AS (SELECT removed_pkg, y AS to_pkg, dependent, from_version, to_version, to_ts, added_count,
                   row_number() OVER (PARTITION BY removed_pkg, y ORDER BY added_count, to_ts DESC) rn
            FROM events, unnest(added) AS u(y))
SELECT p.from_pkg, p.to_pkg, round(p.votes,1) AS votes, p.co_events, p.removal_events, p.publisher_months,
       round(p.a_rate*100,2) AS a_pct, round(p.b_rate*100,3) AS b_pct, round(p.lift,1) AS lift,
       ex.dependent AS example_dependent, ex.from_version AS example_from_version, ex.to_version AS example_to_version,
       strftime(ex.to_ts,'%Y-%m-%d') AS example_to_date
FROM pairs p JOIN ex ON ex.removed_pkg=p.from_pkg AND ex.to_pkg=p.to_pkg AND ex.rn=1
WHERE p.lift>=5 AND p.votes>=12 AND p.publisher_months>=10 AND p.a_rate>=0.03
ORDER BY p.votes DESC LIMIT 100""").fetchdf(), "migration_pairs_100.csv")

save(con.execute(f"""
SELECT dependent, publisher, line, from_version, to_version, strftime(to_ts,'%Y-%m-%d %H:%M:%S') AS to_published_at,
       removed_pkg, array_to_string(added,'|') AS added_pkgs, added_count, round(vote_each,3) AS vote_each
FROM (SELECT *, row_number() OVER (PARTITION BY removed_pkg ORDER BY added_count, random()) rn
      FROM events WHERE removed_pkg IN ({quoted(EVENT_SAMPLE_TARGETS)}))
WHERE rn<=5 ORDER BY removed_pkg, rn""").fetchdf(), "migration_events_100.csv")

# ---------- deprecated 쌍 × requirements(최신 릴리스) ----------
con.execute(f"CREATE OR REPLACE VIEW d AS SELECT * FROM read_json_auto('{J}')")
con.execute(f"""CREATE OR REPLACE TABLE lat AS
SELECT Name, Version, Description FROM (
  SELECT Name, Version, Description, row_number() OVER (PARTITION BY Name ORDER BY ordinal DESC) rn
  FROM read_parquet('{V}') WHERE is_release AND (Name IN (SELECT name FROM d) OR Name IN (SELECT replacement FROM d))
) WHERE rn=1""")
con.execute(f"""CREATE OR REPLACE TABLE req AS
SELECT r.Name, r.Version, lat.Description,
       list_sort(list_transform(r.Dependencies, x -> x.Name)) AS deps,
       list_sort(list_transform(r.Dependencies, x -> x.Name || '@' || x.Requirement)) AS deps_req,
       list_sort(list_transform(r.PeerDependencies, x -> x.Name)) AS peers,
       list_sort(list_transform(r.PeerDependencies, x -> x.Name || '@' || x.Requirement)) AS peers_req
FROM read_parquet('{R}') r JOIN lat USING (Name, Version)""")

DESC_JAC = ("round(CASE WHEN length(coalesce(a.Description,''))>=2 AND length(coalesce(b.Description,''))>=2 "
            "THEN jaccard(lower(a.Description), lower(b.Description)) ELSE 0 END,3)")

# 패키지 1개당 1행 — 모델이 실제로 받는 입력 형태 (README §2-3a). 처음 만든 표본은 별도 시드(0.7)였으므로 재생성 시 행이 바뀐다.
save(con.execute("""
SELECT Name AS package, Version AS version, Description AS description,
       array_to_string(deps,'|') AS dependencies, len(deps) AS dependency_count,
       array_to_string(peers,'|') AS peer_dependencies
FROM req WHERE len(deps)>=2 ORDER BY random() LIMIT 100""").fetchdf(), "dependencies_per_package_100.csv")

save(con.execute(f"""
WITH j AS (
 SELECT d.name AS deprecated_pkg, a.Version AS deprecated_version, d.replacement AS replacement_pkg, b.Version AS replacement_version,
   array_to_string(a.deps_req,'|') AS deprecated_dependencies, array_to_string(b.deps_req,'|') AS replacement_dependencies,
   len(a.deps) AS n_dep_a, len(b.deps) AS n_dep_b, array_to_string(list_intersect(a.deps,b.deps),'|') AS shared_dependencies,
   round(len(list_intersect(a.deps,b.deps))::DOUBLE/len(list_distinct(a.deps||b.deps)),3) AS dep_jaccard,
   {DESC_JAC} AS desc_jaccard, a.Description AS deprecated_description, b.Description AS replacement_description
 FROM d JOIN req a ON a.Name=d.name JOIN req b ON b.Name=d.replacement
 WHERE len(a.deps)>=2 AND len(b.deps)>=2 AND d.replacement_alive)
SELECT * FROM ((SELECT * FROM j WHERE desc_jaccard<0.5 ORDER BY random() LIMIT 50)
               UNION ALL (SELECT * FROM j WHERE desc_jaccard>=0.5 ORDER BY random() LIMIT 50))
ORDER BY desc_jaccard""").fetchdf(), "dependencies_100.csv")

save(con.execute(f"""
SELECT d.name AS deprecated_pkg, a.Version AS deprecated_version, d.replacement AS replacement_pkg, b.Version AS replacement_version,
   array_to_string(a.peers_req,'|') AS deprecated_peer_dependencies, array_to_string(b.peers_req,'|') AS replacement_peer_dependencies,
   array_to_string(list_intersect(a.peers,b.peers),'|') AS shared_peers, len(a.peers) AS n_peer_a, len(b.peers) AS n_peer_b,
   CASE WHEN len(b.peers)=0 THEN 'replacement_has_no_peer'
        WHEN len(list_intersect(a.peers,b.peers))>0 THEN 'match' ELSE 'mismatch' END AS peer_match,
   {DESC_JAC} AS desc_jaccard, a.Description AS deprecated_description, b.Description AS replacement_description
FROM d JOIN req a ON a.Name=d.name JOIN req b ON b.Name=d.replacement
WHERE len(a.peers)>=1 AND d.replacement_alive
ORDER BY random() LIMIT 100""").fetchdf(), "peer_dependencies_100.csv")
log("done")
