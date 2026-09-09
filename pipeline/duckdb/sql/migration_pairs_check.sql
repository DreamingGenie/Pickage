-- 마이그레이션 이동쌍 확인 쿼리 모음 (DuckDB)
--
-- [A] 원천 뷰(requirements / versions_full)만으로 계산하는 쿼리 — 팀원 PC(duckdb_ui.py)에서 그대로 실행 가능
-- [B] build_migration_pairs.py 가 남기는 data/migration_pairs.duckdb 의 pairs / events 테이블 기준 쿼리
-- 실행: 빌드가 끝난 뒤(파일 잠금 해제 후) read_only 로 연다.
--   .venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py -c "ATTACH 'data/migration_pairs.duckdb' AS mp (READ_ONLY)" 처럼 UI 카탈로그에 붙이거나,
--   DuckDB UI(localhost:4213) SQL 편집기에 ATTACH 문을 먼저 실행한 뒤 아래 쿼리의 pairs/events 를 mp.pairs/mp.events 로 바꿔 실행한다.
--
-- 컬럼 의미 (pairs)
--   votes            제거 이벤트 1건을 added 개수로 나눠 분배한 표의 합
--   co_events        from_pkg 제거 + to_pkg 추가가 같은 전이에서 일어난 횟수
--   removal_events   from_pkg 가 제거된 전이 수 (추가가 있는 것만)
--   a_rate           co_events / removal_events   (A: X 뺀 전이 중 Y 넣은 비율)
--   b_rate           npm 전수 전이 중 Y 를 추가한 비율 (B: 기저율)
--   lift             a_rate / b_rate
--   publisher_months 배포주체×월 단위 중복 제거 표본 수
-- 필터 기준: strict = lift>=5 AND votes>=12 AND publisher_months>=10 AND a_rate>=0.03 / loose = lift>=5 AND votes>=3


-- ============================================================================
-- [A] 원천 뷰만으로 계산 (duckdb_ui.py 환경: requirements / versions_full 뷰만 있는 팀원 PC)
--     build_migration_pairs.py 의 1~6단계를 한 쿼리로 접었다. pairs 테이블이 없어도 돈다.
--     비용: requirements(17 GiB)+versions_full(24 GiB) 전수 스캔 + 윈도우. 로컬 기준 수십 분.
--     메모리 부족하면 먼저 실행:  SET memory_limit='24GB'; SET temp_directory='data/duckdb_tmp'; SET preserve_insertion_order=false;
-- ============================================================================

