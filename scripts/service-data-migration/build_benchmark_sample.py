#!/usr/bin/env python3
"""Build a bounded, referentially closed real-data sample for migration benchmarks.

The source is accessed through the already prepared dump-client container.  All
source-side tables are temporary and the process never issues DDL or DML that
survives the source session.  The benchmark database is a new local PostgreSQL
container mounted below ``data/service-data-migration/benchmark-01``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


SOURCE = "pickage-267-validation"
HELPER = "pickage-341-local-dump-client-pickage-267-validation"
SOURCE_DB = "pickage_267_full_defaulted"
TARGET_CONTAINER = "pickage-341-benchmark-01"
TARGET_DB = "pickage_341_benchmark_01"
SCHEMA = "vd193_reload_20260912_ready01"
SOURCE_ARCHIVE = Path("data/service-data-migration/341/local-dump-probe")
OUTPUT = Path("data/service-data-migration/benchmark-01")


class SampleError(RuntimeError):
    pass


def run(cmd: Sequence[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(cmd), input=input_text, text=True, capture_output=True,
                            encoding="utf-8", errors="replace")
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SampleError(f"명령 실패({result.returncode}): {' '.join(cmd[:4])}: {detail[-1000:]}")
    return result


def source_psql(sql: str) -> str:
    result = run(["docker", "exec", "-i", HELPER, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                  "-h", "127.0.0.1", "-U", "postgres", "-d", SOURCE_DB, "-At"], input_text=sql)
    return result.stdout


def shell_psql(container: str, database: str, sql: str) -> str:
    return run(["docker", "exec", "-i", container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", database, "-At"], input_text=sql).stdout


def qident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def child_partitions() -> list[tuple[str, float]]:
    text = source_psql(
        "SELECT c.relname, c.reltuples::double precision "
        "FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE i.inhparent='public.package_version_snapshot'::regclass "
        "ORDER BY c.relname;"
    )
    values = []
    for line in text.splitlines():
        name, estimate = line.split("|", 1)
        values.append((name, max(float(estimate), 1.0)))
    if len(values) < 4:
        raise SampleError(f"pvs 파티션이 4개 미만입니다: {len(values)}")
    return values


def signature_query(table: str) -> str:
    return f"""
SELECT count(*)::text,
       coalesce(sum((('x'||substr(row_hash,1,16))::bit(64)::bigint)::numeric),0)::text,
       coalesce(sum((('x'||substr(row_hash,17,16))::bit(64)::bigint)::numeric),0)::text
FROM (SELECT md5(row_to_json(s)::text) AS row_hash FROM {table} s) q;
"""


def prepare_source(out: Path, *, pvs_cap: int, version_cap: int, package_snapshot_cap: int, package_cap: int) -> dict:
    parts = child_partitions()
    selected = [parts[0], parts[len(parts) // 3], parts[(2 * len(parts)) // 3], parts[-1]]
    # A generous rate plus LIMIT prevents a stale reltuples estimate from
    # producing a tiny sample, while the LIMIT keeps the benchmark bounded.
    def rate(cap: int, estimate: float) -> float:
        return min(100.0, max(0.25, cap * 100.0 / estimate * 1.8))

    source_rel = lambda filename: f"/work/{out.name}/source-csv/{filename}"
    pvs_parts = []
    for index, (name, estimate) in enumerate(selected):
        pvs_parts.append(
            f"(SELECT * FROM {qident(SCHEMA)}.{qident(name)} TABLESAMPLE SYSTEM ({rate(pvs_cap // 4, estimate):.8f}) "
            f"REPEATABLE (341 + {index}) LIMIT {pvs_cap // 4})"
        )
    sql_parts = "\nUNION ALL\n".join(pvs_parts)
    first_partition = selected[0][0]
    sql = rf"""
CREATE TEMP TABLE sampled_pvs AS TABLE {qident(SCHEMA)}.{qident(first_partition)} WITH NO DATA;
CREATE TEMP TABLE sampled_package_snapshot AS TABLE public.package_snapshot WITH NO DATA;
CREATE TEMP TABLE sampled_version AS TABLE public.version WITH NO DATA;
CREATE TEMP TABLE sampled_package AS TABLE public.package WITH NO DATA;
CREATE TEMP TABLE sampled_snapshot AS TABLE public.snapshot WITH NO DATA;
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL DateStyle = 'ISO, YMD';
INSERT INTO sampled_pvs
{sql_parts};
INSERT INTO sampled_package_snapshot
  SELECT * FROM public.package_snapshot TABLESAMPLE SYSTEM (0.15) REPEATABLE (1341)
  LIMIT {package_snapshot_cap};
