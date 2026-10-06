-- 날짜 하나의 서비스 파티션을 새 회차 파티션으로 교체한다.
--
-- 데이터를 복사하지 않는다. DETACH/ATTACH/SET SCHEMA 는 전부 카탈로그 변경이다.
-- 옛 파티션은 지우지 않고 백업 스키마로 옮긴다. DROP 은 별도 단계다
-- (partition-swap-drop-old.sql) — 대조가 끝나기 전에는 디스크를 비우지 않는다.
--
-- 실행 전 psql 변수 네 개를 준다.
--   -v sch=vd193_reload_455_20260922   새 회차를 담은 스테이징 스키마
--   -v bak=vd455_backup_20260922       옛 파티션을 옮겨 둘 백업 스키마
--   -v day=2026-08-31                  교체할 기준일
--   -v cmp=full                        값 대조 범위: full | sample | none
--
-- 운영에서는 full 만 쓴다. 리허설에서 실제로 돌려 본 것도 full 뿐이다
-- (782만 행 대조에 3.5초). sample 과 none 은 코드에 있으나 검증하지 않았다.
--   -v parent=public.package_version_snapshot   교체 대상 부모 테이블
--
-- `parent` 를 인자로 받는 이유는 리허설 때문이다. 로컬 공유 DB 의 public 표를 건드리지
-- 않고 스테이징 부모끼리 같은 문장으로 연습할 수 있어야 한다. 운영에서는 반드시
-- public.package_version_snapshot 을 준다. 그 외 이름은 vd193_reload_ / vd455_ 스키마만 받는다.
--
-- 한 날짜가 한 트랜잭션이다. 어느 검사든 실패하면 전체가 ROLLBACK 되고
-- 서비스 테이블은 손대기 전 상태 그대로 남는다.

\set ON_ERROR_STOP on
\timing on

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '600s';
SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL search_path = pg_catalog, public;

-- psql 은 달러 인용 문자열 안을 치환하지 않는다. 그래서 값을 먼저 세션 설정으로 옮긴다.
SELECT set_config('vd455.stage',  :'sch', true),
       set_config('vd455.backup', :'bak', true),
       set_config('vd455.day',    :'day', true),
       set_config('vd455.cmp',    :'cmp', true),
       set_config('vd455.parent', :'parent', true);

DO $swap$
DECLARE
    v_stage      text := current_setting('vd455.stage');
    v_backup     text := current_setting('vd455.backup');
    v_day        date := current_setting('vd455.day')::date;
    v_cmp        text := current_setting('vd455.cmp');
    v_next       date := (current_setting('vd455.day')::date + 1);
    v_childname  text;
    v_new        regclass;
    v_old        regclass;
    v_oldname    text;
    v_parentname text := current_setting('vd455.parent');
    v_parent     regclass;
    v_stparent   regclass;
    v_newparent  oid;
    v_receiptoid oid;
    v_expected   bigint;
    v_actual     bigint;
    v_oldrows    bigint;
    v_oldbytes   bigint;
    v_newbytes   bigint;
    v_common     bigint;
    v_mismatch   bigint;
    v_bound      text;
    v_n          integer;
    v_con        record;