-- A1. X 를 뺀 사람들이 무엇으로 갈아탔나 (lift 포함, 결과 = pairs 테이블과 동일 정의)
--     첫 줄 'moment' 만 바꿔 쓴다.
WITH x AS (SELECT 'moment' AS pkg),
rel AS (
  SELECT r.Name, r.Version, v.published_at, v.source_repo,
         list_sort(list_transform(r.Dependencies, d -> d.Name)) AS deps,
         coalesce(list_transform(r.PeerDependencies, d -> d.Name), []::VARCHAR[])
           || coalesce(list_transform(r.OptionalDependencies, d -> d.Name), []::VARCHAR[]) AS nonreg
  FROM requirements r
  JOIN versions_full v ON v.Name = r.Name AND v.Version = r.Version AND v.snapshot = r.snapshot
  WHERE r.snapshot = '2026-08-31' AND v.is_release AND v.published_at IS NOT NULL
    AND regexp_matches(r.Version, '^\d+\.\d+')
),
seq AS (
  SELECT Name, Version, published_at, deps, nonreg,
    CASE WHEN try_cast(regexp_extract(Version, '^(\d+)\.(\d+)', 1) AS INT) > 0 THEN regexp_extract(Version, '^(\d+)\.(\d+)', 1)
         ELSE '0.' || regexp_extract(Version, '^(\d+)\.(\d+)', 2) END AS line,
    CASE WHEN Name LIKE '@%' THEN split_part(Name, '/', 1)
         WHEN source_repo IS NOT NULL THEN regexp_replace(lower(source_repo), '\.git$|^git\+|^https?://|^git://|^ssh://git@', '', 'g')
         ELSE Name END AS publisher
  FROM rel
),
trans AS (
  SELECT Name, publisher, line, from_version, to_version, to_ts,
         list_filter(removed_raw, e -> NOT list_contains(nonreg, e)) AS removed, added
  FROM (
    SELECT Name, publisher, line, lag(Version) OVER w AS from_version, Version AS to_version, published_at AS to_ts, nonreg,
           list_filter(lag(deps) OVER w, e -> NOT list_contains(deps, e)) AS removed_raw,
           list_filter(deps, e -> NOT list_contains(lag(deps) OVER w, e)) AS added
    FROM seq WINDOW w AS (PARTITION BY Name, line ORDER BY published_at)
    QUALIFY from_version IS NOT NULL
  )
),
n AS (SELECT count(*) AS n_trans FROM trans),
base AS (
  SELECT y AS to_pkg, count(*)::DOUBLE / (SELECT n_trans FROM n) AS b_rate
  FROM trans, unnest(added) AS u(y) GROUP BY y
),
events AS (
  SELECT Name AS dependent, publisher, to_ts, added, 1.0 / len(added) AS vote_each
  FROM trans WHERE list_contains(removed, (SELECT pkg FROM x)) AND len(added) > 0
),
rm AS (SELECT count(*) AS removal_events FROM events),
ev AS (
  SELECT y AS to_pkg, sum(vote_each) AS votes, count(*) AS co_events,
         count(DISTINCT publisher || '|' || strftime(to_ts, '%Y-%m')) AS publisher_months,
         count(DISTINCT dependent) AS dependents, min(to_ts) AS first_seen, max(to_ts) AS last_seen
  FROM events, unnest(added) AS u(y) WHERE y <> (SELECT pkg FROM x) GROUP BY y
),
pairs_x AS (
  SELECT (SELECT pkg FROM x) AS from_pkg, ev.to_pkg, ev.votes, ev.co_events, ev.publisher_months, ev.dependents,
         rm.removal_events, ev.co_events::DOUBLE / rm.removal_events AS a_rate, base.b_rate,
         (ev.co_events::DOUBLE / rm.removal_events) / base.b_rate AS lift, ev.first_seen, ev.last_seen
  FROM ev CROSS JOIN rm JOIN base USING (to_pkg)
)
SELECT from_pkg, to_pkg, round(votes, 1) AS votes,
       round(votes / sum(votes) OVER (), 3) AS share,
       co_events, removal_events, publisher_months, dependents,
       round(a_rate * 100, 2) AS a_pct, round(b_rate * 100, 4) AS b_pct, round(lift, 1) AS lift,
       CASE WHEN lift >= 5 AND votes >= 12 AND publisher_months >= 10 AND a_rate >= 0.03 THEN 'strict'
            WHEN lift >= 5 AND votes >= 3 THEN 'loose' ELSE '-' END AS grade,
       strftime(first_seen, '%Y-%m-%d') AS first_seen, strftime(last_seen, '%Y-%m-%d') AS last_seen
FROM pairs_x
WHERE lift >= 5 AND votes >= 3
ORDER BY votes DESC
LIMIT 30;

