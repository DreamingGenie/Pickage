"""Production cache validation using cumulative totals for all snapshot dates.

Legacy H4 files stay byte-stable. Metadata and row rejection rules mirror H4,
with the repeated per-date aggregate queries replaced by bounded event summaries.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes
from .historical import STATUSES
from .historical_reference import SOURCE_GAPS
from .historical_cache import (
    _FILES, _FORMAT, _QUALITY_ORIGIN, _SCHEMAS, _calendar, _canonical, _connection,
    _lineage, _record, _reject_reparse_ancestors, _reparse, _runtime, _sha,
    _sha_file, generation_contract,
)


def _production_sha():
    return file_sha256(Path(__file__))


def _validate_n(n):
    if type(n) is not int or not 0 < n <= 4096:
        raise ValueError("invalid snapshot count")


def _range_chmax(tags, node, left, right, lo, hi, value):
    if lo >= right or hi <= left:
        return
    if lo <= left and right <= hi:
        tags[node] = max(tags[node], value)
        return
    middle = (left + right) // 2
    _range_chmax(tags, node * 2, left, middle, lo, hi, value)
    _range_chmax(tags, node * 2 + 1, middle, right, lo, hi, value)


def daily_totals(con, n, *, counts="history_count_intervals", targets="history_target_population"):
    """Scan interval bins once; Python memory depends on calendar size only."""
    _validate_n(n)
    if counts not in {"history_count_intervals", "cache_counts"} or targets not in {"history_target_population", "cache_targets"}:
        raise ValueError("unknown production cache table")
    for table, expected in ((counts, _SCHEMAS[_FILES[0]]), (targets, _SCHEMAS[_FILES[1]])):
        schema = [[str(x[0]), str(x[1]).upper()] for x in con.execute(f"DESCRIBE {table}").fetchall()]
        if schema != expected:
            raise ValueError("daily totals schema mismatch")
    if con.execute(f"""SELECT EXISTS(SELECT 1 FROM {counts}
        WHERE package_id IS NULL OR package_id<=0 OR version IS NULL OR trim(version)=''
        OR start_index IS NULL OR end_index IS NULL OR start_index<0 OR start_index>=end_index
        OR end_index>? OR dependents_count IS NULL OR dependents_count<=0 OR dependents_count>2147483647)""", [n]).fetchone()[0]:
        raise ValueError("count interval has invalid bounds or count")
    births = [0] * n
    for index, amount in con.execute(f"SELECT birth_index,count(*) FROM {targets} GROUP BY birth_index").fetchall():
        if type(index) is not int or not 0 <= index < n:
            raise ValueError("target population birth is out of range")
        births[index] = int(amount)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE production_interval_bins AS
        SELECT start_index,end_index,count(*) positive,sum(dependents_count)::BIGINT total,
               max(dependents_count) maximum FROM {counts} GROUP BY start_index,end_index""")
    edge_events, positive_events = [0] * (n + 1), [0] * (n + 1)
    tags = [0] * (4 * n + 8)
    cursor = con.execute("SELECT * FROM production_interval_bins")
    while rows := cursor.fetchmany(4096):
        for start, end, positive, total, maximum in rows:
            edge_events[start] += total
            edge_events[end] -= total
            positive_events[start] += positive
            positive_events[end] -= positive
            _range_chmax(tags, 1, 0, n, start, end, maximum)
    maximums = [0] * n

    def propagate(node, left, right, inherited):
        value = max(inherited, tags[node])
        if right - left == 1:
            maximums[left] = value
        else:
            middle = (left + right) // 2
            propagate(node * 2, left, middle, value)
            propagate(node * 2 + 1, middle, right, value)

    propagate(1, 0, n, 0)
    results = []
    target_count = edge_count = positive = 0
    for index in range(n):
        target_count += births[index]
        edge_count += edge_events[index]
        positive += positive_events[index]
        if edge_count < 0 or positive < 0 or positive > target_count:
            raise ValueError("cache daily totals are inconsistent")
        results.append({"target_versions": target_count, "positive_target_versions": positive,
                        "distinct_edges": edge_count, "max_dependents_count": maximums[index]})
    if edge_count + edge_events[n] or positive + positive_events[n]:
        raise ValueError("count events do not close")
    return results


