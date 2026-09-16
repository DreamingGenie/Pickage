"""Read-only host-side cgroup monitor for one labeled experiment container."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from pipeline.spark_experiment.telemetry import read_snapshot, snapshot_delta

RUN_LABEL = "pickage.experiment"
MAX_DURATION_SECONDS = 24 * 60 * 60
INSPECT_TEMPLATE = (
    '{{.Id}}\n{{.Name}}\n{{json .Config.Labels}}\n{{.State.Running}}\n{{.State.Pid}}\n'
    '{{.HostConfig.PidMode}}\n{{.HostConfig.CgroupnsMode}}\n{{.HostConfig.NanoCpus}}\n'
    '{{.HostConfig.CpuQuota}}\n{{.HostConfig.CpuPeriod}}\n{{.HostConfig.CpusetCpus}}\n'
    '{{.HostConfig.Memory}}\n{{.HostConfig.MemorySwap}}'
)


def docker_inspect(container: str, run_id: str, *, docker_fn=None) -> dict:
    """Fetch only the fields needed for identity, safety, and configured caps."""
    call = docker_fn or _docker
    raw = call("inspect", "--format", INSPECT_TEMPLATE, container)
    lines = raw.splitlines()
    if len(lines) != 13:
        raise ValueError("Docker inspect returned incomplete selective metadata")
    value = {"Id": lines[0], "Name": lines[1], "Labels": json.loads(lines[2]),
             "Running": lines[3].lower() == "true", "Pid": int(lines[4] or 0),
             "PidMode": lines[5], "CgroupnsMode": lines[6],
             "NanoCpus": _int_or_none(lines[7]), "CpuQuota": _int_or_none(lines[8]),
             "CpuPeriod": _int_or_none(lines[9]), "CpusetCpus": lines[10],
             "Memory": _int_or_none(lines[11]), "MemorySwap": _int_or_none(lines[12])}
    return validate_target(value, container, run_id, allow_stopped=True)


def _docker(*args):
    return subprocess.check_output(["docker", *args], text=True, timeout=10)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_target(info: dict, expected_name: str, run_id: str, *, allow_stopped=False) -> dict:
    """Validate exact identity/label and reject host-wide PID/cgroup namespaces."""
    if info.get("Name", "").lstrip("/") != expected_name.lstrip("/"):
        raise ValueError("container name does not match requested exact name")
    labels = info.get("Labels") or {}
    if labels.get(RUN_LABEL) != run_id:
        raise ValueError(f"container lacks expected {RUN_LABEL} label")
    host = info.get("HostConfig") or {}
    pid_mode = info.get("PidMode", host.get("PidMode", ""))
    cgroup_mode = info.get("CgroupnsMode", host.get("CgroupnsMode", ""))
    if pid_mode == "host":
        raise ValueError("refusing container with host PID namespace")
    if cgroup_mode == "host":
        raise ValueError("refusing container with host cgroup namespace")
    if not info.get("Running", (info.get("State") or {}).get("Running", False)):
        if allow_stopped:
            return info
        raise ValueError("container is not running")
    pid = info.get("Pid", (info.get("State") or {}).get("Pid"))
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("container has no valid host PID")
    return info


def resolve_host_cgroup(pid: int, *, proc_root="/proc") -> Path:
    """Resolve a host PID's unified cgroup-v2 path without falling back to host root."""
    root = Path(proc_root)
    proc = root / str(pid)
    rel = None
    for line in (proc / "cgroup").read_text(encoding="ascii").splitlines():
        if line.startswith("0::"):
            rel = line[3:].strip()
            break
    if rel is None:
        raise ValueError("host PID has no unified cgroup-v2 entry")
    relative = Path(rel.lstrip("/"))
    for line in (root / "self" / "mountinfo").read_text(encoding="ascii").splitlines():
        try:
            left, right = line.split(" - ", 1)
            fields, fs = left.split(), right.split()
            if fs[0] != "cgroup2":
                continue
            mount_root, mount_point = Path(fields[3]), Path(fields[4])
            try:
                suffix = relative.relative_to(mount_root.relative_to("/"))
            except ValueError:
                suffix = relative
            candidate = mount_point / suffix
            # Keep the resolved location inside the mounted cgroup tree.
            if candidate.exists():
                return candidate
        except (ValueError, IndexError):
            continue
    raise ValueError("could not resolve container's cgroup-v2 directory")


def _caps(info):
    fields = ("NanoCpus", "CpuQuota", "CpuPeriod", "CpusetCpus", "Memory", "MemorySwap")
    return {key: info.get(key) for key in fields}


