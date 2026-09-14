-- Local recovery BEFORE any subsequent data changes. ON_ERROR_STOP required.
-- Execute inside BEGIN/COMMIT; all checks and the switch must share a transaction.
CREATE OR REPLACE FUNCTION pg_temp.vd_require(ok boolean, message text) RETURNS void
LANGUAGE plpgsql AS $$ BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION '%', message; END IF; END $$;
SELECT pg_temp.vd_require(current_database()='pickage_267_full_defaulted'
 AND (SELECT system_identifier::text='7683005534478250019' FROM pg_control_system()), 'Wrong database');
SELECT pg_temp.vd_require(pg_try_advisory_xact_lock(hashtextextended('curated:package-version',0)), 'Package loader active');
SELECT pg_temp.vd_require(pg_try_advisory_xact_lock(hashtextextended('curated:version-dependents',0)), 'Dependents loader active');
LOCK TABLE public.package_version_snapshot,vd193_backup_20260913.package_version_snapshot IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.etl_load_execution,public.etl_load_attempt,public.etl_dataset_current,
 vd193_reload_20260912_ready01.etl_load_execution,vd193_reload_20260912_ready01.etl_load_attempt,
 vd193_reload_20260912_ready01.etl_dataset_current,
 vd193_backup_20260913.etl_load_execution,vd193_backup_20260913.etl_load_attempt,
 vd193_backup_20260913.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;
SELECT pg_temp.vd_require('public.package_version_snapshot'::regclass::oid=280767
 AND 'vd193_backup_20260913.package_version_snapshot'::regclass::oid=87774
 AND to_regclass('vd193_reload_20260912_ready01.package_version_snapshot') IS NULL, 'Recovery identity changed');
SELECT pg_temp.vd_require((SELECT count(*)=229 FROM pg_inherits WHERE inhparent=280767)
 AND (SELECT sum(n_tup_ins)=1007084608 AND sum(n_tup_upd)=0 AND sum(n_tup_del)=0
 FROM pg_stat_all_tables WHERE relid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent=280767)), 'Data changed or statistics unavailable; review recovery');
SELECT pg_temp.vd_require(NOT EXISTS(SELECT 1 FROM pg_constraint WHERE confrelid=280767)
 AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE refclassid='pg_class'::regclass AND refobjid=280767 AND deptype='n'
 AND NOT (classid='pg_constraint'::regclass AND EXISTS(SELECT 1 FROM pg_constraint c WHERE c.oid=d.objid AND c.conrelid=280767)))
 AND NOT EXISTS(SELECT 1 FROM pg_depend WHERE refclassid='pg_type'::regclass AND refobjid=(SELECT reltype FROM pg_class WHERE oid=280767) AND deptype='n'), 'New service dependency; review recovery');
SELECT pg_temp.vd_require(NOT EXISTS(
 (SELECT * FROM public.etl_load_execution WHERE dataset='version-dependents' EXCEPT ALL SELECT * FROM vd193_reload_20260912_ready01.etl_load_execution)
 UNION ALL (SELECT * FROM vd193_reload_20260912_ready01.etl_load_execution EXCEPT ALL SELECT * FROM public.etl_load_execution WHERE dataset='version-dependents')), 'Execution history changed');
SELECT pg_temp.vd_require(NOT EXISTS(
 (SELECT a.* FROM public.etl_load_attempt a JOIN public.etl_load_execution e USING(execution_id) WHERE e.dataset='version-dependents' EXCEPT ALL SELECT * FROM vd193_reload_20260912_ready01.etl_load_attempt)
 UNION ALL (SELECT * FROM vd193_reload_20260912_ready01.etl_load_attempt EXCEPT ALL SELECT a.* FROM public.etl_load_attempt a JOIN public.etl_load_execution e USING(execution_id) WHERE e.dataset='version-dependents')), 'Attempt history changed');
SELECT pg_temp.vd_require(NOT EXISTS(
 (SELECT * FROM public.etl_dataset_current WHERE dataset='version-dependents' EXCEPT ALL SELECT * FROM vd193_reload_20260912_ready01.etl_dataset_current)
 UNION ALL (SELECT * FROM vd193_reload_20260912_ready01.etl_dataset_current EXCEPT ALL SELECT * FROM public.etl_dataset_current WHERE dataset='version-dependents')), 'Current pointer changed');
SET CONSTRAINTS ALL DEFERRED;
DELETE FROM public.etl_dataset_current WHERE dataset='version-dependents';
DELETE FROM public.etl_load_attempt WHERE execution_id IN (SELECT execution_id FROM vd193_reload_20260912_ready01.etl_load_execution);
DELETE FROM public.etl_load_execution WHERE dataset='version-dependents';
INSERT INTO public.etl_load_execution SELECT * FROM vd193_backup_20260913.etl_load_execution;
INSERT INTO public.etl_load_attempt SELECT * FROM vd193_backup_20260913.etl_load_attempt;
INSERT INTO public.etl_dataset_current SELECT * FROM vd193_backup_20260913.etl_dataset_current;
ALTER TABLE public.package_version_snapshot SET SCHEMA vd193_reload_20260912_ready01;
ALTER TABLE vd193_backup_20260913.package_version_snapshot SET SCHEMA public;
SET CONSTRAINTS ALL IMMEDIATE;
SELECT pg_temp.vd_require('public.package_version_snapshot'::regclass::oid=87774
 AND 'vd193_reload_20260912_ready01.package_version_snapshot'::regclass::oid=280767, 'Recovery identity mismatch');