-- A2. 가벼운 버전 (lift 없음): X 를 의존한 적 있는 패키지만 윈도우 → 메모리 부담이 작다 (스캔은 2회라 시간은 비슷할 수 있음)
--     votes·share·a_pct 는 A1 과 같고, b_pct·lift 만 없다. 후보를 빨리 훑을 때 쓴다.
WITH x AS (SELECT 'moment' AS pkg),
rel AS (
  SELECT r.Name, r.Version, v.published_at, v.source_repo,
         list_sort(list_transform(r.Dependencies, d -> d.Name)) AS deps,
         coalesce(list_transform(r.PeerDependencies, d -> d.Name), []::VARCHAR[])
           || coalesce(list_transform(r.OptionalDependencies, d -> d.Name), []::VARCHAR[]) AS nonreg
  FROM requirements r
  JOIN versions_full v ON v.Name = r.Name AND v.Version = r.Version AND v.snapshot = r.snapshot
  WHERE r.snapshot = '2026-08-31' AND v.is_release AND v.published_at IS NOT NULL
    AND regexp_matches(r.Version, '^\d+\.\d+')
    AND r.Name IN (SELECT DISTINCT Name FROM requirements, unnest(Dependencies) AS u(d)
                   WHERE snapshot = '2026-08-31' AND d.Name = (SELECT pkg FROM x))
),
seq AS (
  SELECT Name, Version, published_at, deps, nonreg,
    CASE WHEN try_cast(regexp_extract(Version, '^(\d+)\.(\d+)', 1) AS INT) > 0 THEN regexp_extract(Version, '^(\d+)\.(\d+)', 1)
         ELSE '0.' || regexp_extract(Version, '^(\d+)\.(\d+)', 2) END AS line,
    CASE WHEN Name LIKE '@%' THEN split_part(Name, '/', 1)
         WHEN source_repo IS NOT NULL THEN regexp_replace(lower(source_repo), '\.git$|^git\+|^https?://|^git://|^ssh://git@', '', 'g')
         ELSE Name END AS publisher
  FROM rel
),
trans AS (
  SELECT Name, publisher, to_ts,
         list_filter(removed_raw, e -> NOT list_contains(nonreg, e)) AS removed, added
  FROM (
    SELECT Name, publisher, lag(Version) OVER w AS from_version, published_at AS to_ts, nonreg,
           list_filter(lag(deps) OVER w, e -> NOT list_contains(deps, e)) AS removed_raw,
           list_filter(deps, e -> NOT list_contains(lag(deps) OVER w, e)) AS added
    FROM seq WINDOW w AS (PARTITION BY Name, line ORDER BY published_at)
    QUALIFY from_version IS NOT NULL
  )
),
events AS (
  SELECT Name AS dependent, publisher, to_ts, added, 1.0 / len(added) AS vote_each
  FROM trans WHERE list_contains(removed, (SELECT pkg FROM x)) AND len(added) > 0
),
rm AS (SELECT count(*) AS removal_events FROM events),
ev AS (
  SELECT y AS to_pkg, sum(vote_each) AS votes, count(*) AS co_events,
         count(DISTINCT publisher || '|' || strftime(to_ts, '%Y-%m')) AS publisher_months,
         count(DISTINCT dependent) AS dependents, min(to_ts) AS first_seen, max(to_ts) AS last_seen
  FROM events, unnest(added) AS u(y) WHERE y <> (SELECT pkg FROM x) GROUP BY y
)
SELECT (SELECT pkg FROM x) AS from_pkg, to_pkg, round(votes, 1) AS votes,
       round(votes / sum(votes) OVER (), 3) AS share,
       co_events, rm.removal_events, publisher_months, dependents,
       round(co_events * 100.0 / rm.removal_events, 2) AS a_pct,
       strftime(first_seen, '%Y-%m-%d') AS first_seen, strftime(last_seen, '%Y-%m-%d') AS last_seen
FROM ev CROSS JOIN rm
WHERE votes >= 3
ORDER BY votes DESC
LIMIT 30;

-- ============================================================================
-- [B] 빌드 결과 테이블 기준 (data/migration_pairs.duckdb 의 pairs / events 가 있는 환경)
-- ============================================================================

-- B1. 특정 패키지 X 를 뺀 사람들이 무엇으로 갈아탔나 (이동쌍 조회, 핵심 쿼리)
--     :from_pkg 를 바꿔 쓴다. share = X 에서 나간 표 중 Y 가 차지한 비율
WITH x AS (SELECT 'moment' AS from_pkg)
SELECT p.from_pkg, p.to_pkg,
       round(p.votes, 1)                                        AS votes,
       round(p.votes / sum(p.votes) OVER (), 3)                 AS share,
       p.co_events, p.removal_events, p.publisher_months, p.dependents,
       round(p.a_rate * 100, 2)                                 AS a_pct,
       round(p.b_rate * 100, 4)                                 AS b_pct,
       round(p.lift, 1)                                         AS lift,
       CASE WHEN p.lift >= 5 AND p.votes >= 12 AND p.publisher_months >= 10 AND p.a_rate >= 0.03 THEN 'strict'
            WHEN p.lift >= 5 AND p.votes >= 3 THEN 'loose'
            ELSE '-' END                                        AS grade,
       strftime(p.first_seen, '%Y-%m-%d') AS first_seen,
       strftime(p.last_seen,  '%Y-%m-%d') AS last_seen
FROM pairs p JOIN x USING (from_pkg)
WHERE p.lift >= 5 AND p.votes >= 3
ORDER BY p.votes DESC
LIMIT 30;

-- B2. 특정 (X → Y) 쌍의 실제 근거 이벤트 (어느 패키지가 언제 어떤 버전에서 바꿨는지)
SELECT dependent, publisher, line, from_version, to_version,
       strftime(to_ts, '%Y-%m-%d') AS changed_at,
       array_to_string(added, '|') AS added_pkgs, added_count, round(vote_each, 3) AS vote_each
