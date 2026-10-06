"""Read-only comparison of a completed load with its exact Curated input.

The PostgreSQL connection runs in a read-only transaction. This checks current
data; it intentionally refuses to compare a historical run with a newer current.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.postgresql.postgres import PgLoader  # noqa: E402
from pipeline.postgresql.input import DEFAULT_DEPENDENCY, DEFAULT_DEPENDENCY_JSON  # noqa: E402


STATS = """count(*) AS rows,
    count(*) FILTER (WHERE published_at IS NULL) AS published_at_null,
    count(*) FILTER (WHERE description IS NULL) AS description_null,
    count(*) FILTER (WHERE licenses IS NULL) AS licenses_sql_null,
    count(*) FILTER (WHERE CAST(licenses AS VARCHAR)='null') AS licenses_json_null,
    count(*) FILTER (WHERE deprecated IS NULL) AS deprecated_null,
    count(*) FILTER (WHERE dependency IS NULL) AS dependency_sql_null,
    count(*) FILTER (WHERE CAST(dependency AS VARCHAR)='null') AS dependency_json_null,
    min(ordinal) AS min_ordinal, max(ordinal) AS max_ordinal"""


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def records(cursor):
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--docker-container", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for value in (args.docker_container, args.database):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            parser.error("container and database must be simple names")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report["status"] != "PUBLISHED":
        parser.error("the load report must be PUBLISHED")
    metadata = report["input"]
    base = args.report.resolve().parent
    literal = PgLoader._literal

    def query(sql):
        result = subprocess.run(
            ["docker", "exec", "-i", args.docker_container, "psql", "-X", "-q", "-A", "-t",
             "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", args.database],
            input=("BEGIN READ ONLY; SET timezone='UTC'; SET standard_conforming_strings=on;\n"
                   + sql + "\nROLLBACK;\n").encode("utf-8"), capture_output=True, timeout=900)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-2000:])
        return json.loads(result.stdout.decode("utf-8"))

    current = query("SELECT row_to_json(c) FROM public.etl_dataset_current c WHERE dataset='package-version';")
    if current["manifest_sha256"] != metadata["manifest_sha256"]:
        raise ValueError("DB current input differs; do not compare historical attributes with a newer input")
    paths = {}
    for table, entries in metadata["_service_records"].items():
        paths[table] = []
        for entry in entries:
            path = base / "cache" / table / (entry["sha256"] + ".parquet")
            if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
                raise ValueError("input cache verification failed: " + path.name)
            paths[table].append(path.as_posix())
    print("Verified exact input cache hashes", flush=True)
    with duckdb.connect(config={"threads": 4, "memory_limit": "4GB"}) as con:
        raw_stats = records(con.execute(f"SELECT {STATS} FROM read_parquet(?,hive_partitioning=false)", [paths["version"]]))[0]
        expected_stats = dict(raw_stats, dependency_sql_null=0)
        defaulted_keys = set(con.execute("SELECT package_id,version FROM read_parquet(?,hive_partitioning=false) WHERE dependency IS NULL", [paths["version"]]).fetchall())
        expected_packages = records(con.execute("SELECT count(*) AS rows,count(*) FILTER(WHERE repo_url IS NULL) AS repo_url_null FROM read_parquet(?,hive_partitioning=false)", [paths["package"]]))[0]
        samples = []
        for path in paths["version"]:
            samples.extend(records(con.execute("SELECT * FROM read_parquet(?,hive_partitioning=false) LIMIT 5", [path])))
        for condition in ("dependency IS NULL", "licenses IS NULL", "published_at IS NULL", "contains(description,chr(10))"):
            samples.extend(records(con.execute(f"SELECT * FROM read_parquet(?,hive_partitioning=false) WHERE {condition} LIMIT 30", [paths["version"]])))
        samples = {(row["package_id"], row["version"]): row for row in samples}
        expected_versions = []
        for key in sorted(samples):
            row = samples[key]
            if row["dependency"] is None:
                row["dependency"] = DEFAULT_DEPENDENCY_JSON
            row["licenses_sql_null"] = row["licenses"] is None
            row["dependency_sql_null"] = row["dependency"] is None
            for name in ("licenses", "dependency"):
                if row[name] is not None:
                    row[name] = json.loads(row[name])
            if row["published_at"] is not None:
                row["published_at"] = row["published_at"].strftime("%Y-%m-%d %H:%M:%S.%f")
            expected_versions.append(row)
        ids = sorted({row["package_id"] for row in expected_versions})
        id_sql = ",".join(str(int(value)) for value in ids)
        expected_package_samples = records(con.execute(f"SELECT * FROM read_parquet(?,hive_partitioning=false) WHERE package_id IN ({id_sql}) ORDER BY package_id", [paths["package"]]))
    print("Collected source statistics and cross-file samples", flush=True)
    actual_stats = query(f"SELECT row_to_json(s) FROM (SELECT {STATS.replace('VARCHAR', 'TEXT')} FROM public.version) s;")
    actual_packages = query("SELECT row_to_json(s) FROM (SELECT count(*) AS rows,count(*) FILTER(WHERE repo_url IS NULL) AS repo_url_null FROM public.package) s;")
    keys = ",".join(f"({row['package_id']},{literal(row['version'])})" for row in expected_versions)
    actual_versions = query("SELECT json_agg(s ORDER BY package_id,version) FROM (SELECT version,package_id,"
                            "to_char(published_at,'YYYY-MM-DD HH24:MI:SS.US') AS published_at,ordinal,description,licenses,deprecated,dependency,"
                            "licenses IS NULL AS licenses_sql_null,dependency IS NULL AS dependency_sql_null FROM public.version "
                            f"WHERE (package_id,version) IN (VALUES {keys})) s;")
    actual_package_samples = query(f"SELECT json_agg(s ORDER BY package_id) FROM (SELECT * FROM public.package WHERE package_id IN ({id_sql})) s;")
    # Compare by Python Unicode ordering; DB collation ordering can differ.
    actual_versions.sort(key=lambda row: (row["package_id"], row["version"]))
    execution = query("SELECT row_to_json(e) FROM public.etl_load_execution e "
                      f"WHERE execution_id={literal(report['execution_id'])};")
    attempt_quality = query("SELECT quality_report FROM public.etl_load_attempt "
                            f"WHERE attempt_id={literal(report['attempt_id'])};")
    quality = report["quality"]["dependency_defaulted"]
    quality_path = Path(quality["path"])
    quality_rows = [json.loads(line) for line in quality_path.read_text(encoding="utf-8").splitlines() if line]
    dependency_not_null = query("SELECT to_json(attnotnull) FROM pg_attribute WHERE attrelid='public.version'::regclass AND attname='dependency';")
    constraints = query("SELECT json_agg(json_build_object('table',conrelid::regclass::text,'name',conname,'validated',convalidated)) "
                        "FROM pg_constraint WHERE conrelid IN ('public.package'::regclass,'public.version'::regclass);")
    checks = {
        "package_counts_and_nulls": expected_packages == actual_packages,
        "version_counts_and_nulls": expected_stats == actual_stats,
        "package_sample_fields": expected_package_samples == actual_package_samples,
        "version_sample_fields": expected_versions == actual_versions,
        "constraints_validated": all(row["validated"] for row in constraints),
        "execution_published": execution["status"] == "PUBLISHED",
        "execution_identity": execution["manifest_sha256"] == metadata["manifest_sha256"] and execution["contract_sha256"] == report["contract_sha256"],
        "empty_database_counts": report.get("service_before_counts") == {"package": 0, "version": 0},
        "dependency_not_null": dependency_not_null is True,
        "quality_file_hash": digest(quality_path) == quality["sha256"],
        "quality_defaulted_rows": len(quality_rows) == quality["count"] == raw_stats["dependency_sql_null"]
            and {(row["package_id"], row["version"]) for row in quality_rows} == defaulted_keys
            and all(row["replacement"] == DEFAULT_DEPENDENCY and row["source_dependency_is_sql_null"] is True for row in quality_rows),
        "quality_database_history": attempt_quality == report["quality"],
    }
    output = {"verified_at": datetime.now(timezone.utc).isoformat(), "status": "PASSED" if all(checks.values()) else "FAILED",
              "database": args.database, "container": args.docker_container, "execution_id": report["execution_id"],
              "input_manifest_sha256": metadata["manifest_sha256"], "contract_sha256": report["contract_sha256"],
              "input_file_count": sum(len(value) for value in paths.values()), "checks": checks,
              "expected_package": expected_packages, "actual_package": actual_packages,
              "expected_version": expected_stats, "actual_version": actual_stats, "constraints": constraints,
              "source_version_before_defaults": raw_stats, "dependency_defaulted_count": quality["count"],
              "package_sample_count": len(expected_package_samples), "version_sample_count": len(expected_versions),
              "sample_sha256": {"package_expected": canonical_hash(expected_package_samples), "package_actual": canonical_hash(actual_package_samples),
                                 "version_expected": canonical_hash(expected_versions), "version_actual": canonical_hash(actual_versions)},
              "limitation": "Full counts/null aggregates and input key/DB constraints; field equality is sampled, not all-row field equality."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "checks": checks, "output": str(args.output)}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
