"""Persist the normalized H3 historical result as a compact Parquet cache.

The cache stores positive count runs, target births, and one JSON quality row per
snapshot.  It deliberately has no database or production publication side effect.
"""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import hashlib
import json
from contextlib import contextmanager
import re
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256 as value_sha256
from pipeline.preprocessing.snapshot.policy import parse_timestamp
from pipeline.preprocessing.version_dependents.artifact import _reject_reparse_ancestors, _reparse, _sql_literal
from pipeline.preprocessing.version_dependents.historical import STATUSES
from pipeline.preprocessing.version_dependents.historical_reference import MAX_FIXTURE_BYTES, SOURCE_GAPS

_FORMAT = "historical-count-cache-v1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FILES = ("count_intervals.parquet", "target_population.parquet", "quality.parquet")
_QUALITY_ORIGIN = "UPSTREAM_H3_METADATA_WITH_CONSERVATION_CHECKS"
_SCHEMAS = {
    "count_intervals.parquet": [["package_id", "INTEGER"], ["version", "VARCHAR"],
                                 ["start_index", "INTEGER"], ["end_index", "INTEGER"],
                                 ["dependents_count", "BIGINT"]],
    "target_population.parquet": [["package_id", "INTEGER"], ["version", "VARCHAR"],
                                   ["birth_index", "INTEGER"]],
    "quality.parquet": [["snapshot_index", "INTEGER"], ["quality_json", "VARCHAR"]],
}


def _canonical(value: Any) -> bytes:
    return canonical_bytes(value).rstrip(b"\n")


def _sha_file(path: Path) -> tuple[int, str]:
    h = hashlib.sha256(); size = 0
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            size += len(chunk); h.update(chunk)
    return size, h.hexdigest()


def _code_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generation_contract() -> dict[str, str]:
    base = REPO_ROOT
    relative = ("pipeline/preprocessing/version_dependents/historical_cache.py", "pipeline/preprocessing/version_dependents/historical.py",
                 "pipeline/preprocessing/version_dependents/historical_semver_worker.cjs", "pipeline/preprocessing/version_dependents/historical_reference.py",
                 "pipeline/preprocessing/snapshot/policy.py", "pipeline/preprocessing/requirements_resolution/policy.py",
                 "pipeline/preprocessing/requirements_resolution/bridge.py", "pipeline/preprocessing/requirements_resolution/input.py",
                 "pipeline/preprocessing/version_dependents/artifact.py")
    result = {}
    for name in relative:
        path = base / name
        if not path.is_file(): raise ValueError(f"required generation path missing: {name}")
        result[name] = _code_sha(path)
    return result


