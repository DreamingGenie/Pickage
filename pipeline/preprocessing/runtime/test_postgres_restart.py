"""Fresh-fixture regression for offline WAL import followed by same-container restart."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path


LABEL = "pickage.bounded.fixture"


def run(*args: str, check: bool = True, input: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, input=input, capture_output=True, check=check, timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--bytes", type=int, default=536870912,
                        help="Fresh fixture WAL/staging image size; at most the 17GB production cap")
    parser.add_argument("--check-collation-rejection", action="store_true",
                        help="Inject a mismatch into this disposable fixture and require startup refusal")
    args = parser.parse_args()
    if not 67108864 <= args.bytes <= 17_000_000_000:
        parser.error("--bytes must be between 64MiB and 17GB")
    suffix = uuid.uuid4().hex[:12]
    source_volume = f"pickage-fixture-pg-data-{suffix}"
    wal_volume = f"pickage-fixture-pg-wal-{suffix}"
    source_container = f"pickage-fixture-source-{suffix}"
    bounded_container = f"pickage-fixture-bounded-{suffix}"
    resources = [("container", source_container), ("container", bounded_container),
                 ("volume", source_volume), ("volume", wal_volume)]
    label_value = f"postgres-restart-{suffix}"
    label = f"{LABEL}={label_value}"
    backing_inode = None
    try:
        run("docker", "volume", "create", "--label", label, source_volume)
        run("docker", "volume", "create", "--label", label, wal_volume)
        # A legacy-sized file must be rejected without formatting or mounting.
        # This sparse sentinel contains no user data and belongs to this fixture.
        run("docker", "run", "--rm", "--entrypoint", "sh",
            "-v", f"{wal_volume}:/owned", args.image, "-c",
            "printf '2d3f4f5e-95d0-4ebd-9c5b-3b8a4e3d4f12\\n' > /owned/OWNER_UUID; "
            "printf legacy-sentinel > /owned/wal-staging.ext4; truncate -s 40000000000 /owned/wal-staging.ext4")
        refused = run("docker", "run", "--name", bounded_container, "--label", label,
                      "--privileged", "--read-only", "--tmpfs", "/run:size=16m", "--tmpfs", "/tmp:size=16m",
                      "-v", f"{wal_volume}:/var/lib/pickage-postgres-bounded", args.image, check=False)
        if refused.returncode == 0 or "image size differs; refusing format" not in refused.stderr:
            raise AssertionError("legacy-sized image was not rejected before format")
        sentinel = run("docker", "run", "--rm", "--entrypoint", "sh",
                       "-v", f"{wal_volume}:/owned:ro", args.image, "-c",
                       "stat -c %s /owned/wal-staging.ext4; head -c 15 /owned/wal-staging.ext4").stdout
        if sentinel != "40000000000\nlegacy-sentinel":
            raise AssertionError("rejected legacy image was changed")
        run("docker", "rm", bounded_container)
        run("docker", "run", "--rm", "--entrypoint", "sh",
            "-v", f"{wal_volume}:/owned", args.image, "-c", "rm -- /owned/wal-staging.ext4")
        run("docker", "run", "-d", "--name", source_container, "--label", label,
            "-e", "POSTGRES_PASSWORD=fixture-only",
            "-v", f"{source_volume}:/var/lib/postgresql/data",
            "--entrypoint", "/usr/local/bin/docker-entrypoint.sh", args.image, "postgres")
        run("docker", "exec", source_container, "sh", "-c",
            "until pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; do sleep 1; done")
        run("docker", "exec", "-u", "postgres", source_container, "psql", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", "-c",
            "CREATE TABLE import_marker(id int primary key, note text); "
            "INSERT INTO import_marker VALUES (1, 'restart-regression');")
        run("docker", "stop", "-t", "15", source_container)
        run("docker", "rm", source_container)
        run("docker", "run", "-d", "--name", bounded_container, "--label", label,
            "--privileged", "--memory=2g", "--memory-swap=2g",
            "-e", "POSTGRES_IMPORT_MODE=offline",
            "-e", f"BOUNDED_POSTGRES_BYTES={args.bytes}",
            "-e", "POSTGRES_PASSWORD=fixture-only",
            "-v", f"{wal_volume}:/var/lib/pickage-postgres-bounded",
            "-v", f"{source_volume}:/var/lib/postgresql/data", args.image)
        run("docker", "exec", bounded_container, "sh", "-c",
            "until pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; do sleep 1; done")
        first = run("docker", "exec", "-u", "postgres", bounded_container,
                    "psql", "-At", "-d", "postgres", "-c", "SELECT id||'|'||note FROM import_marker").stdout.strip()
        run("docker", "exec", bounded_container, "sh", "-c",
            "until test -f /run/pickage-postgres-ready; do sleep 1; done")
        device = run("docker", "exec", bounded_container, "findmnt", "-rn", "-M",
                      "/run/pickage-postgres-bounded", "-o", "SOURCE").stdout.strip()
        image_size = run("docker", "exec", bounded_container, "stat", "-c", "%s",
                         "/var/lib/pickage-postgres-bounded/wal-staging.ext4").stdout.strip()
        if image_size != str(args.bytes):
            raise AssertionError(f"bounded image size differs: {image_size!r}")
        association = json.loads(run("docker", "exec", bounded_container, "losetup", "-J", "-l",
                                     "-O", "NAME,BACK-INO,AUTOCLEAR", device).stdout)["loopdevices"]
        if len(association) != 1 or association[0]["autoclear"] is not True:
            raise AssertionError(f"bounded loop must autoclear: {association}")
        backing_inode = association[0]["back-ino"]
        run("docker", "exec", bounded_container, "sh", "-c",
            "test -L /var/lib/postgresql/data/pg_wal && "
            "test \"$(readlink -f /var/lib/postgresql/data/pg_wal)\" = /run/pickage-postgres-bounded/wal")
        run("docker", "exec", "-u", "postgres", bounded_container,
            "psql", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", "CHECKPOINT")
        run("docker", "restart", bounded_container)
        run("docker", "exec", bounded_container, "sh", "-c",
            "until pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; do sleep 1; done")
        second = run("docker", "exec", "-u", "postgres", bounded_container,
                     "psql", "-At", "-d", "postgres", "-c", "SELECT id||'|'||note FROM import_marker").stdout.strip()
        run("docker", "exec", bounded_container, "sh", "-c",
            "until test -f /run/pickage-postgres-ready; do sleep 1; done")
        if first != "1|restart-regression" or second != first:
            raise AssertionError(f"row was not preserved: first={first!r} second={second!r}")
        ddl = "".join(
            f"CREATE TABLE {name}(id int primary key);\n"
            for name in ("etl_curated_stage_package", "etl_curated_stage_version",
                         "etl_curated_stage_package_snapshot", "etl_curated_stage_version_snapshot")
        )
        run("docker", "exec", "-i", "-u", "postgres", bounded_container, "psql", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", input=ddl)
        run("docker", "exec", "-u", "postgres", bounded_container, "psql", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", "-c", "INSERT INTO etl_curated_stage_package VALUES (1)")
        configure = Path(__file__).with_name("configure_bounded_staging.sql").read_text(encoding="utf-8")
        occupied = run("docker", "exec", "-i", "-u", "postgres", bounded_container, "psql", "-d", "postgres",
                       "-v", "ON_ERROR_STOP=1", input=configure, check=False)
        if occupied.returncode == 0:
            raise AssertionError("occupied staging was accepted")
        run("docker", "exec", "-u", "postgres", bounded_container, "psql", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", "-c", "TRUNCATE etl_curated_stage_package")
        run("docker", "exec", "-i", "-u", "postgres", bounded_container, "psql", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", input=configure)
        settings = run("docker", "exec", "-u", "postgres", bounded_container, "psql", "-At", "-d", "postgres",
                       "-c", "SELECT (SELECT spcname FROM pg_tablespace WHERE spcname='curated_work'),"
                             "current_setting('temp_tablespaces'), current_setting('temp_file_limit')").stdout.strip()
        if "curated_work|curated_work|8GB" not in settings:
            raise AssertionError(f"bounded staging settings missing: {settings!r}")
        placements = run("docker", "exec", "-u", "postgres", bounded_container,
                         "psql", "-At", "-d", "postgres", "-c",
                         "SELECT count(*) FROM pg_class c JOIN pg_tablespace s ON s.oid=c.reltablespace "
                         "WHERE c.relnamespace='public'::regnamespace "
                         "AND c.relname LIKE 'etl_curated_stage_%' AND c.relkind IN ('r','i') "
                         "AND s.spcname='curated_work'").stdout.strip()
        if placements != "8":
            raise AssertionError(f"four staging tables and primary indexes must be bounded: {placements}")
        if args.check_collation_rejection:
            run("docker", "exec", "-u", "postgres", bounded_container, "psql", "-d", "postgres",
                "-v", "ON_ERROR_STOP=1", "-c",
                "UPDATE pg_database SET datcollversion='fixture-incompatible' WHERE datname='postgres'")
            run("docker", "restart", "-t", "15", bounded_container)
            exit_code = run("docker", "wait", bounded_container).stdout.strip()
            logs = run("docker", "logs", bounded_container)
            if exit_code != "2" or "database collation differs from runtime" not in logs.stderr:
                raise AssertionError(f"collation mismatch was not rejected: exit={exit_code}")
        print(json.dumps({"status": "PASS", "image": args.image, "image_size_bytes": int(image_size), "first_row": first,
                          "restart_row": second, "wal_target": "/run/pickage-postgres-bounded/wal",
                          "staging_settings": settings, "bounded_relations": int(placements),
                          "loop_autoclear": True, "loop_backing_inode": backing_inode,
                          "fixture_suffix": suffix,
                          "legacy_image_rejected_unchanged": True,
                          "collation_mismatch_rejected": args.check_collation_rejection}, sort_keys=True))
        return 0
    except Exception:
        for name in (source_container, bounded_container):
            evidence = run("docker", "inspect", name, "--format", "{{json .State}}", check=False)
            if evidence.returncode == 0:
                print(f"FIXTURE_STATE {name} {evidence.stdout.strip()}", file=sys.stderr)
                logs = run("docker", "logs", "--tail", "40", name, check=False)
                print(logs.stdout + logs.stderr, file=sys.stderr)
        raise
    finally:
        for kind, name in resources:
            inspect = run("docker", kind, "inspect", name, check=False)
            if inspect.returncode == 0:
                label_path = ".Config.Labels" if kind == "container" else ".Labels"
                owner = run("docker", kind, "inspect", name, "--format",
                            "{{index " + label_path + " \"pickage.bounded.fixture\"}}",
                            check=False)
                if owner.returncode != 0 or owner.stdout.strip() != label_value:
                    raise RuntimeError(f"refusing cleanup of unowned fixture resource: {kind}/{name}")
        run("docker", "rm", "-f", bounded_container, check=False)
        run("docker", "rm", "-f", source_container, check=False)
        if backing_inode is not None:
            loops = json.loads(run("docker", "run", "--rm", "--privileged", "--entrypoint", "losetup",
                                   args.image, "-J", "-l", "-O", "NAME,BACK-INO,AUTOCLEAR").stdout)["loopdevices"]
            if any(row["back-ino"] == backing_inode for row in loops):
                raise AssertionError("fixture loop survived forced container removal; volumes retained")
            print("FORCED_REMOVAL_LOOP_RELEASED", backing_inode)
        run("docker", "volume", "rm", wal_volume, check=False)
        run("docker", "volume", "rm", source_volume, check=False)


if __name__ == "__main__":
    sys.exit(main())
