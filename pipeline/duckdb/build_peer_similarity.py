"""대체 후보 peer 의존 유사도 — "A 가 B 를 대체할 수 있나" 판단용 특징 테이블 (S15P21A506-350)

`peerDependencies` 는 패키지가 **자기 것으로 설치하지 않고 사용자 프로젝트에 이미 있어야 한다고 요구하는**
패키지다. 플러그인·컴포넌트·어댑터가 어느 호스트(react, vue, @angular/core, eslint, webpack) 위에서
동작하는지를 선언하므로 사실상 "생태계 소속" 표지다. description 이 "date picker component" 로 같아도
react 용과 vue 용은 서로 대체가 아니다.

`datasets/feature_candidates_260908/` 에 이미 100행 표본(`peer_dependencies_100.csv`)과 분석(README §1-3)이
있다. 이 스크립트는 그 결론을 **조인해서 쓸 수 있는 전수 표**로 만든다. 표본 스크립트
(`build_feature_candidates.py`)에 합치지 않은 이유는 그쪽 산출물 계약이 "AI 팀원에게 보여 줄 예시 100건"
이어서, 전수 특징 표를 끼워 넣으면 두 목적이 다 흐려지기 때문이다.

입력  data/raw/requirements (PeerDependencies), data/raw/versions_full (최신 릴리스 판정) — 2026-08-31 스냅샷
      datasets/migration_pairs_260908/          실행용 의존 이동쌍 (npm 전수)
      datasets/migration_pairs_dev_260914/      개발용 의존 이동쌍 (상위 10만, S15P21A506-349)
      datasets/deprecated_replacement_260831/   폐기→대체 학습쌍
## 두 가지 범위 (--scope)

`pairs` (기본) — 쌍 목록에 등장한 패키지만. 이동쌍·폐기쌍의 (A, B) 를 실제로 비교한다.
`all` — npm 전수에서 peer 를 가진 패키지 전부. 쌍 목록에 없는 임의의 조합도 즉석 비교할 수
있게 하는 재료다. 다만 peer 보유 81.4만 중 23.9%가 릴리스 1개짜리이므로(2026-09-15 실측)
`--recent-since` 하한을 넘긴 것을 따로 한 파일 더 낸다.

출력  --scope pairs
      data/peer_similarity/
        package_peers.parquet          패키지 1행 — 최신 릴리스의 peer 목록
        pair_peer_similarity.parquet   쌍 1행 — 양쪽 peer 목록·교집합·Jaccard·판정
      datasets/peer_similarity_260914/
        package_peers.csv, pair_peer_similarity.csv   같은 내용 (UTF-8 BOM, 배열은 | 로 이음)
        stats.json

      --scope all
      data/package_peers/
        package_peers_all.parquet      peer 보유 패키지 전부 + 품질 열 4종
        package_peers_recent.parquet   그중 최신 릴리스가 --recent-since 이후인 것
      datasets/peer_similarity_260914/package_peers_scope_all_stats.json
실행  .venv-bq/Scripts/python.exe pipeline/duckdb/build_peer_similarity.py               (약 10초)
      .venv-bq/Scripts/python.exe pipeline/duckdb/build_peer_similarity.py --scope all   (약 50초)

## 읽는 사람이 반드시 알아야 할 것

**`peer_verdict` 의 `no_peer_either` 는 결측이 아니라 범주다.** peer 는 희소한 속성이어서
이동쌍의 약 60%가 양쪽 다 peer 를 갖고 있지 않다. 이것을 NULL 로 두거나 `mismatch` 로 흘리면
모델이 "결측 = 대체 불가" 를 배운다. 비교 불가와 불일치는 다른 사실이다.

**hard filter 가 아니라 감점 입력이다.** `tslint → eslint` 는 peer 겹침이 0인데 정답지에 있는
진짜 대체쌍이다(tslint 의 peer 는 typescript, eslint 는 없음/다름). peer 불일치만으로 탈락시키면
이런 쌍을 잃는다. `feature_candidates` README §1-3 의 권고와 같다.
"""
import argparse
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

ap = argparse.ArgumentParser()
ap.add_argument("--scope", choices=("pairs", "all"), default="pairs",
                help="pairs(기본) 쌍 목록에 등장한 패키지만 · all npm 전수에서 peer 를 가진 패키지 전부")
ap.add_argument("--recent-since", default="2023-01-01",
                help="--scope all 에서 '살아 있음' 하한. 최신 릴리스가 이 날짜 이후인 것만 따로 낸다")
