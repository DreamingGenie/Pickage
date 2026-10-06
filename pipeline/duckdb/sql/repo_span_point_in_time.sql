-- 01_span_build.sql 을 먼저 실행한 뒤 사용.

-- (1) 월 1일 격자 × 패키지 : 그 시점 유효한 저장소 → 직전 주간 스냅샷 값
WITH grid AS (
  SELECT unnest(generate_series(DATE '2022-06-01', DATE '2026-09-01', INTERVAL 1 MONTH))::date AS as_of
)
SELECT t.name, g.as_of, s.repo_name,
       ps.valid_from AS projects_snapshot_at, ps.stars, ps.open_issues
FROM target t
CROSS JOIN grid g
LEFT JOIN package_repo_span s
       ON s.name = t.name
      AND g.as_of >= s.valid_from::date
      AND (s.valid_to IS NULL OR g.as_of < s.valid_to::date)
LEFT JOIN project_snapshot_span ps
       ON ps.repo_type = s.repo_type AND ps.repo_name = s.repo_name
      AND g.as_of >= ps.valid_from
      AND (ps.valid_to IS NULL OR g.as_of < ps.valid_to)
ORDER BY t.name, g.as_of;

-- (1b) 같은 결과를 span 테이블 없이 projects 뷰에 직접 ASOF JOIN 하는 형태 (임시 조회용)
WITH grid AS (
  SELECT unnest(generate_series(DATE '2022-06-01', DATE '2026-09-01', INTERVAL 1 MONTH))::date AS as_of
)
SELECT t.name, g.as_of, s.repo_name, p.snapshot AS projects_snapshot_at, p.StarsCount, p.OpenIssuesCount
FROM target t
CROSS JOIN grid g
LEFT JOIN package_repo_span s
       ON s.name = t.name AND g.as_of >= s.valid_from::date AND (s.valid_to IS NULL OR g.as_of < s.valid_to::date)
ASOF LEFT JOIN projects p
       ON p.Type = s.repo_type AND p.project_name = s.repo_name AND p.snapshot <= g.as_of
ORDER BY t.name, g.as_of;

-- (2) 버전별 : 버전 발행일 기준 "그 버전이 나올 때의 저장소 상태" (Projects 는 2022-05-08 이후만 값이 있음)
--     projects 뷰(1.2억 행)에 직접 ASOF 하면 느리다. 01에서 만든 project_snapshot_span 에 구간 조인한다.
SELECT v.Name AS name, v.Version AS version, v.published_at, r.ProjectName AS repo_name,
       ps.valid_from AS projects_snapshot_at, ps.stars, ps.open_issues
FROM versions_full v
JOIN (SELECT DISTINCT Name, Version, ProjectType, ProjectName
      FROM pkg_project
      WHERE RelationType = 'SOURCE_REPO_TYPE' AND Name IN (SELECT name FROM target)) r   -- 필터를 안쪽에 둬야 빠르다
  ON r.Name = v.Name AND r.Version = v.Version
LEFT JOIN project_snapshot_span ps
  ON ps.repo_type = r.ProjectType AND ps.repo_name = r.ProjectName
 AND v.published_at::date >= ps.valid_from
 AND (ps.valid_to IS NULL OR v.published_at::date < ps.valid_to)
WHERE v.Name IN (SELECT name FROM target) AND v.is_release AND v.published_at IS NOT NULL
ORDER BY v.Name, v.published_at;

-- (3) 별칭 판정 : 같은 패키지에서 나온 저장소 이름 쌍의 같은 스냅샷 스타 수가 얼마나 일치하나
SELECT a.name, a.repo_name AS repo_a, b.repo_name AS repo_b,
       count(*) AS n_snapshots,
       round(100.0 * avg(abs(pa.stars - pb.stars) / greatest(pa.stars, pb.stars, 1)), 3) AS avg_pct_diff
FROM (SELECT DISTINCT name, repo_type, repo_name FROM package_repo_span) a
JOIN (SELECT DISTINCT name, repo_type, repo_name FROM package_repo_span) b
  ON a.name = b.name AND a.repo_name < b.repo_name
JOIN project_snapshot_span pa ON pa.repo_type = a.repo_type AND pa.repo_name = a.repo_name
JOIN project_snapshot_span pb ON pb.repo_type = b.repo_type AND pb.repo_name = b.repo_name AND pb.valid_from = pa.valid_from
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
