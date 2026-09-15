-- V1 이력을 복제한 후보 DB의 빈 서비스 테이블만 제거한다.
-- 먼저 같은 배포 revision으로 Flyway validate(target=1)를 실행해야 한다.
-- psql -X -v ON_ERROR_STOP=1 -f prepare_candidate.sql
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $guard$
DECLARE
    relation_name text;
    has_rows boolean;
BEGIN
    IF current_database() !~ '^pickage_import_341_[a-z0-9_]+$' THEN
        RAISE EXCEPTION 'Not a 341 candidate database: %', current_database();
    END IF;
    IF to_regclass('public.flyway_schema_history') IS NULL THEN
        RAISE EXCEPTION 'Genuine V1 Flyway history is required';
    END IF;
    IF (SELECT count(*) FROM public.flyway_schema_history) <> 1
       OR NOT EXISTS (SELECT 1 FROM public.flyway_schema_history
                      WHERE version = '1' AND type = 'SQL' AND success AND checksum IS NOT NULL) THEN
        RAISE EXCEPTION 'Only successfully applied V1 history is supported';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp'
          AND c.relkind IN ('r','p','v','m','f','S')
          AND NOT (n.nspname = 'public' AND c.relname IN
            ('package','version','snapshot','package_snapshot','package_version_snapshot','flyway_schema_history'))
    ) THEN
        RAISE EXCEPTION 'Candidate contains unexpected relations; nothing removed';
    END IF;
    FOREACH relation_name IN ARRAY ARRAY['package','version','snapshot','package_snapshot','package_version_snapshot'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_class WHERE oid = to_regclass('public.' || relation_name)
                       AND relkind = 'r' AND relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)) THEN
            RAISE EXCEPTION 'Missing, partitioned or differently owned candidate table: %', relation_name;
        END IF;
        EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', relation_name);
    END LOOP;
    FOREACH relation_name IN ARRAY ARRAY['package','version','snapshot','package_snapshot','package_version_snapshot'] LOOP
        EXECUTE format('SELECT EXISTS (SELECT FROM public.%I LIMIT 1)', relation_name) INTO STRICT has_rows;
        IF has_rows THEN
            RAISE EXCEPTION 'Candidate table % is not empty; nothing removed', relation_name;
        END IF;
    END LOOP;
END $guard$;
-- CASCADE 금지: 예상 밖 view/FK 의존성이 있으면 전체 트랜잭션을 되돌린다.
DROP TABLE public.package_version_snapshot;
DROP TABLE public.package_snapshot;
DROP TABLE public.version;
DROP TABLE public.package;
DROP TABLE public.snapshot;
COMMIT;
