\timing off
SELECT attname, correlation FROM pg_stats WHERE tablename='package_snapshot' AND attname IN ('snapshot_at','package_id');
SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) AS size, indexdef FROM pg_indexes WHERE tablename='package_snapshot';
SELECT pg_size_pretty(pg_relation_size('package_snapshot')) AS heap, pg_size_pretty(pg_database_size(current_database())) AS db;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM package_snapshot WHERE snapshot_at = DATE '2026-08-31';
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM package_snapshot WHERE snapshot_at = DATE '2026-08-24';
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM package_snapshot WHERE snapshot_at = DATE '2025-03-03';
