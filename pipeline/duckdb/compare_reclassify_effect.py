"""실행용 의존 제거 중 "개발용 의존으로 옮긴 것"이 얼마나 섞였나 — 재분류 필터 효과 측정 (S15P21A506-349)

deps.dev NPMRequirements 에는 devDependencies 칸이 없다. 그래서 지금까지의 이동쌍 계산은
"dependencies 에서 빼고 devDependencies 로 옮긴" 재분류를 전부 '제거'로 세어 왔다.
설계 문서 §5-1 의 peerDependencies 함정과 같은 함정이 dev 칸에도 있었던 것이다.

registry 수집분(상위 10만)에는 두 칸이 다 있으므로, **같은 모집단에서 필터만 바꿔** 두 번 돌리면
그 과대 계상의 크기를 분리해 잴 수 있다. 모집단까지 바꾸면 필터 효과와 모집단 차이가 섞인다.

  legacy : 재분류 판정에 Peer/Optional 만 본다  = 지금 deps.dev 결과가 하는 것
  full   : Dev/Peer/Optional 을 본다            = 고친 것

선행
  .venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py --source registry --kind regular --reclassify-legacy
  .venv-bq/Scripts/python.exe pipeline/duckdb/build_migration_pairs.py --source registry --kind regular
실행
  .venv-bq/Scripts/python.exe pipeline/duckdb/compare_reclassify_effect.py
출력  datasets/migration_pairs_dev_260914/
  reclassify_effect_removals.csv   X별 제거 수 legacy vs full (legacy 제거 3건 이상)
  reclassify_effect_pairs.csv      legacy strict 통과 쌍이 full 에서 어떻게 됐나
  reclassify_effect.json           요약 + 팀 공유본(depsdev strict) 영향 범위
"""
import json
import os
import sys
import time
from pathlib import Path

import duckdb

try:
    # 콘솔이 아니면 stdout 인코딩이 cp949 로 정해져 한글 한 글자에 죽는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2].as_posix()
LEGACY_DB = f"{ROOT}/data/migration_pairs_regular_legacy.duckdb"
FULL_DB = f"{ROOT}/data/migration_pairs_regular.duckdb"
DEPSDEV_STRICT = f"{ROOT}/datasets/migration_pairs_260908/migration_pairs_strict.csv"
OUT = f"{ROOT}/datasets/migration_pairs_dev_260914"
os.makedirs(OUT, exist_ok=True)

for path in (LEGACY_DB, FULL_DB):
    if not os.path.exists(path):
        sys.exit(f"먼저 빌더를 돌려 주세요 — 없음: {path}")


def strict(alias):
    """README 의 strict 필터를 주어진 테이블 별칭에 붙인다."""
    return (f"{alias}.lift >= 5 AND {alias}.votes >= 12 "
            f"AND {alias}.publisher_months >= 10 AND {alias}.a_rate >= 0.03")


t0 = time.time()
con = duckdb.connect()
con.execute(f"SET threads=8; SET memory_limit='16GB'; SET temp_directory='{ROOT}/data/duckdb_tmp'")
con.execute(f"ATTACH '{LEGACY_DB}' AS L (READ_ONLY)")
con.execute(f"ATTACH '{FULL_DB}' AS F (READ_ONLY)")

s = {}

# 1) X 별 제거 수 — legacy 는 dev 로 옮긴 것도 제거로 세고, full 은 안 센다
con.execute("""CREATE TABLE rm AS
SELECT coalesce(l.removed_pkg, f.removed_pkg) AS removed_pkg,
       coalesce(l.removals_total, 0) AS legacy_removals,
       coalesce(f.removals_total, 0) AS full_removals,
       coalesce(l.removals_total, 0) - coalesce(f.removals_total, 0) AS reclassified_to_dev,
       coalesce(l.dependents, 0) AS legacy_dependents,
       coalesce(f.dependents, 0) AS full_dependents
FROM L.removal_stats l FULL OUTER JOIN F.removal_stats f ON f.removed_pkg = l.removed_pkg""")

s["removed_pkgs_legacy"] = con.execute("SELECT count(*) FROM rm WHERE legacy_removals > 0").fetchone()[0]
s["removals_legacy"] = con.execute("SELECT sum(legacy_removals) FROM rm").fetchone()[0]
s["removals_full"] = con.execute("SELECT sum(full_removals) FROM rm").fetchone()[0]
s["reclassified_to_dev"] = s["removals_legacy"] - s["removals_full"]
s["reclassified_pct"] = round(s["reclassified_to_dev"] * 100.0 / s["removals_legacy"], 2)
# 그 패키지의 '제거'가 전부 dev 이동이었던 경우 — X 자체가 목록에서 사라진다
s["pkgs_fully_reclassified"] = con.execute(
    "SELECT count(*) FROM rm WHERE legacy_removals > 0 AND full_removals = 0").fetchone()[0]
print(f"[{time.time() - t0:5.0f}s] 제거 {s['removals_legacy']:,} -> {s['removals_full']:,} "
      f"(재분류 {s['reclassified_to_dev']:,} · {s['reclassified_pct']}%)", flush=True)

con.execute(f"""COPY (
    SELECT removed_pkg, legacy_removals, full_removals, reclassified_to_dev,
           round(reclassified_to_dev * 100.0 / nullif(legacy_removals, 0), 1) AS reclassified_pct,
           legacy_dependents, full_dependents
    FROM rm WHERE legacy_removals >= 3
    ORDER BY reclassified_to_dev DESC, removed_pkg)
TO '{OUT}/reclassify_effect_removals.csv' (HEADER, DELIMITER ',')""")

