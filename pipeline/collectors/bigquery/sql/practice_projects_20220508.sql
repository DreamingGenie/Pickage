SELECT SnapshotAt, Type, Name AS project_name,
       StarsCount, ForksCount, OpenIssuesCount
FROM `bigquery-public-data.deps_dev_v1.Projects`
WHERE DATE(SnapshotAt) = DATE '2022-05-08'
-- 연습용: 첫 스냅샷(2022-05-08)의 Projects. 파일 첫 줄에 주석을 두면 bq CLI가 플래그로 오해하므로 끝에 둔다
