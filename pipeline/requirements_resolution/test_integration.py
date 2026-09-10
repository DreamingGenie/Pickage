"""Explicit integration check: real Spark/Node with synthetic data and in-memory S3."""
import argparse
import json
from pathlib import Path
import uuid

import duckdb

from .build import run, BUCKET, PREFIX, _io_path
from .policy import make_policy, canonical_bytes
from .test_support import Fixture, SNAPSHOT


def verify(work_dir):
    fixture = Fixture()
    try:
        fixture.raw_rows["requirements"][0]["Dependencies"] = [{"Name": "a", "Requirement": "^1"}]
        fixture.raw_rows["requirements"][0]["PeerDependencies"] = [{"Name": "peer", "Requirement": "latest"}]
        fixture._refresh_raw("requirements")
        fixture._publish_curated(fixture.curated / "package/data/part-000.parquet",
                                 fixture.curated / "version/data/part-000.parquet")
        fixture.s3.delete_object = lambda Bucket, Key, IfMatch=None: fixture.s3.objects.pop((Bucket, Key), None)
        args = fixture.arguments()
        args.pop("output")
        run_id = "integration-" + uuid.uuid4().hex[:8]
        args.update(run_id=run_id, work_dir=Path(work_dir).resolve(), threads=2, shuffle_partitions=2,
                    policy=make_policy(kinds=["dependencies"], unknown_published_at="include", unresolved="partial",
                                       decision_reference="SYNTHETIC INTEGRATION FIXTURE ONLY; no production policy approval"))
        manifest = run(fixture.s3, **args)
        root = args["work_dir"] / run_id
        outputs = root / manifest["final_output"]
        assert manifest["finalize_report"]["output_counts"] == {
            "declaration_outcomes": 1, "source_outcomes": 1, "edges": 1, "target_quality": 0}
        with duckdb.connect() as con:
            edge = con.execute("SELECT source_package_id,source_version,target_package_id,target_version "
                               "FROM read_parquet(?)", [[str(_io_path(p)) for p in (outputs / "edges").glob("*.parquet")]]).fetchall()
            assert edge == [(1, "1.0.0", 1, "1.0.0")], edge
            peers = con.execute("SELECT excluded_peer_count FROM read_parquet(?)",
                                [[str(_io_path(p)) for p in (outputs / "source_outcomes").glob("*.parquet")]]).fetchall()
            assert peers == [(1,)], peers
        body = (root / "run_manifest.json").read_bytes()
        assert run(fixture.s3, **args, verify_only=True)["reverified"] is True
        # Simulate the two marker-last crash windows, retaining verified data.
        (root / "_SUCCESS").unlink()
        assert run(fixture.s3, **args)["reverified"] is True
        assert (root / "_SUCCESS").is_file()
        assert run(fixture.s3, **args, publish=True)["reverified"] is True
        key = f"{PREFIX}/snapshot={SNAPSHOT}/run_id={run_id}/_SUCCESS"
        fixture.s3.objects.pop((BUCKET, key))
        assert run(fixture.s3, **args, publish=True)["reverified"] is True
        assert (BUCKET, key) in fixture.s3.objects
        assert body == (root / "run_manifest.json").read_bytes()
        result = {"status": "PASSED", "run_id": run_id, "synthetic_inputs": True,
                  "actual_spark_and_node": True, "s3": "in_memory_test_double_no_external_writes",
                  "input_fixtures_removed_after_test": True, "output_counts": manifest["finalize_report"]["output_counts"],
                  "replay": "verified_without_recomputation", "local_and_remote_marker_recovery": "passed"}
        (root / "verification.json").write_bytes(canonical_bytes(result))
        print(json.dumps(result), flush=True)
        return result
    finally:
        fixture.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    verify(parser.parse_args().work_dir)
