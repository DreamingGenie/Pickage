#!/usr/bin/env python3
"""Prepare a read-only PostgreSQL client beside the isolated local source DB.

The source container is intentionally left untouched.  The helper shares only
its network namespace, so pg_dump can reach a source that has no published
host port.  The archive directory is the helper's only host bind mount.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


LABEL = "pickage.task=341-local-dump-client"
HELPER_PREFIX = "pickage-341-local-dump-client"
DEFAULT_SOURCE = "pickage-267-validation"
DEFAULT_DB = "pickage_267_full_defaulted"
DEFAULT_USER = "postgres"


class DumpClientError(RuntimeError):
    pass


def run(command: Sequence[str], *, env: dict[str, str] | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command), check=False, text=True, capture_output=capture,
            encoding="utf-8", errors="replace", env=env,
        )
    except OSError as exc:
        raise DumpClientError(f"명령을 실행할 수 없습니다: {exc}") from exc


def checked(command: Sequence[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = run(command, env=env)
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise DumpClientError(f"명령이 실패했습니다({result.returncode}): {detail[-500:]}")
    return result


def docker_inspect(container: str) -> dict:
    result = checked(["docker", "inspect", container])
    try:
        values = json.loads(result.stdout)
        return values[0]
    except (ValueError, IndexError, TypeError) as exc:
        raise DumpClientError(f"컨테이너 정보를 읽을 수 없습니다: {container}") from exc


def container_env(info: dict) -> dict[str, str]:
    values = {}
    for item in info.get("Config", {}).get("Env", []):
        if "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def source_details(source: str) -> tuple[str, str, str | None]:
    info = docker_inspect(source)
    if info.get("State", {}).get("Running") is not True:
        raise DumpClientError(f"원본 컨테이너가 실행 중이 아닙니다: {source}")
    if info.get("HostConfig", {}).get("NetworkMode") != "none":
        raise DumpClientError(f"원본 컨테이너의 네트워크 모드가 none이 아닙니다: {source}")
    mounts = info.get("Mounts", [])
    if any(mount.get("Destination") != "/var/lib/postgresql/data" for mount in mounts):
        raise DumpClientError("원본 컨테이너에 예상하지 않은 마운트가 있습니다")
    if len(mounts) != 1:
        raise DumpClientError("원본 컨테이너의 데이터 마운트를 확인할 수 없습니다")
    env = container_env(info)
    user = env.get("POSTGRES_USER", DEFAULT_USER)
    database = env.get("POSTGRES_DB", DEFAULT_DB)
    image = info.get("Config", {}).get("Image")
    if not image:
        raise DumpClientError("원본 이미지가 없습니다")
    # Do not print or return the password. It is passed only through the
    # subprocess environment when the source image requires one.
    password = env.get("POSTGRES_PASSWORD")
    return image, user, password


def source_id(source: str) -> str:
    value = docker_inspect(source).get("Id")
    if not isinstance(value, str) or not value:
        raise DumpClientError(f"원본 컨테이너 ID를 읽을 수 없습니다: {source}")
    return value


def helper_name(source: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in source)
    return f"{HELPER_PREFIX}-{safe}"[:63]


def helper_env(password: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if password is not None:
        env["PGPASSWORD"] = password
    return env


def ensure_archive(path: Path) -> Path:
    resolved = path.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise DumpClientError(f"archive 경로가 디렉터리가 아닙니다: {resolved}")
    return resolved


def inspect_existing(name: str) -> dict | None:
    result = run(["docker", "inspect", name])
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)[0]
    except (ValueError, IndexError, TypeError) as exc:
        raise DumpClientError(f"보조 컨테이너 정보를 읽을 수 없습니다: {name}") from exc


def validate_helper(info: dict, *, source: str, archive: Path | None = None) -> None:
    labels = info.get("Config", {}).get("Labels", {}) or {}
    if labels.get("pickage.task") != "341-local-dump-client" or labels.get("pickage.source") != source:
        raise DumpClientError("보조 컨테이너 라벨이 일치하지 않습니다")
    if info.get("HostConfig", {}).get("NetworkMode") != f"container:{source_id(source)}":
        raise DumpClientError("보조 컨테이너가 원본과 네트워크 네임스페이스를 공유하지 않습니다")
    env = container_env(info)
    if env.get("PGHOST") != "127.0.0.1":
        raise DumpClientError("보조 컨테이너의 PGHOST가 127.0.0.1이 아닙니다")
    binds = [mount for mount in info.get("Mounts", []) if mount.get("Type") == "bind" and mount.get("Destination") == "/work"]
    if len(binds) != 1 or len([mount for mount in info.get("Mounts", []) if mount.get("Type") == "bind"]) != 1:
        raise DumpClientError("보조 컨테이너의 host bind mount 구성이 예상과 다릅니다")
    if archive is not None and Path(binds[0].get("Source", "")).resolve() != archive:
        raise DumpClientError("기존 보조 컨테이너의 archive 마운트가 요청과 다릅니다")


def validate_helper_identity(info: dict, *, source: str) -> None:
    labels = info.get("Config", {}).get("Labels", {}) or {}
    if labels.get("pickage.task") != "341-local-dump-client" or labels.get("pickage.source") != source:
        raise DumpClientError("대상 보조 컨테이너 라벨이 일치하지 않아 제거하지 않습니다")


def start(args: argparse.Namespace) -> dict:
    image, user, password = source_details(args.source_container)
    archive = ensure_archive(args.archive_dir)
    name = helper_name(args.source_container)
    existing = inspect_existing(name)
    if existing is not None:
        validate_helper(existing, source=args.source_container, archive=archive)
        if existing.get("State", {}).get("Running") is not True:
            checked(["docker", "start", name])
        return {"helper": name, "source": args.source_container, "archive": str(archive), "reused": True, "user": user}

    command = [
        "docker", "run", "-d", "--name", name,
        "--label", LABEL,
        "--label", f"pickage.source={args.source_container}",
        "--network", f"container:{args.source_container}",
        "--volume", f"{archive}:/work",
        "--env", "PGPASSWORD",
        "--env", "PGHOST=127.0.0.1",
        "--entrypoint", "sleep", image, "infinity",
    ]
    checked(command, env=helper_env(password))
    return {"helper": name, "source": args.source_container, "archive": str(archive), "reused": False, "user": user}


def probe(args: argparse.Namespace) -> dict:
    image, user, password = source_details(args.source_container)
    name = helper_name(args.source_container)
    info = inspect_existing(name)
    if info is None or info.get("State", {}).get("Running") is not True:
        raise DumpClientError("실행 중인 보조 컨테이너가 없습니다. 먼저 start를 실행하세요")
    validate_helper(info, source=args.source_container, archive=ensure_archive(args.archive_dir))
    ready = run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", user, "-d", args.database], env=helper_env(password))
    if ready.returncode:
        raise DumpClientError("원본 PostgreSQL 연결 확인에 실패했습니다")
    # The help text is not sufficient to detect the build's compression
    # libraries.  Execute a tiny schema-only dump to /dev/null instead.
    compression = run(["docker", "exec", name, "pg_dump", "--schema-only", "--compress=zstd:1",
                       "--dbname", args.database, "--username", user, "--host", "127.0.0.1",
                       "--table=public.snapshot", "--file", "/dev/null"], env=helper_env(password))
    return {"ok": True, "helper": name, "source": args.source_container, "database": args.database, "user": user,
            "image": image, "network_shared": True, "zstd_supported": compression.returncode == 0}


def dump_schema(args: argparse.Namespace) -> dict:
    image, user, password = source_details(args.source_container)
    name = helper_name(args.source_container)
    archive = ensure_archive(args.archive_dir)
    info = inspect_existing(name)
    if info is None or info.get("State", {}).get("Running") is not True:
        raise DumpClientError("실행 중인 보조 컨테이너가 없습니다. 먼저 start를 실행하세요")
    validate_helper(info, source=args.source_container, archive=archive)
    output = archive / "source-schema.sql"
    if output.exists():
        raise DumpClientError(f"기존 schema 파일을 덮어쓰지 않습니다: {output}")
    command = ["docker", "exec", name, "pg_dump", "--schema-only", "--no-owner", "--no-privileges",
               "--dbname", args.database, "--username", user, "--host", "127.0.0.1",
               "--table=public.package", "--table=public.version", "--table=public.snapshot",
               "--table=public.package_snapshot", "--table-and-children=public.package_version_snapshot",
               "--file", "/work/source-schema.sql"]
    checked(command, env=helper_env(password))
    return {"ok": True, "schema": str(output), "bytes": output.stat().st_size, "helper": name}


def stop(args: argparse.Namespace) -> dict:
    name = helper_name(args.source_container)
    info = inspect_existing(name)
    if info is None:
        return {"stopped": False, "helper": name, "reason": "absent"}
    validate_helper_identity(info, source=args.source_container)
    checked(["docker", "rm", "-f", name])
    return {"stopped": True, "helper": name}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-container", default=DEFAULT_SOURCE)
    p.add_argument("--database", default=DEFAULT_DB)
    p.add_argument("--archive-dir", type=Path, default=Path("data/service-data-migration/341/local-dump-probe"))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("start")
    sub.add_parser("probe")
    sub.add_parser("dump-schema")
    sub.add_parser("stop")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        action = {"start": start, "probe": probe, "dump-schema": dump_schema, "stop": stop}[args.command]
        print(json.dumps(action(args), ensure_ascii=False))
        return 0
    except DumpClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
