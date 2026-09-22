"""Validate the fixed local input set for the npm downloads Bronze run."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import duckdb


_RUN = re.compile(r"^[A-Za-z0-9_-]+$")
_DATE_PART = re.compile(r"^date=(\d{4}-\d{2}-\d{2})$")
_PART = re.compile(r"^part-\d+\.jsonl\.gz$")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _record(root: Path, path: Path, role: str, *, row_count=None,
            min_date=None, max_date=None, statistics_note=None, sha256=None) -> dict[str, Any]:
    record = {"path": _rel(root, path), "role": role, "bytes": path.stat().st_size,
            "sha256": sha256 or _digest(path), "row_count": row_count,
            "min_date": min_date, "max_date": max_date}
    if statistics_note:
        record["statistics_note"] = statistics_note
    return record


def _schema(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    return [{"column": row[0], "type": row[1], "nullable": row[2] == "YES"}
            for row in con.execute("DESCRIBE " + sql, params).fetchall()]


def _require_schema(schema: list[dict[str, Any]], required: dict[str, str], label: str) -> None:
    actual = {item["column"]: item["type"] for item in schema}
    missing = sorted(set(required) - set(actual))
    if missing:
        raise ValueError(f"{label} schema missing columns: {missing}")
    for name, expected in required.items():
        if expected not in actual[name].upper():
            raise ValueError(f"{label}.{name} must be {expected}, got {actual[name]}")


def _iso(value: Any) -> str | None:
    return None if value is None else str(value)


def _read_json_bytes(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid metadata JSON: {_rel(path.parent, path)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"metadata must be an object: {path}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return _read_json_bytes(path.read_bytes(), path)
    except OSError as exc:
        raise ValueError(f"cannot read metadata: {path}: {exc}") from exc


def _assert_no_symlink(root: Path) -> None:
    for directory, dirs, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        if directory_path.is_symlink() or any((directory_path / name).is_symlink() for name in dirs + files):
            raise ValueError(f"symlink is not allowed in download source: {directory_path}")


def _excluded(root: Path, path: Path) -> str | None:
    name = path.name
    rel = _rel(root, path)
    if name.endswith(".broken"):
        return "broken partial output"
    if name in {"checkpoint.sqlite", "targets_smoke.csv"}:
        return "checkpoint or smoke fixture"
    if path.suffix == ".log" or name.endswith(".err.log"):
        return "execution log"
    if rel.startswith("parquet_smoke/") or rel.startswith("raw/run=smoke-"):
        return "smoke output"
    return None


def _select(root: Path, source_run: str, target_name: str) -> tuple[list[tuple[Path, str]], list[dict[str, str]]]:
    target = root / target_name
    raw_root = root / "raw" / f"run={source_run}"
    daily_root = root / "parquet" / "downloads"
    status_path = root / "parquet" / "downloads_status.parquet"
    run_json = raw_root / "run.json"
    manifest_json = raw_root / "manifest.json"
    if not target.is_file():
        raise ValueError(f"target CSV is missing: {_rel(root, target)}")
    if not raw_root.is_dir() or not run_json.is_file() or not manifest_json.is_file():
        raise ValueError(f"source run metadata is incomplete: raw/run={source_run}")
    if not daily_root.is_dir() or not status_path.is_file():
        raise ValueError("download Parquet source is incomplete")
    selected: list[tuple[Path, str]] = [(target, "target_csv"), (run_json, "source_metadata"),
                                        (manifest_json, "source_metadata"), (status_path, "status_parquet")]
    raw_parts = sorted(p for p in raw_root.iterdir() if p.is_file() and _PART.fullmatch(p.name))
    if not raw_parts:
        raise ValueError(f"no raw response parts found for {source_run}")
    selected.extend((p, "raw_response") for p in raw_parts)
    daily_files: list[Path] = []
    for folder in sorted(p for p in daily_root.iterdir() if p.is_dir()):
        match = _DATE_PART.fullmatch(folder.name)
        if not match:
            raise ValueError(f"invalid download date partition: {_rel(root, folder)}")
        files = sorted(folder.glob("*.parquet"))
        if not files:
            raise ValueError(f"empty download date partition: {_rel(root, folder)}")
        daily_files.extend(files)
    if not daily_files:
        raise ValueError("no daily download Parquet files found")
    selected.extend((p, "daily_parquet") for p in daily_files)
    selected_paths = {p.resolve() for p, _ in selected}
    excluded: list[dict[str, str]] = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: _rel(root, p)):
        if path.resolve() in selected_paths:
            continue
        reason = _excluded(root, path)
        if reason is None:
            raise ValueError(f"unknown regular file must be classified: {_rel(root, path)}")
        excluded.append({"path": _rel(root, path), "reason": reason})
    return selected, excluded


def discover_source(root: Path, source_run: str,
                    target_name: str = "targets_top100k_20260902.csv") -> dict[str, Any]:
    """Return the deterministic selected/excluded file inventory without hashing."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"download source root does not exist: {root}")
    if not _RUN.fullmatch(source_run):
        raise ValueError("source_run contains unsupported characters")
    if Path(target_name).name != target_name or not target_name.endswith(".csv"):
        raise ValueError("target_name must be a root-level CSV filename")
    _assert_no_symlink(root)
    selected, excluded = _select(root, source_run, target_name)
    return {"files": [{"path": _rel(root, p), "role": role} for p, role in selected],
            "excluded": excluded}


