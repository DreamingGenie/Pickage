SELECT Name, Version, VersionInfo.IsRelease, VersionInfo.Ordinal, UpstreamPublishedAt, Deprecated IS NOT NULL AS dep
FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
WHERE System='NPM' AND DATE(SnapshotAt) = DATE '2026-08-31'
