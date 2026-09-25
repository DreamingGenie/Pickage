# U2 운영 명령서 (downloads 재적재, S15P21A506-453) — 타워 작성 2026-09-22
실행 트리: C:\git\S15P21A506-453 (2f2ba7e, origin/develop 포함 확인). 주 트리 develop 은 72커밋 뒤라 쓰지 않는다.
입력 3개는 U5(합본) 후 확정: DAILY_ROOT / BRONZE_RUN / BRONZE_SHA.

0. 공통
cd C:\git\S15P21A506-453; $env:DOCKER_HOST='ssh://a506app'; $PY='C:\git\S15P21A506\.venv-bq\Scripts\python.exe'; $DR='C:\git\S15P21A506\data\downloads\bronze_468k\parquet'; $BR='npm-downloads-468k-20260922-v1'; $BS='e4f80714a3c4179454e24bbd7b44d39522bbe341b134e3b337cc3a152e725ee6'; $C=@('--docker-container','pickage-app-postgres-1','--database','pickage','--db-user','pickage')

1. 사전 확인(읽기)
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -X -At -c "SELECT count(*) FROM etl_load_execution WHERE dataset='package-snapshot';" -c "SELECT pg_size_pretty(pg_relation_size('package_snapshot')), pg_size_pretty(pg_indexes_size('package_snapshot'));"
기대: 0 / 24 GB | 14 GB 근처

2. verify-only (2일)
& $PY -m pipeline.package_snapshot.downloads_reload --daily-root $DR --bronze-run-id $BR --bronze-manifest-sha256 $BS --run-id downloads-468k-20260922-v1 --snapshots 2026-08-31 2026-08-24 @C --verify-only
기대: STAGING_READY staging_rows≈46.8만, daily_dates 7 / SNAPSHOT_COMPLETE action VERIFY_ONLY, nonnull_before 97,728(08-31)·97,675(08-24), changed_rows≈36만
멈춤: "recomputed downloads differ ... mismatched=N" → 합본 입력 문제, 타워 보고
기록: data/package_snapshot/downloads_reload/downloads-468k-20260922-v1/plan.json 의 contract_sha256 → Jira -453 코멘트

3. 본실행(105일, 타워 신호 후)
& $PY -m pipeline.package_snapshot.downloads_reload --daily-root $DR --bronze-run-id $BR --bronze-manifest-sha256 $BS --run-id downloads-468k-20260922-v1 --from 2024-09-02 --to 2026-08-31 @C
기대: 날짜당 1~3분, 105일 2~5h. 보고 기준: 날짜당 5분 초과 또는 heap+index +50 MB/일 초과
중단 재개: 같은 명령 + --skip-published

4. 완료 확인
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -X -At -c "SELECT count(*) FILTER (WHERE status='PUBLISHED'), count(*) FROM etl_load_execution WHERE dataset='package-snapshot' AND execution_id='reload-453-downloads-468k-20260922-v1-'||snapshot_at::text;" -c "SELECT snapshot_at, count(downloads) FROM package_snapshot WHERE snapshot_at IN (DATE '2026-08-31', DATE '2026-08-24', DATE '2024-09-02') GROUP BY 1 ORDER BY 1;"
기대: 105 | 105 / 채움 97,728→약 46만, 97,675→약 46만, 41,820→소폭 증가
