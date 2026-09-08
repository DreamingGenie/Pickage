-- PackageVersionToProject npm (T0 · T2m). dry-run 기대치 10.37 GiB
SELECT SnapshotAt, Name, Version, ProjectType, ProjectName, RelationType
FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject`
WHERE System = 'NPM' AND DATE(SnapshotAt) = DATE '{snap}'{extra}
