"""Local Parquet verification and a small synthetic two-snapshot example."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb

from pipeline.snapshot.policy import parse_timestamp
from .artifact import save_artifact, verify_artifact


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def demo(output_root: Path) -> dict:
    """Create new fixture files and two artifacts; never use actual package data."""
    output_root = output_root.absolute()
    output_root.mkdir(parents=True, exist_ok=False)
    results = []
    policy = {"fixture": True, "dependency_kind": "dependencies", "null_published_at": "EXCLUDE"}
    policy_bytes = _json_bytes(policy)
    (output_root / "fixture-policy.json").write_bytes(policy_bytes)
    policy_hash = hashlib.sha256(policy_bytes).hexdigest()
    for snapshot in (date(2026, 8, 31), date(2026, 9, 7)):
        stamp = datetime.combine(snapshot, datetime.min.time(), tzinfo=timezone.utc).replace(hour=12)
        edges = [(1, "1.0.0", 10, "3.0.0"), (1, "2.0.0", 10, "3.0.0"),
                 (1, "2.0.0", 10, "3.0.0"), (2, "1.0.0", 10, "3.0.0")]
        if snapshot.month == 9:
            edges = edges[:1]
        published = datetime(2020, 1, 1, tzinfo=timezone.utc)
        populations = {
            "approved_sources": [(1, "1.0.0"), (1, "2.0.0"), (2, "1.0.0")],
            "approved_targets": [(10, "3.0.0"), (20, "1.0.0")],
        }
        fixture_dir = output_root / "fixtures" / snapshot.isoformat()
        fixture_dir.mkdir(parents=True)
        lineage = []
        with duckdb.connect() as con:
            con.execute("CREATE TABLE requirements_edges(source_package_id INTEGER, source_version VARCHAR, target_package_id INTEGER, target_version VARCHAR, snapshot_at DATE, snapshot_timestamp TIMESTAMPTZ)")
            con.executemany("INSERT INTO requirements_edges VALUES (?, ?, ?, ?, ?, ?)",
                            [(*edge, snapshot, stamp) for edge in edges])
            for role, rows in populations.items():
                con.execute(f"CREATE TABLE {role}(package_id INTEGER, version VARCHAR, published_at TIMESTAMPTZ, snapshot_at DATE, snapshot_timestamp TIMESTAMPTZ)")
                con.executemany(f"INSERT INTO {role} VALUES (?, ?, ?, ?, ?)",
                                [(*row, published, snapshot, stamp) for row in rows])
            for role, rows in {"requirements_edges": edges, **populations}.items():
                body = _json_bytes({"fixture": True, "role": role, "rows": rows,
                                    "snapshot_at": snapshot.isoformat(),
                                    "snapshot_timestamp": stamp.isoformat(),
                                    "population_published_at": published.isoformat(),
                                    "policy_sha256": policy_hash})
                (fixture_dir / f"{role}.json").write_bytes(body)
                lineage.append({"role": role, "run_id": "synthetic-v1",
                                "manifest_sha256": hashlib.sha256(body).hexdigest(),
                                "policy_sha256": policy_hash})
            result = save_artifact(con, output_root=output_root, run_id="synthetic-v1",
                                   expected_snapshot_at=snapshot, snapshot_timestamp=stamp,
                                   resolution_status="COMPLETE", ready_for_dependents=True,
                                   input_lineage=lineage)
        # Verify again after the input connection has been closed.
        manifest = verify_artifact(Path(result["run_dir"]), manifest_sha256=result["manifest_sha256"],
                                   expected_snapshot_at=snapshot, snapshot_timestamp=stamp)
        results.append({"snapshot_at": snapshot.isoformat(), "run_dir": result["run_dir"],
                        "manifest_sha256": result["manifest_sha256"], "quality": manifest["quality"]})
    receipt = {"synthetic_data_only": True, "ready_for_load": False, "results": results}
    (output_root / "demo-results.json").write_bytes(_json_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify local dependents Parquet files without a database")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Verify files against a pinned manifest SHA; no upstream approval")
    verify.add_argument("--run-dir", type=Path, required=True)
    verify.add_argument("--manifest-sha256", required=True)
    verify.add_argument("--snapshot-at", type=date.fromisoformat)
    verify.add_argument("--snapshot-timestamp", type=parse_timestamp)
    example = commands.add_parser("demo", help="Generate synthetic results for two snapshot dates")
    example.add_argument("--output-root", type=Path, required=True, help="New directory; existing directories are refused")
    args = parser.parse_args()
    if args.command == "demo":
        result = demo(args.output_root)
    else:
        manifest = verify_artifact(args.run_dir, manifest_sha256=args.manifest_sha256,
                                   expected_snapshot_at=args.snapshot_at,
                                   snapshot_timestamp=args.snapshot_timestamp)
        result = {"run_dir": str(args.run_dir.absolute()), "manifest_sha256": args.manifest_sha256,
                  "snapshot_at": manifest["snapshot_at"], "quality": manifest["quality"],
                  "verification_scope": manifest["verification_scope"],
                  "input_verification": manifest["input_verification"],
                  "ready_for_load": manifest["ready_for_load"]}
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
