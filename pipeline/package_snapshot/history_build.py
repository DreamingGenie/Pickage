"""Prepare and build publication-date-based historical package snapshots."""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
from pathlib import Path
import duckdb
from pipeline.downloads_interval.aggregate import reject, require_schema, MAX_BIGINT
from .quality import (COMMON_SCHEMA, HISTORY_FIELDS, QUALITY_SCHEMA_ID,
                      history_quality_projection, require_schema as require_quality_schema)


def _paths(values, label):
    if not values:
        raise ValueError(label + " is empty")
    result = [Path(v).resolve() for v in values]
    if any(not p.is_file() for p in result):
        raise ValueError(label + " contains a missing file")
    return result


def _sql_path(path):
    return "'" + str(Path(path).resolve()).replace("'", "''") + "'"


def _sql_paths(paths):
    return "[" + ",".join(_sql_path(p) for p in paths) + "]"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_state(prepared: dict, state_dir: Path, *, memory="8GB", threads=4) -> dict:
    """Materialise reusable known-publication and repository-candidate state."""
    package = _paths(prepared.get("package_files"), "package_files")
    candidates = _paths(prepared.get("candidate_files"), "candidate_files")
    if not isinstance(prepared.get("input_sha256"), str) or len(prepared["input_sha256"]) != 64:
        raise ValueError("prepared input SHA is required")
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    output = state_dir / "asof_versions.parquet"
    population_output = state_dir / "population_history.parquet"
    timeline_output = state_dir / "repository_timeline.parquet"
    with duckdb.connect() as con:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET memory_limit=?", [memory])
        con.execute("SET threads=?", [threads])
        con.execute("SET temp_directory=?", [str(state_dir / "tmp")])
        con.execute(f"CREATE OR REPLACE TEMP VIEW packages AS SELECT package_id,name FROM read_parquet({_sql_paths(package)})")
        con.execute(f"CREATE OR REPLACE TEMP VIEW candidates AS SELECT * FROM read_parquet({_sql_paths(candidates)})")
        columns = {row[0]: row[1].upper() for row in con.execute("DESCRIBE candidates").fetchall()}
        required = {"package_id", "version", "published_at", "ordinal", "repo_url", "eligible"}
        if not required.issubset(columns):
            raise ValueError("candidate schema is missing required columns")
        source_rows = con.execute("SELECT count(*) FROM candidates WHERE package_id IS NOT NULL").fetchone()[0]
        con.execute(f"""COPY (SELECT c.package_id,p.name,c.version,c.published_at,c.ordinal,c.repo_url,c.eligible
            FROM candidates c JOIN packages p USING(package_id)
            WHERE c.package_id IS NOT NULL) TO {_sql_path(output)} (FORMAT PARQUET)""")
        rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(output)]).fetchone()[0]
        if rows != source_rows:
            raise ValueError("candidate rows do not all reference approved packages")
        con.execute(f"""COPY (SELECT package_id,name,min(published_at) AS first_published_at
            FROM read_parquet({_sql_path(output)}) WHERE published_at IS NOT NULL
            GROUP BY package_id,name) TO {_sql_path(population_output)} (FORMAT PARQUET)""")
        con.execute(f"""COPY (
            WITH ranked AS (
                SELECT package_id,version,published_at,ordinal,repo_url,
                    row_number() OVER (
                        PARTITION BY package_id
                        ORDER BY ordinal DESC,published_at DESC,version ASC
                    ) AS preference_rank
                FROM read_parquet({_sql_path(output)})
                WHERE eligible AND published_at IS NOT NULL AND repo_url IS NOT NULL
            ), events AS (
                SELECT package_id,published_at,min(preference_rank) AS event_rank
                FROM ranked
                GROUP BY package_id,published_at
            ), running AS (
                SELECT package_id,published_at,event_rank,
                    min(event_rank) OVER (
                        PARTITION BY package_id
                        ORDER BY published_at
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS selected_rank
                FROM events
            ), changes AS (
                SELECT package_id,published_at AS selected_from,selected_rank,
                    lead(published_at) OVER (
                        PARTITION BY package_id ORDER BY published_at
                    ) AS selected_until
                FROM running
                WHERE event_rank=selected_rank
            )
            SELECT c.package_id,r.version,r.published_at,r.ordinal,r.repo_url,
                c.selected_from,c.selected_until
            FROM changes c
            JOIN ranked r ON r.package_id=c.package_id AND r.preference_rank=c.selected_rank
        ) TO {_sql_path(timeline_output)} (FORMAT PARQUET)""")
        known = con.execute("SELECT count(DISTINCT package_id) FROM read_parquet(?) WHERE published_at IS NOT NULL", [str(output)]).fetchone()[0]
        unknown = con.execute("""SELECT count(DISTINCT package_id) FROM read_parquet(?)
            WHERE package_id NOT IN (SELECT DISTINCT package_id FROM read_parquet(?) WHERE published_at IS NOT NULL)""",
            [str(output), str(output)]).fetchone()[0]
    return {"files": {"asof_versions": str(output), "population": str(population_output),
                       "repository_timeline": str(timeline_output)}, "input_sha256": prepared["input_sha256"],
            "counts": {"candidate_rows": rows, "known_publication_packages": known,
                       "unknown_publication_packages": unknown}}