args = ap.parse_args()

ROOT = Path(__file__).resolve().parents[2].as_posix()
R = f"{ROOT}/data/raw/requirements/**/*.parquet"
V = f"{ROOT}/data/raw/versions_full/snapshot=2026-08-31/*.parquet"
MP = f"{ROOT}/datasets/migration_pairs_260908"
MP_DEV = f"{ROOT}/datasets/migration_pairs_dev_260914"
DEPRECATED = f"{ROOT}/datasets/deprecated_replacement_260831/deprecated_replacement_20260831.jsonl"
TARGETS = f"{ROOT}/datasets/targets/rank_top100k_20260902.csv"
PQ_DIR = f"{ROOT}/data/peer_similarity"
# 전수 모드는 출력 폴더를 따로 쓴다. pipeline/minio/ingest_derived.py 가 데이터셋 root 의
# *.parquet 를 통째로 올리므로, 한 폴더에 섞으면 이미 _SUCCESS 가 찍힌 실행에 파일이 늘어
# "Completed run missing object" 로 막힌다.
PQ_DIR_ALL = f"{ROOT}/data/package_peers"
OUT = f"{ROOT}/datasets/peer_similarity_260914"
TMP = f"{ROOT}/data/duckdb_tmp"
for d in (PQ_DIR, PQ_DIR_ALL, OUT, TMP):
    os.makedirs(d, exist_ok=True)

t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)


con = duckdb.connect()
con.execute(f"SET threads=8; SET memory_limit='24GB'; SET temp_directory='{TMP}'; "
            "SET preserve_insertion_order=false")

stats = {"scope": args.scope}


def build_latest_release(where_extra=""):
    """패키지 1행 = 최신 릴리스. 두 모드가 같은 판정을 쓰게 하려고 함수로 뺐다.

    '최신'은 versions_full 의 is_release 중 ordinal 이 가장 큰 것이다. published_at 이 아니라
    ordinal 을 쓰는 이유는 유지보수 릴리스(5.0.0 뒤에 나온 4.17.3)가 최신으로 잡히지 않게 하기
    위해서다.

    `published_at IS NOT NULL` 은 배포일을 쓰려는 게 아니라 **가짜 패키지를 빼려는 것이다.**
    deps.dev 의 npm 노드에는 `@winglang/sdk>0.76.19>cdktf>safe-buffer` 처럼 번들된 중첩
    의존성의 경로가 패키지처럼 들어 있다. npm 이름에 `>` 는 쓸 수 없으므로 실제 패키지가
    아니다. 2026-09-15 실측으로 versions_full 고유 이름 1,138만 중 705만(61.9%)이 이 형태이고,
    그 7,052,193 행은 **전부** published_at 이 NULL 이다(정상 패키지는 430 행만 NULL). 그래서
    배포일 조건 하나로 정확히 갈린다. S15P21A506-283 의 `unknown_published_at=exclude` 와
    같은 기준이다.

    이 조건이 없던 동안 `--scope all` 산출물에 219,299 행(21.2%)이 섞여 있었다. 그때는 그것을
    "릴리스 1 개짜리 방치 패키지" 로 읽었지만 실제로는 패키지가 아니었다. `--recent-since`
    하한이 NULL 을 함께 떨궈 recent 파일만 우연히 깨끗했던 것이지 설계가 막은 게 아니다.

    형제 스크립트 build_feature_candidates.py 는 한 곳(69 행)에서 이미 이 조건을 쓰고 다른
    곳(132 행)에서는 쓰지 않는다. 이 함수는 예전에 후자를 따랐다. 132 행 쪽은 이 MR 범위가
    아니라 손대지 않는다.
    """
    con.execute(f"""CREATE OR REPLACE TABLE lat AS
    SELECT Name, Version, published_at, Deprecated, n_rel FROM (
      SELECT Name, Version, published_at, Deprecated,
             count(*) OVER (PARTITION BY Name) AS n_rel,
             row_number() OVER (PARTITION BY Name ORDER BY ordinal DESC) rn
      FROM read_parquet('{V}')
      WHERE is_release AND published_at IS NOT NULL {where_extra}) WHERE rn = 1""")
    return con.execute("SELECT count(*) FROM lat").fetchone()[0]


