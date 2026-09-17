"""Aggregate verified daily values over the approved snapshot population."""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
from pathlib import Path
import re

import duckdb

MAX_BIGINT = 9223372036854775807
HASH_COLUMNS = ("input_manifest_sha256", "policy_sha256", "aggregation_policy_sha256")
DATE_PART = re.compile(r"(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)")


def quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def iso_date(value, label) -> date:
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"{label} must be an ISO date")
    return date.fromisoformat(value)


def paths(value, label, *, empty=False) -> list[str]:
    if not isinstance(value, list) or (not empty and not value):
        raise ValueError(f"{label} must be a path list")
    if any(not isinstance(p, str) or not Path(p).is_file() for p in value):
        raise ValueError(f"{label} contains a missing file")
    return value


def require_schema(con, relation, required):
    columns = {r[0]: r[1] for r in con.execute(f"DESCRIBE {relation}").fetchall()}
    for name, kind in required.items():
        if columns.get(name) != kind:
            raise ValueError(f"{relation} schema: {name} must be {kind}")
    return columns


def reject(con, query, message):
    if con.execute(f"SELECT EXISTS ({query})").fetchone()[0]:
        raise ValueError(message)


def aggregate(prepared: dict, output_dir: Path, *, memory_limit="2GB", threads=4) -> dict:
    package_files = paths(prepared.get("package_files"), "package_files")
    daily_files = paths(prepared.get("daily_files"), "daily_files", empty=True)
    target = paths([prepared.get("target_file")], "target_file")[0]
    status = paths([prepared.get("status_file")], "status_file")[0]
    interval = prepared["interval"]
    end = iso_date(interval["snapshot_at"], "snapshot_at")
    start = interval.get("previous_snapshot_at")
    start = None if start is None else iso_date(start, "previous_snapshot_at")
    expected = None if start is None else (end - start).days
    if expected is not None and expected <= 0:
        raise ValueError("snapshot interval must be positive")
    if "interval_days" in interval and interval["interval_days"] != expected:
        raise ValueError("interval_days disagrees with boundaries")
    available_start = iso_date(prepared["available_start"], "available_start")
    available_end = iso_date(prepared["available_end"], "available_end")
    if available_start > available_end:
        raise ValueError("available_start must not exceed available_end")
    if start is None and daily_files:
        raise ValueError("first snapshot cannot consume daily files")
    lineage = prepared["lineage"]
    for key in HASH_COLUMNS:
        if not isinstance(lineage.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", lineage[key]):
            raise ValueError(f"lineage {key} must be SHA-256 hex")
    if type(threads) is not int or not 1 <= threads <= 16:
        raise ValueError("threads must be between 1 and 16")
    if not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", memory_limit):
        raise ValueError("invalid memory limit")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(f"SET memory_limit={quote(memory_limit)}")
        con.execute(f"SET threads={threads}")
        con.execute(f"SET temp_directory={quote(output_dir / 'tmp')}")
        # Aggregate the small daily input first; the full population needs no GROUP BY.
        for path in package_files:
            con.execute(f"CREATE OR REPLACE TEMP VIEW one_package AS SELECT * FROM read_parquet({quote(path)}, hive_partitioning=false)")
            require_schema(con, "one_package", {"package_id": "INTEGER", "name": "VARCHAR", "repo_url": "VARCHAR"})
        con.execute(f"CREATE TEMP VIEW packages AS SELECT package_id,name FROM read_parquet([{','.join(map(quote, package_files))}], hive_partitioning=false)")
        reject(con, "SELECT 1 FROM packages WHERE package_id IS NULL OR package_id<=0 OR name IS NULL OR name=''", "invalid package identity")
        reject(con, "SELECT name FROM packages GROUP BY name HAVING count(*)>1", "duplicate package name")
        reject(con, "SELECT package_id FROM packages GROUP BY package_id HAVING count(*)>1", "duplicate package ID")
        package_rows = con.execute("SELECT count(*) FROM packages").fetchone()[0]
        if prepared.get("expected_package_rows", package_rows) != package_rows:
            raise ValueError("approved package row count mismatch")
        con.execute(f"CREATE TEMP VIEW target_raw AS SELECT * FROM read_csv({quote(target)}, header=true, all_varchar=true)")
        require_schema(con, "target_raw", {"name": "VARCHAR"})
        reject(con, "SELECT 1 FROM target_raw WHERE name IS NULL OR name=''", "invalid target name")
        duplicate_targets = con.execute("SELECT count(*)-count(DISTINCT name) FROM target_raw").fetchone()[0]
        con.execute("CREATE TEMP TABLE targets AS SELECT DISTINCT name FROM target_raw")
        con.execute(f"CREATE TEMP TABLE statuses AS SELECT * FROM read_parquet({quote(status)}, hive_partitioning=false)")
        require_schema(con, "statuses", {"name": "VARCHAR", "status": "VARCHAR"})
        reject(con, "SELECT 1 FROM statuses WHERE name IS NULL OR name='' OR status IS NULL OR status NOT IN ('READY','NOT_FOUND')", "invalid status row")
        reject(con, "SELECT name FROM statuses GROUP BY name HAVING count(*)>1", "duplicate status name")
        reject(con, "SELECT name FROM targets ANTI JOIN statuses USING(name)", "target/status name sets differ")
        reject(con, "SELECT name FROM statuses ANTI JOIN targets USING(name)", "target/status name sets differ")

        daily_selects = []
        for path in daily_files:
            match = DATE_PART.search(Path(path).as_posix())
            if not match:
                raise ValueError(f"daily file lacks Hive date: {path}")
            day = iso_date(match.group(1), "daily partition date")
            if not start <= day < end:
                raise ValueError("daily date outside [P,S)")
            if not available_start <= day <= available_end:
                raise ValueError("daily date outside available range")
            con.execute(f"CREATE OR REPLACE TEMP VIEW one_daily AS SELECT * FROM read_parquet({quote(path)}, hive_partitioning=false)")
            columns = require_schema(con, "one_daily", {"name": "VARCHAR", "downloads": "BIGINT", "imputed_gap": "BOOLEAN"})
            if "date" in columns:
                require_schema(con, "one_daily", {"date": "DATE"})
                reject(con, f"SELECT 1 FROM one_daily WHERE date IS NULL OR date<>DATE '{day}'", "physical daily date differs from Hive date")
            daily_selects.append(f"SELECT name,downloads,imputed_gap,DATE '{day}' AS date FROM read_parquet({quote(path)}, hive_partitioning=false)")
        if daily_selects:
            con.execute("CREATE TEMP TABLE daily AS " + " UNION ALL ".join(daily_selects))
        else:
            con.execute("CREATE TEMP TABLE daily(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN,date DATE)")
        reject(con, "SELECT 1 FROM daily WHERE name IS NULL OR name='' OR imputed_gap IS NULL OR downloads<0", "invalid daily name, negative value, or NULL imputed_gap")
        reject(con, "SELECT name,date FROM daily GROUP BY name,date HAVING count(*)>1", "duplicate daily (name,date)")
        reject(con, "SELECT d.name FROM daily d LEFT JOIN statuses s USING(name) WHERE s.name IS NULL OR s.status<>'READY'", "daily name has no READY status (unknown or NOT_FOUND)")
        con.execute("""CREATE TEMP TABLE daily_aggregate AS
            SELECT name,count(*)::INTEGER AS observed_days,
                   count(*) FILTER(WHERE downloads IS NOT NULL AND NOT imputed_gap)::INTEGER AS valid_days,
                   count(*) FILTER(WHERE downloads IS NULL)::INTEGER AS null_days,
                   count(*) FILTER(WHERE imputed_gap)::INTEGER AS gap_days,
                   sum(downloads::DECIMAL(38,0)) FILTER(WHERE downloads IS NOT NULL AND NOT imputed_gap) AS total
            FROM daily GROUP BY name""")
        reject(con, f"SELECT name FROM daily_aggregate WHERE total>{MAX_BIGINT}", "BIGINT sum overflow")
        hashes = ",".join(f"{quote(lineage[key])} AS {key}" for key in HASH_COLUMNS)
        if start is None:
            con.execute(f"""CREATE TEMP VIEW results AS SELECT package_id,DATE '{end}' AS snapshot_at,
                NULL::DATE AS previous_snapshot_at,NULL::BIGINT AS download_sum,NULL::INTEGER AS expected_days,
                0::INTEGER AS observed_days,0::INTEGER AS valid_days,'UNAVAILABLE' AS data_status,
                'NO_PREVIOUS_SNAPSHOT' AS null_reason,['NO_PREVIOUS_SNAPSHOT'] AS quality_reasons,{hashes} FROM packages""")
        else:
            overlap = max(0, (min(end, available_end + timedelta(days=1)) - max(start, available_start)).days)
            outside_range = overlap < expected
            con.execute(f"""CREATE TEMP VIEW results AS WITH covered AS (
                SELECT p.package_id,t.name IS NOT NULL AS targeted,s.status,
                       coalesce(d.observed_days,0)::INTEGER AS observed_days,
                       coalesce(d.valid_days,0)::INTEGER AS valid_days,
                       coalesce(d.null_days,0) AS null_days,coalesce(d.gap_days,0) AS gap_days,d.total
                FROM packages p LEFT JOIN targets t USING(name)
                LEFT JOIN statuses s USING(name) LEFT JOIN daily_aggregate d USING(name))
                SELECT package_id,DATE '{end}' AS snapshot_at,DATE '{start}' AS previous_snapshot_at,
                       total::BIGINT AS download_sum,{expected}::INTEGER AS expected_days,observed_days,valid_days,
                       CASE WHEN valid_days=0 THEN 'UNAVAILABLE' WHEN valid_days={expected} THEN 'COMPLETE' ELSE 'PARTIAL' END AS data_status,
                       CASE WHEN valid_days>0 THEN NULL WHEN NOT targeted THEN 'OUTSIDE_TARGET_LIST'
                            WHEN status='NOT_FOUND' THEN 'NOT_FOUND' WHEN {overlap}=0 THEN 'OUTSIDE_AVAILABLE_RANGE'
                            ELSE 'MISSING_DAILY_VALUES' END AS null_reason,
                       list_filter([
                           CASE WHEN NOT targeted THEN 'OUTSIDE_TARGET_LIST' END,
                           CASE WHEN status='NOT_FOUND' THEN 'NOT_FOUND' END,
                           CASE WHEN {str(outside_range).lower()} THEN 'OUTSIDE_AVAILABLE_RANGE' END,
                           CASE WHEN targeted AND valid_days<{expected} THEN 'MISSING_DAILY_VALUES' END,
                           CASE WHEN targeted AND observed_days<{overlap} THEN 'ROW_MISSING' END,
                           CASE WHEN null_days>0 THEN 'NULL_VALUE' END,
                           CASE WHEN gap_days>0 THEN 'IMPUTED_GAP' END], x -> x IS NOT NULL) AS quality_reasons,
                       {hashes} FROM covered""")
        reject(con, "SELECT 1 FROM results WHERE valid_days>observed_days OR observed_days>expected_days OR (download_sum IS NULL)<>(valid_days=0)", "invalid interval coverage or sum")

        interval_path = output_dir / "interval_downloads.parquet"
        con.execute("COPY (SELECT * FROM results ORDER BY package_id) TO ? (FORMAT PARQUET)", [str(interval_path)])
        quality_path = output_dir / "daily_quality.parquet"
        if start is None:
            con.execute("CREATE TEMP VIEW daily_quality AS SELECT NULL::INTEGER AS package_id,NULL::VARCHAR AS name,NULL::DATE AS date,NULL::VARCHAR AS reason WHERE false")
        else:
            # Only targeted names need a per-date expansion, including unmatched targets.
            con.execute(f"""CREATE TEMP VIEW daily_quality AS WITH days AS (
                SELECT gs::DATE AS date FROM generate_series(DATE '{start}',DATE '{end-timedelta(days=1)}',INTERVAL 1 DAY) g(gs)),
                names AS (SELECT p.package_id,t.name FROM targets t LEFT JOIN packages p USING(name)),
                reasons AS (SELECT n.package_id,n.name,days.date,list_filter([
                    CASE WHEN days.date<DATE '{available_start}' OR days.date>DATE '{available_end}' THEN 'OUTSIDE_AVAILABLE_RANGE' END,
                    CASE WHEN days.date BETWEEN DATE '{available_start}' AND DATE '{available_end}' AND d.name IS NULL THEN 'ROW_MISSING' END,
                    CASE WHEN d.name IS NOT NULL AND d.downloads IS NULL THEN 'NULL_VALUE' END,
                    CASE WHEN d.imputed_gap THEN 'IMPUTED_GAP' END], x -> x IS NOT NULL) AS reasons
                    FROM names n CROSS JOIN days LEFT JOIN daily d ON d.name=n.name AND d.date=days.date)
                SELECT package_id,name,date,unnest(reasons) AS reason FROM reasons""")
        con.execute("COPY (SELECT * FROM daily_quality ORDER BY name,date,reason) TO ? (FORMAT PARQUET)", [str(quality_path)])
        unmatched_path = output_dir / "unmatched_packages.parquet"
        con.execute("""CREATE TEMP VIEW unmatched AS SELECT t.name,s.status AS input_status,
            coalesce(d.observed_days,0)::INTEGER AS observed_days,'TARGET_NOT_IN_APPROVED_POPULATION' AS reason
            FROM targets t LEFT JOIN packages p USING(name) JOIN statuses s ON s.name=t.name
            LEFT JOIN daily_aggregate d ON d.name=t.name WHERE p.package_id IS NULL""")
        con.execute("COPY (SELECT * FROM unmatched ORDER BY name) TO ? (FORMAT PARQUET)", [str(unmatched_path)])
        counts = con.execute("""SELECT count(*),count(*) FILTER(WHERE data_status='COMPLETE'),
            count(*) FILTER(WHERE data_status='PARTIAL'),count(*) FILTER(WHERE data_status='UNAVAILABLE'),
            count(*) FILTER(WHERE download_sum=0),count(*) FILTER(WHERE download_sum=0 AND data_status='PARTIAL') FROM results""").fetchone()
        if counts[0] != package_rows or sum(counts[1:4]) != package_rows:
            raise ValueError("output population or status counts differ")
        quality = dict(zip(("package_rows", "complete_rows", "partial_rows", "unavailable_rows", "zero_rows", "partial_zero_rows"), counts))
        quality.update(target_rows=con.execute("SELECT count(*) FROM targets").fetchone()[0],
                       target_duplicate_rows=duplicate_targets,
                       unmatched_names=con.execute("SELECT count(*) FROM unmatched").fetchone()[0],
                       daily_quality_rows=con.execute("SELECT count(*) FROM daily_quality").fetchone()[0],
                       null_reason_counts=dict(con.execute("SELECT null_reason,count(*) FROM results WHERE null_reason IS NOT NULL GROUP BY null_reason ORDER BY null_reason").fetchall()))
        records, schemas = [], {}
        for path, role in ((interval_path, "interval_downloads"), (quality_path, "daily_quality"), (unmatched_path, "unmatched_packages")):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b""):
                    digest.update(chunk)
            row_count = con.execute("SELECT count(*) FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchone()[0]
            records.append({"path": path.name, "role": role, "bytes": path.stat().st_size, "sha256": digest.hexdigest(), "row_count": row_count})
            schemas[role] = [{"name": r[0], "type": r[1]} for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchall()]
        if records[0]["row_count"] != package_rows:
            raise ValueError("written output row count mismatch")
        return {"files": records, "quality": quality, "schema": {"grain": "(package_id,snapshot_at)", **schemas}, "lineage": lineage}
