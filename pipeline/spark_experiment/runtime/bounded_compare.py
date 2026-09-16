"""Exact bounded-memory multiset comparison for frozen engine outputs."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from pipeline.spark_experiment.compare import files_for
from pipeline.spark_experiment.job import GROUPS


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _canonical_json(value):
    if value is None:
        return None
    parsed = json.loads(value) if isinstance(value, str) else value
    return json.dumps(parsed, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _schema(con, paths):
    if not paths:
        raise ValueError("Missing output Parquet")
    return sorted((row[0], row[1]) for row in con.execute(
        "DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [paths]).fetchall())


def _logical_schema(schema, json_columns):
    return [(name, "JSON" if name in json_columns else
             "UTC_TIMESTAMP" if kind in ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE") else kind)
            for name, kind in schema]


def _projection(schema, json_columns):
    expressions = []
    for name, kind in schema:
        col = _quote(name)
        if name in json_columns:
            expr = f"canonical_json(CAST({col} AS VARCHAR)) AS {col}"
        elif kind == "TIMESTAMP WITH TIME ZONE":
            expr = f"timezone('UTC', {col}) AS {col}"
        else:
            expr = col
        expressions.append(expr)
    return ", ".join(expressions)


def _staging_projection(schema, json_columns):
    expressions = []
    for name, kind in schema:
        col = _quote(name)
        if name in json_columns or kind == "JSON":
            expr = f"CAST({col} AS VARCHAR) AS {col}"
        elif kind == "TIMESTAMP WITH TIME ZONE":
            expr = f"timezone('UTC', {col}) AS {col}"
        else:
            expr = col
        expressions.append(expr)
    return ", ".join(expressions)


def _count(con, files):
    return con.execute("SELECT count(*) FROM read_parquet(?, hive_partitioning=false)", [files]).fetchone()[0]


def _difference_count(con, left, left_projection, right, right_projection):
    sql = (f"SELECT count(*) FROM (SELECT {left_projection} FROM read_parquet(?, hive_partitioning=false) "
           f"EXCEPT ALL SELECT {right_projection} FROM read_parquet(?, hive_partitioning=false))")
    return con.execute(sql, [left, right]).fetchone()[0]


def _stage_json_side(con, table, files, schema, json_columns):
    """Canonicalize JSON in bounded batches into a spillable DuckDB temp table."""
    projection = _staging_projection(schema, json_columns)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} AS SELECT {projection} "
                "FROM read_parquet(?, hive_partitioning=false) WHERE false", [files])
    names = [name for name, _ in schema]
    quoted = ", ".join(_quote(name) for name in names)
    placeholders = ", ".join("?" for _ in names)
    insert = f"INSERT INTO {table} ({quoted}) VALUES ({placeholders})"
    cursor = con.cursor()
    cursor.execute("SELECT " + projection +
                   " FROM read_parquet(?, hive_partitioning=false)", [files])
    count = 0
    while batch := cursor.fetchmany(2048):
        normalized = []
        for row in batch:
            values = list(row)
            for index, (name, _) in enumerate(schema):
                if name in json_columns:
                    values[index] = _canonical_json(values[index])
            normalized.append(values)
        con.executemany(insert, normalized)
        count += len(normalized)
    return count


def _compare_group(con, baseline_files, spark_files, json_columns):
    baseline_schema = _schema(con, baseline_files)
    spark_schema = _schema(con, spark_files)
    baseline_logical = _logical_schema(baseline_schema, json_columns)
    spark_logical = _logical_schema(spark_schema, json_columns)
    logical_schema_equal = baseline_logical == spark_logical
    # Use the intersection only when schemas agree; on mismatch report counts/schema without
    # manufacturing a row comparison across different types or columns.
    baseline_rows, spark_rows = _count(con, baseline_files), _count(con, spark_files)
    if logical_schema_equal and json_columns:
        baseline_rows = _stage_json_side(con, "bounded_baseline", baseline_files,
                                         baseline_schema, json_columns)
        spark_rows = _stage_json_side(con, "bounded_spark", spark_files,
                                      spark_schema, json_columns)
        baseline_only = con.execute(
            "SELECT count(*) FROM (SELECT * FROM bounded_baseline EXCEPT ALL "
            "SELECT * FROM bounded_spark)").fetchone()[0]
        spark_only = con.execute(
            "SELECT count(*) FROM (SELECT * FROM bounded_spark EXCEPT ALL "
            "SELECT * FROM bounded_baseline)").fetchone()[0]
    elif logical_schema_equal:
        baseline_projection = _projection(baseline_schema, json_columns)
        spark_projection = _projection(spark_schema, json_columns)
        baseline_only = _difference_count(con, baseline_files, baseline_projection,
                                          spark_files, spark_projection)
        spark_only = _difference_count(con, spark_files, spark_projection,
                                        baseline_files, baseline_projection)
    else:
        baseline_rows, spark_rows = _count(con, baseline_files), _count(con, spark_files)
        baseline_only = spark_only = None
    return {
        "equal": logical_schema_equal and baseline_only == 0 and spark_only == 0,
        "baseline_only_rows": baseline_only,
        "spark_only_rows": spark_only,
        "logical_schema_equal": logical_schema_equal,
        "outputs": [
            {"engine": "baseline", "rows": baseline_rows, "schema": baseline_schema},
            {"engine": "spark", "rows": spark_rows, "schema": spark_schema},
        ],
    }


def compare(baseline, spark, directory):
    """Compare exact row multisets one Parquet group at a time using DuckDB SQL."""
    if baseline.get("status") != "COMPUTED" or spark.get("status") != "COMPUTED":
        raise ValueError("Both engines must finish before comparison")
    if baseline.get("input_identity") != spark.get("input_identity"):
        raise ValueError("Engine inputs differ")
    if baseline.get("code_sha256") != spark.get("code_sha256"):
        raise ValueError("Source code changed between engine runs")
    if set(baseline.get("stages", {})) != set(spark.get("stages", {})):
        raise ValueError("Engine stage sets differ")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    scratch = root / "scratch"
    scratch.mkdir()
    results = {}
    with duckdb.connect(config={"memory_limit": "1GB", "threads": 2}) as con:
        con.execute("SET temp_directory=?", [str(scratch)])
        for stage in baseline["stages"]:
            for group in GROUPS[stage]:
                label = stage + "/" + group
                json_columns = {"licenses", "dependency"} if label == "package_version/version/data" else set()
                left = files_for(baseline["stages"][stage]["output"], "baseline", stage, group)
                right = files_for(spark["stages"][stage]["output"], "spark", stage, group)
                results[label] = _compare_group(con, left, right, json_columns)
    return {
        "status": "EQUAL" if all(result["equal"] for result in results.values()) else "DIFFERENT",
        "groups": results,
        "comparison": "EXACT_CANONICAL_ROW_MULTISET",
        "normalizations": ["JSON logical annotation/string and object key order",
                           "declared UTC timestamp representation", "column order"],
        "file_bytes_compared": False,
        "bounded_group_processing": True,
    }
