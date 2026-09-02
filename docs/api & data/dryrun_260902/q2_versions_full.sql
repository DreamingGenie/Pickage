SELECT SnapshotAt, Name, Version, VersionInfo.IsRelease, VersionInfo.Ordinal, UpstreamPublishedAt, Deprecated, Description, Licenses,
 (SELECT URL FROM UNNEST(Links) WHERE Label='SOURCE_REPO' LIMIT 1) AS source_repo
FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
WHERE System='NPM' AND DATE(SnapshotAt) = DATE '2026-08-31'
