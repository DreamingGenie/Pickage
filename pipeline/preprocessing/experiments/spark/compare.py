"""Exact multiset comparison; file layout and JSON object key order may differ."""
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
from pipeline.preprocessing.experiments.spark.job import GROUPS


def files_for(output, engine, stage, group):
    if stage == "dependents" and engine == "baseline":
        root = Path(output) / "outputs" / (group + ".parquet")
    else:
        root = Path(output) / group
    return [str(root)] if root.is_file() else [str(p) for p in sorted(root.rglob("*.parquet"))]


def _normalize(value):
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value.isoformat() if hasattr(value, "isoformat") else value


def canonicalize(con, files, target, json_columns):
    if not files:
        raise ValueError("Missing output Parquet")
    schema = sorted((r[0], r[1]) for r in con.execute(
        "DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [files]).fetchall())
    names = [name for name, _ in schema]
    quoted = {name: '"' + name.replace('"', '""') + '"' for name in names}
    columns = ",".join(
        f"({quoted[name]} AT TIME ZONE 'UTC') AS {quoted[name]}"
        if kind == "TIMESTAMP WITH TIME ZONE" else quoted[name] for name, kind in schema)
    query = con.execute("SELECT " + columns + " FROM read_parquet(?,hive_partitioning=false)", [files])
    count = 0
    with target.open("x", encoding="utf-8") as stream:
        while batch := query.fetchmany(4096):
            for row in batch:
                values = list(row)
                for i, name in enumerate(names):
                    if name in json_columns and values[i] is not None:
                        values[i] = json.loads(values[i])
                stream.write(json.dumps(_normalize(values), sort_keys=True, ensure_ascii=True,
                                        separators=(",", ":"), allow_nan=False) + "\n")
                count += 1
    logical = [(name, "JSON" if name in json_columns else
                "UTC_TIMESTAMP" if kind in ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE") else kind)
               for name, kind in schema]
    return schema, logical, count


def compare(baseline, spark, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    results = {}
    if baseline["status"] != "COMPUTED" or spark["status"] != "COMPUTED":
        raise ValueError("Both engines must finish before comparison")
    if baseline["input_identity"] != spark["input_identity"]:
        raise ValueError("Engine inputs differ")
    if baseline.get("code_sha256") != spark.get("code_sha256"):
        raise ValueError("Source code changed between engine runs")
    if set(baseline["stages"]) != set(spark["stages"]):
        raise ValueError("Engine stage sets differ")
    with duckdb.connect(config={"memory_limit": "1GB", "threads": 2}) as con:
        con.execute("SET temp_directory=?", [str(root / "scratch")])
        for stage in baseline["stages"]:
            for index, group in enumerate(GROUPS[stage]):
                label = stage + "/" + group
                json_columns = {"licenses", "dependency"} if label == "package_version/version/data" else set()
                tables, records = [], []
                for engine, report in (("baseline", baseline), ("spark", spark)):
                    path = root / f"{stage}-{index}-{engine}.jsonl"
                    files = files_for(report["stages"][stage]["output"], engine, stage, group)
                    schema, logical, count = canonicalize(con, files, path, json_columns)
                    table = "a" if engine == "baseline" else "b"
                    con.execute(f"CREATE OR REPLACE TABLE {table}(value VARCHAR)")
                    if count:
                        con.execute(f"INSERT INTO {table} SELECT * FROM read_csv(?,header=false,"
                                    "columns={'value':'VARCHAR'},delim='\x1f',quote='',escape='',"
                                    "max_line_size=67108864,buffer_size=134217728,parallel=false)", [str(path)])
                    tables.append(logical)
                    records.append({"engine": engine, "rows": count, "schema": schema})
                missing = con.execute("SELECT count(*) FROM (SELECT * FROM a EXCEPT ALL SELECT * FROM b)").fetchone()[0]
                extra = con.execute("SELECT count(*) FROM (SELECT * FROM b EXCEPT ALL SELECT * FROM a)").fetchone()[0]
                results[label] = {"equal": tables[0] == tables[1] and missing == extra == 0,
                                  "baseline_only_rows": missing, "spark_only_rows": extra,
                                  "logical_schema_equal": tables[0] == tables[1], "outputs": records}
    return {"status": "EQUAL" if all(r["equal"] for r in results.values()) else "DIFFERENT", "groups": results,
            "comparison": "EXACT_CANONICAL_ROW_MULTISET", "normalizations": [
                "JSON logical annotation/string and object key order", "declared UTC timestamp representation", "column order"],
            "file_bytes_compared": False}
