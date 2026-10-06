"""Bounded, read-only checks for npm downloads raw-to-Parquet lineage."""
from __future__ import annotations
import gzip, json
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

_REQUIRED = {"name", "rank", "kind", "start", "end", "tier", "fetched_at", "task_id", "status", "downloads"}
_MAX_SAMPLE_PACKAGES = 8

def _safe_path(root: Path, relative: Any) -> tuple[str, Path]:
    if not isinstance(relative, str) or "\\" in relative or not relative:
        raise ValueError(f"input path must be a non-empty POSIX relative path: {relative!r}")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise ValueError(f"input path must be root-relative: {relative}")
    current = root
    for part in posix.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"input path traverses a symlink: {relative}")
    path = current.resolve()
    try: path.relative_to(root)
    except ValueError as error: raise ValueError(f"input path escapes root: {relative}") from error
    if not path.is_file(): raise ValueError(f"input file is missing: {relative}")
    return posix.as_posix(), path

def _raw_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip(): continue
            try: row = json.loads(line)
            except json.JSONDecodeError as error: raise ValueError(f"invalid JSON at {path}:{number}") from error
            if not isinstance(row, dict) or not _REQUIRED.issubset(row): raise ValueError(f"invalid npm response shape at {path}:{number}")
            if not isinstance(row["name"], str) or not row["name"]: raise ValueError(f"invalid package name at {path}:{number}")
            try:
                start, end = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
                fetched = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
            except (TypeError, ValueError) as error: raise ValueError(f"invalid response dates/timestamp at {path}:{number}") from error
            if end < start or fetched.tzinfo is None: raise ValueError(f"invalid response date range/timestamp at {path}:{number}")
            status, downloads = row["status"], row["downloads"]
            if status not in {"ok", "not_found"}: raise ValueError(f"unknown response status at {path}:{number}: {status!r}")
            if status == "not_found":
                if downloads is not None: raise ValueError(f"not_found response must have null downloads at {path}:{number}")
                yield row; continue
            if not isinstance(downloads, list): raise ValueError(f"ok response downloads must be an array at {path}:{number}")
            for item in downloads:
                if not isinstance(item, dict) or not isinstance(item.get("day"), str): raise ValueError(f"invalid daily value at {path}:{number}")
                try: day = date.fromisoformat(item["day"])
                except ValueError as error: raise ValueError(f"invalid daily date at {path}:{number}") from error
                value = item.get("downloads")
                if not isinstance(value, int) or isinstance(value, bool) or value < 0: raise ValueError(f"invalid daily downloads at {path}:{number}")
                if not start <= day <= end: raise ValueError(f"daily date outside response range at {path}:{number}")
            yield row