if args.scope == "all":
    # npm 전수에서 peer 를 가진 패키지 전부. 쌍 목록과 무관하게, 임의의 두 패키지를 즉석에서
    # 비교할 수 있게 하는 용도다.
    #
    # peer 가 없는 패키지(전체의 80.0%)는 넣지 않는다. "peer 가 없다" 는 사실은 이 표에
    # 행이 없다는 것으로 똑같이 표현되고, 빈 배열 325만 행은 파일만 키운다.
    #
    # 품질 열을 함께 담는 이유: peer 보유 패키지 814,025 중 23.9%가 릴리스 1개짜리이고
    # 41.1%가 3년 넘게 방치돼 있다(2026-09-15 실측). 어디서 끊을지는 쓰는 용도마다 달라서
    # 여기서 하나로 정하지 않고, 판단 재료를 열로 준다.
    log("전수 모드 — 최신 릴리스 집계 중 (1~2분)")
    stats["packages_total"] = build_latest_release()
    log("최신 릴리스 있는 패키지", f"{stats['packages_total']:,}")

    con.execute(f"""CREATE TABLE rank AS
    SELECT name, min(rank) AS download_rank FROM read_csv_auto('{TARGETS}') GROUP BY 1""")

    con.execute(f"""CREATE TABLE package_peers AS
    SELECT l.Name AS name, l.Version AS version,
           list_sort(list_transform(r.PeerDependencies, x -> x.Name)) AS peers,
           list_sort(list_transform(r.PeerDependencies, x -> x.Name || '@' || x.Requirement)) AS peers_req,
           len(r.PeerDependencies) AS n_peers,
           l.n_rel AS n_releases,
           l.published_at AS last_published_at,
           (l.Deprecated IS NOT NULL AND l.Deprecated <> '') AS is_deprecated,
           k.download_rank
    FROM lat l
    JOIN read_parquet('{R}') r ON r.Name = l.Name AND r.Version = l.Version
    LEFT JOIN rank k ON k.name = l.Name
    WHERE len(coalesce(r.PeerDependencies, [])) > 0""")
    stats["peer_bearing"] = con.execute("SELECT count(*) FROM package_peers").fetchone()[0]
    log("peer 보유", f"{stats['peer_bearing']:,}")

    SINCE = args.recent_since
    stats["recent_since"] = SINCE
    stats["peer_bearing_recent"] = con.execute(
        f"SELECT count(*) FROM package_peers WHERE last_published_at >= TIMESTAMP '{SINCE}'").fetchone()[0]

    # 두 파일로 나눠 낸다. recent 는 all 의 부분집합이며 열 구성이 같다
    con.execute(f"""COPY (SELECT * FROM package_peers ORDER BY name)
                    TO '{PQ_DIR_ALL}/package_peers_all.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    con.execute(f"""COPY (SELECT * FROM package_peers
                          WHERE last_published_at >= TIMESTAMP '{SINCE}' ORDER BY name)
                    TO '{PQ_DIR_ALL}/package_peers_recent.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")

    # 집계 — 두 파일이 서로 얼마나 다른지, 그리고 어디서 더 끊을 수 있는지
    def agg(where):
        return con.execute(f"""SELECT count(*), sum(n_peers),
            count(*) FILTER (WHERE n_releases = 1),
            count(*) FILTER (WHERE is_deprecated),
            count(*) FILTER (WHERE download_rank IS NOT NULL),
            count(DISTINCT CASE WHEN name LIKE '@%' THEN split_part(name,'/',1) ELSE name END)
            FROM package_peers WHERE {where}""").fetchone()

    keys = ("packages", "peer_declarations", "single_release", "deprecated",
            "in_top100k", "distinct_scopes")
    stats["agg_all"] = dict(zip(keys, agg("TRUE")))
    stats["agg_recent"] = dict(zip(keys, agg(f"last_published_at >= TIMESTAMP '{SINCE}'")))
    stats["file_bytes"] = {
        "package_peers_all.parquet": os.path.getsize(f"{PQ_DIR_ALL}/package_peers_all.parquet"),
        "package_peers_recent.parquet": os.path.getsize(f"{PQ_DIR_ALL}/package_peers_recent.parquet"),
    }
    stats["elapsed_sec"] = round(time.time() - t0)
    with open(f"{OUT}/package_peers_scope_all_stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    log("done", json.dumps(stats, ensure_ascii=False))
    sys.exit(0)

# 1) 비교할 쌍 모으기 ----------------------------------------------------------
#    source 로 어느 원천에서 왔는지 남긴다. 이동쌍은 등급이 포개져 있으므로(all ⊃ recommended)
#    tier 까지 함께 두고, 쓰는 쪽에서 필요한 등급만 고르게 한다.
sources = [
    ("migration", "strict", f"{MP}/migration_pairs_strict.csv"),
    ("migration", "recommended", f"{MP}/migration_pairs_recommended.csv"),
    ("migration", "all", f"{MP}/migration_pairs_all.csv"),
    ("migration_dev", "strict", f"{MP_DEV}/migration_pairs_strict.csv"),
    ("migration_dev", "recommended", f"{MP_DEV}/migration_pairs_recommended.csv"),
    ("migration_dev", "all", f"{MP_DEV}/migration_pairs_all.csv"),
]
selects = [f"SELECT '{src}' AS source, '{tier}' AS tier, from_pkg, to_pkg "
           f"FROM read_csv_auto('{path}')" for src, tier, path in sources if os.path.exists(path)]
# 폐기→대체 학습쌍. replacement_alive 인 것만 — 죽은 대체재는 후보가 아니다
selects.append(f"""SELECT 'deprecated' AS source, 'all' AS tier, name AS from_pkg, replacement AS to_pkg
                   FROM read_json_auto('{DEPRECATED}') WHERE replacement_alive""")
con.execute("CREATE TABLE pairs AS " + " UNION ALL ".join(selects))
stats["pairs_in"] = {f"{s}/{t}": n for s, t, n in
                     con.execute("SELECT source, tier, count(*) FROM pairs GROUP BY 1,2 "
                                 "ORDER BY 1,2").fetchall()}
log("쌍", stats["pairs_in"])

con.execute("CREATE TABLE names AS SELECT DISTINCT from_pkg AS name FROM pairs "
            "UNION SELECT DISTINCT to_pkg FROM pairs")
stats["packages_in_pairs"] = con.execute("SELECT count(*) FROM names").fetchone()[0]

# 2) 패키지별 peer — 최신 릴리스 기준 -------------------------------------------
#    "A 가 B 를 대체할 수 있나" 는 지금 시점 판단이라 최신 릴리스를 쓴다(표본 스크립트와 같은 방식).
#    한계: A 가 폐기·방치된 패키지면 그 최신은 몇 년 전 선언이라 그 시절 생태계를 반영한다.
#    예) moment 의 peer 는 2020년 기준이다. 이동 시점 기준이 필요하면 별도 작업이다.
stats["packages_with_release"] = build_latest_release("AND Name IN (SELECT name FROM names)")
log("최신 릴리스", stats["packages_with_release"], "/", stats["packages_in_pairs"])

con.execute(f"""CREATE TABLE package_peers AS
SELECT r.Name AS name, r.Version AS version,
       list_sort(list_transform(r.PeerDependencies, x -> x.Name)) AS peers,
       list_sort(list_transform(r.PeerDependencies, x -> x.Name || '@' || x.Requirement)) AS peers_req,
       len(coalesce(r.PeerDependencies, [])) AS n_peers
FROM read_parquet('{R}') r JOIN lat USING (Name, Version)""")
stats["packages_with_peers"] = con.execute(
    "SELECT count(*) FROM package_peers WHERE n_peers > 0").fetchone()[0]
log("peer 보유", stats["packages_with_peers"], "/", stats["packages_with_release"])

# 3) 쌍별 비교 -----------------------------------------------------------------
#    양쪽 다 peer 가 없는 경우(비교 불가)를 no_peer_either 로 **명시**한다. NULL 이나 mismatch 로
#    흘리면 모델이 결측을 "대체 불가" 로 배운다. jaccard 는 그 경우에만 NULL 이다.
con.execute("""CREATE TABLE pair_peer_similarity AS
SELECT p.source, p.tier, p.from_pkg, a.version AS from_version, p.to_pkg, b.version AS to_version,
       coalesce(a.peers, []::VARCHAR[]) AS from_peers,
       coalesce(b.peers, []::VARCHAR[]) AS to_peers,
       coalesce(a.peers_req, []::VARCHAR[]) AS from_peers_req,
       coalesce(b.peers_req, []::VARCHAR[]) AS to_peers_req,
       coalesce(a.n_peers, 0) AS n_peer_from, coalesce(b.n_peers, 0) AS n_peer_to,
       list_intersect(coalesce(a.peers, []::VARCHAR[]), coalesce(b.peers, []::VARCHAR[])) AS shared_peers,
       len(list_intersect(coalesce(a.peers, []::VARCHAR[]), coalesce(b.peers, []::VARCHAR[]))) AS n_shared,
       CASE WHEN coalesce(a.n_peers, 0) = 0 OR coalesce(b.n_peers, 0) = 0 THEN NULL
            ELSE len(list_intersect(a.peers, b.peers))::DOUBLE
                 / len(list_distinct(a.peers || b.peers)) END AS peer_jaccard,
       CASE WHEN coalesce(a.n_peers, 0) = 0 AND coalesce(b.n_peers, 0) = 0 THEN 'no_peer_either'
            WHEN coalesce(a.n_peers, 0) = 0 OR coalesce(b.n_peers, 0) = 0 THEN 'one_side_only'
            WHEN len(list_intersect(a.peers, b.peers)) > 0 THEN 'match'
            ELSE 'mismatch' END AS peer_verdict,
       (a.name IS NULL OR b.name IS NULL) AS missing_release
FROM pairs p
LEFT JOIN package_peers a ON a.name = p.from_pkg
LEFT JOIN package_peers b ON b.name = p.to_pkg""")

stats["pairs_out"] = con.execute("SELECT count(*) FROM pair_peer_similarity").fetchone()[0]
stats["verdict"] = {f"{s}/{t}/{v}": n for s, t, v, n in con.execute(
    "SELECT source, tier, peer_verdict, count(*) FROM pair_peer_similarity "
    "GROUP BY 1,2,3 ORDER BY 1,2,3").fetchall()}
stats["jaccard_band"] = {b: n for b, n in con.execute("""
    SELECT CASE WHEN peer_jaccard = 0 THEN '0'
                WHEN peer_jaccard < 0.5 THEN '0<j<0.5'
                WHEN peer_jaccard < 1 THEN '0.5<=j<1' ELSE '1' END, count(*)
    FROM pair_peer_similarity WHERE peer_jaccard IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()}
log("판정", stats["jaccard_band"])

# 4) 출력 ----------------------------------------------------------------------
con.execute(f"""COPY (SELECT * FROM package_peers ORDER BY name)
                TO '{PQ_DIR}/package_peers.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")
con.execute(f"""COPY (SELECT * FROM pair_peer_similarity ORDER BY source, tier, from_pkg, to_pkg)
                TO '{PQ_DIR}/pair_peer_similarity.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")

# CSV 는 배열을 | 로 이어 붙인다 (datasets/README.md 관례, 엑셀·구글시트 호환)
con.execute(f"""COPY (
    SELECT name, version, array_to_string(peers, '|') AS peer_dependencies,
           array_to_string(peers_req, '|') AS peer_dependencies_req, n_peers
    FROM package_peers ORDER BY name)
TO '{OUT}/package_peers.csv' (HEADER, DELIMITER ',')""")
con.execute(f"""COPY (
    SELECT source, tier, from_pkg, from_version, to_pkg, to_version,
           array_to_string(from_peers, '|') AS from_peer_dependencies,
           array_to_string(to_peers, '|') AS to_peer_dependencies,
           array_to_string(from_peers_req, '|') AS from_peer_dependencies_req,
           array_to_string(to_peers_req, '|') AS to_peer_dependencies_req,
           n_peer_from, n_peer_to, array_to_string(shared_peers, '|') AS shared_peers, n_shared,
           round(peer_jaccard, 4) AS peer_jaccard, peer_verdict, missing_release
    FROM pair_peer_similarity ORDER BY source, tier, from_pkg, to_pkg)
TO '{OUT}/pair_peer_similarity.csv' (HEADER, DELIMITER ',')""")

for name in ("package_peers.csv", "pair_peer_similarity.csv"):
    p = f"{OUT}/{name}"
    with open(p, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\xef\xbb\xbf"):
        with open(p, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + data)

stats["file_bytes"] = {
    "package_peers.parquet": os.path.getsize(f"{PQ_DIR}/package_peers.parquet"),
    "pair_peer_similarity.parquet": os.path.getsize(f"{PQ_DIR}/pair_peer_similarity.parquet"),
    "package_peers.csv": os.path.getsize(f"{OUT}/package_peers.csv"),
    "pair_peer_similarity.csv": os.path.getsize(f"{OUT}/pair_peer_similarity.csv"),
}
stats["version_basis"] = "latest release (versions_full.is_release, ordinal DESC)"
stats["snapshot"] = "2026-08-31"
stats["elapsed_sec"] = round(time.time() - t0)
with open(f"{OUT}/stats.json", "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2)
log("done", json.dumps({k: v for k, v in stats.items() if k != "verdict"}, ensure_ascii=False))
