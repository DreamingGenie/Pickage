-- NPMRequirements (T0 · T2). Dependents 대체 원천. dry-run 기대치 17.51 GiB
SELECT SnapshotAt, Name, Version,
       Dependencies, PeerDependencies, OptionalDependencies
FROM `bigquery-public-data.deps_dev_v1.NPMRequirements`
WHERE DATE(SnapshotAt) = DATE '{snap}'{extra}
