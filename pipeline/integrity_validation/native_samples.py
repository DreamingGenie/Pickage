"""Check only explicitly selected tiny Parquet copies against pinned file records."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from .local_bundle import (MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_SAMPLES, MAX_SAMPLE_ROWS,
                           read_bounded, relative_file)


def _schema(dataset, role, manifest):
    if dataset == "package-version":
        from pipeline.postgresql.input import _SCHEMAS
        return _SCHEMAS[role]
    from pipeline.package_snapshot.load import SCHEMAS
    from pipeline.package_snapshot.quality_schema import (QUALITY_SCHEMA, QUALITY_SCHEMA_ID,
                                                         LEGACY_OBSERVED_SCHEMA)
    if role != "quality":
        return SCHEMAS[role]
    marker = manifest.get("quality_schema")
    if marker == QUALITY_SCHEMA_ID:
        return QUALITY_SCHEMA
    if marker is None:
        return LEGACY_OBSERVED_SCHEMA
    raise ValueError("Unsupported observed quality schema version")


def verify_samples(root: Path, samples: list, selection: dict) -> dict:
    if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
        raise ValueError("At most 16 explicitly selected sample files are allowed")
    records = {record["key"]: record for record in selection["records"]}
    chosen, seen, local_paths, size_total = [], set(), set(), 0
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {"key", "path"}:
            raise ValueError("Sample fields must be key and path")
        key = sample["key"]
        if not isinstance(key, str) or key not in records or key in seen:
            raise ValueError("Sample must name a unique file in the pinned native manifest")
        record = records[key]
        if record["bytes"] > MAX_FILE_BYTES:
            raise ValueError("Selected native file exceeds 2 MiB; it is not a small sample")
        path = relative_file(root, sample["path"])
        if path in local_paths:
            raise ValueError("Each sample requires a distinct local file")
        if path.stat().st_size != record["bytes"]:
            raise ValueError("Sample byte count differs from the pinned native record")
        size_total += record["bytes"]
        if size_total > MAX_TOTAL_BYTES:
            raise ValueError("Selected sample files exceed the 8 MiB total limit")
        chosen.append((sample, path, record))
        seen.add(key)
        local_paths.add(path)
    checked, total_rows = [], 0
    metadata = selection["metadata"]
    # Copy only capped, explicitly selected bytes to private temporary paths. The
    # SHA, footer and schema checks then examine the same bytes, with no source writes.
    with TemporaryDirectory(prefix="integrity-samples-") as scratch:
        with duckdb.connect(":memory:", config={"threads": 1, "memory_limit": "128MB",
                            "max_temp_directory_size": "0B", "autoinstall_known_extensions": False,
                            "autoload_known_extensions": False}) as con:
            for index, (sample, path, record) in enumerate(chosen):
                body = read_bounded(path)
                digest = hashlib.sha256(body).hexdigest()
                if len(body) != record["bytes"] or digest != record["sha256"]:
                    raise ValueError("Sample SHA/size differs from the pinned native record")
                copied = Path(scratch) / f"sample-{index}.parquet"
                copied.write_bytes(body)
                rows = con.execute("SELECT num_rows FROM parquet_file_metadata(?)", [str(copied)]).fetchall()
                if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
                    raise ValueError("Invalid sample Parquet row metadata")
                count = rows[0][0]
                total_rows += count
                if total_rows > MAX_SAMPLE_ROWS:
                    raise ValueError("Sample footer row count exceeds the 5,000-row total limit")
                if "row_count" in record and record["row_count"] != count:
                    raise ValueError("Sample row count differs from the pinned native record")
                actual = [(row[0], row[1]) for row in con.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(copied)]).fetchall()]
                if actual != _schema(metadata["dataset"], record["role"], metadata["manifest"]):
                    raise ValueError("Sample Parquet schema mismatch: " + record["role"])
                checked.append({"key": sample["key"], "path": sample["path"], "role": record["role"],
                                "bytes": len(body), "sha256": digest, "rows": count,
                                "checks": "SIZE_SHA256_SCHEMA_FOOTER_ROWS_MATCH"})
    counts = metadata["counts"]
    coverage = {}
    for role in sorted({record["role"] for record in records.values()}):
        group = [record for record in records.values() if record["role"] == role]
        selected = [row for row in checked if row["role"] == role]
        all_selected = len(selected) == len(group)
        expected = counts[role] if metadata["dataset"] == "package-version" else counts["package_snapshot"]
        actual = sum(row["rows"] for row in selected)
        if actual > expected or (all_selected and actual != expected):
            raise ValueError("Sample rows disagree with native manifest total: " + role)
        coverage[role] = {"manifest_files": len(group), "checked_files": len(selected),
                          "checked_rows": actual, "manifest_rows": expected,
                          "all_role_files_selected": all_selected}
    return {"status": "MATCH" if checked else "NOT_RUN", "files": checked,
            "bytes_read": size_total, "rows": total_rows, "coverage": coverage,
            "row_values_checked": False}