def _sha(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")


def _lineage(lineage: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(lineage, dict) or set(lineage) != {"source_kind", "input_manifest_sha256", "policy_sha256"}:
        raise ValueError("lineage has an invalid shape")
    if lineage["source_kind"] not in {"SYNTHETIC_FIXTURE", "NORMALIZED_HISTORY_TABLES"}:
        raise ValueError("lineage source_kind is invalid")
    _sha(lineage["input_manifest_sha256"], "input_manifest_sha256")
    _sha(lineage["policy_sha256"], "policy_sha256")
    return dict(lineage)


def _calendar(calendar: list[dict[str, str]], observed: str) -> list[dict[str, str]]:
    if not isinstance(calendar, list) or not 0 < len(calendar) <= 4096:
        raise ValueError("calendar must contain 1..4096 snapshots")
    try: observed_dt = parse_timestamp(observed)
    except Exception as exc: raise ValueError("observed_snapshot_timestamp is invalid") from exc
    days, stamps = [], []
    for row in calendar:
        if not isinstance(row, dict) or set(row) != {"snapshot_at", "snapshot_timestamp"}:
            raise ValueError("calendar row has an invalid shape")
        if not isinstance(row["snapshot_at"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["snapshot_at"]):
            raise ValueError("snapshot_at must be YYYY-MM-DD")
        if not isinstance(row["snapshot_timestamp"], str): raise ValueError("snapshot_timestamp is invalid")
        try: stamp_dt = parse_timestamp(row["snapshot_timestamp"])
        except Exception as exc: raise ValueError("snapshot_timestamp is invalid") from exc
        if stamp_dt.date().isoformat() != row["snapshot_at"]: raise ValueError("snapshot date does not match snapshot_at")
        if row["snapshot_at"] in days or (stamps and stamp_dt <= stamps[-1]):
            raise ValueError("calendar must be strictly ordered and unique")
        days.append(row["snapshot_at"]); stamps.append(stamp_dt)
    last_dt = stamps[-1]
    if last_dt > observed_dt:
        raise ValueError("calendar exceeds observed_snapshot_timestamp")
    return [dict(row) for row in calendar]


def _runtime(runtime):
    if not isinstance(runtime, dict):
        raise ValueError("runtime metadata is required")
    for key in ("node_version", "semver_version", "package_arg_version"):
        if not isinstance(runtime.get(key), str) or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", runtime[key]):
            raise ValueError("runtime version is invalid: " + key)
    for key in ("semver_sha256", "package_arg_sha256", "dependency_closure_sha256"):
        _sha(runtime.get(key), "runtime " + key)
    if (runtime.get("options") != {"loose": False, "includePrerelease": False}
            or any(type(v) is not bool for v in runtime["options"].values())
            or runtime.get("equal_precedence_tie") != "original_version_utf16_ascending"
            or runtime.get("interval_end") != "exclusive"):
        raise ValueError("runtime resolution policy mismatch")
    bounds = runtime.get("bounds")
    expected = {"max_snapshots": 4096, "max_candidates": 100000, "max_unique_requirements": 512,
                "max_candidate_requirement_work": 2000000, "max_result_intervals": 20000,
                "max_frame_bytes": 7 * 1024 * 1024}
    if bounds != expected or any(type(v) is not int for v in bounds.values()):
        raise ValueError("runtime bounds mismatch")
    # Store provenance of the upstream computation; writing dates does not rerun Node.
    return json.loads(canonical_bytes(runtime))


@contextmanager
def _connection():
    with tempfile.TemporaryDirectory(prefix="historical-cache-scratch-") as scratch:
        with duckdb.connect(config={"threads": 2, "memory_limit": "1GB"}) as con:
            con.execute("SET temp_directory=?", [scratch])
            con.execute("SET max_temp_directory_size='4GB'")
            yield con


def _describe(path: Path) -> tuple[list[list[str]], int]:
    try:
        with _connection() as con:
            literal = _sql_literal(path)
            schema = [[str(x[0]), str(x[1]).upper()] for x in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet({literal}, hive_partitioning=false)").fetchall()]
            rows = int(con.execute(f"SELECT count(*) FROM read_parquet({literal}, hive_partitioning=false)").fetchone()[0])
            return schema, rows
    except Exception as exc:
        raise ValueError(f"invalid parquet file: {path.name}") from exc


def _record(path: Path) -> dict[str, Any]:
    schema, rows = _describe(path); size, digest = _sha_file(path)
    return {"name": path.name, "sha256": digest, "bytes": size, "rows": rows, "schema": schema,
            "schema_sha256": hashlib.sha256(_canonical(schema)).hexdigest()}


def _check_tables(con, n: int) -> None:
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
        actual_targets = con.execute("SELECT count(*) FROM history_target_population WHERE birth_index <= ?", [index]).fetchone()[0]
        actual_edges = con.execute("SELECT coalesce(sum(dependents_count),0) FROM history_count_intervals WHERE start_index <= ? AND end_index > ?", [index, index]).fetchone()[0]
        if int(actual_targets) != q["target_versions"] or int(actual_edges) != q["distinct_edges"]:
            raise ValueError("quality does not match cached target/count rows")


def create_cache(con, *, output: Path, calendar: list[dict[str, str]], observed_snapshot_timestamp: str,
                 lineage: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    contract = generation_contract()
    calendar = _calendar(calendar, observed_snapshot_timestamp); n = len(calendar); lineage = _lineage(lineage)
    runtime = _runtime(runtime)
    _check_tables(con, n)
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
                    "duckdb_version": duckdb.__version__}
        if generation_contract() != contract: raise ValueError("generation contract changed during write")
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


def verify_cache(cache_dir: Path, manifest_sha256: str) -> dict[str, Any]:
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
        _check_tables(con, n)
    if expected_contract != generation_contract() or file_sha256(manifest_path) != manifest_sha256:
        raise ValueError("cache identity changed during verification")
    return manifest


def create_fixture_cache(fixture_path: Path, output: Path) -> dict[str, Any]:
    """Small example adapter only; production H1 streaming belongs to H5."""
    from pipeline.preprocessing.version_dependents.historical import compute_optimized
    fixture_path, output = Path(fixture_path).absolute(), Path(output).absolute()
    _reject_reparse_ancestors(fixture_path)
    _reject_reparse_ancestors(output)
    if not fixture_path.is_file() or fixture_path.stat().st_size > MAX_FIXTURE_BYTES:
        raise ValueError("fixture is missing or exceeds 4 MiB")
    if output.exists():
        raise ValueError("output already exists")
    input_sha, contract = file_sha256(fixture_path), generation_contract()
    fixture = json.loads(fixture_path.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    # Unique logs do not overwrite a previous calculation's provenance.
    import uuid
    log_path = output.with_name(output.name + ".worker-" + uuid.uuid4().hex + ".log")
    result = compute_optimized(fixture, log_path=log_path)
    if file_sha256(fixture_path) != input_sha or generation_contract() != contract:
        raise ValueError("fixture input or generation contract changed during computation")
    calendar = [{"snapshot_at": s["snapshot_at"], "snapshot_timestamp": s["snapshot_timestamp"]}
                for s in result["snapshots"]]
    n = len(calendar)
    allvals = {(int(t["package_id"]), t["version"]): [0] * n for t in result["target_population"]}
    for i, snapshot in enumerate(result["snapshots"]):
        for row in snapshot["counts"]:
            allvals[(int(row["package_id"]), row["version"])][i] = int(row["dependents_count"])
    intervals = []
    for (package_id, version), values in allvals.items():
        start = 0
        for i in range(1, n + 1):
            if i == n or values[i] != values[i - 1]:
                if values[i - 1] > 0:
                    intervals.append({"package_id": package_id, "version": version, "start_index": start,
                                      "end_index": i, "dependents_count": values[i - 1]})
                start = i
    quality = [{"snapshot_index": i, "quality_json": canonical_bytes(s["quality"]).decode()}
               for i, s in enumerate(result["snapshots"])]
    with _connection() as con:
        for table, file, rows in (("history_count_intervals", _FILES[0], intervals),
                                  ("history_target_population", _FILES[1], result["target_population"]),
                                  ("history_quality", _FILES[2], quality)):
            schema = dict(_SCHEMAS[file])
            con.execute(f"CREATE TABLE {table} AS SELECT unnest(from_json(?,?), recursive:=true)",
                        [json.dumps(rows), json.dumps([schema])])
        if file_sha256(fixture_path) != input_sha or generation_contract() != contract:
            raise ValueError("fixture input or generation contract changed before cache creation")
        return create_cache(con, output=output, calendar=calendar,
                            observed_snapshot_timestamp=fixture["observed_snapshot_timestamp"],
                            lineage={"source_kind": "SYNTHETIC_FIXTURE", "input_manifest_sha256": value_sha256(fixture),
                                     "policy_sha256": value_sha256({
                                         "mode": "BOUNDED_H3_FIXTURE", "dependency_kinds": ["dependencies"],
                                         "source_population": "ALL_MAPPED_RELEASE_VERSIONS_WITH_KNOWN_PUBLICATION",
                                         "target_population": "MAPPED_STABLE_SEMVER", "cutoff": "published_at <= snapshot_timestamp",
                                         "selection": "MAX_SATISFYING_SEMVER", "unresolved": "PRESERVE_PARTIAL",
                                         "distinct_key": ["source_package_id", "source_version", "target_package_id", "target_version"],
                                         "alias_prerelease_protocol": "INHERIT_TASK07_POLICY"})},
                            runtime=result["runtime"])
