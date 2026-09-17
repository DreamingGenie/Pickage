"""Container and Spark event-log measurements for bounded experiment runs.

Container counters are sampled from the current cgroup v2. Network counters use
``/proc/self/net/dev``; with host networking those counters may describe the
host network namespace and must not be interpreted as container-isolated IO.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time


def _read_int(path):
    try:
        value = Path(path).read_text(encoding="ascii").strip()
        return None if value == "max" else int(value)
    except (OSError, ValueError):
        return None


def _key_values(path):
    result = {}
    try:
        for line in Path(path).read_text(encoding="ascii").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                try:
                    result[parts[0]] = int(parts[1])
                except ValueError:
                    continue
    except OSError:
        pass
    return result


def _find_cgroup(proc_cgroup="/proc/self/cgroup", mountinfo="/proc/self/mountinfo"):
    """Resolve the unified cgroup-v2 directory for this process, or return None."""
    try:
        rel = next(line.split("::", 1)[1].strip() for line in Path(proc_cgroup).read_text().splitlines()
                   if line.startswith("0::"))
        for line in Path(mountinfo).read_text().splitlines():
            left, right = line.split(" - ", 1)
            fields = left.split()
            fs = right.split()
            if fs[0] != "cgroup2":
                continue
            mount_root, mount_point = Path(fields[3]), Path(fields[4])
            relative = Path(rel.lstrip("/"))
            try:
                suffix = relative.relative_to(mount_root.relative_to("/"))
            except ValueError:
                suffix = relative
            return mount_point / suffix
    except (OSError, StopIteration, ValueError, IndexError):
        return None
    return None


def _network_bytes(path):
    totals = {"rx_bytes": 0, "tx_bytes": 0}
    found = False
    try:
        for line in Path(path).read_text(encoding="ascii").splitlines()[2:]:
            if ":" not in line:
                continue
            _, values = line.split(":", 1)
            columns = values.split()
            if len(columns) >= 9:
                totals["rx_bytes"] += int(columns[0])
                totals["tx_bytes"] += int(columns[8])
                found = True
    except (OSError, ValueError):
        return {"rx_bytes": None, "tx_bytes": None}
    return totals if found else {"rx_bytes": None, "tx_bytes": None}


def _host_name(value):
    if not value:
        return None
    host = str(value)
    if host.startswith("[") and "]" in host:
        return host[1:host.index("]")]
    # Spark executor endpoints are host:port. Leave raw IPv6 literals intact.
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def read_snapshot(*, cgroup_dir=None, proc_cgroup="/proc/self/cgroup",
                  mountinfo="/proc/self/mountinfo", net_dev="/proc/self/net/dev",
                  timestamp=None):
    """Read one JSON-safe snapshot; unavailable counters remain ``None``."""
    cg = Path(cgroup_dir) if cgroup_dir is not None else _find_cgroup(proc_cgroup, mountinfo)
    cpu = _key_values(cg / "cpu.stat") if cg else {}
    events = _key_values(cg / "memory.events") if cg else {}
    memory_stat = _key_values(cg / "memory.stat") if cg else {}
    io = {}
    if cg:
        try:
            for line in (cg / "io.stat").read_text(encoding="ascii").splitlines():
                parts = line.split()
                for pair in parts[1:]:
                    key, val = pair.split("=", 1)
                    io[key] = io.get(key, 0) + int(val)
        except (OSError, ValueError):
            io = {}
    result = {
        "timestamp": time.time() if timestamp is None else timestamp,
        "scope": "current_cgroup_v2" if cg else None,
        "cpu": {key: cpu.get(key) for key in ("usage_usec", "user_usec", "system_usec")},
        "memory": {"current": _read_int(cg / "memory.current") if cg else None,
                   "peak": _read_int(cg / "memory.peak") if cg else None,
                   "stat": {key: memory_stat.get(key) for key in ("anon", "file", "kernel", "sock")},
                   "events": {key: events.get(key) for key in ("low", "high", "max", "oom", "oom_kill", "oom_group_kill")}},
        "io": {key: io.get(key) for key in ("rbytes", "wbytes", "rios", "wios")},
        "network": _network_bytes(net_dev),
        "limitations": {"cpu_scope": "container cgroup aggregate; includes all processes in cgroup",
                        "memory_peak_scope": "cgroup-lifetime high-water mark; may predate sampling",
                        "network_scope": "proc self network namespace; not container isolated with host networking"},
    }
    return result


def _counter_delta(before, after):
    """Return a delta and whether a decreasing counter signals a reset."""
    if before is None or after is None:
        return None, False
    if after < before:
        return None, True
    return after - before, False


def snapshot_delta(before, after):
    """Counter deltas plus gauges, preserving missing measurements as null."""
    resets = {}

    def deltas(section, prior, current):
        values, flags = {}, {}
        for key in prior:
            values[key], flags[key] = _counter_delta(prior[key], current[key])
        resets[section] = flags
        return values

    cpu = deltas("cpu", before["cpu"], after["cpu"])
    memory_events = deltas("memory.events", before["memory"]["events"], after["memory"]["events"])
    io = deltas("io", before["io"], after["io"])
    network = deltas("network", before["network"], after["network"])
    # Older callers and stored samples may predate memory.stat support.
    memory_stat = after["memory"].get("stat") or {}
    return {"elapsed_seconds": after["timestamp"] - before["timestamp"], "cpu": cpu,
            "memory": {"current": after["memory"]["current"], "peak": after["memory"]["peak"],
                       "stat": {key: memory_stat.get(key) for key in ("anon", "file", "kernel", "sock")},
                       "events": memory_events}, "io": io, "network": network,
            "counter_resets": resets}


class Sampler:
    """Periodic sampler with context-manager lifecycle and aggregate summary."""
    def __init__(self, interval=1.0, *, snapshot_fn=read_snapshot):
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.interval, self.snapshot_fn = interval, snapshot_fn
        self.samples = []
        self._stop = threading.Event()
        self._thread = None

    def sample(self):
        item = self.snapshot_fn()
        self.samples.append(item)
        return item

    def start(self):
        if self._thread is not None:
            raise RuntimeError("sampler already started")
        self.sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.wait(self.interval):
            self.sample()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self.sample()
            self._thread = None
        return self.summary()

    def summary(self):
        return {"sample_count": len(self.samples), "samples": self.samples,
                "delta": snapshot_delta(self.samples[0], self.samples[-1]) if len(self.samples) >= 2 else None}

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()


def parse_event_log(path):
    """Summarize Spark 3.5 JSON event logs, deduping task ends and heartbeats.

    Task-end metrics are authoritative. Heartbeat accumulator updates are kept
    by max value per task/accumulator, so repeated cumulative updates do not add
    the same work repeatedly. Executor CPU is available only when Spark reports
    executorCpuTime for task ends.
    """
    executors, hosts, stages, tasks, heartbeat, stage_names = {}, set(), {}, {}, {}, {}
    malformed_line_count = 0
    application_end_seen = False
    in_progress = str(path).endswith(".inprogress")

    metric_fields = {
        "executor_cpu_time_ns": ("Executor CPU Time",),
        "executor_run_time_ms": ("Executor Run Time",),
        "shuffle_local_read_bytes": ("Shuffle Read Metrics", "Local Bytes Read"),
        "shuffle_remote_read_bytes": ("Shuffle Read Metrics", "Remote Bytes Read"),
        "shuffle_write_bytes": ("Shuffle Write Metrics", "Shuffle Bytes Written"),
        "memory_spill_bytes": ("Memory Bytes Spilled",),
        "disk_spill_bytes": ("Disk Bytes Spilled",),
    }

    def stage_row(stage_id, attempt):
        key = (int(stage_id), int(attempt or 0))
        row = stages.setdefault(key, {"stage_id": key[0], "stage_attempt_id": key[1], "task_count": 0,
            "executors": set(), "_metric_sums": {name: 0 for name in metric_fields},
            "_metric_counts": {name: 0 for name in metric_fields}})
        row["job_group_id"] = stage_names.get(key)
        row["stage_name"] = stage_names.get(key)
        return row

    def nested_number(obj, path_parts):
        for part in path_parts:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(part)
        return obj if isinstance(obj, (int, float)) and not isinstance(obj, bool) else None

    with Path(path).open(encoding="utf-8-sig") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                malformed_line_count += 1
                continue
            if not isinstance(event, dict):
                malformed_line_count += 1
                continue
            name = event.get("Event", "")
            if name == "SparkListenerApplicationEnd":
                application_end_seen = True
            elif name == "SparkListenerStageSubmitted":
                info = event.get("Stage Info") or {}
                sid = event.get("Stage ID", info.get("Stage ID"))
                attempt = event.get("Stage Attempt ID", info.get("Stage Attempt ID", 0))
                props = event.get("Properties") or {}
                group_id = props.get("spark.jobGroup.id")
                if sid is not None and group_id is not None:
                    stage_names[(int(sid), int(attempt or 0))] = str(group_id)
                    existing = stages.get((int(sid), int(attempt or 0)))
                    if existing is not None:
                        existing["job_group_id"] = str(group_id)
                        existing["stage_name"] = str(group_id)
            elif name == "SparkListenerExecutorAdded":
                info = event.get("Executor Info") or {}
                executor_id = str(event.get("Executor ID", "unknown"))
                hostport = info.get("Host") or ""
                host = _host_name(hostport)
                executors[executor_id] = host
                if host:
                    hosts.add(host)
            elif name == "SparkListenerTaskEnd":
                info = event.get("Task Info") or {}
                taskid = info.get("Task ID")
                if taskid is None:
                    continue
                key = (int(event.get("Stage ID", 0)), int(event.get("Stage Attempt ID", 0)), int(taskid))
                if key in tasks:
                    continue
                m = event.get("Task Metrics")
                executor = str(info.get("Executor ID", "unknown"))
                host = executors.get(executor) or _host_name(info.get("Host"))
                if host:
                    hosts.add(str(host))
                row = stage_row(key[0], key[1])
                row["task_count"] += 1
                for field, metric_path in metric_fields.items():
                    value = nested_number(m, metric_path)
                    if value is not None:
                        row["_metric_sums"][field] += value
                        row["_metric_counts"][field] += 1
                row["executors"].add(executor)
                tasks[key] = True
            elif name == "SparkListenerExecutorMetricsUpdate":
                for update in event.get("Accumulator Updates", event.get("accumUpdates", [])) or []:
                    # Spark JSON's compact representation is [taskId, stageId,
                    # stageAttemptId, [[accId, name, update, value], ...]].
                    if isinstance(update, list) and len(update) >= 4:
                        tid, sid, attempt, accs = update[:4]
                        for acc in accs or []:
                            if isinstance(acc, list) and len(acc) >= 3:
                                aid, val = str(acc[0]), acc[2]
                                if isinstance(val, (int, float)):
                                    hk = (int(sid), int(attempt or 0), int(tid), aid)
                                    heartbeat[hk] = max(heartbeat.get(hk, val), val)
                        continue
                    if not isinstance(update, dict):
                        continue
                    tid, sid = update.get("Task ID", update.get("taskId")), update.get("Stage ID", update.get("stageId"))
                    if tid is None or sid is None:
                        continue
                    attempt = update.get("Stage Attempt ID", update.get("stageAttemptId", 0))
                    accs = update.get("Accumulables", update.get("accumUpdates", [])) or []
                    for acc in accs:
                        if not isinstance(acc, dict):
                            continue
                        aid = str(acc.get("ID", acc.get("id", acc.get("Name", acc.get("name", "unknown")))))
                        val = acc.get("Update", acc.get("Value", acc.get("update", acc.get("value"))))
                        if isinstance(val, (int, float)):
                            hk = (int(sid), int(attempt or 0), int(tid), aid)
                            heartbeat[hk] = max(heartbeat.get(hk, val), val)
    summarized_stages = []
    for _, row in sorted(stages.items()):
        coverage = {}
        for field in metric_fields:
            reported = row["_metric_counts"][field]
            expected = row["task_count"]
            row[field] = row["_metric_sums"][field] if reported == expected else None
            coverage[field] = {"reported_tasks": reported, "expected_tasks": expected,
                               "incomplete": reported != expected}
        row["metric_coverage"] = coverage
        del row["_metric_sums"]
        del row["_metric_counts"]
        summarized_stages.append({**row, "executors": sorted(row["executors"])})

    completed = application_end_seen and not in_progress
    return {"format": "spark_event_log_json_lines", "spark_version": "3.5.x",
            "completed": completed, "incomplete_log": malformed_line_count > 0 or not completed,
            "malformed_line_count": malformed_line_count,
            "executor_hosts": sorted(hosts), "executors": [{"executor_id": k, "host": v}
                for k, v in sorted(executors.items())], "heartbeat_accumulator_count": len(heartbeat),
            "heartbeat_accumulators": [{"stage_id": k[0], "stage_attempt_id": k[1],
                "task_id": k[2], "accumulator_id": k[3], "max_update": v}
                for k, v in sorted(heartbeat.items())],
            "stages": summarized_stages,
            "limitations": {"task_metrics": "summed once from unique TaskEnd events; a stage metric is null if any task did not report it",
                            "heartbeat": "cumulative updates retained as per-task maxima and excluded from totals to avoid double counting"}}
