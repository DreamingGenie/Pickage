"""패키지별 dependents 목록 — "누가 이 패키지에 의존하는가" (S15P21A506-354)

`dependents` 는 의존의 **역방향**이다. `axios` 의 dependents 는 axios 를 쓰는 패키지들이고,
이 집합이 겹친다는 것은 "같은 자리에 쓰인다" 가 아니라 **"같이 쓰인다"** 를 뜻한다.
react 와 react-dom 은 dependents 가 크게 겹치지만 서로 대체재가 아니라 보완재다.
S15P21A506-173 의 관문이 교집합 0.3 초과를 탈락시키는 이유가 이것이다.

이미 있는 dependents 데이터는 전부 **수(count)** 뿐이라 교집합을 잴 수 없다 —
`datasets/targets/rank_top100k_20260902.csv` 의 ecosyste.ms `dependent_packages_count`,
S15P21A506-193 의 버전별 `dependents_count` 둘 다 의존자의 신원이 없다. 그래서 목록을 새로 낸다.

입력  data/raw/requirements    (Dependencies·PeerDependencies·OptionalDependencies) — 2026-08-31 스냅샷
      data/raw/versions_full   (최신 릴리스 판정)
      --targets 의 CSV          (대상 목록. name 열만 있으면 된다)
      datasets/targets/rank_top100k_20260902.csv
        대상 목록이 무엇이든 download_rank·ecosystems_dependent_count 는 항상 여기서 온다.
        상위 10만 밖이면 두 열이 NULL 이고, 그것이 "순위 밖" 이라는 사실을 담는다.

출력  data/package_dependents<_label>/package_dependents.parquet
        (name, kind) 1행 — dependents[] 배열과 개수, 판단 재료 열
      datasets/package_dependents_<label 또는 260915>/
        dependents_summary.csv   같은 표에서 배열만 뺀 것
        stats.json

실행  기본 회차 — 다운로드 상위 10만 대상 (약 90초)
      .venv-bq/Scripts/python.exe pipeline/duckdb/build_package_dependents.py

      다른 대상 목록으로 한 회차 더 (예: AI 후보 풀, S15P21A506-359)
      .venv-bq/Scripts/python.exe pipeline/duckdb/build_package_dependents.py \
        --targets datasets/targets/candidate_pool_260916.csv --label candidate_pool_260916

`--label` 은 폴더 이름이 되므로 영문 소문자·숫자·밑줄만 쓴다. 한글을 넣으면 MinIO
객체 키까지 한글이 되고, 이 저장소의 datasets 폴더는 모두 영문이라 관례와도 어긋난다.

`--label` 을 주면 출력 폴더가 갈린다. 회차를 한 폴더에 섞으면 안 되는 이유는 아래
PQ_DIR 주석에 있다. 대상 목록만 다르고 계산은 같으므로, 두 회차에 겹치는 패키지의
값은 같아야 한다 — 다르면 둘 중 하나가 잘못된 것이다.

## 읽는 사람이 반드시 알아야 할 것

**devDependencies 는 원천에 없다.** deps.dev `NPMRequirements` 는 Dependencies·PeerDependencies·
OptionalDependencies 세 가지만 담는다. 그래서 주로 개발 의존으로 쓰이는 패키지는 구조적으로
과소 계상된다 — `typescript` 는 우리 57,189 인데 ecosyste.ms 는 488,056 이다(0.12배).
**eslint·jest·vitest·prettier 류의 대체 판단에 이 데이터를 그대로 쓰면 안 된다.**
반대로 런타임 의존이 주인 패키지는 잘 맞는다 (express 1.01 · fs-extra 1.00 · debug 1.01 · lodash 0.95).

**배열을 통째로 메모리에 올리지 말 것.** `react` 의 의존자가 19만, `react-dom` 이 16만이다
(2026-09-15 실측). 10만 대상을 전부 `dict[str, set]` 으로 만들면 파이썬 문자열 객체
오버헤드만으로 수 GB 다. 후보 30개처럼 **필요한 이름만 걸러 읽어라.**

**`n_dependents = 0` 은 결측이 아니라 범주다.** 대상 10만 중 dependents 가 하나도 없는
패키지가 1.8만이다. 행을 빼지 않고 빈 배열로 남기는 이유는, 쓰는 쪽에서 "조회 실패" 와
"의존자가 없음" 을 구분할 수 있어야 하기 때문이다. `package_exists` 열로 "npm 에 최신 릴리스가
있는가" 까지 따로 본다.

**ecosyste.ms 값과 일치하지 않는다.** `ecosystems_dependent_count` 를 같은 행에 둔 것은
대조하라는 뜻이지 맞춰야 한다는 뜻이 아니다. 집계 기준(시점·모집단·의존 종류)이 서로 달라
자릿수만 맞으면 된다.

**최신 릴리스 1개만 본다.** 한 패키지의 과거 버전이 무엇에 의존했는지는 세지 않는다.
`build_peer_similarity.py` 의 `build_latest_release()` 와 같은 기준(is_release 중 ordinal 최대)이다.
공용 모듈로 빼지 않은 것은 그 파일이 S15P21A506-350 에서 MR 대기 중이라 지금 고치면
브랜치가 충돌하기 때문이다. 공용화는 그쪽 머지 후 별건으로 한다.

한계는 datasets/package_dependents_260915/README.md 에 적었다 —
직접 의존만·선언 기반·생존 편향·대표 릴리스 조건 차이.
"""
import json
import os
import sys
import argparse
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
RANK = f"{ROOT}/datasets/targets/rank_top100k_20260902.csv"

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--targets", default=RANK,
                help="대상 목록 CSV. name 열만 있으면 된다 (기본: 다운로드 상위 10만)")
