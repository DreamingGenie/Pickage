"""Run the H5 input profiler with file receipts and sampled resource limits."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes
from pipeline.preprocessing.version_dependents.artifact import _reject_reparse_ancestors, _reparse, _validate_sha
from pipeline.preprocessing.version_dependents.historical_artifact import _run_lock, _publish_json


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(path):
    _reject_reparse_ancestors(path)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Missing, unsafe, or oversized job metadata")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Job metadata must be an object")
    return value


def _status(path, value):
    _reject_reparse_ancestors(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _bytes(path):
    if not path.exists():
        return 0
    total = 0
    for root, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            target = Path(root) / name
            if _reparse(target):
                raise ValueError("Job output contains an unsafe reparse point")
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except FileNotFoundError:
                pass  # DuckDB may delete a spill file between directory and stat.
    return total


def _memory(process):
    if os.name == "nt":
        # Microsoft PSAPI PROCESS_MEMORY_COUNTERS_EX; no extra dependency.
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("peak_rss", "rss", "peak_paged", "paged",
                    "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]
        function = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        function.restype = wintypes.BOOL
        value = Counters()
        value.cb = ctypes.sizeof(value)
        if not function(int(process._handle), ctypes.byref(value), value.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"rss_bytes": value.rss, "os_peak_rss_bytes": value.peak_rss,
                "private_bytes": value.private}
    status = Path(f"/proc/{process.pid}/status").read_text()
    values = {line.split(':')[0]: line.split(':')[1].strip().split()[0]
              for line in status.splitlines() if line.startswith(("VmRSS:", "VmHWM:"))}
    return {"rss_bytes": int(values["VmRSS"]) * 1024,
            "os_peak_rss_bytes": int(values["VmHWM"]) * 1024, "private_bytes": None}


def _worker_python():
    # Windows venv python.exe can be a redirector with a different PID/RSS from
    # the interpreter. Use its underlying interpreter and inherit module paths.
    return sys._base_executable if os.name == "nt" else sys.executable


def _worker_environment():
    return dict(os.environ, H5_SUPERVISOR_PID=str(os.getpid()),
                PYTHONPATH=os.pathsep.join(str(Path(p).absolute()) for p in sys.path if p))


def _command(args, output):
    command = [_worker_python(), "-B", "-m", "pipeline.preprocessing.version_dependents.historical_profile", "build"]
    for key in ("input_dir", "input_manifest_sha256", "threads", "memory_limit", "max_temp_size"):
        command += ["--" + key.replace("_", "-"), str(args[key])]
    return command + ["--output", str(output)]


def _latest_phase(path):
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 16384))
        lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            return json.loads(line).get("phase")
        except (ValueError, AttributeError):
            continue
    return None


def _stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _start_parent_guard(parent_pid, job):
    """Exit if the resource supervisor dies; a model session is not involved."""
    if os.getppid() != parent_pid:
        raise RuntimeError("Profiler supervisor PID differs from its actual parent")
    job = Path(job).absolute()
    _reject_reparse_ancestors(job)
    kernel, handle = None, None
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def watch():
        try:
            if kernel:
                if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) != 0:
                    raise RuntimeError("Cannot wait for supervisor process")
            else:
                while os.getppid() == parent_pid:
                    time.sleep(1)
            state = _json(job / "status.json")
            state.update(status="FAILED", reason="SUPERVISOR_LOST", updated_at=_now(), finished_at=_now())
            _status(job / "status.json", state)
            _publish_json(job / "supervisor_lost.json", state)
        except BaseException as error:
            try:
                _publish_json(job / "supervisor_lost.json", {"status": "FAILED", "reason": "SUPERVISOR_WATCH_FAILED",
                                                            "message": str(error)[:2000], "updated_at": _now()})
            except BaseException:
                pass
        finally:
            if kernel:
                kernel.CloseHandle(handle)
            os._exit(70)
    threading.Thread(target=watch, name="h5-supervisor-lifetime", daemon=True).start()


def _size(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", value):
        raise ValueError("Engine resource sizes must use MB or GB")
    return int(value[:-2]) * (1000**3 if value.endswith("GB") else 1000**2)


def supervise(*, config, config_sha256):
    config = Path(config).absolute()
    _validate_sha(config_sha256, "job config SHA")
    settings = _json(config)
    if file_sha256(config) != config_sha256 or settings.get("format") != "historical-profile-job-v1":
        raise ValueError("Job config identity mismatch")
    job = Path(settings["job_dir"]).absolute()
    _reject_reparse_ancestors(job)
    if not job.is_dir() or not config.is_relative_to(job):
        raise ValueError("Job directory must contain its config")
    budget = settings["budget"]
    required = {"max_rss_bytes", "max_scratch_bytes", "max_output_bytes", "min_free_disk_bytes", "max_seconds", "sample_seconds"}
    if (set(budget) != required
            or any(type(budget[k]) is not int or budget[k] <= 0 for k in required - {"max_seconds"})
            or budget["sample_seconds"] > 30):
        raise ValueError("Explicit positive resource budgets are required")
    max_seconds = budget["max_seconds"]
    if max_seconds is not None and (type(max_seconds) is not int or max_seconds <= 0):
        raise ValueError("max_seconds must be null (no elapsed limit) or a positive integer")
    args = settings["profile_args"]
    if set(args) != {"input_dir", "input_manifest_sha256", "threads", "memory_limit", "max_temp_size"}:
        raise ValueError("Invalid profile arguments")
    if _size(args["max_temp_size"]) > budget["max_scratch_bytes"] or _size(args["memory_limit"]) * 1.25 > budget["max_rss_bytes"]:
        raise ValueError("Engine limits exceed supervisor budgets or omit memory overhead")
    free = shutil.disk_usage(job).free
    if budget["max_scratch_bytes"] > free // 2 or budget["max_scratch_bytes"] + budget["max_output_bytes"] + budget["min_free_disk_bytes"] > free:
        raise ValueError("Job disk budget exceeds available space")
    profile, status_path = job / "profile", job / "status.json"
    with _run_lock(job):
        if status_path.exists() or profile.exists():
            raise ValueError("Job was already started; preserve it and use a new job directory")
        started = time.monotonic()
        state = {"scope": "H5_INPUT_WORKLOAD_PROFILE", "status": "RUNNING", "started_at": _now(),
                 "updated_at": _now(), "supervisor_pid": os.getpid(), "worker_pid": None,
                 "config_sha256": config_sha256, "count_status": "NOT_COMPUTED", "ready_for_load": False,
                 "peak_rss_bytes": 0, "peak_scratch_bytes": 0, "peak_output_bytes": 0,
                 "memory_samples": 0, "resource_guard_mode": "SAMPLED_SOFT_LIMITS",
                 "elapsed_limit_enforced": max_seconds is not None,
                 "budget": budget, "disk_free_bytes_at_start": free}
        process = None
        _status(status_path, state)
        try:
            with (job / "worker.stdout.log").open("xb") as stdout, (job / "worker.stderr.log").open("xb") as stderr:
                command = _command(args, profile)
                environment = _worker_environment()
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=REPO_ROOT,
                                           env=environment,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                state.update(worker_pid=process.pid, command=command)
                while True:
                    code = process.poll()
                    memory = {"rss_bytes": 0, "os_peak_rss_bytes": 0, "private_bytes": None}
                    if code is None:
                        try:
                            memory = _memory(process)
                            state["memory_samples"] += 1
                        except OSError:
                            if process.poll() is None:
                                raise
                    scratch = _bytes(profile / "scratch")
                    output_bytes = max(0, _bytes(profile) - scratch)
                    elapsed = time.monotonic() - started
                    state.update(updated_at=_now(), elapsed_seconds=elapsed, phase=_latest_phase(profile / "progress.jsonl"),
                                 scratch_bytes=scratch, output_bytes=output_bytes, **memory)
                    state["peak_rss_bytes"] = max(state["peak_rss_bytes"], memory["rss_bytes"], memory["os_peak_rss_bytes"])
                    state["peak_scratch_bytes"] = max(state["peak_scratch_bytes"], scratch)
                    state["peak_output_bytes"] = max(state["peak_output_bytes"], output_bytes)
                    checks = [(max_seconds is not None and elapsed > max_seconds, "elapsed time"),
                              (state["peak_rss_bytes"] > budget["max_rss_bytes"], "process RSS"),
                              (scratch > budget["max_scratch_bytes"], "scratch size"),
                              (output_bytes > budget["max_output_bytes"], "output size"),
                              (shutil.disk_usage(job).free < budget["min_free_disk_bytes"], "disk free space")]
                    exceeded = next((name for bad, name in checks if bad), None)
                    if exceeded:
                        state.update(status="BUDGET_EXCEEDED", reason=exceeded)
                        _stop(process)
                        break
                    _status(status_path, state)
                    if code is not None:
                        if code != 0:
                            raise RuntimeError(f"Profile worker failed with exit code {code}; see worker.stderr.log")
                        result = _json(profile / "result.json")
                        if (result.get("profile_status") != "COMPLETE" or result.get("count_status") != "NOT_COMPUTED"
                                or result.get("ready_for_load") is not False or result.get("output") != str(profile)
                                or file_sha256(profile / "profile_manifest.json") != result.get("manifest_sha256")):
                            raise ValueError("Worker completion receipt mismatch")
                        manifest = _json(profile / "profile_manifest.json")
                        if manifest.get("profile_status") != "COMPLETE" or manifest.get("count_status") != "NOT_COMPUTED":
                            raise ValueError("Profile completion manifest mismatch")
                        if file_sha256(config) != config_sha256:
                            raise ValueError("Job config changed during execution")
                        state.update(status="COMPLETE", result=result)
                        break
                    time.sleep(budget["sample_seconds"])
        except BaseException as error:
            _stop(process)
            state.update(status="FAILED", reason=f"{type(error).__name__}: {str(error)[:2000]}")
        finally:
            _stop(process)
            state.update(updated_at=_now(), finished_at=_now(), elapsed_seconds=time.monotonic() - started,
                         exit_code=process.poll() if process is not None else None)
            if state["memory_samples"] == 0:
                state["peak_rss_bytes"] = None
            state["rss_peak_scope"] = "OS_PEAK_OBSERVED_WHILE_ALIVE; NOT_A_HARD_MEMORY_LIMIT"
            _publish_json(job / "job_receipt.json", state)
            state["job_receipt_sha256"] = file_sha256(job / "job_receipt.json")
            _status(status_path, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    state = supervise(**vars(parser.parse_args()))
    print(json.dumps(state, ensure_ascii=True))
    if state["status"] != "COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
