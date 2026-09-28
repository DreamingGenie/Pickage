#!/bin/sh
# S15P21A506-475 1d — 보고서 탭별 데이터 보유 패키지 수 (app 노드, 읽기 전용).
#
# D2 "분석 보고서를 줄 수 있는 패키지만 연다" 의 기준을 정하기 위한 조회.
# 최신 스냅샷(파티션 하나)만 본다. 쿼리마다 statement_timeout 60초. 쓰기 SQL 없음.
#
# 실행:
#   ssh -i ~/Downloads/J15A506T.pem -o BatchMode=yes ubuntu@j15a506.p.ssafy.io 'sh -s' \
#     < docs/worklogs/S15P21A506-475/phase1d-probe-report-coverage.sh \
#     > docs/worklogs/S15P21A506-475/evidence/phase1/app-node-probe1d.txt 2>&1
set +e
docker exec -i pickage-app-postgres-1 sh -c 'PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=60000" psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=0 -P pager=off' <<'SQL'
\timing on
SHOW default_transaction_read_only;
\echo '### snapshot calendar'
SELECT count(*) AS dates, min(snapshot_at), max(snapshot_at) FROM snapshot;

\echo '### package_snapshot: 최신 시점에 downloads 있는 패키지'
SELECT count(*) FROM package_snapshot
 WHERE snapshot_at = (SELECT max(snapshot_at) FROM snapshot) AND downloads IS NOT NULL;
\echo '### package_snapshot: 시점 수 분포 (downloads 있는 행)'
SELECT n_dates, count(*) AS packages FROM (
  SELECT package_id, count(*) AS n_dates FROM package_snapshot WHERE downloads IS NOT NULL GROUP BY 1) t
 GROUP BY 1 ORDER BY 1 DESC LIMIT 12;

\echo '### package_version_snapshot: 최신 시점에 행 있는 패키지'
SELECT count(DISTINCT package_id) FROM package_version_snapshot
 WHERE snapshot_at = (SELECT max(snapshot_at) FROM snapshot);

\echo '### package_env: 패키지 수'
SELECT count(DISTINCT package_id) FROM package_env;

\echo '### dependent_transition / migration_pair: 패키지 수'
SELECT count(DISTINCT package_id) FROM dependent_transition;
SELECT count(DISTINCT from_package_id) FROM migration_pair;

\echo '### 교집합 (D=downloads 최신, V=version snapshot 최신, E=env, A=available)'
WITH s AS (SELECT max(snapshot_at) AS at FROM snapshot),
d AS (SELECT package_id FROM package_snapshot, s WHERE snapshot_at = s.at AND downloads IS NOT NULL),
v AS (SELECT DISTINCT package_id FROM package_version_snapshot, s WHERE snapshot_at = s.at),
e AS (SELECT DISTINCT package_id FROM package_env),
a AS (SELECT package_id FROM available_package)
SELECT
  (SELECT count(*) FROM d JOIN v USING (package_id))                           AS d_and_v,
  (SELECT count(*) FROM d JOIN v USING (package_id) JOIN e USING (package_id)) AS d_v_e,
  (SELECT count(*) FROM a JOIN d USING (package_id))                           AS a_in_d,
  (SELECT count(*) FROM a JOIN v USING (package_id))                           AS a_in_v,
  (SELECT count(*) FROM a JOIN e USING (package_id))                           AS a_in_e,
  (SELECT count(*) FROM d JOIN v USING (package_id) WHERE package_id NOT IN (SELECT package_id FROM a)) AS dv_not_a;
SQL