FROM events
WHERE removed_pkg = 'moment' AND list_contains(added, 'dayjs')
ORDER BY to_ts DESC
LIMIT 50;

-- B3. 특정 Y 로 유입된 원천 (반대 방향: 무엇을 버리고 Y 를 택했나)
SELECT from_pkg, to_pkg, round(votes, 1) AS votes, co_events, publisher_months, round(lift, 1) AS lift
FROM pairs
WHERE to_pkg = 'dayjs' AND lift >= 5 AND votes >= 3
ORDER BY votes DESC
LIMIT 30;

-- B4. strict 통과 쌍 전체 상위 (기획서 '이동 지도' 후보)
SELECT from_pkg, to_pkg, round(votes, 1) AS votes, co_events, removal_events, publisher_months, dependents,
       round(a_rate * 100, 2) AS a_pct, round(lift, 1) AS lift
FROM pairs
WHERE lift >= 5 AND votes >= 12 AND publisher_months >= 10 AND a_rate >= 0.03
ORDER BY votes DESC
LIMIT 100;

-- B5. X 별 이동 지도 요약: 대체재 개수·1순위 대체재·1순위 점유율 (strict 기준)
WITH s AS (
  SELECT * FROM pairs WHERE lift >= 5 AND votes >= 12 AND publisher_months >= 10 AND a_rate >= 0.03
), ranked AS (
  SELECT *, row_number() OVER (PARTITION BY from_pkg ORDER BY votes DESC) AS rn,
         votes / sum(votes) OVER (PARTITION BY from_pkg) AS share
  FROM s
)
SELECT from_pkg,
       count(*)                                        AS n_targets,
       max(CASE WHEN rn = 1 THEN to_pkg END)           AS top_target,
       round(max(CASE WHEN rn = 1 THEN share END), 3)  AS top_share,
       round(sum(votes), 1)                            AS total_votes,
       max(removal_events)                             AS removal_events
FROM ranked
GROUP BY from_pkg
ORDER BY total_votes DESC
LIMIT 100;

-- B6. 양방향 쌍 점검 (X→Y 와 Y→X 둘 다 살아 있으면 대체가 아니라 동시 유행일 가능성)
SELECT a.from_pkg, a.to_pkg, round(a.votes, 1) AS votes_fwd, round(b.votes, 1) AS votes_rev,
       round(a.lift, 1) AS lift_fwd, round(b.lift, 1) AS lift_rev
FROM pairs a JOIN pairs b ON a.from_pkg = b.to_pkg AND a.to_pkg = b.from_pkg
WHERE a.lift >= 5 AND a.votes >= 3 AND b.lift >= 5 AND b.votes >= 3 AND a.from_pkg < a.to_pkg
ORDER BY least(a.votes, b.votes) DESC
LIMIT 50;

-- B7. 필터 단계별 잔존 개수 (임계값 조정 근거)
SELECT 'lift>=5'                          AS step, count(*) AS pairs, count(DISTINCT from_pkg) AS from_pkgs FROM pairs WHERE lift >= 5
UNION ALL SELECT 'lift>=5, votes>=3',      count(*), count(DISTINCT from_pkg) FROM pairs WHERE lift >= 5 AND votes >= 3
UNION ALL SELECT 'lift>=5, votes>=12',     count(*), count(DISTINCT from_pkg) FROM pairs WHERE lift >= 5 AND votes >= 12
UNION ALL SELECT '+ publisher_months>=10', count(*), count(DISTINCT from_pkg) FROM pairs WHERE lift >= 5 AND votes >= 12 AND publisher_months >= 10
UNION ALL SELECT '+ a_rate>=0.03 (strict)',count(*), count(DISTINCT from_pkg) FROM pairs WHERE lift >= 5 AND votes >= 12 AND publisher_months >= 10 AND a_rate >= 0.03;

-- B8. 결과 CSV 만 있을 때 (duckdb 없이) 동일 조회
-- SELECT * FROM read_csv('datasets/migration_pairs_260908/migration_pairs_all.csv') WHERE from_pkg = 'moment' ORDER BY votes DESC;
-- SELECT * FROM read_parquet('data/migration_pairs/migration_events.parquet') WHERE removed_pkg = 'moment' AND list_contains(added_pkgs, 'dayjs');