# 2) 쌍 수준 — legacy 에서 strict 를 통과한 쌍이 full 에서 어떻게 되나
con.execute(f"""CREATE TABLE pr AS
SELECT l.from_pkg, l.to_pkg,
       l.votes AS legacy_votes, f.votes AS full_votes,
       l.lift AS legacy_lift, f.lift AS full_lift,
       l.publisher_months AS legacy_pm, f.publisher_months AS full_pm,
       l.a_rate AS legacy_a, f.a_rate AS full_a,
       (f.from_pkg IS NULL) AS gone,
       (f.from_pkg IS NOT NULL AND NOT ({strict('f')})) AS demoted
FROM L.pairs l LEFT JOIN F.pairs f ON f.from_pkg = l.from_pkg AND f.to_pkg = l.to_pkg
WHERE {strict('l')}""")

s["legacy_strict_pairs"] = con.execute("SELECT count(*) FROM pr").fetchone()[0]
s["strict_pairs_gone"] = con.execute("SELECT count(*) FROM pr WHERE gone").fetchone()[0]
s["strict_pairs_demoted"] = con.execute("SELECT count(*) FROM pr WHERE demoted").fetchone()[0]
s["strict_pairs_kept"] = s["legacy_strict_pairs"] - s["strict_pairs_gone"] - s["strict_pairs_demoted"]
print(f"[{time.time() - t0:5.0f}s] legacy strict {s['legacy_strict_pairs']:,} 쌍 -> "
      f"사라짐 {s['strict_pairs_gone']:,} · 기준 미달 {s['strict_pairs_demoted']:,} · "
      f"유지 {s['strict_pairs_kept']:,}", flush=True)

con.execute(f"""COPY (
    SELECT from_pkg, to_pkg,
           round(legacy_votes, 1) AS legacy_votes, round(full_votes, 1) AS full_votes,
           round(legacy_lift, 1) AS legacy_lift, round(full_lift, 1) AS full_lift,
           legacy_pm, full_pm,
           round(legacy_a * 100, 2) AS legacy_a_pct, round(full_a * 100, 2) AS full_a_pct,
           CASE WHEN gone THEN '사라짐' WHEN demoted THEN '기준 미달' ELSE '유지' END AS 결과
    FROM pr ORDER BY (legacy_votes - coalesce(full_votes, 0)) DESC, from_pkg)
TO '{OUT}/reclassify_effect_pairs.csv' (HEADER, DELIMITER ',')""")

# 3) 팀에 공유된 depsdev strict 쌍 중 영향권에 드는 것
#    (registry 모집단에 없는 X 는 조인되지 않는다 — 그건 '영향 없음'이 아니라 '못 잼'이다)
con.execute(f"CREATE TABLE dd AS SELECT * FROM read_csv_auto('{DEPSDEV_STRICT}')")
s["depsdev_strict_pairs"] = con.execute("SELECT count(*) FROM dd").fetchone()[0]
s["depsdev_strict_x_total"] = con.execute("SELECT count(DISTINCT from_pkg) FROM dd").fetchone()[0]
s["depsdev_strict_x_measurable"] = con.execute(
    "SELECT count(DISTINCT dd.from_pkg) FROM dd JOIN rm ON rm.removed_pkg = dd.from_pkg").fetchone()[0]
s["depsdev_strict_x_with_reclassified"] = con.execute(
    "SELECT count(DISTINCT dd.from_pkg) FROM dd JOIN rm ON rm.removed_pkg = dd.from_pkg "
    "WHERE rm.reclassified_to_dev > 0").fetchone()[0]
s["depsdev_strict_pairs_with_reclassified_x"] = con.execute(
    "SELECT count(*) FROM dd JOIN rm ON rm.removed_pkg = dd.from_pkg "
    "WHERE rm.reclassified_to_dev > 0").fetchone()[0]
s["most_affected"] = [
    {"from_pkg": r[0], "legacy_removals": r[1], "full_removals": r[2],
     "reclassified_pct": r[3], "depsdev_strict_pairs": r[4]}
    for r in con.execute("""SELECT rm.removed_pkg, rm.legacy_removals, rm.full_removals,
                                   round(rm.reclassified_to_dev * 100.0 / rm.legacy_removals, 1),
                                   count(*)
                            FROM dd JOIN rm ON rm.removed_pkg = dd.from_pkg
                            WHERE rm.legacy_removals >= 20
                            GROUP BY 1, 2, 3, 4
                            ORDER BY 4 DESC, 2 DESC LIMIT 20""").fetchall()]

s["elapsed_sec"] = round(time.time() - t0)
s["note"] = ("registry 상위 10만 모집단에서 필터만 바꿔 잰 값이다. 그 밖 패키지의 "
             "dependencies→devDependencies 강등은 deps.dev 원천에 dev 칸이 없어 여전히 잴 수 없다.")

with open(f"{OUT}/reclassify_effect.json", "w", encoding="utf-8") as fh:
    json.dump(s, fh, ensure_ascii=False, indent=2)

# UTF-8 BOM (팀 공유 CSV 관례)
for name in ("reclassify_effect_removals.csv", "reclassify_effect_pairs.csv"):
    p = f"{OUT}/{name}"
    with open(p, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\xef\xbb\xbf"):
        with open(p, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + data)

print(json.dumps(s, ensure_ascii=False, indent=2))
