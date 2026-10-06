"""Profile the bounded H5 dependency lookup workload.

The profiler deliberately keeps the original declaration grain only long enough
to aggregate it.  It never expands declarations by snapshot date and does not
materialize the source dependency arrays in Python.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb


_LOOKUP_SCHEMA = (
    ("lookup_id", "BIGINT"),
    ("declared_name", "VARCHAR"),
    ("requirement", "VARCHAR"),
    ("declaration_count", "BIGINT"),
    ("first_source_birth", "INTEGER"),
)
_PACKAGE_SCHEMA = (
    ("name", "VARCHAR"),
    ("candidate_count", "BIGINT"),
    ("lookup_count", "BIGINT"),
    ("declaration_count", "BIGINT"),
    ("known_package", "BOOLEAN"),
    ("package_id", "INTEGER"),
    ("candidate_payload_bytes", "BIGINT"),
    ("active_candidate", "BOOLEAN"),
)


def _sql_path(path: Path) -> str:
    return "'" + str(Path(path).resolve()).replace("'", "''") + "'"


def _schema(con: duckdb.DuckDBPyConnection, relation: str, expected: tuple[tuple[str, str], ...]) -> None:
    actual = tuple((str(row[0]), str(row[1]).upper().replace('"', ""))
                   for row in con.execute(f"DESCRIBE {relation}").fetchall())
    if actual != expected:
        raise ValueError(f"{relation} schema mismatch: expected {expected}, got {actual}")


def _json(value: Any) -> Any:
    """Convert DuckDB scalar results to JSON-safe values without full fetches."""
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    if hasattr(value, "item"):
        return _json(value.item())
    return value


def _validate_inputs(con: duckdb.DuckDBPyConnection, snapshot_count: int) -> None:
    if not isinstance(snapshot_count, int) or isinstance(snapshot_count, bool) or snapshot_count <= 0:
        raise ValueError("snapshot_count must be a positive integer")
    for relation, columns in {
        "source_population": (
            ("source_package_id", "INTEGER"), ("source_name", "VARCHAR"),
            ("source_version", "VARCHAR"), ("birth_index", "INTEGER"),
            ("requirements_present", "BOOLEAN"), ("selected_list_null", "BOOLEAN"),
            ("declaration_count", "BIGINT"), ("excluded_peer_count", "BIGINT"),
            ("excluded_optional_count", "BIGINT"), ("dependency_error", "BOOLEAN")),
        "target_population": (("package_id", "INTEGER"), ("name", "VARCHAR"),
                              ("version", "VARCHAR"), ("birth_index", "INTEGER")),
        "input_requirements": (("Name", "VARCHAR"), ("Version", "VARCHAR"),
                                ("Dependencies", "STRUCT(Name VARCHAR, Requirement VARCHAR)[]")),
        "input_package": (("package_id", "INTEGER"), ("name", "VARCHAR")),
    }.items():
        actual = [(str(row[0]), str(row[1]).upper().replace('"', ""))
                  for row in con.execute(f"DESCRIBE {relation}").fetchall()]
        actual_map = dict(actual)
        for name, type_name in columns:
            actual_type = actual_map.get(name)
            if actual_type is None:
                raise ValueError(f"{relation} is missing required column: {name}")
            # H1 projection files can carry extra provenance columns and do not
            # promise a column order.  Dependency arrays are accepted with
            # DuckDB's quoted STRUCT field spelling as well.
            if name == "Dependencies":
                if not actual_type.startswith("STRUCT") and "STRUCT" not in actual_type:
                    raise ValueError(f"{relation}.{name} must be a STRUCT array")
            elif actual_type != type_name:
                raise ValueError(f"{relation}.{name} type mismatch: {actual_type} != {type_name}")
    bad = con.execute("""
        SELECT count(*) FROM source_population
        WHERE declaration_count IS NULL OR declaration_count < 0
           OR birth_index IS NULL OR birth_index < 0
    """).fetchone()[0]
    if bad:
        raise ValueError("source_population contains invalid declaration or birth values")
    if con.execute("SELECT count(*) FROM source_population WHERE birth_index >= ?", [snapshot_count]).fetchone()[0]:
        raise ValueError("source_population birth_index is outside snapshot_count")
    bad = con.execute("""
        SELECT count(*) FROM target_population
        WHERE package_id IS NULL OR package_id <= 0 OR name IS NULL
           OR version IS NULL OR birth_index IS NULL OR birth_index < 0
    """).fetchone()[0]
    if bad:
        raise ValueError("target_population contains invalid identity or birth values")
    if con.execute("SELECT count(*) FROM target_population WHERE birth_index >= ?", [snapshot_count]).fetchone()[0]:
        raise ValueError("target_population birth_index is outside snapshot_count")
    if con.execute("SELECT count(*) FROM input_package WHERE package_id IS NULL OR name IS NULL").fetchone()[0]:
        raise ValueError("input_package contains null identity")
    if con.execute("SELECT count(*) FROM (SELECT package_id FROM input_package GROUP BY 1 HAVING count(*)>1)").fetchone()[0]:
        raise ValueError("input_package has duplicate package_id")
    if con.execute("SELECT count(*) FROM (SELECT name FROM input_package GROUP BY 1 HAVING count(*)>1)").fetchone()[0]:
        raise ValueError("input_package has duplicate name")


def _write_outputs(con: duckdb.DuckDBPyConnection, output: Path) -> None:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for filename in ("lookup_workload.parquet", "package_workload.parquet"):
        path = output / filename
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
    con.execute(f"COPY lookup_workload TO {_sql_path(output / 'lookup_workload.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(f"COPY package_workload TO {_sql_path(output / 'package_workload.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)")


def _stats(con: duckdb.DuckDBPyConnection, snapshot_count: int) -> dict[str, Any]:
    source = con.execute("""
        SELECT count(*)::BIGINT, coalesce(sum(declaration_count),0)::HUGEINT,
               count(*) FILTER (WHERE requirements_present)::BIGINT,
               count(*) FILTER (WHERE selected_list_null)::BIGINT
        FROM source_population
    """).fetchone()
    targets = con.execute("SELECT count(*)::BIGINT, count(DISTINCT name)::BIGINT FROM target_population").fetchone()
    lookups = con.execute("""
        SELECT count(*)::BIGINT, coalesce(sum(declaration_count),0)::HUGEINT,
               count(*) FILTER (WHERE declared_name IS NULL)::BIGINT,
               count(*) FILTER (WHERE requirement IS NULL)::BIGINT
        FROM lookup_workload
    """).fetchone()
    package_counts = con.execute("""
        SELECT count(*)::BIGINT,
               count(*) FILTER (WHERE known_package)::BIGINT,
               count(*) FILTER (WHERE candidate_count > 100000)::BIGINT,
               coalesce(max(candidate_count),0)::BIGINT,
               count(*) FILTER (WHERE candidate_count > 0 AND lookup_count = 0)::BIGINT,
               count(*) FILTER (WHERE active_candidate)::BIGINT,
               coalesce(max(candidate_count) FILTER (WHERE active_candidate),0)::BIGINT
        FROM package_workload
    """).fetchone()
    estimates = con.execute("""

        SELECT coalesce(sum(candidate_count::HUGEINT * lookup_count::HUGEINT),0)::HUGEINT,
               coalesce(max(candidate_count::HUGEINT * lookup_count::HUGEINT),0)::HUGEINT
        FROM package_workload WHERE name IS NOT NULL
    """).fetchone()
    payload = con.execute("""
        SELECT coalesce(max(candidate_payload_bytes) FILTER (WHERE active_candidate),0),
               count(*) FILTER (WHERE active_candidate AND candidate_payload_bytes > 7340032),
               count(*) FILTER (WHERE active_candidate AND candidate_count > 100000)
        FROM package_workload
    """).fetchone()
    lengths = con.execute("""
        SELECT coalesce(max(octet_length(encode(coalesce(declared_name,'')))),0),
               coalesce(max(octet_length(encode(coalesce(requirement,'')))),0)
        FROM lookup_workload
    """).fetchone()
    length_buckets = con.execute("""
        SELECT bucket, count(*)::BIGINT FROM (
          SELECT CASE
            WHEN octet_length(encode(coalesce(declared_name,'')))=0 THEN '0'
            WHEN octet_length(encode(coalesce(declared_name,'')))<=32 THEN '1-32'
            WHEN octet_length(encode(coalesce(declared_name,'')))<=128 THEN '33-128'
            WHEN octet_length(encode(coalesce(declared_name,'')))<=512 THEN '129-512'
            ELSE '513+'
          END AS bucket FROM lookup_workload
        ) GROUP BY bucket ORDER BY bucket
    """).fetchall()
    # A worker must not receive more than either the frame or lookup bound.
    max_candidates = int(package_counts[6] or 0)
    candidate_bound = 2_000_000 // max_candidates if max_candidates else 512
    batch_limit = min(512, candidate_bound, 20_000 // snapshot_count)
    batch_limit = max(0, batch_limit)
    heavy = con.execute("""
        SELECT name, candidate_count, lookup_count, declaration_count, known_package, package_id,
               candidate_payload_bytes, active_candidate
        FROM package_workload
        WHERE name IS NOT NULL ORDER BY candidate_count DESC, name LIMIT 50
    """).fetchall()
    heavy_lookup = con.execute("""
        SELECT lookup_id, declared_name, requirement, declaration_count, first_source_birth
        FROM lookup_workload ORDER BY declaration_count DESC, lookup_id LIMIT 50
    """).fetchall()
    # Hash-selected rows are deterministic and bounded; the full relations stay in Parquet.
    sample = con.execute("""
        SELECT lookup_id, declared_name, requirement, declaration_count, first_source_birth
        FROM lookup_workload
        ORDER BY md5(to_json(struct_pack(name := declared_name, req := requirement))), lookup_id
        LIMIT 20
    """).fetchall()
    return _json({
        "source_rows": int(source[0]), "source_declarations": source[1],
        "sources_with_requirements": int(source[2]), "sources_with_null_dependency_list": int(source[3]),
        "target_rows": int(targets[0]), "target_names": int(targets[1]),
        "unique_lookups": int(lookups[0]), "lookup_declarations": lookups[1],
        "null_declared_name_lookups": int(lookups[2]), "null_requirement_lookups": int(lookups[3]),
        "package_workload_rows": int(package_counts[0]), "known_package_names": int(package_counts[1]),
        "candidate_overbound_package_count": int(package_counts[2]), "max_candidate_count": int(package_counts[3]),
        "target_names_without_lookup": int(package_counts[4]), "active_candidate_names": int(package_counts[5]),
        "max_active_candidate_count": int(package_counts[6]),
        "estimated_candidate_x_lookup": estimates[0],
        "max_active_candidate_payload_bytes": int(payload[0]),
        "active_candidate_payload_overbound_packages": int(payload[1]),
        "active_candidate_count_overbound_packages": int(payload[2]),
        "max_candidate_x_lookup": estimates[1], "snapshot_count": snapshot_count,
        "worker_requirement_batch_max": batch_limit,
        "worker_batch_overbound": bool(max_candidates > 100000 or payload[1] or batch_limit == 0),
        "candidate_payload_bytes_are_estimates": True,
        "candidate_payload_definition": "UTF-8 bytes of JSON array of {version,birth_index} candidate objects; worker raw JSON escaping may differ",
        "full_worker_request_bytes_measured": False,
        "max_declared_name_utf8_bytes": int(lengths[0]), "max_requirement_utf8_bytes": int(lengths[1]),
        "declared_name_length_distribution": {str(k): int(v) for k, v in length_buckets},
        "top50_heavy_candidates": [dict(zip(("name", "candidate_count", "lookup_count", "declaration_count", "known_package", "package_id", "candidate_payload_bytes", "active_candidate"), row)) for row in heavy],
        "top50_heavy_lookups": [dict(zip(("lookup_id", "declared_name", "requirement", "declaration_count", "first_source_birth"), row)) for row in heavy_lookup],
        "hash_sample_20_lookups": [dict(zip(("lookup_id", "declared_name", "requirement", "declaration_count", "first_source_birth"), row)) for row in sample],
    })


def profile_tables(con: duckdb.DuckDBPyConnection, *, output: Path, snapshot_count: int,
                   on_stage=None) -> dict[str, Any]:
    """Create the two bounded workload Parquets and return JSON-safe statistics."""
    def report(phase):
        if on_stage is not None:
            on_stage(phase)

    report("VALIDATE_PROFILE_TABLES")
    _validate_inputs(con, snapshot_count)
    # One row per original declaration. UNNEST remains inside DuckDB and preserves
    # duplicates, null fields, and empty strings; no array is fetched to Python.
    con.execute("""
        CREATE OR REPLACE TEMP VIEW declaration_rows AS
        SELECT s.birth_index AS first_source_birth,
               d.Name AS declared_name, d.Requirement AS requirement
        FROM source_population s
        JOIN input_requirements r ON r.Name = s.source_name AND r.Version = s.source_version
        CROSS JOIN UNNEST(r.Dependencies) AS u(d)
    """)
    report("SUM_SOURCE_DECLARATIONS")
    source_sum = con.execute("SELECT coalesce(sum(declaration_count),0)::HUGEINT FROM source_population").fetchone()[0]
    report("GROUP_UNIQUE_REQUIREMENTS")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE lookup_workload AS
        SELECT row_number() OVER (ORDER BY declared_name NULLS FIRST, requirement NULLS FIRST)::BIGINT AS lookup_id,
               declared_name, requirement, count(*)::BIGINT AS declaration_count,
               min(first_source_birth)::INTEGER AS first_source_birth
        FROM declaration_rows
        GROUP BY declared_name, requirement
    """)
    report("CHECK_DECLARATION_CONSERVATION")
    actual_sum = con.execute("SELECT coalesce(sum(declaration_count),0)::HUGEINT FROM lookup_workload").fetchone()[0]
    if actual_sum != source_sum:
        raise ValueError(f"declaration conservation failure: source={source_sum}, expanded={actual_sum}")
    report("GROUP_PACKAGE_CANDIDATES")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE package_workload AS
        WITH candidates AS (
            SELECT name, count(*)::BIGINT AS candidate_count,
                   (2 + sum(octet_length(encode(to_json(struct_pack(
                       version := version, birth_index := birth_index))))) + count(*) - 1)::BIGINT
                       AS candidate_payload_bytes
            FROM target_population GROUP BY name
        ), lookups AS (
            SELECT declared_name AS name, count(*)::BIGINT AS lookup_count,
                   sum(declaration_count)::BIGINT AS declaration_count
            FROM lookup_workload GROUP BY declared_name
        ), names AS (
            SELECT name FROM candidates UNION SELECT name FROM lookups
        )
        SELECT n.name, coalesce(c.candidate_count,0)::BIGINT AS candidate_count,
               coalesce(l.lookup_count,0)::BIGINT AS lookup_count,
               coalesce(l.declaration_count,0)::BIGINT AS declaration_count,
               p.package_id IS NOT NULL AS known_package,
               p.package_id::INTEGER AS package_id,
               coalesce(c.candidate_payload_bytes,0)::BIGINT AS candidate_payload_bytes,
               (coalesce(c.candidate_count,0) > 0 AND coalesce(l.lookup_count,0) > 0) AS active_candidate
        FROM names n
        LEFT JOIN candidates c ON (n.name = c.name OR (n.name IS NULL AND c.name IS NULL))
        LEFT JOIN lookups l ON (n.name = l.name OR (n.name IS NULL AND l.name IS NULL))
        LEFT JOIN input_package p ON n.name = p.name
        ORDER BY n.name NULLS FIRST
    """)
    report("WRITE_PROFILE_OUTPUTS")
    _write_outputs(con, Path(output))
    report("SUMMARIZE_PROFILE_OUTPUTS")
    stats = _stats(con, snapshot_count)
    if stats["source_declarations"] != stats["lookup_declarations"]:
        raise ValueError("output lookup declaration total disagrees with source total")
    return stats


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_profile_tables(con: duckdb.DuckDBPyConnection, output: Path, expected_stats: dict[str, Any]) -> dict[str, Any]:
    """Re-read both Parquets through DuckDB and verify pinned aggregate invariants."""
    output = Path(output)
    lookup = output / "lookup_workload.parquet"
    package = output / "package_workload.parquet"
    if not lookup.is_file() or not package.is_file():
        raise ValueError("profile output is incomplete")
    con.execute(f"CREATE OR REPLACE TEMP VIEW verify_lookup AS SELECT * FROM read_parquet({_sql_path(lookup)}, hive_partitioning=false)")
    con.execute(f"CREATE OR REPLACE TEMP VIEW verify_package AS SELECT * FROM read_parquet({_sql_path(package)}, hive_partitioning=false)")
    _schema(con, "verify_lookup", _LOOKUP_SCHEMA)
    _schema(con, "verify_package", _PACKAGE_SCHEMA)
    if con.execute("SELECT EXISTS (SELECT 1 FROM verify_lookup GROUP BY lookup_id HAVING count(*)<>1)").fetchone()[0]:
        raise ValueError("lookup_id is not unique")
    if con.execute("""
        SELECT count(*) FROM (
          SELECT lookup_id, row_number() OVER (ORDER BY lookup_id)::BIGINT AS expected_id
          FROM verify_lookup
        ) WHERE lookup_id <> expected_id
    """).fetchone()[0]:
        raise ValueError("lookup_id sequence is not deterministic")
    bad = con.execute("""
        SELECT count(*) FROM (
          SELECT declared_name, requirement, count(*) AS n FROM verify_lookup
          GROUP BY 1,2 HAVING n<>1
        )
    """).fetchone()[0]
    if bad:
        raise ValueError("duplicate lookup condition")
    if con.execute("SELECT count(*) FROM (SELECT name FROM verify_package GROUP BY name HAVING count(*)<>1)").fetchone()[0]:
        raise ValueError("package workload name is not unique")
    if con.execute("SELECT count(*) FROM verify_package WHERE candidate_count < 0 OR lookup_count < 0 OR declaration_count < 0").fetchone()[0]:
        raise ValueError("package workload contains a negative count")
    actual = con.execute("""
        SELECT count(*)::BIGINT, coalesce(sum(declaration_count),0)::HUGEINT
        FROM verify_lookup
    """).fetchone()
    expected = expected_stats.get("source_declarations")
    if expected is None or int(actual[1]) != int(expected):
        raise ValueError("verified lookup declarations disagree with expected source total")
    package_rows = int(con.execute("SELECT count(*) FROM verify_package").fetchone()[0])
    if expected_stats.get("package_workload_rows") is not None and package_rows != int(expected_stats["package_workload_rows"]):
        raise ValueError("verified package workload row count changed")
    if con.execute("SELECT count(*) FROM verify_package WHERE name IS NULL AND known_package").fetchone()[0]:
        raise ValueError("NULL declared-name row cannot be a known package")
    if con.execute("SELECT count(*) FROM verify_lookup WHERE first_source_birth IS NULL OR first_source_birth < 0 OR first_source_birth >= ? OR lookup_id IS NULL OR lookup_id <= 0 OR declaration_count IS NULL OR declaration_count <= 0", [expected_stats["snapshot_count"]]).fetchone()[0]:
        raise ValueError("lookup workload has an invalid first source birth")
    if expected_stats.get("unique_lookups") is not None and int(actual[0]) != int(expected_stats["unique_lookups"]):
        raise ValueError("verified lookup count changed")
    package_totals = con.execute("""
        SELECT coalesce(sum(candidate_count),0)::HUGEINT,
               coalesce(sum(lookup_count),0)::HUGEINT,
               coalesce(sum(declaration_count),0)::HUGEINT
        FROM verify_package
    """).fetchone()
    if expected_stats.get("target_rows") is not None and int(package_totals[0]) != int(expected_stats["target_rows"]):
        raise ValueError("verified candidate total changed")
    if int(package_totals[1]) != int(actual[0]):
        raise ValueError("verified package lookup total changed")
    if int(package_totals[2]) != int(expected):
        raise ValueError("verified package declaration total changed")
    for original, stored, label in (("lookup_workload", "verify_lookup", "lookup"),
                                    ("package_workload", "verify_package", "package")):
        mismatch = con.execute(
            f"SELECT count(*) FROM ((SELECT * FROM {original} EXCEPT ALL SELECT * FROM {stored}) "
            f"UNION ALL (SELECT * FROM {stored} EXCEPT ALL SELECT * FROM {original}))"
        ).fetchone()[0]
        if mismatch:
            raise ValueError(f"{label} Parquet differs from the original SQL relation")
    return {
        "verified": True,
        "lookup_rows": int(actual[0]),
        "package_rows": package_rows,
        "lookup_workload_sha256": _file_sha(lookup),
        "package_workload_sha256": _file_sha(package),
    }
