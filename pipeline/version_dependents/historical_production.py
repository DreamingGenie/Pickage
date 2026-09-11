"""Partitioned all-date computation; full selection requires an explicit option."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes
import json
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import uuid

from pipeline.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes, sha256
from .historical import WORKER, _check_lookup
from .historical_artifact import _path, _publish_json, _read_json, _run_lock
from .historical_cache import _record, generation_contract
from .historical_production_cache import serialize_tables as create_cache, verify_cache
from .historical_job import _memory
from .historical_production_input import (connection, contract as input_contract, event,
                                          open_inputs, prepare, verify_inputs)
from .historical_production_sql import aggregate_partition, finalize_quality
from .historical_production_writer import build_history, verify_history
from . import historical_production_resolver as ranked_resolver


FORMAT = "historical-production-run-v1"
DEFAULT_ALGORITHM = "interval-sql-v1"
WEIGHTED_ALGORITHM = "weighted-events-v2"
WEIGHTED_FORMAT = "historical-production-run-v2"
PART_FILES = {"lookup_intervals": "lookup_intervals", "counts": "p_counts", "sources": "p_sources",
              "source_deltas": "p_source_deltas", "status_deltas": "p_status_deltas"}
WEIGHTED_PART_FILES = {"lookup_intervals": "lookup_intervals", "counts": "p_counts",
                       "source_summary": "p_source_summary", "status_deltas": "p_status_deltas"}


def _part_files(algorithm):
    if algorithm == DEFAULT_ALGORITHM:
        return PART_FILES
    if algorithm == WEIGHTED_ALGORITHM:
        return WEIGHTED_PART_FILES
    raise ValueError("Unknown production aggregation algorithm")


def contract(algorithm=DEFAULT_ALGORITHM, resolver_backend="npm"):
    _part_files(algorithm)
    ranked_resolver.validate_options(resolver_backend, 1024, 128)
    result = {"runner_sha256": file_sha256(Path(__file__)),
            "resolver_adapter_sha256": file_sha256(Path(ranked_resolver.__file__)),
            "sql_sha256": file_sha256(Path(__file__).with_name("historical_production_sql.py")),
            "input_contract": input_contract(), "h4_generation": generation_contract(),
            "h4_writer_sha256": file_sha256(Path(__file__).with_name("historical_artifact.py")),
            "production_writer_sha256": file_sha256(Path(__file__).with_name("historical_production_writer.py")),
            "production_cache_sha256": file_sha256(Path(__file__).with_name("historical_production_cache.py")),
            "production_daily_sha256": file_sha256(Path(__file__).with_name("historical_production_daily.py"))}
    if algorithm == WEIGHTED_ALGORITHM:
        result["algorithm"] = algorithm
        result["weighted_events_sha256"] = file_sha256(Path(__file__).with_name("historical_production_events.py"))
        result["weighted_quality_sha256"] = file_sha256(Path(__file__).with_name("historical_production_quality.py"))
    if resolver_backend != "npm":
        result["resolver_backend"] = resolver_backend
        result["resolver_generation"] = ranked_resolver.generation_contract()
    return result


def current_memory():
    if os.name == "nt":
        get = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentProcess
        get.restype = ctypes.c_void_p
        process = SimpleNamespace(_handle=get())
    else:
        process = SimpleNamespace(pid=os.getpid())
    return _memory(process)


class MeasuredNode(NodeSession):
    """Measure the actual UTF-8 response line read from the worker pipe."""
    def __init__(self, *args, **kwargs):
        self.last_response_bytes = 0
        self.metrics = Counter()
        super().__init__(*args, **kwargs)

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(8 * 1024 * 1024 + 1)
                if not line:
                    self.responses.put(None)
                    return
                size = len(line.encode("utf-8"))
                if size > 8 * 1024 * 1024 or not line.endswith("\n"):
                    self.responses.put(ValueError("Node response exceeds framing limit"))
                    return
                self.last_response_bytes = size
                self.responses.put(line)
        except BaseException as error:
            self.responses.put(error)

    def request(self, message):
        size = len(canonical_bytes(message))
        started = time.monotonic()
        result = super().request(message)
        self.metrics["requests"] += 1
        self.metrics["request_utf8_bytes"] += size
        self.metrics["response_utf8_bytes"] += self.last_response_bytes
        self.metrics["max_request_utf8_bytes"] = max(self.metrics["max_request_utf8_bytes"], size)
        self.metrics["max_response_utf8_bytes"] = max(self.metrics["max_response_utf8_bytes"], self.last_response_bytes)
        self.metrics["request_seconds"] += time.monotonic() - started
        return result


def batches(name, candidates, requirements, *, known_package, snapshot_count, bounds):
    """Bound both request and worst-case response, including long original specs."""
    if len(candidates) > bounds["max_candidates"] or snapshot_count > bounds["max_snapshots"]:
        raise ValueError("Candidate/calendar limit exceeded; package needs a different strategy")
    maximum = min(bounds["max_unique_requirements"],
                  bounds["max_candidate_requirement_work"] // max(len(candidates), 1),
                  bounds["max_result_intervals"] // snapshot_count)
    if maximum < 1:
        raise ValueError("Worker cannot fit a single lookup")
    base = {"op": "package", "name": name, "known_package": known_package,
            "snapshot_count": snapshot_count, "candidates": candidates, "requirements": []}
    longest = max((len(json.dumps(c["version"], ensure_ascii=False).encode("utf-8")) for c in candidates), default=4)
    # accepted candidates are echoed in each response. Each interval contains
    # status/range/version plus field names. Reserve generous fixed JSON overhead.
    accepted_bytes = len(canonical_bytes(candidates)) + 2048
    pending, response_bound = [], accepted_bytes
    for lookup_id, requirement in requirements:
        original_bytes = len(json.dumps(requirement, ensure_ascii=False).encode("utf-8"))
        # npm's normalized range can expand a short ^/~ expression; reserve 4x
        # original bytes plus 1024 per interval as well as the longest version.
        estimate = original_bytes + snapshot_count * (4 * original_bytes + longest + 1024)
        proposed = pending + [(lookup_id, requirement)]
        message = {**base, "requirements": [r for _, r in proposed]}
        too_large = (len(proposed) > maximum or len(canonical_bytes(message)) > bounds["max_frame_bytes"]
                     or response_bound + estimate > bounds["max_frame_bytes"])
        if too_large and pending:
            yield pending, {**base, "requirements": [r for _, r in pending]}
            pending, response_bound = [], accepted_bytes
            proposed = [(lookup_id, requirement)]
            message = {**base, "requirements": [requirement]}
        if (len(canonical_bytes(message)) > bounds["max_frame_bytes"]
                or response_bound + estimate > bounds["max_frame_bytes"]):
            raise ValueError("One lookup exceeds request/response framing budget")
        pending = proposed
        response_bound += estimate
    if pending:
        yield pending, {**base, "requirements": [r for _, r in pending]}


def _resolve_partition(con, node, metadata, partition_id, n):
    con.execute("""CREATE TEMP TABLE lookup_intervals(
        lookup_id BIGINT,start_index INTEGER,end_index INTEGER,status VARCHAR,
        normalized_range VARCHAR,target_package_id INTEGER,target_version VARCHAR)""")
    metrics = Counter()
    packages = con.execute("SELECT name,package_id,known_package FROM target_names WHERE partition_id=? ORDER BY name",
                           [partition_id]).fetchall()
    schema = '[{"lookup_id":"BIGINT","start_index":"INTEGER","end_index":"INTEGER",' \
             '"status":"VARCHAR","normalized_range":"VARCHAR","target_package_id":"INTEGER","target_version":"VARCHAR"}]'
    for name, package_id, known in packages:
        candidates = [{"version": v, "birth_index": b} for v, b in con.execute(
            "SELECT version,birth_index FROM target_population WHERE name=? ORDER BY birth_index,version", [name]).fetchall()]
        cursor = con.cursor().execute("SELECT lookup_id,requirement FROM lookups WHERE declared_name=? ORDER BY lookup_id", [name])
        def requests():
            while rows := cursor.fetchmany(512):
                yield from rows
        try:
            for requested, message in batches(name, candidates, requests(), known_package=known,
                                               snapshot_count=n, bounds=metadata["bounds"]):
                reply = node.request(message)
                if reply["rejected"] or reply["accepted"] != candidates:
                    raise ValueError("Worker candidate validation differs from pinned H1 candidates")
                if len(reply["lookups"]) != len(requested):
                    raise ValueError("Worker lookup count mismatch")
                mapped = []
                for (lookup_id, requirement), result in zip(requested, reply["lookups"]):
                    if result["requirement"] != requirement:
                        raise ValueError("Worker changed requirement")
                    _check_lookup(result["intervals"], n)
                    for row in result["intervals"]:
                        mapped.append({"lookup_id": lookup_id, **{k: row[k] for k in
                            ("start_index", "end_index", "status", "normalized_range", "target_version")},
                            "target_package_id": package_id if row["status"] == "RESOLVED" else None})
                if mapped:
                    con.execute("INSERT INTO lookup_intervals SELECT unnest(from_json(?,?),recursive:=true)",
                                [json.dumps(mapped, ensure_ascii=False), schema])
                metrics.update(reply["metrics"])
                metrics["lookup_intervals"] += len(mapped)
                metrics["resolved_lookups"] += len(requested)
        finally:
            cursor.close()
    return dict(metrics)


def _within(root, relative):
    path = _path(Path(root) / relative)
    if not path.is_relative_to(_path(root)):
        raise ValueError("Output pointer escapes its run")
    return path


def _read_partition(root, plan_sha, partition_id, expected_names, algorithm=DEFAULT_ALGORITHM):
    part_files = _part_files(algorithm)
    directory = root / "partitions" / f"{partition_id:03d}"
    pointer = directory / "complete.json"
    if not pointer.exists():
        return None
    ref = _read_json(pointer)
    attempt = _within(directory, ref["attempt"])
    receipt = attempt / "receipt.json"
    if file_sha256(receipt) != ref["receipt_sha256"]:
        raise ValueError("Partition receipt SHA mismatch")
    value = _read_json(receipt)
    if (value["plan_sha256"] != plan_sha or value["partition_id"] != partition_id
            or value["names"] != expected_names or value["status"] != "COMPLETE"
            or len(value["files"]) != len(part_files)
            or {r["name"] for r in value["files"]} != {p + ".parquet" for p in part_files}):
        raise ValueError("Partition receipt contract mismatch")
    for record in value["files"]:
        if _record(_within(attempt, record["name"])) != record:
            raise ValueError("Partition output changed")
    return {"partition_id": partition_id, "attempt": str(attempt.relative_to(root).as_posix()),
            "receipt_sha256": ref["receipt_sha256"], "names": expected_names}


def _coverage(con):
    groups = {}
    for partition_id, name in con.execute("SELECT partition_id,name FROM target_names ORDER BY partition_id,name").fetchall():
        groups.setdefault(partition_id, []).append(name)
    return groups


def _check_output_path(root):
    # H4 publishes via a sibling temporary filename. Reject too-long Windows
    # paths before any calculation, even when the eventual final name would fit.
    longest = (root / "finalizations" / ("a" * 32) / "history" / "snapshot=2000-01-01"
               / "attempts" / ("a" * 32) / ("snapshot_manifest.json.tmp-" + "a" * 32))
    if os.name == "nt" and len(str(longest)) >= 260:
        raise ValueError("Windows output path is too long; use a short run path such as data/vd-run-001")


def _provenance(plan, receipts):
    weighted = plan.get("algorithm", DEFAULT_ALGORITHM) == WEIGHTED_ALGORITHM
    return {"format": plan["format"], "plan_sha256": sha256(plan), "partitions": receipts,
                  "computation_origin": "H5_PRODUCTION_WEIGHTED_EVENTS" if weighted else "H5_PRODUCTION_INTERVAL_SQL",
                  "storage_adapter": "H4_V1_NORMALIZED_TABLE_SERIALIZER",
                  "legacy_cache_quality_origin_is_serializer_label": True,
                  "resolver_backend": plan["resolver_backend"],
                  "resolver_settings": plan["resolver_settings"],
                  "resolver_runtime": plan["resolver_runtime"],
                  "upstream_resolution_status": "PARTIAL", "ready_for_load": False}


def _merge_partitions(con, root, inputs, plan, receipts):
    con.read_parquet(str(Path(plan["prepared_dir"]) / "target_population.parquet"), hive_partitioning=False).create_view("target_population", replace=True)
    weighted = plan.get("algorithm", DEFAULT_ALGORITHM) == WEIGHTED_ALGORITHM
    tables = (("counts", "all_counts"), ("source_summary", "all_source_summary"),
              ("status_deltas", "all_status_deltas")) if weighted else (
              ("counts", "all_counts"), ("sources", "all_sources"),
              ("source_deltas", "all_source_deltas"), ("status_deltas", "all_status_deltas"))
    for suffix, table in tables:
        paths = [str(_within(root, r["attempt"]) / (suffix + ".parquet")) for r in receipts]
        con.read_parquet(paths, hive_partitioning=False).create_view(table)
    if weighted:
        from .historical_production_quality import finalize_quality_weighted
        finalize_quality_weighted(con, len(inputs["calendar"]))
    else:
        finalize_quality(con, len(inputs["calendar"]))


def _check_cache_derivation(con, cache_dir):
    for table, name in (("history_count_intervals", "count_intervals"),
                        ("history_target_population", "target_population"),
                        ("history_quality", "quality")):
        con.read_parquet(str(cache_dir / (name + ".parquet")), hive_partitioning=False).create_view("stored_" + name)
        difference = con.execute(f"""SELECT count(*) FROM (
            (SELECT * FROM {table} EXCEPT ALL SELECT * FROM stored_{name})
            UNION ALL
            (SELECT * FROM stored_{name} EXCEPT ALL SELECT * FROM {table})
        )""").fetchone()[0]
        if difference:
            raise ValueError("Cache differs from partition-derived " + name)


def _verify_cache_chain(root, saved, inputs, plan, receipts):
    if set(saved) != {"directory", "provenance_sha256", "cache_sha256"}:
        raise ValueError("Invalid cache pointer contract")
    directory = _within(root, saved["directory"])
    if (_read_json(directory / "provenance.json") != _provenance(plan, receipts)
            or file_sha256(directory / "provenance.json") != saved["provenance_sha256"]):
        raise ValueError("Production provenance chain mismatch")
    cache = verify_cache(directory / "cache", saved["cache_sha256"])
    if (cache["lineage"]["input_manifest_sha256"] != saved["provenance_sha256"]
            or cache["lineage"]["policy_sha256"] != sha256(inputs["policy"])
            or cache["runtime"] != plan["runtime"] or cache["calendar"] != inputs["calendar"]):
        raise ValueError("Production cache lineage mismatch")
    return directory


def _finalize(root, input_manifest, plan, receipts, settings):
    pointer = root / "cache_complete.json"
    provenance = _provenance(plan, receipts)
    if pointer.exists():
        saved = _read_json(pointer)
        directory = _verify_cache_chain(root, saved, input_manifest, plan, receipts)
        with connection(root / ("verify-cache-" + uuid.uuid4().hex + ".duckdb"), **settings) as con:
            _merge_partitions(con, root, input_manifest, plan, receipts)
            _check_cache_derivation(con, directory / "cache")
        return saved
    directory = root / "finalizations" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    _publish_json(directory / "provenance.json", provenance)
    with connection(directory / "working.duckdb", **settings) as con:
        _merge_partitions(con, root, input_manifest, plan, receipts)
        cached = create_cache(con, output=directory / "cache", calendar=input_manifest["calendar"],
                              observed_snapshot_timestamp=input_manifest["observed_snapshot_timestamp"],
                              lineage={"source_kind": "NORMALIZED_HISTORY_TABLES",
                                       "input_manifest_sha256": file_sha256(directory / "provenance.json"),
                                       "policy_sha256": sha256(input_manifest["policy"])}, runtime=plan["runtime"])
    saved = {"directory": directory.relative_to(root).as_posix(),
             "provenance_sha256": file_sha256(directory / "provenance.json"),
             "cache_sha256": cached["manifest_sha256"]}
    _publish_json(pointer, saved)
    return saved


def run(*, prepared_dir, manifest_sha256, output, resume=False, allow_full_selected=False,
        max_partitions=None, max_snapshots=None, runtime=None, threads=4, memory_limit="4GB",
        max_temp_size="40GB", min_free_bytes=20_000_000_000, request_timeout=60,
        algorithm=DEFAULT_ALGORITHM, resolver_backend="npm", resolver_lookup_batch=1024,
        gpu_workspace_mib=128):
    started = time.monotonic()
    ranked_resolver.validate_options(resolver_backend, resolver_lookup_batch, gpu_workspace_mib)
    part_files = _part_files(algorithm)
    weighted = algorithm == WEIGHTED_ALGORITHM
    prepared_dir, root = _path(prepared_dir), _path(output)
    _check_output_path(root)
    inputs = verify_inputs(prepared_dir, manifest_sha256)
    if inputs["scope"] == "FULL_SELECTED" and not allow_full_selected:
        raise ValueError("Full selected execution requires explicit allow_full_selected=True")
    if root.is_relative_to(prepared_dir) or prepared_dir.is_relative_to(root):
        raise ValueError("Run output overlaps prepared input")
    if max_partitions is not None and (type(max_partitions) is not int or max_partitions < 1):
        raise ValueError("max_partitions must be positive")
    if type(min_free_bytes) is not int or min_free_bytes < 0:
        raise ValueError("Invalid disk guard")
    # Fail before creating an output when the requested optional backend is unavailable.
    resolver_runtime = ranked_resolver.runtime_identity(resolver_backend)
    if resume:
        if not root.is_dir():
            raise ValueError("Resume requires existing output")
    else:
        root.mkdir(parents=True, exist_ok=False)
    settings = {"threads": threads, "memory_limit": memory_limit, "max_temp_size": max_temp_size}
    reused, written = [], []
    with _run_lock(root), ExitStack() as stack:
        node_runtime = runtime or discover_runtime()
        metadata_node = stack.enter_context(MeasuredNode(node_runtime,
            root / ("node-" + uuid.uuid4().hex + ".log"), worker=WORKER, timeout=request_timeout))
        metadata = metadata_node.request({"op": "metadata"})
        node = metadata_node if resolver_backend == "npm" else stack.enter_context(MeasuredNode(
            node_runtime, root / ("ranked-node-" + uuid.uuid4().hex + ".log"),
            worker=ranked_resolver.NORMALIZER, timeout=request_timeout))
        generation = contract(algorithm, resolver_backend)
        with connection(root / ("inventory-" + uuid.uuid4().hex + ".duckdb"), **settings) as con:
            open_inputs(con, prepared_dir, inputs)
            groups = _coverage(con)
            if weighted:
                from .historical_production_events import validate_weighted_inputs
                validate_weighted_inputs(con, len(inputs["calendar"]))
        if sum(map(len, groups.values())) != inputs["selection"]["chosen_count"]:
            raise ValueError("Selection target-name coverage mismatch")
        plan = {"format": WEIGHTED_FORMAT if weighted else FORMAT,
                "prepared_dir": str(prepared_dir), "input_manifest_sha256": manifest_sha256,
                "scope": inputs["scope"], "generation_contract": generation, "runtime": metadata,
                "resolver_backend": resolver_backend,
                "resolver_settings": {"lookup_batch": resolver_lookup_batch,
                                      "workspace_mib": gpu_workspace_mib},
                "resolver_runtime": resolver_runtime,
                "partitions": {str(k): v for k, v in groups.items()}, "settings": settings,
                "full_selected_scope": inputs["scope"] == "FULL_SELECTED",
                "upstream_resolution_status": "PARTIAL", "ready_for_load": False}
        if weighted:
            plan["algorithm"] = algorithm
        plan_path = root / "run_plan.json"
        if plan_path.exists():
            if _read_json(plan_path) != plan or file_sha256(plan_path) != sha256(plan):
                raise ValueError("Run input, runtime, code, or partition plan changed")
        else:
            if resume:
                raise ValueError("Resume has no published run plan")
            _publish_json(plan_path, plan)
        receipts, pending = [], []
        for part, names in groups.items():
            receipt = _read_partition(root, sha256(plan), part, names, algorithm)
            if receipt:
                receipts.append(receipt)
                reused.append(part)
            else:
                pending.append(part)
        for part in pending[:max_partitions]:
            if shutil.disk_usage(root).free < min_free_bytes:
                raise ValueError("Free disk guard reached before partition")
            event(root, "RESOLVE_PARTITION", partition_id=part, target_names=len(groups[part]),
                  resolver_backend=resolver_backend)
            attempt = root / "partitions" / f"{part:03d}" / "attempts" / uuid.uuid4().hex
            attempt.mkdir(parents=True)
            part_started = time.monotonic()
            with connection(attempt / "working.duckdb", **settings) as con:
                open_inputs(con, prepared_dir, inputs)
                resolve_started = time.monotonic()
                if resolver_backend == "npm":
                    metrics = _resolve_partition(con, node, metadata, part, len(inputs["calendar"]))
                else:
                    metrics = ranked_resolver.resolve_partition(con, node, metadata, part,
                        len(inputs["calendar"]), backend=resolver_backend,
                        lookup_batch=resolver_lookup_batch, workspace_mib=gpu_workspace_mib)
                metrics["resolution_seconds"] = time.monotonic() - resolve_started
                event(root, "AGGREGATE_PARTITION", partition_id=part)
                if weighted:
                    from .historical_production_events import aggregate_partition_weighted
                    aggregation = aggregate_partition_weighted(con, len(inputs["calendar"]), part,
                                                               global_validated=True)
                else:
                    aggregation = aggregate_partition(con, len(inputs["calendar"]), part)
                metrics["aggregation"] = aggregation
                for name, table in part_files.items():
                    con.execute(f"COPY {table} TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(attempt / (name + ".parquet"))])
            if contract(algorithm, resolver_backend) != generation:
                raise ValueError("Generation code changed during partition")
            receipt = {"status": "COMPLETE", "partition_id": part, "names": groups[part],
                       "plan_sha256": sha256(plan), "metrics": metrics,
                       "files": [_record(attempt / (name + ".parquet")) for name in part_files],
                       "seconds": time.monotonic() - part_started, "memory": current_memory()}
            _publish_json(attempt / "receipt.json", receipt)
            parent = attempt.parent.parent
            _publish_json(parent / "complete.json", {"attempt": attempt.relative_to(parent).as_posix(),
                                                     "receipt_sha256": file_sha256(attempt / "receipt.json")})
            receipts.append(_read_partition(root, sha256(plan), part, groups[part], algorithm))
            written.append(part)
        receipts.sort(key=lambda r: r["partition_id"])
        if len(receipts) < len(groups):
            return {"run_status": "INCOMPLETE", "written_partitions": written, "reused_partitions": reused,
                    "remaining_partitions": len(groups) - len(receipts),
                    "full_selection_executed": False, "ready_for_load": False}
        event(root, "FINALIZE_INTERVAL_CACHE")
        cached = _finalize(root, inputs, plan, receipts, settings)
        directory = _within(root, cached["directory"])
        event(root, "WRITE_SNAPSHOT_PARQUETS")
        history = build_history(cache_dir=directory / "cache", cache_sha256=cached["cache_sha256"],
                                output=directory / "history", resume=(directory / "history").exists(),
                                max_snapshots=max_snapshots)
        verify_inputs(prepared_dir, manifest_sha256)
        if contract(algorithm, resolver_backend) != generation:
            raise ValueError("Generation code changed during run")
        if ranked_resolver.runtime_identity(resolver_backend) != resolver_runtime:
            raise ValueError("Resolver runtime changed during run")
        result = {"format": plan["format"], "run_status": history["run_status"], "plan_sha256": sha256(plan),
                  "partitions": receipts, "cache": cached, "history": history,
                  "scope": inputs["scope"], "full_selection_executed": inputs["scope"] == "FULL_SELECTED" and history["run_status"] == "COMPLETE",
                  "upstream_resolution_status": "PARTIAL", "ready_for_load": False}
        if history["run_status"] == "COMPLETE":
            path = root / "run_manifest.json"
            if path.exists():
                if _read_json(path) != result:
                    # written/reused dates are execution observations, not result identity.
                    prior = _read_json(path)
                    for key in ("written_dates", "reused_dates"):
                        result["history"][key] = prior["history"][key]
                    if prior != result:
                        raise ValueError("Published production result differs")
            else:
                _publish_json(path, result)
        event(root, "RUN_" + history["run_status"], seconds=time.monotonic() - started)
        return {"run_dir": str(root), "run_status": history["run_status"], "scope": inputs["scope"],
                "run_manifest_sha256": file_sha256(root / "run_manifest.json") if history["run_status"] == "COMPLETE" else None,
                "cache_dir": str(directory / "cache"), "cache_sha256": cached["cache_sha256"],
                "written_partitions": written, "reused_partitions": reused, "worker_metrics": dict(node.metrics),
                "resolver_backend": resolver_backend, "resolver_runtime": resolver_runtime,
                "elapsed_seconds": time.monotonic() - started, "memory": current_memory(),
                "full_selection_executed": result["full_selection_executed"], "ready_for_load": False}


def verify_run(*, run_dir, manifest_sha256):
    root = _path(run_dir)
    path = root / "run_manifest.json"
    if file_sha256(path) != manifest_sha256:
        raise ValueError("Run manifest SHA mismatch")
    result = _read_json(path)
    plan = _read_json(root / "run_plan.json")
    algorithm = plan.get("algorithm", DEFAULT_ALGORITHM)
    backend = plan.get("resolver_backend", "npm")
    resolver_settings = plan.get("resolver_settings", {"lookup_batch": 1024, "workspace_mib": 128})
    ranked_resolver.validate_options(backend, resolver_settings["lookup_batch"], resolver_settings["workspace_mib"])
    _part_files(algorithm)
    expected_format = WEIGHTED_FORMAT if algorithm == WEIGHTED_ALGORITHM else FORMAT
    if (plan["format"] != expected_format or result["format"] != expected_format
            or sha256(plan) != result["plan_sha256"] or plan["generation_contract"] != contract(algorithm, backend)
            or plan.get("resolver_runtime", {}).get("backend") != backend
            or result["run_status"] != "COMPLETE" or result["ready_for_load"] is not False):
        raise ValueError("Production run contract mismatch")
    inputs = verify_inputs(plan["prepared_dir"], plan["input_manifest_sha256"])
    if (result["scope"] != inputs["scope"] or plan["scope"] != inputs["scope"]
            or plan["full_selected_scope"] != (inputs["scope"] == "FULL_SELECTED")
            or result["full_selection_executed"] != (inputs["scope"] == "FULL_SELECTED")
            or result["upstream_resolution_status"] != "PARTIAL"):
        raise ValueError("Production scope mismatch")
    receipts = [_read_partition(root, sha256(plan), int(part), names, algorithm)
                for part, names in plan["partitions"].items()]
    if receipts != result["partitions"]:
        receipts.sort(key=lambda r: r["partition_id"] if r else -1)
        if receipts != result["partitions"]:
            raise ValueError("Partition coverage/receipt mismatch")
    cached = result["cache"]
    if _read_json(root / "cache_complete.json") != cached:
        raise ValueError("Cache completion pointer mismatch")
    directory = _verify_cache_chain(root, cached, inputs, plan, receipts)
    with connection(root / ("verify-run-" + uuid.uuid4().hex + ".duckdb"), **plan["settings"]) as con:
        if algorithm == WEIGHTED_ALGORITHM:
            from .historical_production_events import validate_weighted_inputs
            open_inputs(con, plan["prepared_dir"], inputs)
            validate_weighted_inputs(con, len(inputs["calendar"]))
        else:
            con.read_parquet(str(Path(plan["prepared_dir"]) / "target_names.parquet"), hive_partitioning=False).create_view("target_names")
        if {str(k): v for k, v in _coverage(con).items()} != plan["partitions"]:
            raise ValueError("Prepared input partition coverage mismatch")
        _merge_partitions(con, root, inputs, plan, receipts)
        _check_cache_derivation(con, directory / "cache")
    verify_history(run_dir=directory / "history", cache_dir=directory / "cache",
                   cache_sha256=cached["cache_sha256"],
                   run_manifest_sha256=result["history"]["run_manifest_sha256"])
    return {"verified": True, "scope": inputs["scope"], "partitions": len(receipts),
            "snapshots": len(inputs["calendar"]), "upstream_resolution_status": "PARTIAL", "ready_for_load": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("h1-dir", "h1-manifest-sha256", "profile-manifest", "profile-manifest-sha256",
                 "selection-csv", "selection-sha256", "output"):
        p.add_argument("--" + name, required=True)
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument("--sample-name", action="append", dest="sample_names")
    scope.add_argument("--full-selected", action="store_true")
    p.add_argument("--partition-count", type=int, default=128)
    r = sub.add_parser("run")
    for name in ("prepared-dir", "manifest-sha256", "output"):
        r.add_argument("--" + name, required=True)
    r.add_argument("--resume", action="store_true")
    r.add_argument("--allow-full-selected", action="store_true")
    r.add_argument("--max-partitions", type=int)
    r.add_argument("--max-snapshots", type=int)
    r.add_argument("--algorithm", choices=(DEFAULT_ALGORITHM, WEIGHTED_ALGORITHM), default=DEFAULT_ALGORITHM)
    r.add_argument("--resolver-backend", choices=("npm", "cpu", "gpu"), default="npm")
    r.add_argument("--resolver-lookup-batch", type=int, default=1024)
    r.add_argument("--gpu-workspace-mib", type=int, default=128)
    v = sub.add_parser("verify")
    v.add_argument("--run-dir", required=True)
    v.add_argument("--manifest-sha256", required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    result = {"prepare": prepare, "run": run, "verify": verify_run}[command](**args)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