def check_tables(con, n: int) -> list[dict[str, int]]:
    _validate_n(n)
    required = {"history_count_intervals", "history_target_population", "history_quality"}
    present = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    if not required <= present:
        raise ValueError("missing required history tables")
    for table, expected in (("history_count_intervals", _SCHEMAS["count_intervals.parquet"]),
                            ("history_target_population", _SCHEMAS["target_population.parquet"]),
                            ("history_quality", _SCHEMAS["quality.parquet"])):
        actual = [[str(x[0]), str(x[1]).upper()] for x in con.execute(f"DESCRIBE {table}").fetchall()]
        if actual != expected:
            raise ValueError(f"{table} schema mismatch")
    if con.execute("SELECT count(*) FROM history_quality").fetchone()[0] != n:
        raise ValueError("quality must contain exactly one row per snapshot")
    if con.execute("SELECT count(*) FROM history_quality WHERE snapshot_index IS NULL OR snapshot_index < 0 OR snapshot_index >= ?", [n]).fetchone()[0]:
        raise ValueError("quality snapshot index out of bounds")
    if con.execute("SELECT count(*) FROM (SELECT snapshot_index FROM history_quality GROUP BY 1 HAVING count(*) <> 1)").fetchone()[0]:
        raise ValueError("quality snapshot indexes must be unique")
    if con.execute("SELECT count(*) FROM history_target_population WHERE package_id IS NULL OR package_id <= 0 OR version IS NULL OR trim(version)='' OR birth_index IS NULL OR birth_index < 0 OR birth_index >= ?", [n]).fetchone()[0]:
        raise ValueError("target population has invalid row")
    if con.execute("SELECT count(*) FROM (SELECT package_id,version FROM history_target_population GROUP BY 1,2 HAVING count(*) <> 1)").fetchone()[0]:
        raise ValueError("target population keys must be unique")
    bad = con.execute("""SELECT count(*) FROM history_count_intervals
        WHERE package_id IS NULL OR package_id <= 0 OR version IS NULL OR trim(version)=''
        OR start_index IS NULL OR end_index IS NULL OR start_index < 0 OR start_index >= end_index
        OR end_index > ? OR dependents_count IS NULL OR dependents_count <= 0
        OR dependents_count > 2147483647""", [n]).fetchone()[0]
    if bad: raise ValueError("count interval has invalid row")
    if con.execute("""SELECT count(*) FROM history_count_intervals c
        LEFT JOIN history_target_population t USING(package_id,version)
        WHERE t.package_id IS NULL OR c.start_index < t.birth_index""").fetchone()[0]:
        raise ValueError("count interval starts before target birth")
    if con.execute("""SELECT count(*) FROM (SELECT package_id,version,start_index,
        lag(end_index) OVER(PARTITION BY package_id,version ORDER BY start_index,end_index) prior_end
        FROM history_count_intervals) WHERE prior_end IS NOT NULL AND start_index < prior_end""").fetchone()[0]:
        raise ValueError("count intervals overlap")
    totals = daily_totals(con, n)
    for index, raw in con.execute("SELECT snapshot_index, quality_json FROM history_quality ORDER BY snapshot_index").fetchall():
        try: q = json.loads(raw)
        except Exception as exc: raise ValueError("quality_json is not JSON") from exc
        if not isinstance(q, dict): raise ValueError("quality_json must be an object")
        for key in ("source_versions", "target_versions", "selected_declarations", "resolved_declarations", "unresolved_declarations", "distinct_edges", "duplicate_resolved_declarations"):
            if type(q.get(key)) is not int or q[key] < 0: raise ValueError("quality count is invalid")
        if q["resolved_declarations"] + q["unresolved_declarations"] != q["selected_declarations"]:
            raise ValueError("quality declaration conservation failed")
        if q["distinct_edges"] + q["duplicate_resolved_declarations"] != q["resolved_declarations"]:
            raise ValueError("quality edge conservation failed")
        if q.get("resolution_status") not in {"COMPLETE", "PARTIAL"}: raise ValueError("quality status is invalid")
        for field in ("source_status_counts", "declaration_status_counts"):
            values = q.get(field)
            if not isinstance(values, dict) or any(type(v) is not int or v < 0 for v in values.values()):
                raise ValueError("quality detailed status counts are invalid")
        source_states = SOURCE_GAPS | {"OBSERVED_NO_DEPENDENCIES", "RESOLVED", "PARTIAL", "UNRESOLVED"}
        if (set(q["source_status_counts"]) - source_states
                or set(q["declaration_status_counts"]) - STATUSES):
            raise ValueError("quality contains unknown status")
        if sum(q["source_status_counts"].values()) != q["source_versions"]:
            raise ValueError("source status conservation failed")
        if sum(q["declaration_status_counts"].values()) != q["selected_declarations"]:
            raise ValueError("declaration status conservation failed")
        if q["declaration_status_counts"].get("RESOLVED", 0) != q["resolved_declarations"]:
            raise ValueError("resolved declaration status conservation failed")
        for field in ("source_null_publication_excluded", "source_future_excluded"):
            if type(q.get(field)) is not int or q[field] < 0:
                raise ValueError("quality exclusion count is invalid")
        for field, keys in (("excluded_kind_declarations", {"peer_dependencies", "optional_dependencies"}),
                            ("target_rejections", {"INVALID_TARGET_SEMVER", "PRERELEASE_TARGET"})):
            values = q.get(field)
            if (not isinstance(values, dict) or set(values) - keys
                    or (field == "excluded_kind_declarations" and set(values) != keys)
                    or any(type(v) is not int or v < 0 for v in values.values())):
                raise ValueError("quality exclusion details are invalid")
        expected_status = "COMPLETE" if q["unresolved_declarations"] == 0 and not any(q["source_status_counts"].get(k, 0) for k in SOURCE_GAPS) else "PARTIAL"
        if q["resolution_status"] != expected_status: raise ValueError("quality status does not match details")
        actual_targets = totals[index]["target_versions"]
        actual_edges = totals[index]["distinct_edges"]
        if int(actual_targets) != q["target_versions"] or int(actual_edges) != q["distinct_edges"]:
            raise ValueError("quality does not match cached target/count rows")
    return totals