ap.add_argument("--label", default=None,
                help="회차 이름. 주면 출력 폴더가 갈린다. 기본 회차(상위 10만)는 생략한다")
args = ap.parse_args()

R = f"{ROOT}/data/raw/requirements/**/*.parquet"
V = f"{ROOT}/data/raw/versions_full/snapshot=2026-08-31/*.parquet"
TARGETS = args.targets

# 출력 폴더는 회차마다 갈라야 한다. pipeline/minio/ingest_derived.py 가 root 의 *.parquet 를
# 통째로 올리므로, 한 폴더에 두 회차를 섞으면 이미 _SUCCESS 가 찍힌 실행에 파일이 늘어
# 재검증이 막힌다 (build_peer_similarity.py 가 같은 이유로 폴더를 나눈다).
_suffix = f"_{args.label}" if args.label else ""
PQ_DIR = f"{ROOT}/data/package_dependents{_suffix}"
OUT = f"{ROOT}/datasets/package_dependents_{args.label or '260915'}"
TMP = f"{ROOT}/data/duckdb_tmp"
for d in (PQ_DIR, OUT, TMP):
    os.makedirs(d, exist_ok=True)

t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)


con = duckdb.connect()
con.execute(f"SET threads=8; SET memory_limit='24GB'; SET temp_directory='{TMP}'; "
            "SET preserve_insertion_order=false")

