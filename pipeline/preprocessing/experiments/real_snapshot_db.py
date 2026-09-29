r"""Create an isolated local PostgreSQL/MinIO target for the 2026-09-14 test.

This helper deliberately uses names and loopback ports that are unrelated to the
normal Pickage compose stack.  It never connects to the production tunnel.

Examples (PowerShell):
  py C:\pg914\db_setup.py setup --repo C:\Users\SSAFY\workspace\S15P21A506-raw-to-curated-pipeline
  py C:\pg914\db_setup.py status
  py C:\pg914\db_setup.py run --repo ... --bundle-prefix ... --manifest-sha256 ...
  py C:\pg914\db_setup.py assert-published
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

PG_CONTAINER = "pickage-real914-pg"
MINIO_CONTAINER = "pickage-real914-minio"
PG_PORT = 15441
MINIO_PORT = 19030
MINIO_CONSOLE_PORT = 19031
DB = "pickage"
USER = "pickage"
PASSWORD = "real914-local-only"
MINIO_ACCESS = "real914-local"
MINIO_SECRET = "real914-local-only"
MINIO_IMAGE = "quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"

DEFAULT_REPO = Path(r"C:\Users\SSAFY\workspace\S15P21A506-raw-to-curated-pipeline")
RUN_DIR = Path(r"C:\pg914\run")
DEFAULT_WORK = RUN_DIR / "loader-work"
FROZEN_JAR = Path(r"C:\pg914\curated-loader.jar")
JAVA21 = Path(r"C:\Users\SSAFY\.gradle\jdks\eclipse_adoptium-21-amd64-windows.2\bin\java.exe")


def configure(root: Path, endpoint: str) -> None:
    global RUN_DIR, FROZEN_JAR, MINIO_PORT, MINIO_CONSOLE_PORT, MINIO_CONTAINER
    if endpoint not in ('http://127.0.0.1:19030', 'http://127.0.0.1:19040', 'http://127.0.0.1:19050'):
        raise ValueError('Only dedicated local experiment MinIO endpoints are allowed')
    RUN_DIR = Path(root).resolve() / 'run'
    FROZEN_JAR = Path(root).resolve() / 'curated-loader.jar'
    MINIO_PORT = int(endpoint.rsplit(':', 1)[1])
    MINIO_CONSOLE_PORT = MINIO_PORT + 1
    MINIO_CONTAINER = {19030: 'pickage-real914-minio', 19040: 'pickage-real914r2-minio',
                       19050: 'pickage-real914r3-minio'}[MINIO_PORT]


def run(command: list[str], *, input_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, input=input_bytes, check=check, capture_output=True)


def output(result: subprocess.CompletedProcess) -> str:
    return (result.stdout or b"").decode(errors="replace") + (result.stderr or b"").decode(errors="replace")


def container_exists(name: str) -> bool:
    return run(["docker", "inspect", name], check=False).returncode == 0


def start_postgres() -> None:
    if not container_exists(PG_CONTAINER):
        run([
            "docker", "run", "-d", "--name", PG_CONTAINER,
            "-e", f"POSTGRES_DB={DB}", "-e", f"POSTGRES_USER={USER}",
            "-e", f"POSTGRES_PASSWORD={PASSWORD}",
            "-p", f"127.0.0.1:{PG_PORT}:5432",
            "--tmpfs", "/run", "--tmpfs", "/tmp",
            "postgres:16",
        ])
    else:
        run(["docker", "start", PG_CONTAINER], check=False)
    deadline = time.time() + 90
    while time.time() < deadline:
        probe = run(["docker", "exec", PG_CONTAINER, "pg_isready", "-U", USER, "-d", DB], check=False)
        if probe.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError("isolated PostgreSQL did not become ready")


def start_minio() -> None:
    if not container_exists(MINIO_CONTAINER):
        run([
            "docker", "run", "-d", "--name", MINIO_CONTAINER,
            "-e", f"MINIO_ROOT_USER={MINIO_ACCESS}",
            "-e", f"MINIO_ROOT_PASSWORD={MINIO_SECRET}",
            "-p", f"127.0.0.1:{MINIO_PORT}:9000",
            "-p", f"127.0.0.1:{MINIO_CONSOLE_PORT}:9001",
            MINIO_IMAGE, "server", "/data", "--console-address", ":9001",
        ])
    else:
        run(["docker", "start", MINIO_CONTAINER], check=False)
    deadline = time.time() + 90
    while time.time() < deadline:
        probe = run(["docker", "exec", MINIO_CONTAINER, "mc", "ready", "local"], check=False)
        if probe.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError("isolated MinIO did not become ready")
    run(["docker", "exec", MINIO_CONTAINER, "mc", "alias", "set", "local", "http://127.0.0.1:9000", MINIO_ACCESS, MINIO_SECRET])
    run(["docker", "exec", MINIO_CONTAINER, "mc", "mb", "--ignore-existing", "local/pickage-curated"])


def apply_migrations(repo: Path) -> None:
    migration_dir = repo / "backend" / "src" / "main" / "resources" / "db" / "migration"
    files = sorted(migration_dir.glob("V*__*.sql"), key=lambda p: int(p.name.split("__", 1)[0][1:]))
    if not files:
        raise RuntimeError(f"no migrations found under {migration_dir}")
    # This target is disposable and freshly created. Applying the repository's
    # ordered SQL files directly keeps the helper independent of API startup.
    for path in files:
        data = path.read_bytes()
        result = run(["docker", "exec", "-i", PG_CONTAINER, "psql", "-v", "ON_ERROR_STOP=1", "-U", USER, "-d", DB], input_bytes=data, check=False)
        if result.returncode:
            raise RuntimeError(f"migration failed: {path.name}\n{output(result)}")


def build_jar(repo: Path) -> Path:
    gradle = repo / "backend" / "gradlew.bat"
    result = subprocess.run([str(gradle), "curatedBootJar"], cwd=repo / "backend", capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(output(result))
    jar = repo / "backend" / "build" / "curated-loader" / "curated-loader.jar"
    if not jar.exists():
        raise RuntimeError(f"loader jar not found: {jar}")
    return jar


def freeze_jar(repo: Path) -> Path:
    source = build_jar(repo)
    FROZEN_JAR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, FROZEN_JAR)
    return FROZEN_JAR


def setup(repo: Path, build: bool) -> None:
    start_postgres()
    start_minio()
    # This helper applies the repository SQL directly (without Flyway's
    # history table), so use the V8 staging table as the idempotence marker.
    probe = run(["docker", "exec", PG_CONTAINER, "psql", "-At", "-U", USER, "-d", DB, "-c", "SELECT to_regclass('public.etl_curated_stage_package')"], check=False)
    if not probe.stdout.strip() or probe.stdout.strip() == b"null":
        apply_migrations(repo)
    if build:
        freeze_jar(repo)
    print(json.dumps({
        "postgres": {"container": PG_CONTAINER, "jdbc_url": f"jdbc:postgresql://127.0.0.1:{PG_PORT}/{DB}", "user": USER},
        "minio": {"container": MINIO_CONTAINER, "endpoint": f"http://127.0.0.1:{MINIO_PORT}", "bucket": "pickage-curated", "access_key": MINIO_ACCESS},
        "migration": "applied-or-already-present",
        "jar": str(FROZEN_JAR),
    }, ensure_ascii=False, indent=2))


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def snapshot_from_prefix(prefix: str) -> str:
    match = re.search(r"(?:^|/)snapshot=(\d{4}-\d{2}-\d{2})(?:/|$)", prefix)
    if not match:
        raise ValueError("bundle prefix must contain snapshot=YYYY-MM-DD")
    return match.group(1)


def db_verification(prefix: str, manifest_sha: str, snapshot: str) -> dict:
    exact = sql(
        "SELECT COALESCE(json_agg(x), '[]'::json)::text FROM ("
        "SELECT execution_id,dataset,status,snapshot_at,run_prefix,manifest_sha256,updated_at "
        "FROM etl_load_execution WHERE dataset='curated-bundle' AND run_prefix="
        + sql_literal(prefix) + " AND manifest_sha256=" + sql_literal(manifest_sha)
        + " ORDER BY updated_at DESC) x"
    )
    execution_rows = json.loads(exact or "[]")
    counts = sql(
        "SELECT json_build_object("
        "'package',(SELECT count(*) FROM package),"
        "'version',(SELECT count(*) FROM version),"
        "'package_snapshot',(SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE " + sql_literal(snapshot) + "),"
        "'package_version_snapshot',(SELECT count(*) FROM package_version_snapshot WHERE snapshot_at=DATE " + sql_literal(snapshot) + "),"
        "'version_snapshot_null_dependents',(SELECT count(*) FROM package_version_snapshot WHERE snapshot_at=DATE " + sql_literal(snapshot) + " AND dependents_count IS NULL),"
        "'version_snapshot_zero_dependents',(SELECT count(*) FROM package_version_snapshot WHERE snapshot_at=DATE " + sql_literal(snapshot) + " AND dependents_count=0)"
        ")::text"
    )
    matching_published = [row for row in execution_rows if row.get("status") == "PUBLISHED"]
    return {"matching_executions": execution_rows, "matching_published": bool(matching_published), "counts": json.loads(counts or "{}")}


def load(repo: Path, prefix: str, manifest_sha: str, label: str, mode: str = "once") -> dict:
    """Run the frozen loader and return a verified, JSON-serializable result."""
    if not FROZEN_JAR.exists():
        freeze_jar(repo)
    start_postgres()
    start_minio()
    snapshot = snapshot_from_prefix(prefix)
    work_dir = RUN_DIR / f"db-{label}"
    log_path = RUN_DIR.parent / f"db-{label}.log"
    work_dir.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    props = RUN_DIR / f"curated-load-{label}.properties"
    props.write_text("\n".join([
        "pickage.curated-load.enabled=true",
        f"pickage.curated-load.mode={mode}",
        f"pickage.curated-load.jdbc-url=jdbc:postgresql://127.0.0.1:{PG_PORT}/{DB}?currentSchema=public",
        f"pickage.curated-load.db-user={USER}",
        f"pickage.curated-load.db-password={PASSWORD}",
        f"pickage.curated-load.s3-endpoint=http://127.0.0.1:{MINIO_PORT}",
        f"pickage.curated-load.s3-access-key={MINIO_ACCESS}",
        f"pickage.curated-load.s3-secret-key={MINIO_SECRET}",
        f"pickage.curated-load.work-dir={work_dir.as_posix()}",
        f"pickage.curated-load.bundle-prefix={prefix}",
        f"pickage.curated-load.manifest-sha256={manifest_sha}",
    ]) + "\n", encoding="utf-8")
    java = JAVA21 if JAVA21.exists() else Path(os.environ.get("JAVA21", "java"))
    started = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(java), "-Xmx512m", "-jar", str(FROZEN_JAR), "--spring.config.additional-location=file:" + props.as_posix()],
            cwd=repo, stdout=log, stderr=subprocess.STDOUT,
        )
        return_code = process.wait()
    last_run_path = work_dir / "last-run.json"
    last_run = json.loads(last_run_path.read_text(encoding="utf-8")) if last_run_path.exists() else {}
    process_status = last_run.get("status")
    verification = db_verification(prefix, manifest_sha, snapshot)
    status = process_status if process_status in {"PUBLISHED", "SKIPPED"} else "UNVERIFIED"
    result = {
        "label": label, "snapshot": snapshot, "prefix": prefix, "manifest_sha256": manifest_sha,
        "return_code": return_code, "status": status, "last_run": last_run, "log": str(log_path),
        "work_dir": str(work_dir), "elapsed_seconds": round(time.time() - started, 3),
        "verification": verification,
    }
    if return_code != 0 or status not in {"PUBLISHED", "SKIPPED"} or not verification["matching_published"]:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def run_loader(repo: Path, prefix: str, manifest_sha: str, mode: str, work_dir: Path) -> int:
    # Kept as a compatibility CLI entry point; the named load() API is the
    # orchestrator-facing interface and owns the durable per-label paths.
    result = load(repo, prefix, manifest_sha, "manual", mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def sql(query: str) -> str:
    result = run(["docker", "exec", PG_CONTAINER, "psql", "-At", "-F", "\t", "-U", USER, "-d", DB, "-c", query], check=False)
    if result.returncode:
        raise RuntimeError(output(result))
    return result.stdout.decode(errors="replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["setup", "build", "run", "load", "status", "assert-published"])
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--bundle-prefix")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--label")
    parser.add_argument("--mode", choices=["once", "adopt-baseline"], default="once")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    args = parser.parse_args()
    if args.command == "setup":
        setup(args.repo, build=True)
    elif args.command == "build":
        print(build_jar(args.repo))
    elif args.command == "run":
        if not args.bundle_prefix or not args.manifest_sha256:
            parser.error("run requires --bundle-prefix and --manifest-sha256")
        raise SystemExit(run_loader(args.repo, args.bundle_prefix, args.manifest_sha256, args.mode, args.work_dir))
    elif args.command == "load":
        if not args.bundle_prefix or not args.manifest_sha256:
            parser.error("load requires --bundle-prefix and --manifest-sha256")
        label = getattr(args, "label", None) or "manual"
        print(json.dumps(load(args.repo, args.bundle_prefix, args.manifest_sha256, label, args.mode), ensure_ascii=False, indent=2))
    elif args.command == "status":
        print(sql("SELECT execution_id, dataset, status, snapshot_at, updated_at FROM etl_load_execution ORDER BY updated_at DESC LIMIT 20"))
    elif args.command == "assert-published":
        row = sql("SELECT status || E'\\t' || execution_id FROM etl_load_execution ORDER BY updated_at DESC LIMIT 1")
        if not row or not row.split("\t", 1)[0] == "PUBLISHED":
            raise SystemExit(f"last execution is not PUBLISHED: {row or '<none>'}")
        print(row)
    return 0


if __name__ == "__main__":
    main()
