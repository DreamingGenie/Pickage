"""Local-only integration tests for V7 constraint-name normalization.

Requires Docker, Java 17+, and PICKAGE_341_JAVA_CLASSPATH with the existing
application Flyway/JDBC runtime jars. Creates one uniquely named loopback-only
PostgreSQL 16 container and removes only that container on exit. Never uses a
source or server database.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "backend/src/main/resources/db/migration"
V6 = MIGRATIONS / "V6__partition_package_version_snapshot.sql"
V7 = MIGRATIONS / "V7__normalize_package_version_snapshot_constraints.sql"
EXPECTED_NAMES = {
    "p": "pk_package_version_snapshot",
    "f:version": "fk_version_package_version_snapshot",
    "f:snapshot": "fk_snapshot_package_version_snapshot",
    "c": "ck_package_version_snapshot_dependents_nonnegative",
}


def run(args, *, stdin=None, expected=True, env=None):
    result = subprocess.run([str(arg) for arg in args], input=stdin, capture_output=True, env=env)
    if expected and result.returncode:
        raise RuntimeError(f"Command failed ({args[0]}): {result.stderr.decode('utf-8', 'replace')[-5000:]}")
    if not expected and not result.returncode:
        raise AssertionError(f"Unexpected success: {args[0]}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="postgres:16-alpine")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    classpath = os.environ.get("PICKAGE_341_JAVA_CLASSPATH")
    if not classpath:
        raise RuntimeError("PICKAGE_341_JAVA_CLASSPATH must point to application runtime jars")
    if not V7.is_file():
        raise RuntimeError(f"V7 migration not found: {V7}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex[:12]
    container = "pickage-341-constraint-" + run_id
    report = {"run_id": run_id, "scope": "local V7 constraint-name integration tests",
              "server_executed": False, "checks": [], "status": "RUNNING"}
    created = False

    def check(name):
        report["checks"].append(name)
        print("PASS " + name, flush=True)

    try:
        run(["docker", "run", "-d", "--name", container, "--label", "pickage.task=341-constraint-test",
             "--memory=2g", "--shm-size=256m", "-p", "127.0.0.1::5432",
             "-e", "POSTGRES_HOST_AUTH_METHOD=trust", args.image])
        created = True
        for _ in range(90):
            ready = subprocess.run(["docker", "exec", container, "pg_isready", "-U", "postgres"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Test PostgreSQL not ready")
        port = run(["docker", "port", container, "5432/tcp"]).stdout.decode().strip().rsplit(":", 1)[1]
        report.update(container=container, port=port)

        def sql(database, statement, *, expected=True):
            return run(["docker", "exec", "-i", container, "psql", "-X", "-U", "postgres", "-d", database,
                        "-v", "ON_ERROR_STOP=1", "-At"], stdin=statement.encode(), expected=expected).stdout.decode().strip()

        def flyway(database, target="latest", action="migrate", *, expected=True):
            env = os.environ.copy()
            env["PICKAGE_341_TEST_JDBC_URL"] = f"jdbc:postgresql://127.0.0.1:{port}/{database}"
            result = run(["java", "--class-path", classpath, HERE / "LocalFlyway.java", action, MIGRATIONS, target],
                         expected=expected, env=env)
            with (output / "flyway.log").open("ab") as log:
                log.write(result.stdout + result.stderr)
            return result

        def database(suffix, target="1"):
            name = f"pickage_import_341_{run_id}_{suffix}"
            sql("postgres", f'CREATE DATABASE "{name}";')
            flyway(name, target)
            return name

        def root_names(db):
            return sql(db, """
                SELECT contype::text || CASE WHEN contype='f' THEN ':' || confrelid::regclass::text ELSE '' END || '=' || conname
                FROM pg_constraint WHERE conrelid='public.package_version_snapshot'::regclass
                ORDER BY contype, confrelid::regclass::text NULLS FIRST;
            """).splitlines()

        def assert_names(db):
            got = set(root_names(db))
            got_fk = {line.split("=", 1)[1] for line in got if line.startswith("f:")}
            wanted_fk = {EXPECTED_NAMES["f:version"], EXPECTED_NAMES["f:snapshot"]}
            assert "p=" + EXPECTED_NAMES["p"] in got, got
            assert "c=" + EXPECTED_NAMES["c"] in got, got
            assert got_fk == wanted_fk, got
            assert len(got) == 4, got

        def seed_populated_partitioned(db, *, names="historical"):
            # Start from the immutable V1 schema, then model the production dump's
            # partitioned parent and two data-bearing daily leaves.
            pk, version_fk, snapshot_fk, check_name = (
                ("package_version_snapshot_pkey", "version_fk", "snapshot_fk", "dependents_nonnegative")
                if names == "historical" else
                ('"PK_PACKAGE_VERSION_SNAPSHOT"', '"FK_VERSION_PACKAGE_VERSION_SNAPSHOT"',
                 '"FK_SNAPSHOT_PACKAGE_VERSION_SNAPSHOT"', '"CK_PACKAGE_VERSION_SNAPSHOT_DEPENDENTS_NONNEGATIVE"')
            )
            sql(db, f"""
                INSERT INTO public."package"(package_id,name) VALUES (1,'fixture');
                INSERT INTO public."version"(package_id,version) VALUES (1,'1.0.0');
                INSERT INTO public."snapshot"(snapshot_at) VALUES ('2026-08-24'),('2026-08-31');
                DROP TABLE public.package_version_snapshot;
                CREATE TABLE public.package_version_snapshot (
                    package_id int NOT NULL, version varchar(100) NOT NULL,
                    snapshot_at date NOT NULL, dependents_count int NOT NULL DEFAULT 0,
                    CONSTRAINT {pk} PRIMARY KEY(package_id,version,snapshot_at),
                    CONSTRAINT {version_fk} FOREIGN KEY(package_id,version) REFERENCES public.version(package_id,version),
                    CONSTRAINT {snapshot_fk} FOREIGN KEY(snapshot_at) REFERENCES public.snapshot(snapshot_at),
                    CONSTRAINT {check_name} CHECK(dependents_count >= 0)
                ) PARTITION BY RANGE(snapshot_at);
                CREATE SCHEMA vd193_reload_20260912_ready01;
                CREATE TABLE vd193_reload_20260912_ready01.d20260824 PARTITION OF public.package_version_snapshot
                    FOR VALUES FROM ('2026-08-24') TO ('2026-08-25');
                CREATE TABLE vd193_reload_20260912_ready01.d20260831 PARTITION OF public.package_version_snapshot
                    FOR VALUES FROM ('2026-08-31') TO ('2026-09-01');
                INSERT INTO public.package_version_snapshot VALUES
                    (1,'1.0.0','2026-08-24',17),(1,'1.0.0','2026-08-31',23);
            """)

        def inventory(db):
            # Stable physical identity plus complete constraint definitions and
            # validity/inheritance flags prove a rename did not rebuild data.
            return sql(db, """
                SELECT jsonb_build_object(
                  'tables', (SELECT jsonb_agg(jsonb_build_array(c.oid::text,c.relname,c.relfilenode::text) ORDER BY c.oid)
                    FROM pg_class c WHERE c.oid='public.package_version_snapshot'::regclass
                       OR c.oid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent='public.package_version_snapshot'::regclass)),
                  'indexes', (SELECT jsonb_agg(jsonb_build_array(i.indexrelid::text,ic.relname,ic.relfilenode::text) ORDER BY i.indexrelid)
                    FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
                    WHERE i.indrelid='public.package_version_snapshot'::regclass
                       OR i.indrelid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent='public.package_version_snapshot'::regclass)),
                  'constraints', (SELECT jsonb_agg(jsonb_build_array(c.conrelid::regclass::text,c.conname,
                    pg_get_constraintdef(c.oid),c.convalidated::text,c.conislocal::text,c.coninhcount::text,
                    c.oid::text,c.conparentid::text)
                    ORDER BY c.conrelid,c.contype,c.conname) FROM pg_constraint c
                    WHERE c.conrelid='public.package_version_snapshot'::regclass
                       OR c.conrelid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent='public.package_version_snapshot'::regclass)),
                  'inheritance_count', (SELECT count(*)::text FROM pg_inherits WHERE inhparent='public.package_version_snapshot'::regclass),
                  'rows', (SELECT jsonb_agg(jsonb_build_array(package_id::text,version,snapshot_at::text,dependents_count::text)
                    ORDER BY package_id,version,snapshot_at) FROM public.package_version_snapshot)
                )::text;
            """)

        def test_historical_populated():
            for suffix, source_names in (("historical", "historical"), ("capital_history", "capital")):
                db = database(suffix)
                seed_populated_partitioned(db, names=source_names)
                # Bring every database to the identical pre-V7 state first. V2-V6
                # add the regular schema objects, including V4's secondary index.
                flyway(db, "6")
                before = inventory(db)
                flyway(db)
                assert_names(db)
                after = inventory(db)
                old, new = json.loads(before), json.loads(after)
                for field in ("tables", "inheritance_count", "rows"):
                    assert old[field] == new[field], f"V7 changed {field}: {old[field]} != {new[field]}"
                old_index_ids = sorted((row[0], row[2]) for row in old["indexes"])
                new_index_ids = sorted((row[0], row[2]) for row in new["indexes"])
                assert old_index_ids == new_index_ids, (old_index_ids, new_index_ids)
                # Constraint definitions and validated states must be retained; names
                # change only for the four parent constraints and inherited CHECKs.
                old_defs = sorted((row[0], row[2], row[3], row[4], row[5], row[6], row[7]) for row in old["constraints"])
                new_defs = sorted((row[0], row[2], row[3], row[4], row[5], row[6], row[7]) for row in new["constraints"])
                assert old_defs == new_defs, (old_defs, new_defs)
                child_checks = [row for row in new["constraints"] if row[0].startswith("vd193_reload") and "CHECK" in row[2]]
                assert child_checks and all(row[1] == EXPECTED_NAMES["c"] for row in child_checks), child_checks
                # Applying the SQL a second time is a no-op and preserves the same identities.
                sql(db, V7.read_text(encoding="utf-8"))
                assert inventory(db) == after
                flyway(db, action="validate")
            check("historical and capitalized names normalized; populated rows, object identities, definitions and validation preserved; direct rerun is a no-op")

        def test_capitalized_fresh_path():
            db = database("capital")
            # V1 creates quoted uppercase constraint names; V6 converts the empty
            # table to a partitioned parent, then V7 normalizes that path as well.
            flyway(db, "6")
            before = inventory(db)
            flyway(db)
            assert_names(db)
            after = inventory(db)
            old, new = json.loads(before), json.loads(after)
            assert old["tables"] == new["tables"]
            assert old["indexes"] == new["indexes"]
            assert old["inheritance_count"] == new["inheritance_count"] == "0"
            assert old["rows"] == new["rows"] is None
            # This documents issue 4's explicit caller responsibility: parent-only
            # INSERT fails, then succeeds once the requested day is created.
            sql(db, "INSERT INTO public.package VALUES(1,'fixture',NULL); INSERT INTO public.version(package_id,version) VALUES(1,'1.0.0'); INSERT INTO public.snapshot VALUES('2026-08-31');")
            sql(db, "INSERT INTO public.package_version_snapshot VALUES(1,'1.0.0','2026-08-31',7);", expected=False)
            sql(db, "CREATE SCHEMA vd193_reload_20260912_ready01; CREATE TABLE vd193_reload_20260912_ready01.d20260831 PARTITION OF public.package_version_snapshot FOR VALUES FROM ('2026-08-31') TO ('2026-09-01'); INSERT INTO public.package_version_snapshot VALUES(1,'1.0.0','2026-08-31',7);")
            assert sql(db, "SELECT dependents_count FROM public.package_version_snapshot;") == "7"
            check("V1 quoted-name and V6 fresh-parent path normalized; insert requires the update process to create the date partition first")

        def test_wrong_definition_collision():
            db = database("collision")
            seed_populated_partitioned(db)
            flyway(db, "6")
            sql(db, "ALTER TABLE public.package_version_snapshot RENAME CONSTRAINT dependents_nonnegative TO fk_version_package_version_snapshot;")
            before = inventory(db)
            result = flyway(db, expected=False)
            assert b"V7" in result.stderr + result.stdout, result.stderr.decode("utf-8", "replace")
            assert inventory(db) == before
            assert sql(db, "SELECT count(*) FROM public.flyway_schema_history WHERE version='7' AND success;") == "0"
            check("wrong-definition target-name collision refused atomically")

        def test_unrelated_index_collision():
            db = database("indexcollision")
            seed_populated_partitioned(db)
            flyway(db, "6")
            sql(db, "CREATE TABLE public.unrelated(id int); CREATE INDEX pk_package_version_snapshot ON public.unrelated(id);")
            before = inventory(db)
            result = flyway(db, expected=False)
            assert b"V7" in result.stderr + result.stdout, result.stderr.decode("utf-8", "replace")
            assert inventory(db) == before
            assert sql(db, "SELECT count(*) FROM public.flyway_schema_history WHERE version='7' AND success;") == "0"
            check("unrelated public index name collision refused atomically")

        def test_late_child_check_collision_rolls_back_renames():
            db = database("latecollision")
            seed_populated_partitioned(db)
            flyway(db, "6")
            sql(db, "ALTER TABLE vd193_reload_20260912_ready01.d20260824 ADD CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK (dependents_count < 1000);")
            before = inventory(db)
            result = flyway(db, expected=False)
            assert b"V7" in result.stderr + result.stdout, result.stderr.decode("utf-8", "replace")
            assert inventory(db) == before
            assert sql(db, "SELECT count(*) FROM public.flyway_schema_history WHERE version='7' AND success;") == "0"
            check("late inherited child CHECK name collision rolled back earlier parent constraint renames")

        def test_missing_or_malformed_expected_constraint():
            for suffix, mutation in (
                ("missing", "ALTER TABLE public.package_version_snapshot DROP CONSTRAINT version_fk;"),
                ("malformed", "ALTER TABLE public.package_version_snapshot DROP CONSTRAINT version_fk; ALTER TABLE public.package_version_snapshot ADD CONSTRAINT version_fk FOREIGN KEY(package_id) REFERENCES public.package(package_id);"),
            ):
                db = database(suffix)
                seed_populated_partitioned(db)
                flyway(db, "6")
                sql(db, mutation)
                before = inventory(db)
                result = flyway(db, expected=False)
                assert b"V7" in result.stderr + result.stdout, result.stderr.decode("utf-8", "replace")
                assert inventory(db) == before, suffix
                assert sql(db, "SELECT count(*) FROM public.flyway_schema_history WHERE version='7' AND success;") == "0"
            check("missing and malformed expected FK definitions refused atomically")

        test_historical_populated()
        test_capitalized_fresh_path()
        test_wrong_definition_collision()
        test_unrelated_index_collision()
        test_late_child_check_collision_rolls_back_renames()
        test_missing_or_malformed_expected_constraint()
        report["status"] = "PASS"
    except BaseException as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        raise
    finally:
        if created:
            # Exact unique container created by this invocation; never touch another DB.
            run(["docker", "rm", "-f", "-v", container])
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
