"""Synthetic two-snapshot receipt fixture; no collector or external API calls."""
import json
from pathlib import Path
import duckdb

from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import RAW_BUCKET, BRONZE_RUN, PRIOR_BRONZE_RUN, SNAPSHOT, PRIOR, _seed_curated_bronze, _sha, _put, make_fixture


def publish_parquet(s3, path, table, snapshot, run_id):
    body = Path(path).read_bytes()
    with duckdb.connect() as con:
        rows = con.execute("SELECT count(*) FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchone()[0]
    prefix = f"depsdev/v1/{table}/snapshot={snapshot}/run_id={run_id}"
    record = {"path": "part.parquet", "key": prefix + "/data/part.parquet",
              "bytes": len(body), "sha256": _sha(body)}
    source = json_bytes({"status": "done", "verify": "ok", "snapshot": snapshot,
        "table": table, "rows": rows, "gcs_files": 1, "gcs_bytes": len(body)})
    manifest = json_bytes({"contract_version": 1, "run_id": run_id, "status": "PASSED",
        "table": table, "snapshot": snapshot, "row_count": rows, "file_count": 1,
        "bytes": len(body), "verification": "GET_SHA256_ALL_FILES",
        "source_manifest_sha256": _sha(source), "files": [record]})
    for suffix, value in (("/data/part.parquet", body), ("/source_manifest.json", source),
                          ("/run_manifest.json", manifest), ("/_SUCCESS", b"")):
        _put(s3, RAW_BUCKET, prefix + suffix, value)
    return {"bucket": RAW_BUCKET, "key": prefix + "/run_manifest.json", "sha256": _sha(manifest)}


def make_weekly_fixture(root, population=3):
    root = Path(root)
    fixture = make_fixture(root)
    first = fixture.first_request()
    extra = tuple(f"p{i:04d}" for i in range(1, population - 2))
    prior = _seed_curated_bronze(fixture.s3, root / "weekly-prior", PRIOR, PRIOR_BRONZE_RUN,
                                names=("alpha", "obsolete", *extra))
    for table, _, checksum in prior["files"]:
        first["raw_refs"][table]["sha256"] = checksum
    _seed_curated_bronze(fixture.s3, root / "weekly-current", SNAPSHOT, BRONZE_RUN,
                        names=("alpha", "beta", "gamma", *extra))
    with duckdb.connect() as con:
        con.execute("CREATE TABLE v AS SELECT * EXCLUDE(Description,Licenses,source_repo) FROM read_parquet(?)",
                    [str(root / "weekly-current" / "versions.parquet")])
        con.execute("UPDATE v SET Deprecated='weekly deprecation' WHERE Name='alpha'")
        con.execute("INSERT INTO v SELECT Name,'2.0.0',published_at,is_release,2,NULL,SnapshotAt FROM v WHERE Name='alpha' AND Version='1.0.0'")
        con.execute("INSERT INTO v SELECT Name,'3.0.0',published_at,is_release,3,NULL,SnapshotAt FROM v WHERE Name='alpha' AND Version='1.0.0'")
        path = root / "weekly-min.parquet"
        con.execute("COPY v TO ? (FORMAT PARQUET)", [str(path)])
        con.execute("CREATE TABLE r AS SELECT * FROM read_parquet(?)", [str(root / "weekly-current" / "requirements.parquet")])
        for version in ('2.0.0', '3.0.0'):
            con.execute("INSERT INTO r SELECT Name,?,Dependencies,PeerDependencies,OptionalDependencies,SnapshotAt FROM r WHERE Name='alpha' AND Version='1.0.0'", [version])
        requirements = root / "weekly-requirements.parquet"
        con.execute("COPY r TO ? (FORMAT PARQUET)", [str(requirements)])
    publish_parquet(fixture.s3, path, "versions_min", SNAPSHOT, BRONZE_RUN)
    publish_parquet(fixture.s3, requirements, "requirements", SNAPSHOT, BRONZE_RUN)
    first["options"]["repository_engine"] = "native"
    first["options"]["memory_limit"] = "1GB"
    return fixture, first
