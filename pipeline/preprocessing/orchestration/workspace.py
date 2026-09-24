"""Safe cleanup for run-local preprocessing scratch space.

Only directories created by this run and carrying the ownership marker may be
removed. Remote manifests and checkpoints remain the recovery source of truth.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


MARKER = ".pickage-run-workspace.json"
_STAGES = {"snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents"}


def _reject_reparse(path: Path) -> None:
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("workspace cleanup refuses symlink ancestor")
        try:
            if getattr(parent.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
                raise ValueError("workspace cleanup refuses reparse point")
        except FileNotFoundError:
            continue


def claim(root: Path, run_id: str) -> Path:
    root = Path(root).absolute()
    if not run_id or not isinstance(run_id, str):
        raise ValueError("workspace run_id is required")
    _reject_reparse(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / MARKER
    _reject_reparse(marker)
    if marker.exists():
        try:
            body = json.loads(marker.read_text(encoding="utf-8"))
        except Exception as error:
            raise ValueError("invalid workspace ownership marker") from error
        if body.get("format") != 1 or body.get("run_id") != run_id or body.get("root") != str(root):
            raise ValueError("workspace belongs to another run")
    else:
        if any(root.iterdir()):
            raise ValueError("refusing unmarked non-empty workspace")
        marker.write_text(json.dumps({"format": 1, "run_id": run_id, "root": str(root)},
                                     sort_keys=True), encoding="utf-8")
    return root


def cleanup_stage(root: Path, stage: str) -> list[str]:
    """Remove only known scratch children after a verified remote checkpoint."""
    root = Path(root).absolute()
    if stage not in _STAGES:
        raise ValueError("unknown workspace stage")
    _reject_reparse(root)
    marker = root / MARKER
    _reject_reparse(marker)
    if not marker.is_file():
        raise ValueError("workspace ownership marker is missing")
    body = json.loads(marker.read_text(encoding="utf-8"))
    if body.get("format") != 1 or not body.get("run_id") or body.get("root") != str(root):
        raise ValueError("workspace ownership marker does not match root")
    candidates = set()
    # Snapshot candidate/projects metadata is a cross-stage input and must
    # survive until package_snapshot has consumed the exact inventory.
    stage_dirs = {"package_version": "package-version", "package_snapshot": "package-snapshot"}
    if stage != "snapshot":
        candidates.add(stage_dirs.get(stage, stage))
    # These are stage-private caches. Snapshot inputs/candidate are retained
    # because repository needs the candidate and projects metadata later.
    if stage == "package_version":
        candidates.update({"inputs/.raw-cache", "inputs/requirements", "inputs/versions_min"})
    if stage == "repository":
        candidates.update({"inputs/versions_full", "inputs/curated"})
    if stage == "package_snapshot":
        candidates.update({"snapshot", "inputs/projects"})
    removed = []
    for relative in sorted(candidates):
        target = root.joinpath(*Path(relative).parts).absolute()
        if not target.is_relative_to(root) or target == root:
            raise ValueError("unsafe workspace cleanup target")
        if not target.exists():
            continue
        _reject_reparse(target)
        shutil.rmtree(target)
        removed.append(relative.replace("\\", "/"))
    return removed


def cleanup_failed(root: Path) -> list[str]:
    """Drop bounded scratch after failure; remote checkpoints remain authoritative."""
    root = Path(root).absolute()
    _reject_reparse(root)
    marker = root / MARKER
    _reject_reparse(marker)
    if not marker.is_file():
        raise ValueError("workspace ownership marker is missing")
    body = json.loads(marker.read_text(encoding="utf-8"))
    if body.get("format") != 1 or body.get("root") != str(root) or not body.get("run_id"):
        raise ValueError("invalid workspace ownership marker")
    removed = []
    for child in list(root.iterdir()):
        if child.name.startswith("snapshot-prepare-") or child.name in {
                "snapshot", "package-version", "downloads", "repository",
                "package-snapshot", "dependents"}:
            _reject_reparse(child)
            if child.is_dir(): shutil.rmtree(child)
            else: child.unlink()
            removed.append(child.name)
    inputs = root / "inputs"
    if inputs.is_dir():
        for child in list(inputs.iterdir()):
            if child.name in {"projects", "requirements", "versions_full", "versions_min", "curated", ".raw-cache", "download-cache"}:
                _reject_reparse(child)
                shutil.rmtree(child)
                removed.append("inputs/" + child.name)
    return sorted(removed)


__all__ = ["MARKER", "claim", "cleanup_stage", "cleanup_failed"]
