"""Inspect local Projects Parquet snapshots without scanning their rows."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

_PARTITION = re.compile(r"^snapshot=(\d{4}-\d{2}-\d{2})$")
_PART = re.compile(r"^part-[^/]+\.parquet$")


def _canonical(value: Any) -> tuple[str, str]:
    """Return canonical UTC text and the original scalar text."""
    from pipeline.preprocessing.snapshot.policy import parse_timestamp

    original = str(value)
    # DuckDB TIMESTAMPTZ statistics may render an offset as ``+00``.
    original_for_parse = re.sub(r"([+-]\d{2})$", r"\1:00", original)
    try:
        parsed = parse_timestamp(original_for_parse, allow_naive_utc=True)
    except ValueError:
        # DuckDB renders timestamp statistics with a space separator.
        parsed = parse_timestamp(original_for_parse.replace(" ", "T", 1), allow_naive_utc=True)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z"), original


def _footer_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        if size < 12:
            raise ValueError(f"invalid Parquet footer: {path}")
        stream.seek(size - 8)
        trailer = stream.read(8)
        if trailer[-4:] != b"PAR1":
            raise ValueError(f"invalid Parquet footer: {path}")
        length = int.from_bytes(trailer[:4], "little")
        start = size - 8 - length
        if start < 4:
            raise ValueError(f"invalid Parquet footer length: {path}")
        stream.seek(start)
        footer = stream.read(length)
        if len(footer) != length:
            raise ValueError(f"truncated Parquet footer: {path}")
    return hashlib.sha256(footer).hexdigest()


def _inspect_file(con: Any, path: Path, root: Path) -> dict:
    before = path.stat()
    try:
        described = con.execute(
            "DESCRIBE SELECT SnapshotAt FROM read_parquet(?, hive_partitioning=false)",
            [str(path)],
        ).fetchall()
    except Exception as exc:
        raise ValueError(f"Cannot inspect SnapshotAt schema for {path}: {exc}") from exc
    if not described or described[0][0] != "SnapshotAt":
        raise ValueError(f"Projects file is missing SnapshotAt: {path}")
    type_name = str(described[0][1]).upper()
    if type_name not in {"TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_MS", "TIMESTAMP_S"}:
        raise ValueError(f"SnapshotAt must be timestamp: {path} ({type_name})")
    rows = con.execute("SELECT * FROM parquet_metadata(?)", [str(path)]).fetchall()
    columns = [d[0] for d in con.description]
    metadata = [dict(zip(columns, row)) for row in rows]
    groups = {}
    all_group_ids = {item.get("row_group_id") for item in metadata
                     if item.get("row_group_id") is not None}
    for item in metadata:
        if item.get("path_in_schema") == "SnapshotAt":
            groups.setdefault(item.get("row_group_id"), []).append(item)
    if not groups:
        raise ValueError(f"SnapshotAt statistics missing: {path}")
    instants: set[str] = set()
    row_count = 0
    checks = []
    if not all_group_ids or set(groups) != all_group_ids:
        raise ValueError(f"SnapshotAt statistics missing for a row group: {path}")
    source_texts: set[str] = set()
    for group_id in sorted(all_group_ids):
        stats = groups.get(group_id, [])
        if len(stats) != 1:
            raise ValueError(f"SnapshotAt statistics are not scalar: {path}")
        stat = stats[0]
        n = stat.get("row_group_num_rows")
        num_values = stat.get("num_values")
        null_count = stat.get("stats_null_count")
        if (type(n) is not int or type(num_values) is not int or type(null_count) is not int):
            raise ValueError(f"missing SnapshotAt statistics: {path} row_group={group_id}")
        minimum, maximum = stat.get("stats_min_value"), stat.get("stats_max_value")
        if n <= 0 or num_values != n or null_count != 0 or minimum is None or maximum is None:
            raise ValueError(f"invalid SnapshotAt statistics: {path} row_group={group_id}")
        if stat.get("min_is_exact") is False or stat.get("max_is_exact") is False:
            raise ValueError(f"inexact SnapshotAt statistics: {path} row_group={group_id}")
        min_text, min_source = _canonical(minimum)
        max_text, _ = _canonical(maximum)
        if min_text != max_text:
            raise ValueError(f"mixed SnapshotAt values in row group: {path} row_group={group_id}")
        instants.add(min_text)
        source_texts.add(min_source)
        row_count += n
        checks.append({"row_group_id": group_id, "rows": n, "snapshot_timestamp": min_text,
                       "min_is_exact": stat.get("min_is_exact"),
                       "max_is_exact": stat.get("max_is_exact")})
    if len(instants) != 1:
        raise ValueError(f"mixed SnapshotAt values in file: {path}")
    footer_sha = _footer_sha256(path)
    after = path.stat()
    if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise ValueError(f"Projects file changed during inspection: {path}")
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "parquet_footer_sha256": footer_sha,
        "rows": row_count,
        "snapshot_timestamp": next(iter(instants)),
        "source_timestamp_texts": sorted(source_texts),
        "pre_stats": {"bytes": before.st_size, "mtime_ns": before.st_mtime_ns},
        "post_stats": {"bytes": after.st_size, "mtime_ns": after.st_mtime_ns},
        "row_groups": checks,
    }


def _manifest(folder: Path, partition: str) -> tuple[dict, str]:
    marker = folder / "_MANIFEST.json"
    if not marker.is_file() or marker.stat().st_size == 0:
        raise ValueError(f"missing _MANIFEST.json: {folder}")
    raw = marker.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid _MANIFEST.json: {marker}") from exc
    if not isinstance(value, dict) or value.get("status") != "done" or value.get("verify") != "ok":
        raise ValueError(f"manifest is not verified: {marker}")
    if value.get("table") != "projects" or value.get("snapshot") != partition:
        raise ValueError(f"manifest identity mismatch: {marker}")
    rows = value.get("rows")
    if type(rows) is not int or rows <= 0:
        raise ValueError(f"manifest rows must be positive: {marker}")
    return value, hashlib.sha256(raw).hexdigest()


def inspect_projects(root: Path) -> dict:
    """Validate only Projects snapshot partitions and return reproducible inventory."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Projects root does not exist: {root}")
    folders = []
    for child in root.iterdir():
        if child.is_dir() and child.name.startswith("snapshot="):
            match = _PARTITION.fullmatch(child.name)
            if not match:
                raise ValueError(f"invalid snapshot partition: {child}")
            try:
                date.fromisoformat(match.group(1))
            except ValueError as exc:
                raise ValueError(f"invalid snapshot date: {child}") from exc
            folders.append((match.group(1), child))
    if not folders:
        raise ValueError("no Projects snapshot partitions found")
    import duckdb

    con = duckdb.connect(config={"threads": 1, "memory_limit": "256MB"})
    try:
        snapshots = []
        for partition, folder in sorted(folders):
            manifest, manifest_sha = _manifest(folder, partition)
            files = sorted(p for p in folder.iterdir() if p.is_file() and p.name.endswith(".parquet"))
            if not files or any(not _PART.fullmatch(p.name) for p in files):
                raise ValueError(f"missing or invalid part files: {folder}")
            records = [_inspect_file(con, p, root) for p in files]
            timestamps = {r["snapshot_timestamp"] for r in records}
            if len(timestamps) != 1:
                raise ValueError(f"mixed SnapshotAt values in partition: {folder}")
            timestamp = next(iter(timestamps))
            if timestamp[:10] != partition:
                raise ValueError(f"SnapshotAt does not match partition date: {folder}")
            total = sum(r["rows"] for r in records)
            if total != manifest["rows"]:
                raise ValueError(f"manifest rows mismatch: {folder} ({total} != {manifest['rows']})")
            snapshots.append({"snapshot": partition, "snapshot_timestamp": timestamp,
                              "manifest_sha256": manifest_sha, "files": records,
                              "file_count": len(records), "total_rows": total})
    finally:
        con.close()
    timestamps = [item["snapshot_timestamp"] for item in snapshots]
    return {"source_kind": "local-projects", "validation": "PARQUET_FOOTER_TIMESTAMP_CHECKED",
            "timestamps": timestamps, "snapshots": snapshots,
            "file_count": sum(s["file_count"] for s in snapshots),
            "total_rows": sum(s["total_rows"] for s in snapshots),
            "first_snapshot": snapshots[0]["snapshot"], "last_snapshot": snapshots[-1]["snapshot"]}
