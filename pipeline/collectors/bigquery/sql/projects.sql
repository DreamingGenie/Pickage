-- Projects 전체 (T0 · T1 백필 · T2). dry-run 기대치 0.32 GiB (2026-08-31), 옛 스냅샷은 더 작음
SELECT SnapshotAt, Type, Name AS project_name,
       StarsCount, ForksCount, OpenIssuesCount
FROM `bigquery-public-data.deps_dev_v1.Projects`
WHERE DATE(SnapshotAt) = DATE '{snap}'{extra}
