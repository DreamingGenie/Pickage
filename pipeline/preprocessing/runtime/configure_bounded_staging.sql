\set ON_ERROR_STOP on
-- Run only against an explicitly selected bounded cluster, as the loader role.
-- This script does not discard an existing load or truncate staging data.
DO $$ BEGIN
  IF (SELECT sum(pg_total_relation_size(name::regclass)) FROM unnest(ARRAY[
      'public.etl_curated_stage_package', 'public.etl_curated_stage_version',
      'public.etl_curated_stage_package_snapshot',
      'public.etl_curated_stage_version_snapshot']) AS name) > 1000000 THEN
    RAISE EXCEPTION 'Existing staging must be cleaned by its owner before migration';
  END IF;
  IF EXISTS (SELECT 1 FROM public.etl_curated_stage_package)
      OR EXISTS (SELECT 1 FROM public.etl_curated_stage_version)
      OR EXISTS (SELECT 1 FROM public.etl_curated_stage_package_snapshot)
      OR EXISTS (SELECT 1 FROM public.etl_curated_stage_version_snapshot) THEN
    RAISE EXCEPTION 'An existing staged load must not be moved';
  END IF;
END $$;
SELECT 'CREATE TABLESPACE curated_work LOCATION ''/run/pickage-postgres-bounded/staging'''
WHERE NOT EXISTS (SELECT FROM pg_tablespace WHERE spcname='curated_work')
\gexec
DO $$ BEGIN
  IF pg_tablespace_location((SELECT oid FROM pg_tablespace WHERE spcname='curated_work'))
      <> '/run/pickage-postgres-bounded/staging' THEN
    RAISE EXCEPTION 'Unexpected processing tablespace location';
  END IF;
END $$;
SELECT format('ALTER TABLE public.%I SET TABLESPACE curated_work', name)
FROM (VALUES ('etl_curated_stage_package'), ('etl_curated_stage_version'),
             ('etl_curated_stage_package_snapshot'),
             ('etl_curated_stage_version_snapshot')) AS owned(name)
\gexec
SELECT format('ALTER INDEX %s SET TABLESPACE curated_work', i.indexrelid::regclass)
FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
WHERE c.relnamespace='public'::regnamespace AND c.relname IN (
    'etl_curated_stage_package', 'etl_curated_stage_version',
    'etl_curated_stage_package_snapshot', 'etl_curated_stage_version_snapshot')
\gexec
SELECT format('ALTER DATABASE %I SET temp_tablespaces=''curated_work''', current_database())
\gexec
SELECT format('ALTER ROLE %I IN DATABASE %I SET temp_file_limit=''8GB''',
              current_user, current_database())
\gexec
CHECKPOINT;
