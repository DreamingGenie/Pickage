"""Deterministic source hashes for validation evidence.

Text sources are decoded as UTF-8 and line endings are normalized to LF before
hashing.  This makes a hash describe source content rather than the checkout's
working-tree line-ending policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HASH_BASIS = "UTF-8 text with CRLF and CR normalized to LF, then SHA-256"


def normalized_utf8_bytes(data: bytes) -> bytes:
    """Return UTF-8 source bytes with CRLF and CR line endings changed to LF."""
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def normalized_sha256(data: bytes) -> str:
    return hashlib.sha256(normalized_utf8_bytes(data)).hexdigest()


def file_sha256(path: Path) -> str:
    return normalized_sha256(path.read_bytes())


def _git_blob_sha256(repo: Path, object_path: str) -> str:
    """Hash a Git object path, without consulting the working tree."""
    result = subprocess.run(
        ["git", "-C", str(repo), "show", object_path],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return normalized_sha256(result.stdout)


def git_sha256(repo: Path, revision: str, path: str) -> str:
    """Hash a path from a Git revision, without consulting the working tree."""
    return _git_blob_sha256(repo, f"{revision}:{path}")


def index_sha256(repo: Path, path: str) -> str:
    """Hash a path from the Git index, without consulting the working tree."""
    return _git_blob_sha256(repo, f":{path}")


def source_hashes(
    repo: Path,
    paths: list[str],
    *,
    revision: str | None = None,
    index: bool = False,
) -> dict[str, str]:
    if revision is not None and index:
        raise ValueError("revision and index are mutually exclusive")
    if index:
        return {path: index_sha256(repo, path) for path in paths}
    if revision is None:
        return {path: file_sha256(repo / path) for path in paths}
    return {path: git_sha256(repo, revision, path) for path in paths}


def verify_evidence(repo: Path, evidence_path: Path, *, source: str | None = None) -> None:
    """Raise ``ValueError`` when an evidence file's recorded hashes do not match."""
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("source_hash_basis") != HASH_BASIS:
        raise ValueError(f"unsupported or missing source_hash_basis (expected {HASH_BASIS!r})")
    recorded = evidence.get("source_sha256")
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("evidence has no source_sha256 map")
    revision = evidence.get("source_revision")
    if source is None:
        if not revision:
            raise ValueError("evidence has no source_revision")
        actual = source_hashes(repo, list(recorded), revision=revision)
    elif source == "index":
        actual = source_hashes(repo, list(recorded), index=True)
    elif source == "worktree":
        actual = source_hashes(repo, list(recorded))
    else:
        actual = source_hashes(repo, list(recorded), revision=source)
    mismatches = {path: {"expected": recorded[path], "actual": actual[path]} for path in recorded if recorded[path] != actual[path]}
    if mismatches:
        raise ValueError(json.dumps({"mismatches": mismatches}, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--revision", help="Hash Git blobs at this revision instead of working-tree files")
    source_group.add_argument("--index", action="store_true", help="Hash Git index entries instead of working-tree files")
    source_group.add_argument("--worktree", action="store_true", help="Hash working-tree files explicitly")
    parser.add_argument("--verify", type=Path, help="Verify source_sha256 recorded in an evidence JSON file")
    parser.add_argument("paths", nargs="*", help="Repository-relative source paths")
    args = parser.parse_args()
    if args.verify:
        if args.paths:
            parser.error("--verify cannot be combined with paths")
        try:
            selected_source = "worktree" if args.worktree else args.revision or ("index" if args.index else None)
            verify_evidence(args.repo, args.verify, source=selected_source)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            parser.exit(1, f"source evidence verification failed: {error}\n")
        print("source evidence verification: PASSED")
        return 0
    if not args.paths:
        parser.error("paths are required unless --verify is used")
    print(json.dumps(source_hashes(args.repo, args.paths, revision=args.revision, index=args.index), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
