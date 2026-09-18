"""마이그레이션 이동쌍 전수 계산 — npm 전체 패키지 대상 (removed X → added Y)

입력  data/raw/requirements (NPMRequirements), data/raw/versions_full (PackageVersions) — 2026-08-31 스냅샷
출력  datasets/migration_pairs_260908/
        migration_pairs_all.csv      lift≥5 AND votes≥3 인 (from, to) 쌍 전부 (UTF-8 BOM)
        migration_pairs_strict.csv   README 필터(lift≥5, votes≥12, publisher_months≥10, A≥3%) 통과 쌍
        migration_pairs_recommended.csv  권고 하한(lift≥5, votes≥8, publisher_months≥5, share≥10%) 통과 쌍
        removal_stats.csv            X별 이탈 요약(제거 총수·대체 없이 제거·대체 동반 제거·dependents). removals_total≥3 만
        removal_by_year.csv          X × 연도 이탈 추이. 같은 X 기준
        removal_by_period.csv        X × 구간(1y·3y·5y) 이탈 사유. 같은 X 기준
        stats.json                   규모 통계(패키지 수·전이 수·이벤트 수·파일 크기)
      data/migration_pairs/migration_events.parquet   제거 이벤트 원시 전부(모델 최소 단위)
      data/migration_pairs/removal_stats.parquet, removal_by_year.parquet, removal_by_period.parquet
                                                      위 세 표 필터 없이 전부
실행  .venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py   (중간 결과 data/migration_pairs.duckdb)

원천·의존 종류 (S15P21A506-349, 2026-09-14 추가)
  --source depsdev  (기본) deps.dev NPMRequirements · npm 전수 · 실행용 의존만. 위 출력 경로 그대로
  --source registry --kind dev      npm registry 수집분(S15P21A506-280) · 상위 10만 · 개발용 의존
  --source registry --kind regular  같은 입력의 실행용 의존. depsdev 결과의 재분류 과대 계상을 재는 대조군

계산은 docs/설계_마이그레이션쌍_탐지_260831.md 0~4단계. build_feature_candidates.py 와 같은 로직이되
- TARGETS 제한 없이 모든 removed 패키지를 X 로 본다 (분모 B 도 그 모집단의 전수 전이)
- 5-1 반영: 다음 버전의 "다른 의존 칸"으로 옮겨진 이름은 제거가 아니라 재분류로 보고 X 후보에서 뺀다.
  어느 칸을 보는지는 KIND 가 정한다 — regular 면 Dev/Peer/Optional, dev 면 Dependencies/Peer/Optional.
  depsdev 원천에는 Dev 칸 자체가 없어 Peer/Optional 만 본다(그래서 regular→dev 강등이 제거로 남는다. 이게 대조군이 필요한 이유)
- 7단계(S15P21A506-281): trans 를 지우기 전에 "대체 없이 제거"(X 를 뺐지만 같은 전이에서 아무것도 안 넣음) 와
  연도별 이탈 수를 removal_stats / removal_by_year 로 집계. 점유율은 votes 기준 share 와 함께 (배포주체, 월) 기준 share_pm 도 낸다
- 구간별 집계(S15P21A506-378): 화면이 쓰는 1y·3y·5y 로 같은 것을 다시 센다(removal_by_period).
  구간은 겹치고(1y ⊂ 3y ⊂ 5y) 경계는 유지·유입·이탈에서 가져온다 — pipeline/duckdb/removal_periods.py

**이 결과와 유지·유입·이탈(build_dependent_transitions.py)은 세는 단위가 다르다.** 저쪽은 시점 두 개의
선언 집합을 비교한 **패키지 수**이고 이쪽은 연속한 두 릴리스를 훑은 **전이 건수**다. 한 패키지가 넣었다
뺐다를 반복하면 이쪽에서는 여러 건이 된다. 그래서 "이탈 = 대체 동반 + 대체 없음" 이라는 덧셈이 저쪽의
이탈과는 성립하지 않는다. 같은 화면에 놓더라도 더하거나 나누지 말 것.

주의: lift 의 분모 B 는 그 실행의 모집단 전이 수다. depsdev(전수 3,958만)와 registry(상위 10만 726만)는
모집단이 달라 lift 절댓값을 직접 비교할 수 없다. 쌍을 합치거나 votes 를 더하지 말 것.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import duckdb

try:
    # 콘솔이 아니면(로그 파일 리다이렉트·파이프) stdout 인코딩이 로캘(cp949)로 정해져
    # 한글 한 글자에 UnicodeEncodeError 로 죽는다. chcp 65001 은 콘솔 코드페이지만 바꾼다.
    # 수집기(pipeline/collectors/registry/collect.py)와 같은 방어.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ap = argparse.ArgumentParser()
ap.add_argument("--source", choices=("depsdev", "registry"), default="depsdev")
ap.add_argument("--kind", choices=("regular", "dev"), default="regular")
ap.add_argument("--tag", default="", help="출력 폴더 접미사. 비우면 원천·종류로 정한다")
ap.add_argument("--reclassify-legacy", action="store_true",
                help="재분류 판정에서 Dev 칸을 보지 않는다(Peer/Optional 만). depsdev 원천의 한계를 "
                     "registry 모집단에서 그대로 재현하는 대조군용 — 같은 모집단에서 필터만 바꿔 "
                     "비교해야 '필터 효과'와 '모집단 차이'가 섞이지 않는다")
args = ap.parse_args()
if args.source == "depsdev" and args.kind != "regular":
    ap.error("depsdev 원천에는 개발용 의존이 없습니다. --source registry 와 함께 쓰세요.")

ROOT = Path(__file__).resolve().parents[2].as_posix()  # 리포 루트

# 구간별 이탈 사유(S15P21A506-378)의 판정 문장과 검산. 구간 경계가 왜 여기 있지 않고
# 유지·유입·이탈에서 오는지는 그 모듈의 docstring 에 있다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from removal_periods import (  # noqa: E402
    PERIODS, REMOVAL_BY_PERIOD_SQL, T2, build_periods, require_monotonic)

R = f"{ROOT}/data/raw/requirements/**/*.parquet"
V = f"{ROOT}/data/raw/versions_full/snapshot=2026-08-31/*.parquet"
RG = f"{ROOT}/data/registry/parquet/registry_versions/*.parquet"

# 의존 칸: 분석 대상(deps) 과 "여기로 옮겨졌으면 제거가 아니라 재분류"(nonreg)
KIND_COL = {"regular": "Dependencies", "dev": "DevDependencies"}[args.kind]
OTHER_COLS = {"regular": ["DevDependencies", "PeerDependencies", "OptionalDependencies"],
              "dev": ["Dependencies", "PeerDependencies", "OptionalDependencies"]}[args.kind]
if args.source == "depsdev" or args.reclassify_legacy:
    OTHER_COLS = ["PeerDependencies", "OptionalDependencies"]  # depsdev 는 원천에 Dev 칸이 없다

if args.source == "depsdev":
    SUFFIX, DATESTAMP = "", "260908"   # 기존 산출물 경로를 그대로 쓴다 (재실행 호환)
else:
    SUFFIX, DATESTAMP = args.tag or f"_{args.kind}" + ("_legacy" if args.reclassify_legacy else ""), "260914"
OUT = f"{ROOT}/datasets/migration_pairs{SUFFIX}_{DATESTAMP}"
EV_DIR = f"{ROOT}/data/migration_pairs{SUFFIX}"
DB = f"{ROOT}/data/migration_pairs{SUFFIX}.duckdb"
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

ADOPT_SRC = R if args.source == "depsdev" else RG

stats = {}

# 1) 릴리스 + 의존성 (분석 대상 KIND_COL / 다른 칸으로 옮겨진 것 = 재분류이지 제거가 아니다)
_NONREG = " || ".join(f"coalesce(list_transform(r.{c}, x -> x.Name), []::VARCHAR[])" for c in OTHER_COLS)
if args.source == "depsdev":
    SELECT_REL = f"""SELECT r.Name, r.Version, v.published_at, v.source_repo,
       list_sort(list_transform(r.{KIND_COL}, x -> x.Name)) AS deps,
       {_NONREG} AS nonreg
