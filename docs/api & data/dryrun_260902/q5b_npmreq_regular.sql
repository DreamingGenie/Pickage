SELECT Name, Version, Dependencies
FROM `bigquery-public-data.deps_dev_v1.NPMRequirements`
WHERE DATE(SnapshotAt) = DATE '2026-08-31'
