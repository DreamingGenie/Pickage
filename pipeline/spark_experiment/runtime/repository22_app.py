"""App-EC2 supervisor for the isolated repository22 two-EC2 experiment.

This module deliberately wraps ``benchmark_app_host``.  The production-shaped
supervisor remains unchanged; this run only changes its run label and the
experiment container's resource policy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from . import benchmark_app_host as base

_BASE_SAVE = base.save
_BASE_WORKER_DOCKER_COMMAND = base.worker_docker_command


RUN = "repository22-20260917-a1"
APP_HOST = "172.26.6.235"
CONTAINER_MEMORY = "5632m"
CONTAINER_MEMORY_BYTES = 5632 * 1024**2
WORKER_MEMORY = "4096M"
WORKER_CORES = 2
CONTAINER_CPUS = 2
RUN_SECONDS = 30 * 60
MIN_AVAILABLE_MEMORY = 8 * 1024**3
MAX_IO_PRESSURE_AVG10 = 10.0
MAX_MEMORY_PRESSURE_AVG10 = 1.0


def parse_pressure_avg10(text: str) -> float:
    """Return PSI ``some`` avg10, rejecting missing or malformed input."""
    for line in text.splitlines():
        if line.startswith("some "):
            match = re.search(r"(?:^| )avg10=([0-9]+(?:\.[0-9]+)?)", line)
            if match:
                return float(match.group(1))
    raise ValueError("PSI some avg10 value is missing")


def validate_host_resources(*, available_memory: int, io_avg10: float,
                            memory_avg10: float) -> dict:
    if available_memory < MIN_AVAILABLE_MEMORY:
        raise RuntimeError("App host MemAvailable is below 8 GiB")
    if io_avg10 > MAX_IO_PRESSURE_AVG10:
        raise RuntimeError("App host IO pressure avg10 is above 10%")
    if memory_avg10 > MAX_MEMORY_PRESSURE_AVG10:
        raise RuntimeError("App host memory pressure avg10 is above 1%")
    return {"available_memory_bytes": available_memory, "io_pressure_avg10": io_avg10,
            "memory_pressure_avg10": memory_avg10}


def unknown_running_experiments(rows: list[dict], *, run: str = RUN) -> list[dict]:
    """Find running labelled experiments; production containers have no label."""
    return [row for row in rows if row.get("running") and
            row.get("experiment") not in (None, "", run)]


def validate_no_unknown_running_experiments(rows: list[dict], *, run: str = RUN) -> None:
    unknown = unknown_running_experiments(rows, run=run)
    if unknown:
        raise RuntimeError("Unknown running experiment containers: " + json.dumps(unknown))


def _docker_rows() -> list[dict]:
    ids = base.docker("ps", "-q").split()
    if not ids:
        return []
    raw = base.docker("inspect", *ids)
    return [{"name": item.get("Name", "").lstrip("/"),
             "running": bool((item.get("State") or {}).get("Running")),
             "experiment": ((item.get("Config") or {}).get("Labels") or {}).get(
                 "pickage.experiment")}
            for item in json.loads(raw)]


def preflight() -> dict:
    if base.socket.gethostname() != base.APP_HOSTNAME:
        raise RuntimeError("This preparation is for the app EC2 only")
    mem = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
           for line in Path("/proc/meminfo").read_text().splitlines()}
    io_avg10 = parse_pressure_avg10(Path("/proc/pressure/io").read_text())
    memory_avg10 = parse_pressure_avg10(Path("/proc/pressure/memory").read_text())
    resources = validate_host_resources(available_memory=mem["MemAvailable"],
                                        io_avg10=io_avg10, memory_avg10=memory_avg10)
    rows = _docker_rows()
    validate_no_unknown_running_experiments(rows)
    return {"status": "READY", "run_id": RUN, "host": APP_HOST,
            "resource_policy": resources,
            "running_experiment_containers": [row for row in rows if row["running"] and
                                                row["experiment"]],
            "production_service_changes": False, "db_loaded": False}


def worker_docker_command(*, credential_names=None) -> list[str]:
    if credential_names is None:
        credential_names = base.CREDENTIAL_ENV
    root = Path("/home/ubuntu/pickage-experiments") / RUN
    base.RUN, base.ROOT = RUN, root
    base.CODE, base.OUTPUT = root / "code", root / "output"
    base.APP_HOST = APP_HOST
    command = _BASE_WORKER_DOCKER_COMMAND(credential_names=credential_names)
    # The base command is the canonical image/mount/security definition.  Only
    # replace resource knobs for this isolated run.
    def replace(option: str, value: str) -> None:
        index = command.index(option)
        command[index + 1] = value

    replace("--cpus", str(CONTAINER_CPUS))
    replace("--memory", CONTAINER_MEMORY)
    replace("--memory-swap", CONTAINER_MEMORY)
    replace("--port", str(base.WORKER_PORT))
    replace("--cores", str(WORKER_CORES))
    replace("--memory", CONTAINER_MEMORY)
    # The second --memory belongs to Spark Worker. Replace it separately.
    worker_memory_index = len(command) - 1
    command[worker_memory_index] = WORKER_MEMORY
    command[-3] = str(WORKER_CORES)
    command[command.index("--memory") + 1] = CONTAINER_MEMORY
    command[command.index("--memory-swap") + 1] = CONTAINER_MEMORY
    command[command.index("--cpus") + 1] = str(CONTAINER_CPUS)
    command[command.index("--cores") + 1] = str(WORKER_CORES)
    image_index = command.index(base.IMAGE)
    command[image_index + 1:image_index + 1] = ["nice", "-n", "10"]
    image_index = command.index(base.IMAGE)
    command[image_index:image_index] = [
        "--cpu-shares", "128", "--device-read-bps", "/dev/nvme0n1:32mb",
        "--device-write-bps", "/dev/nvme0n1:32mb"]
    return command


def verify_container_caps(info: dict) -> None:
    host = info.get("HostConfig") or {}
    if (host.get("NanoCpus") != CONTAINER_CPUS * 1_000_000_000 or
            host.get("Memory") != CONTAINER_MEMORY_BYTES or
            host.get("MemorySwap") != CONTAINER_MEMORY_BYTES or
            host.get("CpuShares") != 128 or
            (host.get("RestartPolicy") or {}).get("Name") != "no"):
        raise RuntimeError("App worker container does not match repository22 caps")
    labels = (info.get("Config") or {}).get("Labels") or {}
    if labels.get("pickage.experiment") != RUN:
        raise RuntimeError("Refusing to manage an unlabelled or foreign worker container")


def _save(name: str, value: dict) -> None:
    if name in ("status.json", "result.json"):
        value = dict(value)
        value.update(container_cpu=CONTAINER_CPUS, container_memory_bytes=CONTAINER_MEMORY_BYTES,
                     container_swap_bytes=0, memory_swap_limit_bytes=CONTAINER_MEMORY_BYTES,
                     worker_cores=WORKER_CORES,
                     worker_memory=WORKER_MEMORY, run_id=RUN)
    _BASE_SAVE(name, value)


def _rewrite_guard_command(args):
    if isinstance(args, list) and "pipeline.spark_experiment.runtime.ec2_guard" in args:
        return ["pipeline.spark_experiment.runtime.repository22_guard" if value ==
                "pipeline.spark_experiment.runtime.ec2_guard" else value for value in args]
    return args


def run_supervisor() -> dict:
    preflight()
    # Configure the reusable supervisor without modifying its source module.
    base.RUN, base.ROOT = RUN, Path("/home/ubuntu/pickage-experiments") / RUN
    base.CODE, base.OUTPUT, base.METRICS = base.ROOT / "code", base.ROOT / "output", base.ROOT / "metrics"
    base.APP_HOST, base.RUN_SECONDS = APP_HOST, RUN_SECONDS
    base.CONTAINER_MEMORY, base.WORKER_MEMORY = CONTAINER_MEMORY, WORKER_MEMORY
    # Local-input runs do not need S3A credentials.  The default remains strict
    # because a MinIO-backed distributed run must authenticate explicitly.
    if os.environ.get("PICKAGE_REPOSITORY22_REQUIRE_S3A_CREDENTIALS", "1") == "0":
        base.CREDENTIAL_ENV = ()
    base.worker_docker_command = worker_docker_command
    base.verify_container_caps = verify_container_caps
    base.save = _save
    original_subprocess = base.subprocess

    class _SubprocessProxy:
        def __getattr__(self, name):
            return getattr(original_subprocess, name)

        def Popen(self, args, *positional, **kwargs):
            args = _rewrite_guard_command(args)
            return original_subprocess.Popen(args, *positional, **kwargs)

    base.subprocess = _SubprocessProxy()
    try:
        return base.run_supervisor()
    finally:
        base.subprocess = original_subprocess


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        print(json.dumps(preflight(), indent=2))
        return 0
    result = run_supervisor()
    return 0 if result.get("status") == "EXPECTED_MASTER_STOP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
