"""Proof that a finalization retry may reuse completed partition receipts.

The partition workers already wrote immutable receipts before the previous run
failed.  This module verifies the old plan and every accepted pointer before a
new finalizer is allowed to read those receipts.  It deliberately does not
rewrite the old plan or its checkpoints.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents.artifact import _validate_sha
from pipeline.preprocessing.version_dependents.historical_artifact import _path, _read_json


_FORMAT = "finalization-recovery-v1"
_PROOF_ENV = "PICKAGE_FINALIZATION_RECOVERY_PROOF"
_PROOF_SHA_ENV = "PICKAGE_FINALIZATION_RECOVERY_PROOF_SHA256"
_ALLOWED_STEMS = frozenset({
    "historical_production_quality",
    "historical_parallel",
    "historical_parallel_input",
    "finalization_recovery",
})
_PROOF_KEYS = frozenset({
    "format", "run_root", "plan_sha256", "previous_contract",
    "new_contract", "checkpoints", "helper_sha256",
})


def _changed_leaf_is_reviewed(path: tuple[str, ...]) -> bool:
    """Return whether a changed contract leaf belongs to an approved file."""
    leaf = path[-1]
    if leaf in {"parallel_input_sha256", "weighted_quality_sha256"}:
        return True
    return leaf in _ALLOWED_STEMS


def _compare_contracts(previous: Any, current: Any, path: tuple[str, ...] = ()) -> None:
    """Compare contracts while allowing only reviewed code hash leaves."""
    if isinstance(previous, dict) or isinstance(current, dict):
        if not isinstance(previous, dict) or not isinstance(current, dict):
            raise ValueError("Finalization recovery contract shape changed")
        if set(previous) != set(current):
            raise ValueError("Finalization recovery contract keys changed")
        for key in sorted(previous):
            _compare_contracts(previous[key], current[key], path + (str(key),))
        return
    if isinstance(previous, list) or isinstance(current, list):
        if previous != current:
            raise ValueError("Finalization recovery contract list changed")
        return
    if previous == current:
        return
    if not _changed_leaf_is_reviewed(path):
        raise ValueError("Finalization recovery contains an unreviewed contract change")
    _validate_sha(previous, "previous reviewed code hash")
    _validate_sha(current, "new reviewed code hash")


def _checkpoint_paths(root: Path, plan: dict[str, Any]) -> dict[str, Path]:
    partitions = plan.get("partitions")
    if not isinstance(partitions, dict):
        raise ValueError("Finalization recovery plan partitions are missing")
    result: dict[str, Path] = {}
    for value in partitions:
        if not isinstance(value, str) or not value.isdecimal():
            raise ValueError("Finalization recovery has an unsafe partition id")
        relative = f"partitions/{int(value):03d}/complete.json"
        candidate = _path(root / relative)
        if candidate.relative_to(root).as_posix() != relative:
            raise ValueError("Finalization recovery checkpoint path changed")
        result[relative] = candidate
    return result


def verify(root: str | Path, plan: dict[str, Any], current_contract: dict[str, Any]):
    """Verify a pinned finalization proof, or return ``None`` for a normal run."""
    root = _path(root)
    previous = plan.get("generation_contract")
    if previous == current_contract:
        return None

    proof_name = os.environ.get(_PROOF_ENV)
    proof_sha = os.environ.get(_PROOF_SHA_ENV)
    if not proof_name or not proof_sha:
        raise ValueError("Finalization recovery proof is required for a changed contract")
    _validate_sha(proof_sha, "finalization recovery proof SHA")
    proof_path = _path(Path(proof_name))
    if file_sha256(proof_path) != proof_sha:
        raise ValueError("Finalization recovery proof SHA mismatch")
    proof = _read_json(proof_path)
    if set(proof) != _PROOF_KEYS or proof.get("format") != _FORMAT:
        raise ValueError("Finalization recovery proof format mismatch")
    if _path(proof["run_root"]) != root:
        raise ValueError("Finalization recovery proof run root mismatch")
    plan_path = root / "run_plan.json"
    if _read_json(plan_path) != plan:
        raise ValueError("Finalization recovery plan object mismatch")
    plan_sha = file_sha256(plan_path)
    if proof["plan_sha256"] != plan_sha:
        raise ValueError("Finalization recovery proof plan SHA mismatch")
    if proof["previous_contract"] != previous or proof["new_contract"] != current_contract:
        raise ValueError("Finalization recovery proof contract mismatch")
    _compare_contracts(previous, current_contract)

    checkpoints = proof["checkpoints"]
    if not isinstance(checkpoints, dict):
        raise ValueError("Finalization recovery checkpoint map is invalid")
    expected = _checkpoint_paths(root, plan)
    if set(checkpoints) != set(expected):
        raise ValueError("Finalization recovery checkpoint coverage mismatch")
    for relative, path in expected.items():
        digest = checkpoints[relative]
        _validate_sha(digest, f"checkpoint SHA: {relative}")
        if file_sha256(path) != digest:
            raise ValueError("Finalization recovery checkpoint SHA mismatch")

    helper_sha = proof["helper_sha256"]
    _validate_sha(helper_sha, "finalization recovery helper SHA")
    if file_sha256(Path(__file__)) != helper_sha:
        raise ValueError("Finalization recovery helper changed")
    return {"path": str(proof_path), "sha256": proof_sha}