FROM read_parquet('{R}') r JOIN read_parquet('{V}') v ON v.Name=r.Name AND v.Version=r.Version
WHERE v.is_release AND v.published_at IS NOT NULL AND regexp_matches(r.Version,'^\\d+\\.\\d+')"""
else:
    # registry 원천 (S15P21A506-349)
    #  - is_release 조인이 필요 없다. 조인 적중 2,039만 행에서 is_release 와 "버전에 '-' 가 없다" 가
    #    불일치 0건으로 동치임을 확인했다(09-14). 조인을 하나 줄여 실행이 빠르다
    #  - source_repo 는 패키지 단위로 붙인다. 버전 단위로 조인하면 08-31 스냅샷 이후 발행된
    #    20.1만 행(2만 패키지)이 비어 publisher 가 이름으로 떨어진다. 저장소는 버전마다 바뀌지 않으므로
    #    any_value 로 패키지에 한 번 붙인다 (91,582 / 97,733 패키지 적중)
    #  - unpublished 행은 의존을 모른다(NULL). 넣으면 "의존 전부 제거"로 잡힌다 — 수집계획 §5-3
    SELECT_REL = f"""SELECT r.Name, r.Version, r.published_at, v.source_repo,
       list_sort(list_transform(r.{KIND_COL}, x -> x.Name)) AS deps,
       {_NONREG} AS nonreg
