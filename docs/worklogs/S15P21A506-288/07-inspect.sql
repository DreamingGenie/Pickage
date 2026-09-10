-- 로컬 검증 DB pickage_267_full_defaulted에서 실행하는 읽기 전용 조회.
-- 먼저 실행 상태를 확인한 뒤 서비스 수치와 품질 근거를 조회한다.

SELECT e.execution_id, e.status, e.snapshot_at, e.manifest_sha256,
       e.actual_counts, a.attempt_id, a.status AS attempt_status,
       a.quality_report->>'verification_scope' AS verification_scope
FROM etl_load_execution e
JOIN etl_load_attempt a ON a.attempt_id = e.active_attempt_id
WHERE e.dataset = 'package-snapshot'
ORDER BY e.created_at;

SELECT snapshot_at, count(*) AS packages,
       count(downloads) AS downloads_available,
       count(*) FILTER (WHERE downloads = 0) AS downloads_zero,
       count(stars) AS stars_available,
       count(open_issues) AS issues_available,
       sum(downloads) AS downloads_sum
FROM package_snapshot
WHERE snapshot_at = DATE '2026-08-31'
GROUP BY snapshot_at;

SELECT p.package_id, p.name, s.snapshot_at, s.downloads, s.stars, s.open_issues
FROM package_snapshot s
JOIN package p USING (package_id)
WHERE s.snapshot_at = DATE '2026-08-31'
  AND p.name IN ('react', 'typescript')
ORDER BY p.name;

-- 부분합 여부와 상세 NULL 사유는 quality Parquet에 보존된다.
-- 아래 DB 이력에서 요약, 입력 해시와 상세 파일 key/sha256을 찾는다.
SELECT e.execution_id,
       e.input_metadata->'quality' AS quality_summary,
       e.input_metadata#>>'{input_manifest,downloads,manifest_sha256}' AS downloads_manifest_sha256,
       e.input_metadata#>>'{input_manifest,repository_metrics,manifest_sha256}' AS repository_manifest_sha256,
       e.input_metadata->'files' AS curated_files
FROM etl_load_execution e
WHERE e.dataset = 'package-snapshot' AND e.status = 'PUBLISHED'
ORDER BY e.created_at;

SELECT dataset, execution_id, snapshot_at, manifest_sha256, published_at
FROM etl_dataset_current
WHERE dataset IN ('package-version', 'package-snapshot')
ORDER BY dataset;
