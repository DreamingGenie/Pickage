#!/usr/bin/env python
"""폐기(deprecated) npm 패키지 → 대체 패키지 데이터셋 생성.

원천: data/raw/versions_full (deps.dev BigQuery PackageVersions, System='NPM', T0 스냅샷).
대상: 최신 릴리스(Ordinal 최고, IsRelease)가 폐기됐고, 폐기 문구에서 대체 패키지명이 추출되며
      그 이름이 npm에 실존하는 패키지. (조사 2026-09-07: 약 2.8만 개, 정밀도 85~90%)

실행:  .venv-bq/Scripts/python pipeline/duckdb/build_deprecated_dataset.py [--out DIR]
산출:  <out>/deprecated_replacement_<snapshot>.csv / .jsonl / README.md

keywords 열은 deps.dev BigQuery에 없어(30개 테이블 전부 확인) 비워 두고, 외부 API로 채운다.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import duckdb

sys.stdout.reconfigure(encoding="utf-8")

RAW = "data/raw/versions_full/snapshot=*/part-*.parquet"
PROJ = "data/raw/pkg_project/snapshot=*/part-*.parquet"

# "동사 + 패키지명" 패턴. RE2 문법(DuckDB). 첫 번째 후보만 취한다.
VERB = r"(?:use|switch to|replaced by|moved to|renamed to|migrate to|in favou?r of|superseded by|merged into|successor is|replaced with|now lives at|now)"
NAME = r"((?:@[a-z0-9._-]+/)?[a-z0-9][a-z0-9._-]*[a-z0-9])"
RX = rf"(?i){VERB}\s+[`'\"]?{NAME}"  # SQL에는 바인드 파라미터로 전달(따옴표 충돌 방지)

# 정규식이 잡지만 패키지명이 아닌 일반 단어. npm에 같은 이름의 스쿼팅 패키지가 있어 실존 검사를 통과하므로 명시 제외.
STOP = """
the a an it it. this that these those at npm npx yarn pnpm bun node nodejs deno https http www version versions
something our your my his her their its new newer latest instead and or of to in on for with as is are be been being
was were only now then package packages module modules library libraries plugin plugins tool tools framework
javascript typescript native built standard separate utility util utils v1 v2 v3 v4 v5 v6 v7 v8 v9 es5 es6 es2015 esm cjs
string object array promise promises async fetch import require es one another either directly aws azure gcp google
deprecated deprecate available under part called moved published namespaced private public internal official
different any all some other others another same original main master core base default local remote
please see also here there more less about after before again always because both each few from further had has have
if into just like may might much must no not off once out over own same should so than too until up very what when
where which while who whom why will would yes you yours we they them me us him she he them
distributed github included supports scoped components using bundled use heroku across simply organization organisation ships ship
alternative lives live renamed inside individual considered hosts hosted scope obsolete unmaintained supported replaced unscoped stable includes
upstream uses within provided named targets pure contained data component working covers open direct can natively able released reliability org by
system contains web trace mit jsr bing pi claude
""".split()
SPLIT_TOKENS = {"or", "and", "/"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="datasets/deprecated_replacement_260831")
    # CSV·JSONL 은 git 으로 공유하고, 같은 내용의 Parquet 은 MinIO 입고용으로 data/ 에 둔다.
    ap.add_argument("--parquet-out", default="data/deprecated_replacement")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pq_out = Path(args.parquet_out)
    pq_out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET threads TO 8; SET memory_limit = '12GB';")
    stop_sql = ", ".join("'" + s.replace("'", "''") + "'" for s in STOP)
    t0 = time.time()

    con.execute(f"""
    CREATE TEMP TABLE v AS
    SELECT Name, Version, is_release, ordinal, published_at, Deprecated, Description, Licenses, source_repo, snapshot
    FROM read_parquet('{RAW}', hive_partitioning=true)""")
    snap = con.sql("SELECT MAX(snapshot)::VARCHAR FROM v").fetchone()[0]

    con.execute("""
    CREATE TEMP TABLE latest AS
    SELECT * EXCLUDE rn FROM (
      SELECT Name, Version, published_at, Deprecated, Description, Licenses, source_repo,
             ROW_NUMBER() OVER (PARTITION BY Name ORDER BY ordinal DESC) rn
      FROM v WHERE is_release) WHERE rn = 1""")
    con.execute("""
    CREATE TEMP TABLE stats AS
    SELECT Name, MIN(published_at) first_published_at, COUNT(*) versions_count,
           SUM(is_release::INT) releases_count, SUM((Deprecated IS NOT NULL)::INT) deprecated_versions_count
    FROM v GROUP BY 1""")
    con.execute("CREATE TEMP TABLE names AS SELECT DISTINCT Name FROM v")

    con.execute("""
    CREATE TEMP TABLE ex AS
    SELECT l.*, lower(regexp_extract(l.Deprecated, ?, 1)) AS cand
    FROM latest l WHERE l.Deprecated IS NOT NULL""", [RX])

    # 대체 패키지의 저장소 주소. deps.dev가 owner/repo로 정규화해 둔 PackageVersionToProject를 쓴다.
    # versions_full의 source_repo 원문은 git+ssh://·git@host:·owner/repo 약식이 섞여 있어 손파싱이 필요하다.
    # ProjectType과 원문 host는 2만 건 대조에서 어긋나는 행이 없었다(GITHUB=github.com 등).
    # 최신 릴리스에 매핑이 없는 패키지가 있어 ordinal이 가장 큰 쪽을 고른다.
    con.execute("""
    CREATE TEMP TABLE cand AS SELECT DISTINCT cand AS name FROM ex WHERE cand <> ''""")
    con.execute(f"""
    CREATE TEMP TABLE rep_repo AS
    SELECT v.Name                              AS name,
           arg_max(p.ProjectType, v.ordinal)   AS project_type,
           arg_max(p.ProjectName, v.ordinal)   AS project_name
    FROM v
    JOIN cand c ON c.name = v.Name
    JOIN read_parquet('{PROJ}', hive_partitioning=true) p
      ON p.Name = v.Name AND p.Version = v.Version AND p.RelationType = 'SOURCE_REPO_TYPE'
    GROUP BY 1""")

    con.execute(f"""
    CREATE TEMP TABLE ds AS
    SELECT
      e.Name                       AS name,
      e.Version                    AS last_version,
      e.published_at               AS last_version_published_at,
      s.first_published_at,
      s.versions_count,
      s.releases_count,
      s.deprecated_versions_count,
      e.Description                AS description,
      NULL::VARCHAR[]              AS keywords,
      e.Deprecated                 AS deprecated,
      e.cand                       AS replacement,
      (t.Deprecated IS NULL)       AS replacement_alive,
      t.Version                    AS replacement_last_version,
      CASE WHEN regexp_matches(e.cand, '[@/.0-9-]')
             OR regexp_matches(e.Deprecated, '[`''"]' || regexp_escape(e.cand) || '[`''"]')
           THEN 'high' ELSE 'medium' END AS replacement_confidence,
      t.source_repo                AS replacement_source_repo,
      CASE r.project_type WHEN 'GITHUB'    THEN 'https://github.com/'
                          WHEN 'GITLAB'    THEN 'https://gitlab.com/'
                          WHEN 'BITBUCKET' THEN 'https://bitbucket.org/' END
        || r.project_name          AS replacement_repo_url,
      e.source_repo,
      e.Licenses                   AS licenses,
      '{snap}'                     AS snapshot_at
    FROM ex e
    JOIN stats s USING (Name)
    JOIN names n ON n.Name = e.cand
    LEFT JOIN latest t ON t.Name = e.cand
    LEFT JOIN rep_repo r ON r.name = e.cand
    WHERE e.cand <> '' AND e.cand <> e.Name AND e.cand NOT IN ({stop_sql})
      -- deps.dev는 번들 의존성을 'pkg>1.0.0>dep' 꼴 가짜 이름으로 기록한다(npm에 없음, ecosyste.ms 404). npm 이름 규격만 남긴다.
      AND regexp_matches(e.Name, '^(@[a-z0-9._-]+/)?[a-z0-9._-]+$')
    ORDER BY e.Name""")

    n_dep = con.sql("SELECT COUNT(*) FROM ex").fetchone()[0]
    n_hit = con.sql("SELECT COUNT(*) FROM ex WHERE cand <> ''").fetchone()[0]
    n_ds, n_alive, n_high, n_url = con.sql(
        "SELECT COUNT(*), SUM(replacement_alive::INT), SUM((replacement_confidence='high')::INT),"
        " SUM((replacement_repo_url IS NOT NULL)::INT) FROM ds").fetchone()
    print(f"snapshot={snap}  최신릴리스 폐기={n_dep:,}  정규식 매칭={n_hit:,}  최종 행={n_ds:,} (대체 생존 {n_alive:,} · high {n_high:,} · 대체 저장소 {n_url:,})  {time.time()-t0:.0f}s")

    print("\n## 대체 대상 top 40 (불용어 점검용)")
    print(con.sql("SELECT replacement, COUNT(*) n FROM ds GROUP BY 1 ORDER BY 2 DESC LIMIT 40"))

    cols = [d[0] for d in con.execute("SELECT * FROM ds LIMIT 0").description]
    rows = con.execute("SELECT * FROM ds").fetchall()

    stem = out / f"deprecated_replacement_{snap.replace('-', '')}"
    with open(f"{stem}.csv", "w", encoding="utf-8-sig", newline="") as f:  # BOM: 엑셀에서 한글·이모지 깨짐 방지
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([("|".join(x) if isinstance(x, list) else str(x).lower() if isinstance(x, bool)
                         else (x.isoformat() if hasattr(x, "isoformat") else x)) for x in r])
    with open(f"{stem}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            d = {c: (x.isoformat() if hasattr(x, "isoformat") else x) for c, x in zip(cols, r)}
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    pq = pq_out / f"deprecated_replacement_{snap.replace('-', '')}.parquet"
    con.execute("COPY ds TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(pq)])
    print(f"\n저장: {stem}.csv / {stem}.jsonl / {pq}  ({len(rows):,}행)")


if __name__ == "__main__":
    main()
