#!/bin/sh
# S15P21A506-475 1c — app 노드(j15a506) 읽기 전용 조회.
#
# psql 은 postgres 컨테이너 안에서 default_transaction_read_only=on 으로만 돈다.
# 쓰기 SQL(INSERT/UPDATE/DELETE/DDL/VACUUM) 없음. 자격증명은 컨테이너 환경변수로만 쓰고 출력하지 않는다.
#
# 실행:
#   ssh -i ~/Downloads/J15A506T.pem -o BatchMode=yes ubuntu@j15a506.p.ssafy.io 'sh -s' \
#     < docs/worklogs/S15P21A506-475/phase1c-probe-app-node.sh \
#     > docs/worklogs/S15P21A506-475/evidence/phase1/app-node-probe1c.txt 2>&1
set +e
echo "### date"; date -u
echo "### resources"; nproc; free -m; df -h /
echo "### docker ps"; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"
echo "### docker stats"; docker stats --no-stream --format "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"
echo "### repo status"; cd ~/S15P21A506 && git status --short | head -20; git log --oneline -1
echo "### app compose mem lines"; grep -n -E "mem_limit" deploy/prod/app/compose.yaml
echo "### app .env keys"; sed -n "s/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p" deploy/prod/app/.env 2>/dev/null
echo "### timers"; systemctl list-timers --all --no-pager | grep -iE "pickage|similar" ; systemctl list-unit-files --no-pager | grep -iE "pickage|similar"
echo "### similarity-loader logs (tail)"; docker logs --tail 40 "$(docker ps --format '{{.Names}}' | grep similarity-loader | head -1)" 2>&1

PG=$(docker ps --format '{{.Names}}' | grep -E 'postgres' | head -1)
echo "### postgres container: $PG"
docker exec -i "$PG" sh -c 'PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=60000" psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=0 -P pager=off' <<'SQL'
\echo '### read-only check'
SHOW default_transaction_read_only;
\echo '### flyway versions'
SELECT version, description, installed_on FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5;
\echo '### available_package'
SELECT count(*) AS n, min(created_at), max(created_at) FROM available_package;
SELECT date_trunc('hour', created_at) AS batch, count(*) FROM available_package GROUP BY 1 ORDER BY 1;
\echo '### similar_package by model'
SELECT model_ver, count(*) AS rows, count(DISTINCT package_id) AS bases, max(rank) AS max_rank FROM similar_package GROUP BY 1;
\echo '### sizes'
SELECT relname, pg_size_pretty(pg_total_relation_size(c.oid)) FROM pg_class c
 WHERE relname IN ('similar_package','available_package','package','version','package_env') AND relkind IN ('r','p');
\echo '### candidates outside available_package (all ranks / top3)'
SELECT count(*) AS rows_out, count(*) FILTER (WHERE s.rank <= 3) AS top3_out
FROM similar_package s WHERE NOT EXISTS (SELECT 1 FROM available_package a WHERE a.package_id = s.similar_package_id);
\echo '### bases outside available_package'
SELECT count(DISTINCT s.package_id) FROM similar_package s WHERE NOT EXISTS (SELECT 1 FROM available_package a WHERE a.package_id = s.package_id);
\echo '### sample top3 outside'
SELECT b.name AS base, c.name AS cand, s.rank FROM similar_package s
 JOIN package b ON b.package_id = s.package_id JOIN package c ON c.package_id = s.similar_package_id
 WHERE s.rank <= 3 AND NOT EXISTS (SELECT 1 FROM available_package a WHERE a.package_id = s.similar_package_id)
 ORDER BY b.name LIMIT 15;
\echo '### ws / websocket'
SELECT p.name, p.package_id, EXISTS (SELECT 1 FROM available_package a WHERE a.package_id = p.package_id) AS available
FROM package p WHERE p.name IN ('ws','websocket','eiows','websocket13','pusher','socket.io');
\echo '### etl_dataset_current'
SELECT * FROM etl_dataset_current;
SQL
