"""Bounded, detachable owner for this run's Spark worker on the app EC2 host.

The process waits for the experiment master on the data EC2, then launches only
its labelled worker. It never edits production services or network rules.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time


RUN = os.environ.get("PICKAGE_EXPERIMENT_RUN", "sample1000-ec2-20260916-a2")
if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", RUN):
    raise ValueError("Invalid experiment run label")
ROOT = Path("/home/ubuntu/pickage-experiments") / RUN
CODE = ROOT / "code"
OUTPUT = ROOT / "output"
METRICS = ROOT / "metrics"
IMAGE = "sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479"
APP_HOST = "172.26.6.235"
APP_HOSTNAME = "ip-172-26-6-235"
MASTER = "172.26.8.249"
MASTER_PORT = 40014
WORKER_PORT = 40014
WEBUI_PORT = 18081
WORKER_MEMORY = "2048M"
CONTAINER_MEMORY = "2816m"
RUN_SECONDS = 6 * 60 * 60
CHECK_INTERVAL = 3
MAX_HEARTBEAT_AGE = 20
MIN_DISK_FREE = 30 * 1024**3
ACCESS_JAR = "aws-java-sdk-bundle-1.12.262.jar"
HADOOP_JAR = "hadoop-aws-3.3.4.jar"
CREDENTIAL_ENV = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                  "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3")


def save(name: str, value: dict) -> None:
    target = ROOT / name
    temporary = ROOT / (name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(target)


def docker(*args: str, timeout: int = 30) -> str:
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def host_identity(hostname: str, *, address_is_local: bool) -> None:
    if hostname != APP_HOSTNAME or not address_is_local:
        raise RuntimeError(f"App worker supervisor must run on {APP_HOSTNAME} ({APP_HOST})")


def port_is_free(host: str, port: int, *, socket_factory=socket.socket) -> bool:
    try:
        with socket_factory(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return True
    except OSError:
        return False


def check_ports_free(*, bind=port_is_free) -> None:
    occupied = [port for port in (WORKER_PORT, WEBUI_PORT) if not bind(APP_HOST, port)]
    if occupied:
        raise RuntimeError("Experiment app-host ports already occupied: " + ",".join(map(str, occupied)))


def master_reachable(host: str = MASTER, port: int = MASTER_PORT, *, connect=socket.create_connection) -> bool:
    try:
        with connect((host, port), timeout=2):
            return True
    except OSError:
        return False


def worker_docker_command(*, credential_names=CREDENTIAL_ENV) -> list[str]:
    command = ["docker", "run", "-d", "--pull", "never", "--name", RUN + "-app-worker",
               "--label", "pickage.experiment=" + RUN, "--network", "host", "--restart", "no",
               "--cpus", "1", "--memory", CONTAINER_MEMORY, "--memory-swap", CONTAINER_MEMORY,
               "--pids-limit", "512", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--log-opt", "max-size=20m", "--log-opt", "max-file=2",
               "--mount", f"type=bind,source={CODE},target=/workspace,readonly",
               "--mount", f"type=bind,source={ROOT / 'jars' / HADOOP_JAR},target=/opt/spark/jars/{HADOOP_JAR},readonly",
               "--mount", f"type=bind,source={ROOT / 'jars' / ACCESS_JAR},target=/opt/spark/jars/{ACCESS_JAR},readonly",
               "--mount", f"type=bind,source={OUTPUT},target=/experiment/" + RUN,
               "-e", "SPARK_LOCAL_IP=" + APP_HOST,
               "-e", "SPARK_DAEMON_MEMORY=256m",
               "-e", "SPARK_WORKER_DIR=/experiment/" + RUN + "/worker",
               "-e", "SPARK_LOCAL_DIRS=/experiment/" + RUN + "/local",
               "-e", "PYTHONPATH=/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip",
               "-e", "PYTHONUNBUFFERED=1"]
    for name in credential_names:
        if os.environ.get(name):
            command += ["-e", name]
    command += [IMAGE, "/opt/spark/bin/spark-class", "org.apache.spark.deploy.worker.Worker",
                f"spark://{MASTER}:{MASTER_PORT}", "--host", APP_HOST, "--port", str(WORKER_PORT),
                "--webui-port", str(WEBUI_PORT), "--cores", "1", "--memory", WORKER_MEMORY]
    return command


def verify_container_caps(info: dict) -> None:
    host = info.get("HostConfig") or {}
    expected_memory = int(2816 * 1024**2)
    if (host.get("NanoCpus") != 1_000_000_000 or host.get("Memory") != expected_memory
            or host.get("MemorySwap") != expected_memory
            or (host.get("RestartPolicy") or {}).get("Name") != "no"):
        raise RuntimeError("App worker container does not match the approved CPU/memory/swap/restart caps")
    labels = (info.get("Config") or {}).get("Labels") or {}
    if labels.get("pickage.experiment") != RUN:
        raise RuntimeError("Refusing to manage an unlabelled or foreign worker container")


def classify_worker_exit(exit_code: int | None, *, master_failures: int,
                         master_was_reachable: bool) -> str:
    if master_failures >= 3 and master_was_reachable:
        return "EXPECTED_MASTER_STOP"
    if exit_code != 0:
        return "WORKER_EXITED_NONZERO"
    return "WORKER_EXITED_BEFORE_MASTER_STOP" if master_failures == 0 else "WORKER_EXITED_UNEXPECTEDLY"


def _read_last_guard() -> dict:
    lines = (ROOT / "guard.jsonl").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise RuntimeError("App service guard has not produced a sample")
    return json.loads(lines[-1])


def _write_heartbeat() -> None:
    save("supervisor-heartbeat.json", {"time": time.time(), "run_id": RUN,
                                       "host": APP_HOST, "role": "app-worker-supervisor"})


def _guard_startup(guard: subprocess.Popen, deadline: float) -> None:
    while time.monotonic() < deadline:
        if guard.poll() is not None:
            raise RuntimeError("App service guard exited during startup")
        path = ROOT / "guard.jsonl"
        if path.exists() and path.stat().st_size:
            point = _read_last_guard()
            if point.get("issue"):
                raise RuntimeError("App service guard reported an issue at startup")
            if time.time() - float(point.get("time", 0)) <= 8:
                return
        time.sleep(1)
    raise TimeoutError("App service guard did not become ready")


def _assert_guard_healthy(guard: subprocess.Popen, *, issue_seen: bool) -> tuple[dict, bool]:
    if guard.poll() is not None:
        raise RuntimeError("APP_SERVICE_GUARD_EXITED")
    point = _read_last_guard()
    if time.time() - float(point.get("time", 0)) > MAX_HEARTBEAT_AGE:
        raise RuntimeError("APP_SERVICE_GUARD_STALE")
    issue_seen = issue_seen or bool(point.get("issue"))
    if int(point.get("consecutive_issues", 0)) >= 3:
        raise RuntimeError("APP_SERVICE_GUARD_HEALTH_FAILED")
    return point, issue_seen


def _monitor_ready(monitor: subprocess.Popen, *, timeout: int = 30) -> None:
    samples = METRICS / "container-metrics.jsonl"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if monitor.poll() is not None:
            raise RuntimeError("App worker resource monitor exited during startup")
        if samples.exists() and samples.stat().st_size:
            return
        time.sleep(1)
    raise TimeoutError("App worker resource monitor produced no initial sample")


def _inspect_worker() -> tuple[dict, dict]:
    raw = docker("inspect", RUN + "-app-worker", timeout=10)
    info = json.loads(raw)[0]
    verify_container_caps(info)
    state = info.get("State") or {}
    return info, state


def run_supervisor() -> dict:
    host_identity(socket.gethostname(), address_is_local=port_is_free(APP_HOST, 0))
    if not ROOT.is_dir() or not CODE.is_dir():
        raise FileNotFoundError("Prepared app-host experiment root and code snapshot are required")
    if (ROOT / "result.json").exists() or (ROOT / "guard.done").exists():
        raise FileExistsError("This app-host experiment run already has a terminal result")
    stale_evidence = [name for name in ("status.json", "guard.jsonl", "guard-result.json",
        "supervisor-heartbeat.json", "launch.json", "guard.log", "worker.log", "monitor.log")
        if (ROOT / name).exists()]
    if stale_evidence:
        raise FileExistsError("This app-host experiment run already contains evidence: "
                              + ",".join(stale_evidence))
    for path in (OUTPUT, METRICS):
        if path.exists():
            raise FileExistsError(f"Experiment output already exists: {path}")
    for name in (HADOOP_JAR, ACCESS_JAR):
        jar = ROOT / "jars" / name
        if not jar.is_file():
            raise FileNotFoundError(f"Required experiment-only Spark connector JAR missing: {jar.name}")
    missing_credentials = [name for name in CREDENTIAL_ENV[:2] if not os.environ.get(name)]
    if missing_credentials:
        raise RuntimeError("Required S3A credential environment variables are missing: "
                           + ",".join(missing_credentials))

    check_ports_free()
    if docker("ps", "-aq", "--filter", "label=pickage.experiment=" + RUN):
        raise RuntimeError("This experiment label already owns a container on the app host")
    if docker("image", "inspect", IMAGE, "--format", "{{.Id}}") != IMAGE:
        raise RuntimeError("Pinned Spark experiment runtime image is not present")

    OUTPUT.mkdir()
    OUTPUT.chmod(0o777)
    for name in ("worker", "local"):
        directory = OUTPUT / name
        directory.mkdir()
        directory.chmod(0o777)
    METRICS.mkdir()
    METRICS.chmod(0o777)
    env = dict(os.environ)
    env["PICKAGE_EXPERIMENT_RUN"] = RUN
    env["PICKAGE_GUARD_SECONDS"] = str(RUN_SECONDS)
    env.pop("PICKAGE_GUARD_PEER_HEALTH", None)
    env["PYTHONPATH"] = str(CODE)
    result = {"status": "STARTING", "run_id": RUN, "host": APP_HOST,
              "scope": "APP_EC2_EXPERIMENT_SPARK_WORKER_ONLY", "started_at": time.time(),
              "image_id": IMAGE, "container_cpu": 1, "container_memory_bytes": 2816 * 1024**2,
              "container_swap_bytes": 0, "worker_cores": 1, "worker_memory": WORKER_MEMORY,
              "master": f"spark://{MASTER}:{MASTER_PORT}", "production_service_changes": False,
              "firewall_changes": False, "db_loaded": False}
    save("status.json", result)
    guard = monitor = logs = None
    log_streams = []
    worker_started = False
    master_was_reachable = False
    master_failures = 0
    issue_seen = False
    monitor_seen = False
    stop_reason = "SUPERVISOR_ERROR"
    error = None
    started = time.monotonic()
    deadline = started + RUN_SECONDS
    try:
        guard_log = (ROOT / "guard.log").open("w", encoding="utf-8")
        log_streams.append(guard_log)
        guard = subprocess.Popen(["python3", "-m", "pipeline.spark_experiment.runtime.ec2_guard"],
            cwd=CODE, env=env, stdin=subprocess.DEVNULL, stdout=guard_log, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True)
        _guard_startup(guard, min(deadline, time.monotonic() + 30))

        while time.monotonic() < deadline:
            point, issue_seen = _assert_guard_healthy(guard, issue_seen=issue_seen)
            free = shutil.disk_usage(ROOT).free
            if free < MIN_DISK_FREE:
                stop_reason = "DISK_FREE_BELOW_30_GIB"
                break
            _write_heartbeat()
            if not master_reachable():
                master_failures = 0
                time.sleep(CHECK_INTERVAL)
                continue
            master_was_reachable = True
            check_ports_free()
            command = worker_docker_command()
            # `-e NAME` passes credentials through Docker's environment lookup;
            # neither values nor a secret-bearing command string are persisted.
            cid = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT,
                                          timeout=60).strip()
            info, state = _inspect_worker()
            result.update(status="WORKER_STARTED", container_id=cid,
                          container_name=RUN + "-app-worker", worker_started_at=time.time(),
                          s3a_credential_env_names=[name for name in CREDENTIAL_ENV
                                                   if os.environ.get(name)])
            save("launch.json", {"container_id": cid, "container_name": RUN + "-app-worker",
                                  "image_id": IMAGE, "host_config": info.get("HostConfig"),
                                  "environment_variable_names": result["s3a_credential_env_names"],
                                  "command": command})
            logs_stream = (ROOT / "worker.log").open("w", encoding="utf-8")
            log_streams.append(logs_stream)
            logs = subprocess.Popen(["docker", "logs", "-f", cid], stdin=subprocess.DEVNULL,
                                    stdout=logs_stream, stderr=subprocess.STDOUT,
                                    close_fds=True, start_new_session=True)
            monitor_log = (ROOT / "monitor.log").open("w", encoding="utf-8")
            log_streams.append(monitor_log)
            monitor = subprocess.Popen(["sudo", "-n", "env", "PYTHONPATH=" + str(CODE),
                "python3", "-m", "pipeline.spark_experiment.runtime.monitor_container",
                "--container", RUN + "-app-worker", "--run-id", RUN,
                "--output", str(METRICS), "--duration-seconds", str(RUN_SECONDS)],
                stdin=subprocess.DEVNULL, stdout=monitor_log, stderr=subprocess.STDOUT,
                close_fds=True, start_new_session=True)
            _monitor_ready(monitor)
            worker_started = True
            stop_reason = "TIME_LIMIT_6_HOURS"
            result["status"] = "RUNNING"
            save("status.json", result)
            break

        if worker_started:
            while time.monotonic() < deadline:
                point, issue_seen = _assert_guard_healthy(guard, issue_seen=issue_seen)
                free = shutil.disk_usage(ROOT).free
                if free < MIN_DISK_FREE:
                    stop_reason = "DISK_FREE_BELOW_30_GIB"
                    break
                samples = METRICS / "container-metrics.jsonl"
                if monitor.poll() is not None:
                    summary_path = METRICS / "container-summary.json"
                    if summary_path.exists():
                        monitor_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                        if monitor_summary.get("stop_reason") in ("CONTAINER_STOPPED", "CONTAINER_GONE"):
                            monitor_seen = True
                        else:
                            stop_reason = "RESOURCE_MONITOR_EXITED"
                            break
                    else:
                        stop_reason = "RESOURCE_MONITOR_EXITED"
                        break
                elif not samples.exists() or time.time() - samples.stat().st_mtime > MAX_HEARTBEAT_AGE:
                    stop_reason = "RESOURCE_MONITOR_STALE"
                    break

                if master_reachable():
                    master_failures = 0
                else:
                    master_failures += 1
                info, state = _inspect_worker()
                if not state.get("Running"):
                    result["worker_exit_code"] = state.get("ExitCode")
                    while (0 < master_failures < 3 and master_was_reachable
                           and time.monotonic() < deadline):
                        point, issue_seen = _assert_guard_healthy(guard, issue_seen=issue_seen)
                        _write_heartbeat()
                        time.sleep(CHECK_INTERVAL)
                        if master_reachable():
                            master_failures = 0
                            break
                        master_failures += 1
                    stop_reason = classify_worker_exit(state.get("ExitCode"),
                        master_failures=master_failures, master_was_reachable=master_was_reachable)
                    break
                if master_failures >= 3 and master_was_reachable:
                    stop_reason = "EXPECTED_MASTER_STOP"
                    break
                _write_heartbeat()
                result["last_guard_sample_time"] = point.get("time")
                result["last_master_check_failures"] = master_failures
                save("status.json", result)
                time.sleep(CHECK_INTERVAL)
        elif stop_reason == "SUPERVISOR_ERROR":
            stop_reason = "TIME_LIMIT_WAITING_FOR_MASTER"

    except BaseException as caught:
        error = {"type": type(caught).__name__, "message": str(caught)}
        stop_reason = "SUPERVISOR_ERROR"
    finally:
        cleanup_errors = []
        # Only inspect/stop/remove the exact container created by this process,
        # after verifying its immutable run label.
        try:
            raw = docker("inspect", RUN + "-app-worker", timeout=10)
            info = json.loads(raw)[0]
            verify_container_caps(info)
            if (info.get("Config", {}).get("Labels") or {}).get("pickage.experiment") != RUN:
                raise RuntimeError("Worker label changed; refusing cleanup")
            if (info.get("State") or {}).get("Running"):
                docker("stop", "--time", "10", RUN + "-app-worker", timeout=20)
                info = json.loads(docker("inspect", RUN + "-app-worker", timeout=10))[0]
            result["worker_final_state"] = info.get("State")
        except subprocess.CalledProcessError:
            pass
        except BaseException as cleanup_error:
            cleanup_errors.append({"step": "stop_worker", "message": str(cleanup_error)})

        (ROOT / "guard.done").touch(exist_ok=True)
        for process, label in ((monitor, "monitor"), (guard, "guard"), (logs, "docker_logs")):
            if process is None:
                continue
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                cleanup_errors.append({"step": label, "message": "child required termination"})
        guard_result = None
        try:
            guard_result_path = ROOT / "guard-result.json"
            if guard_result_path.exists():
                guard_result = json.loads(guard_result_path.read_text(encoding="utf-8"))
            else:
                guard_result = None
            if worker_started:
                summary_path = METRICS / "container-summary.json"
                if summary_path.exists():
                    monitor_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    monitor_seen = monitor_summary.get("stop_reason") in ("CONTAINER_STOPPED", "CONTAINER_GONE")
            try:
                info = json.loads(docker("inspect", RUN + "-app-worker", timeout=10))[0]
                verify_container_caps(info)
                if (info.get("State") or {}).get("Running"):
                    raise RuntimeError("App worker remained running after cleanup")
                docker("rm", RUN + "-app-worker", timeout=20)
            except subprocess.CalledProcessError:
                pass
        except BaseException as cleanup_error:
            cleanup_errors.append({"step": "collect_cleanup_evidence", "message": str(cleanup_error)})
        for stream in log_streams:
            try:
                stream.close()
            except OSError:
                pass

        if stop_reason == "EXPECTED_MASTER_STOP" and not error:
            if issue_seen:
                error = {"type": "GuardIssue", "message": "App service guard reported at least one health issue"}
            elif not monitor_seen:
                error = {"type": "MonitorEvidenceMissing", "message": "Final cgroup monitor summary is missing or invalid"}
            elif guard_result is None or guard_result.get("reason") != "FINISHED":
                error = {"type": "GuardDidNotFinish", "message": "App service guard did not report FINISHED"}
            elif cleanup_errors:
                error = {"type": "CleanupFailed", "message": "One or more bounded cleanup operations failed"}
        status = stop_reason if stop_reason == "EXPECTED_MASTER_STOP" and error is None else "FAILED"
        if stop_reason.startswith("TIME_LIMIT"):
            status = "TIME_LIMIT"
        if stop_reason == "DISK_FREE_BELOW_30_GIB":
            status = "ABORTED"
        result.update(status=status, stop_reason=stop_reason, finished_at=time.time(),
                      master_was_reachable=master_was_reachable, master_unreachable_samples=master_failures,
                      guard_issue_seen=issue_seen, guard_result=guard_result,
                      resource_monitor_finished=monitor_seen, cleanup_errors=cleanup_errors,
                      error=error, supervisor_duration_seconds=time.monotonic() - started,
                      production_service_changes=False, firewall_changes=False, db_loaded=False)
        save("result.json", result)
        save("status.json", result)
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foreground", action="store_true",
                        help="internal mode: run the detached supervisor in this process")
    args = parser.parse_args(argv)
    return args


def detach() -> int:
    if not ROOT.is_dir() or not CODE.is_dir():
        raise FileNotFoundError("Prepared app-host experiment root and code snapshot are required")
    pid_file = ROOT / "app-supervisor.pid"
    if pid_file.exists():
        raise FileExistsError("App-host supervisor PID record already exists")
    log = (ROOT / "app-supervisor.log").open("a", encoding="utf-8")
    env = dict(os.environ)
    env["PICKAGE_EXPERIMENT_RUN"] = RUN
    env["PYTHONPATH"] = str(CODE)
    process = subprocess.Popen([sys.executable, "-m",
        "pipeline.spark_experiment.runtime.benchmark_app_host", "--foreground"],
        cwd=CODE, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        close_fds=True, start_new_session=True)
    log.close()
    try:
        with pid_file.open("x", encoding="ascii") as stream:
            stream.write(str(process.pid) + "\n")
    except BaseException:
        process.terminate()
        raise
    print(json.dumps({"status": "DETACHED", "pid": process.pid, "run_id": RUN,
                      "log": str(ROOT / "app-supervisor.log")}), flush=True)
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.foreground:
        return detach()
    result = run_supervisor()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str), flush=True)
    return 0 if result.get("status") == "EXPECTED_MASTER_STOP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
