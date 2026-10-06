SELECT Name, Version, Description, Licenses, Links
FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
WHERE System='NPM' AND DATE(SnapshotAt) = DATE '2026-08-31'
