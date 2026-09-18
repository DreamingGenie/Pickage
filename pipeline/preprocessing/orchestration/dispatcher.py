"""One timer tick: select and resume at most one completed weekly raw snapshot.

The deployment wrapper owns the shared ingest/Curated flock. This module also
serializes dispatcher invocations on one host. It never collects or loads a DB.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import traceback

from pipeline.preprocessing.curated.storage import json_bytes, put_immutable, read_optional
from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.orchestration.contracts import iso_day
from pipeline.preprocessing.orchestration.intake import _check_marker
from pipeline.preprocessing.orchestration.storage import (
    BUCKET, WaitingInput, atomic_json, host_lock, pinned, required, save_event, save_state,
)
from pipeline.preprocessing.orchestration.weekly_parent import CURRENT, read_bundle
from pipeline.preprocessing.orchestration.weekly_request import RAW_BUCKET, build_request

OPS = "_ops/preprocessing"
RAW_OPS = "_ops/weekly/"
MAX_FAILURES = 10


def _documents(s3):
    """Paginated discovery includes unfinished older weeks, preventing gaps."""
    result = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=RAW_BUCKET, Prefix=RAW_OPS):
        for item in page.get("Contents", []):
            key = item["Key"]
            parts = key.removeprefix(RAW_OPS).split("/")
            if len(parts) != 2 or parts[1] != "run.json":
                continue
            snapshot = parts[0]
            iso_day(snapshot)
            result[snapshot] = json.loads(required(s3, RAW_BUCKET, key))
    return result


def _history(s3):
    """Walk completed lineage; current alone is not a completion ledger."""
    pointer = json.loads(required(s3, BUCKET, CURRENT))
    history = {}
    while pointer:
        snapshot = pointer["snapshot"]
        iso_day(snapshot)
        if snapshot in history:
            raise ValueError("Curated parent lineage contains a cycle")
        bundle = read_bundle(s3, pointer)
        history[snapshot] = bundle["request"]
        parent = bundle["request"].get("parent_bundle")
        if parent and parent["snapshot"] >= snapshot:
            raise ValueError("Curated parent chronology is invalid")
        pointer = parent
    return history


def _verify_raw(s3, request):
    for ref in request["raw_refs"].values():
        pinned(s3, ref)
        _check_marker(s3, ref)


def _read_state(s3, prefix, local):
    remote = read_optional(s3, BUCKET, prefix + "/status.json")
    candidates = [json.loads(remote[0])] if remote else []
    if (local / "status.json").exists():
        candidates.append(json.loads((local / "status.json").read_bytes()))
    # Retain the newer local failure when MinIO was unavailable during recording.
    return max(candidates, key=lambda value: value.get("updated_at", "")) if candidates else {}


def _record(s3, prefix, local, state):
    try:
        save_state(s3, prefix, local, state)
        save_event(s3, prefix, local, state)
    except Exception:
        # save_state writes local evidence first; the service journal records
        # the remote logging failure as well as the original error.
        traceback.print_exc()
        raise
    print(json.dumps(state, ensure_ascii=False), flush=True)


def _error(s3, prefix, local, state, error, now):
    waiting = isinstance(error, WaitingInput)
    failures = state.get("consecutive_failures", 0) + (0 if waiting else 1)
    blocked = not waiting and (isinstance(error, (ValueError, KeyError, TypeError)) or failures >= MAX_FAILURES)
    state.update(status="WAITING_INPUT" if waiting else "BLOCKED" if blocked else "FAILED",
                 consecutive_failures=failures,
                 error={"type": type(error).__name__, "message": str(error)},
                 finished_at=now.isoformat(),
                 next_retry_at=None if blocked else (now + timedelta(minutes=min(60, 10 * 2 ** min(max(failures - 1, 0), 3)))).isoformat())
    atomic_json(local / "status.json", {**state, "updated_at": now.isoformat()})
    _record(s3, prefix, local, state)
    return 2 if waiting else 1


def dispatch(s3, work_dir, *, retry_snapshot=None, now=None):
    """Caller must hold the dispatcher lock (CLI does); injection supports tests."""
    fixed_clock = now is not None
    now = now or datetime.now(timezone.utc)
    work_dir = Path(work_dir).resolve()
    if retry_snapshot:
        iso_day(retry_snapshot)
    history = _history(s3)  # A validated initial baseline is mandatory.
    baseline = min(history)
    weeks = _documents(s3)
    # Also check completed weekly inputs even if a producer state was removed.
    for snapshot in sorted(set(weeks) | set(history)):
        if snapshot <= baseline:
            continue
        prefix = f"{OPS}/{snapshot}"
        local = work_dir / "dispatch" / snapshot
        state = _read_state(s3, prefix, local)
        state.update(snapshot=snapshot, run_id=f"curated-weekly-{snapshot.replace('-', '')}")
        try:
            if snapshot in history:
                _verify_raw(s3, history[snapshot])
                # Immutable bundle lineage is authoritative, not mutable status.
                if state.get("status") != "COMPLETE":
                    state.update(status="COMPLETE", error=None, consecutive_failures=0, next_retry_at=None)
                    _record(s3, prefix, local, state)
                continue
            if snapshot < max(history):
                raise ValueError("Unprocessed snapshot is older than current Curated history; explicit backfill required")
            if state.get("status") == "BLOCKED" and retry_snapshot != snapshot:
                print(json.dumps({"snapshot": snapshot, "status": "BLOCKED", "reason": "manual retry required"}), flush=True)
                return 1
            if retry_snapshot == snapshot:
                state.update(consecutive_failures=0, next_retry_at=None)
            if state.get("next_retry_at") and datetime.fromisoformat(state["next_retry_at"]) > now:
                return 0
            if weeks[snapshot].get("status") != "SUCCEEDED":
                raise WaitingInput("Raw weekly run has not succeeded")
            if state.get("status") == "RUNNING":
                # The host lock is free, so a previous process died without a
                # final record. Count it, instead of retrying OOM forever.
                state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
                if state["consecutive_failures"] >= MAX_FAILURES:
                    state.update(status="BLOCKED", next_retry_at=None,
                                 error={"type": "InterruptedRun", "message": "Interrupted attempts exhausted the retry budget"},
                                 finished_at=now.isoformat())
                    _record(s3, prefix, local, state)
                    return 1
            state.update(status="RUNNING", attempt=state.get("attempt", 0) + 1,
                         started_at=now.isoformat(), error=None, next_retry_at=None)
            _record(s3, prefix, local, state)
            request_key = prefix + "/request.json"
            stored = read_optional(s3, BUCKET, request_key)
            if stored:
                request = json.loads(stored[0])
            else:
                request = build_request(s3, snapshot, state["run_id"], work_dir,
                    options={"workers": 2, "threads": 2, "memory_limit": "2GB", "repository_engine": "duckdb"})
                put_immutable(s3, BUCKET, request_key, json_bytes(request))
            if request["snapshot"] != snapshot or request["run_id"] != state["run_id"]:
                raise ValueError("Saved dispatcher request identity differs")
            atomic_json(work_dir / "requests" / (state["run_id"] + ".json"), request)
            _verify_raw(s3, request)
            runner.run(request, s3, work_dir)
            state.update(status="COMPLETE", consecutive_failures=0, error=None,
                         next_retry_at=None, finished_at=datetime.now(timezone.utc).isoformat())
            _record(s3, prefix, local, state)
            return 0  # Bound each tick to one snapshot.
        except Exception as error:
            traceback.print_exc()
            failed_at = now if fixed_clock else datetime.now(timezone.utc)
            return _error(s3, prefix, local, state, error, failed_at)
    print(json.dumps({"status": "IDLE", "reason": "no pending weekly snapshots"}), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path("data/orchestration"))
    parser.add_argument("--retry-snapshot", help="Explicitly reset retries; never repin or overwrite inputs")
    args = parser.parse_args(argv)
    from pipeline.minio.ingest_raw import client
    s3 = None
    try:
        s3 = client()
        with host_lock(s3, namespace="dispatcher"):
            code = dispatch(s3, args.work_dir, retry_snapshot=args.retry_snapshot)
            _record(s3, OPS + "/_dispatcher", args.work_dir / "dispatch" / "_dispatcher",
                    {"status": "TICK_FINISHED", "exit_code": code})
            return code
    except Exception as error:
        # Discovery/bootstrap/connection failures occur before a snapshot is selected.
        local = args.work_dir / "dispatch" / "_dispatcher"
        traceback.print_exc()
        state = {"status": "WAITING_INPUT" if isinstance(error, WaitingInput) else "FAILED",
                 "error": {"type": type(error).__name__, "message": str(error)}}
        atomic_json(local / "status.json", state)
        if s3 is not None:
            try:
                _record(s3, OPS + "/_dispatcher", local, state)
            except Exception:
                pass  # Original failure and local evidence remain intact.
        print(json.dumps(state, ensure_ascii=False), flush=True)
        return 2 if isinstance(error, WaitingInput) else 1


if __name__ == "__main__":
    raise SystemExit(main())
