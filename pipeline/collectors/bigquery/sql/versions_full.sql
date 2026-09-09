-- PackageVersions 전체 열 (T0 · T2m). dry-run 기대치 24.44 GiB (2026-08-31)
SELECT
  SnapshotAt, Name, Version,
  VersionInfo.IsRelease AS is_release,
  VersionInfo.Ordinal   AS ordinal,
  UpstreamPublishedAt   AS published_at,
  Deprecated,
  DependencyError       AS dependency_error,
  Description, Licenses,
  (SELECT URL FROM UNNEST(Links) WHERE Label = 'SOURCE_REPO' LIMIT 1) AS source_repo
FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
WHERE System = 'NPM' AND DATE(SnapshotAt) = DATE '{snap}'{extra}
