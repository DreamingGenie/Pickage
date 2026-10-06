-- Deferred PostgreSQL plan templates, adapted from PackageQueryRepository.
-- EXPLAIN without ANALYZE: estimates only, no measured latency/rows/buffers/WAL.
-- Select approved package/date inputs before a later isolated verification run.
-- Example parameters below are not proof that this run is approved or published.
\set ON_ERROR_STOP on
\set package_name 'react'
\set from_date '2026-08-24'
\set to_date '2026-08-31'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

EXPLAIN (VERBOSE, COSTS, FORMAT JSON)
SELECT p.name, ps.snapshot_at, ps.downloads AS value
FROM public.package_snapshot ps
JOIN public.package p ON p.package_id = ps.package_id
WHERE p.name = :'package_name'
  AND ps.snapshot_at BETWEEN :'from_date'::DATE AND :'to_date'::DATE
  AND ps.downloads IS NOT NULL
ORDER BY p.name, ps.snapshot_at;

EXPLAIN (VERBOSE, COSTS, FORMAT JSON)
SELECT p.name, pvs.snapshot_at, SUM(pvs.dependents_count) AS value
FROM public.package_version_snapshot pvs
JOIN public.package p ON p.package_id = pvs.package_id
WHERE p.name = :'package_name'
  AND pvs.snapshot_at BETWEEN :'from_date'::DATE AND :'to_date'::DATE
GROUP BY p.name, pvs.snapshot_at
ORDER BY p.name, pvs.snapshot_at;

EXPLAIN (VERBOSE, COSTS, FORMAT JSON)
WITH cur AS (
  SELECT p.name, pvs.version, pvs.dependents_count
  FROM public.package_version_snapshot pvs
  JOIN public.package p ON p.package_id = pvs.package_id
  WHERE p.name = :'package_name'
    AND pvs.snapshot_at = :'to_date'::DATE
    AND pvs.dependents_count > 0
)
SELECT name, split_part(version, '.', 1) AS major,
       SUM(dependents_count) AS dependents,
       ROUND(100.0 * SUM(dependents_count)
             / NULLIF(SUM(SUM(dependents_count)) OVER (PARTITION BY name), 0), 1) AS pct
FROM cur
GROUP BY name, 2
ORDER BY name, dependents DESC;

ROLLBACK;
