-- DuckDB UI(pipeline/duckdb/duckdb_ui.py)에서 그대로 실행. 원본 뷰 projects / pkg_project / versions_full 만 사용한다.
-- 0. 대상 패키지. 화면에서 고르는 패키지 목록. 전체를 만들 때는 WHERE ... IN (SELECT name FROM target) 두 줄만 지운다.
CREATE OR REPLACE TABLE target AS SELECT unnest(['express', 'moment', 'axios', 'react', 'vue']) AS name;   -- 여기 이름을 추가하고 01 전체를 다시 실행

-- 1. package_repo_span : 대표 릴리스를 발행 순으로 보며 저장소 이름이 바뀌는 지점마다 구간을 끊는다.
--    대표 릴리스 = 발행 순으로 볼 때 Ordinal 누적 최댓값을 갱신하는 릴리스(수집계획 v2 §5-1, deps.dev "최고 릴리스"와 동일).
--    이 필터가 없으면 vue 처럼 2.x(vuejs/vue)·3.x(vuejs/core) 두 라인을 병행 유지보수하는 패키지가 17번 왔다 갔다 하는 것으로 잡힌다.
CREATE OR REPLACE TABLE package_repo_span AS
WITH ver_repo AS (                       -- 버전 1개 = 저장소 1개 (중복행·복수 저장소는 이름순 첫 번째)
  SELECT v.Name AS name, v.Version AS version, v.published_at, v.ordinal,
         p.ProjectType AS repo_type, p.ProjectName AS repo_name
  FROM versions_full v
  JOIN pkg_project p ON p.Name = v.Name AND p.Version = v.Version AND p.RelationType = 'SOURCE_REPO_TYPE'
  WHERE v.Name IN (SELECT name FROM target) AND v.published_at IS NOT NULL AND v.is_release   -- 프리릴리스 제외
  QUALIFY row_number() OVER (PARTITION BY v.Name, v.Version ORDER BY p.ProjectName) = 1
),
rep AS (                                 -- 대표 릴리스만 남김 (유지보수 라인의 뒤늦은 릴리스는 누적 최댓값을 못 넘어 제외됨)
  SELECT *, max(ordinal) OVER (PARTITION BY name ORDER BY published_at, ordinal
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS run_max
  FROM ver_repo
  QUALIFY run_max IS NULL OR ordinal > run_max
),
ordered AS (
  SELECT *, lag(repo_name) OVER (PARTITION BY name ORDER BY published_at, ordinal) AS prev_repo FROM rep
),
breaks AS (                              -- 앞 대표 릴리스와 저장소가 달라지는 지점만 남김
  SELECT name, repo_type, repo_name, published_at AS valid_from, version AS from_version
  FROM ordered WHERE prev_repo IS NULL OR prev_repo <> repo_name
)
SELECT name, repo_type, repo_name, from_version, valid_from,
       lead(valid_from) OVER (PARTITION BY name ORDER BY valid_from) AS valid_to
FROM breaks;

-- 2. project_snapshot_span : 주간 스냅샷을 [valid_from, valid_to) 구간으로.
--    중복행(2023-11-27·2024-02-12·2024-08-05)은 먼저 제거하고 나서 lead 를 계산해야 한다.
--    (QUALIFY 는 윈도우 계산 뒤에 걸리므로, 같은 문장에서 하면 lead 가 중복행을 가리켜 그 주가 빈 구간이 된다)
CREATE OR REPLACE TABLE project_snapshot_span AS
WITH dedup AS (
  SELECT Type AS repo_type, project_name AS repo_name, snapshot,
         StarsCount AS stars, ForksCount AS forks, OpenIssuesCount AS open_issues
  FROM projects
  WHERE project_name IN (SELECT repo_name FROM package_repo_span)
  QUALIFY row_number() OVER (PARTITION BY snapshot, Type, project_name ORDER BY StarsCount) = 1
)
SELECT repo_type, repo_name, stars, forks, open_issues,
       snapshot AS valid_from,
       lead(snapshot) OVER (PARTITION BY repo_type, repo_name ORDER BY snapshot) AS valid_to
FROM dedup;
