#!/usr/bin/env python
"""내려받은 raw Parquet를 DuckDB로 훑어보는 스크립트. 읽기 전용, 결과는 화면 출력.

실행:  .venv-bq/Scripts/python pipeline/bigquery/inspect_duckdb.py [--quick]
  --quick : 무거운 쿼리(requirements 배열 펼치기)를 건너뜀
"""
import sys
import time

import duckdb

sys.stdout.reconfigure(encoding="utf-8")
QUICK = "--quick" in sys.argv
RAW = "data/raw"
T = {
    "versions_full": f"read_parquet('{RAW}/versions_full/snapshot=*/part-*.parquet', hive_partitioning=true)",
    "requirements": f"read_parquet('{RAW}/requirements/snapshot=*/part-*.parquet', hive_partitioning=true)",
    "pkg_project": f"read_parquet('{RAW}/pkg_project/snapshot=*/part-*.parquet', hive_partitioning=true)",
    "projects": f"read_parquet('{RAW}/projects/snapshot=*/part-*.parquet', hive_partitioning=true)",
}
con = duckdb.connect()
con.execute("SET threads TO 8; SET memory_limit = '12GB';")


def q(title: str, sql: str, heavy: bool = False) -> None:
    if heavy and QUICK:
        print(f"\n## {title}  (--quick: 건너뜀)")
        return
    print(f"\n## {title}")
    print(sql.strip())
    t0 = time.time()
    rel = con.sql(sql)
    print(rel.limit(30))
    print(f"   ({time.time() - t0:.1f}s)")


# 1. 스키마
for name, src in T.items():
    print(f"\n## 스키마 {name}")
    for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall():
        print(f"   {r[0]}: {r[1]}")

# 2. 행 수 — 매니페스트 기대치: versions_full 78,559,731 · requirements 78,559,731 · pkg_project 106,450,418
q("행 수 (T0 3테이블)", f"""
SELECT 'versions_full' t, COUNT(*) n FROM {T['versions_full']}
UNION ALL SELECT 'requirements', COUNT(*) FROM {T['requirements']}
UNION ALL SELECT 'pkg_project', COUNT(*) FROM {T['pkg_project']}
""")

# 3. Projects 스냅샷 분포 — 229개, 행 수는 해마다 증가
q("projects 스냅샷별 행 수 (처음 3·마지막 3)", f"""
WITH s AS (SELECT snapshot, COUNT(*) n FROM {T['projects']} GROUP BY 1)
SELECT * FROM (SELECT * FROM s ORDER BY snapshot LIMIT 3)
UNION ALL SELECT * FROM (SELECT * FROM s ORDER BY snapshot DESC LIMIT 3) ORDER BY snapshot
""")
q("projects 스냅샷 수 / 기간", f"""
SELECT COUNT(DISTINCT snapshot) snapshots, MIN(snapshot) first_snap, MAX(snapshot) last_snap FROM {T['projects']}
""")

# 4. 별 수 시계열 예시 — T1 백필의 존재 이유
q("expressjs/express 별·이슈 시계열 (연 1점)", f"""
SELECT snapshot, StarsCount, ForksCount, OpenIssuesCount
FROM {T['projects']}
WHERE Type='GITHUB' AND project_name='expressjs/express'
  AND (snapshot = (SELECT MAX(snapshot) FROM {T['projects']}) OR strftime(snapshot, '%m-%d') BETWEEN '01-01' AND '01-07')
ORDER BY snapshot
""")

# 5. versions_full 모집단 프로파일 — 09-01 문서 §2-2 재현 (npm 버전 78,559,731 · 폐기 3,884,071 · 발행시각 NULL 7,052,623)
q("versions_full 프로파일 (09-01 BigQuery 실측과 대조)", f"""
SELECT COUNT(*) AS n_versions, COUNT(DISTINCT Name) AS n_names,
       SUM(is_release::INT) AS n_releases,
       SUM((Deprecated IS NOT NULL)::INT) AS n_deprecated,
       SUM((published_at IS NULL)::INT) AS n_published_null,
       SUM(dependency_error::INT) AS n_dep_error,
       MIN(published_at) AS first_publish, MAX(published_at) AS last_publish
FROM {T['versions_full']}
""")

# 6. 표본
q("versions_full 표본: express 최신 3", f"""
SELECT Name, Version, is_release, ordinal, published_at, Licenses, source_repo
FROM {T['versions_full']} WHERE Name='express' ORDER BY ordinal DESC LIMIT 3
""")
q("requirements 표본: express@5.2.1 의존 선언 앞 5개", f"""
SELECT d.Name, d.Requirement
FROM (SELECT unnest(Dependencies) AS d FROM {T['requirements']} WHERE Name='express' AND Version='5.2.1') LIMIT 5
""")
q("pkg_project 표본: express 저장소 매핑 (RelationType별)", f"""
SELECT ProjectType, ProjectName, RelationType, COUNT(*) versions
FROM {T['pkg_project']} WHERE Name='express' GROUP BY 1,2,3 ORDER BY 4 DESC
""")

# 7. 무거운 검증 — 09-01 문서 §4-1 "누적 선언 패키지 수" 재현
#    BigQuery 실측(2026-08-31 대표 버전 기준): axios 152,316 · moment 51,443 · dayjs 20,916 · date-fns 19,423
#    여기서는 각 패키지의 Ordinal 최고 릴리스(발행시각 있음)를 대표로 잡는다.
q("역방향 의존 재현: 대표 릴리스가 regular로 선언한 패키지 수 (moment·dayjs·date-fns·axios)", f"""
WITH rep AS (
  SELECT Name, Version FROM (
    SELECT Name, Version, ROW_NUMBER() OVER (PARTITION BY Name ORDER BY ordinal DESC) rn
    FROM {T['versions_full']} WHERE is_release AND published_at IS NOT NULL
  ) WHERE rn = 1
),
decl AS (
  SELECT r.Name AS dependent, unnest(r.Dependencies) AS d
  FROM {T['requirements']} r JOIN rep USING (Name, Version)
)
SELECT d.Name AS dep, COUNT(DISTINCT dependent) AS n_dependents FROM decl
WHERE d.Name IN ('moment','dayjs','date-fns','axios','luxon') GROUP BY 1 ORDER BY 2 DESC
""", heavy=True)

print("\n끝. 다른 질의는 이 파일의 T[...] 문자열을 FROM에 그대로 쓰면 된다.")
