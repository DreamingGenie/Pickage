"""Opt-in CPU/CUDA resolution with the production npm policy and bounded I/O."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import time

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes
from .historical import _check_lookup
from .historical_gpu import NORMALIZER, cpu_ranks, gpu_ranks, intervals_from_ranks, validate_plan

MAX_FRAME_BYTES = 7 * 1024 * 1024
MAX_LOOKUP_BATCH = 1024


def validate_options(backend, lookup_batch, workspace_mib):
    if backend not in {"npm", "cpu", "gpu"}:
        raise ValueError("backend must be npm, cpu, or gpu")
    if type(lookup_batch) is not int or not 1 <= lookup_batch <= MAX_LOOKUP_BATCH:
        raise ValueError("lookup_batch must be between 1 and 1024")
    if type(workspace_mib) is not int or not 1 <= workspace_mib <= 512:
        raise ValueError("workspace_mib must be between 1 and 512")


def runtime_identity(backend):
    validate_options(backend, 1, 1)
    if backend == "npm":
        return {"backend": backend}
    import numpy as np
    runtime = {"backend": backend, "numpy": np.__version__}
    if backend == "cpu":
        return {**runtime, "algorithm": "min-birth-segment-tree"}
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU backend requested but CUDA is unavailable")
    device = torch.cuda.get_device_properties(0)
    return {**runtime, "torch": torch.__version__, "cuda": torch.version.cuda,
            "device": device.name, "total_memory_bytes": int(device.total_memory),
            "algorithm": "cuda-scatter-amax-cummax"}


def generation_contract():
    return {name: file_sha256(path) for name, path in (
        ("historical_production_resolver.py", Path(__file__)),
        ("historical_gpu.py", Path(__file__).with_name("historical_gpu.py")),
        ("historical_gpu_normalize.cjs", NORMALIZER))}


def _batches(name, known, candidates, rows, n, lookup_batch):
    validate_options("cpu", lookup_batch, 1)
    if type(n) is not int or not 1 <= n <= 4096 or len(candidates) > 100000:
        raise ValueError("Candidate/calendar limit exceeded")
    base = {"op": "package", "name": name, "known_package": known,
            "snapshot_count": n, "candidates": candidates, "requirements": []}
    base_bytes = len(canonical_bytes(base))
    if base_bytes >= MAX_FRAME_BYTES:
        raise ValueError("resolver request exceeds framing bound")
    pending, size = [], base_bytes
    for lookup_id, requirement in rows:
        spec_bytes = len(canonical_bytes(requirement))
        addition = spec_bytes + bool(pending)
        if pending and (len(pending) >= lookup_batch or size + addition >= MAX_FRAME_BYTES):
            yield pending, {**base, "requirements": [item[1] for item in pending]}
            pending, size, addition = [], base_bytes, spec_bytes
        if size + addition >= MAX_FRAME_BYTES:
            raise ValueError("resolver request exceeds framing bound")
        pending.append((lookup_id, requirement))
        size += addition
    if pending:
        yield pending, {**base, "requirements": [item[1] for item in pending]}


def _checked_plan(node, message, metadata):
    plan = node.request(message)
    if len(canonical_bytes(plan)) >= MAX_FRAME_BYTES:
        raise ValueError("resolver response exceeds framing bound")
    candidates = message["candidates"]
    if plan.get("accepted") != candidates or plan.get("rejected") != []:
        raise ValueError("Normalizer candidate validation differs from pinned H1 candidates")
    births = {item["version"]: item["birth_index"] for item in candidates}
    versions = plan.get("rank_to_version", [])
    if (len(births) != len(candidates) or len(versions) != len(candidates)
            or set(versions) != set(births)
            or plan.get("birth_by_rank") != [births[v] for v in versions]
            or plan.get("known_package") is not message["known_package"]
            or plan.get("snapshot_count") != message["snapshot_count"]):
        raise ValueError("Normalizer candidate/rank mapping mismatch")
    runtime = plan.get("runtime", {})
    for key, expected in (("node", "node_version"), ("semver", "semver_version"),
                          ("package_arg", "package_arg_version"), ("options", "options"),
                          ("tie", "equal_precedence_tie")):
        if expected not in metadata or runtime.get(key) != metadata[expected]:
            raise ValueError("Normalizer runtime differs from pinned npm metadata: " + key)
    if [item.get("requirement") for item in plan.get("lookups", [])] != message["requirements"]:
        raise ValueError("Normalizer changed lookup requirements")
    validate_plan(plan)
    return plan


def _insert(con, rows):
    # Typed column batches avoid per-row SQL calls and a second JSON serialization.
    # NULL-only columns retain the production schema without optional Arrow/pandas.
    con.execute("""INSERT INTO lookup_intervals SELECT
        unnest(?::BIGINT[]),unnest(?::INTEGER[]),unnest(?::INTEGER[]),
        unnest(?::VARCHAR[]),unnest(?::VARCHAR[]),unnest(?::INTEGER[]),unnest(?::VARCHAR[])""",
        [list(values) for values in zip(*rows)])


def resolve_partition(con, node, metadata, partition_id, n, *, backend,
                      lookup_batch=1024, workspace_mib=128):
    validate_options(backend, lookup_batch, workspace_mib)
    if backend == "npm":
        raise ValueError("npm uses the original production resolver")
    started = time.perf_counter()
    metrics = Counter()
    con.execute("""CREATE TEMP TABLE lookup_intervals(
      lookup_id BIGINT,start_index INTEGER,end_index INTEGER,status VARCHAR,
      normalized_range VARCHAR,target_package_id INTEGER,target_version VARCHAR)""")
    packages = con.execute("SELECT name,package_id,known_package FROM target_names WHERE partition_id=? ORDER BY name", [partition_id]).fetchall()
    for name, package_id, known in packages:
        if type(known) is not bool or known != (package_id is not None):
            raise ValueError("Target identity differs from known_package")
        tick = time.perf_counter()
        candidates = [{"version": version, "birth_index": int(birth)} for version, birth in con.execute(
            "SELECT version,birth_index FROM target_population WHERE name=? ORDER BY birth_index,version", [name]).fetchall()]
        metrics["candidate_read_seconds"] += time.perf_counter() - tick
        # Inserts on con must not invalidate the still-streaming lookup SELECT.
        cursor = con.cursor()
        metrics["packages"] += 1
        metrics["candidates"] += len(candidates)
        def stream():
            tick = time.perf_counter()
            cursor.execute("SELECT lookup_id,requirement FROM lookups WHERE declared_name=? ORDER BY lookup_id", [name])
            metrics["lookup_read_seconds"] += time.perf_counter() - tick
            while True:
                tick = time.perf_counter()
                rows = cursor.fetchmany(lookup_batch)
                metrics["lookup_read_seconds"] += time.perf_counter() - tick
                if not rows:
                    return
                yield from rows
        had_lookups = False
        try:
            for requested, message in _batches(name, known, candidates, stream(), n, lookup_batch):
                had_lookups = True
                tick = time.perf_counter()
                plan = _checked_plan(node, message, metadata)
                metrics["normalize_seconds"] += time.perf_counter() - tick
                metrics["lookup_requests"] += 1
                metrics["lookup_conditions"] += len(requested)
                tick = time.perf_counter()
                if backend == "gpu":
                    ranks, detail = gpu_ranks(plan, workspace_mib=workspace_mib)
                    for key in ("host_preparation_seconds", "h2d_seconds", "compute_seconds", "d2h_seconds"):
                        metrics[key] += detail.get(key, 0)
                    for key in ("peak_allocated_bytes", "peak_reserved_bytes"):
                        metrics[key] = max(metrics[key], detail.get(key, 0))
                    if metrics["peak_allocated_bytes"] >= 6 * 1024 ** 3:
                        raise RuntimeError("GPU resolver exceeded the 6 GiB allocation guard")
                else:
                    ranks, detail = cpu_ranks(plan)
                metrics["numeric_seconds"] += time.perf_counter() - tick
                tick = time.perf_counter()
                resolved = intervals_from_ranks(plan, ranks)
                metrics["interval_seconds"] += time.perf_counter() - tick
                if len(resolved) != len(requested):
                    raise ValueError("Resolver result lookup count mismatch")
                tick = time.perf_counter()
                rows = []
                for (lookup_id, requirement), item in zip(requested, resolved):
                    if item.get("requirement") != requirement:
                        raise ValueError("Resolver changed lookup requirement")
                    _check_lookup(item["intervals"], n)
                    for interval in item["intervals"]:
                        target_id = package_id if interval["status"] == "RESOLVED" else None
                        rows.append((lookup_id, interval["start_index"], interval["end_index"], interval["status"],
                                     interval["normalized_range"], target_id, interval["target_version"]))
                metrics["mapping_seconds"] += time.perf_counter() - tick
                if rows:
                    tick = time.perf_counter()
                    _insert(con, rows)
                    metrics["insert_seconds"] += time.perf_counter() - tick
                metrics["lookup_intervals"] += len(rows)
                metrics["resolved_lookups"] += len(requested)
            if not had_lookups:
                tick = time.perf_counter()
                _checked_plan(node, {"op": "package", "name": name, "known_package": known,
                                    "snapshot_count": n, "candidates": candidates, "requirements": []}, metadata)
                metrics["normalize_seconds"] += time.perf_counter() - tick
                metrics["zero_lookup_packages"] += 1
        finally:
            cursor.close()
    return {**metrics, "seconds": time.perf_counter() - started,
            "backend": backend, "partition_id": partition_id}
