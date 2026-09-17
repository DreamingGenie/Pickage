"""Small producer-shaped inputs for orchestration integration tests.

The fixture uses the same object contracts as the existing bronze and curated
builders.  It keeps the canonical bucket names in the request while the S3
client can map them to an isolated namespace for a real MinIO smoke run.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
from botocore.exceptions import ClientError

from pipeline.downloads import load as bronze_load
from pipeline.preprocessing.curated.storage import json_bytes


RAW_BUCKET = "pickage-raw"
CURATED_BUCKET = "pickage-curated"
# The download producer fixture covers 2026-08-28 through 2026-08-31.
# Keep the parent calendar inside that interval so the interval stage can
# exercise real rows without inventing coverage outside the source receipt.
PRIOR = "2026-08-28"
SNAPSHOT = "2026-08-31"
SNAPSHOT_TS = "2026-08-31T21:01:10Z"
BRONZE_RUN = "orchestration-fixture-raw"
PRIOR_BRONZE_RUN = "orchestration-fixture-prior-raw"
DOWNLOAD_RUN = "orchestration-fixture-downloads"



def request_fixture():
    snapshot, bronze = "2026-08-31", "raw-test"
    raw = {table: {"bucket": "pickage-raw", "key":
           f"depsdev/v1/{table}/snapshot={snapshot}/run_id={bronze}/run_manifest.json", "sha256": "a" * 64}
           for table in ("versions_full", "requirements", "projects")}
    raw["downloads"] = {"bucket": "pickage-raw", "run_id": "dl-test", "sha256": "b" * 64,
                         "key": "npm-downloads/v1/run_id=dl-test/run_manifest.json"}
    return {"format_version": 1, "run_id": "run-test", "snapshot": snapshot,
            "snapshot_timestamp": snapshot + "T21:00:00Z", "bronze_run_id": bronze,
            "raw_refs": raw, "calendar_refs": [{**raw["projects"], "snapshot": snapshot, "run_id": bronze}],
            "parent": None, "targets": {"dependents": {"bucket": "pickage-raw",
                "key": "targets/test.parquet", "sha256": "c" * 64}}, "options": {"workers": 1}}


class _Body:
    def __init__(self, value: bytes):
        self.value, self.offset = value, 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.value) - self.offset
        result = self.value[self.offset:self.offset + size]
        self.offset += len(result)
        return result

    def close(self) -> None:
        return None


class FakeS3:
    """Minimal bytes-backed S3 client shared by every pipeline stage."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    @staticmethod
    def _missing() -> ClientError:
        return ClientError({"Error": {"Code": "404"}}, "GetObject")

    @staticmethod
    def _precondition() -> ClientError:
        return ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise self._missing()
        return {"Body": _Body(body), "ETag": '"' + hashlib.md5(body).hexdigest() + '"'}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise self._missing()
        return {"ContentLength": len(body), "ETag": '"' + hashlib.md5(body).hexdigest() + '"'}

    def put_object(self, *, Bucket: str, Key: str, Body, IfNoneMatch=None, IfMatch=None, **_kwargs):
        old = self.objects.get((Bucket, Key))
        if IfNoneMatch == "*" and old is not None:
            raise self._precondition()
        if IfMatch is not None and (old is None or hashlib.md5(old).hexdigest() != IfMatch.strip('"')):
            raise self._precondition()
        body = Body if isinstance(Body, bytes) else Body.read()
        self.objects[(Bucket, Key)] = body
        return {"ETag": '"' + hashlib.md5(body).hexdigest() + '"'}

    def delete_object(self, *, Bucket: str, Key: str, IfMatch=None, **_kwargs):
        old = self.objects.get((Bucket, Key))
        if old is None:
            raise self._missing()
        if IfMatch is not None and hashlib.md5(old).hexdigest() != IfMatch.strip('"'):
            raise self._precondition()
        del self.objects[(Bucket, Key)]

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **_kwargs):
        return {"Contents": [{"Key": key} for bucket, key in sorted(self.objects)
                              if bucket == Bucket and key.startswith(Prefix)],
                "IsTruncated": False}


