"""Bind validation evidence to explicitly pinned local metadata sources.

This module deliberately reads small JSON manifests only.  It never opens a
database, native client, Parquet object, or a directory discovered by a broad
recursive walk.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any

MAX_JSON_BYTES = 8 * 1024 * 1024


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _safe_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or "\\" in relative or
            Path(relative).is_absolute() or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("metadata path must be a safe relative path")
    root = Path(root).absolute()
    path = root.joinpath(*relative.split("/"))
    # Inspect the lexical path before resolving it, so a symlink cannot hide
    # the object that was actually opened.
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("metadata symlink/reparse point is not allowed")
    resolved_root, resolved_path = root.resolve(strict=True), path.resolve(strict=True)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"path escapes source root: {relative}")
    return path


def _read_bounded(path: Path, limit: int) -> bytes:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("metadata file is not a bounded regular file")
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("metadata file grew beyond bounded limit")
    return body


def _strict_json(body: bytes):
    return json.loads(body.decode("utf-8"), object_pairs_hook=_no_duplicates,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(
                          f"invalid JSON constant: {value}")))


def _read_json(root: Path, relative: str) -> tuple[Any, dict[str, Any]]:
    path = _safe_path(root, relative)
    raw = _read_bounded(path, MAX_JSON_BYTES)
    size = len(raw)
    digest = hashlib.sha256(raw).hexdigest()
    value = _strict_json(raw)
    return value, {"path": relative.replace("\\", "/"), "bytes": size, "sha256": digest}


def _status(name: str, status: str, reason: str | None = None, **extra):
    item = {"name": name, "status": status}
    if reason:
        item["reason"] = reason
    item.update(extra)
    return item


def bind_sources(original_root: Path, metadata: dict, plan: dict) -> dict:
    """Bind explicit local artifacts using each producer's own hash contract."""
    from pipeline.preprocessing.package_snapshot.policy import canonical_bytes
    from pipeline.postgresql.version_dependents.historical_db_reload import contract, validate_generation

    root = Path(original_root).absolute()
    checked, checks, deferred = [], [], []
    results = {}
    executions = metadata["executions"]

    def relative(value):
        path = Path(value)
        # Keep lexical components until _safe_path has checked for links.
        return path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()

    def read(path):
        value, receipt = _read_json(root, relative(path))
        checked.append(receipt)
        return value, receipt["sha256"]

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def run(name, operation):
        try:
            checks.append(_status(name, "PASS", **operation()))
        except FileNotFoundError as error:
            checks.append(_status(name, "NOT_RUN", str(error)))
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            checks.append(_status(name, "FAIL", str(error) or "required record is missing"))

    def source_manifest():
        require(bool(plan.get("source_run_dir")) and bool(plan.get("source_run_manifest_sha256")), "source run path and SHA are required")
        value, digest = read(Path(plan["source_run_dir"]) / "run_manifest.json")
        require(digest == plan["source_run_manifest_sha256"], "source run manifest raw SHA mismatch")
        require(value.get("run_status") == "COMPLETE" and value.get("full_selection_executed") is True,
                "source run must be COMPLETE with full_selection_executed=true")
        return {"manifest_sha256": digest, "run_status": value.get("run_status"),
                "full_selection_executed": value.get("full_selection_executed")}

    run("pinned_source_run_manifest", source_manifest)

    def candidate():
        refs = [e for e in executions if e["dataset"] == "snapshot-reference" and e["status"] == "PUBLISHED"]
        require(len(refs) == 1, "one published snapshot-reference execution required")
        execution = refs[0]
        folder = Path(execution["run_prefix"])
        value, digest = read(folder / "snapshot-candidate.json")
        require(digest == execution["manifest_sha256"], "candidate raw SHA differs from reference execution")
        require(value == execution["input_metadata"]["candidate"], "candidate JSON differs from reference metadata")
        files = value["files"]
        require(bool(files), "candidate inventory and SQL pins missing")
        for entry in files:
            path = _safe_path(root, relative(folder / entry["path"]))
            raw = _read_bounded(path, MAX_JSON_BYTES)
            file_sha = hashlib.sha256(raw).hexdigest()
            require(file_sha == entry["sha256"], "candidate linked file SHA mismatch: " + entry["path"])
            checked.append({"path": relative(path), "bytes": len(raw), "sha256": file_sha})
        return {"manifest_sha256": digest, "linked_files": len(files)}

    run("pinned_snapshot_candidate", candidate)

    expected = plan.get("generation")
    if not isinstance(expected, dict) or not expected:
        checks.append(_status("prepared_plan_generation", "NOT_RUN", "generation contract absent"))
    else:
        try:
            validate_generation(expected)
            checks.append(_status("prepared_plan_generation", "PASS", entries=len(expected)))
        except ValueError as error:
            actual = contract()
            changed = [name for name in sorted(set(actual) | set(expected)) if actual.get(name) != expected.get(name)]
            evidence = {"changed": changed, "expected": {n: expected.get(n) for n in changed}, "actual": {n: actual.get(n) for n in changed}}
            # Explain CRLF without changing the existing loader's byte contract.
            script = Path(__file__).resolve().parents[2] / "scripts/version-dependents-reload.ps1"
            raw = script.read_bytes()
            evidence["script_lf_sha256"] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
            evidence["only_script_line_endings_differ"] = changed == ["version-dependents-reload.ps1"] and evidence["script_lf_sha256"] == expected.get("version-dependents-reload.ps1")
            checks.append(_status("prepared_plan_generation", "FAIL", str(error), **evidence))

    ps = [e for e in executions if e["dataset"] == "package-snapshot" and e["status"] == "PUBLISHED"]
    base_date = max(plan["dates"])

    def base(execution):
        build, _ = read("data/package_snapshot/S15P21A506-288/build-result.json")
        value, digest = read(build["result"]["manifest_path"])
        require(digest == execution["manifest_sha256"] == build["result"]["manifest_sha256"], "base manifest raw SHA mismatch")
        require(value == execution["input_metadata"], "base manifest differs from DB metadata")
        receipt, _ = read("data/package_snapshot/S15P21A506-288/first-load-result.json")
        require(receipt["input"]["manifest_sha256"] == digest and receipt["input"]["manifest"] == value,
                "base first-load receipt belongs to another manifest")
        results[base_date] = receipt
        return {"manifest_sha256": digest, "hash_contract": "raw bytes", "date": base_date}

    def history(execution):
        day = execution["snapshot_at"]
        folder = Path("data/package_snapshot/history/full-history-288-20260909-v1") / day
        receipt, _ = read(folder / "result.json")
        value, raw_sha = read(folder / "run_manifest.json")
        # history.py saves pretty JSON; history_load.verify_publication hashes
        # package_snapshot.policy.canonical_bytes, without a trailing newline.
        digest = hashlib.sha256(canonical_bytes(value)).hexdigest()
        require(digest == execution["manifest_sha256"], "history producer canonical SHA mismatch")
        require(value == execution["input_metadata"], "history manifest differs from DB metadata")
        require(receipt["publication"]["manifest_sha256"] == digest == receipt["database"]["manifest_sha256"],
                "history publication/database receipt SHA mismatch")
        require(receipt["database"]["execution_id"] == execution["execution_id"], "history receipt execution mismatch")
        results[day] = receipt
        return {"date": day, "manifest_sha256": digest, "local_raw_sha256": raw_sha,
                "hash_contract": "package_snapshot.policy.canonical_bytes"}

    for execution in ps:
        day = execution["snapshot_at"]
        run("package_snapshot_binding:" + day, lambda e=execution: base(e) if e["snapshot_at"] == base_date else history(e))
        if not execution["input_metadata"].get("build_contract_sha256"):
            deferred.append("legacy_build_contract_sha256:" + execution["execution_id"])

    if set(results) != set(plan["dates"]):
        checks.append(_status("package_snapshot_result_coverage", "FAIL", "not all planned dates have bound receipts",
                              missing=sorted(set(plan["dates"]) - set(results))))
    else:
        checks.append(_status("package_snapshot_result_coverage", "PASS", dates=len(results)))
    deferred += ["package_version_raw_manifest_and_payload", "all_source_parquet_keys_values",
                 "remote_object_approval_recheck", "native_generation_reuse_not_approved"]
    statuses = [c["status"] for c in checks]
    return {"status": "FAILED" if "FAIL" in statuses else "BOUND_WITH_DEFERRED",
            "checks": checks, "checked_files": checked,
            "package_snapshot_results": results, "explicit_deferred": deferred,
            "audit": {"read_scope": "explicit bounded local metadata", "database_access": "NOT_RUN", "parquet_access": "NOT_RUN"}}
