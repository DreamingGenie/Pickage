"""Versioned integration policy and reproducible code contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb


def policy_document() -> dict:
    return {
        "policy_version": "package-snapshot-v1",
        "grain": "(package_id,snapshot_at)",
        "population": "approved package/data full population",
        "join": "exact complete key sets at the same approved snapshot",
        "downloads": "preserve COMPLETE/PARTIAL sums, NULL UNAVAILABLE, and actual zero",
        "repository": "preserve independent NULL and zero values without summing repositories",
        "quality": "one full-population row preserving download and repository selection fields",
        "details": "immutable upstream quality references with size and SHA256",
        "retry": "reuse and fully reverify an immutable completed output for identical inputs and code",
    }


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def policy_sha256() -> str:
    return hashlib.sha256(canonical_bytes(policy_document())).hexdigest()


def contract_sha256() -> str:
    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), Path(__file__).with_name("input.py"),
             Path(__file__).with_name("quality.py"),
             Path(__file__).with_name("build.py"), root / "pipeline/downloads/bronze.py",
             root / "pipeline/downloads_interval/input.py", root / "pipeline/curated/storage.py",
             root / "pipeline/postgresql/input.py", root / "pipeline/snapshot/input.py",
             root / "pipeline/snapshot/policy.py", root / "pipeline/downloads_interval/policy.py",
             root / "pipeline/repository_metrics/policy.py"]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_text(encoding="utf-8").encode() + b"\0")
    digest.update(canonical_bytes({"policy": policy_document(), "duckdb": duckdb.__version__}))
    return digest.hexdigest()