class BucketMapS3:
    """Map canonical request buckets to unique buckets for a real smoke run."""

    def __init__(self, client, mapping: dict[str, str]):
        self.client, self.mapping = client, dict(mapping)

    def _bucket(self, value):
        return self.mapping.get(value, value)

    def __getattr__(self, name):
        method = getattr(self.client, name)
        if name not in {"get_object", "head_object", "put_object", "delete_object", "list_objects_v2"}:
            return method

        def call(**kwargs):
            if "Bucket" in kwargs:
                kwargs["Bucket"] = self._bucket(kwargs["Bucket"])
            return method(**kwargs)

        return call


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _parquet(path: Path, schema: str, rows: list[tuple]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE fixture ({schema})")
        if rows:
            con.executemany("INSERT INTO fixture VALUES (" + ",".join("?" for _ in rows[0]) + ")", rows)
        con.execute("COPY fixture TO ? (FORMAT PARQUET)", [str(path)])
    return path.read_bytes()


def _put(s3, bucket: str, key: str, body: bytes) -> dict[str, Any]:
    s3.put_object(Bucket=bucket, Key=key, Body=body)
    return {"bucket": bucket, "key": key, "sha256": _sha(body), "bytes": len(body)}


def _seed_curated_bronze(s3, root: Path, snapshot: str, run_id: str,
                         names: tuple[str, ...] = ("alpha", "beta", "gamma")) -> dict[str, Any]:
    ts = snapshot + "T21:01:10"
    versions = [(name, "1.0.0", ts, True, 1, name, ["MIT"], None,
                 f"https://github.com/example/{name}.git", ts) for name in names]
    requirements = [(name, "1.0.0",
                     [{"Name": "beta", "Requirement": "^1"}] if name == "alpha" else [],
                     [], [], ts) for name in names]
    version_body = _parquet(root / "versions.parquet",
                            "Name VARCHAR, Version VARCHAR, published_at TIMESTAMP, is_release BOOLEAN, ordinal BIGINT, Description VARCHAR, Licenses VARCHAR[], Deprecated VARCHAR, source_repo VARCHAR, SnapshotAt TIMESTAMP",
                            versions)
    requirement_body = _parquet(root / "requirements.parquet",
                                "Name VARCHAR, Version VARCHAR, Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], PeerDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], OptionalDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], SnapshotAt TIMESTAMP",
                                requirements)
    files = []
    for table, filename, body in (("versions_full", "versions.parquet", version_body),
                                  ("requirements", "requirements.parquet", requirement_body)):
        prefix = f"depsdev/v1/{table}/snapshot={snapshot}/run_id={run_id}"
        record = {"path": filename, "key": prefix + "/data/" + filename,
                  "bytes": len(body), "sha256": _sha(body)}
        _put(s3, RAW_BUCKET, record["key"], body)
        source = {"status": "done", "verify": "ok", "snapshot": snapshot,
                    "table": table, "rows": len(names), "gcs_files": 1, "gcs_bytes": len(body)}
        source_body = json_bytes(source)
        _put(s3, RAW_BUCKET, prefix + "/source_manifest.json", source_body)
        manifest = {"contract_version": 1, "run_id": run_id, "status": "PASSED",
                    "table": table, "snapshot": snapshot, "row_count": len(names),
                    "file_count": 1, "bytes": len(body),
                    "verification": "GET_SHA256_ALL_FILES",
                    "source_manifest_sha256": _sha(source_body), "files": [record]}
        manifest_body = json_bytes(manifest)
        _put(s3, RAW_BUCKET, prefix + "/run_manifest.json", manifest_body)
        _put(s3, RAW_BUCKET, prefix + "/_SUCCESS", b"")
        files.append((table, manifest, _sha(manifest_body)))
    return {"run_id": run_id, "snapshot": snapshot, "files": files}


@dataclass
class OrchestrationFixture:
    root: Path
    s3: FakeS3
    request: dict[str, Any]
    prior_snapshot: str = PRIOR
    snapshot: str = SNAPSHOT

    def first_request(self) -> dict[str, Any]:
        """Return a bootstrap request for the first calendar snapshot."""
        bronze = _seed_curated_bronze(self.s3, self.root / "prior-raw", self.prior_snapshot,
                                      PRIOR_BRONZE_RUN, names=("alpha",))
        refs = {}
        for table, _manifest, manifest_sha in bronze["files"]:
            refs[table] = {
                "bucket": RAW_BUCKET,
                "key": f"depsdev/v1/{table}/snapshot={self.prior_snapshot}/run_id={PRIOR_BRONZE_RUN}/run_manifest.json",
                "sha256": manifest_sha,
            }
        projects_ref = self.request["calendar_refs"][0]
        first = copy.deepcopy(self.request)
        first.update({
            "run_id": "fixture-first",
            "snapshot": self.prior_snapshot,
            "snapshot_timestamp": self.prior_snapshot + "T21:01:10Z",
            "bronze_run_id": PRIOR_BRONZE_RUN,
            "parent": None,
        })
        first["raw_refs"].update({"versions_full": refs["versions_full"],
                                  "requirements": refs["requirements"],
                                  "projects": projects_ref})
        first["calendar_refs"] = [projects_ref]
        return first

    def current_request_after(self, s3=None) -> dict[str, Any]:
        """Copy the current request and bind it to the published first mapping."""
        from pipeline.preprocessing.curated.build import CURRENT

        store = self.s3 if s3 is None else s3
        if isinstance(store, FakeS3):
            pointer = json.loads(store.objects[(CURATED_BUCKET, CURRENT)].decode("utf-8"))
        else:
            pointer = json.loads(store.get_object(Bucket=CURATED_BUCKET, Key=CURRENT)["Body"].read())
        current = copy.deepcopy(self.request)
        current["parent"] = pointer
        return current

    def bootstrap_parent(self) -> dict[str, Any]:
        """Publish the prior package/version mapping used for ID continuity."""
        from pipeline.preprocessing.curated import build

        _seed_curated_bronze(self.s3, self.root / "prior-raw", self.prior_snapshot,
                              PRIOR_BRONZE_RUN, names=("alpha",))
        result = build.run(self.s3, self.prior_snapshot, PRIOR_BRONZE_RUN,
                           "orchestration-fixture-prior", self.root / "prior-work",
                           workers=1, threads=1, memory="512MB")
        pointer = json.loads(self.s3.objects[(CURATED_BUCKET, build.CURRENT)].decode("utf-8"))
        self.request["parent"] = pointer
        return result


def make_fixture(root: Path) -> OrchestrationFixture:
    """Create raw objects and a current-snapshot request for ``runner.run``."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    s3 = FakeS3()
    bronze = _seed_curated_bronze(s3, root / "raw", SNAPSHOT, BRONZE_RUN)

    # Download Bronze is produced through the real ingestion path, including
    # its manifest, marker, source checks, and immutable object layout.
    source = root / "download-source"
    from pipeline.downloads.test_support import make_source
    make_source(source)
    download_report = bronze_load.run(source, "source-1", DOWNLOAD_RUN, root / "bronze-work", s3=s3)

    projects = root / "projects"
    project_refs = []
    for day, names in ((PRIOR, ["alpha"]), (SNAPSHOT, ["alpha", "beta", "gamma"])):
        folder = projects / f"snapshot={day}"
        project_run_id = BRONZE_RUN if day == SNAPSHOT else PRIOR_BRONZE_RUN
        rows = [("GITHUB", f"example/{name}", (i + 1) * 10, i, day + "T21:01:10")
                for i, name in enumerate(names)]
        body = _parquet(folder / "part-000.parquet",
                        "Type VARCHAR, project_name VARCHAR, StarsCount BIGINT, OpenIssuesCount BIGINT, SnapshotAt TIMESTAMP", rows)
        key_prefix = f"depsdev/v1/projects/snapshot={day}/run_id={project_run_id}"
        record = {"path": "part-000.parquet", "key": key_prefix + "/data/part-000.parquet",
                  "bytes": len(body), "sha256": _sha(body)}
        source = {"status": "done", "verify": "ok", "snapshot": day,
                  "table": "projects", "rows": len(rows), "gcs_files": 1,
                  "gcs_bytes": len(body)}
        source_body = json_bytes(source)
        _put(s3, RAW_BUCKET, key_prefix + "/source_manifest.json", source_body)
        manifest = {"contract_version": 1, "run_id": project_run_id,
                    "status": "PASSED", "table": "projects", "snapshot": day,
                    "row_count": len(rows), "file_count": 1, "bytes": len(body),
                    "verification": "GET_SHA256_ALL_FILES",
                    "source_manifest_sha256": _sha(source_body), "files": [record]}
        manifest_body = json_bytes(manifest)
        key = f"depsdev/v1/projects/snapshot={day}/run_id={project_run_id}/run_manifest.json"
        _put(s3, RAW_BUCKET, key, manifest_body)
        _put(s3, RAW_BUCKET, key.rsplit("/", 1)[0] + "/data/part-000.parquet", body)
        _put(s3, RAW_BUCKET, key.rsplit("/", 1)[0] + "/_SUCCESS", b"")
        project_refs.append({"snapshot": day, "run_id": project_run_id,
                             "bucket": RAW_BUCKET, "key": key, "sha256": _sha(manifest_body)})

    target_body = _parquet(root / "targets.parquet", "name VARCHAR",
                           [("alpha",), ("beta",)])
    target_prefix = f"depsdev/v1/targets/snapshot={SNAPSHOT}/run_id={BRONZE_RUN}"
    target_key = target_prefix + "/targets.parquet"
    _put(s3, RAW_BUCKET, target_key, target_body)
    target_ref = {"bucket": RAW_BUCKET, "key": target_key, "sha256": _sha(target_body)}
    bronze_manifest_key = f"npm-downloads/v1/run_id={DOWNLOAD_RUN}/run_manifest.json"
    request = {
        "format_version": 1, "run_id": "fixture-current", "snapshot": SNAPSHOT,
        "snapshot_timestamp": SNAPSHOT_TS, "bronze_run_id": BRONZE_RUN,
        "parent": None,
        "raw_refs": {
            "versions_full": {"bucket": RAW_BUCKET, "key": f"depsdev/v1/versions_full/snapshot={SNAPSHOT}/run_id={BRONZE_RUN}/run_manifest.json", "sha256": bronze["files"][0][2]},
            "requirements": {"bucket": RAW_BUCKET, "key": f"depsdev/v1/requirements/snapshot={SNAPSHOT}/run_id={BRONZE_RUN}/run_manifest.json", "sha256": bronze["files"][1][2]},
            "projects": project_refs[-1],
            "downloads": {"bucket": RAW_BUCKET, "key": bronze_manifest_key, "sha256": download_report["manifest_sha256"], "run_id": DOWNLOAD_RUN},
        },
        "calendar_refs": project_refs,
        "targets": {"dependents": target_ref},
        "options": {"workers": 1, "threads": 1, "memory_limit": "512MB",
                     "repository_engine": "duckdb"},
    }
    return OrchestrationFixture(root, s3, request)


__all__ = ["BucketMapS3", "CURATED_BUCKET", "FakeS3", "OrchestrationFixture", "PRIOR", "RAW_BUCKET", "SNAPSHOT", "make_fixture"]
