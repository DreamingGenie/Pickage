"""Build and publish a complete package snapshot from explicitly approved inputs."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
import hashlib
import json
from pathlib import Path
import uuid

import duckdb

from pipeline.preprocessing.curated.storage import read_optional
from pipeline.downloads.bronze import publish
from pipeline.preprocessing.downloads_interval.input import _fetch, _file_digest, _safe_relative
from pipeline.minio.ingest_raw import client
from pipeline.preprocessing.common.curated_input import sql_path as _sql_path, sql_paths as _sql_paths
from pipeline.preprocessing.package_snapshot.input import BUCKET, RUN, SHA, prepare, revalidate
from pipeline.preprocessing.package_snapshot.policy import canonical_bytes, contract_sha256, policy_document, policy_sha256
from pipeline.preprocessing.package_snapshot.quality_schema import DOWNLOAD_FIELDS, QUALITY_SCHEMA, QUALITY_SCHEMA_ID, SELECTION_FIELDS, require_schema

ROOT = REPO_ROOT
PREFIX = "depsdev/v1/package-snapshot"
SCHEMAS = {
    "population_files": [("package_id", "INTEGER"), ("name", "VARCHAR"), ("repo_url", "VARCHAR")],
    "download_files": [("package_id", "INTEGER")] + DOWNLOAD_FIELDS,
    "repository_files": [("package_id", "INTEGER"), ("snapshot_at", "DATE"),
                         ("stars", "INTEGER"), ("open_issues", "INTEGER")],
    "selection_files": [("package_id", "INTEGER")] + SELECTION_FIELDS,
}
VIEWS = {"population_files": "population", "download_files": "downloads",
         "repository_files": "repository", "selection_files": "selection"}


def _reject(con, sql, message, parameters=None):
    if con.execute("SELECT EXISTS(" + sql + ")", parameters or []).fetchone()[0]:
        raise ValueError(message)


def _schema(con, path):
    return [(row[0], row[1]) for row in con.execute(
        "DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchall()]


def validate_inputs(con, prepared):
    expected = prepared["population_rows"]
    snapshot = prepared["interval"]["snapshot_at"]
    interval = prepared["interval"]
    manifest = prepared["input_manifest"]
    for group, schema in SCHEMAS.items():
        paths, records = prepared[group], manifest[group]
        if not paths or len(paths) != len(records):
            raise ValueError(group + " file inventory mismatch")
        for path, record in zip(paths, records):
            if _schema(con, path) != schema:
                raise ValueError(group + " schema mismatch")
            if "row_count" in record:
                count = con.execute("SELECT count(*) FROM read_parquet(?)", [path]).fetchone()[0]
                if count != record["row_count"]:
                    raise ValueError(group + " file row count mismatch")
        view = VIEWS[group]
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet({_sql_paths(paths)},hive_partitioning=false)")
        if con.execute(f"SELECT count(*) FROM {view}").fetchone()[0] != expected:
            raise ValueError(view + " population count mismatch")
        _reject(con, f"SELECT 1 FROM {view} WHERE package_id IS NULL OR package_id<=0", view + " invalid package ID")
        _reject(con, f"SELECT package_id FROM {view} GROUP BY package_id HAVING count(*)<>1", view + " duplicate package ID")
        if view != "population":
            _reject(con, f"SELECT 1 FROM population p FULL JOIN {view} m USING(package_id) "
                         "WHERE p.package_id IS NULL OR m.package_id IS NULL", view + " missing/extra package ID")
    _reject(con, "SELECT 1 FROM population WHERE name IS NULL OR name='' OR contains(name,chr(0))",
            "invalid package name")
    _reject(con, "SELECT name FROM population GROUP BY name HAVING count(*)<>1", "duplicate package name")
    for view in ("downloads", "repository"):
        _reject(con, f"SELECT 1 FROM {view} WHERE snapshot_at IS DISTINCT FROM ?::DATE",
                view + " snapshot mismatch", [snapshot])
    _reject(con, "SELECT 1 FROM downloads WHERE previous_snapshot_at IS DISTINCT FROM ?::DATE "
                 "OR expected_days IS DISTINCT FROM ?::INTEGER", "download interval coverage mismatch",
            [interval["previous_snapshot_at"], interval["interval_days"]])
    _reject(con, "SELECT 1 FROM downloads WHERE observed_days IS NULL OR valid_days IS NULL "
                 "OR observed_days<0 OR valid_days<0 OR valid_days>observed_days "
                 "OR observed_days>expected_days OR download_sum<0 OR quality_reasons IS NULL "
                 "OR data_status IS NULL OR data_status NOT IN ('COMPLETE','PARTIAL','UNAVAILABLE') "
                 "OR (download_sum IS NULL) IS DISTINCT FROM (valid_days=0) "
                 "OR (null_reason IS NOT NULL) IS DISTINCT FROM (valid_days=0) "
                 "OR (data_status='UNAVAILABLE') IS DISTINCT FROM (valid_days=0) "
                 "OR (data_status='COMPLETE' AND (expected_days IS NULL OR valid_days<>expected_days)) "
                 "OR (data_status='PARTIAL' AND (expected_days IS NULL OR valid_days<=0 OR valid_days>=expected_days)) "
                 "OR (expected_days IS NULL AND (observed_days<>0 OR valid_days<>0 "
                 "OR null_reason IS DISTINCT FROM 'NO_PREVIOUS_SNAPSHOT'))", "invalid download values/coverage/status")
    _reject(con, "SELECT 1 FROM downloads WHERE input_manifest_sha256 IS DISTINCT FROM ? "
                 "OR policy_sha256 IS DISTINCT FROM ? OR aggregation_policy_sha256 IS DISTINCT FROM ?",
            "download row lineage mismatch", [manifest["downloads"]["input_manifest_sha256"],
            manifest["candidate"]["policy_sha256"], manifest["downloads"]["policy_sha256"]])
    _reject(con, "SELECT 1 FROM repository WHERE stars<0 OR open_issues<0", "negative repository metric")
    _reject(con, "SELECT 1 FROM selection WHERE snapshot IS DISTINCT FROM ? "
                 "OR snapshot_timestamp IS DISTINCT FROM ? "
                 "OR (observed_timestamp IS NOT NULL AND observed_timestamp<>?::TIMESTAMPTZ)",
            "repository selection exact timestamp mismatch", [snapshot, interval["snapshot_timestamp"],
                                                              interval["snapshot_timestamp"]])
    _reject(con, "SELECT 1 FROM selection WHERE reason IS NULL OR reason NOT IN "
                 "('SELECTED','NO_VALID_REPOSITORY','NO_EXACT_OBSERVATION','PROJECT_METRIC_CONFLICT','INVALID_METRIC_VALUE') "
                 "OR mapping_status IS DISTINCT FROM CASE WHEN repo_url IS NULL THEN 'NO_SELECTED_REPOSITORY' "
                 "WHEN observed_timestamp IS NULL THEN 'NO_EXACT_PROVIDER_PATH_MATCH' ELSE 'MATCHED' END "
                 "OR (reason='SELECTED' AND (repo_url IS NULL OR observed_timestamp IS NULL)) "
                 "OR (reason='NO_VALID_REPOSITORY' AND repo_url IS NOT NULL) "
                 "OR (reason='NO_EXACT_OBSERVATION' AND (repo_url IS NULL OR observed_timestamp IS NOT NULL))",
            "invalid repository selection status")
    _reject(con, "SELECT 1 FROM repository r JOIN selection q USING(package_id) WHERE q.reason<>'SELECTED' "
                 "AND (r.stars IS NOT NULL OR r.open_issues IS NOT NULL)", "repository NULL quality mismatch")
    for path, record in zip(prepared["detail_files"], manifest["detail_files"]):
        if con.execute("SELECT count(*) FROM read_parquet(?)", [path]).fetchone()[0] != record["row_count"]:
            raise ValueError("download detail file count mismatch")


def _expected_views(con):
    con.execute("CREATE VIEW expected_service AS SELECT p.package_id,d.snapshot_at,d.download_sum AS downloads,"
                "r.stars,r.open_issues FROM population p JOIN downloads d USING(package_id) "
                "JOIN repository r USING(package_id,snapshot_at)")
    download_columns = ",".join("d." + name for name, _ in SCHEMAS["download_files"] if name != "package_id")
    repository_columns = ",".join("q." + name + " AS repository_" + name
                                  for name, _ in SCHEMAS["selection_files"] if name != "package_id")
    con.execute("CREATE VIEW expected_quality AS SELECT p.package_id,p.name," + download_columns + ","
                + repository_columns + ",r.stars,r.open_issues,NULL::TIMESTAMPTZ first_published_at,"
                "NULL::TIMESTAMPTZ selected_published_at FROM population p JOIN downloads d USING(package_id) "
                "JOIN selection q ON q.package_id=p.package_id AND q.snapshot=CAST(d.snapshot_at AS VARCHAR) "
                "JOIN repository r ON r.package_id=p.package_id AND r.snapshot_at=d.snapshot_at")
    require_schema(con, "expected_quality", QUALITY_SCHEMA)


def _quality_report(con, prepared):
    row = con.execute("SELECT count(*),count(downloads),count(stars),count(open_issues),"
                      "CAST(sum(downloads) AS VARCHAR),count(*) FILTER(WHERE downloads=0),"
                      "count(*) FILTER(WHERE stars=0),count(*) FILTER(WHERE open_issues=0) FROM service_output").fetchone()
    statuses = dict(con.execute("SELECT data_status,count(*) FROM quality_output GROUP BY 1").fetchall())
    reasons = dict(con.execute("SELECT repository_reason,count(*) FROM quality_output GROUP BY 1").fetchall())
    null_reasons = dict(con.execute("SELECT null_reason,count(*) FROM quality_output "
                                    "WHERE null_reason IS NOT NULL GROUP BY 1").fetchall())
    partial_sum = con.execute("SELECT CAST(sum(download_sum) AS VARCHAR) FROM quality_output "
                              "WHERE data_status='PARTIAL'").fetchone()[0]
    return {
        "status": "PASSED", "verification": "ALL_KEYS_SCHEMA_COUNTS_VALUES_AND_QUALITY",
        "rows": row[0], "nonnull": dict(zip(("downloads", "stars", "open_issues"), row[1:4])),
        "download_sum": row[4], "download_partial_sum": partial_sum,
        "zero": dict(zip(("downloads", "stars", "open_issues"), row[5:])),
        "download_status": statuses, "download_null_reason": null_reasons,
        "repository_reason": reasons, "detail_references": prepared["input_manifest"]["detail_files"],
        "repository_selection_references": prepared["input_manifest"]["selection_files"],
    }


def _validate_outputs(con, out, prepared):
    for role, source in (("service_output", "package_snapshot"), ("quality_output", "quality"),
                         ("identity_output", "package_identity")):
        path = out / (source + ".parquet")
        con.execute(f"CREATE VIEW {role} AS SELECT * FROM read_parquet({_sql_path(path)},hive_partitioning=false)")
        if con.execute(f"SELECT count(*) FROM {role}").fetchone()[0] != prepared["population_rows"]:
            raise ValueError(source + " output population count mismatch")
    for actual, expected in (("service_output", "expected_service"), ("quality_output", "expected_quality"),
                             ("identity_output", "(SELECT package_id,name FROM population)")):
        _reject(con, f"(SELECT * FROM {actual} EXCEPT ALL SELECT * FROM {expected}) UNION ALL "
                     f"(SELECT * FROM {expected} EXCEPT ALL SELECT * FROM {actual})",
                actual + " output values or quality differ from inputs")


def _build(prepared, out, *, memory_limit, threads):
    out.mkdir(parents=True, exist_ok=False)
    with duckdb.connect() as con:
        con.execute("SET memory_limit=?", [memory_limit])
        con.execute("SET threads=?", [threads])
        con.execute("SET TimeZone='UTC'")
        con.execute("SET temp_directory=?", [str(out.parent / "duckdb-temp")])
        validate_inputs(con, prepared)
        _expected_views(con)
        for role, sql in (("package_snapshot", "SELECT * FROM expected_service ORDER BY package_id"),
                          ("quality", "SELECT * FROM expected_quality ORDER BY package_id"),
                          ("package_identity", "SELECT package_id,name FROM population ORDER BY package_id")):
            con.execute(f"COPY ({sql}) TO {_sql_path(out / (role + '.parquet'))} (FORMAT PARQUET)")
        _validate_outputs(con, out, prepared)
        quality = _quality_report(con, prepared)
    records = []
    for role in ("package_snapshot", "package_identity", "quality"):
        path = out / (role + ".parquet")
        size, checksum = _file_digest(path)
        records.append({"path": path.name, "role": role, "bytes": size, "sha256": checksum,
                        "row_count": prepared["population_rows"]})
    return records, quality


def _reconcile_saved(prepared, out, quality, *, memory_limit, threads):
    with duckdb.connect() as con:
        con.execute("SET memory_limit=?", [memory_limit])
        con.execute("SET threads=?", [threads])
        con.execute("SET TimeZone='UTC'")
        con.execute("SET temp_directory=?", [str(out.parent / "duckdb-temp")])
        validate_inputs(con, prepared)
        _expected_views(con)
        _validate_outputs(con, out, prepared)
        if _quality_report(con, prepared) != quality:
            raise ValueError("saved quality report differs from actual output")


def _compatible(manifest, prepared, run_id, contract):
    expected = {"dataset": "package-snapshot", "status": "PASSED", "format_version": 1,
                "quality_schema": QUALITY_SCHEMA_ID,
                "run_id": run_id, "snapshot": prepared["interval"]["snapshot_at"],
                "snapshot_timestamp": prepared["interval"]["snapshot_timestamp"],
                "interval": prepared["interval"], "input_manifest": prepared["input_manifest"],
                "input_manifest_sha256": prepared["input_manifest_sha256"],
                "policy": policy_document(), "policy_sha256": policy_sha256(),
                "contract_sha256": contract, "counts": {"package_snapshot": prepared["population_rows"]},
                "required_remote_verification": "GET_SHA256_ALL_FILES"}
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("run ID already has different input, policy, or code contract")
    roles = set()
    for record in manifest.get("files", []):
        role, path = record.get("role"), _safe_relative(record.get("path"), "output path")
        if (role not in ("package_snapshot", "package_identity", "quality") or role in roles
                or path != role + ".parquet" or type(record.get("bytes")) is not int or record["bytes"] <= 0
                or not SHA.fullmatch(str(record.get("sha256", "")))
                or record.get("row_count") != prepared["population_rows"]):
            raise ValueError("invalid existing output record")
        roles.add(role)
    if roles != {"package_snapshot", "package_identity", "quality"} or manifest.get("quality", {}).get("status") != "PASSED":
        raise ValueError("existing output roles or quality missing")


def run(*, snapshot, population_run_id, population_manifest_sha256, candidate_path,
        candidate_sha256, download_run_id, download_manifest_sha256, repository_run_id,
        repository_manifest_sha256, run_id, work_dir, s3=None, workers=4,
        memory_limit="4GB", threads=2, verify_only=False, failpoint=None):
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id) or type(threads) is not int or threads < 1:
        raise ValueError("invalid run ID or threads")
    s3 = client() if s3 is None else s3
    work = Path(work_dir).resolve() / run_id
    work.mkdir(parents=True, exist_ok=True)
    prepared = prepare(s3, snapshot=snapshot, population_run_id=population_run_id,
                       population_manifest_sha256=population_manifest_sha256,
                       candidate_path=candidate_path, candidate_sha256=candidate_sha256,
                       download_run_id=download_run_id, download_manifest_sha256=download_manifest_sha256,
                       repository_run_id=repository_run_id, repository_manifest_sha256=repository_manifest_sha256,
                       cache_dir=work / "inputs", workers=workers)
    prefix = f"{PREFIX}/snapshot={snapshot}/run_id={run_id}"
    contract = contract_sha256()
    artifact = work / "artifact.json"
    remote_manifest = read_optional(s3, BUCKET, prefix + "/run_manifest.json")
    success = read_optional(s3, BUCKET, prefix + "/_SUCCESS")
    reused = remote_manifest is not None or artifact.exists()
    if success is not None and remote_manifest is None:
        raise ValueError("completed run manifest missing")
    if remote_manifest is not None:
        manifest = json.loads(remote_manifest[0])
        _compatible(manifest, prepared, run_id, contract)
        checksum = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
        lock = read_optional(s3, BUCKET, prefix + "/_INPUT.json")
        if (remote_manifest[0] != canonical_bytes(manifest) or lock is None
                or json.loads(lock[0]) != {"manifest_sha256": checksum}
                or (success is not None and success[0] != (checksum + "\n").encode())):
            raise ValueError("existing manifest, input lock, or completion marker mismatch")
        out = work / "remote-output"
        for record in manifest["files"]:
            _fetch(s3, BUCKET, prefix + "/data/" + record["path"], record, out / record["path"])
    elif artifact.exists():
        saved = json.loads(artifact.read_text(encoding="utf-8"))
        manifest = saved["manifest"]
        _compatible(manifest, prepared, run_id, contract)
        relative = _safe_relative(saved["output_dir"], "local artifact output")
        out = work / relative
        for record in manifest["files"]:
            path = out / record["path"]
            if path.is_symlink() or _file_digest(path) != (record["bytes"], record["sha256"]):
                raise ValueError("local immutable output changed")
    else:
        out = work / uuid.uuid4().hex / "output"
        print("Validating complete input keys and building integrated Parquet", flush=True)
        records, quality = _build(prepared, out, memory_limit=memory_limit, threads=threads)
        manifest = {"dataset": "package-snapshot", "status": "PASSED", "format_version": 1,
                    "quality_schema": QUALITY_SCHEMA_ID,
                    "run_id": run_id, "snapshot": snapshot,
                    "snapshot_timestamp": prepared["interval"]["snapshot_timestamp"],
                    "interval": prepared["interval"], "input_manifest": prepared["input_manifest"],
                    "input_manifest_sha256": prepared["input_manifest_sha256"],
                    "policy": policy_document(), "policy_sha256": policy_sha256(),
                    "contract_sha256": contract, "files": records, "quality": quality,
                    "counts": {"package_snapshot": prepared["population_rows"]},
                    "required_remote_verification": "GET_SHA256_ALL_FILES"}
        # A saved artifact makes retries reuse the exact bytes even if Parquet output
        # ordering could differ in another execution. Existing run artifacts are immutable.
        with artifact.open("x", encoding="utf-8") as stream:
            json.dump({"manifest": manifest, "output_dir": out.relative_to(work).as_posix()}, stream,
                      ensure_ascii=False, sort_keys=True, indent=2)
    if reused:
        _reconcile_saved(prepared, out, manifest["quality"], memory_limit=memory_limit, threads=threads)
    body = canonical_bytes(manifest)
    manifest_path = out.parent / "run_manifest.json"
    if manifest_path.exists() and manifest_path.read_bytes() != body:
        raise ValueError("local run manifest changed")
    manifest_path.write_bytes(body)
    if verify_only:
        revalidate(s3, prepared)
        result = {"status": "VERIFIED", "run_id": run_id, "prefix": prefix}
    else:
        result = publish(s3, bucket=BUCKET, prefix=prefix, root=out, manifest=manifest,
                         failpoint=failpoint, before_commit=lambda: revalidate(s3, prepared))
    return {**result, "manifest_sha256": hashlib.sha256(body).hexdigest(),
            "manifest_path": str(manifest_path), "output_dir": str(out), "quality": manifest["quality"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "population-run-id", "population-manifest-sha256", "candidate",
                 "candidate-sha256", "download-run-id", "download-manifest-sha256",
                 "repository-run-id", "repository-manifest-sha256", "run-id"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/package_snapshot/executions")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="4GB")
    parser.add_argument("--verify-only", action="store_true")
    arguments = vars(parser.parse_args())
    arguments["candidate_path"] = Path(arguments.pop("candidate"))
    print(json.dumps(run(**arguments), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
