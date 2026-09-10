"""Sequential read-only verification of completed 07 data, with bounded JSON output."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid
import duckdb
from pipeline.requirements_resolution.build import _io_path, _safe_output, _verify_inventory, _verify_stage_counts, _verify_manifest_status
from pipeline.requirements_resolution.policy import canonical_bytes, validate_policy

GROUPS = ("declaration_outcomes", "source_outcomes", "edges", "target_quality")
LINEAGE = ("snapshot_at", "snapshot_timestamp", "run_id", "input_sha256", "curated_run_id", "bronze_run_id", "policy_sha256")

def literal(value):
    return "'" + str(value).replace("'", "''") + "'"

def view(con, name, paths):
    array = "[" + ",".join(literal(_io_path(Path(p))) for p in paths) + "]"
    con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({array},hive_partitioning=false)")

def verify(manifest_path, report_path, *, allow_test_policy=False, candidate_manifest=False):
    started = time.monotonic()
    manifest_path, report_path = Path(manifest_path).resolve(), Path(report_path).resolve()
    body = _io_path(manifest_path).read_bytes()
    manifest = json.loads(body)
    root = manifest_path.parent
    if candidate_manifest:
        if manifest.get("status") != "RECOVERY_CANDIDATE":
            raise ValueError("Recovery validation requires an explicit candidate manifest")
        declared_gaps = manifest.get("recovery", {}).get("gaps")
        if (not isinstance(declared_gaps, list) or not declared_gaps
                or any(not isinstance(gap, str) or not gap.strip() for gap in declared_gaps)):
            raise ValueError("Recovery candidate must declare provenance gaps")
    else:
        if json.loads((root / "_SUCCESS").read_bytes()) != {"manifest_sha256": hashlib.sha256(body).hexdigest()}:
            raise ValueError("Completion marker SHA mismatch")
        if manifest.get("status") != "PASSED":
            raise ValueError("Run did not pass its calculation checks")
    doc = validate_policy(manifest["policy"])
    if (doc["kinds"] != ["dependencies"] or doc["unknown_published_at"] != "exclude"
            or doc["unresolved"] != "partial") and not allow_test_policy:
        raise ValueError("Expected the approved dependencies/exclude/partial policy")
    final_root = _safe_output(root, manifest["final_output"])
    inputs = manifest["input"]
    for source in [final_root, *(Path(p).resolve() for p in inputs["sources"].values())]:
        if report_path.is_relative_to(source) or source.is_relative_to(report_path):
            raise ValueError("Verification output overlaps calculation/input data")
    if report_path.exists():
        raise ValueError("Report already exists")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _verify_inventory(final_root, manifest["files"])
    _verify_stage_counts(final_root, manifest["finalize_report"])
    _verify_manifest_status(manifest)
    paths = {g: [str(final_root / r["path"]) for r in manifest["files"] if r["path"].split("/")[0] == g] for g in GROUPS}
    checks = [{"name": "candidate_policy_inventory_and_group_counts" if candidate_manifest
               else "marker_policy_inventory_and_group_counts", "passed": True}]
    gaps = list(manifest["recovery"]["gaps"]) if candidate_manifest else []
    metrics, examples = {}, {}
    scratch = report_path.parent / ("scratch-" + uuid.uuid4().hex[:8])
    scratch.mkdir()
    with duckdb.connect(config={"threads": 1, "memory_limit": "2GB"}) as con:
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET TimeZone='UTC'")
        con.execute("SET temp_directory=?", [str(_io_path(scratch))])
        for name, group in (("decl", GROUPS[0]), ("src", GROUPS[1]), ("edge", GROUPS[2]), ("tq", GROUPS[3])):
            view(con, name, paths[group])
        con.execute("CREATE TABLE params AS SELECT CAST(? AS TIMESTAMPTZ)::TIMESTAMP AS t", [inputs["snapshot_timestamp"]])
        def zero(name, query, parameters=None):
            count = int(con.execute(query, parameters or []).fetchone()[0])
            checks.append({"name": name, "passed": count == 0, "violations": count, "query": query})
            print(json.dumps({"check": name, "violations": count}), flush=True)
        def equal(name, actual, expected):
            checks.append({"name": name, "passed": actual == expected, "actual": actual, "expected": expected})

        source = con.execute("""
          SELECT count(*),count(*) FILTER(WHERE published_at IS NULL),
                 count(*) FILTER(WHERE published_at>t),sum(declaration_count),sum(resolved_count),
                 sum(unresolved_count),sum(excluded_peer_count),sum(excluded_optional_count)
          FROM src,params""").fetchone()
        metrics.update(source_versions=source[0], source_null_dates=source[1], source_future_dates=source[2],
                       selected_declarations=source[3] or 0, resolved_declarations=source[4] or 0,
                       unresolved_declarations=source[5] or 0, excluded_peer_declarations=source[6] or 0,
                       excluded_optional_declarations=source[7] or 0)
        if doc["unknown_published_at"] == "exclude":
            equal("no_source_null_dates", source[1], 0)
            zero("no_unknown_source_publication_flag", "SELECT count(*) FROM src WHERE published_at_unknown IS DISTINCT FROM false")
        equal("no_future_source_dates", source[2], 0)
        zero("source_count_arithmetic", """SELECT count(*) FROM src WHERE declaration_count IS NULL
          OR resolved_count IS NULL OR unresolved_count IS NULL
          OR observed_declaration_count IS DISTINCT FROM declaration_count
          OR resolved_count+unresolved_count<>declaration_count OR least(resolved_count,unresolved_count)<0""")
        declaration_groups = con.execute("""SELECT status,count(*),first(example),last(example) FROM (
          SELECT status,struct_pack(source_package_id:=source_package_id,source_version:=source_version,
            declared_name:=declared_name,requirement:=left(requirement,500),target_package_id:=target_package_id,
            target_version:=target_version,status:=status) AS example FROM decl) GROUP BY status""").fetchall()
        metrics["declaration_status_counts"] = {status: count for status, count, _, _ in declaration_groups}
        for status, _, first, last in declaration_groups:
            examples[status] = [first] if first == last else [first, last]
        metrics["source_status_counts"] = dict(con.execute("SELECT status,count(*) FROM src GROUP BY status").fetchall())
        metrics["target_quality_reason_counts"] = dict(con.execute("SELECT reason,count(*) FROM tq GROUP BY reason").fetchall())
        report = manifest["finalize_report"]
        equal("declaration_statuses_match_manifest", metrics["declaration_status_counts"], report["declaration_status_counts"])
        equal("source_statuses_match_manifest", metrics["source_status_counts"], report["source_status_counts"])
        equal("declaration_total", sum(metrics["declaration_status_counts"].values()), metrics["selected_declarations"])
        equal("resolved_total", metrics["declaration_status_counts"].get("RESOLVED", 0), metrics["resolved_declarations"])
        zero("selected_kind_and_resolution_fields", """SELECT count(*) FROM decl WHERE kind IS DISTINCT FROM 'dependencies'
          OR status IS NULL OR source_package_id IS NULL OR source_version IS NULL
          OR (status='RESOLVED') IS DISTINCT FROM (target_package_id IS NOT NULL AND target_version IS NOT NULL)""")
        zero("declaration_source_fk", """SELECT count(*) FROM decl d ANTI JOIN src s
          ON d.source_package_id=s.source_package_id AND d.source_version=s.source_version""")
        zero("declaration_unique_key", """SELECT count(*) FROM (SELECT source_package_id,source_version,
          kind,declaration_index FROM decl GROUP BY ALL HAVING count(*)>1)""")
        zero("edge_key_and_kind", """SELECT count(*) FROM edge WHERE source_package_id IS NULL OR source_version IS NULL
          OR target_package_id IS NULL OR target_version IS NULL OR declaration_count IS NULL OR declaration_count<=0
          OR dependency_kinds IS DISTINCT FROM ['dependencies']""")
        zero("edge_unique_key", """SELECT count(*) FROM (SELECT snapshot_at,source_package_id,source_version,
          target_package_id,target_version FROM edge GROUP BY ALL HAVING count(*)>1)""")
        edges = con.execute("SELECT count(*),coalesce(sum(declaration_count),0) FROM edge").fetchone()
        metrics["edge_rows"] = edges[0]
        equal("edge_declarations_equal_resolved", edges[1], metrics["resolved_declarations"])
        zero("edge_resolved_declaration_equivalence", """WITH expected AS (
          SELECT source_package_id,source_version,target_package_id,target_version,count(*) AS n
          FROM decl WHERE status='RESOLVED' GROUP BY ALL)
          SELECT count(*) FROM expected d FULL OUTER JOIN edge e
          ON d.source_package_id=e.source_package_id AND d.source_version=e.source_version
          AND d.target_package_id=e.target_package_id AND d.target_version=e.target_version
          WHERE d.n IS DISTINCT FROM e.declaration_count""")

        available = all(_io_path(Path(p)).is_file() for p in inputs["files"]["version"])
        if available:
            view(con, "ver", inputs["files"]["version"])
            population = con.execute("""SELECT count(*),count(*) FILTER(WHERE published_at IS NULL),
              count(*) FILTER(WHERE published_at>t),count(*) FILTER(WHERE published_at IS NOT NULL AND published_at<=t)
              FROM ver,params""").fetchone()
            metrics.update(curated_versions=population[0], excluded_null_publication_versions=population[1],
                           excluded_future_publication_versions=population[2], known_eligible_versions=population[3])
            where = "published_at IS NOT NULL AND published_at<=t" if doc["unknown_published_at"] == "exclude" else "published_at IS NULL OR published_at<=t"
            con.execute("CREATE VIEW eligible AS SELECT package_id,version FROM ver,params WHERE " + where)
            eligible_count = population[3] + (population[1] if doc["unknown_published_at"] == "include" else 0)
            equal("eligible_population_size", metrics["source_versions"], eligible_count)
            zero("source_eligible_fk", """SELECT count(*) FROM src s ANTI JOIN eligible v
              ON s.source_package_id=v.package_id AND s.source_version=v.version""")
            zero("source_unique_key", """SELECT count(*) FROM (SELECT source_package_id,source_version FROM src GROUP BY ALL HAVING count(*)>1)""")
            zero("resolved_target_eligible_fk", """SELECT count(*) FROM (SELECT * FROM decl WHERE status='RESOLVED') d
              ANTI JOIN eligible v ON d.target_package_id=v.package_id AND d.target_version=v.version""")
        elif allow_test_policy:
            gaps.append("Synthetic run input fixture has been removed; eligible-population and target-date FK checks not run")
        else:
            raise ValueError("Approved version input files missing")

        values = [inputs["snapshot"], inputs["snapshot_timestamp"], manifest["request"]["run_id"], inputs["input_sha256"],
                  inputs["curated_run_id"], inputs["bronze_run_id"], manifest["policy"]["sha256"]]
        conditions = ["snapshot_at IS DISTINCT FROM CAST(? AS DATE)", "snapshot_timestamp IS DISTINCT FROM CAST(? AS TIMESTAMPTZ)::TIMESTAMP"]
        conditions += [field + " IS DISTINCT FROM ?" for field in LINEAGE[2:]]
        for name in ("decl", "src", "edge", "tq"):
            zero(name + "_lineage", "SELECT count(*) FROM " + name + " WHERE " + " OR ".join(conditions), values)

    # Scratch is intentionally kept for reproducible failure inspection; no data is deleted.
    failed = [c["name"] for c in checks if not c["passed"]]
    result = {"status": "FAILED" if failed else "VERIFIED_WITH_GAPS" if gaps else "PASSED",
              "data_checks_passed": not failed, "candidate_manifest": candidate_manifest,
              "resolution_status": manifest["resolution_status"], "ready_for_dependents": manifest["ready_for_dependents"],
              "policy_sha256": manifest["policy"]["sha256"], "manifest_sha256": hashlib.sha256(body).hexdigest(),
              "runtime_metadata": manifest["runtime_metadata"], "input_counts": inputs["counts"], "metrics": metrics,
              "output_files": len(manifest["files"]), "output_bytes": sum(r["bytes"] for r in manifest["files"]),
              "checks": checks, "gaps": gaps, "examples": examples, "elapsed_seconds": round(time.monotonic()-started,3),
              "scope": "observed declared direct edges; no dependents_count or PostgreSQL load"}
    with report_path.open("xb") as stream:
        stream.write(canonical_bytes(result))
    print(json.dumps({"verification_status": result["status"], "failed": failed, "gaps": gaps, "report": str(report_path)}), flush=True)
    if failed:
        raise ValueError("Verification found violations: " + ",".join(failed))
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-test-policy", action="store_true")
    parser.add_argument("--candidate-manifest", action="store_true",
                        help="Validate an unsealed RECOVERY_CANDIDATE; never creates a completion marker")
    args = parser.parse_args()
    verify(args.manifest, args.output, allow_test_policy=args.allow_test_policy,
           candidate_manifest=args.candidate_manifest)
