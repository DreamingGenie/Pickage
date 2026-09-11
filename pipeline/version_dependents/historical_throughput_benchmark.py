"""Sequential 8/16/32 full-source sample runs with local resource observations."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

from pipeline.requirements_resolution.input import file_sha256
from .historical_job import _memory, _worker_python


def _write(path, body):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _selection(path, digest):
    if file_sha256(path) != digest:
        raise ValueError("pilot selection changed")
    selection = json.loads(Path(path).read_bytes())
    sets = selection["nested_selection"]
    eight = sets["base8"]
    sixteen = eight + sets["add_to_16"]
    thirty_two = sixteen + sets["add_to_32"]
    samples = {8: eight, 16: sixteen, 32: thirty_two}
    for size, rows in samples.items():
        if len(rows) != size or len({r["name"] for r in rows}) != size:
            raise ValueError("pilot requires unique nested 8/16/32 targets")
    return selection, samples


def _resources(root_pid):
    """Read only this child process tree; report sampled RSS and CPU time."""
    if os.name != "nt":
        raise RuntimeError("this local resource observer currently requires Windows")
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                    ("heap", ctypes.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                    ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                    ("exe", w.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    entry = Entry(); entry.size = ctypes.sizeof(Entry)
    try:
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[int(entry.pid)] = int(entry.parent)
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    family = {root_pid}
    while True:
        expanded = family | {pid for pid, parent in parents.items() if parent in family}
        if expanded == family:
            break
        family = expanded
    rss = 0
    cpu = {}
    for pid in family:
        handle = kernel.OpenProcess(0x410, False, pid)
        if not handle:
            continue
        try:
            try:
                memory = _memory(SimpleNamespace(_handle=handle, pid=pid))
            except OSError:
                # A short-lived child may exit between enumeration and inspection.
                continue
            rss += memory["rss_bytes"]
            created, exited, system, user = (w.FILETIME() for _ in range(4))
            if kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in (created, exited, system, user)]):
                value = lambda t: (int(t.dwHighDateTime) << 32) | int(t.dwLowDateTime)
                cpu[str(pid)] = (value(system) + value(user)) / 10_000_000
        finally:
            kernel.CloseHandle(handle)
    return {"tree_rss_bytes": rss, "cpu_seconds_by_pid": cpu, "observed_pids": sorted(family)}


def _disk(root):
    scratch = databases = outputs = 0
    for directory, _dirs, files in os.walk(root):
        is_scratch = any("scratch" in p or p == "runtime-temp" for p in Path(directory).parts)
        for name in files:
            path = Path(directory) / name
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue
            if is_scratch:
                scratch += size
            elif path.suffix in {".duckdb", ".wal"}:
                databases += size
            else:
                outputs += size
    return {"scratch_bytes": scratch, "working_database_bytes": databases, "output_bytes": outputs}


def _worker(args):
    from .historical_production import run, verify_run, contract, WEIGHTED_ALGORITHM, current_memory
    from .historical_production_input import prepare
    selection, samples = _selection(args.selection, args.selection_sha)
    root = Path(args.output).resolve() / str(args.size)
    pinned = selection["pinned_inputs"]
    started = time.perf_counter()
    generation = contract(WEIGHTED_ALGORITHM)
    harness_sha = file_sha256(__file__)
    if args.harness_sha != harness_sha:
        raise ValueError("measurement code changed before pilot stage")
    if args.stage == "prepare":
        h1 = pinned["h1_input_manifest"]
        profile = pinned["h5_a_profile_manifest"]
        csv = pinned["selection_csv"]
        result = prepare(h1_dir=Path(h1["path"]).parent, h1_manifest_sha256=h1["sha256"],
                         profile_manifest=profile["path"], profile_manifest_sha256=profile["sha256"],
                         selection_csv=csv["path"], selection_sha256=csv["sha256"],
                         sample_names=[r["name"] for r in samples[args.size]], output=root / "input",
                         partition_count=128, threads=4, memory_limit="4GB", max_temp_size="40GB")
        expected = {"target_names": args.size,
                    "target_population": sum(r["V"] for r in samples[args.size]),
                    "lookups": sum(r["Q"] for r in samples[args.size]),
                    "declarations": sum(r["D"] for r in samples[args.size])}
        if result["rows"] != expected:
            raise ValueError("prepared rows differ from the selected full-source profile")
    elif args.stage == "run":
        prepared = json.loads((root / "prepare.json").read_bytes())["result"]
        result = run(prepared_dir=prepared["prepared_dir"], manifest_sha256=prepared["manifest_sha256"],
                     output=root / "run", algorithm=WEIGHTED_ALGORITHM,
                     threads=4, memory_limit="4GB", max_temp_size="40GB")
        if result["run_status"] != "COMPLETE" or result["scope"] != "SAMPLE":
            raise ValueError("pilot did not complete its exact sample scope")
    else:
        computed = json.loads((root / "run.json").read_bytes())["result"]
        result = verify_run(run_dir=computed["run_dir"], manifest_sha256=computed["run_manifest_sha256"])
    if generation != contract(WEIGHTED_ALGORITHM) or harness_sha != file_sha256(__file__):
        raise ValueError("code changed during pilot stage")
    report = {"size": args.size, "stage": args.stage, "elapsed_seconds": time.perf_counter() - started,
              "result": result, "memory": current_memory(), "generation": generation,
              "harness_sha256": harness_sha,
              "selection_sha256": args.selection_sha, "full_selection_executed": False}
    _write(root / (args.stage + ".json"), report)
    return report


def benchmark(args):
    if os.name != "nt":
        raise RuntimeError("this local resource observer requires Windows")
    from .historical_production import contract, WEIGHTED_ALGORITHM
    harness_sha = file_sha256(__file__)
    generation = contract(WEIGHTED_ALGORITHM)
    selection, samples = _selection(args.selection, args.selection_sha)
    root = Path(args.output).resolve()
    # Keep generated attempt paths under Windows' existing production path guard.
    if len(str(root)) > 90:
        raise ValueError("use a short pilot output path")
    root.mkdir(parents=True, exist_ok=False)
    _write(root / "selection.json", selection)
    observations = []
    started = time.time()
    for size in (8, 16, 32):
        sample = root / str(size)
        sample.mkdir()
        temp = sample / "runtime-temp"
        temp.mkdir()
        for stage in ("prepare", "run", "verify"):
            if harness_sha != file_sha256(__file__) or generation != contract(WEIGHTED_ALGORITHM):
                raise ValueError("code changed between pilot stages")
            command = [_worker_python(), "-B", "-m", "pipeline.version_dependents.historical_throughput_benchmark",
                       "--selection", str(Path(args.selection).resolve()), "--selection-sha", args.selection_sha,
                       "--output", str(root), "--stage", stage, "--size", str(size), "--worker",
                       "--harness-sha", harness_sha]
            env = dict(os.environ, TEMP=str(temp), TMP=str(temp),
                       PYTHONPATH=os.pathsep.join(str(Path(p).absolute()) for p in sys.path if p))
            peak = {"tree_rss_bytes": 0, "scratch_bytes": 0, "working_database_bytes": 0, "output_bytes": 0}
            disk_before = _disk(sample)
            cpus, pids = {}, set()
            sample_count = 0
            observed_started = time.perf_counter()
            failure = None
            with (sample / (stage + ".log")).open("wb") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    while process.poll() is None:
                        resource = _resources(process.pid)
                        disk = _disk(sample)
                        for key in peak:
                            peak[key] = max(peak[key], resource.get(key, disk.get(key, 0)))
                        for pid, value in resource["cpu_seconds_by_pid"].items():
                            cpus[pid] = max(cpus.get(pid, 0), value)
                        pids.update(resource["observed_pids"])
                        sample_count += 1
                        state = {"status": "RUNNING", "size": size, "stage": stage,
                                 "pid": process.pid, "elapsed_seconds": time.perf_counter() - observed_started,
                                 "peak": peak, "latest": disk, "sample_count": sample_count}
                        _write(root / "status.json", state)
                        if (resource["tree_rss_bytes"] > 12 * 1024**3 or disk["scratch_bytes"] > 64 * 1024**3
                                or shutil.disk_usage(root).free < 20 * 1024**3):
                            raise RuntimeError("pilot sampled memory or disk guard reached")
                        time.sleep(1)
                except BaseException as exc:
                    failure = str(exc)
                    if process.poll() is None:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                        process.wait()
                exit_code = process.wait()
            observed = {"size": size, "stage": stage, "exit_code": exit_code,
                        "elapsed_seconds": time.perf_counter() - observed_started, "peak": peak,
                        "cumulative_sample_disk_before": disk_before,
                        "cumulative_sample_disk_after": _disk(sample),
                        "disk_peak_scope": "CUMULATIVE_SAMPLE_FOOTPRINT_INCLUDING_PRIOR_STAGES",
                        "disk_peak_growth_bytes": {k: max(0, peak[k] - v) for k, v in disk_before.items()},
                        "observed_cpu_seconds": sum(cpus.values()), "observed_pids": sorted(pids),
                        "sample_count": sample_count, "failure": failure,
                        "harness_sha256": harness_sha,
                        "artifacts": {"result": str(sample / (stage + ".json")),
                                      "log": str(sample / (stage + ".log")),
                                      "resources": str(sample / (stage + "-resources.json"))},
                        "measurement": "1_SECOND_SAMPLED_PROCESS_TREE_AND_TASK_DIRECTORIES"}
            _write(sample / (stage + "-resources.json"), observed)
            observations.append(observed)
            if exit_code or failure:
                _write(root / "status.json", {"status": "FAILED", **observed})
                raise RuntimeError(f"sample {size} {stage} failed; see {sample / (stage + '.log')}")
            print(json.dumps({"finished_size": size, "stage": stage, "seconds": observed["elapsed_seconds"]}), flush=True)
    if harness_sha != file_sha256(__file__) or generation != contract(WEIGHTED_ALGORITHM):
        raise ValueError("code changed at pilot completion")
    report = {"status": "COMPLETE", "sizes": [8, 16, 32], "observations": observations,
              "harness_sha256": harness_sha, "generation": generation,
              "selection_sha256": args.selection_sha, "elapsed_seconds": time.time() - started,
              "profile_workload": {str(k): {m: sum(r[m] for r in v) for m in ("D", "V", "Q", "QV")}
                                   for k, v in samples.items()},
              "prepared_rows": {str(k): json.loads((root / str(k) / "prepare.json").read_bytes())["result"]["rows"]
                                for k in samples},
              "measurement_limits": "RSS/CPU/disk sampled each second; short children and instantaneous peaks may be missed. Disk peaks include prior-stage files; growth is relative to stage start.",
              "full_selection_executed": False, "db_load_executed": False,
              "source_scope": "ALL_ELIGIBLE_SOURCE_VERSIONS_FOR_EACH_SELECTED_TARGET"}
    _write(root / "report.json", report)
    _write(root / "status.json", {"status": "COMPLETE", "report": str(root / "report.json")})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--selection-sha", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--harness-sha")
    parser.add_argument("--size", type=int, choices=(8, 16, 32))
    parser.add_argument("--stage", choices=("prepare", "run", "verify"))
    args = parser.parse_args()
    if args.worker and (args.size is None or args.stage is None):
        parser.error("worker requires size and stage")
    print(json.dumps(_worker(args) if args.worker else benchmark(args), indent=2))


if __name__ == "__main__":
    main()
