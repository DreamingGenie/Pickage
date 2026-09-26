-- S15P21A506-475 — available_package 를 "보고서 가능 패키지" 로 교체한다.
--
-- 보고서 가능 = 최신 기준일(snapshot 표의 max)에
--   ① package_version_snapshot 행이 있고 (의존 수 추이·버전 점유율)
--   ② package_snapshot 의 downloads 가 NULL 이 아닌 (다운로드 추이·검색 정렬)
-- 패키지. 운영 available_package(97,743, 09-22 수동 입력)가 ①과 같은 규모임을 확인했다.
--
-- 한 트랜잭션: 계산 → 가드 → 백업 → 교체 → 보고. 가드 하나라도 걸리면 ROLLBACK 되어 아무것도 안 바뀐다.
-- 교체 중 읽기는 막지 않는다(SHARE ROW EXCLUSIVE 는 SELECT 의 ACCESS SHARE 와 충돌하지 않는다).
--
-- psql 변수 (전부 필수):
--   verify_only  on|off   on 이면 끝에서 ROLLBACK (백업 표도 남지 않는다)
--   expect_min   정수     새 목록 행 수 하한
--   expect_max   정수     새 목록 행 수 상한
--   min_keep_pct 정수     기존 목록 중 새 목록에 남아야 하는 최소 비율(%)
--   backup_table 이름     백업 표 이름 (예: available_package_bak_20260926). 이미 있으면 중단
--
-- 실행 예 (운영에서는 run_available_package_swap.sh 가 부른다):
--   psql -v verify_only=on -v expect_min=85000 -v expect_max=100000 -v min_keep_pct=60 \
--        -v backup_table=available_package_bak_20260926 -f available_package_swap.sql

\set ON_ERROR_STOP on
\timing on

BEGIN;
SET LOCAL lock_timeout = '5s';          -- 다른 적재기가 잡고 있으면 기다리지 말고 실패
SET LOCAL statement_timeout = '15min';

CREATE TEMP TABLE _latest ON COMMIT DROP AS SELECT max(snapshot_at) AS at FROM snapshot;
-- 기준일은 리터럴로 넣는다. 임시 표와 조인하면 계획 시점 프루닝이 안 돼
-- package_version_snapshot 229개 파티션(약 10.9억 행)을 전부 읽는다 (2026-09-26 운영 verify 에서 확인).
SELECT at AS latest_at FROM _latest \gset

-- ① 최신 기준일 파티션만 본다 (파티션 프루닝 + (package_id, snapshot_at) 인덱스)
CREATE TEMP TABLE _pvs ON COMMIT DROP AS
SELECT DISTINCT pvs.package_id
  FROM package_version_snapshot pvs
 WHERE pvs.snapshot_at = :'latest_at';

-- ② ①의 id 로만 PK 조회 (package_snapshot 전수 스캔을 피한다)
CREATE TEMP TABLE _new ON COMMIT DROP AS
SELECT v.package_id, p."name" AS package_name
  FROM _pvs v
  JOIN package_snapshot ps ON ps.package_id = v.package_id AND ps.snapshot_at = :'latest_at' AND ps.downloads IS NOT NULL
  JOIN package p ON p.package_id = v.package_id;
ALTER TABLE _new ADD PRIMARY KEY (package_id);

CREATE TEMP TABLE _report ON COMMIT DROP AS
SELECT (SELECT at FROM _latest)                                            AS latest_snapshot,
       (SELECT count(*) FROM available_package)                            AS old_rows,
       (SELECT count(*) FROM _pvs)                                         AS with_version_snapshot,
       (SELECT count(*) FROM _new)                                         AS new_rows,
       (SELECT count(*) FROM _pvs WHERE package_id NOT IN (SELECT package_id FROM _new)) AS dropped_no_downloads,
       (SELECT count(*) FROM available_package a JOIN _new n USING (package_id)) AS kept,
       (SELECT count(*) FROM available_package a WHERE NOT EXISTS (SELECT 1 FROM _new n WHERE n.package_id = a.package_id)) AS removed,
       (SELECT count(*) FROM _new n WHERE NOT EXISTS (SELECT 1 FROM available_package a WHERE a.package_id = n.package_id)) AS added;

\echo '### 계산 결과'
SELECT * FROM _report;

-- 가드 — 걸리면 예외. ON_ERROR_STOP 이라 트랜잭션 전체가 취소되고 psql 이 오류 코드로 끝난다.
-- (psql 변수는 $$ 안에서 치환되지 않으므로 임시 표로 넘긴다)
CREATE TEMP TABLE _params ON COMMIT DROP AS
SELECT :expect_min::int AS expect_min, :expect_max::int AS expect_max,
       :min_keep_pct::numeric AS min_keep_pct, :'backup_table'::text AS backup_table;

DO $$
DECLARE r record; p record;
BEGIN
  SELECT * INTO r FROM _report;
  SELECT * INTO p FROM _params;
  IF r.new_rows NOT BETWEEN p.expect_min AND p.expect_max THEN
    RAISE EXCEPTION '중단: 새 목록 % 행이 기대 범위 [%, %] 밖이다', r.new_rows, p.expect_min, p.expect_max;
  END IF;
  IF r.old_rows > 0 AND 100.0 * r.kept / r.old_rows < p.min_keep_pct THEN
    RAISE EXCEPTION '중단: 기존 목록 유지 비율 % %% 가 하한 % %% 보다 낮다',
      round(100.0 * r.kept / r.old_rows, 2), p.min_keep_pct;
  END IF;
  IF to_regclass(p.backup_table) IS NOT NULL THEN
    RAISE EXCEPTION '중단: 백업 표 % 가 이미 있다 — 다른 이름을 줄 것', p.backup_table;
  END IF;
END $$;

-- 백업 (롤백용). verify_only 면 트랜잭션과 함께 사라진다
CREATE TABLE :"backup_table" AS SELECT * FROM available_package;

LOCK TABLE available_package IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM available_package;
INSERT INTO available_package (package_id, package_name) SELECT package_id, package_name FROM _new;

\echo '### 교체 후'
SELECT count(*) AS available_rows,
       (SELECT count(*) FROM :"backup_table") AS backup_rows
  FROM available_package;

\if :verify_only
  \echo '검증 전용 — ROLLBACK'
  ROLLBACK;
\else
  COMMIT;
  \echo '교체 완료 — COMMIT'
\endif
