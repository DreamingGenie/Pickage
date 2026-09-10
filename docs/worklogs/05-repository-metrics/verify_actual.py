"""Independent DuckDB reconciliation for the measured 05 run."""
import json
from pathlib import Path
import sys
import time

import duckdb
from pipeline.repository_metrics.build import verify_completed

directory = Path(sys.argv[1]).resolve()
started = time.monotonic()
manifest, _ = verify_completed(directory)
github_fold = manifest.get("policy", {}).get("project_path_comparison", {}).get("github.com") == "lowercase"
checks = {}
with duckdb.connect(config={"threads": 2, "memory_limit": "2GB", "preserve_insertion_order": False}) as con:
    con.execute("SET TimeZone='UTC'")
    scratch = directory / "independent-verify-temp"
    scratch.mkdir(exist_ok=True)
    con.execute("SET temp_directory = ?", [str(scratch)])
    for dataset in manifest["report"]["output_counts"]:
        files = [str(directory / record["path"]) for record in manifest["files"] if record["dataset"] == dataset]
        con.read_parquet(files, hive_partitioning=False).create_view(dataset.replace("/", "_"))
    for table in ("package", "projects"):
        con.read_parquet(manifest["input"]["files"][table], hive_partitioning=False).create_view("input_" + table)
    counts = con.execute("""SELECT count(*),count(DISTINCT package_id),
        count(*) FILTER(WHERE snapshot_at != DATE '2026-08-31' OR package_id IS NULL OR snapshot_at IS NULL),
        count(*) FILTER(WHERE stars<0 OR open_issues<0),
        count(*) FILTER(WHERE stars IS NULL),count(*) FILTER(WHERE open_issues IS NULL),
        count(*) FILTER(WHERE stars=0),count(*) FILTER(WHERE open_issues=0)
        FROM metric_data""").fetchone()
    checks["metrics"] = dict(zip(("rows", "distinct_package_ids", "invalid_identity", "negative_values",
                                  "null_stars", "null_open_issues", "zero_stars", "zero_open_issues"), counts))
    assert counts[0] == counts[1] == manifest["input"]["counts"]["package"]
    assert counts[2] == counts[3] == 0
    missing = con.execute("SELECT count(*) FROM (SELECT package_id FROM metric_data EXCEPT SELECT package_id FROM input_package)").fetchone()[0]
    checks["unknown_package_ids"] = missing
    assert missing == 0
    candidate_rows, selected = con.execute("SELECT count(*),count(*) FILTER(WHERE selected) FROM quality_candidates").fetchone()
    assert candidate_rows == manifest["input"]["counts"]["version"]
    assert selected == manifest["report"]["mapping"]["selected"]
    checks["candidates"] = {"rows": candidate_rows, "selected": selected}
    assert manifest["report"]["output_counts"]["quality/selection"] == counts[0]
    mismatches = con.execute("""SELECT count(*) FROM input_package p FULL OUTER JOIN quality_selection s USING(package_id)
        WHERE p.package_id IS NULL OR s.package_id IS NULL OR p.repo_url IS DISTINCT FROM s.repo_url""").fetchone()[0]
    checks["repository_selection_mismatches"] = mismatches
    assert mismatches == 0
    project_key = "CASE WHEN provider='github.com' THEN lower(project_name) ELSE project_name END" if github_fold else "project_name"
    con.execute(f"""CREATE TEMP TABLE expected_observation AS
        WITH mapped AS (SELECT *,CASE upper(Type) WHEN 'GITHUB' THEN 'github.com'
        WHEN 'GITLAB' THEN 'gitlab.com' END AS provider FROM input_projects),
        keyed AS (SELECT *, {project_key} AS project_path FROM mapped),
        grouped AS (SELECT provider,project_path,SnapshotAt,min(project_name) AS source_project_path,count(*) AS source_rows,
        count(DISTINCT row(StarsCount,OpenIssuesCount)) AS pairs,
        bool_or(coalesce(StarsCount<0 OR StarsCount>2147483647 OR OpenIssuesCount<0 OR OpenIssuesCount>2147483647,false)) AS invalid,
        min(StarsCount) AS stars_raw,min(OpenIssuesCount) AS issues_raw
        FROM keyed WHERE provider IS NOT NULL AND length(trim(project_name))>0 GROUP BY ALL)
        SELECT *, CASE WHEN pairs>1 OR invalid THEN NULL ELSE stars_raw END AS stars,
        CASE WHEN pairs>1 OR invalid THEN NULL ELSE issues_raw END AS open_issues FROM grouped""")
    mismatches = con.execute("""SELECT count(*) FROM expected_observation e FULL OUTER JOIN quality_project_observations o
        ON e.provider=o.provider AND e.project_path=o.project_path AND e.SnapshotAt=o.SnapshotAt
        WHERE e.provider IS NULL OR o.provider IS NULL OR e.stars IS DISTINCT FROM o.stars
        OR e.open_issues IS DISTINCT FROM o.open_issues OR e.source_rows IS DISTINCT FROM o.source_rows
        OR e.pairs IS DISTINCT FROM o.distinct_metric_pairs OR e.invalid::INTEGER IS DISTINCT FROM o.invalid""").fetchone()[0]
    checks["source_observation_mismatches"] = mismatches
    assert mismatches == 0
    selection_key = "CASE WHEN s.provider='github.com' THEN lower(s.project_path) ELSE s.project_path END" if github_fold else "s.project_path"
    extra = f" OR s.comparison_project_path IS DISTINCT FROM ({selection_key}) OR s.observed_project_path IS DISTINCT FROM e.source_project_path" if github_fold else ""
    mismatches = con.execute(f"""SELECT count(*) FROM metric_data m JOIN quality_selection s USING(package_id)
        LEFT JOIN expected_observation e ON s.provider=e.provider AND ({selection_key})=e.project_path
        AND e.SnapshotAt=CAST(? AS TIMESTAMP)
        WHERE m.stars IS DISTINCT FROM e.stars OR m.open_issues IS DISTINCT FROM e.open_issues
        OR s.observed_timestamp IS DISTINCT FROM e.SnapshotAt {extra}""", [manifest["snapshot_timestamp"]]).fetchone()[0]
    checks["package_metric_or_observed_time_mismatches"] = mismatches
    assert mismatches == 0
    mapped = con.execute("SELECT coalesce(sum(source_rows),0) FROM quality_project_observations").fetchone()[0]
    unmapped = con.execute("SELECT count(*) FROM quality_unmapped_projects").fetchone()[0]
    checks["project_rows"] = {"mapped_source_rows": mapped, "unmapped_source_rows": unmapped}
    assert mapped + unmapped == manifest["input"]["counts"]["projects"]
    checks["unmapped_providers"] = [{"type": row[0], "rows": row[1]} for row in con.execute(
        "SELECT Type,count(*) FROM quality_unmapped_projects GROUP BY Type ORDER BY Type").fetchall()]
    sample = con.execute("""SELECT p.name,m.package_id,s.version,s.repo_url,m.stars,m.open_issues,s.reason,s.observed_timestamp
        FROM input_package p JOIN metric_data m USING(package_id) JOIN quality_selection s USING(package_id)
        WHERE p.name IN ('react','express','lodash','vue','typescript','@angular/core','@gitlab/ui','vite') ORDER BY p.name""")
    columns = [field[0] for field in sample.description]
    checks["sample"] = [dict(zip(columns, row)) for row in sample.fetchall()]
checks["elapsed_seconds"] = round(time.monotonic() - started, 3)
checks["status"] = "PASSED"
with (directory / "independent-verification.json").open("x", encoding="utf-8") as stream:
    json.dump(checks, stream, default=str, ensure_ascii=False, indent=2)
print(json.dumps(checks, default=str, ensure_ascii=False, indent=2))
