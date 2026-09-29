"""Summarize repository-stage Spark listener events.

This is an experiment-only reader.  It deliberately reports summed task
metrics (work) and does not pretend that they are wall-clock elapsed time.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator


METRICS = {
    "executor_run_time_ms": ("Executor Run Time",),
    "executor_cpu_time_ns": ("Executor CPU Time",),
    "executor_deserialize_time_ms": ("Executor Deserialize Time",),
    "result_serialization_time_ms": ("Result Serialization Time",),
    "jvm_gc_time_ms": ("JVM GC Time",),
    "memory_spill_bytes": ("Memory Bytes Spilled",),
    "disk_spill_bytes": ("Disk Bytes Spilled",),
    "input_bytes": ("Input Metrics", "Bytes Read"),
    "output_bytes": ("Output Metrics", "Bytes Written"),
    "shuffle_local_read_bytes": ("Shuffle Read Metrics", "Local Bytes Read"),
    "shuffle_remote_read_bytes": ("Shuffle Read Metrics", "Remote Bytes Read"),
    "shuffle_fetch_wait_time_ms": ("Shuffle Read Metrics", "Fetch Wait Time"),
    "shuffle_write_bytes": ("Shuffle Write Metrics", "Shuffle Bytes Written"),
}


def _number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _nested(obj: Any, path: tuple[str, ...]) -> int | float | None:
    for part in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return _number(obj)


def _profile(value: Any) -> tuple[str, str] | None:
    """Return (profile id, action) for the instrumentation group id."""
    if not isinstance(value, str) or not value.startswith("repository-profile:"):
        return None
    pieces = value.split(":", 2)
    if len(pieces) != 3 or not pieces[1] or not pieces[2]:
        return None
    return value, pieces[2]


def _event_lines(events: Path) -> Iterator[tuple[Path, int, str]]:
    files = sorted(p for p in events.rglob("*") if p.is_file()) if events.is_dir() else [events]
    for path in files:
        # Hadoop/Spark event-log directories commonly contain per-file .crc
        # sidecars.  They are binary checksums, not JSON event streams.
        if path.name.startswith(".") or path.name.endswith(".crc"):
            continue
        if path.suffix.lower() in {".gz", ".bz2", ".zip", ".snappy", ".lz4", ".zstd"}:
            raise ValueError(f"compressed event logs are unsupported: {path}")
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line_number, line in enumerate(stream, 1):
                yield path, line_number, line


def summarize(events: str | Path) -> dict[str, Any]:
    """Read JSON-lines Spark event logs under *events* and return a summary."""
    event_path = Path(events)
    if not event_path.exists():
        raise FileNotFoundError(event_path)
    stage_labels: dict[int, list[tuple[str, str]]] = {}
    stage_owner: dict[int, tuple[str, str]] = {}
    stage_attempt_owner: dict[tuple[int, int], tuple[str, str]] = {}
    tasks: dict[tuple[int, int, int], dict[str, Any]] = {}
    malformed: list[dict[str, Any]] = []
    applications = 0
    application_ends = 0
    job_count = 0
    event_count = 0

    for path, line_number, line in _event_lines(event_path):
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("event is not an object")
        except (json.JSONDecodeError, TypeError, ValueError):
            malformed.append({"file": str(path), "line": line_number})
            continue
        event_count += 1
        name = event.get("Event")
        if name == "SparkListenerApplicationStart":
            applications += 1
        elif name == "SparkListenerApplicationEnd":
            application_ends += 1
        elif name == "SparkListenerJobStart":
            group = _profile((event.get("Properties") or {}).get("spark.jobGroup.id"))
            if group:
                job_count += 1
                for stage_id in event.get("Stage IDs", []) or []:
                    try:
                        sid = int(stage_id)
                    except (TypeError, ValueError):
                        continue
                    labels = stage_labels.setdefault(sid, [])
                    if group not in labels:
                        labels.append(group)
                    stage_owner.setdefault(sid, group)
        elif name == "SparkListenerStageSubmitted":
            info = event.get("Stage Info") or {}
            try:
                sid = int(event.get("Stage ID", info.get("Stage ID")))
                attempt = int(event.get("Stage Attempt ID", info.get("Stage Attempt ID", 0)) or 0)
            except (TypeError, ValueError):
                continue
            group = _profile((event.get("Properties") or {}).get("spark.jobGroup.id"))
            if group:
                stage_attempt_owner.setdefault((sid, attempt), group)
                labels = stage_labels.setdefault(sid, [])
                if group not in labels:
                    labels.append(group)
                stage_owner.setdefault(sid, group)
        elif name == "SparkListenerTaskEnd":
            info = event.get("Task Info") or {}
            try:
                sid = int(event.get("Stage ID"))
                attempt = int(event.get("Stage Attempt ID", 0) or 0)
                task_id = int(info.get("Task ID"))
            except (TypeError, ValueError):
                continue
            key = (sid, attempt, task_id)
            if key in tasks:
                continue
            reason = event.get("Task End Reason")
            reason_name = reason.get("Reason") if isinstance(reason, dict) else reason
            successful = str(reason_name or "").lower() == "success"
            metrics = event.get("Task Metrics") or {}
            values = {name: _nested(metrics, path) for name, path in METRICS.items()}
            tasks[key] = {"stage_id": sid, "stage_attempt_id": attempt,
                          "successful": successful, "metrics": values}

    if applications > 1:
        raise ValueError("event directory contains multiple Spark applications; use one log per summary")

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for task in tasks.values():
        owner = stage_attempt_owner.get((task["stage_id"], task["stage_attempt_id"]))
        if owner is None:
            owner = stage_owner.get(task["stage_id"])
        if owner is None:
            continue
        profile_id, action = owner
        row = grouped.setdefault((profile_id, action), {
            "profile_id": profile_id, "action": action, "stage_ids": [],
            "shared_stage_count": 0, "task_attempt_count": 0,
            "successful_task_count": 0, "failed_task_count": 0,
            "metrics": {name: 0 for name in METRICS},
            "metric_coverage": {name: 0 for name in METRICS},
        })
        sid = task["stage_id"]
        if sid not in row["stage_ids"]:
            row["stage_ids"].append(sid)
            if len(stage_labels.get(sid, [])) > 1:
                row["shared_stage_count"] += 1
        row["task_attempt_count"] += 1
        if task["successful"]:
            row["successful_task_count"] += 1
        else:
            row["failed_task_count"] += 1
        for name, value in task["metrics"].items():
            if value is not None:
                row["metrics"][name] += value
                row["metric_coverage"][name] += 1

    for row in grouped.values():
        row["stage_ids"].sort()
    return {
        "format": "spark_repository_profile_summary_v1",
        "event_path": str(event_path),
        "applications": applications,
        "application_ends": application_ends,
        "profile_job_count": job_count,
        "stage_count": len(stage_labels),
        "task_attempt_count": len(tasks),
        "malformed_line_count": len(malformed),
        "incomplete_log": bool(malformed) or application_ends < applications or event_count == 0 or (not applications and bool(tasks)),
        "malformed_lines": malformed,
        "profiles": sorted(grouped.values(), key=lambda row: (row["profile_id"], row["action"])),
        "limitations": {
            "metric_basis": "task metrics are summed once per unique (stage, stage attempt, task id)",
            "time_semantics": "executor_run_time_ms and executor_cpu_time_ns are summed task work, not wall-clock time",
            "shared_stages": "a stage attempt is assigned from StageSubmitted job group when available; otherwise the stage is assigned to its first profile",
            "jvm_gc_time": "JVM GC time is reported per task and may overlap across concurrently running tasks",
            "truncated_final_line": "a malformed or truncated JSON line marks the log incomplete",
        },
    }


def write_summary(events: str | Path, output: str | Path) -> dict[str, Any]:
    result = summarize(events)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize repository Spark event logs")
    parser.add_argument("--events", required=True, type=Path, help="event log file or directory")
    parser.add_argument("--output", required=True, type=Path, help="new summary JSON path")
    args = parser.parse_args(argv)
    write_summary(args.events, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