FROM read_parquet('{RG}') r
LEFT JOIN (SELECT Name, any_value(source_repo) AS source_repo FROM read_parquet('{V}')
           WHERE source_repo IS NOT NULL GROUP BY Name) v ON v.Name = r.Name
WHERE NOT r.unpublished AND r.published_at IS NOT NULL
  AND regexp_matches(r.Version,'^\\d+\\.\\d+') AND NOT contains(r.Version,'-')"""

con.execute(f"""CREATE OR REPLACE TABLE rel AS
{SELECT_REL}""")
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
#
# **정렬에 동순위 처리가 있어야 한다** (S15P21A506-378, 2026-09-18).
# published_at 만으로 줄을 세우면 같은 시각에 발행된 릴리스 사이에서 lag() 가 무엇을 앞
# 버전으로 잡을지 정해지지 않고, 그러면 "무엇이 빠졌나" 가 실행마다 달라진다. 같은 입력을
# 두 번 돌려 removals_total 이 2,058,952 / 2,058,928 로 갈린 것을 실측했다.
# 동순위 그룹 1,142개 · 703 패키지 · 한 그룹 최대 38개.
#
# 원천 둘에 같은 규칙을 쓰려고 ordinal 이 아니라 버전 숫자로 깬다 — registry 경로는
# versions_full 을 버전 단위로 조인하지 않아 ordinal 이 없다. is_release / '-' 없음 조건에
# prerelease 가 이미 걸러져 있어 (major, minor, patch) 로 충분하고, 마지막 Version 이
# 순서를 완전하게 만든다.
#
# 자리마다 따로 뽑는 것이 중요하다. '^(\d+)\.(\d+)\.(\d+)' 한 번으로 뽑으면 두 자리
# 버전(1.3)에 아예 안 맞아 전부 0 이 되고, 1.3 이 1.2.3 보다 앞에 선다.
con.execute(r"""CREATE OR REPLACE TABLE trans AS
SELECT Name, publisher, line, from_version, to_version, to_ts,
  list_filter(removed_raw, x -> NOT list_contains(nonreg, x)) AS removed,
  list_filter(removed_raw, x -> list_contains(nonreg, x)) AS reclassified,
  added
