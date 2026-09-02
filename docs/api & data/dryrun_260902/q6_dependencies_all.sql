SELECT Name, Version, Dependency.Name, Dependency.Version, MinimumDepth
FROM `bigquery-public-data.deps_dev_v1.Dependencies`
WHERE System='NPM' AND DATE(SnapshotAt) = DATE '2026-08-31' AND MinimumDepth=1