def _expected_series(rows: list[dict[str, Any]], names: set[str]) -> dict[tuple[str, str], tuple[int | None, bool]]:
    latest: dict[tuple[str, str], tuple[datetime, int]] = {}
    for row in rows:
        if row["name"] not in names or row["status"] != "ok": continue
        fetched = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
        for item in row["downloads"]:
            key = (row["name"], item["day"]); previous = latest.get(key)
            if previous is None or fetched > previous[0]: latest[key] = (fetched, item["downloads"])
            elif fetched == previous[0] and item["downloads"] != previous[1]: raise ValueError(f"same fetched_at has conflicting values for {key}")
    by_name: dict[str, list[tuple[str, int]]] = {name: [] for name in names}
    for (name, day), (_, value) in latest.items(): by_name[name].append((day, value))
    expected: dict[tuple[str, str], tuple[int | None, bool]] = {}
    for name, values in by_name.items():
        values.sort()
        for index, (day, value) in enumerate(values):
            window = sorted(v for _, v in values[max(0, index - 7):index + 8])
            median = window[len(window)//2] if len(window) % 2 else (window[len(window)//2-1] + window[len(window)//2]) / 2
            gap = value == 0 and median >= 1000
            expected[(name, day)] = (None if gap else value, gap)
    return expected

def _parquet_values(paths: list[Path], names: set[str]) -> dict[tuple[str, str], tuple[int | None, bool]]:
    if not paths or not names: return {}
    try: import duckdb
    except ImportError: return {}
    con = duckdb.connect()
    try:
        rows = con.execute("SELECT name, CAST(date AS VARCHAR), downloads, imputed_gap FROM read_parquet(?) WHERE name IN (SELECT unnest(?))", [[str(p) for p in paths], sorted(names)]).fetchall()
    finally: con.close()
    return {(name, day): (value, bool(gap)) for name, day, value, gap in rows}

def inspect_lineage(root: Path, files: list[dict], source_run: str) -> dict:
    """Stream raw responses and compare a bounded package sample to Parquet."""
    root = Path(root).resolve()
    if not isinstance(source_run, str) or not source_run: raise ValueError("source_run is required")
    raw_records = [r for r in files if r.get("role") == "raw_response"]
    parquet_records = [r for r in files if r.get("role") in {"daily_parquet", "parquet"}]
    if not raw_records: raise ValueError("at least one raw_response file is required")
    seen: set[str] = set(); resolved_raw: list[tuple[str, Path]] = []
    for record in raw_records:
        relative, path = _safe_path(root, record.get("path"))
        if relative in seen: raise ValueError(f"duplicate input path: {relative}")
        seen.add(relative); resolved_raw.append((relative, path))
    response_count = 0; package_names: set[str] = set(); ok_names: set[str] = set(); status_counts = {"ok": 0, "not_found": 0}; min_day = max_day = None; declared_min = declared_max = None; raw_files = []
    for relative, path in resolved_raw:
        count = 0; file_min = file_max = None
        for row in _raw_rows(path):
            count += 1; response_count += 1; package_names.add(row["name"]); status_counts[row["status"]] += 1
            start, end = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
            declared_min = start if declared_min is None or start < declared_min else declared_min; declared_max = end if declared_max is None or end > declared_max else declared_max
            if row["status"] == "ok": ok_names.add(row["name"])
            for item in row["downloads"] or []:
                day = date.fromisoformat(item["day"])
                file_min = day if file_min is None or day < file_min else file_min; file_max = day if file_max is None or day > file_max else file_max
                min_day = day if min_day is None or day < min_day else min_day; max_day = day if max_day is None or day > max_day else max_day
        raw_files.append({"path": relative, "role": "raw_response", "row_count": count, "min_date": file_min.isoformat() if file_min else None, "max_date": file_max.isoformat() if file_max else None})
    sample_names = set(sorted(ok_names)[:_MAX_SAMPLE_PACKAGES]); selected_rows = []
    for _, path in resolved_raw: selected_rows.extend(row for row in _raw_rows(path) if row["name"] in sample_names)
    expected = _expected_series(selected_rows, sample_names)
    parquet_paths = [_safe_path(root, r.get("path"))[1] for r in parquet_records]; actual = _parquet_values(parquet_paths, sample_names)
    comparison = []
    for key, expected_value in sorted(expected.items()):
        actual_value = actual.get(key); match = actual_value == expected_value if actual_value is not None else None
        comparison.append({"name": key[0], "day": key[1], "expected": expected_value[0], "expected_imputed_gap": expected_value[1], "parquet": actual_value[0] if actual_value else None, "parquet_imputed_gap": actual_value[1] if actual_value else None, "match": match})
    expected_keys, actual_keys = set(expected), set(actual)
    missing_keys, extra_keys = sorted(expected_keys - actual_keys), sorted(actual_keys - expected_keys)
    mismatches = [item for item in comparison if item["match"] is False]
    if parquet_paths and (missing_keys or extra_keys):
        raise ValueError(f"raw-to-Parquet sample key mismatch: missing={missing_keys[:3]} extra={extra_keys[:3]}")
    if mismatches: raise ValueError(f"raw-to-Parquet sample mismatch: {mismatches[:3]}")
    comparable = [item for item in comparison if item["match"] is not None]
    target = next((r for r in files if r.get("role") == "target_csv"), None)
    target_info = {"status": "UNKNOWN"}
    if target:
        _, target_path = _safe_path(root, target.get("path")); import csv
        with target_path.open(encoding="utf-8", newline="") as stream:
            target_names = {row.get("name", "") for row in csv.DictReader(stream) if row.get("name")}
        target_info = {"status": "CHECKED", "target_unique_name_count": len(target_names), "raw_only_names": sorted(package_names - target_names)[:20], "target_without_raw_names": sorted(target_names - package_names)[:20]}
    return {"source_run": source_run, "raw_files": raw_files, "summary": {"response_row_count": response_count, "status_counts": status_counts, "unique_package_count": len(package_names), "min_date": min_day.isoformat() if min_day else None, "max_date": max_day.isoformat() if max_day else None, "declared_start_min": declared_min.isoformat() if declared_min else None, "declared_end_max": declared_max.isoformat() if declared_max else None, "sample_package_names": sorted(sample_names), "deterministic_sample": comparison, "sample_compared": bool(comparable), "sample_match": bool(comparable) and all(x["match"] for x in comparable), "missing_sample_keys": missing_keys, "extra_sample_keys": extra_keys, "target": target_info, "daily_row_count_is_not_inferred": True}, "provenance": {"generator_candidate": {"path": "pipeline/collectors/downloads/to_parquet.py", "commit": "33b49adef8ea6f6f01bf1f91048ffcf239c7a73d", "blob_sha": "d9562f12af10e62eac98e81f604c9635522ba56a", "status": "HISTORY_ONLY_CANDIDATE"}, "generator_execution_version": "UNVERIFIED", "rules": ["status=ok responses are unnested", "(name,date) latest fetched_at wins", "ROWS BETWEEN 7 PRECEDING AND 7 FOLLOWING median >= 1000 changes zero to NULL + imputed_gap=true"], "unverified": ["historical generator was found but its use for this input run and full rebuild were not verified"]}}

__all__ = ["inspect_lineage"]