def serialize_tables(con, *, output: Path, calendar: list[dict[str, str]], observed_snapshot_timestamp: str,
                 lineage: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    contract = generation_contract()
    production_sha = _production_sha()
    calendar = _calendar(calendar, observed_snapshot_timestamp); n = len(calendar); lineage = _lineage(lineage)
    runtime = _runtime(runtime)
    check_tables(con, n)
    root = Path(output).absolute(); _reject_reparse_ancestors(root)
    if root.exists(): raise ValueError("output already exists")
    root.mkdir(parents=True)
    try:
        for table, name, order in (("history_count_intervals", _FILES[0], "1,2,3,4"),
                                   ("history_target_population", _FILES[1], "1,2,3"),
                                   ("history_quality", _FILES[2], "1")):
            con.execute(f"COPY (SELECT * FROM {table} ORDER BY {order}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(root / name)])
        manifest = {"format": _FORMAT, "calendar": calendar, "observed_snapshot_timestamp": observed_snapshot_timestamp,
                    "lineage": lineage, "runtime": runtime, "generation_contract": {"code_sha256": contract},
                    "files": [_record(root / name) for name in _FILES], "ready_for_load": False,
                    "verification_scope": "NORMALIZED_HISTORY_TABLES_ONLY", "quality_origin": _QUALITY_ORIGIN,
                    "duckdb_version": duckdb.__version__, "production_cache_sha256": production_sha}
        if generation_contract() != contract or _production_sha() != production_sha:
            raise ValueError("generation contract changed during write")
        temporary = root / "cache_manifest.json.tmp"
        with temporary.open("xb") as stream:
            stream.write(canonical_bytes(manifest))
            stream.flush()
            import os
            os.fsync(stream.fileno())
        temporary.replace(root / "cache_manifest.json")
        size, digest = _sha_file(root / "cache_manifest.json")
        return {"cache_dir": str(root), "manifest_sha256": digest, "manifest": manifest, "manifest_bytes": size}
    except Exception:
        # Preserve partial output for diagnosis and never overwrite a prior run.
        raise


def verify_cache(cache_dir: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    manifest_sha256 = expected_manifest_sha256
    production_sha = _production_sha()
    if not isinstance(manifest_sha256, str): raise ValueError("pinned manifest SHA is required")
    _sha(manifest_sha256, "manifest_sha256")
    root = Path(cache_dir).absolute(); _reject_reparse_ancestors(root); manifest_path = root / "cache_manifest.json"
    if not root.is_dir() or {p.name for p in root.iterdir()} != {*_FILES, "cache_manifest.json"}:
        raise ValueError("cache file set mismatch")
    if any(_reparse(root / name) or not (root / name).is_file() for name in (*_FILES, "cache_manifest.json")):
        raise ValueError("unsafe or missing cache file")
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("cache manifest exceeds size bound")
    size, digest = _sha_file(manifest_path)
    if digest != manifest_sha256: raise ValueError("manifest SHA mismatch")
    raw_manifest = manifest_path.read_bytes()
    try: manifest = json.loads(raw_manifest)
    except Exception as exc: raise ValueError("manifest is not JSON") from exc
    if raw_manifest != _canonical(manifest) + b"\n": raise ValueError("manifest canonical bytes changed")
    if (not isinstance(manifest, dict) or manifest.get("format") != _FORMAT
            or manifest.get("ready_for_load") is not False
            or manifest.get("verification_scope") != "NORMALIZED_HISTORY_TABLES_ONLY"
            or manifest.get("quality_origin") != _QUALITY_ORIGIN
            or manifest.get("duckdb_version") != duckdb.__version__):
        raise ValueError("manifest contract mismatch")
    calendar = _calendar(manifest.get("calendar"), manifest.get("observed_snapshot_timestamp")); n = len(calendar)
    _lineage(manifest.get("lineage")); _runtime(manifest.get("runtime"))
    expected_contract = manifest.get("generation_contract", {}).get("code_sha256")
    if expected_contract != generation_contract(): raise ValueError("generation contract changed")
    if "production_cache_sha256" in manifest and manifest["production_cache_sha256"] != production_sha:
        raise ValueError("production cache generation changed")
    files = manifest.get("files")
    if not isinstance(files, list) or any(not isinstance(x, dict) for x in files) or [x.get("name") for x in files] != list(_FILES): raise ValueError("file manifest mismatch")
    with _connection() as con:
        for record, name in zip(files, _FILES):
            path = root / name
            if not path.is_file(): raise ValueError(f"missing cache file: {name}")
            actual = _record(path)
            if actual != record or actual["schema"] != _SCHEMAS[name]: raise ValueError(f"cache file mismatch: {name}")
        def parquet_view(name, path):
            literal = "'" + str(path.resolve()).replace("'", "''") + "'"
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({literal}, hive_partitioning=false)")
        parquet_view("history_count_intervals", root / _FILES[0])
        parquet_view("history_target_population", root / _FILES[1])
        parquet_view("history_quality", root / _FILES[2])
        check_tables(con, n)
    if expected_contract != generation_contract() or file_sha256(manifest_path) != manifest_sha256:
        raise ValueError("cache identity changed during verification")
    verify_cache_bytes(root, manifest_sha256, manifest)
    if _production_sha() != production_sha:
        raise ValueError("production cache code changed during verification")
    return manifest


create_cache = serialize_tables


def verify_cache_bytes(cache_dir, expected_manifest_sha256, manifest):
    """Recheck all bytes after one full validation; never replace initial validation."""
    _sha(expected_manifest_sha256, "manifest_sha256")
    root = Path(cache_dir).absolute()
    _reject_reparse_ancestors(root)
    if not root.is_dir() or {p.name for p in root.iterdir()} != {*_FILES, "cache_manifest.json"}:
        raise ValueError("cache file set mismatch")
    if any(_reparse(root / name) or not (root / name).is_file() for name in (*_FILES, "cache_manifest.json")):
        raise ValueError("unsafe or missing cache file")
    path = root / "cache_manifest.json"
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("cache manifest exceeds size bound")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256 or raw != _canonical(manifest) + b"\n":
        raise ValueError("cache manifest changed during verification")
    records = manifest.get("files")
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records) or [r.get("name") for r in records] != list(_FILES):
        raise ValueError("cache file manifest mismatch")
    if manifest.get("generation_contract", {}).get("code_sha256") != generation_contract():
        raise ValueError("cache generation changed")
    if "production_cache_sha256" in manifest and manifest["production_cache_sha256"] != _production_sha():
        raise ValueError("production cache generation changed")
    for record, name in zip(records, _FILES):
        size, digest = _sha_file(root / name)
        if size != record["bytes"] or digest != record["sha256"]:
            raise ValueError("cache file changed during verification: " + name)
