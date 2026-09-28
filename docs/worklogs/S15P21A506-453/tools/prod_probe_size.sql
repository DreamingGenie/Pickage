SELECT now()::time(0) AS at, pg_size_pretty(pg_relation_size('package_env')) AS heap, pg_size_pretty(pg_indexes_size('package_env')) AS idx, pg_relation_size('package_env') AS heap_bytes;