def _interval_values(interval):
    snapshot = interval.get("snapshot_at")
    if not isinstance(snapshot, str):
        raise ValueError("interval snapshot_at is required")
    date.fromisoformat(snapshot)
    previous = interval.get("previous_snapshot_at")
    if previous is not None:
        date.fromisoformat(previous)
        if previous >= snapshot:
            raise ValueError("invalid historical interval")
    return snapshot, previous


def build_snapshot(prepared: dict, state: dict, interval: dict, output_dir: Path, *, memory="8GB", threads=4) -> dict:
    """Build one historical S using as-of version and exact Projects observations."""
    snapshot, previous = _interval_values(interval)
    if state.get("input_sha256") != prepared.get("input_sha256"):
        raise ValueError("state belongs to a different input")
    package = _paths(prepared.get("package_files"), "package_files")
    candidate_state = _paths([state["files"]["repository_timeline"]], "state")
    population_state = _paths([state["files"]["population"]], "state")
    projects = _paths(prepared.get("project_files", {}).get(snapshot), "project_files")
    available_start = date.fromisoformat(prepared.get("available_start", snapshot))
    available_end = date.fromisoformat(prepared.get("available_end", snapshot))
    if available_start > available_end:
        raise ValueError("invalid available daily range")
    output_dir = Path(output_dir).resolve()
    # Only called when the driver has no saved manifest; a failed build can retry.
    output_dir.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET memory_limit=?", [memory])
        con.execute("SET threads=?", [threads])
        con.execute("SET temp_directory=?", [str(output_dir / "tmp")])
        con.execute(f"CREATE OR REPLACE TEMP VIEW packages AS SELECT package_id,name FROM read_parquet({_sql_paths(package)})")
        con.execute(f"CREATE OR REPLACE TEMP VIEW population AS SELECT * FROM read_parquet({_sql_paths(population_state)}) WHERE first_published_at<=TIMESTAMPTZ '{interval['snapshot_timestamp']}'")
        target_path = _paths([prepared.get("target_file")], "target_file")[0]
        status_path = _paths([prepared.get("status_file")], "status_file")[0]
        con.execute(f"CREATE OR REPLACE TEMP TABLE targets AS SELECT DISTINCT name FROM read_csv({_sql_path(target_path)}, header=true, all_varchar=true)")
        con.execute(f"CREATE OR REPLACE TEMP TABLE statuses AS SELECT name,status FROM read_parquet({_sql_path(status_path)}, hive_partitioning=false)")
        if con.execute("SELECT EXISTS (SELECT 1 FROM targets WHERE name IS NULL OR name='')").fetchone()[0]:
            raise ValueError("invalid target name")
        if con.execute("SELECT EXISTS (SELECT name FROM statuses GROUP BY name HAVING count(*)>1)").fetchone()[0]:
            raise ValueError("duplicate status name")
        if con.execute("SELECT EXISTS (SELECT 1 FROM statuses WHERE status NOT IN ('READY','NOT_FOUND') OR status IS NULL)").fetchone()[0]:
            raise ValueError("invalid status")
        reject(con, "SELECT name FROM targets ANTI JOIN statuses USING(name)", "target/status name sets differ")
        reject(con, "SELECT name FROM statuses ANTI JOIN targets USING(name)", "target/status name sets differ")
        daily_selects = []
        for day, paths in prepared.get('daily_files', {}).items():
            if previous is None or not previous <= day < snapshot:
                continue
            if not available_start <= date.fromisoformat(day) <= available_end:
                raise ValueError('daily date outside available range')
            for path in _paths(paths, 'daily_files'):
                con.execute(f'CREATE OR REPLACE TEMP VIEW one_daily AS SELECT * FROM read_parquet({_sql_path(path)},hive_partitioning=false)')
                columns = require_schema(con, 'one_daily', {'name': 'VARCHAR', 'downloads': 'BIGINT', 'imputed_gap': 'BOOLEAN'})
                if 'date' in columns:
                    require_schema(con, 'one_daily', {'date': 'DATE'})
                    reject(con, f"SELECT 1 FROM one_daily WHERE date IS NULL OR date<>DATE '{day}'", 'physical daily date differs from partition date')
                daily_selects.append(f"SELECT name,downloads,imputed_gap,DATE '{day}' date FROM read_parquet({_sql_path(path)},hive_partitioning=false)")
        if daily_selects:
            con.execute('CREATE TEMP TABLE daily AS ' + ' UNION ALL '.join(daily_selects))
        else:
            con.execute('CREATE TEMP TABLE daily(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN,date DATE)')
        reject(con, "SELECT 1 FROM daily WHERE name IS NULL OR name='' OR imputed_gap IS NULL OR downloads<0", 'invalid daily name, value, or imputed_gap')
        reject(con, 'SELECT name,date FROM daily GROUP BY name,date HAVING count(*)>1', 'duplicate daily (name,date)')
        reject(con, "SELECT d.name FROM daily d LEFT JOIN statuses s USING(name) WHERE s.name IS NULL OR s.status<>'READY'", 'daily name has no READY status')
        con.execute('''CREATE TEMP TABLE daily_aggregate AS SELECT name,count(*)::INTEGER observed_days,
            count(*) FILTER(WHERE downloads IS NOT NULL AND NOT imputed_gap)::INTEGER valid_days,
            count(*) FILTER(WHERE downloads IS NULL)::INTEGER null_days,
            count(*) FILTER(WHERE imputed_gap)::INTEGER gap_days,
            sum(downloads::DECIMAL(38,0)) FILTER(WHERE downloads IS NOT NULL AND NOT imputed_gap) total
            FROM daily GROUP BY name''')
        reject(con, f'SELECT name FROM daily_aggregate WHERE total>{MAX_BIGINT}', 'BIGINT sum overflow')
        con.execute('''CREATE TEMP VIEW downloads AS SELECT p.package_id,p.name,t.name IS NOT NULL targeted,st.status,
            coalesce(d.observed_days,0)::INTEGER observed_days,coalesce(d.valid_days,0)::INTEGER valid_days,
            coalesce(d.null_days,0)::INTEGER null_days,coalesce(d.gap_days,0)::INTEGER gap_days,d.total::BIGINT download_sum
            FROM population p LEFT JOIN targets t USING(name) LEFT JOIN statuses st USING(name)
            LEFT JOIN daily_aggregate d USING(name)''')
        con.execute(f"""CREATE OR REPLACE TEMP TABLE selected AS
            SELECT v.*
            FROM read_parquet({_sql_paths(candidate_state)}) v
            JOIN population p USING(package_id)
            WHERE v.selected_from<=TIMESTAMPTZ '{interval['snapshot_timestamp']}'
              AND (v.selected_until IS NULL OR v.selected_until>TIMESTAMPTZ '{interval['snapshot_timestamp']}')""")
        project_timestamp = str(interval["snapshot_timestamp"]).replace("Z", "+00:00").replace("'", "''")
        con.execute(f"CREATE OR REPLACE TEMP VIEW project_source AS SELECT * FROM read_parquet({_sql_paths(projects)},hive_partitioning=false)")
        if con.execute(f"SELECT EXISTS (SELECT 1 FROM project_source WHERE SnapshotAt IS NULL OR CAST(SnapshotAt AS TIMESTAMPTZ)<>TIMESTAMPTZ '{project_timestamp}')").fetchone()[0]:
            raise ValueError("Projects input contains a wrong SnapshotAt")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE projects AS
            SELECT *,CASE WHEN upper(Type)='GITHUB' THEN 'github.com' WHEN upper(Type)='GITLAB' THEN 'gitlab.com' END provider,
              CASE WHEN upper(Type)='GITHUB' THEN lower(project_name) WHEN upper(Type)='GITLAB' THEN project_name END project_path
            FROM read_parquet({_sql_paths(projects)},hive_partitioning=false)
            WHERE CAST(SnapshotAt AS TIMESTAMPTZ)=TIMESTAMPTZ '{project_timestamp}'""")
        con.execute("""CREATE OR REPLACE TEMP TABLE metrics AS
            SELECT s.package_id,
              CASE WHEN count(DISTINCT (pr.StarsCount,pr.OpenIssuesCount))=1
                    AND min(pr.StarsCount) BETWEEN 0 AND 2147483647
                    AND NOT coalesce(bool_or(pr.OpenIssuesCount<0 OR pr.OpenIssuesCount>2147483647),false)
                   THEN min(pr.StarsCount)::INTEGER END stars,
              CASE WHEN count(DISTINCT (pr.StarsCount,pr.OpenIssuesCount))=1
                    AND min(pr.OpenIssuesCount) BETWEEN 0 AND 2147483647
                    AND NOT coalesce(bool_or(pr.StarsCount<0 OR pr.StarsCount>2147483647),false)
                   THEN min(pr.OpenIssuesCount)::INTEGER END open_issues,
              min(CAST(pr.SnapshotAt AS TIMESTAMPTZ)) observed_timestamp,
              count(DISTINCT (pr.StarsCount,pr.OpenIssuesCount)) pairs,
              bool_or(pr.StarsCount<0 OR pr.OpenIssuesCount<0 OR pr.StarsCount>2147483647 OR pr.OpenIssuesCount>2147483647) invalid_metric
            FROM selected s LEFT JOIN projects pr ON pr.provider=regexp_extract(s.repo_url,'https://([^/]+)/',1)
              AND pr.project_path=CASE WHEN lower(regexp_extract(s.repo_url,'https://([^/]+)/',1))='github.com' THEN lower(regexp_extract(s.repo_url,'https://[^/]+/(.+)',1)) ELSE regexp_extract(s.repo_url,'https://[^/]+/(.+)',1) END
            GROUP BY s.package_id""")
        expected_days = None if previous is None else (date.fromisoformat(snapshot)-date.fromisoformat(previous)).days
        if 'interval_days' in interval and interval['interval_days'] != expected_days:
            raise ValueError('interval_days disagrees with boundaries')
        overlap = 0 if previous is None else max(0, (
            min(date.fromisoformat(snapshot), available_end + timedelta(days=1)) -
            max(date.fromisoformat(previous), available_start)).days)
        quality_reasons = """list_filter([
            CASE WHEN d.targeted IS NOT TRUE THEN 'OUTSIDE_TARGET_LIST' END,
            CASE WHEN d.status='NOT_FOUND' THEN 'NOT_FOUND' END,
            CASE WHEN {outside} THEN 'OUTSIDE_AVAILABLE_RANGE' END,
            CASE WHEN d.targeted AND d.valid_days<{expected} THEN 'MISSING_DAILY_VALUES' END,
            CASE WHEN d.targeted AND d.observed_days<{overlap} THEN 'ROW_MISSING' END,
            CASE WHEN d.null_days>0 THEN 'NULL_VALUE' END,
            CASE WHEN d.gap_days>0 THEN 'IMPUTED_GAP' END], x -> x IS NOT NULL)""".format(
            outside=str(previous is not None and overlap < expected_days).lower(),
            expected=expected_days or 0, overlap=overlap)
        if previous is None:
            quality_reasons = "['NO_PREVIOUS_SNAPSHOT']"
        con.execute(f"""CREATE OR REPLACE TEMP TABLE quality_raw AS SELECT p.package_id,DATE '{snapshot}' snapshot_at,p.first_published_at,
            s.published_at selected_published_at,d.download_sum,m.stars,m.open_issues,
            CASE WHEN {str(previous is None).lower()} THEN 'UNAVAILABLE' WHEN d.valid_days=0 THEN 'UNAVAILABLE' WHEN d.valid_days={expected_days or 0} THEN 'COMPLETE' ELSE 'PARTIAL' END data_status,
            {expected_days if expected_days is not None else 'NULL'}::INTEGER expected_days,d.observed_days,d.valid_days,
            CASE WHEN {str(previous is None).lower()} THEN 'NO_PREVIOUS_SNAPSHOT' WHEN d.valid_days>0 THEN NULL WHEN d.targeted IS NOT TRUE THEN 'OUTSIDE_TARGET_LIST'
                 WHEN d.status='NOT_FOUND' THEN 'NOT_FOUND' WHEN {overlap}=0 THEN 'OUTSIDE_AVAILABLE_RANGE'
                 WHEN d.valid_days=0 THEN 'MISSING_DAILY_VALUES' END null_reason,
            {quality_reasons} quality_reasons,
            CASE WHEN s.repo_url IS NULL THEN 'NO_VALID_REPOSITORY' WHEN m.pairs>1 THEN 'PROJECT_METRIC_CONFLICT' WHEN m.invalid_metric THEN 'INVALID_METRIC_VALUE' WHEN m.observed_timestamp IS NULL THEN 'NO_EXACT_OBSERVATION' ELSE 'SELECTED' END repository_reason,
            s.repo_url,s.version selected_version,m.observed_timestamp
            FROM population p LEFT JOIN selected s ON s.package_id=p.package_id
            JOIN downloads d ON d.package_id=p.package_id AND d.name=p.name
            LEFT JOIN metrics m ON m.package_id=p.package_id""")
        con.execute("CREATE TEMP VIEW package_identity AS SELECT package_id,name FROM population")
        history_quality_projection(con, interval)
        require_quality_schema(con, "quality", COMMON_SCHEMA + HISTORY_FIELDS)
        quality_rows = con.execute("SELECT count(*),count(DISTINCT package_id) FROM quality").fetchone()
        population_rows = con.execute("SELECT count(*) FROM population").fetchone()[0]
        if quality_rows[0] != population_rows or quality_rows[1] != quality_rows[0]:
            raise ValueError("quality population or key uniqueness check failed")
        con.execute(f"COPY (SELECT package_id,snapshot_at,download_sum downloads,stars,open_issues FROM quality ORDER BY package_id) TO {_sql_path(output_dir/'package_snapshot.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT package_id,name FROM population ORDER BY package_id) TO {_sql_path(output_dir/'package_identity.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT * FROM quality ORDER BY package_id) TO {_sql_path(output_dir/'quality.parquet')} (FORMAT PARQUET)")
        rows = quality_rows[0]
        summary = dict(con.execute("SELECT data_status,count(*) FROM quality GROUP BY 1").fetchall())
    files = {role: str(output_dir / (role + ".parquet")) for role in ("package_snapshot", "package_identity", "quality")}
    return {"files": files, "rows": rows, "quality_schema": QUALITY_SCHEMA_ID,
            "quality": {"status": "PASSED", "status_counts": summary,
            "reconstruction": "PUBLICATION_DATE_AS_OF", "input_sha256": prepared["input_sha256"]},
            "validation": {"rows": rows, "sha256": {role: _sha(path) for role, path in files.items()}}}