BEGIN
    IF v_stage !~ '^vd193_reload_[a-z0-9_]{1,40}$' THEN
        RAISE EXCEPTION '스테이징 스키마 이름이 규칙에 맞지 않습니다: %', v_stage;
    END IF;
    IF v_backup !~ '^vd455_backup_[a-z0-9_]{1,40}$' THEN
        RAISE EXCEPTION '백업 스키마 이름이 규칙에 맞지 않습니다: %', v_backup;
    END IF;
    IF v_cmp NOT IN ('full', 'sample', 'none') THEN
        RAISE EXCEPTION 'cmp 는 full/sample/none 중 하나여야 합니다: %', v_cmp;
    END IF;
    -- 오타로 엉뚱한 표를 교체하지 않도록 받을 수 있는 이름을 좁힌다.
    IF v_parentname <> 'public.package_version_snapshot'
       AND v_parentname !~ '^(vd193_reload_|vd455_)[a-z0-9_]{1,40}\.package_version_snapshot$' THEN
        RAISE EXCEPTION '교체 대상 부모 이름이 허용 범위 밖입니다: %', v_parentname;
    END IF;
    v_parent := to_regclass(v_parentname);
    IF v_parent IS NULL THEN
        RAISE EXCEPTION '교체 대상 부모가 없습니다: %', v_parentname;
    END IF;
    IF (SELECT relkind FROM pg_class WHERE oid = v_parent) <> 'p' THEN
        RAISE EXCEPTION '교체 대상이 파티션 부모가 아닙니다: %', v_parentname;
    END IF;

    v_childname := 'd' || to_char(v_day, 'YYYYMMDD');
    v_new       := to_regclass(format('%I.%I', v_stage, v_childname));
    v_stparent  := to_regclass(format('%I.package_version_snapshot', v_stage));

    IF v_new IS NULL THEN
        RAISE EXCEPTION '새 파티션이 없습니다: %.%', v_stage, v_childname;
    END IF;
    IF v_stparent IS NULL THEN
        RAISE EXCEPTION '스테이징 부모가 없습니다: %', v_stage;
    END IF;

    ---------------------------------------------------------------- 1. 새 파티션 검사
    -- 붙어 있을 곳은 스테이징 부모뿐이거나, 아무 데도 아니어야 한다.
    -- 한 번 되돌린 뒤 다시 교체하는 경우 복구 스크립트가 새 파티션을 떼어 둔 상태다.
    -- 그때도 다시 붙일 수 있어야 하므로 "떼어져 있음"을 실패로 보지 않는다.
    SELECT i.inhparent INTO v_newparent FROM pg_inherits i WHERE i.inhrelid = v_new;
    IF v_newparent IS NOT NULL AND v_newparent <> v_stparent THEN
        RAISE EXCEPTION '새 파티션이 예상 밖의 부모에 붙어 있습니다: % -> %', v_new, v_newparent::regclass;
    END IF;

    -- date_bound CHECK 가 있어야 ATTACH 가 전수 스캔을 건너뛴다. 이게 없으면
    -- 붙이는 순간 수백만 행을 읽으므로, 빠져 있으면 여기서 멈춘다.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = v_new AND contype = 'c'
                      AND conname = 'date_bound') THEN
        RAISE EXCEPTION '새 파티션에 date_bound CHECK 가 없습니다: %', v_new;
    END IF;

    SELECT count(*) INTO v_n FROM pg_constraint
     WHERE conrelid = v_new AND contype = 'f' AND convalidated;
    IF v_n <> 2 THEN
        RAISE EXCEPTION '새 파티션의 검증된 외래키가 2개가 아닙니다: % 개', v_n;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_index
                    WHERE indrelid = v_new AND indisprimary AND indisvalid) THEN
        RAISE EXCEPTION '새 파티션의 기본키가 없거나 무효합니다: %', v_new;
    END IF;

    -- 서비스 부모의 CHECK 제약(V7 ck_package_version_snapshot_dependents_nonnegative 등)은
    -- ATTACH 전에 자식에도 같은 이름·정의로 있어야 한다. 없으면 PostgreSQL 이
    -- "child table is missing constraint" 로 거부한다 (2026-09-25 운영 첫 교체에서 실제 발생 —
    -- 적재기는 스테이징 부모 기준으로 자식을 만들어 이 CHECK 를 달지 않는다).
    -- 자식만 잠그고 자식만 스캔하므로(7.8M 행 수 초) 부모 잠금 전인 여기서 맞춘다.
    FOR v_con IN
        SELECT p.conname, pg_get_constraintdef(p.oid) AS condef
          FROM pg_constraint p
         WHERE p.conrelid = v_parent AND p.contype = 'c'
           AND NOT EXISTS (SELECT 1 FROM pg_constraint c
                            WHERE c.conrelid = v_new AND c.contype = 'c' AND c.conname = p.conname)
         ORDER BY p.conname
    LOOP
        RAISE NOTICE '부모 CHECK 를 새 파티션에 추가합니다: % %', v_con.conname, v_con.condef;
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s', v_new::text, v_con.conname, v_con.condef);
    END LOOP;
    -- 이름이 같은데 정의가 다르면 ATTACH 가 거부한다. 미리 확인해 분명한 메시지로 멈춘다.
    FOR v_con IN
        SELECT p.conname, pg_get_constraintdef(p.oid) AS condef, pg_get_constraintdef(c.oid) AS childdef
          FROM pg_constraint p JOIN pg_constraint c
            ON c.conrelid = v_new AND c.contype = 'c' AND c.conname = p.conname
         WHERE p.conrelid = v_parent AND p.contype = 'c'
           AND pg_get_constraintdef(p.oid) <> pg_get_constraintdef(c.oid)
    LOOP
        RAISE EXCEPTION '부모와 새 파티션의 CHECK % 정의가 다릅니다: 부모 % / 자식 %',
              v_con.conname, v_con.condef, v_con.childdef;
    END LOOP;

    ---------------------------------------------------------------- 2. 적재 영수증 대조
    EXECUTE format('SELECT rows, child_oid FROM %I.reload_partition WHERE snapshot_at = $1', v_stage)
       INTO v_expected, v_receiptoid USING v_day;
    IF v_expected IS NULL THEN
        RAISE EXCEPTION '적재 영수증이 없습니다: % %', v_stage, v_day;
    END IF;
    -- 영수증이 가리키는 표가 지금 붙이려는 표와 같아야 한다.
    -- 이름이 같아도 지우고 다시 만든 표라면 OID 가 달라져 여기서 걸린다.
    IF v_receiptoid <> v_new::oid THEN
        RAISE EXCEPTION '영수증의 파티션과 실제 파티션이 다릅니다: 영수증 % / 실제 %',
              v_receiptoid, v_new::oid;
    END IF;

    EXECUTE format('SELECT count(*) FROM %s', v_new::text) INTO v_actual;
    IF v_actual <> v_expected THEN
        RAISE EXCEPTION '새 파티션 행 수가 영수증과 다릅니다: 실제 % / 영수증 %',
              v_actual, v_expected;
    END IF;

    ---------------------------------------------------------------- 3. 옛 파티션 찾기
    -- 이름을 가정하지 않는다. 경계값으로 찾는다.
    SELECT c.oid, n.nspname || '.' || c.relname
      INTO v_old, v_oldname
      FROM pg_inherits i
      JOIN pg_class c ON c.oid = i.inhrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE i.inhparent = v_parent
       AND pg_get_expr(c.relpartbound, c.oid)
           = format('FOR VALUES FROM (%L) TO (%L)', v_day, v_next);

    IF v_old IS NULL THEN
        RAISE EXCEPTION '그 날짜의 서비스 파티션을 찾지 못했습니다: %', v_day;
    END IF;
    IF v_old = v_new THEN
        RAISE EXCEPTION '이미 교체된 날짜입니다: %', v_day;
    END IF;

    EXECUTE format('SELECT count(*) FROM %s', v_old::text) INTO v_oldrows;
    v_oldbytes := pg_total_relation_size(v_old);
    v_newbytes := pg_total_relation_size(v_new);

    ---------------------------------------------------------------- 4. 값 대조
    -- 두 회차에 공통으로 있는 (package_id, version) 은 dependents_count 가 같아야 한다.
    -- 선정 목록은 target 만 고르고 source 는 전체 생태계이므로, 대상이 바뀌어도
    -- 살아남은 대상의 count 는 변하지 않는다. 다르면 계산이 달라진 것이다.
    IF v_cmp = 'none' THEN
        v_common := NULL; v_mismatch := NULL;
    ELSE
        EXECUTE format($q$
            SELECT count(*), count(*) FILTER (WHERE o.dependents_count <> n.dependents_count)
              FROM %s o JOIN %s n
                     ON n.package_id = o.package_id AND n.version = o.version
             %s $q$,
            v_old::text, v_new::text,
            CASE WHEN v_cmp = 'sample'
                 THEN 'WHERE (o.package_id %% 20) = 0'
                 ELSE '' END)
           INTO v_common, v_mismatch;

        IF v_common = 0 THEN
            RAISE EXCEPTION '공통 대상이 하나도 없습니다 — 입력이 의심스럽습니다: %', v_day;
        END IF;
        IF v_mismatch <> 0 THEN
            RAISE EXCEPTION '기존 대상의 값이 % 건 다릅니다 (공통 % 건). 교체를 중단합니다.',
                  v_mismatch, v_common;
        END IF;
    END IF;

    ---------------------------------------------------------------- 5. 교체
    -- 여기부터 부모에 ACCESS EXCLUSIVE 가 걸린다. 전부 카탈로그 변경이라 밀리초 단위다.
    IF v_newparent IS NOT NULL THEN
        EXECUTE format('ALTER TABLE %s DETACH PARTITION %s', v_stparent::text, v_new::text);
    END IF;
    EXECUTE format('ALTER TABLE %s DETACH PARTITION %s', v_parent::text, v_old::text);
    EXECUTE format('ALTER TABLE %s SET SCHEMA %I', v_old::text, v_backup);
    EXECUTE format('ALTER TABLE %s ATTACH PARTITION %s FOR VALUES FROM (%L) TO (%L)',
                   v_parent::text, v_new::text, v_day, v_next);

    ---------------------------------------------------------------- 6. 교체 후 검사
    SELECT pg_get_expr(c.relpartbound, c.oid) INTO v_bound
      FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
     WHERE i.inhparent = v_parent AND i.inhrelid = v_new;
    IF v_bound IS DISTINCT FROM format('FOR VALUES FROM (%L) TO (%L)', v_day, v_next) THEN
        RAISE EXCEPTION '새 파티션이 기대한 경계로 붙지 않았습니다: %', v_bound;
    END IF;

    SELECT count(*) INTO v_n
      FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
     WHERE i.inhparent = v_parent
       AND pg_get_expr(c.relpartbound, c.oid)
           = format('FOR VALUES FROM (%L) TO (%L)', v_day, v_next);
    IF v_n <> 1 THEN
        RAISE EXCEPTION '그 날짜의 파티션이 1개가 아닙니다: % 개', v_n;
    END IF;

    -- 기존 인덱스와 외래키가 재사용됐는지 본다. conparentid <> 0 은 부모 제약에
    -- 딸려 붙었다는 뜻이다. 0 이면 ATTACH 가 새로 만든 것이라 계약이 다르다.
    IF NOT EXISTS (SELECT 1 FROM pg_index
                    WHERE indrelid = v_new AND indisprimary AND indisvalid) THEN
        RAISE EXCEPTION '교체 후 기본키가 무효합니다: %', v_new;
    END IF;
    SELECT count(*) INTO v_n FROM pg_constraint
     WHERE conrelid = v_new AND contype = 'f' AND convalidated AND conparentid <> 0;
    IF v_n <> 2 THEN
        RAISE EXCEPTION '교체 후 상속된 외래키가 2개가 아닙니다: % 개', v_n;
    END IF;

    ---------------------------------------------------------------- 7. 영수증
    EXECUTE format($q$
        INSERT INTO %I.swap_receipt
            (snapshot_at, old_relation, old_oid, old_rows, old_bytes,
             new_relation, new_oid, new_rows, new_bytes,
             compared_rows, compare_scope, swapped_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, clock_timestamp())
    $q$, v_backup)
    USING v_day, v_oldname, v_old::oid, v_oldrows, v_oldbytes,
          v_new::text, v_new::oid, v_actual, v_newbytes, v_common, v_cmp;

    RAISE NOTICE '% 교체 완료 — 옛 % 행 / % bytes, 새 % 행 / % bytes, 공통 % 건 전부 일치',
          v_day, v_oldrows, v_oldbytes, v_actual, v_newbytes, v_common;
END
$swap$;

COMMIT;

-- 교체 결과. 이 값을 컨트롤 타워 장부에 적는다.
SELECT snapshot_at,
       old_rows, pg_size_pretty(old_bytes) AS old_size,
       new_rows, pg_size_pretty(new_bytes) AS new_size,
       new_bytes - old_bytes AS delta_bytes,
       round(new_bytes::numeric / NULLIF(new_rows, 0), 1) AS bytes_per_row,
       compared_rows, compare_scope, old_relation
  FROM :"bak".swap_receipt
 WHERE snapshot_at = :'day'::date;
