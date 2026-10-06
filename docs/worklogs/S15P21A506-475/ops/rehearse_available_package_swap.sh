#!/bin/sh
# S15P21A506-475 — available_package 교체·롤백 스크립트를 스크래치 DB 에서 시험한다 (운영 아님).
#
# 전제: rehearsal475-pg 컨테이너에 "455 적재 후" 상태를 흉내 낸 합성 데이터가 들어 있다.
#   기존 available_package = 기존 10만 · 최신 기준일 package_version_snapshot = 재정렬 10만 ·
#   package_snapshot downloads = 46.9만(1,000 개 중 1 개는 NULL)
#
# 사용 (저장소 루트): sh docs/worklogs/S15P21A506-475/ops/rehearse_available_package_swap.sh
set -u
D=docs/worklogs/S15P21A506-475
E=$D/evidence/phase5/available_swap
mkdir -p "$E"
PG=rehearsal475-pg
EXPECTED=$(cat data/rehearsal475/seed_expected_new.txt)
psqlf() { docker exec -i $PG psql -X -U postgres -d pickage_rehearsal "$@"; }
fp() { psqlf -At -c "SELECT count(*), md5(string_agg(package_id||':'||package_name, ',' ORDER BY package_id)) FROM available_package"; }
run() {  # run <name> <sql file> <vars...>
  NAME=$1; F=$2; shift 2
  psqlf "$@" < "$F" > "$E/$NAME.log" 2>&1; RC=$?
  echo "== $NAME exit=$RC  available=$(fp)" | tee -a "$E/summary.txt"
  grep -E "중단|ERROR|완료|ROLLBACK|new_rows|^ *[0-9-]+ *\|" "$E/$NAME.log" | head -6 | sed 's/^/   /' | tee -a "$E/summary.txt"
}
: > "$E/summary.txt"
BEFORE=$(fp); echo "before=$BEFORE expected_new=$EXPECTED" | tee -a "$E/summary.txt"
S=$D/ops/available_package_swap.sql; R=$D/ops/available_package_rollback.sql
V="-v expect_min=$((EXPECTED-100)) -v expect_max=$((EXPECTED+100)) -v min_keep_pct=60 -v backup_table=available_package_bak_rehearsal"

run T1_verify_only   $S -v verify_only=on  $V
run T2_guard_range   $S -v verify_only=off -v expect_min=1 -v expect_max=1000 -v min_keep_pct=60 -v backup_table=available_package_bak_rehearsal
run T3_guard_keep    $S -v verify_only=off -v expect_min=1 -v expect_max=999999 -v min_keep_pct=99 -v backup_table=available_package_bak_rehearsal
[ "$(fp)" = "$BEFORE" ] && echo "   T1~T3 뒤 변경 없음 확인" | tee -a "$E/summary.txt" || echo "   !! T1~T3 뒤 내용이 바뀌었다" | tee -a "$E/summary.txt"
psqlf -At -c "SELECT 'backup exists after T1~T3: ' || (to_regclass('available_package_bak_rehearsal') IS NOT NULL)" | tee -a "$E/summary.txt"

# T4 실제 교체 + 동시 조회 (검색 API 의 SEARCH_SQL 모양)
Q="SELECT count(*) FROM available_package p JOIN package_snapshot ps ON ps.package_id=p.package_id AND ps.snapshot_at=(SELECT max(snapshot_at) FROM snapshot) WHERE p.package_name LIKE '%websocket%'"
( while [ ! -f "$E/.stop" ]; do S0=$(date +%s%3N); N=$(psqlf -At -c "$Q" 2>&1 | tr -d '\n'); echo "$(date +%s%3N),$(( $(date +%s%3N)-S0 )),$N"; sleep 0.2; done ) > "$E/reads-during-T4.csv" &
RD=$!; rm -f "$E/.stop"; sleep 2
run T4_swap          $S -v verify_only=off $V
sleep 2; touch "$E/.stop"; wait $RD; rm -f "$E/.stop"
AFTER=$(fp); echo "   after_swap=$AFTER" | tee -a "$E/summary.txt"
awk -F, '{print $3}' "$E/reads-during-T4.csv" | sort | uniq -c | sed 's/^/   reads /' | tee -a "$E/summary.txt"

run T5_guard_backup_exists $S -v verify_only=off $V
[ "$(fp)" = "$AFTER" ] && echo "   T5 뒤 변경 없음 확인" | tee -a "$E/summary.txt"

run T6_rollback_verify $R -v verify_only=on  -v backup_table=available_package_bak_rehearsal
run T7_rollback        $R -v verify_only=off -v backup_table=available_package_bak_rehearsal
[ "$(fp)" = "$BEFORE" ] && echo "   롤백 후 내용 지문이 교체 전과 동일" | tee -a "$E/summary.txt" || echo "   !! 롤백 후 내용이 교체 전과 다르다" | tee -a "$E/summary.txt"
