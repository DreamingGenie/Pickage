SELECT pid, state, wait_event_type, wait_event, now()-xact_start AS xact_age, now()-query_start AS q_age, left(regexp_replace(query, '\s+', ' ', 'g'), 110) AS query FROM pg_stat_activity WHERE datname='pickage' AND pid <> pg_backend_pid() AND state <> 'idle' ORDER BY xact_start;
SELECT relname, n_live_tup, n_dead_tup FROM pg_stat_user_tables WHERE relname IN ('package_env');