stats = {"snapshot": "2026-08-31", "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

# 1) 최신 릴리스 -------------------------------------------------------------
#    published_at 이 아니라 ordinal 을 쓴다. 5.0.0 뒤에 나온 유지보수 릴리스 4.17.3 이
#    최신으로 잡히면 안 되기 때문이다.
#
#    의존자 걸러내기가 이 스크립트에서 가장 중요한 부분이다. deps.dev 의 npm 노드에는
#    `@winglang/sdk>0.76.19>cdktf>safe-buffer` 처럼 **번들된 중첩 의존성의 경로**가
#    패키지처럼 들어 있다. 2026-09-15 실측으로 versions_full 고유 이름 1,138만 중
#    705만(61.9%)이 이 형태였다. npm 이름에 `>` 는 쓸 수 없으므로 실제 패키지가 아니다.
#    걸러내지 않으면 이 가짜 노드들이 각자 의존을 선언해 의존자 수가 통째로 부풀고,
#    `tslib` 가 116,820(ecosyste.ms 122,729) 대신 972,523 으로 나온다.
#
#    조건이 두 개인 이유: `published_at IS NOT NULL` 이 정본이고 `NOT LIKE '%>%'` 는
#    문서용이다. 실측상 번들 경로 노드는 7,052,193 행 **전부** published_at 이 NULL 이고
#    정상 패키지는 430 행만 NULL 이라, 배포일 조건 하나로 같은 집합이 걸러진다.
#    배포일 기준을 정본으로 삼는 것은 S15P21A506-283 의 `unknown_published_at=exclude`
#    정책과 같은 기준을 쓰기 위해서다. 이름 조건은 지웠을 때 무엇이 돌아오는지
#    읽는 사람이 알 수 있게 남겨 둔다.
log("1/4 최신 릴리스 판정")
con.execute(f"""CREATE OR REPLACE TABLE lat AS
SELECT Name, Version FROM (
  SELECT Name, Version, row_number() OVER (PARTITION BY Name ORDER BY ordinal DESC) rn
  FROM read_parquet('{V}')
  WHERE is_release AND published_at IS NOT NULL AND Name NOT LIKE '%>%') WHERE rn = 1""")
stats["packages_with_release"] = con.execute("SELECT count(*) FROM lat").fetchone()[0]
stats["bundled_path_nodes_excluded"] = con.execute(
    f"SELECT count(DISTINCT Name) FROM read_parquet('{V}') WHERE Name LIKE '%>%'").fetchone()[0]
log("   최신 릴리스 있는 패키지", f"{stats['packages_with_release']:,}",
    f"(번들 경로 노드 {stats['bundled_path_nodes_excluded']:,} 제외)")

# 2) 대상 목록 ---------------------------------------------------------------
#    CSV 에 같은 이름이 여러 행으로 있을 수 있어 접는다.
#
#    대상 목록에는 name 열만 요구하고, download_rank·eco_cnt 는 목록이 무엇이든 **항상 상위
#    10만 표에서** 왼쪽 조인해 온다. 그래야 두 가지가 지켜진다 — 임의의 목록을 받아도 열
#    구성이 같고, 상위 10만 밖 패키지는 NULL 이 되어 "순위 밖" 이라는 사실이 값으로 남는다.
#    (대상이 상위 10만 그 자체이면 조인 결과가 예전과 같아 기본 회차는 동작이 바뀌지 않는다.)
log("2/4 대상 목록")
con.execute(f"""CREATE OR REPLACE TABLE tgt AS
SELECT t.name,
       k.download_rank,
       k.eco_cnt
FROM (SELECT DISTINCT trim(name) AS name FROM read_csv_auto('{TARGETS}', header=true)
      WHERE name IS NOT NULL AND trim(name) <> '') t
LEFT JOIN (SELECT name, min(rank) AS download_rank, max(dependent_packages_count) AS eco_cnt
           FROM read_csv_auto('{RANK}') GROUP BY 1) k ON k.name = t.name""")
stats["targets_list"] = TARGETS.replace(ROOT + "/", "")
stats["targets"] = con.execute("SELECT count(*) FROM tgt").fetchone()[0]
stats["targets_outside_top100k"] = con.execute(
    "SELECT count(*) FROM tgt WHERE download_rank IS NULL").fetchone()[0]
log("   대상", f"{stats['targets']:,}",
    f"(상위 10만 밖 {stats['targets_outside_top100k']:,})")

# 3) 엣지 -------------------------------------------------------------------
#    세 종류를 한 번에 펼치고 kind 로 구분한다. 쓰는 쪽에서 무엇을 셀지 고르게 하려는 것이고,
#    나중에 peer 를 넣기로 바뀌어도 재계산이 필요 없다.
#    DISTINCT 는 같은 의존자가 같은 대상을 두 번 선언한 경우를 한 번으로 접는다.
log("3/4 엣지 전개 (2~3분)")
con.execute(f"""CREATE OR REPLACE TABLE ed AS
SELECT DISTINCT u.target, u.kind, l.Name AS dependent
FROM lat l
JOIN read_parquet('{R}') r ON r.Name = l.Name AND r.Version = l.Version,
LATERAL (
  SELECT unnest(list_transform(coalesce(r.Dependencies, []), x -> x.Name)) AS target,
         'regular' AS kind
  UNION ALL
  SELECT unnest(list_transform(coalesce(r.PeerDependencies, []), x -> x.Name)), 'peer'
  UNION ALL
  SELECT unnest(list_transform(coalesce(r.OptionalDependencies, []), x -> x.Name)), 'optional'
) u
WHERE u.target IN (SELECT name FROM tgt)""")
stats["edges"] = con.execute("SELECT count(*) FROM ed").fetchone()[0]
log("   엣지", f"{stats['edges']:,}")

# 4) 집계 -------------------------------------------------------------------
#    대상 × 3종류를 모두 만들고 없으면 빈 배열을 넣는다. 행을 빼면 "조회 실패" 와
#    "의존자 없음" 이 구별되지 않는다.
log("4/4 집계·저장")
con.execute("""CREATE OR REPLACE TABLE agg AS
SELECT target, kind, list_sort(list(dependent)) AS dependents, count(*) AS n
FROM ed GROUP BY 1, 2""")

con.execute("""CREATE OR REPLACE TABLE out AS
SELECT t.name,
       k.kind,
       coalesce(a.dependents, []::VARCHAR[]) AS dependents,
       coalesce(a.n, 0)::BIGINT             AS n_dependents,
       t.download_rank,
       t.eco_cnt                            AS ecosystems_dependent_count,
       (l.Name IS NOT NULL)                 AS package_exists
FROM tgt t
CROSS JOIN (SELECT unnest(['regular', 'peer', 'optional']) AS kind) k
LEFT JOIN agg a ON a.target = t.name AND a.kind = k.kind
LEFT JOIN lat l ON l.Name = t.name""")

# 정렬 키에 name 을 반드시 넣는다. download_rank 만으로는 **동순위가 생겨 실행마다 행 순서가
# 달라지고**, 내용이 같은데도 파일 바이트가 흔들린다. 상위 10만 대상만 쓸 때는 순위가 유일해서
# 드러나지 않았지만, 순위 밖 패키지가 섞인 목록에서는 그 행들의 download_rank 가 전부 NULL 이라
# 동순위가 된다 — 2026-09-16 후보 풀 회차에서 같은 입력으로 세 번 돌려 61,674,812 / 61,674,384 /
# 61,673,694 바이트가 나왔다(내용은 동일). NULLS LAST 는 순위 있는 것을 앞에 두려는 것이다.
ORDER = "ORDER BY download_rank NULLS LAST, name, kind"

con.execute(f"""COPY (SELECT * FROM out {ORDER})
                TO '{PQ_DIR}/package_dependents.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")

# 배열을 뺀 요약만 CSV 로 낸다. react 한 행의 배열이 19만 원소라 CSV 셀에 들어가지 않는다.
CSV = f"{OUT}/dependents_summary.csv"
con.execute(f"""COPY (SELECT name, kind, n_dependents, download_rank,
                             ecosystems_dependent_count, package_exists
                      FROM out {ORDER})
                TO '{CSV}' (FORMAT CSV, HEADER)""")
# datasets/README.md 규칙 — CSV 는 UTF-8 BOM (엑셀·구글시트가 BOM 없이는 한글을 깬다).
# DuckDB COPY 는 BOM 을 쓰지 않으므로 여기서 붙인다.
with open(CSV, "rb") as fh:
    body = fh.read()
if not body.startswith(b"\xef\xbb\xbf"):
    with open(CSV, "wb") as fh:
        fh.write(b"\xef\xbb\xbf" + body)

# 집계 — 어디서 끊을 수 있는지, ecosyste.ms 와 얼마나 벌어지는지
for k in ("regular", "peer", "optional"):
    row = con.execute(f"""SELECT count(*) FILTER (WHERE n_dependents > 0),
                                 sum(n_dependents), max(n_dependents),
                                 quantile_cont(n_dependents, [0.5, 0.9, 0.99])
                          FROM out WHERE kind = '{k}'""").fetchone()
    stats[k] = dict(zip(("targets_with_dependents", "edges", "max", "p50_p90_p99"), row))

stats["targets_no_dependents_any_kind"] = con.execute(
    "SELECT count(DISTINCT name) FROM out WHERE name NOT IN "
    "(SELECT name FROM out WHERE n_dependents > 0)").fetchone()[0]
stats["targets_missing_from_npm"] = con.execute(
    "SELECT count(DISTINCT name) FROM out WHERE NOT package_exists").fetchone()[0]
stats["top20_regular"] = con.execute(
    "SELECT name, n_dependents, ecosystems_dependent_count FROM out "
    "WHERE kind = 'regular' ORDER BY n_dependents DESC LIMIT 20").fetchall()
# ecosyste.ms 와의 자릿수 대조. 값이 같기를 기대하지 않는다 (집계 기준이 다르다)
stats["vs_ecosystems"] = con.execute("""
    SELECT count(*), median(n_dependents::DOUBLE / nullif(ecosystems_dependent_count, 0))
    FROM out WHERE kind = 'regular' AND n_dependents > 0
      AND ecosystems_dependent_count > 0""").fetchone()
stats["file_bytes"] = os.path.getsize(f"{PQ_DIR}/package_dependents.parquet")
stats["elapsed_sec"] = round(time.time() - t0)

with open(f"{OUT}/stats.json", "w", encoding="utf-8") as fh:
    json.dump(stats, fh, ensure_ascii=False, indent=2, default=str)
log("done", json.dumps(stats, ensure_ascii=False, default=str))
