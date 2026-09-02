SELECT Name, Version, ProjectType, ProjectName, RelationType
FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject`
WHERE System='NPM' AND DATE(SnapshotAt) = DATE '2026-08-31'
