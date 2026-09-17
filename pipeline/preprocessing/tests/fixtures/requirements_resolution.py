"""Tiny end-to-end input fixtures matching the approved local/remote contracts."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile

import duckdb

from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.postgresql import input as loader
from pipeline.postgresql.test_input import FakeS3 as BaseFakeS3
from botocore.exceptions import ClientError

SNAPSHOT = "2026-08-31"
CURATED_RUN = "curated-test"
BRONZE_RUN = "bronze-test"
STAMP = "2026-08-31T21:01:10.123456"


class FakeS3(BaseFakeS3):
    def put_object(self, Bucket, Key, Body, **kwargs):
        if kwargs.get("IfNoneMatch") == "*" and (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        if hasattr(Body, "read"):
            Body = Body.read()
        return super().put_object(Bucket=Bucket, Key=Key, Body=Body, **kwargs)


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _write(path: Path, table: str, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas = {
        "package": "package_id INTEGER, name VARCHAR, repo_url VARCHAR",
        "version": "version VARCHAR, package_id INTEGER, published_at TIMESTAMP, ordinal BIGINT, description VARCHAR, licenses JSON, deprecated VARCHAR, dependency JSON",
        "versions_full": "SnapshotAt TIMESTAMP, Name VARCHAR, Version VARCHAR, is_release BOOLEAN, ordinal BIGINT, published_at TIMESTAMP, Deprecated VARCHAR, dependency_error BOOLEAN, Description VARCHAR, Licenses VARCHAR[], source_repo VARCHAR",
        "requirements": 'SnapshotAt TIMESTAMP, Name VARCHAR, Version VARCHAR, Dependencies STRUCT("Name" VARCHAR, Requirement VARCHAR)[], PeerDependencies STRUCT("Name" VARCHAR, Requirement VARCHAR)[], OptionalDependencies STRUCT("Name" VARCHAR, Requirement VARCHAR)[]',
    }
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE t ({schemas[table]})")
        for row in rows:
            if table == "package":
                con.execute("INSERT INTO t VALUES (?, ?, ?)", [row["package_id"], row["name"], row.get("repo_url")])
            elif table == "version":
                con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [row["version"], row["package_id"], row.get("published_at"), row.get("ordinal", 0), row.get("description"), row.get("licenses", "[]"), row.get("deprecated"), row.get("dependency", "{}")])
            elif table == "versions_full":
                con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [row["SnapshotAt"], row["Name"], row["Version"], row["is_release"], row.get("ordinal", 0), row.get("published_at"), row.get("Deprecated"), row.get("dependency_error"), row.get("Description"), row.get("Licenses", []), row.get("source_repo")])
            else:
                con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", [row["SnapshotAt"], row["Name"], row["Version"], row.get("Dependencies"), row.get("PeerDependencies"), row.get("OptionalDependencies")])
        con.execute("COPY t TO ? (FORMAT PARQUET)", [str(path)])


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s3 = FakeS3()
        self.curated = self.root / "curated"
        self.versions = self.root / "versions_full"
        self.requirements = self.root / "requirements"
        package = self.curated / "package/data/part-000.parquet"
        version = self.curated / "version/data/part-000.parquet"
        _write(package, "package", [{"package_id": 1, "name": "a", "repo_url": "https://example.invalid/a"}])
        _write(version, "version", [{"version": "1.0.0", "package_id": 1, "published_at": "2026-08-30 01:02:03.123456", "licenses": "[]", "dependency": "{}"}])
        self.raw_rows = {
            "versions_full": [{"SnapshotAt": "2026-08-31 21:01:10.123456", "Name": "a", "Version": "1.0.0", "is_release": True, "published_at": "2026-08-30 01:02:03.123456", "dependency_error": False, "Licenses": []}],
            "requirements": [{"SnapshotAt": "2026-08-31 21:01:10.123456", "Name": "a", "Version": "1.0.0", "Dependencies": [], "PeerDependencies": [], "OptionalDependencies": []}],
        }
        self._refresh_raw("versions_full")
        self._refresh_raw("requirements")
        self._publish_curated(package, version)

    def _refresh_raw(self, table):
        folder = self.versions if table == "versions_full" else self.requirements
        path = folder / "part-000.parquet"
        _write(path, table, self.raw_rows[table])
        body = path.read_bytes()
        summary = {"status": "done", "verify": "ok", "snapshot": SNAPSHOT, "table": table, "rows": len(self.raw_rows[table]), "gcs_files": 1, "gcs_bytes": len(body)}
        marker = folder / "_MANIFEST.json"
        marker.write_bytes(json_bytes(summary))
        prefix = f"depsdev/v1/{table}/snapshot={SNAPSHOT}/run_id={BRONZE_RUN}"
        record = {"key": prefix + "/data/part-000.parquet", "bytes": len(body), "sha256": sha(body)}
        self.s3.put_object(Bucket="pickage-raw", Key=record["key"], Body=body)
        self.s3.put_object(Bucket="pickage-raw", Key=prefix + "/source_manifest.json", Body=marker.read_bytes())
        run = {"contract_version": 1, "run_id": BRONZE_RUN, "status": "PASSED", "table": table, "snapshot": SNAPSHOT, "row_count": len(self.raw_rows[table]), "file_count": 1, "bytes": len(body), "verification": "GET_SHA256_ALL_FILES", "source_manifest_sha256": sha(marker.read_bytes()), "files": [record]}
        self.s3.put_object(Bucket="pickage-raw", Key=prefix + "/run_manifest.json", Body=json_bytes(run))
        self.s3.put_object(Bucket="pickage-raw", Key=prefix + "/_SUCCESS", Body=b"")

    def _publish_curated(self, package, version):
        prefix = f"{loader.PREFIX}/snapshot={SNAPSHOT}/run_id={CURATED_RUN}"
        files = []
        for table, path in (("package", package), ("version", version)):
            key = prefix + "/attempts/attempt-1/" + table + "/data/part-000.parquet"
            body = path.read_bytes()
            self.s3.put_object(Bucket=loader.CURATED_BUCKET, Key=key, Body=body)
            files.append({"key": key, "bytes": len(body), "sha256": sha(body)})
        aux = prefix + "/attempts/attempt-1/quality/metadata.parquet"
        self.s3.put_object(Bucket=loader.CURATED_BUCKET, Key=aux, Body=b"quality")
        files.append({"key": aux, "bytes": 7, "sha256": sha(b"quality")})
        sources = {}
        for table in ("requirements", "versions_full"):
            key = f"depsdev/v1/{table}/snapshot={SNAPSHOT}/run_id={BRONZE_RUN}/run_manifest.json"
            body = self.s3.objects[("pickage-raw", key)][0]
            sources[table] = {"key": key, "sha256": sha(body)}
        request = {"contract_version": 1, "snapshot": SNAPSHOT, "bronze_run_id": BRONZE_RUN, "run_id": CURATED_RUN, "sources": sources}
        manifest = {"contract_version": 1, "status": "PASSED", "verification": "GET_SHA256_ALL_FILES", "request": request, "report": {"snapshot_timestamp": STAMP, "output_counts": {"package/data": 1, "version/data": 1}, "packages": 1, "versions": 1}, "files": files}
        body = json_bytes(manifest)
        self.s3.put_object(Bucket=loader.CURATED_BUCKET, Key=prefix + "/run_manifest.json", Body=body)
        self.s3.put_object(Bucket=loader.CURATED_BUCKET, Key=prefix + "/_SUCCESS", Body=json_bytes({"manifest_sha256": sha(body)}))

    def arguments(self, output=None):
        return {"snapshot": SNAPSHOT, "curated_run_id": CURATED_RUN, "curated_outputs": self.curated, "versions_dir": self.versions, "requirements_dir": self.requirements, "output": output}

    def close(self):
        self.temp.cleanup()
