"""DuckDB implementation of the repository metric transformation.

This module deliberately has no Spark dependency.  It is an experiment
backend for comparing the repository stage while keeping the same input
contract, six output relations, and validation rules as the normal stage.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
import json

from pipeline.curated.repository import normalize_repository_url
from pipeline.snapshot.policy import parse_timestamp


class ValidationError(ValueError):
    """An input or publication contract failed."""


_MAX_INT = 2_147_483_647
_OUTPUTS = (
    "metric/data",
    "quality/selection",
    "quality/candidates",
    "quality/project_observations",
    "quality/project_conflicts",
    "quality/unmapped_projects",
)


def _files(inputs: dict, name: str) -> list[str]:
    values = inputs.get("files", {}).get(name)
    if not isinstance(values, list) or not values or any(not isinstance(x, str) for x in values):
        raise ValidationError(f"missing input files: {name}")
    return values


def _read(con: Any, inputs: dict, name: str) -> str:
    expected = inputs.get("counts", {}).get(name)
    if type(expected) is not int or expected < 0:
        raise ValidationError(f"missing manifest count: {name}")
    table = "input_" + name.replace("-", "_")
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} AS SELECT * FROM read_parquet(?)", [_files(inputs, name)])
    actual = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if actual != expected:
        raise ValidationError(f"input row count mismatch: {name}")
    print(f"INPUT_COUNT_VERIFIED {name} rows={expected}", flush=True)
    return table


def _columns(con: Any, table: str) -> dict[str, str]:
    return {row[0]: row[1] for row in con.execute(f"DESCRIBE {table}").fetchall()}


def _require(con: Any, table: str, name: str, columns: set[str]) -> dict[str, str]:
    schema = _columns(con, table)
    missing = columns.difference(schema)
    if missing:
        raise ValidationError(f"{name} schema missing: {','.join(sorted(missing))}")
    return schema


def _is_timestamp(type_name: str) -> bool:
    # DuckDB can expose UTC-annotated Parquet timestamps with or without a
    # timezone. Both represent Spark's TimestampType input contract.
    return type_name.upper() in {"TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE"}


def _is_integral(type_name: str) -> bool:
    return type_name.upper().split("(", 1)[0] in {"TINYINT", "SMALLINT", "INTEGER", "BIGINT"}


def _is_string(type_name: str) -> bool:
    return type_name.upper().split("(", 1)[0] == "VARCHAR"


def _write(con: Any, output: Path, name: str, table: str) -> int:
    target = output / name
    target.mkdir(parents=True, exist_ok=True)
    file = target / "part-00000.parquet"
    con.execute("COPY (SELECT * FROM " + table + ") TO ? (FORMAT PARQUET)", [str(file)])
    return con.execute("SELECT count(*) FROM read_parquet(?)", [str(file)]).fetchone()[0]


def transform(con: Any, inputs: dict, output: Path) -> dict:
    """Transform approved package/version and Projects Parquet into evidence."""
    if not isinstance(inputs, dict) or not isinstance(inputs.get("snapshot_timestamp"), str):
        raise ValidationError("snapshot_timestamp is required")
    snapshot = inputs.get("snapshot")
    if not isinstance(snapshot, str):
        raise ValidationError("snapshot is required")
    timestamp_text = inputs["snapshot_timestamp"]
    try:
        parsed = parse_timestamp(timestamp_text[:-1] + "+00:00" if timestamp_text.endswith("Z") else timestamp_text)
    except (TypeError, ValueError) as exc:
        raise ValidationError("invalid snapshot_timestamp") from exc
    if parsed.date().isoformat() != snapshot:
        raise ValidationError("snapshot_timestamp date does not match snapshot")
    # All comparisons below use UTC-naive values, matching Spark's UTC session
    # semantics while retaining the original text in lineage columns.
    instant_value = parsed.replace(tzinfo=None)
    con.execute("SET TimeZone='UTC'")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValidationError("output must be a fresh empty directory")
    output.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    def mark(name: str, started: float) -> None:
        timings[name] = round(perf_counter() - started, 6)

    started = perf_counter()
    package, version = _read(con, inputs, "package"), _read(con, inputs, "version")
    raw, projects = _read(con, inputs, "versions_full"), _read(con, inputs, "projects")
    schemas = {
        "package": _require(con, package, "package", {"package_id", "name"}),
        "version": _require(con, version, "version", {"package_id", "version", "published_at", "ordinal"}),
        "versions_full": _require(con, raw, "versions_full", {"SnapshotAt", "Name", "Version", "is_release", "published_at", "ordinal", "source_repo"}),
        "projects": _require(con, projects, "projects", {"SnapshotAt", "Type", "project_name", "StarsCount", "OpenIssuesCount"}),
    }
    for table, name, column in ((version, "version", "published_at"), (raw, "versions_full", "published_at"), (raw, "versions_full", "SnapshotAt"), (projects, "projects", "SnapshotAt")):
        if not _is_timestamp(schemas[name][column]):
            raise ValidationError(f"{name} timestamp schema must be TIMESTAMP")
    for table, name, columns in ((package, "package", ("package_id",)), (version, "version", ("package_id", "ordinal")), (raw, "versions_full", ("ordinal",)), (projects, "projects", ("StarsCount", "OpenIssuesCount"))):
        if any(not _is_integral(schemas[name][column]) for column in columns):
            raise ValidationError(f"{name} numeric schema is invalid")
    if schemas["versions_full"]["is_release"].upper() not in {"BOOLEAN", "BOOL"}:
        raise ValidationError("versions_full is_release schema is invalid")
    for name, columns in (("package", ("name",)), ("version", ("version",)), ("versions_full", ("Name", "Version", "source_repo")), ("projects", ("Type", "project_name"))):
        if any(not _is_string(schemas[name][column]) for column in columns):
            raise ValidationError(f"{name} string schema is invalid")
    # Normalize timezone-bearing Parquet timestamps to UTC-naive columns once,
    # so every later join and published output has the same instant semantics.
    version = "input_version_normalized"
    raw = "input_versions_full_normalized"
    projects = "input_projects_normalized"
    con.execute("CREATE OR REPLACE TEMP TABLE " + version + " AS SELECT package_id, version, CAST(published_at AS TIMESTAMP) AS published_at, ordinal FROM input_version")
    con.execute("CREATE OR REPLACE TEMP TABLE " + raw + " AS SELECT CAST(SnapshotAt AS TIMESTAMP) AS SnapshotAt, Name, Version, is_release, CAST(published_at AS TIMESTAMP) AS published_at, ordinal, source_repo FROM input_versions_full")
    con.execute("CREATE OR REPLACE TEMP TABLE " + projects + " AS SELECT * REPLACE (CAST(SnapshotAt AS TIMESTAMP) AS SnapshotAt) FROM input_projects")
    checks = {
        "package": f"package_id IS NULL OR package_id < 1 OR package_id > {_MAX_INT} OR name IS NULL OR length(trim(name)) = 0",
        "version": f"package_id IS NULL OR package_id < 1 OR package_id > {_MAX_INT} OR version IS NULL OR length(trim(version)) = 0 OR ordinal IS NULL OR ordinal < 0",
    }
    for name, table in (("package", package), ("version", version)):
        if con.execute(f"SELECT 1 FROM {table} WHERE {checks[name]} LIMIT 1").fetchone():
            raise ValidationError(f"invalid {name} key/range/null")
    if con.execute(f"SELECT package_id FROM {package} GROUP BY package_id HAVING count(*) > 1 LIMIT 1").fetchone() or con.execute(f"SELECT name FROM {package} GROUP BY name HAVING count(*) > 1 LIMIT 1").fetchone():
        raise ValidationError("duplicate package key")
    if con.execute(f"SELECT package_id, version FROM {version} GROUP BY package_id, version HAVING count(*) > 1 LIMIT 1").fetchone():
        raise ValidationError("duplicate curated version key")
    if con.execute(f"SELECT 1 FROM {version} v LEFT JOIN {package} p USING (package_id) WHERE p.package_id IS NULL LIMIT 1").fetchone():
        raise ValidationError("version package FK missing")
    con.execute("CREATE OR REPLACE TEMP TABLE approved AS SELECT v.package_id, p.name, v.version, v.ordinal, v.published_at FROM " + version + " v JOIN " + package + " p USING (package_id)")
    if con.execute("SELECT count(*) FROM approved").fetchone()[0] != inputs["counts"]["version"]:
        raise ValidationError("approved version count mismatch")
    mark("input_validation_and_approved_join", started)
    print("KEYS_AND_EXACT_TIMESTAMPS_VERIFIED", flush=True)
    print("APPROVED_VERSION_JOIN_VERIFIED", flush=True)

    instant = "CAST(? AS TIMESTAMP)"
    if con.execute(f"SELECT 1 FROM {raw} WHERE SnapshotAt IS NULL OR SnapshotAt <> ? LIMIT 1", [instant_value]).fetchone() or con.execute(f"SELECT 1 FROM {projects} WHERE SnapshotAt IS NULL OR SnapshotAt <> ? LIMIT 1", [instant_value]).fetchone():
        raise ValidationError("source has missing or wrong exact SnapshotAt")
    con.execute("CREATE OR REPLACE TEMP TABLE matched AS SELECT v.package_id, v.name, v.version, v.ordinal AS curated_ordinal, v.published_at AS curated_published_at, r.Name AS raw_name, r.ordinal, r.published_at, r.is_release, r.source_repo FROM approved v LEFT JOIN " + raw + " r ON v.name = r.Name AND v.version = r.Version")
    if con.execute("SELECT 1 FROM matched WHERE raw_name IS NULL LIMIT 1").fetchone():
        raise ValidationError("approved version missing raw key")
    if con.execute("SELECT 1 FROM matched WHERE is_release IS NULL OR NOT is_release OR published_at > ? LIMIT 1", [instant_value]).fetchone():
        raise ValidationError("approved version violates release/snapshot eligibility")
    if con.execute("SELECT 1 FROM matched GROUP BY package_id, version HAVING count(*) > 1 LIMIT 1").fetchone():
        raise ValidationError("duplicate raw version key")
    if con.execute("SELECT 1 FROM matched WHERE curated_ordinal IS DISTINCT FROM ordinal OR curated_published_at IS DISTINCT FROM published_at LIMIT 1").fetchone():
        raise ValidationError("Curated/raw ordinal or published_at mismatch")
    print("BRONZE_VERSION_JOIN_VERIFIED", flush=True)

    # The benchmark image intentionally has no NumPy, which DuckDB's Python
    # UDF bridge requires.  Normalize URL keys in bounded batches instead of
    # collecting the full candidate input into Python.
    con.execute("CREATE OR REPLACE TEMP TABLE url_map(source_repo VARCHAR, repo_url VARCHAR)")
    last_url: str | None = None
    while True:
        if last_url is None:
            batch = con.execute("SELECT DISTINCT source_repo FROM matched WHERE source_repo IS NOT NULL ORDER BY source_repo LIMIT 4096").fetchall()
        else:
            batch = con.execute("SELECT DISTINCT source_repo FROM matched WHERE source_repo IS NOT NULL AND source_repo > ? ORDER BY source_repo LIMIT 4096", [last_url]).fetchall()
        if not batch:
            break
        con.executemany("INSERT INTO url_map VALUES (?, ?)", [(value[0], normalize_repository_url(value[0])) for value in batch])
        last_url = batch[-1][0]
    con.execute("CREATE OR REPLACE TEMP TABLE candidates AS SELECT m.package_id, m.name, m.version, m.ordinal, m.published_at, m.source_repo, u.repo_url, u.repo_url IS NOT NULL AS eligible, CASE WHEN m.source_repo IS NULL THEN 'NO_REPOSITORY_URL' WHEN u.repo_url IS NULL THEN 'INVALID_OR_UNSUPPORTED_REPOSITORY_URL' ELSE 'VALID_REPOSITORY_CANDIDATE' END AS reason FROM matched m LEFT JOIN url_map u USING (source_repo)")
    con.execute("CREATE OR REPLACE TEMP TABLE selected AS SELECT *, regexp_extract(repo_url, '^https://([^/]+)/', 1) AS provider, regexp_extract(repo_url, '^https://[^/]+/(.+)$', 1) AS project_path, CASE WHEN regexp_extract(repo_url, '^https://([^/]+)/', 1) = 'github.com' THEN lower(regexp_extract(repo_url, '^https://[^/]+/(.+)$', 1)) ELSE regexp_extract(repo_url, '^https://[^/]+/(.+)$', 1) END AS comparison_project_path, regexp_extract(repo_url, '^https://([^/]+)/', 1) || '|' || CASE WHEN regexp_extract(repo_url, '^https://([^/]+)/', 1) = 'github.com' THEN lower(regexp_extract(repo_url, '^https://[^/]+/(.+)$', 1)) ELSE regexp_extract(repo_url, '^https://[^/]+/(.+)$', 1) END AS repo_key, TRUE AS selected FROM candidates WHERE eligible QUALIFY row_number() OVER (PARTITION BY package_id ORDER BY ordinal DESC, published_at DESC NULLS LAST, version ASC) = 1")
    con.execute("CREATE OR REPLACE TEMP TABLE observations_base AS SELECT *, CASE WHEN upper(Type) = 'GITHUB' THEN 'github.com' WHEN upper(Type) = 'GITLAB' THEN 'gitlab.com' END AS provider, project_name AS source_project_path, CASE WHEN upper(Type) = 'GITHUB' THEN lower(project_name) ELSE project_name END AS project_path FROM " + projects)
    con.execute("CREATE OR REPLACE TEMP TABLE observations_base2 AS SELECT *, CASE WHEN provider IS NOT NULL AND length(trim(project_path)) > 0 THEN provider || '|' || project_path END AS repo_key, (StarsCount < 0 OR OpenIssuesCount < 0 OR StarsCount > " + str(_MAX_INT) + " OR OpenIssuesCount > " + str(_MAX_INT) + ") AS invalid_metric FROM observations_base")
    con.execute("CREATE OR REPLACE TEMP TABLE unmapped AS SELECT *, 'PROVIDER_PATH_MAPPING_FAILED' AS reason FROM observations_base2 WHERE repo_key IS NULL OR length(trim(project_path)) = 0")
    con.execute("CREATE OR REPLACE TEMP TABLE pairs AS SELECT repo_key, provider, project_path, SnapshotAt, StarsCount, OpenIssuesCount, count(*) AS source_rows, min(source_project_path) AS source_project_path, max(CASE WHEN invalid_metric THEN 1 ELSE 0 END) AS invalid_metric FROM observations_base2 WHERE repo_key IS NOT NULL AND length(trim(project_path)) > 0 GROUP BY ALL")
    con.execute("CREATE OR REPLACE TEMP TABLE canonical AS SELECT repo_key, provider, project_path, SnapshotAt, first(StarsCount) AS stars_raw, first(OpenIssuesCount) AS open_issues_raw, min(source_project_path) AS source_project_path, max(invalid_metric) AS invalid, CAST(sum(source_rows) AS BIGINT) AS source_rows, count(*) AS distinct_metric_pairs FROM pairs GROUP BY ALL")
    con.execute("CREATE OR REPLACE TEMP TABLE canonical_values AS SELECT *, CASE WHEN distinct_metric_pairs > 1 OR invalid = 1 THEN NULL ELSE CAST(stars_raw AS INTEGER) END AS stars, CASE WHEN distinct_metric_pairs > 1 OR invalid = 1 THEN NULL ELSE CAST(open_issues_raw AS INTEGER) END AS open_issues FROM canonical")
    con.execute("CREATE OR REPLACE TEMP TABLE joined AS SELECT p.package_id, s.*, c.repo_key AS observed_repo_key, c.source_project_path AS observed_project_path, c.SnapshotAt, c.stars_raw, c.open_issues_raw, c.invalid, c.source_rows, c.distinct_metric_pairs, c.stars, c.open_issues FROM " + package + " p LEFT JOIN selected s USING (package_id) LEFT JOIN canonical_values c ON s.repo_key = c.repo_key AND c.SnapshotAt = ?", [instant_value])
    con.execute("CREATE OR REPLACE TEMP TABLE metric_data AS SELECT package_id, CAST(? AS DATE) AS snapshot_at, stars, open_issues FROM joined", [snapshot])
    con.execute("CREATE OR REPLACE TEMP TABLE selection AS SELECT package_id, version, ordinal, repo_url, provider, project_path, comparison_project_path, observed_project_path, ? AS snapshot, ? AS snapshot_timestamp, CASE WHEN SnapshotAt IS NOT NULL THEN SnapshotAt END AS observed_timestamp, CASE WHEN repo_key IS NULL THEN 'NO_VALID_REPOSITORY' WHEN distinct_metric_pairs > 1 THEN 'PROJECT_METRIC_CONFLICT' WHEN invalid = 1 THEN 'INVALID_METRIC_VALUE' WHEN SnapshotAt IS NULL THEN 'NO_EXACT_OBSERVATION' ELSE 'SELECTED' END AS reason, CASE WHEN repo_url IS NULL THEN 'NO_SELECTED_REPOSITORY' WHEN SnapshotAt IS NULL THEN 'NO_EXACT_PROVIDER_PATH_MATCH' ELSE 'MATCHED' END AS mapping_status FROM joined", [snapshot, timestamp_text])
    con.execute("CREATE OR REPLACE TEMP TABLE candidates_out AS SELECT c.package_id, c.version, c.source_repo, c.repo_url, c.ordinal, c.published_at, c.eligible, c.reason, coalesce(s.selected, FALSE) AS selected, ? AS snapshot, ? AS snapshot_timestamp FROM candidates c LEFT JOIN selected s USING (package_id, version)", [snapshot, timestamp_text])
    con.execute("CREATE OR REPLACE TEMP TABLE project_observations AS SELECT repo_key, provider, project_path, source_project_path, SnapshotAt, stars, open_issues, source_rows, distinct_metric_pairs, invalid FROM canonical_values")
    con.execute("CREATE OR REPLACE TEMP TABLE project_conflicts AS SELECT p.*, 'PROJECT_METRIC_CONFLICT' AS reason FROM pairs p JOIN (SELECT repo_key, SnapshotAt FROM pairs GROUP BY repo_key, SnapshotAt HAVING count(*) > 1) c USING (repo_key, SnapshotAt)")
    con.execute("CREATE OR REPLACE TEMP TABLE unmapped_projects AS SELECT * FROM unmapped")
    names = {"metric_data": "metric/data", "selection": "quality/selection", "candidates_out": "quality/candidates", "project_observations": "quality/project_observations", "project_conflicts": "quality/project_conflicts", "unmapped_projects": "quality/unmapped_projects"}
    counts = {}
    for table, name in names.items():
        print(f"WRITING_OUTPUT {name}", flush=True)
        counts[name] = _write(con, output, name, table)
        print(f"OUTPUT_COUNT_VERIFIED {name} rows={counts[name]}", flush=True)
    if con.execute("SELECT count(*) FROM metric_data").fetchone()[0] != con.execute(f"SELECT count(*) FROM {package}").fetchone()[0] or con.execute("SELECT 1 FROM metric_data GROUP BY package_id, snapshot_at HAVING count(*) > 1 LIMIT 1").fetchone():
        raise ValidationError("metric output count/key reconciliation failed")
    def grouped(table: str, column: str) -> dict[str, int]:
        return {str(k): int(v) for k, v in con.execute(f"SELECT {column}, count(*) FROM {table} GROUP BY {column}").fetchall()}
    null_reasons = {str(k): int(v) for k, v in con.execute("SELECT reason, count(*) FROM selection WHERE package_id IN (SELECT package_id FROM metric_data WHERE stars IS NULL OR open_issues IS NULL) GROUP BY reason").fetchall()}
    report = {"output_counts": counts, "mapping": {"packages": inputs["counts"]["package"], "selected": con.execute("SELECT count(*) FROM selected").fetchone()[0], "null": con.execute("SELECT count(*) FROM metric_data WHERE stars IS NULL AND open_issues IS NULL").fetchone()[0]}, "selection_reasons": grouped("selection", "reason"), "null_reasons": null_reasons, "candidate_reasons": grouped("candidates", "reason"), "conflicts": con.execute("SELECT count(*) FROM (SELECT repo_key, SnapshotAt FROM pairs GROUP BY repo_key, SnapshotAt HAVING count(*) > 1)").fetchone()[0], "unsupported_project_rows": counts["quality/unmapped_projects"], "validation": "PASSED", "lineage": {"snapshot": snapshot, "snapshot_timestamp": timestamp_text, "counts": inputs["counts"]}}
    # Keep the comparison report byte-for-byte contract compatible with the
    # Spark report; timing is diagnostic metadata in a sidecar artifact.
    (output.parent / "duckdb-actions.json").write_text(json.dumps({"timings_seconds": timings}, indent=2), encoding="utf-8")
    return report


__all__ = ["ValidationError", "transform"]
