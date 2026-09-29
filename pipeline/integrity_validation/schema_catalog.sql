-- PostgreSQL only. Deferred, read-only catalog evidence; not a schema PASS decision.
-- Compare to V1~V4 and the selected run's schema fingerprint in an isolated validation DB.
\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '2s';

SELECT table_name, ordinal_position, column_name, data_type, udt_name,
       character_maximum_length, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('package', 'version', 'snapshot', 'package_snapshot', 'package_version_snapshot')
ORDER BY table_name, ordinal_position;

SELECT t.relname AS table_name, c.conname, c.contype, c.convalidated,
       c.condeferrable, c.condeferred,
       pg_get_constraintdef(c.oid) AS ordered_definition
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname IN ('package', 'version', 'snapshot', 'package_snapshot', 'package_version_snapshot')
ORDER BY t.relname, c.conname;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('package', 'version', 'snapshot', 'package_snapshot', 'package_version_snapshot')
ORDER BY tablename, indexname;

ROLLBACK;
