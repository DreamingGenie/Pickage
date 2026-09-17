"""Data EC2-only ABBA benchmark for Spark repository transform vs DuckDB."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from pipeline.preprocessing.experiments.spark.runtime import benchmark_data_host as host
from pipeline.preprocessing.experiments.spark.runtime import repository_profile_host as profile
from pipeline.preprocessing.experiments.spark.runtime import weekly_priority

RUN = "repository-duckdb10000-20260917-a1"
SOURCE_RUN = "sample-ec2-20260916-a1"
ROOT = Path("/home/ubuntu/pickage-experiments") / RUN
SOURCE = ROOT.parent / SOURCE_RUN / "output"
DEST = "/experiment/" + RUN
SOURCE_DEST = "/experiment/" + SOURCE_RUN
MANIFEST_SHA = "2a2a733c505a30023570a67078074acb37ba8ed5659ff703f3e81e87b524f765"
TRIALS = ("spark-1", "duckdb-1", "duckdb-2", "spark-2")
ENTRY_MODULE = "pipeline.preprocessing.experiments.spark.runtime.repository_duckdb10k_entry"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preflight():
    if socket.gethostname() != "ip-172-26-8-249":
        raise RuntimeError("This benchmark runs on the data EC2 only")
    manifest = SOURCE / "local-manifest.json"
    if not manifest.is_file() or _sha(manifest) != MANIFEST_SHA:
        raise ValueError("Frozen sample manifest changed or missing")
    value = json.loads(manifest.read_bytes())
    if value.get("sample", {}).get("package_rows") != 10000:
        raise ValueError("Expected frozen 10,000-package sample")
    # Validate every frozen input byte and the staged source inventory.  The
    # 1k profile preflight cannot be reused because it intentionally requires a
    # successful 1k reference run.
    for record in value.get("input_files", []):
        relative = Path(record["path"]).relative_to(SOURCE_DEST)
        path = (SOURCE / relative).resolve()
        if not path.is_relative_to(SOURCE.resolve()) or path.stat().st_size != record["bytes"] or _sha(path) != record["sha256"]:
            raise ValueError("Frozen input changed: " + str(relative))
    prepared = json.loads((ROOT / "prepared.json").read_bytes())
    expected_code = prepared.get("code_files_sha256", {})
    if not expected_code:
        raise ValueError("Prepared code inventory is missing")
    actual_code = {p.relative_to(ROOT / "code").as_posix(): _sha(p) for p in (ROOT / "code").rglob("*") if p.is_file() and p.suffix in (".py", ".cjs") and "node_modules" not in p.parts}
    if actual_code != expected_code:
        raise ValueError("Prepared code inventory differs")
    host.command("docker", "image", "inspect", host.IMAGE)

    names = host.command("docker", "ps", "--format", "{{.Names}}").splitlines()
    allowed = {"pickage-data-mlflow-1", "pickage-data-spark-worker-1-1", "pickage-data-spark-master-1", "pickage-data-minio-1", weekly_priority.WEEKLY}
    competing = [name for name in names if name not in allowed]
    weekly = weekly_priority.observe()
    issue = weekly_priority.violation(weekly)
    free = shutil.disk_usage(ROOT).free
    return {"status": "READY" if not competing and not issue and free >= 30 * 1024**3 else "WAITING",
            "competing_containers": competing, "weekly": weekly, "weekly_issue": issue,
            "free_disk_bytes": free, "manifest_sha256": MANIFEST_SHA,
            "input_identity": value["input_identity"], "sample": value["sample"],
            "container_cpu_limit": 2, "container_memory_mib": 7680,
            "cpu_shares": 128, "nice": 10, "disk_read_write_limit_mib_s_each": 32,
            "engine_threads": 2, "engine_memory": "4GB", "schedule": list(TRIALS),
            "prepared_code_files": len(expected_code),
            "db_loaded": False, "production_publication": False}


class WeeklyPrioritySupervisor(profile.WeeklyPrioritySupervisor):
    """Reuse the existing weekly/service guard and scoped container cleanup."""

    def phase(self, name, entry, extra=()):
        self.result.update(status="RUNNING", phase=name)
        host.save(ROOT / "status.json", self.result)
        started = time.time()
        hostname = RUN + "-" + name
        extra = [*extra, "-e", "SPARK_LOCAL_IP=127.0.0.1", "--hostname", hostname, "--add-host", hostname + ":127.0.0.1"]
        cid = self.start(name, 2, "7680m", entry, network="none", extra=extra, gated=True)
        while True:
            self.check()
            state = json.loads(host.command("docker", "inspect", "--format", "{{json .State}}", cid))
            if not state["Running"]: break
            time.sleep(3)
        self.control = None
        state = self.finish(name)
        self.result["phases"][name] = {"seconds": time.time() - started, "state": state}
        host.save(ROOT / "status.json", self.result)
        if state["ExitCode"] or state["OOMKilled"]:
            raise RuntimeError("Phase failed: " + name)


def run():
    check = preflight()
    if check["status"] != "READY":
        raise RuntimeError("Experiment must wait: " + json.dumps(check))
    if (ROOT / "result.json").exists() or (ROOT / "output").exists():
        raise FileExistsError("Run already started; use a new run ID")
    if host.command("docker", "ps", "-aq", "--filter", "label=pickage.experiment=" + RUN):
        raise RuntimeError("Experiment container already exists")
    host.RUN, host.ROOT, host.CODE = RUN, ROOT, ROOT / "code"
    host.OUT, host.DEST = ROOT / "output", DEST
    profile.ROOT = ROOT  # inherited weekly observer writes only into this run
    supervisor = WeeklyPrioritySupervisor(check["weekly"])
    supervisor.result["resource_policy"] = check
    host.OUT.mkdir(); host.OUT.chmod(0o777)
    for name in ("tmp", "local"):
        (host.OUT / name).mkdir(); (host.OUT / name).chmod(0o777)
    env = dict(os.environ, PICKAGE_EXPERIMENT_RUN=RUN, PICKAGE_GUARD_SECONDS="1800",
               PICKAGE_GUARD_PEER_HEALTH="https://j15a506.p.ssafy.io/actuator/health",
               PYTHONPATH=str(host.CODE))
    try:
        supervisor.guard = subprocess.Popen(["python3", "-m", "pipeline.preprocessing.experiments.spark.runtime.ec2_guard"], cwd=host.CODE, env=env, stdout=(ROOT / "guard.log").open("w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        for _ in range(20):
            if (ROOT / "guard.jsonl").exists() and (ROOT / "guard.jsonl").stat().st_size: break
            time.sleep(1)
        supervisor.check()
        entry_base = ["python3", "-m", ENTRY_MODULE]
        for trial in TRIALS:
            engine = trial.split("-", 1)[0]
            supervisor.phase(trial, entry_base + ["run", "--engine", engine, "--manifest", SOURCE_DEST + "/local-manifest.json", "--manifest-sha256", MANIFEST_SHA, "--output", DEST + "/" + trial, "--control", "/control"], ["--mount", f"type=bind,source={SOURCE},target={SOURCE_DEST},readonly", "--cpu-shares", "128", "--device-read-bps", "/dev/nvme0n1:32mb", "--device-write-bps", "/dev/nvme0n1:32mb"])
        comparison = DEST + "/comparison.json"
        supervisor.phase("compare", entry_base + ["compare", "--trials", *(DEST + "/" + trial for trial in TRIALS), "--output", comparison, "--control", "/control"], ["--cpu-shares", "128", "--device-read-bps", "/dev/nvme0n1:32mb", "--device-write-bps", "/dev/nvme0n1:32mb"])
        compared = json.loads((ROOT / "output" / "comparison.json").read_bytes())
        if compared.get("status") != "VERIFIED":
            raise RuntimeError("DuckDB/Spark comparison was not verified")
        supervisor.result["comparison"] = compared
        supervisor.result["status"] = "COMPLETE"
    except BaseException as error:
        supervisor.result.update(status="FAILED", error={"type": type(error).__name__, "message": str(error)})
    finally:
        errors = []
        for name in list(supervisor.owned):
            try: supervisor.finish(name)
            except Exception as error: errors.append(str(error))
        (ROOT / "guard.done").touch()
        if supervisor.guard:
            try: supervisor.guard.wait(timeout=15)
            except subprocess.TimeoutExpired: supervisor.guard.terminate()
        supervisor.result.update(finished_at=time.time(), cleanup_errors=errors)
        if errors: supervisor.result["status"] = "FAILED"
        host.save(ROOT / "result.json", supervisor.result); host.save(ROOT / "status.json", supervisor.result)
    return 0 if supervisor.result["status"] == "COMPLETE" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); return (print(json.dumps(preflight(), indent=2)) or 0) if args.check else run()


if __name__ == "__main__": raise SystemExit(main())