def inspect_source(root: Path, source_run: str,
                   target_name: str = "targets_top100k_20260902.csv") -> dict[str, Any]:
    """Select and validate one download run without modifying source files.

    Raw gzip response rows are intentionally not parsed here: this stage checks
    their complete byte identity and leaves response structure/lineage to the
    raw-response validator.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"download source root does not exist: {root}")
    if not _RUN.fullmatch(source_run):
        raise ValueError("source_run contains unsupported characters")
    if Path(target_name).name != target_name or not target_name.endswith(".csv"):
        raise ValueError("target_name must be a root-level CSV filename")
    _assert_no_symlink(root)

    target = root / target_name
    raw_root = root / "raw" / f"run={source_run}"
    status_path = root / "parquet" / "downloads_status.parquet"
    run_json = raw_root / "run.json"
    manifest_json = raw_root / "manifest.json"
    selected, excluded = _select(root, source_run, target_name)
    daily_files = [p for p, role in selected if role == "daily_parquet"]

    pre_state = {p.resolve(): (p.stat().st_size, _digest(p)) for p, _ in selected}
    # 기본 4GB/4스레드는 상위 10만(일별 7천만 행) 기준이다. 확장 46.9만(3.3억 행)은 4GB 에서
    # 품질 검사 조인이 OOM 으로 죽어(2026-09-22, S15P21A506-453) 환경 변수로만 올릴 수 있게 했다.
    # 값을 주지 않으면 동작은 이전과 같다. temp_directory 를 주면 한도를 넘는 중간 결과를 디스크로 흘린다.
    config = {"threads": int(os.environ.get("PICKAGE_DOWNLOADS_DUCKDB_THREADS", "4")),
              "memory_limit": os.environ.get("PICKAGE_DOWNLOADS_DUCKDB_MEMORY", "4GB")}
    temp_dir = os.environ.get("PICKAGE_DOWNLOADS_DUCKDB_TEMP")
    if temp_dir:
        config["temp_directory"] = temp_dir
    con = duckdb.connect(database=":memory:", config=config)
    try:
        csv_sql = "read_csv_auto(?, header=true)"
        csv_schema = _schema(con, f"SELECT * FROM {csv_sql}", [str(target)])
        _require_schema(csv_schema, {"name": "VARCHAR"}, "target_csv")
        target_nulls = con.execute(f"SELECT count(*) FROM {csv_sql} WHERE name IS NULL OR trim(name)=''", [str(target)]).fetchone()[0]
        csv_counts = con.execute(f"SELECT count(*), count(DISTINCT name) FROM {csv_sql}", [str(target)]).fetchone()
        duplicate_rows = con.execute(
            f"SELECT name, count(*) AS occurrences FROM {csv_sql} GROUP BY name HAVING count(*) > 1 ORDER BY name",
            [str(target)]).fetchall()
        targets = {row[0] for row in con.execute(f"SELECT DISTINCT name FROM {csv_sql} WHERE name IS NOT NULL", [str(target)]).fetchall()}

        parquet_paths = [p.as_posix() for p in daily_files]
        physical_daily_schema = _schema(con, "SELECT * FROM read_parquet(?, hive_partitioning=false)", [parquet_paths])
        has_physical_date = "date" in {item["column"] for item in physical_daily_schema}
        physical_schema_rows = con.execute(
            "SELECT file_name, name, duckdb_type, column_id FROM parquet_schema(?) "
            "WHERE name <> 'schema' ORDER BY file_name, column_id", [parquet_paths]).fetchall()
        physical_by_file: dict[str, list[tuple[Any, ...]]] = {}
        for file_name, name, duckdb_type, column_id in physical_schema_rows:
            physical_by_file.setdefault(str(file_name).replace('\\', '/'), []).append(
                (name, duckdb_type, column_id))
        signatures = {tuple(rows) for rows in physical_by_file.values()}
        if len(signatures) != 1:
            examples = {key: value for key, value in sorted(physical_by_file.items())}
            raise ValueError(f"daily Parquet physical schemas differ: {list(examples.items())[:2]}")
        daily_sql = ("read_parquet(?, hive_partitioning=false)" if has_physical_date
                     else "read_parquet(?, hive_partitioning=true, hive_types={'date':'DATE'})")
        daily_schema = _schema(con, f"SELECT * FROM {daily_sql}", [parquet_paths])
        _require_schema(daily_schema, {"name": "VARCHAR", "downloads": "INT", "imputed_gap": "BOOLEAN", "date": "DATE"}, "daily_parquet")
        daily_count, daily_min, daily_max = con.execute(
            f"SELECT count(*), min(date), max(date) FROM {daily_sql}", [parquet_paths]).fetchone()
        daily_stats = {Path(row[0]).resolve(): row[1:] for row in con.execute(
            f"SELECT filename, count(*), min(date), max(date) FROM read_parquet(?, filename=true) GROUP BY filename", [parquet_paths]).fetchall()}
        physical_date_mismatch = 0
        if has_physical_date:
            physical_date_mismatch = con.execute(
                "SELECT count(*) FROM read_parquet(?, hive_partitioning=false, filename=true) "
                "WHERE date IS DISTINCT FROM try_cast(regexp_extract(filename, 'date=([0-9]{4}-[0-9]{2}-[0-9]{2})', 1) AS DATE)",
                [parquet_paths]).fetchone()[0]
        negatives = con.execute(f"SELECT count(*) FROM {daily_sql} WHERE downloads < 0", [parquet_paths]).fetchone()[0]
        duplicate_keys = con.execute(
            f"SELECT name, date, count(*) AS occurrences FROM {daily_sql} GROUP BY name,date HAVING count(*) > 1 ORDER BY name,date LIMIT 10",
            [parquet_paths]).fetchall()
        invalid_daily_keys = con.execute(
            f"SELECT count(*) FROM {daily_sql} WHERE name IS NULL OR trim(name)='' OR date IS NULL", [parquet_paths]).fetchone()[0]
        daily_names = {row[0] for row in con.execute(f"SELECT DISTINCT name FROM {daily_sql} WHERE name IS NOT NULL", [parquet_paths]).fetchall()}
        null_count, gap_count, zero_count = con.execute(
            f"SELECT count(*) FILTER (WHERE downloads IS NULL), count(*) FILTER (WHERE imputed_gap), count(*) FILTER (WHERE downloads=0) FROM {daily_sql}",
            [parquet_paths]).fetchone()
        gap_disagreement = con.execute(
            f"SELECT count(*) FROM {daily_sql} WHERE (imputed_gap IS TRUE) IS DISTINCT FROM (downloads IS NULL)", [parquet_paths]).fetchone()[0]

        status_sql = "read_parquet(?)"
        status_schema = _schema(con, f"SELECT * FROM {status_sql}", [str(status_path)])
        _require_schema(status_schema, {"name": "VARCHAR", "status": "VARCHAR", "first_date": "DATE", "last_date": "DATE"}, "status_parquet")
        status_count, status_min, status_max = con.execute(
            f"SELECT count(*), min(first_date), max(last_date) FROM {status_sql}", [str(status_path)]).fetchone()
        duplicate_status_names = con.execute(
            f"SELECT name,count(*) FROM {status_sql} GROUP BY name HAVING count(*) > 1", [str(status_path)]).fetchall()
        invalid_status_keys = con.execute(
            f"SELECT count(*) FROM {status_sql} WHERE name IS NULL OR trim(name)='' OR status IS NULL OR trim(status)=''", [str(status_path)]).fetchone()[0]
        status_counts = con.execute(
            f"SELECT status, count(*) FROM {status_sql} GROUP BY status ORDER BY status", [str(status_path)]).fetchall()
        status_names = {row[0] for row in con.execute(f"SELECT DISTINCT name FROM {status_sql} WHERE name IS NOT NULL", [str(status_path)]).fetchall()}
        invalid_status = con.execute(
            f"SELECT status, count(*) FROM {status_sql} GROUP BY status HAVING status NOT IN ('READY','NOT_FOUND') ORDER BY status", [str(status_path)]).fetchall()
        status_conflicts = con.execute(
            f"SELECT s.name,s.status,count(d.date) FROM {status_sql} s JOIN {daily_sql} d USING(name) WHERE s.status='NOT_FOUND' GROUP BY s.name,s.status HAVING count(d.date)>0 ORDER BY s.name",
            [str(status_path), parquet_paths]).fetchall()
        ready_without_daily = con.execute(
            f"SELECT count(*) FROM {status_sql} s LEFT JOIN (SELECT DISTINCT name FROM {daily_sql}) d USING(name) WHERE s.status='READY' AND d.name IS NULL",
            [str(status_path), parquet_paths]).fetchone()[0]
        ready_coverage_rows = con.execute(
            f"""WITH bounds AS (
                    SELECT name, first_date, last_date,
                           date_diff('day', first_date, last_date) + 1 AS expected_days
                    FROM {status_sql} WHERE status='READY'
                ), observed AS (
                    SELECT name, count(DISTINCT date) AS observed_days,
                           count(*) FILTER (WHERE downloads IS NULL) AS null_values
                    FROM {daily_sql} GROUP BY name
                )
                SELECT b.name, b.expected_days,
                       coalesce(o.observed_days, 0) AS observed_days,
                       greatest(b.expected_days - coalesce(o.observed_days, 0), 0) AS missing_days,
                       coalesce(o.null_values, 0) AS null_values
                FROM bounds b LEFT JOIN observed o USING(name)
                ORDER BY b.name""",
            [str(status_path), parquet_paths]).fetchall()
        daily_without_status = con.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT name FROM {daily_sql}) d LEFT JOIN {status_sql} s USING(name) WHERE s.name IS NULL",
            [parquet_paths, str(status_path)]).fetchone()[0]
        date_mismatches = con.execute(
            f"SELECT count(*) FROM {status_sql} s JOIN (SELECT name,min(date) first_date,max(date) last_date FROM {daily_sql} GROUP BY name) d USING(name) WHERE s.first_date IS NOT NULL AND (d.first_date < s.first_date OR d.last_date > s.last_date)",
            [str(status_path), parquet_paths]).fetchone()[0]
    finally:
        con.close()

    post_state = {p.resolve(): (p.stat().st_size, _digest(p)) for p, _ in selected}
    if pre_state != post_state:
        raise ValueError("selected source files changed during inspection")

    if duplicate_keys:
        raise ValueError(f"duplicate daily (name,date) keys: {duplicate_keys[:3]}")
    if invalid_daily_keys:
        raise ValueError(f"null or empty daily key fields: {invalid_daily_keys}")
    if target_nulls:
        raise ValueError(f"null or empty target names: {target_nulls}")
    if gap_disagreement:
        raise ValueError(f"imputed_gap/downloads disagreement: {gap_disagreement}")
    if physical_date_mismatch:
        raise ValueError(f"Parquet physical date differs from partition path: {physical_date_mismatch}")
    if negatives:
        raise ValueError(f"negative downloads values: {negatives}")
    if invalid_status:
        raise ValueError(f"unsupported download statuses: {invalid_status}")
    if duplicate_status_names:
        raise ValueError(f"duplicate status names: {duplicate_status_names[:3]}")
    if invalid_status_keys:
        raise ValueError(f"null or empty status key fields: {invalid_status_keys}")
    missing_target = sorted((daily_names | status_names) - targets)
    if missing_target:
        raise ValueError(f"download/status references unknown targets: {missing_target[:3]}")
    if targets != status_names:
        raise ValueError("target and status name sets differ")
    if status_conflicts:
        raise ValueError(f"NOT_FOUND status has daily rows: {status_conflicts[:3]}")
    if daily_without_status:
        raise ValueError(f"daily names without status rows: {daily_without_status}")
    if date_mismatches:
        raise ValueError(f"status first/last date mismatch: {date_mismatches}")
    ready_period_coverage = {
        "packages": len(ready_coverage_rows),
        "expected_days": sum(row[1] or 0 for row in ready_coverage_rows),
        "observed_days": sum(row[2] for row in ready_coverage_rows),
        "missing_days": sum(row[3] or 0 for row in ready_coverage_rows),
        "packages_with_missing_days": sum((row[3] or 0) > 0 for row in ready_coverage_rows),
        "packages_with_null_values": sum((row[4] or 0) > 0 for row in ready_coverage_rows),
        "complete_packages": sum((row[3] or 0) == 0 and (row[4] or 0) == 0 for row in ready_coverage_rows),
        "incomplete_examples": [
            {"name": row[0], "expected_days": row[1], "observed_days": row[2],
             "missing_days": row[3], "null_values": row[4]}
            for row in ready_coverage_rows if (row[3] or 0) > 0 or (row[4] or 0) > 0
        ][:20],
    }

    files = []
    for path, role in selected:
        if role == "target_csv":
            files.append(_record(root, path, role, row_count=csv_counts[0], sha256=pre_state[path.resolve()][1]))
        elif role == "daily_parquet":
            row_count, min_date, max_date = daily_stats[path.resolve()]
            files.append(_record(root, path, role, row_count=row_count,
                                 min_date=_iso(min_date), max_date=_iso(max_date), sha256=pre_state[path.resolve()][1]))
        elif role == "status_parquet":
            files.append(_record(root, path, role, row_count=status_count,
                                 min_date=_iso(status_min), max_date=_iso(status_max), sha256=pre_state[path.resolve()][1]))
        else:
            files.append(_record(root, path, role, statistics_note="raw response is gzip JSONL; row/date parsing belongs to lineage validation" if role == "raw_response" else "metadata file has no row/date statistics", sha256=pre_state[path.resolve()][1]))
    metadata_bytes = {run_json: run_json.read_bytes(), manifest_json: manifest_json.read_bytes()}
    if any(hashlib.sha256(raw).hexdigest() != pre_state[path.resolve()][1] for path, raw in metadata_bytes.items()):
        raise ValueError("metadata changed during inspection")
    source_metadata = {"run.json": _read_json_bytes(metadata_bytes[run_json], run_json),
                       "manifest.json": _read_json_bytes(metadata_bytes[manifest_json], manifest_json)}
    if source_metadata["run.json"].get("run") != source_run or source_metadata["manifest.json"].get("run") != source_run:
        raise ValueError("source metadata run does not match source_run")
    if source_metadata["manifest.json"].get("final") is not True:
        raise ValueError("source manifest is not final")
    if Path(str(source_metadata["run.json"].get("targets", ""))).name != target_name:
        raise ValueError("run metadata target does not match target_name")
    if Path(str(source_metadata["manifest.json"].get("targets", ""))).name != target_name:
        raise ValueError("manifest target does not match target_name")
    return {
        "format_version": 1, "dataset": "npm-downloads", "source_run": source_run,
        "target_name": target_name, "files": files, "excluded": excluded,
        "quality": {
            "target_rows": csv_counts[0], "target_unique_names": csv_counts[1],
            "target_duplicate_names": [{"name": r[0], "occurrences": r[1]} for r in duplicate_rows],
            "daily_rows": daily_count, "daily_min_date": _iso(daily_min), "daily_max_date": _iso(daily_max),
            "daily_duplicate_keys": [], "negative_downloads": negatives,
            "status_rows": status_count, "status_unique_names": len(status_names),
            "status_min_date": _iso(status_min), "status_max_date": _iso(status_max),
            "status_counts": {str(r[0]): r[1] for r in status_counts},
            "target_reference_missing": [], "not_found_with_daily_rows": [],
            "downloads_null": null_count, "downloads_imputed_gap": gap_count,
            "downloads_zero": zero_count,
            "target_null_or_blank_names": target_nulls,
            "target_status_name_set_equal": targets == status_names,
            "imputed_gap_downloads_disagreement": gap_disagreement,
            "physical_date_path_mismatch": physical_date_mismatch,
            "daily_physical_schema_files": len(physical_by_file),
            "ready_without_daily_rows": ready_without_daily,
            "ready_period_coverage": ready_period_coverage,
            "consistency_checks": {
                "daily_keys_unique": True, "downloads_nonnegative": negatives == 0,
                "status_values_allowlisted": not invalid_status,
                "daily_names_are_targets": not missing_target,
                "status_names_are_targets": not missing_target,
                "not_found_has_no_daily_rows": not status_conflicts,
                "daily_names_have_status": daily_without_status == 0,
                "status_date_range_matches_daily": date_mismatches == 0,
                "target_names_are_nonblank": target_nulls == 0,
                "target_and_status_name_sets_equal": targets == status_names,
                "imputed_gap_matches_null_downloads": gap_disagreement == 0,
                "physical_date_matches_partition": physical_date_mismatch == 0,
                "daily_physical_schemas_equal": len(signatures) == 1,
            },
        },
        "source_metadata": source_metadata,
        "schemas": {"targets": csv_schema, "daily_downloads": daily_schema, "download_status": status_schema},
    }