FROM (
  SELECT Name, publisher, line, lag(Version) OVER w AS from_version, Version AS to_version, published_at AS to_ts, nonreg,
    list_filter(lag(deps) OVER w, x -> NOT list_contains(deps, x)) AS removed_raw,
    list_filter(deps, x -> NOT list_contains(lag(deps) OVER w, x)) AS added
  FROM seq
  WINDOW w AS (PARTITION BY Name, line ORDER BY published_at, coalesce(try_cast(regexp_extract(Version,'^(\d+)',1) AS INT),0), coalesce(try_cast(regexp_extract(Version,'^\d+\.(\d+)',1) AS INT),0), coalesce(try_cast(regexp_extract(Version,'^\d+\.\d+\.(\d+)',1) AS INT),0), Version)
  QUALIFY from_version IS NOT NULL
)""")
con.execute("DROP TABLE seq")
n_trans = one("SELECT count(*) FROM trans")
stats["transitions"] = n_trans
stats["packages_with_transition"] = one("SELECT count(DISTINCT Name) FROM trans")
stats["transitions_with_dep_change"] = one("SELECT count(*) FROM trans WHERE len(removed)>0 OR len(added)>0")
stats["transitions_removed_and_added"] = one("SELECT count(*) FROM trans WHERE len(removed)>0 AND len(added)>0")
# 어느 칸으로 옮겨진 것을 세는지는 OTHER_COLS 가 정한다(stats["reclassify_columns"] 로 함께 남긴다).
# depsdev 는 Peer/Optional 만, registry 는 여기에 반대쪽 의존 칸이 더해진다
stats["reclassified_to_other_kinds"] = one("SELECT coalesce(sum(len(reclassified)),0) FROM trans")
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

# 5-3) 구간별 이탈 사유 (S15P21A506-378) — 화면이 쓰는 1y·3y·5y 에 맞춰 다시 센다.
#      연도별 집계로는 대신할 수 없다. 구간은 2026-08-31 에 끝나는데 연도는 12-31 에 끝나서
#      한 해를 잘라 쓸 수 없고, dependents 는 COUNT(DISTINCT) 라 연도끼리 더해지지 않는다.
build_periods(con)
con.execute(REMOVAL_BY_PERIOD_SQL)
stats["removal_by_period"] = {
    p: {"removals": r, "no_replacement": n, "with_replacement": w, "pkgs": k}
    for p, r, n, w, k in con.execute("""
        SELECT period, sum(removals), sum(removals_no_replacement),
               sum(removals_with_replacement), count(*)
        FROM removal_by_period GROUP BY 1 ORDER BY 1""").fetchall()}
# 구간 밖으로 밀려난 전이가 얼마나 되는지 남긴다. T2 는 스냅샷 경계인데 원천에는 그 뒤에
# 발행된 행이 섞여 있다(versions_full 의 2026-08-31 파티션에 09-01 발행분이 들어 있다).
stats["transitions_after_t2"] = one(
    f"SELECT count(*) FROM trans WHERE to_ts > TIMESTAMP '{T2}'")
require_monotonic(con)
log("removal_by_period", json.dumps(stats["removal_by_period"], ensure_ascii=False),
    "T2 이후 전이", stats["transitions_after_t2"])
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
    # 이 from_pkg 들을 해당 의존 칸에 가진 적 있는 패키지 수 (이동 안내를 받을 수 있는 잠재 대상)
    # 모집단이 원천마다 다르다 — depsdev 는 npm 전수, registry 는 상위 10만. 원천이 다르면 이 수를 비교하지 말 것
    stats[f"{name}_adopters_of_from_pkgs"] = one(f"""
        SELECT count(DISTINCT r.Name) FROM read_parquet('{ADOPT_SRC}') r
        WHERE len(list_intersect(list_transform(r.{KIND_COL}, x -> x.Name),
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
con.execute(f"""COPY (SELECT p.period, p.removed_pkg, p.removals, p.removals_no_replacement,
                             p.removals_with_replacement,
                             round(p.removals_no_replacement*100.0/p.removals, 1) AS no_replacement_pct,
                             p.dependents
                      FROM removal_by_period p JOIN removal_stats s USING (removed_pkg)
                      WHERE s.removals_total >= {REMOVAL_MIN}
                      ORDER BY p.period, p.removals DESC, p.removed_pkg)
                TO '{OUT}/removal_by_period.csv' (HEADER, DELIMITER ',')""")
con.execute(f"COPY (SELECT * FROM removal_stats ORDER BY removals_total DESC) TO '{EV_DIR}/removal_stats.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)")
con.execute(f"COPY (SELECT * FROM removal_by_year ORDER BY removed_pkg, year) TO '{EV_DIR}/removal_by_year.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)")
con.execute(f"COPY (SELECT * FROM removal_by_period ORDER BY period, removed_pkg) TO '{EV_DIR}/removal_by_period.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)")
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
          "removal_stats.csv", "removal_by_year.csv", "removal_by_period.csv"):
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
    "removal_by_period.csv": sz(f"{OUT}/removal_by_period.csv"),
    "removal_stats.parquet": sz(f"{EV_DIR}/removal_stats.parquet"),
    "removal_by_year.parquet": sz(f"{EV_DIR}/removal_by_year.parquet"),
    "removal_by_period.parquet": sz(f"{EV_DIR}/removal_by_period.parquet"),
    "migration_events.parquet": sz(f"{EV_DIR}/migration_events.parquet"),
    "migration_events.csv": sz(f"{EV_DIR}/migration_events.csv"),
    "migration_pairs.duckdb": sz(DB),
}
def dir_bytes(d):
    return sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs)


stats["input_bytes"] = {"versions_full_parquet": dir_bytes(f"{ROOT}/data/raw/versions_full")}
if args.source == "depsdev":
    stats["input_bytes"]["requirements_parquet"] = dir_bytes(f"{ROOT}/data/raw/requirements")
else:
    stats["input_bytes"]["registry_versions_parquet"] = dir_bytes(f"{ROOT}/data/registry/parquet/registry_versions")
stats["periods"] = {k: {"t1": v, "t2": T2} for k, v in PERIODS.items()}
stats["source"] = args.source
stats["kind"] = args.kind
stats["dep_column"] = KIND_COL
stats["reclassify_columns"] = OTHER_COLS
stats["reclassify_legacy"] = args.reclassify_legacy
stats["elapsed_sec"] = round(time.time() - t0)
with open(f"{OUT}/stats.json", "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2)
log("done", json.dumps(stats, ensure_ascii=False))
