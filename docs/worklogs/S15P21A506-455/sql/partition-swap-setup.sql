-- 교체를 시작하기 전에 한 번만 실행한다. 백업 스키마와 교체 영수증 표를 만든다.
--
--   -v bak=vd455_backup_20260922
--   -v parent=public.package_version_snapshot
--
-- 이 스크립트는 서비스 테이블을 건드리지 않는다. 새 스키마와 빈 표 하나를 만들 뿐이다.

\set ON_ERROR_STOP on

BEGIN;

SET LOCAL lock_timeout = '10s';

CREATE SCHEMA IF NOT EXISTS :"bak";
REVOKE ALL ON SCHEMA :"bak" FROM PUBLIC;

CREATE TABLE IF NOT EXISTS :"bak".swap_receipt (
    snapshot_at    date PRIMARY KEY,
    old_relation   text   NOT NULL,
    old_oid        oid    NOT NULL,
    old_rows       bigint NOT NULL CHECK (old_rows >= 0),
    old_bytes      bigint NOT NULL CHECK (old_bytes >= 0),
    new_relation   text   NOT NULL,
    new_oid        oid    NOT NULL,
    new_rows       bigint NOT NULL CHECK (new_rows >= 0),
    new_bytes      bigint NOT NULL CHECK (new_bytes >= 0),
    compared_rows  bigint,
    compare_scope  text   NOT NULL CHECK (compare_scope IN ('full','sample','none')),
    swapped_at     timestamptz NOT NULL,
    old_dropped_at timestamptz
);

COMMENT ON TABLE :"bak".swap_receipt IS
  'S15P21A506-455 날짜별 파티션 교체 기록. old_dropped_at 이 NULL 이면 옛 파티션이 아직 남아 디스크를 쓰고 있다.';

COMMIT;

-- 시작 전 상태. 이 값을 명령서의 "교체 전" 칸에 적는다.
SELECT count(*) AS partitions,
       pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS total_size,
       min(substring(pg_get_expr(c.relpartbound, c.oid) from '\d{4}-\d{2}-\d{2}')) AS first_day,
       max(substring(pg_get_expr(c.relpartbound, c.oid) from '\d{4}-\d{2}-\d{2}')) AS last_day
  FROM pg_inherits i
  JOIN pg_class c ON c.oid = i.inhrelid
 WHERE i.inhparent = to_regclass(:'parent');
