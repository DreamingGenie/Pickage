"""Pure checks for the bounded PostgreSQL metadata snapshot.

This module deliberately only examines JSON already collected by ``real_db``.
It never opens a database connection, reads Parquet, or performs a write.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from pipeline.snapshot.policy import parse_timestamp
from pipeline.requirements_resolution.policy import sha256 as canonical_sha256


def _digest(value: Any) -> str:
    body = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _rows(snapshot: dict, name: str) -> list[dict]:
    value = snapshot.get(name, [])
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"snapshot[{name!r}] must be a list of objects")
    return value


def _check(check_id: str, status: str, evidence: Any) -> dict:
    return {"id": check_id, "status": status, "evidence": evidence}


def _result(check_id: str, ok: bool, evidence: Any) -> dict:
    return _check(check_id, "PASS" if ok else "FAIL", evidence)


def assess_metadata(snapshot: dict, plan: dict) -> list[dict]:
    """Assess collected metadata against the pinned reload plan.

    A detectable disagreement is represented as ``FAIL`` so callers can still
    render a complete report.  Invalid container types are programmer/input
    errors and raise ``ValueError``.
    """
    if not isinstance(snapshot, dict) or not isinstance(plan, dict):
        raise ValueError("snapshot and plan must be objects")
    dates = plan.get("dates")
    if not isinstance(dates, list) or any(not isinstance(x, str) for x in dates):
        raise ValueError("plan.dates must be a list of strings")
    expected_dates = set(dates)
    rows_by_date = plan.get("rows_by_date", {})
    if not isinstance(rows_by_date, dict):
        raise ValueError("plan.rows_by_date must be an object")
    out = []

    identity = snapshot.get("identity")
    if not isinstance(identity, dict):
        out.append(_check("read_only_identity", "FAIL", "identity metadata missing"))
    else:
        expected = plan.get("db_identity", {})
        actual_database = identity.get("database", identity.get("current_database"))
        expected_database = expected.get("current_database", expected.get("database"))
        out.append(_result("read_only_identity",
                           bool(actual_database) and bool(expected_database) and actual_database == expected_database
                           and bool(identity.get("system_identifier")) and bool(expected.get("system_identifier"))
                           and str(identity.get("system_identifier")) == str(expected.get("system_identifier"))
                           and str(identity.get("read_only")).lower() in {"on", "true", "t"},
                           {"expected": expected, "actual": {k: identity.get(k) for k in ("database", "current_database", "system_identifier", "read_only")}}))

    columns = _rows(snapshot, "columns")
    required = {
        "package": [("package_id", "integer", True), ("name", "character varying(300)", True), ("repo_url", "character varying(200)", False)],
        "version": [("version", "character varying(100)", True), ("package_id", "integer", True), ("published_at", "timestamp without time zone", False), ("ordinal", "bigint", True), ("description", "text", False), ("licenses", "json", False), ("deprecated", "text", False), ("dependency", "json", True)],
        "snapshot": [("snapshot_at", "date", True)],
        "package_snapshot": [("package_id", "integer", True), ("snapshot_at", "date", True), ("downloads", "bigint", False), ("stars", "integer", False), ("open_issues", "integer", False)],
        "package_version_snapshot": [("package_id", "integer", True), ("version", "character varying(100)", True), ("snapshot_at", "date", True), ("dependents_count", "integer", True)],
    }
    actual_cols = defaultdict(list)
    for row in columns:
        actual_cols[row.get("table_name")].append((row.get("name"), row.get("type"), row.get("not_null")))
    typed = all(actual_cols.get(table) == names for table, names in required.items())
    col_ok = typed
    null_ok = col_ok
    out.append(_result("service_columns_not_null", col_ok and null_ok,
                       {"expected_order": required, "actual_order": dict(actual_cols), "identity_not_null": null_ok}))

    constraints = _rows(snapshot, "constraints")
    grouped = defaultdict(list)
    for row in constraints:
        grouped[row.get("table_name")].append(row)
    expected_constraints = {
        "package": {("p", ("package_id",), None, ()), ("u", ("name",), None, ())},
        "version": {("p", ("package_id", "version"), None, ()), ("f", ("package_id",), "package", ("package_id",))},
        "snapshot": {("p", ("snapshot_at",), None, ())},
        "package_snapshot": {("p", ("package_id", "snapshot_at"), None, ()), ("f", ("package_id",), "package", ("package_id",)), ("f", ("snapshot_at",), "snapshot", ("snapshot_at",))},
        "package_version_snapshot": {("p", ("package_id", "version", "snapshot_at"), None, ()), ("f", ("package_id", "version"), "version", ("package_id", "version")), ("f", ("snapshot_at",), "snapshot", ("snapshot_at",))},
    }
    actual_constraints = defaultdict(set)
    for r in constraints:
        actual_constraints[r.get("table_name")].add((r.get("type"), tuple(r.get("columns") or []), r.get("target_table"), tuple(r.get("target_columns") or [])))
    pk = next((r for r in grouped.get("package_version_snapshot", []) if r.get("type") == "p"), None)
    pk_ok = all(expected_constraints[t] <= actual_constraints[t] for t in expected_constraints)
    fk_pairs = actual_constraints["package_version_snapshot"]
    validated = all(r.get("validated") is True for r in constraints if r.get("type") in {"p", "u", "f", "c"})
    fk_ok = pk_ok and all(r.get("target_schema") == "public" for r in constraints if r.get("type") == "f")
    out.append(_result("ordered_keys_and_constraints", pk_ok and fk_ok and validated,
                       {"primary_key": pk.get("columns") if pk else None, "foreign_keys": [list(x) for x in sorted(fk_pairs, key=repr)], "all_validated": validated}))

    snap_rows = _rows(snapshot, "snapshots")
    actual_snapshot_dates = {str(r.get("snapshot_at")) for r in snap_rows}
    refs = _rows(snapshot, "references")
    ref_dates = {str(r.get("snapshot_at")) for r in refs}
    calendar_ok = actual_snapshot_dates == expected_dates and ref_dates == expected_dates
    bad_timestamps, bad_predecessors = [], []
    ordered = sorted(refs, key=lambda r: str(r.get("snapshot_at")))
    for i, row in enumerate(ordered):
        try:
            parse_timestamp(row.get("snapshot_timestamp"))
        except (TypeError, ValueError):
            bad_timestamps.append(row.get("snapshot_at"))
        previous = row.get("previous_snapshot_at")
        expected_previous = ordered[i - 1].get("snapshot_at") if i else None
        if str(previous) != str(expected_previous):
            bad_predecessors.append(row.get("snapshot_at"))
    out.append(_result("calendar_and_reference_chain", calendar_ok and not bad_timestamps and not bad_predecessors,
                       {"expected_dates": len(expected_dates), "snapshot_dates": len(actual_snapshot_dates), "reference_dates": len(ref_dates), "bad_timestamps": bad_timestamps[:10], "bad_predecessors": bad_predecessors[:10]}))

    executions = _rows(snapshot, "executions")
    published = [e for e in executions if e.get("status") == "PUBLISHED"]
    by_key = Counter((e.get("dataset"), str(e.get("snapshot_at"))) for e in published)
    vd_keys = {("version-dependents", d) for d in expected_dates}
    ps_keys = {("package-snapshot", d) for d in expected_dates}
    pv = [e for e in published if e.get("dataset") == "package-version"]
    source_refs = [r for r in refs if r.get("dataset") == "snapshot-reference"]
    ref_published = [e for e in published if e.get("dataset") == "snapshot-reference"]
    one_each = len(pv) == 1 and str(pv[0].get("snapshot_at")) == max(expected_dates) and len(ref_published) == 1 and ref_published[0].get("snapshot_at") is None and len(source_refs) == len(expected_dates) and all(by_key[k] == 1 for k in vd_keys | ps_keys)
    out.append(_result("published_execution_coverage", one_each,
                       {"required": {"package_version": 1, "snapshot_reference": len(expected_dates), "package_snapshot": len(ps_keys), "version_dependents": len(vd_keys)}, "published": len(published), "duplicates": {str(k): v for k, v in by_key.items() if v != 1}}))

    count_failures = []
    for e in published:
        day = str(e.get("snapshot_at"))
        expected = rows_by_date.get(day)
        actual = e.get("actual_counts") or {}
        exp = e.get("expected_counts") or {}
        if day in expected_dates and e.get("dataset") == "version-dependents":
            target = actual.get("package_version_snapshot", actual.get("verified_rows"))
            if expected is not None and target != expected:
                count_failures.append((e.get("dataset"), day, expected, target))
        if exp and actual and any(k in exp and actual.get(k) != exp[k] for k in exp):
            count_failures.append((e.get("dataset"), day, "expected_counts", actual))
    out.append(_result("execution_counts", not count_failures, {"failures": count_failures[:20], "checked": len(published)}))

    attempts = _rows(snapshot, "attempts")
    attempt_by_exec = Counter(a.get("execution_id") for a in attempts)
    active_ok = all(e.get("active_attempt_id") and any(a.get("attempt_id") == e.get("active_attempt_id") and a.get("execution_id") == e.get("execution_id") for a in attempts) for e in published)
    failed_active = [e.get("execution_id") for e in published if any(a.get("attempt_id") == e.get("active_attempt_id") and a.get("status") == "FAILED" for a in attempts)]
    out.append(_result("active_attempt_association", active_ok, {"published_executions": len(published), "attempts": len(attempts), "duplicate_attempt_rows": [k for k, v in attempt_by_exec.items() if v > 1], "failed_active_attempts": failed_active[:20], "prior_success_proven_by_association": False}))

    currents = _rows(snapshot, "current")
    latest = max((e for e in published if e.get("dataset") == "version-dependents"),
                 key=lambda e: str(e.get("snapshot_at")), default=None)
    current_by_dataset = {c.get("dataset"): c for c in currents}
    current_ok, pointer_evidence = True, {}
    for dataset in ("package-version", "package-snapshot", "version-dependents"):
        candidates = [e for e in published if e.get("dataset") == dataset]
        expected_latest = max(candidates, key=lambda e: str(e.get("snapshot_at")), default=None)
        pointer = current_by_dataset.get(dataset)
        pointer_evidence[dataset] = bool(pointer)
        if expected_latest is None or pointer is None or any(pointer.get(k) != expected_latest.get(k) for k in ("snapshot_at", "execution_id", "manifest_sha256")) or pointer.get("manifest", pointer.get("input_metadata")) != expected_latest.get("input_metadata"):
            current_ok = False
    out.append(_result("current_published_pointer", current_ok, {"pointers_present": pointer_evidence}))

    lineage_failures = []
    for e in published:
        manifest = e.get("input_metadata")
        if not isinstance(manifest, dict):
            lineage_failures.append((e.get("execution_id"), "input_metadata is not manifest object")); continue
        # manifest_sha256 is a binding supplied by the producer.  Generic
        # JSON re-hashing is invalid because several producers hash raw bytes.
        quality = manifest.get("quality") or {}
        if e.get("dataset") == "version-dependents" and (quality.get("calculation_status") != "COMPLETE" or quality.get("resolution_status") not in {"PARTIAL", "COMPLETE"}):
            lineage_failures.append((e.get("execution_id"), "quality"))
    out.append(_result("manifest_lineage_and_quality", not lineage_failures, {"failures": lineage_failures[:20]}))

    # Compare the lineage pins carried by the three dataset families.  The
    # exact manifest layout evolved, so this intentionally inspects only the
    # stable population/calendar pins when they are present.
    calendars, populations = [], []
    for e in published:
        manifest = e.get("input_metadata")
        if not isinstance(manifest, dict):
            continue
        calendar = manifest.get("calendar")
        lineage = manifest.get("lineage") if isinstance(manifest.get("lineage"), dict) else {}
        population = lineage.get("population") if isinstance(lineage.get("population"), dict) else {}
        if calendar is not None:
            calendars.append((e.get("dataset"), calendar))
        if population:
            populations.append((e.get("dataset"), population))
    source_pin = plan.get("source_run_manifest_sha256")
    vd = [e for e in published if e.get("dataset") == "version-dependents"]
    vd_manifest = vd[-1].get("input_metadata", {}) if vd else {}
    vd_lineage = vd_manifest.get("lineage", {}) if isinstance(vd_manifest, dict) else {}
    pv_sha = pv[0].get("manifest_sha256") if pv else None
    ref_exec = next((e for e in published if e.get("dataset") == "snapshot-reference"), None)
    ref_sha = ref_exec.get("manifest_sha256") if ref_exec else None
    checks = []
    for e in vd:
        m = e.get("input_metadata") if isinstance(e.get("input_metadata"), dict) else {}
        lineage = m.get("lineage") if isinstance(m.get("lineage"), dict) else {}
        checks += [(f"{e.get('execution_id')} population -> PV", (lineage.get("population") or {}).get("manifest_sha256"), pv_sha),
                   (f"{e.get('execution_id')} calendar -> snapshot-reference", (lineage.get("calendar") or {}).get("manifest_sha256"), ref_sha),
                   (f"{e.get('execution_id')} run manifest -> plan", m.get("run_manifest_sha256"), source_pin),
                   (f"{e.get('execution_id')} canonical manifest", e.get("manifest_sha256"), canonical_sha256(m))]
    for e in published:
        if e.get("dataset") == "package-snapshot" and isinstance(e.get("input_metadata"), dict):
            pop = ((e["input_metadata"].get("input_manifest") or {}).get("population") or {}).get("manifest_sha256")
            checks.append((f"{e.get('execution_id')} PS population -> PV", pop, pv_sha))
            candidate_pin = ((e["input_metadata"].get("input_manifest") or {}).get("candidate") or {}).get("sha256")
            checks.append((f"{e.get('execution_id')} PS candidate -> reference", candidate_pin, ref_sha))
    lineage_mismatches = [label for label, actual, expected in checks if actual is None or expected is None or actual != expected]
    out.append(_result("cross_dataset_lineage", not lineage_mismatches,
                       {"mismatches": lineage_mismatches[:20], "pins_checked": len(checks)}))

    receipts = _rows(snapshot, "receipts")
    partitions = _rows(snapshot, "partitions")
    partition_by_name = {p.get("relname"): p for p in partitions}
    receipt_failures = []
    for r in receipts:
        day = str(r.get("snapshot_at")); match = next((e for e in published if e.get("dataset") == "version-dependents" and str(e.get("snapshot_at")) == day and e.get("execution_id") == r.get("execution_id")), None)
        pname = "d" + day.replace("-", "")
        part = partition_by_name.get(pname)
        if day not in expected_dates or r.get("rows") != rows_by_date.get(day) or match is None or part is None or str(r.get("child_oid")) != str(part.get("oid")) or (r.get("table_contract") or {}).get("bound") != part.get("boundary"):
            receipt_failures.append((day, "date/rows/execution")); continue
        if r.get("input_sha") and isinstance(match.get("input_metadata"), dict):
            files = match["input_metadata"].get("files", [])
            counts_file = next((f for f in files if f.get("role") == "counts"), None)
            if counts_file and counts_file.get("sha256") != r.get("input_sha"):
                receipt_failures.append((day, "counts sha"))
    out.append(_result("partition_receipts", not receipt_failures and len(receipts) == len(expected_dates), {"receipts": len(receipts), "expected": len(expected_dates), "failures": receipt_failures[:20]}))
    return out


__all__ = ["assess_metadata"]
