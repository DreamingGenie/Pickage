"""Baseline-aware app-EC2 guard for repository22.

One pre-existing, known failed loader is excluded from restart-count checks only
after its exact container ID and log signature are captured. Every other
pre-existing container remains covered by the normal stable-service checks.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen


RUN = os.environ.get("PICKAGE_EXPERIMENT_RUN", "repository22-20260917-a1")
ROOT = Path("/home/ubuntu/pickage-experiments") / RUN
KNOWN_NAME = "pickage-app-similarity-loader-1"
KNOWN_SIGNATURE = "MinIO credentials not found: pipeline/minio/.env.loader"


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT, timeout=10).strip()


def _inspect(ids: list[str]) -> list[dict]:
    return json.loads(docker("inspect", *ids)) if ids else []


def _find_known_baseline() -> tuple[str, dict]:
    ids = docker("ps", "-q").split()
    matches = [item for item in _inspect(ids)
               if item.get("Name", "").lstrip("/") == KNOWN_NAME]
    if len(matches) != 1:
        raise RuntimeError("Known failed loader baseline is not uniquely running")
    item = matches[0]
    state = item.get("State") or {}
    if not state.get("Running"):
        raise RuntimeError("Known failed loader baseline is not running")
    logs = docker("logs", "--tail", "200", item["Id"])
    if KNOWN_SIGNATURE not in logs:
        raise RuntimeError("Known failed loader log signature is missing")
    return item["Id"], item


def capture_baseline() -> dict:
    known_id, item = _find_known_baseline()
    rows = _inspect(docker("ps", "-q").split())
    original = {row["Id"]: row.get("RestartCount", 0) for row in rows
                if row["Id"] != known_id}
    record = {"name": KNOWN_NAME, "container_id": known_id,
              "signature": KNOWN_SIGNATURE, "captured_at": time.time(),
              "restart_count": item.get("RestartCount", 0),
              "excluded_from_restart_monitor": True,
              "stable_container_ids": sorted(original)}
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "preexisting-failure.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"known_id": known_id, "original": original, "record": record}


def check_known_failure(known_id: str) -> dict:
    rows = _inspect([known_id])
    if len(rows) != 1 or rows[0].get("Id") != known_id:
        raise RuntimeError("Known failed loader container was replaced")
    state = rows[0].get("State") or {}
    if not state.get("Running") or not state.get("Restarting") or state.get("ExitCode") != 1:
        raise RuntimeError("Known failed loader recovered or stopped")
    logs = docker("logs", "--tail", "200", known_id)
    tail = [line.strip() for line in logs.splitlines() if line.strip()][-3:]
    allowed = {KNOWN_SIGNATURE, 'Local: copy .env.example to .env', 'Server: see pipeline/minio/README.md'}
    if KNOWN_SIGNATURE not in logs or not tail or any(line not in allowed for line in tail):
        raise RuntimeError("Known failed loader error signature changed")
    return {"name": KNOWN_NAME, "container_id": known_id,
            "running": True, "signature_present": True, "skipped": True}


def check_stable(original: dict) -> None:
    rows = {row["Id"]: row for row in _inspect(list(original))}
    if set(rows) != set(original):
        raise RuntimeError("Existing stable container was removed or replaced")
    for cid, row in rows.items():
        state = row.get("State") or {}
        if not state.get("Running") or row.get("RestartCount") != original[cid]:
            raise RuntimeError("Existing stable container changed")
        if (state.get("Health") or {}).get("Status") == "unhealthy":
            raise RuntimeError("Existing stable container became unhealthy")


def stop_own() -> None:
    ids = docker("ps", "-q", "--filter", "label=pickage.experiment=" + RUN).split()
    if ids:
        docker("stop", "--time", "5", *ids)


def main() -> None:
    app = socket.gethostname().endswith("6-235")
    url = "http://127.0.0.1:8080/actuator/health" if app else "http://127.0.0.1:9000/minio/health/live"
    baseline = capture_baseline()
    duration = int(os.environ.get("PICKAGE_GUARD_SECONDS", "600"))
    if not 60 <= duration <= 86400:
        raise ValueError("Guard duration must be 60..86400 seconds")
    deadline = time.monotonic() + duration
    failures = 0
    reason = "TIME_LIMIT"
    with (ROOT / "guard.jsonl").open("w", encoding="utf-8") as out:
        try:
            while time.monotonic() < deadline:
                if (ROOT / "guard.done").exists():
                    reason = "FINISHED"
                    break
                mem = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
                       for line in Path("/proc/meminfo").read_text().splitlines()}
                observed = {"time": time.time(), "available_memory_bytes": mem["MemAvailable"],
                            "excluded_baseline_id": baseline["known_id"]}
                issue = None
                try:
                    observed["preexisting_failure"] = check_known_failure(baseline["known_id"])
                    t = time.monotonic()
                    with urlopen(url, timeout=2) as response:
                        body = response.read()
                    observed["service_seconds"] = time.monotonic() - t
                    if app and json.loads(body).get("status") != "UP":
                        issue = "SERVICE_NOT_UP"
                    if observed["service_seconds"] > 1:
                        issue = "SERVICE_RESPONSE_OVER_1S"
                    peer = os.environ.get("PICKAGE_GUARD_PEER_HEALTH")
                    if peer:
                        t = time.monotonic()
                        with urlopen(peer, timeout=2) as response:
                            peer_body = json.load(response)
                        observed["peer_service_seconds"] = time.monotonic() - t
                        if peer_body.get("status") != "UP" or observed["peer_service_seconds"] > 1:
                            issue = "PEER_SERVICE_UNHEALTHY_OR_SLOW"
                    check_stable(baseline["original"])
                    from pipeline.preprocessing.experiments.spark.runtime.repository22_app import parse_pressure_avg10
                    observed['io_pressure_avg10'] = parse_pressure_avg10(Path('/proc/pressure/io').read_text())
                    observed['memory_pressure_avg10'] = parse_pressure_avg10(Path('/proc/pressure/memory').read_text())
                    if observed['io_pressure_avg10'] > 10 or observed['memory_pressure_avg10'] > 1:
                        issue = 'APP_RESOURCE_PRESSURE'
                except Exception as error:
                    issue = type(error).__name__ + ":" + str(error)
                failures = failures + 1 if issue else 0
                observed["issue"] = issue
                observed["consecutive_issues"] = failures
                out.write(json.dumps(observed, sort_keys=True) + "\n")
                out.flush()
                if mem["MemAvailable"] < 4 * 1024**3 or failures >= 3:
                    reason = "MEMORY_BELOW_4G" if mem["MemAvailable"] < 4 * 1024**3 else issue
                    break
                time.sleep(2)
        finally:
            stop_own()
            (ROOT / "guard-result.json").write_text(
                json.dumps({"reason": reason, "run": RUN, "baseline": baseline["record"]}),
                encoding="utf-8")


if __name__ == "__main__":
    main()
