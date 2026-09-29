"""Prepare a Projects-derived calendar and explicit snapshot-date SQL locally.

This command does not connect to PostgreSQL or publish dataset readiness.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from pipeline.preprocessing.snapshot.policy import build_calendar, policy_document, policy_sha256, POLICY_VERSION
from pipeline.preprocessing.snapshot.projects import inspect_projects


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def snapshot_sql(calendar: list[dict]) -> str:
    """Idempotent date insertion only; dates are parsed, never interpolated raw."""
    if not calendar:
        raise ValueError("Snapshot calendar must not be empty")
    dates = [date.fromisoformat(row["snapshot_at"]).isoformat() for row in calendar]
    if len(dates) != len(set(dates)) or dates != sorted(dates):
        raise ValueError("Snapshot dates must be sorted and unique")
    values = ",\n".join(f"    (DATE '{value}')" for value in dates)
    return (
        "-- Projects-derived reference dates only. This does not publish metric readiness.\n"
        "-- Generated from snapshot-candidate.json; preserve that file as provenance.\n"
        "BEGIN;\n"
        'INSERT INTO public."snapshot" (snapshot_at)\nVALUES\n'
        + values
        + "\nON CONFLICT (snapshot_at) DO NOTHING;\nCOMMIT;\n"
    )


def prepare(projects_root: Path, output_dir: Path) -> dict:
    """Validate before creating an exclusive output directory. Never overwrite runs."""
    if output_dir.exists():
        raise ValueError(f"Output directory already exists: {output_dir}")
    source = inspect_projects(projects_root)
    calendar = build_calendar(source["timestamps"])
    sql = snapshot_sql(calendar).encode("utf-8")
    source_body = json_bytes(source)
    candidate = {
        "format_version": 1,
        "dataset": "snapshot-reference",
        "status": "LOCAL_VALIDATED",
        "db_published": False,
        "service_ready": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": POLICY_VERSION,
        "policy_sha256": policy_sha256(),
        "policy": policy_document(),
        "source": {
            "kind": "local-projects",
            "root": str(projects_root.resolve()),
            "inventory_file": "projects-inventory.json",
            "inventory_sha256": hashlib.sha256(source_body).hexdigest(),
            "calendar_scope": "all snapshots present in the selected Projects directory",
            "predecessor_scope": "previous member of this frozen Projects calendar",
            "validation": source["validation"],
        },
        "snapshot_count": len(calendar),
        "first_snapshot_at": calendar[0]["snapshot_at"],
        "last_snapshot_at": calendar[-1]["snapshot_at"],
        "calendar": calendar,
        "files": [
            {"path": "projects-inventory.json", "sha256": hashlib.sha256(source_body).hexdigest()},
            {"path": "snapshot-dates.sql", "sha256": hashlib.sha256(sql).hexdigest()},
        ],
        "limitations": [
            "Projects inventory is the user-selected calendar, not a claim of all deps.dev history.",
            "Parquet footer checks do not validate all metric values or full-file checksums.",
            "No PostgreSQL execution history or service readiness was published.",
            "Historical package/version populations require matching-snapshot source data.",
            "The first listed snapshot has no previous member of this input calendar.",
        ],
    }
    # Candidate is written last: an interrupted output lacks its completion report.
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "projects-inventory.json").write_bytes(source_body)
    (output_dir / "snapshot-dates.sql").write_bytes(sql)
    (output_dir / "snapshot-candidate.json").write_bytes(json_bytes(candidate))
    return {
        "status": candidate["status"], "snapshot_count": len(calendar),
        "first_snapshot_at": candidate["first_snapshot_at"],
        "last_snapshot_at": candidate["last_snapshot_at"],
        "source_file_count": source["file_count"],
        "source_rows": source["total_rows"], "policy_sha256": candidate["policy_sha256"],
        "output_dir": str(output_dir.resolve()), "db_published": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.projects_root, args.output_dir)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"snapshot build failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
