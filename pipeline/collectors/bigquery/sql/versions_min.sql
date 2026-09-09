-- PackageVersions 최소 열 (T2 주간). dry-run 기대치 5.24 GiB
SELECT
  SnapshotAt, Name, Version,
  VersionInfo.IsRelease AS is_release,
  VersionInfo.Ordinal   AS ordinal,
  UpstreamPublishedAt   AS published_at,
  Deprecated,
  DependencyError       AS dependency_error
FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
WHERE System = 'NPM' AND DATE(SnapshotAt) = DATE '{snap}'{extra}
