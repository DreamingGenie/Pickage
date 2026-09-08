"""Validate a frozen snapshot candidate before loading database history."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .build import snapshot_sql
from .policy import POLICY_VERSION, build_calendar, policy_document, policy_sha256
from .projects import inspect_projects


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FILES = {"projects-inventory.json", "snapshot-dates.sql"}


def _fail(message: str) -> None:
    raise ValueError(f"invalid snapshot candidate: {message}")


def _mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{name} must be a non-empty string")
    return value


def _sha(value: Any, name: str) -> str:
    value = _text(value, name)
    if not _SHA256.fullmatch(value):
        _fail(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _read_json(raw: bytes, name: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"{name} is not valid UTF-8 JSON: {exc}")
    return _mapping(value, name)


def _listed_file(candidate_path: Path, item: Any, names: set[str]) -> tuple[str, str, bytes]:
    item = _mapping(item, "files entry")
    path_text = _text(item.get("path"), "files[].path")
    if path_text not in names:
        _fail(f"files contains unexpected path {path_text!r}")
    # Candidate paths are a fixed allow-list, and are resolved below only after
    # that check; this also keeps traversal and absolute path forms out.
    listed = (candidate_path.parent / path_text).resolve()
    if listed.parent != candidate_path.parent.resolve() or listed.name != path_text:
        _fail(f"files path escapes candidate directory: {path_text!r}")
    digest = _sha(item.get("sha256"), f"files[{path_text}].sha256")
    try:
        raw = listed.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        _fail(f"cannot read {path_text}: {exc}")
    if actual != digest:
        _fail(f"byte hash mismatch for {path_text}")
    return path_text, digest, raw


def read_candidate(path: Path) -> dict:
    """Read and revalidate a candidate and its frozen Projects source.

    This performs footer-only source inspection through :func:`inspect_projects`;
    it intentionally does not scan all Parquet rows.
    """
    candidate_path = Path(path).resolve()
    if not candidate_path.is_file():
        _fail(f"candidate file does not exist: {candidate_path}")
    try:
        candidate_bytes = candidate_path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read candidate: {exc}")
    candidate = _read_json(candidate_bytes, "candidate")

    required = ("format_version", "dataset", "status", "db_published", "service_ready",
                "policy_version", "policy_sha256", "policy", "source", "snapshot_count",
                "first_snapshot_at", "last_snapshot_at", "calendar", "files")
    for key in required:
        if key not in candidate:
            _fail(f"missing candidate.{key}")
    if type(candidate["format_version"]) is not int or candidate["format_version"] != 1 or candidate["dataset"] != "snapshot-reference":
        _fail("format_version must be 1 and dataset must be snapshot-reference")
    if candidate["status"] != "LOCAL_VALIDATED" or candidate["db_published"] is not False or candidate["service_ready"] is not False:
        _fail("status/db_published/service_ready do not describe an unpublished LOCAL_VALIDATED candidate")
    if candidate["policy_version"] != POLICY_VERSION:
        _fail("policy_version does not match the installed policy")
    if candidate["policy"] != policy_document():
        _fail("policy body does not exactly match the installed policy")
    if candidate["policy_sha256"] != policy_sha256():
        _fail("policy_sha256 does not match the installed policy")

    source = _mapping(candidate["source"], "candidate.source")
    for key in ("kind", "root", "inventory_file", "inventory_sha256"):
        if key not in source:
            _fail(f"missing candidate.source.{key}")
    if source["kind"] != "local-projects" or source["inventory_file"] != "projects-inventory.json":
        _fail("source kind or inventory_file is invalid")
    source_root = Path(_text(source["root"], "source.root"))
    if not source_root.is_absolute():
        _fail("source.root must be absolute")
    source_inventory_sha = _sha(source["inventory_sha256"], "source.inventory_sha256")

    files = candidate["files"]
    if not isinstance(files, list) or len(files) != 2:
        _fail("files must contain exactly two entries")
    seen: set[str] = set()
    contents: dict[str, bytes] = {}
    for item in files:
        item_map = _mapping(item, "files entry")
        name = _text(item_map.get("path"), "files[].path")
        if name in seen:
            _fail(f"duplicate files path {name!r}")
        seen.add(name)
        path_name, _, raw = _listed_file(candidate_path, item, _FILES)
        contents[path_name] = raw
    if seen != _FILES:
        _fail("files must contain projects-inventory.json and snapshot-dates.sql exactly once")

    inventory_bytes = contents["projects-inventory.json"]
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()
    if inventory_sha != source_inventory_sha:
        _fail("source.inventory_sha256 does not match projects-inventory.json bytes")
    inventory = _read_json(inventory_bytes, "projects-inventory.json")
    try:
        calendar = build_calendar(inventory["timestamps"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"cannot rebuild calendar from inventory: {exc}")
    if candidate["calendar"] != calendar:
        _fail("candidate.calendar does not match inventory timestamps")
    if type(candidate["snapshot_count"]) is not int or candidate["snapshot_count"] != len(calendar):
        _fail("snapshot_count does not match calendar")
    if not calendar or candidate["first_snapshot_at"] != calendar[0]["snapshot_at"] or candidate["last_snapshot_at"] != calendar[-1]["snapshot_at"]:
        _fail("first_snapshot_at/last_snapshot_at do not match calendar")
    try:
        expected_sql = snapshot_sql(calendar).encode("utf-8")
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"calendar cannot produce snapshot SQL: {exc}")
    if contents["snapshot-dates.sql"] != expected_sql:
        _fail("snapshot-dates.sql does not match regenerated SQL")

    try:
        actual_inventory = inspect_projects(source_root)
    except (OSError, ValueError) as exc:
        _fail(f"source inspection failed: {exc}")
    if actual_inventory != inventory:
        _fail("Projects source inventory changed since candidate creation")

    return {
        "candidate": candidate,
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "inventory_sha256": inventory_sha,
        "candidate_path": str(candidate_path),
        "calendar": calendar,
        "inventory": inventory,
    }
