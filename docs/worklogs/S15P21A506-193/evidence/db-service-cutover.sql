-- Local one-time cutover; run with ON_ERROR_STOP inside one transaction.
-- Pinned to pickage_267_full_defaulted, system identifier 7683005534478250019.
CREATE FUNCTION pg_temp.vd_require(ok boolean, message text) RETURNS void
LANGUAGE plpgsql AS $$ BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION '%', message; END IF; END $$;
SELECT pg_temp.vd_require(current_database()='pickage_267_full_defaulted'
 AND (SELECT system_identifier::text='7683005534478250019' FROM pg_control_system()), 'Wrong database');
SELECT pg_temp.vd_require(pg_try_advisory_xact_lock(hashtextextended('curated:package-version',0)), 'Package loader active');
SELECT pg_temp.vd_require(pg_try_advisory_xact_lock(hashtextextended('curated:version-dependents',0)), 'Dependents loader active');
LOCK TABLE public.package_version_snapshot,vd193_reload_20260912_ready01.package_version_snapshot IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.etl_load_execution,public.etl_load_attempt,public.etl_dataset_current,
 vd193_reload_20260912_ready01.etl_load_execution,vd193_reload_20260912_ready01.etl_load_attempt,
 vd193_reload_20260912_ready01.etl_dataset_current,vd193_reload_20260912_ready01.reload_plan,
 vd193_reload_20260912_ready01.reload_partition IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.version,public.snapshot,public.etl_snapshot_reference IN SHARE MODE;
SELECT pg_temp.vd_require('public.package_version_snapshot'::regclass::oid=87774
 AND 'vd193_reload_20260912_ready01.package_version_snapshot'::regclass::oid=280767, 'Table identity changed');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='vd193_backup_20260913'), 'Backup already exists');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM pg_constraint WHERE confrelid=87774)
 AND NOT EXISTS(SELECT 1 FROM pg_depend WHERE refclassid='pg_class'::regclass AND refobjid=87774 AND deptype='n')
 AND NOT EXISTS(SELECT 1 FROM pg_depend WHERE refclassid='pg_type'::regclass AND refobjid=(SELECT reltype FROM pg_class WHERE oid=87774) AND deptype='n'), 'External service dependency appeared');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM pg_class WHERE oid IN (87774,280767)
 AND (relowner<>(SELECT oid FROM pg_roles WHERE rolname=current_user) OR relrowsecurity OR relhasrules))
 AND NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid IN (87774,280767) AND NOT tgisinternal), 'Owner/policy/trigger changed');
SELECT pg_temp.vd_require((SELECT count(*)=229 AND sum(rows)=1007084608
 FROM vd193_reload_20260912_ready01.reload_partition), 'Incomplete receipts');
SELECT pg_temp.vd_require((SELECT count(*)=229 FROM pg_inherits WHERE inhparent=280767)
 AND NOT EXISTS(SELECT 1 FROM vd193_reload_20260912_ready01.reload_partition r
 LEFT JOIN pg_inherits i ON i.inhrelid=r.child_oid AND i.inhparent=280767 WHERE i.inhrelid IS NULL), 'Partition identity mismatch');
SELECT pg_temp.vd_require((SELECT sum(n_tup_ins)=1007084608 AND sum(n_tup_upd)=0 AND sum(n_tup_del)=0
 FROM pg_stat_all_tables WHERE relid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent=280767)), 'Loaded data changed or statistics unavailable');
SELECT pg_temp.vd_require((SELECT count(*)=229 AND bool_and(status='PUBLISHED' AND dataset='version-dependents')
 FROM vd193_reload_20260912_ready01.etl_load_execution), 'Incomplete execution history');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM public.etl_snapshot_reference r
 JOIN public.etl_load_execution e USING(execution_id) WHERE e.dataset='version-dependents'), 'Old history has external reference');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM public.etl_load_execution e
 JOIN vd193_reload_20260912_ready01.etl_load_execution n USING(execution_id))
 AND NOT EXISTS(SELECT 1 FROM public.etl_load_attempt a
 JOIN vd193_reload_20260912_ready01.etl_load_attempt n USING(attempt_id)), 'History ID collision');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM public.etl_load_execution WHERE status='PREPARING'), 'Unfinished public load');
CREATE SCHEMA vd193_backup_20260913 AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA vd193_backup_20260913 FROM PUBLIC;
CREATE TABLE vd193_backup_20260913.etl_load_execution AS
 SELECT * FROM public.etl_load_execution WHERE dataset='version-dependents';
CREATE TABLE vd193_backup_20260913.etl_load_attempt AS
 SELECT a.* FROM public.etl_load_attempt a JOIN vd193_backup_20260913.etl_load_execution e USING(execution_id);
CREATE TABLE vd193_backup_20260913.etl_dataset_current AS
 SELECT * FROM public.etl_dataset_current WHERE dataset='version-dependents';
DELETE FROM public.etl_dataset_current WHERE dataset='version-dependents';
DELETE FROM public.etl_load_attempt WHERE execution_id IN (SELECT execution_id FROM vd193_backup_20260913.etl_load_execution);
DELETE FROM public.etl_load_execution WHERE dataset='version-dependents';
INSERT INTO public.etl_load_execution SELECT * FROM vd193_reload_20260912_ready01.etl_load_execution;
INSERT INTO public.etl_load_attempt SELECT * FROM vd193_reload_20260912_ready01.etl_load_attempt;
INSERT INTO public.etl_dataset_current SELECT * FROM vd193_reload_20260912_ready01.etl_dataset_current;
ALTER TABLE public.package_version_snapshot SET SCHEMA vd193_backup_20260913;
ALTER TABLE vd193_reload_20260912_ready01.package_version_snapshot SET SCHEMA public;
SET CONSTRAINTS ALL IMMEDIATE;
SELECT pg_temp.vd_require('public.package_version_snapshot'::regclass::oid=280767
 AND 'vd193_backup_20260913.package_version_snapshot'::regclass::oid=87774, 'Switch identity mismatch');
SELECT pg_temp.vd_require((SELECT count(*)=229 AND max(snapshot_at)=DATE '2026-08-31'
 FROM public.etl_load_execution WHERE dataset='version-dependents' AND status='PUBLISHED'), 'Public history mismatch');
