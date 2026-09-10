-- 로컬 pickage_267_full_defaulted DB에서 실행한다.
-- 실행 이력은 빠르게 조회할 수 있다. 서비스 행의 전체 COUNT는 데이터 규모에 따라 시간이 걸린다.

-- 1. 완료된 재구성 기준일과 실제 적재 건수
SELECT snapshot_at, status,
       input_metadata->'history_policy'->>'history_kind' AS history_kind,
       (actual_counts->>'package_snapshot')::bigint AS rows,
       execution_id, manifest_sha256
FROM public.etl_load_execution
WHERE dataset = 'package-snapshot'
ORDER BY snapshot_at;

-- 2. 전체 기간 진행 상황: 목표는 재구성 228개 + 기존 관측 기준일 1개
SELECT count(*) FILTER (WHERE status = 'PUBLISHED') AS published_dates,
       count(*) FILTER (WHERE status = 'PREPARING') AS running_dates,
       count(*) FILTER (WHERE status = 'FAILED') AS failed_dates,
       sum((actual_counts->>'package_snapshot')::bigint)
         FILTER (WHERE status = 'PUBLISHED') AS published_rows
FROM public.etl_load_execution
WHERE dataset = 'package-snapshot';

-- 3. 최근 시도와 오류. 같은 날짜의 재실행은 attempt로 구분한다.
SELECT e.snapshot_at, a.status, a.phase, a.actual_counts,
       a.error_message, a.created_at, a.completed_at
FROM public.etl_load_attempt a
JOIN public.etl_load_execution e USING (execution_id)
WHERE e.dataset = 'package-snapshot'
ORDER BY a.created_at DESC
LIMIT 10;

-- 4. 최신 게시 포인터는 기존 2026-08-31을 유지해야 한다.
SELECT dataset, snapshot_at, execution_id
FROM public.etl_dataset_current
WHERE dataset IN ('package-version', 'package-snapshot');

-- 5. 패키지의 기간별 실제 서비스 값. 원하는 패키지 이름으로 바꿔 조회한다.
SELECT p.name, s.snapshot_at, s.downloads, s.stars, s.open_issues
FROM public.package p
JOIN public.package_snapshot s USING (package_id)
WHERE p.name = 'react'
ORDER BY s.snapshot_at;

-- 6. 부분합·NULL 사유·저장소 선택 이력은 아래 quality 파일 경로와 SHA로 찾는다.
SELECT snapshot_at, input_metadata->'interval' AS interval,
       input_metadata->'quality' AS quality_summary,
       run_prefix, input_metadata->'files' AS output_files
FROM public.etl_load_execution
WHERE dataset = 'package-snapshot' AND snapshot_at = DATE '2024-09-02';

-- 7. 전체 적재 완료 후 실제 테이블 날짜별 건수 전수 확인
-- 최종 기대: 229개 기준일 / 646,219,939행.
SELECT snapshot_at, count(*) AS rows
FROM public.package_snapshot
GROUP BY snapshot_at
ORDER BY snapshot_at;
