"""Isolated PostgreSQL/Flyway checks; source is read only. No server connection.

Requires Docker, Java 17+, and PICKAGE_341_JAVA_CLASSPATH containing the existing
application Flyway core/PostgreSQL, Jackson, and PostgreSQL JDBC jars.
Creates only a uniquely named local container, removed in finally.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "backend/src/main/resources/db/migration"
TABLES = ("package", "version", "snapshot", "package_snapshot", "package_version_snapshot")


def run(args, *, stdin=None, expected=True, env=None):
    result = subprocess.run([str(a) for a in args], input=stdin, capture_output=True, env=env)
    if expected and result.returncode:
        raise RuntimeError(f"Command failed ({args[0]}): {result.stderr.decode('utf-8', 'replace')[-5000:]}")
    if not expected and not result.returncode:
        raise AssertionError(f"Unexpected success: {args[0]}")
    return result


def sql(container, database, statement, *, expected=True):
    return run(["docker", "exec", "-i", container, "psql", "-X", "-U", "postgres", "-d", database,
                "-v", "ON_ERROR_STOP=1", "-At"], stdin=statement.encode(), expected=expected).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-container", default="pickage-267-validation")
    parser.add_argument("--source-db", default="pickage_267_full_defaulted")
    parser.add_argument("--image", default="postgres:16-alpine")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    classpath = os.environ.get("PICKAGE_341_JAVA_CLASSPATH")
    if not classpath:
        raise RuntimeError("PICKAGE_341_JAVA_CLASSPATH must point to application runtime jars")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex[:12]
    container = "pickage-341-test-" + run_id
    report = {"run_id": run_id, "scope": "local correctness pilot", "checks": [],
              "server_executed": False, "full_transfer_ready": False}
    started = time.perf_counter()
    created = False

    def check(name):
        report["checks"].append(name)
        print("PASS " + name, flush=True)

    try:
        run(["docker", "run", "-d", "--name", container, "--label", "pickage.task=341-test",
             "--memory=2g", "--shm-size=256m", "-p", "127.0.0.1::5432",
             "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "--mount", f"type=bind,source={output},target=/work", args.image])
        created = True
        for _ in range(60):
            ready = subprocess.run(["docker", "exec", container, "pg_isready", "-U", "postgres"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Test PostgreSQL not ready")
        port = run(["docker", "port", container, "5432/tcp"]).stdout.decode().strip().rsplit(":", 1)[1]

        def flyway(db, target="latest", action="migrate", expected=True):
            env = os.environ.copy()
            env["PICKAGE_341_TEST_JDBC_URL"] = f"jdbc:postgresql://127.0.0.1:{port}/{db}"
            result = run(["java", "--class-path", classpath, HERE / "LocalFlyway.java", action, MIGRATIONS, target],
                         expected=expected, env=env)
            with (output / "flyway.log").open("ab") as log:
                log.write(result.stdout + result.stderr)
            return result

        def database(suffix, target="5"):
            name = "pickage_import_341_" + run_id + "_" + suffix
            sql(container, "postgres", f'CREATE DATABASE "{name}";')
            flyway(name, target)
            return name

        def scalar(db, query):
            return sql(container, db, query).decode().strip()

        def rejected(db, suffix):
            before = scalar(db, "SELECT 'public.package_version_snapshot'::regclass::oid;")
            result = flyway(db, expected=False)
            assert b"V6" in result.stderr + result.stdout or b"partition" in result.stderr + result.stdout
            assert scalar(db, "SELECT 'public.package_version_snapshot'::regclass::oid;") == before
            assert scalar(db, "SELECT count(*) FROM public.flyway_schema_history WHERE version='6';") == "0"
            check(suffix)

        fresh = database("fresh", "latest")
        assert scalar(fresh, "SELECT relkind FROM pg_class WHERE oid='public.package_version_snapshot'::regclass;") == "p"
        flyway(fresh, action="validate")
        check("Flyway V1-to-V6 fresh database")

        populated = database("populated")
        sql(container, populated, """INSERT INTO public.package VALUES (1,'fixture',NULL);
            INSERT INTO public.version(package_id,version) VALUES(1,'1.0.0');
            INSERT INTO public.snapshot VALUES ('2026-08-31');
            INSERT INTO public.package_version_snapshot VALUES(1,'1.0.0','2026-08-31',7);""")
        rejected(populated, "nonempty ordinary table refused atomically")
        assert scalar(populated, "SELECT dependents_count FROM public.package_version_snapshot;") == "7"

        wrong = database("wrong")
        sql(container, wrong, "ALTER TABLE public.package_version_snapshot ADD COLUMN unexpected int;")
        rejected(wrong, "unexpected column refused atomically")

        incoming = database("incoming")
        sql(container, incoming, """CREATE TABLE public.extra_reference(package_id int,version varchar(100),snapshot_at date,
            FOREIGN KEY(package_id,version,snapshot_at) REFERENCES public.package_version_snapshot);""")
        rejected(incoming, "incoming foreign key refused atomically")

        invalid = database("invalid", "latest")
        sql(container, invalid, "ALTER TABLE public.package_version_snapshot ADD COLUMN unexpected int;")
        # Execute immutable V6 directly to re-check an already-partitioned table.
        sql(container, invalid, (MIGRATIONS / "V6__partition_package_version_snapshot.sql").read_text(encoding="utf-8"), expected=False)
        check("invalid existing partition parent refused")

        broad = database("broad", "latest")
        sql(container, broad, """CREATE TABLE public.month_partition PARTITION OF public.package_version_snapshot
            FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');""")
        sql(container, broad, (MIGRATIONS / "V6__partition_package_version_snapshot.sql").read_text(encoding="utf-8"), expected=False)
        check("month-wide child rejected by daily partition contract")

        weak = database("weak", "latest")
        sql(container, weak, """DO $drop_check$ DECLARE n text; BEGIN
            SELECT conname INTO n FROM pg_constraint WHERE conrelid='public.package_version_snapshot'::regclass AND contype='c';
            EXECUTE format('ALTER TABLE public.package_version_snapshot DROP CONSTRAINT %I',n);
            END $drop_check$;
            ALTER TABLE public.package_version_snapshot ADD CHECK (dependents_count >= 0 OR package_id > 0);""")
        sql(container, weak, (MIGRATIONS / "V6__partition_package_version_snapshot.sql").read_text(encoding="utf-8"), expected=False)
        check("weakened nonnegative check refused")

        varchar = database("varchar")
        sql(container, varchar, "ALTER TABLE public.package_version_snapshot ALTER COLUMN version TYPE varchar(200);")
        rejected(varchar, "changed varchar length refused")

        acl = database("acl")
        sql(container, acl, "GRANT SELECT ON public.package_version_snapshot TO PUBLIC;")
        rejected(acl, "custom grants refused without silently removing permissions")

        comments = database("comments")
        sql(container, comments, """COMMENT ON TABLE public.package_version_snapshot IS 'keep table description';
            COMMENT ON COLUMN public.package_version_snapshot.dependents_count IS 'keep metric description';""")
        flyway(comments)
        assert scalar(comments, "SELECT obj_description('public.package_version_snapshot'::regclass);") == "keep table description"
        assert scalar(comments, "SELECT col_description('public.package_version_snapshot'::regclass,4);") == "keep metric description"
        check("table and column comments preserved on empty-table conversion")

        source = database("sample", "1")
        # Reproduce the historical source layout without manufacturing Flyway history.
        sql(container, source, """DROP TABLE public.package_version_snapshot;
            CREATE TABLE public.package_version_snapshot (
              package_id int NOT NULL, version varchar(100) NOT NULL,
              snapshot_at date NOT NULL, dependents_count int NOT NULL DEFAULT 0,
              CONSTRAINT package_version_snapshot_pkey PRIMARY KEY(package_id,version,snapshot_at),
              CONSTRAINT version_fk FOREIGN KEY(package_id,version) REFERENCES public.version(package_id,version),
              CONSTRAINT snapshot_fk FOREIGN KEY(snapshot_at) REFERENCES public.snapshot(snapshot_at),
              CONSTRAINT dependents_nonnegative CHECK(dependents_count >= 0)
            ) PARTITION BY RANGE(snapshot_at);
            CREATE SCHEMA vd193_reload_20260912_ready01;""")
        ids_csv = sql(args.source_container, args.source_db,
                      "COPY (SELECT package_id,name FROM public.package WHERE name IN ('react','pino','winston') ORDER BY name) TO STDOUT WITH CSV;")
        package_rows = list(csv.reader(io.StringIO(ids_csv.decode())))
        assert len(package_rows) == 3
        ids = ",".join(str(int(row[0])) for row in package_rows)
        date_lines = sql(args.source_container, args.source_db,
                     "SELECT snapshot_at FROM public.snapshot ORDER BY snapshot_at DESC LIMIT 3;").decode().splitlines()
        from datetime import date, timedelta
        dates = [date.fromisoformat(item) for item in date_lines]
        assert len(dates) == 3
        dates_sql = ",".join("'" + str(day) + "'" for day in dates)
        for day in dates:
            sql(container, source, f"CREATE TABLE vd193_reload_20260912_ready01.d{day:%Y%m%d} PARTITION OF public.package_version_snapshot FOR VALUES FROM ('{day}') TO ('{day + timedelta(days=1)}');")
        queries = {
            "package": f"SELECT * FROM public.package WHERE package_id IN ({ids}) ORDER BY package_id",
            "version": f"SELECT * FROM public.version WHERE package_id IN ({ids}) ORDER BY package_id,version",
            "snapshot": f"SELECT * FROM public.snapshot WHERE snapshot_at IN ({dates_sql}) ORDER BY snapshot_at",
            "package_snapshot": f"SELECT * FROM public.package_snapshot WHERE package_id IN ({ids}) AND snapshot_at IN ({dates_sql}) ORDER BY package_id,snapshot_at",
            "package_version_snapshot": f"SELECT * FROM public.package_version_snapshot WHERE package_id IN ({ids}) AND snapshot_at IN ({dates_sql}) ORDER BY package_id,version,snapshot_at",
        }
        expected_csv = {}
        for table, query in queries.items():
            rows = sql(args.source_container, args.source_db, f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true);")
            expected_csv[table] = rows
            (output / (table + ".csv")).write_bytes(rows)
            run(["docker", "exec", "-i", container, "psql", "-X", "-U", "postgres", "-d", source, "-v", "ON_ERROR_STOP=1",
                 "-c", f"COPY public.{table} FROM STDIN WITH (FORMAT csv, HEADER true)"], stdin=rows)
        report["sample_packages"] = package_rows
        report["snapshot_dates"] = [str(day) for day in dates]
        report["sample_rows"] = {t: int(scalar(source, f"SELECT count(*) FROM public.{t};")) for t in TABLES}
        check("read-only real source subset copied with original values")

        # Archive/restore pilot is completed below when the CLI is available.
        report["container"] = container
        report["sample_db"] = source
        report["port"] = port
        run_transfer_pilot(container, source, output, database, flyway, scalar, expected_csv, queries, check, report)
        report["status"] = "PASS"
    except BaseException as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        raise
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        if created:
            # Exact container created by this invocation; never touch the source container.
            run(["docker", "rm", "-f", "-v", container])
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def run_transfer_pilot(container, source, output, database, flyway, scalar, expected_csv, queries, check, report):
    import sys
    archive = output / "archive"
    common = ["--archive-dir", archive, "--container", container, "--container-archive-dir", "/work"]

    def cli(command, extra=(), expected=True):
        started = time.perf_counter()
        result = run([sys.executable, HERE / "transfer.py", command, *common, *extra], expected=expected)
        with (output / "transfer.log").open("ab") as log:
            log.write(result.stdout + result.stderr)
        report.setdefault("transfer_steps", []).append({"command": command, "expected_success": expected,
                "elapsed_seconds": round(time.perf_counter() - started, 3)})
        return result

    cli("dump", ["--source-db", source, "--jobs", "4"])
    cli("verify")
    check("selected parallel archive and SHA-256 verified")
    cli("dump", ["--source-db", source], expected=False)
    check("existing archive overwrite refused")
    data_file = next(p for p in archive.iterdir() if p.name != "toc.dat")
    original_bytes = data_file.read_bytes()
    data_file.write_bytes(original_bytes + b"tampered")
    cli("verify", expected=False)
    data_file.write_bytes(original_bytes)
    check("archive byte tampering detected")

    candidate = database("restore", "1")
    prepare = (HERE / "prepare_candidate.sql").read_text(encoding="utf-8")
    history_before = scalar(candidate, "SELECT row_to_json(h) FROM public.flyway_schema_history h;")
    # A populated source with genuine V1 history must remain untouched.
    sql(container, source, prepare, expected=False)
    assert scalar(source, "SELECT count(*) FROM public.package;") == "3"
    check("candidate preparation refuses existing service rows")
    flyway(candidate, "1", "validate")
    sql(container, candidate, prepare)
    assert scalar(candidate, "SELECT row_to_json(h) FROM public.flyway_schema_history h;") == history_before
    check("candidate preparation preserves genuine V1 history")

    options = ["--candidate-db", candidate, "--source-db", source, "--service-db", "pickage", "--jobs", "2"]
    cli("restore", ["--candidate-db", "pickage", "--source-db", source, "--service-db", "pickage"], expected=False)
    check("service database target refused before writes")
    cli("restore", options)
    flyway(candidate)
    flyway(candidate, action="validate")
    check("restored V1 history plus Flyway V2-to-V6 adoption")
    validator = (HERE / "validate_structure.sql").read_text(encoding="utf-8")
    sql(container, candidate, validator)
    first_child = "vd193_reload_20260912_ready01.d" + report["snapshot_dates"][0].replace("-", "")
    sql(container, candidate, f"ALTER TABLE {first_child} ALTER COLUMN dependents_count SET DEFAULT 1;")
    sql(container, candidate, validator, expected=False)
    sql(container, candidate, f"ALTER TABLE {first_child} ALTER COLUMN dependents_count SET DEFAULT 0;")
    sql(container, candidate, validator)
    check("child structure checked and altered child default detected")
    for table, query in queries.items():
        actual = sql(container, candidate, f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true);")
        assert actual == expected_csv[table], f"Different real data in {table}"
    check("all five sample tables match every CSV value including JSON and NULL")
    assert scalar(candidate, "SELECT count(*) FROM pg_inherits WHERE inhparent='public.package_version_snapshot'::regclass;") == "3"
    sql(container, candidate, "UPDATE public.package_version_snapshot SET dependents_count=-1;", expected=False)
    check("partition boundaries and nonnegative constraint preserved")
    cli("restore", options, expected=False)
    check("restoring twice refuses duplicate COPY")
    for table in TABLES:
        sql(container, candidate, f"ANALYZE public.{table};")
    report["archive_bytes"] = sum(p.stat().st_size for p in archive.iterdir() if p.is_file())
    report["candidate_rows"] = {t: int(scalar(candidate, f"SELECT count(*) FROM public.{t};")) for t in TABLES}
    report["flyway_versions"] = scalar(candidate, "SELECT string_agg(version,',' ORDER BY installed_rank) FROM public.flyway_schema_history;")


if __name__ == "__main__":
    main()
