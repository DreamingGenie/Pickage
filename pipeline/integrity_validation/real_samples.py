"""Compare bounded samples from pinned historical package snapshots to PostgreSQL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import time

import duckdb

from .real_db import query, rows as json_rows

MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
HISTORY = Path("data/package_snapshot/history/full-history-288-20260909-v1")


def _safe(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or Path(relative).is_absolute():
        raise ValueError("source path must be a safe relative path")
    path = root.joinpath(*relative.split("/"))
    if any(part in ("", ".", "..") for part in path.relative_to(root).parts):
        raise ValueError("source path must be a safe relative path")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("source symlink/reparse point is not allowed")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("source path escapes original root")
    return path


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _select_rows(path: Path):
    with duckdb.connect(database=":memory:") as con:
        con.execute("SET threads=1")
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        rows = con.execute(
            """WITH source AS NOT MATERIALIZED (SELECT package_id,snapshot_at,downloads,stars,open_issues
               FROM read_parquet(?, hive_partitioning=false)),
            spread AS (SELECT * FROM source ORDER BY hash(package_id),package_id LIMIT 11),
            categories AS (
              (SELECT * FROM source WHERE downloads IS NULL ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE downloads=0 ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE downloads>0 ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE stars IS NULL ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE stars=0 ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE stars>0 ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE open_issues IS NULL ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE open_issues=0 ORDER BY package_id LIMIT 1)
              UNION ALL (SELECT * FROM source WHERE open_issues>0 ORDER BY package_id LIMIT 1))
            SELECT DISTINCT package_id,snapshot_at,downloads,stars,open_issues
            FROM (SELECT * FROM spread UNION ALL SELECT * FROM categories)
            ORDER BY package_id LIMIT 20""", [str(path)]).fetchall()
        read_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
    return rows, read_rows


def _db_rows(container: str, database: str, date: str, package_ids: list[int]):
    if not package_ids:
        return []
    values = ",".join(f"({int(package_id)})" for package_id in sorted(set(package_ids)))
    sql = ("SELECT ps.package_id,ps.snapshot_at,ps.downloads,ps.stars,ps.open_issues "
           "FROM public.package_snapshot ps JOIN (VALUES " + values + ") AS wanted(package_id) "
           "USING (package_id) WHERE ps.snapshot_at=" + "'" + date.replace("'", "''") + "'::date "
           "ORDER BY ps.package_id")
    result, elapsed = query(container, database, json_rows(sql))
    return result, elapsed


def sample_sources(original_root: Path, plan: dict, container: str, database: str) -> dict:
    """Compare up to 20 deterministic rows for first/middle/last planned dates."""
    root = Path(original_root).resolve(strict=True)
    dates = plan.get("dates") if isinstance(plan, dict) else None
    if not isinstance(dates, list) or not dates:
        raise ValueError("plan.dates must be a non-empty list")
    chosen = list(dict.fromkeys(str(value) for value in (dates[0], dates[len(dates) // 2], dates[-1])))
    files, samples, mismatches = [], [], []
    total_bytes = 0
    started = time.perf_counter()
    for date in chosen:
        manifest_rel = HISTORY / date / "run_manifest.json"
        if not (root / manifest_rel).exists():
            # The current base snapshot is published by the build receipt,
            # rather than in the historical date directory.
            receipt_path = _safe(root, "data/package_snapshot/S15P21A506-288/build-result.json")
            receipt = _read_json(receipt_path)
            pointer = receipt.get("result", {}).get("manifest_path")
            output_dir = receipt.get("result", {}).get("output_dir")
            if not isinstance(pointer, str) or not isinstance(output_dir, str):
                raise ValueError(f"base package_snapshot pointers missing: {date}")
            manifest_rel = Path(pointer).absolute().relative_to(root)
            base_output = Path(output_dir).absolute().relative_to(root)
        else:
            base_output = None
        manifest_path = _safe(root, manifest_rel.as_posix())
        manifest_body = manifest_path.read_bytes()
        manifest = json.loads(manifest_body)
        manifest_sha = hashlib.sha256(manifest_body).hexdigest()
        pins = plan.get("manifest_sha256", {})
        expected_pin = pins.get(date) if isinstance(pins, dict) else None
        if expected_pin and expected_pin != manifest_sha:
            raise ValueError(f"run manifest SHA mismatch: {date}")
        record = next((row for row in manifest.get("files", []) if row.get("role") == "package_snapshot"), None)
        if not isinstance(record, dict) or record.get("path") != "package_snapshot.parquet":
            raise ValueError(f"package_snapshot file record missing: {date}")
        relative = ((base_output / record["path"]) if base_output is not None else
                    (HISTORY / date / "output" / record["path"])).as_posix()
        parquet = _safe(root, relative)
        size = parquet.stat().st_size
        if size > MAX_FILE_BYTES or total_bytes + size > MAX_TOTAL_BYTES:
            raise ValueError("sample Parquet exceeds bounded size")
        digest_before = _sha(parquet)
        if size != record.get("bytes") or digest_before != record.get("sha256"):
            raise ValueError(f"package_snapshot file pin mismatch: {date}")
        rows, read_rows = _select_rows(parquet)
        values = [dict(zip(("package_id", "snapshot_at", "downloads", "stars", "open_issues"), row)) for row in rows]
        db_result = _db_rows(container, database, date, [int(row["package_id"]) for row in values])
        db_rows, db_elapsed = db_result if isinstance(db_result, tuple) else (db_result, None)
        by_id = {int(row["package_id"]): row for row in db_rows}
        for row in values:
            actual = by_id.get(int(row["package_id"]))
            if actual is None:
                mismatches.append({"date": date, "package_id": row["package_id"], "reason": "missing_database_row"})
                continue
            for field in ("snapshot_at", "downloads", "stars", "open_issues"):
                source_value = str(row[field]) if field == "snapshot_at" else row[field]
                db_value = str(actual[field]) if field == "snapshot_at" else actual[field]
                if source_value != db_value:
                    mismatches.append({"date": date, "package_id": row["package_id"], "field": field, "source": source_value, "database": db_value})
        digest_after = _sha(parquet)
        if digest_after != digest_before:
            raise ValueError(f"sample Parquet changed while reading: {date}")
        total_bytes += size
        files.append({"date": date, "source_path": relative, "bytes": size, "sha256": digest_before, "read_rows": read_rows, "database_elapsed_seconds": db_elapsed})
        samples.extend(({"date": date, **{**row, "snapshot_at": str(row["snapshot_at"])} } for row in values))
    return {"status": "PASS" if not mismatches else "FAIL", "dates": chosen, "files": files,
            "samples": samples, "mismatches": mismatches,
            "elapsed_seconds": round(time.perf_counter() - started, 3), "total_bytes": total_bytes}


__all__ = ["sample_sources"]
