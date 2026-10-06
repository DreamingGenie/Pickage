SELECT SnapshotAt, Name, Version, Dependent.Name AS dependent_name, Dependent.Version AS dependent_version
FROM `bigquery-public-data.deps_dev_v1.Dependents`
WHERE System='NPM' AND DATE(SnapshotAt) = DATE '2026-08-31' AND MinimumDepth=1 AND DependentIsHighestReleaseWithResolution
