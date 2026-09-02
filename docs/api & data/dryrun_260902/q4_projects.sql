SELECT Type, Name, StarsCount, OpenIssuesCount, ForksCount
FROM `bigquery-public-data.deps_dev_v1.Projects`
WHERE DATE(SnapshotAt) = DATE '2026-08-31'
