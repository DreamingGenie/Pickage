"""Prepare and run the fast, resumable full historical database reload.

The coordinator owns the source/checkpoint lifecycle.  PostgreSQL publication is
delegated to :class:`FastCountLoader`; this module deliberately does not alter
the frozen H7 loader or its resume contract.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import ctypes
import threading
import time
from typing import Any
import uuid

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.postgresql.version_dependents.historical_db_keys import verify_keys, _date
from pipeline.postgresql.version_dependents.historical_db_fast_publish import target_schema
from pipeline.postgresql.version_dependents.historical_db_source import FullSource
from pipeline.preprocessing.version_dependents.historical_artifact import _run_lock


OLD_CONTRACT = (
    "historical_db_keys.py", "historical_db_load.py", "historical_db_publish.py",
    "historical_db_prepare.py", "historical_db_source.py",
)
REQUIRED_GENERATION = set(OLD_CONTRACT) | {"postgres.py", "historical_db_fast_publish.py", "historical_db_reload.py", "historical_artifact.py", "artifact.py", "version-dependents-reload.ps1"}


def contract() -> dict[str, str]:
    """Return the source-generation hashes pinned in a reload plan."""
    here = Path(__file__).resolve().parent
    paths = [here / name for name in OLD_CONTRACT]
    paths.append(here.parent / "postgresql" / "postgres.py")
    paths.extend((here / "historical_db_fast_publish.py", here / "historical_db_reload.py"))
    from pipeline.preprocessing.common.paths import REPO_ROOT
    paths.extend((here/'historical_artifact.py',here/'artifact.py',REPO_ROOT/'scripts/version-dependents-reload.ps1'))
    return {path.name: file_sha256(path) for path in paths}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _event(root: Path, phase: str, **fields: Any) -> None:
    value = {"at": datetime.now(timezone.utc).isoformat(), "pid":os.getpid(), "phase": phase, **fields}
    with (root / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    _write_json(root / "status.json", value)


def _start_heartbeat(root: Path):
    stopped = threading.Event()
    def beat():
        while not stopped.wait(30):
            _write_json(root/'heartbeat.json', {'pid':os.getpid(), 'at':datetime.now(timezone.utc).isoformat()})
    thread = threading.Thread(target=beat, name="vd193-reload-heartbeat", daemon=True)
    thread.start()
    return stopped, thread


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_plan(plan: dict[str, Any]) -> None:
    required = {"schema", "source_run_dir", "source_run_manifest_sha256", "db_command", "dates",
                "generation", "expected_rows", "expected_dates", "rows_by_date", "execution_prefix", "db_identity"}
    missing = required - set(plan)
    if missing:
        raise ValueError("Reload plan is missing: " + ", ".join(sorted(missing)))
    target_schema(plan['schema'])
    if plan.get('scope','FULL_CALENDAR') not in ('FULL_CALENDAR','SELECTED_DATES'):
        raise ValueError('Unknown reload scope')
    if not _valid_sha(plan["source_run_manifest_sha256"]):
        raise ValueError("Invalid source manifest hash")
    if not isinstance(plan["db_command"], list) or not plan['db_command'] or not all(isinstance(v, str) and v for v in plan["db_command"]):
        raise ValueError("db_command must be a non-empty argument list")
    dates = plan["dates"]
    if not isinstance(dates, list) or not dates or len(set(dates)) != len(dates):
        raise ValueError("dates must contain unique calendar dates")
    if dates != sorted(dates):
        raise ValueError("dates must be sorted")
    for day in dates:
        _date(day)
    if not isinstance(plan["expected_rows"], int) or plan["expected_rows"] < 0:
        raise ValueError("expected_rows must be a non-negative integer")
    if plan["expected_dates"] != len(dates):
        raise ValueError("expected_dates differs from dates")
    if not isinstance(plan["rows_by_date"], dict) or set(plan["rows_by_date"]) != set(dates):
        raise ValueError("rows_by_date must cover every date")
    if any(type(rows) is not int or rows < 0 for rows in plan["rows_by_date"].values()):
        raise ValueError("rows_by_date values must be non-negative integers")
    if sum(plan["rows_by_date"].values()) != plan["expected_rows"]:
        raise ValueError("expected_rows differs from rows_by_date")
    if not isinstance(plan["generation"], dict) or not REQUIRED_GENERATION <= set(plan["generation"]):
        raise ValueError("generation contract must include all reload source hashes")
    if not isinstance(plan["execution_prefix"], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',plan['execution_prefix']):
        raise ValueError("execution_prefix is required")
    if "db_identity" in plan and (not isinstance(plan["db_identity"], dict)
                                   or not {"system_identifier", "current_database"} <= set(plan["db_identity"])):
        raise ValueError("db_identity must pin system_identifier and current_database")


def validate_generation(expected: dict[str, str]) -> None:
    actual = contract()
    if expected != actual:
        changed = sorted(set(expected) | set(actual))
        changed = [name for name in changed if expected.get(name) != actual.get(name)]
        raise ValueError("Reload code contract changed: " + ", ".join(changed))


def _verify_db_identity(loader, expected: dict[str, Any] | None) -> None:
    if not expected:
        return
    values = loader._send("SELECT system_identifier::text FROM pg_control_system(); SELECT current_database();")
    if len(values) < 2 or values[-2:] != [str(expected["system_identifier"]), expected["current_database"]]:
        raise ValueError("Database identity differs from reload plan")


def _prevent_sleep(enabled: bool) -> None:
    if os.name == "nt":
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED; keep the detached reload alive.
        api = ctypes.WinDLL('kernel32',use_last_error=True).SetThreadExecutionState
        api.argtypes, api.restype = [ctypes.c_uint32], ctypes.c_uint32
        if not api(0x80000000 | (0x00000001 if enabled else 0)):
            raise ctypes.WinError(ctypes.get_last_error())


def inspect_resources(*, scratch: Path, command: list[str], minimum_gib: int = 200) -> dict[str, Any]:
    """Read-only host and database disk checks used by the preflight command."""
    usage = shutil.disk_usage(scratch)
    result = {"host_scratch_available_bytes": usage.free,
              "minimum_bytes": minimum_gib * 1024 ** 3,
              "host_scratch_ok": usage.free >= minimum_gib * 1024 ** 3}
    try:
        # The configured command ends in psql arguments.  Run df in the DB
        # container itself, rather than passing it as a SQL client option.
        if len(command) >= 3 and command[0].lower().endswith("docker") and "exec" in command:
            exec_at = command.index("exec")
            container_at = next((i for i in range(exec_at + 1, len(command))
                                 if not command[i].startswith("-")), None)
            if container_at is None:
                raise ValueError("docker exec command has no container")
            df_command = command[:container_at + 1] + ["df", "-Pk", "/var/lib/postgresql/data"]
        else:
            raise ValueError('Disk inspection requires an explicit Docker PostgreSQL target')
        completed = subprocess.run(df_command, check=True, capture_output=True, text=True, timeout=30)
        lines = [line.split() for line in completed.stdout.splitlines() if line.strip()]
        if len(lines) >= 2 and len(lines[-1]) >= 4:
            result["database_available_bytes"] = int(lines[-1][3]) * 1024
            result["database_disk_ok"] = result["database_available_bytes"] >= minimum_gib * 1024 ** 3
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result["database_disk_ok"] = False
        result["database_disk_error"] = str(error)
    return result


class ReloadCoordinator:
    def __init__(self, config: dict[str, Any], *, loader_factory=None,
                 source_factory=FullSource, key_verifier=verify_keys):
        self.config = config
        self.root = Path(config["output"]).resolve()
        self.plan = _read_json(Path(config["plan"]).resolve())
        validate_plan(self.plan)
        validate_generation(self.plan["generation"])
        from pipeline.preprocessing.version_dependents.artifact import _reject_reparse_ancestors
        _reject_reparse_ancestors(self.root)
        source_root = Path(self.plan['source_run_dir']).resolve()
        if self.root.is_relative_to(source_root.parent) or source_root.parent.is_relative_to(self.root):
            raise ValueError('Reload output overlaps preserved calculation')
        location = source_root/'input_location.json'
        if location.exists():
            prepared = Path(_read_json(location)['prepared_dir']).resolve()
            if self.root.is_relative_to(prepared) or prepared.is_relative_to(self.root):
                raise ValueError('Reload output overlaps preserved input')
        self.loader_factory = loader_factory
        self.source_factory, self.key_verifier = source_factory, key_verifier

    def inspect_target(self) -> dict[str, Any]:
        if self.loader_factory is None:
            from pipeline.postgresql.version_dependents.historical_db_fast_publish import FastCountLoader
            self.loader_factory = FastCountLoader
        with self.loader_factory(self.plan["db_command"], self.root, self.plan["schema"], self.plan) as loader:
            return loader.inspect_target()

    def _loader(self):
        if self.loader_factory is None:
            from pipeline.postgresql.version_dependents.historical_db_fast_publish import FastCountLoader
            self.loader_factory = FastCountLoader
        return self.loader_factory(self.plan["db_command"], self.root, self.plan["schema"], self.plan)

    def _validate_source(self, source):
        calendar = [row['snapshot_at'] for row in source.calendar]
        if self.plan.get('scope','FULL_CALENDAR') == 'FULL_CALENDAR':
            if calendar != self.plan['dates']:
                raise ValueError('Source calendar differs from reload plan')
        elif not set(self.plan['dates']) <= set(calendar):
            raise ValueError('Pilot dates absent from source calendar')
        rows = {day:source.quality[day]['target_versions'] for day in self.plan['dates']}
        if rows != self.plan['rows_by_date']:
            raise ValueError('Source quality row counts differ from reload plan')

    def check(self) -> dict[str, Any]:
        """Read-only preflight, including source, keys, and private target state."""
        self.root.mkdir(parents=True,exist_ok=True)
        stored_plan = self.root/'plan.json'
        if stored_plan.exists() and _read_json(stored_plan) != self.plan:
            raise ValueError('Stored reload plan differs')
        source_root = self.root / ("check-source-" + uuid.uuid4().hex)
        with self._loader() as loader:
            source = self.source_factory(self.plan["source_run_dir"], self.plan["source_run_manifest_sha256"], source_root)
            try:
                _verify_db_identity(loader, self.plan.get("db_identity"))
                self._validate_source(source)
                keys = self.key_verifier(self.plan["db_command"], source_root, source.identity_file,
                                         source.version_file, source.calendar, source.lineage, source.expected)
                source.recheck()
                target = loader.inspect_target()
                return {"status": "CHECKED", "key_verification": keys, "target": target,
                        "source_expected": source.expected, "expected_dates": len(self.plan["dates"]),
                        "expected_rows": self.plan["expected_rows"]}
            finally:
                source.close()

    def _stop_requested(self) -> bool:
        return (self.root / "stop-request.json").exists()

    def run(self, *, resume: bool = False) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        with _run_lock(self.root):
            if resume and (self.root / "stop-request.json").exists():
                (self.root / "stop-request.json").unlink()
            if self._stop_requested():
                raise RuntimeError("stop request is active; use --resume to continue")
            stored_plan = self.root / "plan.json"
            if stored_plan.exists() and _read_json(stored_plan) != self.plan:
                raise ValueError("Stored reload plan differs; refusing to overwrite it")
            _write_json(stored_plan, self.plan)
            attempt = self.root / ("source-" + uuid.uuid4().hex)
            _event(self.root, "SOURCE_OPEN", resume=resume)
            source = None
            heartbeat_stop, heartbeat_thread = _start_heartbeat(self.root)
            try:
                with self._loader() as loader:
                    _verify_db_identity(loader, self.plan['db_identity'])
                    source = self.source_factory(self.plan['source_run_dir'],self.plan['source_run_manifest_sha256'],attempt)
                    self._validate_source(source)
                    _event(self.root, "KEY_VALIDATION", **source.expected)
                    keys = self.key_verifier(self.plan["db_command"], attempt, source.identity_file, source.version_file,
                                             source.calendar, source.lineage, source.expected)
                    _write_json(self.root / "key-verification.json", keys)
                    source.recheck()
                    results = []
                    loader.initialize()
                    for day in self.plan["dates"]:
                        if self._stop_requested():
                            _event(self.root, "STOPPED", completed=len(results))
                            return {"status": "STOPPED", "dates": results}
                        resources = inspect_resources(scratch=self.root, command=self.plan["db_command"],
                                                     minimum_gib=self.plan.get("minimum_disk_gib", 200))
                        if not resources.get("host_scratch_ok") or not resources.get("database_disk_ok"):
                            _event(self.root, "PAUSED_RESOURCE_LOW", snapshot=day, resources=resources)
                            return {"status": "PAUSED_RESOURCE_LOW", "dates": results, "resources": resources}
                        started = time.monotonic()
                        _event(self.root, "PREPARE_DATE", snapshot=day, verified_dates=len(results),total_dates=len(self.plan['dates']),verified_rows=sum(self.plan['rows_by_date'][r['snapshot']] for r in results),total_rows=self.plan['expected_rows'])
                        metadata, files = source.prepare_date(day)
                        if metadata["counts"]["package_version_snapshot"] != self.plan["rows_by_date"][day]:
                            raise ValueError("Prepared date row count differs from reload plan")
                        execution_id = f'{self.plan["execution_prefix"]}-{self.plan["source_run_manifest_sha256"][:16]}-{day.replace("-", "")}'
                        def before_commit() -> None:
                            validate_generation(self.plan["generation"])
                            source.recheck()
                            for record in metadata["manifest"]["files"]:
                                path = files[record["role"]]
                                if file_sha256(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
                                    raise ValueError("COPY source changed during publication")
                        result = loader.publish_day(metadata, files, execution_id, before_commit)
                        row = {"snapshot": day, **result, "elapsed_seconds": time.monotonic() - started}
                        results.append(row)
                        _write_json(self.root / (day + ".json"), row)
                        _event(self.root, "DATE_VERIFIED", **row, verified_dates=len(results),total_dates=len(self.plan['dates']),verified_rows=sum(self.plan['rows_by_date'][r['snapshot']] for r in results),total_rows=self.plan['expected_rows'])
                    target = loader.inspect_target()
                    if target.get("completed_dates") != len(self.plan["dates"]):
                        raise ValueError("Target completed date count differs from reload plan")
                    if target.get("completed_rows") != self.plan["expected_rows"]:
                        raise ValueError("Target completed row count differs from reload plan")
                    if not target.get('ready'):
                        raise ValueError('Target integrity verification is incomplete')
                    status = 'READY_FOR_CUTOVER' if self.plan.get('scope','FULL_CALENDAR') == 'FULL_CALENDAR' else 'PILOT_VERIFIED'
                    result = {"status": status, "dates": results,
                              "expected_dates": len(self.plan["dates"]), "expected_rows": self.plan["expected_rows"], "target": target}
                    _write_json(self.root / "result.json", result)
                    _event(self.root, "COMPLETE", status=status)
                    return result
            except BaseException as error:
                _event(self.root, "FAILED", error=str(error))
                raise
            finally:
                if source is not None:
                    source.close()
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--publish", action="store_true", help="Write the prepared target")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)
    config = _read_json(Path(args.config).resolve())
    root = Path(config["output"]).resolve()
    if args.stop:
        _write_json(root / "stop-request.json", {"requested_at": datetime.now(timezone.utc).isoformat()})
        return 0
    if args.status:
        state = {'status':_read_json(root/'status.json') if (root/'status.json').exists() else {'phase':'NOT_STARTED'},
                 'heartbeat':_read_json(root/'heartbeat.json') if (root/'heartbeat.json').exists() else None,
                 'stop_requested':(root/'stop-request.json').exists(),
                 'note':'Saved process progress only; Check verifies the database when no load is active'}
        try:
            ReloadCoordinator(config)
            state['code_contract_matches'] = True
        except Exception as error:
            state.update(code_contract_matches=False, error=str(error))
        print(json.dumps(state, ensure_ascii=False))
        return 0
    coordinator = ReloadCoordinator(config)
    root.mkdir(parents=True, exist_ok=True)
    resources = inspect_resources(scratch=root, command=coordinator.plan["db_command"],
                                  minimum_gib=coordinator.plan.get("minimum_disk_gib", 200))
    if not resources.get("host_scratch_ok") or not resources.get("database_disk_ok"):
        raise RuntimeError("Insufficient reload disk space: " + json.dumps(resources))
    if not args.publish:
        result = coordinator.check()
        result["resources"] = resources
        _write_json(root/'preflight.json', result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    _prevent_sleep(True)
    try:
        coordinator.run(resume=args.resume)
    finally:
        _prevent_sleep(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