INSERT INTO sampled_version (version,package_id,published_at,ordinal,description,licenses,deprecated,dependency)
  SELECT v.version, v.package_id, v.published_at, v.ordinal, v.description, v.licenses, v.deprecated, v.dependency
  FROM public.version v TABLESAMPLE SYSTEM (1.2) REPEATABLE (2341)
    LIMIT {version_cap};
INSERT INTO sampled_version (version,package_id,published_at,ordinal,description,licenses,deprecated,dependency)
  SELECT v.version, v.package_id, v.published_at, v.ordinal, v.description, v.licenses, v.deprecated, v.dependency
  FROM public.version v JOIN (SELECT DISTINCT package_id, version FROM sampled_pvs) k
    ON k.package_id=v.package_id AND k.version=v.version
  WHERE NOT EXISTS (SELECT 1 FROM sampled_version x WHERE x.package_id=v.package_id AND x.version=v.version);
INSERT INTO sampled_package
  SELECT * FROM public.package TABLESAMPLE SYSTEM (0.5) REPEATABLE (3341)
  LIMIT {package_cap};
INSERT INTO sampled_package
  SELECT p.* FROM public.package p JOIN (
    SELECT package_id FROM sampled_version
    UNION SELECT package_id FROM sampled_package_snapshot
    UNION SELECT package_id FROM sampled_pvs
  ) k ON k.package_id=p.package_id
  WHERE NOT EXISTS (SELECT 1 FROM sampled_package x WHERE x.package_id=p.package_id);
INSERT INTO sampled_snapshot SELECT * FROM public.snapshot;

