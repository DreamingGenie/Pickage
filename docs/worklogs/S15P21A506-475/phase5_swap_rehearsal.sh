#!/bin/sh
# S15P21A506-475 5단계 — 스크래치 DB 에서 similar_package 교체 중 동시 조회 리허설.
#
# 적재(load.py)를 돌리는 동안 서비스 API 와 같은 SIMILAR_SQL 을 0.2초 간격으로 던져
# 각 조회의 지연(ms)과 결과 model/행 수를 기록한다. 운영 DB 는 건드리지 않는다.
#
# 사용 (저장소 루트):
#   sh docs/worklogs/S15P21A506-475/phase5_swap_rehearsal.sh <run_id> <execution_id>
set -eu
RUN=$1; EXEC=$2
E=docs/worklogs/S15P21A506-475/evidence/phase5
PG=rehearsal475-pg
Q="SELECT count(*) FROM similar_package s JOIN package b ON b.package_id = s.package_id JOIN package c ON c.package_id = s.similar_package_id WHERE b.name = 'ws'"

( while [ ! -f "$E/.stop" ]; do
    S=$(date +%s%3N)
    N=$(docker exec $PG psql -X -At -U postgres -d pickage_rehearsal -c "$Q" 2>&1 | tr -d '\n')
    echo "$(date +%s%3N),$(( $(date +%s%3N) - S )),$N"
    sleep 0.2
  done ) > "$E/reads-during-$RUN.csv" &
READER=$!
rm -f "$E/.stop"
sleep 2
S=$(date +%s)
PYTHONIOENCODING=utf-8 python -m pipeline.similar_package.load --run-dir "data/rehearsal475/runs/$RUN/out/result" \
  --execution-id "$EXEC" --work-dir data/rehearsal475/loader-work --docker-container $PG \
  --database pickage_rehearsal --db-user postgres --allow-gate-skip > "$E/load-$RUN.txt" 2>&1 && RC=0 || RC=$?
echo "exit=$RC sec=$(( $(date +%s) - S ))" >> "$E/load-$RUN.txt"
sleep 2
touch "$E/.stop"; wait $READER; rm -f "$E/.stop"
docker exec $PG psql -X -At -U postgres -d pickage_rehearsal \
  -c "SELECT count(*), count(DISTINCT package_id), md5(string_agg(package_id||':'||similar_package_id||':'||rank||':'||score, ',' ORDER BY package_id, rank)) FROM similar_package" \
  -c "SELECT count(*) FROM similar_package s WHERE NOT EXISTS (SELECT 1 FROM available_package a WHERE a.package_id = s.similar_package_id)" \
  -c "SELECT execution_id FROM etl_dataset_current WHERE dataset = 'similar-package'" > "$E/state-after-$RUN.txt"
tail -3 "$E/load-$RUN.txt"; cat "$E/state-after-$RUN.txt"
awk -F, '{print $2}' "$E/reads-during-$RUN.csv" | sort -n | awk '{a[NR]=$1} END {print "reads", NR, "p50", a[int(NR*0.5)], "p99", a[int(NR*0.99)], "max", a[NR]}'
awk -F, '{print $3}' "$E/reads-during-$RUN.csv" | sort | uniq -c
