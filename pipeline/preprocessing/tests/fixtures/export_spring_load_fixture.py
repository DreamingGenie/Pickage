"""Export a small producer-shaped Curated fixture for the Spring load smoke test.

The fixture is built by the same two-snapshot producer path used by the Python
orchestration tests.  It is deliberately an explicit export: Java tests never
import Python or depend on the in-memory FakeS3 implementation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import duckdb

from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.orchestration.weekly_request import build_request
from pipeline.preprocessing.tests.fixtures.weekly_fixture import (
    BRONZE_RUN,
    SNAPSHOT,
    make_weekly_fixture,
)
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import DOWNLOAD_RUN

CURATED_BUCKET = "pickage-curated"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest_info(objects: dict[tuple[str, str], bytes], snapshot: str, run_id: str) -> dict:
    prefix = f"depsdev/v1/curated-bundle/snapshot={snapshot}/run_id={run_id}"
    key = prefix + "/run_manifest.json"
    if hasattr(objects, "objects"):
        objects = objects.objects
    body = objects[(CURATED_BUCKET, key)]
    return {"prefix": prefix, "manifest_key": key, "sha256": _sha(body), "snapshot": snapshot}


def _jsonable(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _parquet_rows(body: bytes, columns: list[str], scratch: Path) -> list[dict]:
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"{_sha(body)}.parquet"
    path.write_bytes(body)
    with duckdb.connect() as con:
        rows = con.execute("SELECT * FROM read_parquet(?) ORDER BY ALL", [str(path)]).fetchall()
    return [{column: _jsonable(value) for column, value in zip(columns, row)}
            for row in rows]


def _expected(objects: dict[tuple[str, str], bytes], infos: dict[str, dict], scratch: Path) -> dict:
    """Materialize the exact rows selected by CuratedBundleReader."""
    by_key = {key: body for (bucket, key), body in objects.items() if bucket == CURATED_BUCKET}

    def manifest(info):
        return json.loads(by_key[info["manifest_key"]])

    def stage_file(info, stage, predicate):
        stage_info = manifest(info)["stages"][stage]
        stage_manifest_key = stage_info["manifest_key"]
        stage_manifest = json.loads(by_key[stage_manifest_key])
        record = next(record for record in stage_manifest["files"] if predicate(record))
        key = record.get("key") or stage_info["prefix"] + "/data/" + record["path"]
        return by_key[key]

    weekly = infos["weekly"]
    package_version = manifest(weekly)["stages"]["package_version"]["manifest_key"]
    package_version_manifest = json.loads(by_key[package_version])
    package_body = next(r for r in package_version_manifest["files"] if "/master_package/" in r["key"])
    version_body = next(r for r in package_version_manifest["files"] if "/master_version/" in r["key"])
    package_snapshot = stage_file(weekly, "package_snapshot", lambda r: r.get("role") == "package_snapshot")
    dependents = stage_file(weekly, "dependents", lambda r: r.get("role") == "version_dependents")
    packages = _parquet_rows(package_body and by_key[package_body["key"]],
                             ["package_id", "name", "repo_url"], scratch)
    versions = _parquet_rows(by_key[version_body["key"]],
                             ["version", "package_id", "published_at", "ordinal", "description", "licenses", "deprecated", "dependency"], scratch)
    snapshots = _parquet_rows(package_snapshot,
                              ["package_id", "snapshot_at", "downloads", "stars", "open_issues"], scratch)
    dependent_rows = _parquet_rows(dependents,
                                   ["package_id", "version", "snapshot_at", "dependents_count"], scratch)
    null_rows = sum(row["dependents_count"] is None for row in dependent_rows)
    loaded = [row for row in dependent_rows if row["dependents_count"] is not None]
    return {
        "master": {"package": packages, "version": versions},
        "weekly": {"package_snapshot": snapshots, "version_snapshot": loaded},
        "dependents_source_rows": len(dependent_rows),
        "dependents_excluded_null_rows": null_rows,
        "dependents_loaded_zero_rows": sum(row["dependents_count"] == 0 for row in loaded),
    }


def export(output: Path, packages: int = 3) -> dict:
    """Build baseline and weekly bundles, then copy Curated objects to *output*."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)
    # The runner deliberately rejects long Windows work paths.  Keep the
    # producer scratch directory close to the drive root; the exported fixture
    # itself may still live in the caller's normal build directory.
    with tempfile.TemporaryDirectory(prefix="s-", dir=Path(output.anchor)) as work:
        root = Path(work)
        fixture, baseline = make_weekly_fixture(root, population=packages)
        baseline_manifest = runner.run(baseline, fixture.s3, root / "baseline-work")
        baseline_run = baseline["run_id"]

        # Build the weekly request from the producer receipts.  This is
        # intentionally the same request builder used by the dispatcher; the
        # hand-written fixture request has versions_full refs for bootstrap.
        parent_info = _manifest_info(fixture.s3, baseline["snapshot"], baseline_run)
        parent = {"run_prefix": parent_info["prefix"],
                  "manifest_sha256": parent_info["sha256"],
                  "snapshot": parent_info["snapshot"]}
        weekly = build_request(
            fixture.s3, SNAPSHOT, "fixture-current", root / "weekly-request",
            bronze_run_id=BRONZE_RUN, download_run_id=DOWNLOAD_RUN,
            parent_bundle=parent,
            options={"workers": 1, "threads": 1, "memory_limit": "512MB",
                     "repository_engine": "duckdb"},
        )
        runner.run(weekly, fixture.s3, root / "weekly-work")

        baseline_info = _manifest_info(fixture.s3, baseline["snapshot"], baseline_run)
        weekly_info = _manifest_info(fixture.s3, SNAPSHOT, weekly["run_id"])
        expected = _expected(fixture.s3.objects,
                             {"baseline": baseline_info, "weekly": weekly_info},
                             root / "expected")
        objects = []
        object_root = output / "objects"
        for index, ((bucket, key), body) in enumerate(sorted(fixture.s3.objects.items())):
            if bucket != CURATED_BUCKET:
                continue
            # Keep the local path short on Windows.  The S3 identity remains
            # fully represented by the index entry; Java never reconstructs a
            # key from this filename.
            path = object_root / f"{index:06d}.bin"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            objects.append({"bucket": bucket, "key": key,
                            "path": str(path.relative_to(output)).replace("\\", "/"),
                            "bytes": len(body), "sha256": _sha(body)})

    metadata = {
        "format_version": 1,
        "bucket": CURATED_BUCKET,
        "baseline": baseline_info,
        "weekly": weekly_info,
        "objects": objects,
    }
    (output / "fixture.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packages", type=int, default=3)
    args = parser.parse_args(argv)
    if args.packages < 3:
        parser.error("--packages must be at least 3")
    metadata = export(args.output, args.packages)
    print(json.dumps({"output": str(args.output.resolve()),
                      "baseline": metadata["baseline"],
                      "weekly": metadata["weekly"],
                      "objects": len(metadata["objects"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
