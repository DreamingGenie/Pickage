"""Read-only impact measurement for the pending GitHub identity decision."""
import json
from pathlib import Path
import sys
import duckdb

root = Path(sys.argv[1]).resolve()
manifest = json.loads((root / 'run_manifest.json').read_bytes())
with duckdb.connect(config={'threads': 2, 'memory_limit': '2GB'}) as con:
    con.execute("SET TimeZone='UTC'")
    con.read_parquet(manifest['input']['files']['projects'], hive_partitioning=False).create_view('projects')
    con.read_parquet([str(root / r['path']) for r in manifest['files'] if r['dataset'] == 'quality/selection'],
                     hive_partitioning=False).create_view('selection')
    aliases = con.execute("""SELECT count(*) FROM (SELECT lower(project_name) FROM projects
        WHERE upper(Type)='GITHUB' GROUP BY lower(project_name) HAVING count(*)>1)""").fetchone()[0]
    conflicts = con.execute("""SELECT count(*) FROM (SELECT lower(project_name) FROM projects
        WHERE upper(Type)='GITHUB' GROUP BY lower(project_name)
        HAVING count(DISTINCT row(StarsCount,OpenIssuesCount))>1)""").fetchone()[0]
    count, repositories, missing_values = con.execute("""SELECT count(*),count(DISTINCT lower(s.project_path)),
        count(*) FILTER(WHERE p.StarsCount IS NULL OR p.OpenIssuesCount IS NULL)
        FROM selection s JOIN projects p ON upper(p.Type)='GITHUB'
        AND lower(s.project_path)=lower(p.project_name) AND p.SnapshotAt=CAST(s.snapshot_timestamp AS TIMESTAMP)
        WHERE s.provider='github.com' AND s.reason='NO_EXACT_OBSERVATION'""").fetchone()
result = {'status': 'PROPOSAL_ONLY_PENDING_USER_DECISION', 'github_case_only_packages': count,
          'github_case_only_repositories': repositories, 'additional_rows_with_null_metric': missing_values,
          'case_folded_duplicate_repositories': aliases, 'case_folded_metric_conflicts': conflicts,
          'source': 'https://docs.github.com/en/rest/repos/repos#get-a-repository',
          'proposal': 'Lowercase GitHub comparison path only; retain selected URL, exact SnapshotAt, and GitLab path.'}
with (root / 'github-case-impact.json').open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