def monitor(*, container: str, run_id: str, output, duration_seconds: int,
            interval: int = 1, proc_root="/proc", inspect_fn=None,
            snapshot_fn=None, sleep_fn=time.sleep, monotonic_fn=time.monotonic,
            wall_time_fn=time.time):
    if duration_seconds < 1 or duration_seconds > MAX_DURATION_SECONDS:
        raise ValueError(f"duration-seconds must be between 1 and {MAX_DURATION_SECONDS}")
    if interval != 1:
        raise ValueError("sampling interval is fixed at 1 second")
    root = Path(proc_root)
    if inspect_fn is None and (sys.platform != "linux" or platform.system() != "Linux"):
        raise RuntimeError("monitor requires a local Linux Docker host")
    get_info = inspect_fn or (lambda: docker_inspect(container, run_id))
    read = snapshot_fn or read_snapshot
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_path = out_dir / "container-metrics.jsonl"
    summary_path = out_dir / "container-summary.json"
    if sample_path.exists() or summary_path.exists():
        raise FileExistsError("output already contains container monitor evidence files")
    first = last = None
    pinned_id = None
    max_current = max_peak = None
    reason = "DURATION_LIMIT"
    started = monotonic_fn()
    with sample_path.open("w", encoding="utf-8") as stream:
        while True:
            if (out_dir / "guard.done").exists():
                reason = "GUARD_DONE"
                break
            try:
                info = get_info()
                if not info.get("Running", (info.get("State") or {}).get("Running", False)):
                    reason = "CONTAINER_STOPPED"
                    break
                observed_id = info.get("Id")
                if pinned_id is None:
                    pinned_id = observed_id
                elif observed_id != pinned_id:
                    reason = "CONTAINER_REPLACED"
                    break
                pid = info.get("Pid", (info.get("State") or {}).get("Pid"))
                cgroup = resolve_host_cgroup(pid, proc_root=root)
                container_id = (pinned_id or "").lower()
                if not container_id or container_id not in str(cgroup).lower():
                    raise ValueError("resolved cgroup path does not identify the requested container")
                snap = read(cgroup_dir=cgroup, net_dev=root / str(pid) / "net/dev")
            except (subprocess.CalledProcessError, FileNotFoundError, ProcessLookupError):
                reason = "CONTAINER_GONE"
                break
            snap["timestamp"] = wall_time_fn()
            record = {"timestamp": snap["timestamp"], "container_id": info.get("Id"), "snapshot": snap}
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            if first is None:
                first = snap
            last = snap
            current, peak = snap["memory"]["current"], snap["memory"]["peak"]
            if current is not None:
                max_current = current if max_current is None else max(max_current, current)
            if peak is not None:
                max_peak = peak if max_peak is None else max(max_peak, peak)
            if monotonic_fn() - started >= duration_seconds:
                break
            sleep_fn(interval)
    with sample_path.open(encoding="utf-8") as samples_stream:
        sample_count = sum(1 for _ in samples_stream)
    summary = {
        "container": container.lstrip("/"), "container_id": pinned_id,
        "run_id": run_id, "configured_caps": _caps(info) if last else None,
        "sample_count": sample_count,
        "stop_reason": reason, "duration_seconds": max(0, monotonic_fn() - started),
        "max_sampled_memory_current_bytes": max_current,
        "max_observed_memory_peak_bytes": max_peak,
        "delta": snapshot_delta(first, last) if first is not None and last is not None else None,
        "limitations": {
            "memory_peak": "cgroup-lifetime high-water mark; may predate this sampling run",
            "network": "read from /proc/<host-pid>/net/dev; with host networking this describes the host network namespace and is not container-isolated",
            "scope": "read-only local Docker cgroup-v2 sampling; counters may be null when unavailable",
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True, help="exact Docker container name")
    parser.add_argument("--run-id", required=True, help=f"expected {RUN_LABEL} label value")
    parser.add_argument("--output", required=True, help="directory for JSONL samples and summary")
    parser.add_argument("--duration-seconds", required=True, type=int)
    parser.add_argument("--interval", type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.duration_seconds <= MAX_DURATION_SECONDS:
        parser.error(f"--duration-seconds must be between 1 and {MAX_DURATION_SECONDS}")
    if args.interval != 1:
        parser.error("--interval must be 1")
    return args


def main(argv=None):
    args = parse_args(argv)
    if sys.platform != "linux" or platform.system() != "Linux":
        raise SystemExit("monitor requires a local Linux Docker host")
    monitor(container=args.container, run_id=args.run_id, output=args.output,
            duration_seconds=args.duration_seconds, interval=args.interval)


if __name__ == "__main__":
    main()
