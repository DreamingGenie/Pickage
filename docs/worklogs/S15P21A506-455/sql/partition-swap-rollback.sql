-- 교체 한 날짜를 되돌린다. 옛 파티션을 서비스로 되돌리고 새 파티션을 떼어 둔다.
--
--   -v sch=vd193_reload_455_20260922
--   -v bak=vd455_backup_20260922
--   -v day=2026-08-31
--   -v parent=public.package_version_snapshot
--
-- `parent` 는 교체 때 준 값과 같아야 한다. 옛 파티션은 그 부모의 스키마로 되돌린다.
--
-- 쓸 수 있는 조건: 그 날짜의 옛 파티션을 아직 DROP 하지 않았을 것
-- (swap_receipt.old_dropped_at IS NULL). DROP 한 뒤에는 되돌릴 수 없고 재적재해야 한다.
--
-- 데이터를 복사하지 않는다. 교체와 마찬가지로 카탈로그 변경뿐이다.

\set ON_ERROR_STOP on
\timing on

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '300s';
SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL search_path = pg_catalog, public;

SELECT set_config('vd455.stage',  :'sch', true),
       set_config('vd455.backup', :'bak', true),
       set_config('vd455.day',    :'day', true),
       set_config('vd455.parent', :'parent', true);

DO $rollback$
DECLARE
    v_stage    text := current_setting('vd455.stage');
    v_backup   text := current_setting('vd455.backup');
    v_day      date := current_setting('vd455.day')::date;
    v_next     date := (current_setting('vd455.day')::date + 1);
    v_parentname text := current_setting('vd455.parent');
    v_parent   regclass;
    v_new      regclass;
    v_oldsch   text;
    v_oldrel   text;
    v_old      regclass;
    v_oldname  text;
    v_dropped  timestamptz;
    v_rows     bigint;
    v_n        integer;
BEGIN
    IF v_parentname <> 'public.package_version_snapshot'
       AND v_parentname !~ '^(vd193_reload_|vd455_)[a-z0-9_]{1,40}\.package_version_snapshot$' THEN
        RAISE EXCEPTION '부모 이름이 허용 범위 밖입니다: %', v_parentname;
    END IF;
    v_parent := to_regclass(v_parentname);
    IF v_parent IS NULL THEN
        RAISE EXCEPTION '부모가 없습니다: %', v_parentname;
    END IF;

    v_new := to_regclass(format('%I.%I', v_stage, 'd' || to_char(v_day, 'YYYYMMDD')));

    EXECUTE format('SELECT old_relation, old_dropped_at FROM %I.swap_receipt WHERE snapshot_at = $1', v_backup)
       INTO v_oldname, v_dropped USING v_day;

    IF v_oldname IS NULL THEN
        RAISE EXCEPTION '그 날짜의 교체 기록이 없습니다: %', v_day;
    END IF;
    IF v_dropped IS NOT NULL THEN
        RAISE EXCEPTION '옛 파티션을 이미 % 에 DROP 했습니다. 되돌릴 수 없습니다: %', v_dropped, v_day;
    END IF;

    -- 교체 때 백업 스키마로 옮겼으므로 이름은 그대로, 스키마만 바뀌어 있다.
    -- 되돌릴 때는 **원래 있던 스키마**로 보낸다. 부모의 스키마가 아니다.
    -- 2026-09-13 전환에서 부모만 public 으로 옮기고 229개 자식은 원래 스키마에
    -- 남겼으므로, 운영의 옛 파티션은 public 이 아닌 곳에 있을 수 있다.
    -- 부모 스키마로 되돌리면 파티션이 조용히 다른 곳으로 이사한다.
    v_oldsch := split_part(v_oldname, '.', 1);
    v_oldrel := split_part(v_oldname, '.', 2);
    IF v_oldsch = '' OR v_oldrel = '' OR strpos(v_oldname, '.') <> length(v_oldsch) + 1 THEN
        RAISE EXCEPTION '영수증의 옛 파티션 이름을 스키마와 표로 나눌 수 없습니다: %', v_oldname;
    END IF;
    v_old := to_regclass(format('%I.%I', v_backup, v_oldrel));
    IF v_old IS NULL THEN
        RAISE EXCEPTION '백업 스키마에서 옛 파티션을 찾지 못했습니다: %', v_oldname;
    END IF;

    EXECUTE format('SELECT count(*) FROM %s', v_old::text) INTO v_rows;
    IF v_rows = 0 THEN
        RAISE EXCEPTION '옛 파티션이 비어 있습니다. 되돌리면 그 날짜가 빈 값이 됩니다: %', v_day;
    END IF;

    IF v_new IS NOT NULL AND EXISTS (SELECT 1 FROM pg_inherits
                                      WHERE inhrelid = v_new AND inhparent = v_parent) THEN
        EXECUTE format('ALTER TABLE %s DETACH PARTITION %s', v_parent::text, v_new::text);
    END IF;

    EXECUTE format('ALTER TABLE %s SET SCHEMA %I', v_old::text, v_oldsch);
    EXECUTE format('ALTER TABLE %s ATTACH PARTITION %I.%I FOR VALUES FROM (%L) TO (%L)',
                   v_parent::text, v_oldsch, v_oldrel, v_day, v_next);

    SELECT count(*) INTO v_n
      FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
     WHERE i.inhparent = v_parent
       AND pg_get_expr(c.relpartbound, c.oid)
           = format('FOR VALUES FROM (%L) TO (%L)', v_day, v_next);
    IF v_n <> 1 THEN
        RAISE EXCEPTION '되돌린 뒤 그 날짜의 파티션이 1개가 아닙니다: % 개', v_n;
    END IF;

    EXECUTE format('DELETE FROM %I.swap_receipt WHERE snapshot_at = $1', v_backup) USING v_day;

    RAISE NOTICE '% 되돌림 완료 — 옛 파티션 % 행을 서비스로 복귀', v_day, v_rows;
END
$rollback$;

COMMIT;