\copy (SELECT package_id,name,repo_url FROM sampled_package ORDER BY package_id) TO '{source_rel("package.csv")}' WITH (FORMAT csv)
\copy (SELECT package_id,version,published_at,ordinal,description,licenses,deprecated,dependency FROM sampled_version ORDER BY package_id,version) TO '{source_rel("version.csv")}' WITH (FORMAT csv)
\copy (SELECT snapshot_at FROM sampled_snapshot ORDER BY snapshot_at) TO '{source_rel("snapshot.csv")}' WITH (FORMAT csv)
\copy (SELECT package_id,snapshot_at,downloads,stars,open_issues FROM sampled_package_snapshot ORDER BY package_id,snapshot_at) TO '{source_rel("package_snapshot.csv")}' WITH (FORMAT csv)
\copy (SELECT package_id,version,snapshot_at,dependents_count FROM sampled_pvs ORDER BY package_id,version,snapshot_at) TO '{source_rel("package_version_snapshot.csv")}' WITH (FORMAT csv)
"""
    for name, table in [("package", "sampled_package"), ("version", "sampled_version"),
                        ("snapshot", "sampled_snapshot"), ("package_snapshot", "sampled_package_snapshot"),
                        ("package_version_snapshot", "sampled_pvs")]:
        inner = signature_query(table).strip().rstrip(";")
        sql += f"SELECT '{name}', q.* FROM ({inner}) q;\n"
    # The source session is read-only by contract.  COPY files and calculated
    # signatures survive; all temporary tables disappear on rollback.
    sql += "ROLLBACK;\n"
    started = time.monotonic()
    result = source_psql(sql)
    elapsed = time.monotonic() - started
    signatures = {}
    for line in result.splitlines():
        fields = line.split("|", 3)
        if len(fields) == 4 and fields[0] in {"package", "version", "snapshot", "package_snapshot", "package_version_snapshot"}:
            signatures[fields[0]] = {"rows": int(fields[1]), "sum_hi": fields[2], "sum_lo": fields[3]}
    if len(signatures) != 5:
        raise SampleError(f"샘플 집계 결과를 모두 읽지 못했습니다: {result[-1000:]}")
    return {"selected_partitions": [name for name, _ in selected], "source_prepare_seconds": round(elapsed, 3), "signatures": signatures}


def start_target(out: Path) -> None:
    existing = run(["docker", "inspect", TARGET_CONTAINER], check=False)
    if existing.returncode == 0:
        raise SampleError(f"기존 벤치마크 컨테이너가 있어 덮어쓰지 않습니다: {TARGET_CONTAINER}")
    run(["docker", "run", "-d", "--name", TARGET_CONTAINER, "--memory=4g", "--memory-swap=4g",
         "-e", "POSTGRES_PASSWORD=benchmark", "-e", f"POSTGRES_DB={TARGET_DB}",
         "-v", f"{out.resolve()}:/work", "postgres:16", "postgres"])
    for _ in range(60):
        ready = run(["docker", "exec", TARGET_CONTAINER, "pg_isready", "-U", "postgres", "-d", TARGET_DB], check=False)
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise SampleError("벤치마크 PostgreSQL이 준비되지 않았습니다")


def load_target(out: Path, source_meta: dict) -> dict:
    schema_file = SOURCE_ARCHIVE / "source-schema.sql"
    if not schema_file.exists():
        raise SampleError(f"원본 schema 파일이 없습니다: {schema_file}")
    schema_text = schema_file.read_text(encoding="utf-8")
    schema_sql = f'CREATE SCHEMA IF NOT EXISTS {qident(SCHEMA)};\n' + schema_text
    started = time.monotonic()
    run(["docker", "exec", "-i", TARGET_CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres", "-d", TARGET_DB], input_text=schema_sql)
    import_sql = "BEGIN;\n"
    cols = {
        "package": "package_id,name,repo_url", "version": "package_id,version,published_at,ordinal,description,licenses,deprecated,dependency",
        "snapshot": "snapshot_at", "package_snapshot": "package_id,snapshot_at,downloads,stars,open_issues",
        "package_version_snapshot": "package_id,version,snapshot_at,dependents_count",
    }
    for name, columns in cols.items():
        import_sql += f"\\copy public.{name} ({columns}) FROM '/work/source-csv/{name}.csv' WITH (FORMAT csv);\n"
    import_sql += "COMMIT;\n"
    run(["docker", "exec", "-i", TARGET_CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres", "-d", TARGET_DB], input_text=import_sql)
    elapsed = time.monotonic() - started
    actual = {}
    for name in cols:
        row = shell_psql(TARGET_CONTAINER, TARGET_DB, signature_query(f"public.{name}"))
        fields = row.strip().split("|")
        actual[name] = {"rows": int(fields[0]), "sum_hi": fields[1], "sum_lo": fields[2]}
    return {"target_load_seconds": round(elapsed, 3), "target_signatures": actual,
            "signature_match": actual == source_meta["signatures"]}


def validate_args(args: argparse.Namespace) -> tuple[Path, Path]:
    if any(value <= 0 for value in (args.pvs_cap, args.version_cap, args.package_snapshot_cap, args.package_cap)):
        raise SampleError("모든 cap은 양수여야 합니다")
    estimated_max = 2 * args.version_cap + 3 * args.pvs_cap + 2 * args.package_snapshot_cap + args.package_cap + 229
    if estimated_max > 10_000_000:
        raise SampleError(f"보수적 최대 행 수가 10,000,000을 초과합니다: {estimated_max}")
    base = (Path.cwd() / "data" / "service-data-migration").resolve()
    out = args.output.resolve()
    if out.parent != base or not re.fullmatch(r"benchmark-[0-9]+", out.name):
        raise SampleError(f"output은 data/service-data-migration/benchmark-N 형식이어야 합니다: {out}")
    if out.exists() and any(out.iterdir()):
        raise SampleError(f"기존 output을 덮어쓰지 않습니다: {out}")
    csv_dir = SOURCE_ARCHIVE / out.name / "source-csv"
    if csv_dir.exists() and any(csv_dir.iterdir()):
        raise SampleError(f"기존 source CSV를 덮어쓰지 않습니다: {csv_dir}")
    return out, csv_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--pvs-cap", type=int, default=1_000_000)
    parser.add_argument("--version-cap", type=int, default=300_000)
    parser.add_argument("--package-snapshot-cap", type=int, default=300_000)
    parser.add_argument("--package-cap", type=int, default=50_000)
    args = parser.parse_args(argv)
    out = None
    try:
        out, csv_dir = validate_args(args)
        csv_dir.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        metadata = prepare_source(out, pvs_cap=args.pvs_cap, version_cap=args.version_cap,
                                  package_snapshot_cap=args.package_snapshot_cap, package_cap=args.package_cap)
        target_csv = out / "source-csv"
        target_csv.mkdir(parents=True, exist_ok=True)
        for name in ("package", "version", "snapshot", "package_snapshot", "package_version_snapshot"):
            shutil.copy2(csv_dir / f"{name}.csv", target_csv / f"{name}.csv")
        target_started = time.monotonic()
        start_target(out)
        shutil.copy2(SOURCE_ARCHIVE / "source-schema.sql", out / "source-schema.sql")
        loaded = load_target(out, metadata)
        result = {"created_at": datetime.now(timezone.utc).isoformat(), "source_container": SOURCE,
                  "target_container": TARGET_CONTAINER, "target_database": TARGET_DB,
                  "total_seconds": round(time.monotonic() - started, 3), "target_setup_and_load_seconds": round(time.monotonic() - target_started, 3),
                  **metadata, **loaded}
        (out / "sample-metadata.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "expected-signatures.json").write_text(
            json.dumps(metadata["signatures"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if loaded["signature_match"] else 2
    except Exception as exc:
        if out is not None:
            out.mkdir(parents=True, exist_ok=True)
            (out / "failure-status.json").write_text(json.dumps({
                "status": "FAILED", "reason": str(exc),
                "container_left_for_inspection": TARGET_CONTAINER,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
