\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='2s';
SELECT jsonb_build_object(
 'database',current_database(),
 'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),
 'server_version',current_setting('server_version'),
 'read_only',current_setting('transaction_read_only'),
 'tables',(SELECT jsonb_agg(jsonb_build_object('name',c.relname,'oid',c.oid,'kind',c.relkind,'estimated_rows',c.reltuples,'bytes',pg_total_relation_size(c.oid))) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('package','version','snapshot','package_snapshot','package_version_snapshot')),
 'executions',(SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT dataset,status,count(*) AS executions,min(snapshot_at) AS first_date,max(snapshot_at) AS last_date FROM public.etl_load_execution GROUP BY dataset,status ORDER BY dataset,status) x),
 'current',(SELECT jsonb_agg(jsonb_build_object('dataset',dataset,'execution_id',execution_id,'snapshot_at',snapshot_at,'manifest_sha256',manifest_sha256,'manifest_keys',(SELECT jsonb_agg(k) FROM jsonb_object_keys(manifest) k))) FROM public.etl_dataset_current),
 'other_active_sessions',(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state='active')
);
ROLLBACK;
