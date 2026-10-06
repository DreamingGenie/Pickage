-- S15P21A506-475 — available_package 를 백업 표로 되돌린다.
--
-- psql 변수:
--   backup_table  available_package_swap.sql 이 만든 백업 표 이름
--   verify_only   on|off
--
-- 백업 표는 지우지 않는다. 되돌린 뒤 이상이 없으면 사람이 따로 DROP 한다.

\set ON_ERROR_STOP on
\timing on

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TEMP TABLE _params ON COMMIT DROP AS SELECT :'backup_table'::text AS backup_table;
DO $$
DECLARE t text; n bigint;
BEGIN
  SELECT backup_table INTO t FROM _params;
  IF to_regclass(t) IS NULL THEN
    RAISE EXCEPTION '중단: 백업 표 % 가 없다', t;
  END IF;
  EXECUTE format('SELECT count(*) FROM %I', t) INTO n;
  IF n = 0 THEN
    RAISE EXCEPTION '중단: 백업 표 % 가 비어 있다', t;
  END IF;
END $$;

LOCK TABLE available_package IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM available_package;
INSERT INTO available_package (package_id, package_name, created_at)
SELECT package_id, package_name, created_at FROM :"backup_table";

SELECT count(*) AS available_rows, (SELECT count(*) FROM :"backup_table") AS backup_rows FROM available_package;

\if :verify_only
  \echo '검증 전용 — ROLLBACK'
  ROLLBACK;
\else
  COMMIT;
  \echo '되돌림 완료 — COMMIT'
\endif
