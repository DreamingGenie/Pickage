-- 교체가 끝나고 대조를 통과한 날짜의 옛 파티션을 지운다. 디스크가 실제로 줄어드는 유일한 단계다.
--
--   -v bak=vd455_backup_20260922
--   -v day=2026-08-31
--   -v parent=public.package_version_snapshot   (교체 때 준 값과 같아야 한다)
--
-- 지운 뒤에는 그 날짜를 되돌릴 수 없다. 반드시 교체 후 서비스 조회를 한 번 확인하고 실행한다.
-- 여러 날짜를 한꺼번에 지우지 않는다. 날짜마다 따로 실행한다.

\set ON_ERROR_STOP on
\timing on

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL search_path = pg_catalog, public;

SELECT set_config('vd455.backup', :'bak', true),
       set_config('vd455.day',    :'day', true),
       set_config('vd455.parent', :'parent', true);

DO $drop_old$
DECLARE
    v_backup  text := current_setting('vd455.backup');
    v_day     date := current_setting('vd455.day')::date;
    v_next    date := (current_setting('vd455.day')::date + 1);
    v_parent  regclass := to_regclass(current_setting('vd455.parent'));
    v_oldname text;
    v_dropped timestamptz;
    v_old     regclass;
    v_serving oid;
    v_newoid  oid;
BEGIN
    EXECUTE format('SELECT old_relation, old_dropped_at, new_oid FROM %I.swap_receipt WHERE snapshot_at = $1', v_backup)
       INTO v_oldname, v_dropped, v_newoid USING v_day;

    IF v_oldname IS NULL THEN
        RAISE EXCEPTION '그 날짜의 교체 기록이 없습니다: %', v_day;
    END IF;
    IF v_dropped IS NOT NULL THEN
        RAISE NOTICE '이미 % 에 지웠습니다. 할 일이 없습니다: %', v_dropped, v_day;
        RETURN;
    END IF;

    -- 지우기 전에 새 파티션이 실제로 서비스 중인지 확인한다.
    -- 이 검사가 없으면 되돌린 상태에서 옛 파티션을 지워 그 날짜를 잃을 수 있다.
    SELECT c.oid INTO v_serving
      FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
     WHERE i.inhparent = v_parent
       AND pg_get_expr(c.relpartbound, c.oid)
           = format('FOR VALUES FROM (%L) TO (%L)', v_day, v_next);

    IF v_serving IS NULL THEN
        RAISE EXCEPTION '그 날짜에 서비스 파티션이 없습니다. 지우지 않습니다: %', v_day;
    END IF;
    IF v_serving <> v_newoid THEN
        RAISE EXCEPTION '서비스 중인 파티션이 새 회차가 아닙니다(되돌린 상태로 보입니다). 지우지 않습니다: %', v_day;
    END IF;

    v_old := to_regclass(format('%I.%I', v_backup, split_part(v_oldname, '.', 2)));
    IF v_old IS NULL THEN
        RAISE EXCEPTION '백업 스키마에서 옛 파티션을 찾지 못했습니다: %', v_oldname;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_inherits WHERE inhrelid = v_old) THEN
        RAISE EXCEPTION '옛 파티션이 아직 어딘가에 붙어 있습니다. 지우지 않습니다: %', v_oldname;
    END IF;

    -- CASCADE 를 쓰지 않는다. 예상 못 한 의존이 있으면 실패하는 편이 낫다.
    EXECUTE format('DROP TABLE %s', v_old::text);
    EXECUTE format('UPDATE %I.swap_receipt SET old_dropped_at = clock_timestamp() WHERE snapshot_at = $1', v_backup)
      USING v_day;

    RAISE NOTICE '% 옛 파티션 % 제거 완료', v_day, v_oldname;
END
$drop_old$;

COMMIT;

-- 지운 뒤 남은 용량. 장부에 적는다.
SELECT (SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid)))
          FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
         WHERE i.inhparent = to_regclass(:'parent')) AS service_total,
       (SELECT count(*) FROM :"bak".swap_receipt WHERE old_dropped_at IS NULL) AS old_still_on_disk;
