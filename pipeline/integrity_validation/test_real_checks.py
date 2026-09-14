import copy
import unittest

from .real_checks import assess_metadata, _digest


DATES = ["2026-08-24", "2026-08-31"]
COLS = {
    "package": [("package_id", "integer", True), ("name", "character varying(300)", True), ("repo_url", "character varying(200)", False)],
    "version": [("version", "character varying(100)", True), ("package_id", "integer", True), ("published_at", "timestamp without time zone", False), ("ordinal", "bigint", True), ("description", "text", False), ("licenses", "json", False), ("deprecated", "text", False), ("dependency", "json", True)],
    "snapshot": [("snapshot_at", "date", True)],
    "package_snapshot": [("package_id", "integer", True), ("snapshot_at", "date", True), ("downloads", "bigint", False), ("stars", "integer", False), ("open_issues", "integer", False)],
    "package_version_snapshot": [("package_id", "integer", True), ("version", "character varying(100)", True), ("snapshot_at", "date", True), ("dependents_count", "integer", True)],
}
CONSTRAINTS = [
    ("package", "p", ["package_id"], None, []), ("package", "u", ["name"], None, []),
    ("version", "p", ["package_id", "version"], None, []), ("version", "f", ["package_id"], "package", ["package_id"]),
    ("snapshot", "p", ["snapshot_at"], None, []),
    ("package_snapshot", "p", ["package_id", "snapshot_at"], None, []), ("package_snapshot", "f", ["package_id"], "package", ["package_id"]), ("package_snapshot", "f", ["snapshot_at"], "snapshot", ["snapshot_at"]),
    ("package_version_snapshot", "p", ["package_id", "version", "snapshot_at"], None, []), ("package_version_snapshot", "f", ["package_id", "version"], "version", ["package_id", "version"]), ("package_version_snapshot", "f", ["snapshot_at"], "snapshot", ["snapshot_at"]),
]


def fixture():
    pv_manifest = {"population": {"manifest_sha256": "population-sha"}}
    ref_manifest = {"calendar": DATES}
    executions, attempts, receipts = [], [], []
    def add(dataset, day, manifest, counts=None):
        eid = f"{dataset}-{day}"; counts = counts or {}
        e = {"execution_id": eid, "dataset": dataset, "status": "PUBLISHED", "snapshot_at": day, "manifest_sha256": "pv-sha" if dataset == "package-version" else ("ref-sha" if dataset == "snapshot-reference" else _digest(manifest)), "input_metadata": manifest, "expected_counts": counts, "actual_counts": counts, "active_attempt_id": eid + "-a"}
        executions.append(e); attempts.append({"attempt_id": eid + "-a", "execution_id": eid, "status": "PUBLISHED"})
    add("package-version", DATES[-1], pv_manifest)
    add("snapshot-reference", None, ref_manifest)
    for i, day in enumerate(DATES):
        manifest = {"calendar": DATES, "run_manifest_sha256": "source-sha", "lineage": {"population": {"manifest_sha256": "pv-sha"}, "calendar": {"manifest_sha256": "ref-sha"}}, "quality": {"calculation_status": "COMPLETE", "resolution_status": "PARTIAL"}, "files": [{"role": "counts", "sha256": "a" * 64}]}
        add("package-snapshot", day, {"input_manifest": {"population": {"manifest_sha256": "pv-sha"}, "candidate": {"sha256": "ref-sha"}}}, {})
        add("version-dependents", day, manifest, {"package_version_snapshot": 3})
        receipts.append({"snapshot_at": day, "execution_id": f"version-dependents-{day}", "rows": 3, "input_sha": "a" * 64, "child_oid": str(10 + i), "table_contract": {"bound": f"FOR VALUES FROM ('{day}') TO ('{DATES[i + 1] if i + 1 < len(DATES) else '2026-09-01'}')"}})
    vd_latest = next(e for e in executions if e["execution_id"] == "version-dependents-2026-08-31")
    ps_manifest = {"input_manifest": {"population": {"manifest_sha256": "pv-sha"}, "candidate": {"sha256": "ref-sha"}}}
    current = [{"dataset": "package-version", "snapshot_at": DATES[-1], "execution_id": "package-version-2026-08-31", "manifest_sha256": "pv-sha", "manifest": pv_manifest}, {"dataset": "package-snapshot", "snapshot_at": DATES[-1], "execution_id": "package-snapshot-2026-08-31", "manifest_sha256": _digest(ps_manifest), "manifest": ps_manifest}, {"dataset": "version-dependents", "snapshot_at": DATES[-1], "execution_id": vd_latest["execution_id"], "manifest_sha256": vd_latest["manifest_sha256"], "manifest": vd_latest["input_metadata"]}]
    columns = [{"table_name": t, "name": n, "type": typ, "not_null": nn} for t, values in COLS.items() for n, typ, nn in values]
    constraints = [{"table_name": t, "type": typ, "columns": c, "target_schema": "public" if target else None, "target_table": target, "target_columns": tc, "validated": True} for t, typ, c, target, tc in CONSTRAINTS]
    snap = {"identity": {"database": "db", "system_identifier": "7", "read_only": "on"}, "columns": columns, "constraints": constraints, "snapshots": [{"snapshot_at": d} for d in DATES], "references": [{"dataset": "snapshot-reference", "snapshot_at": d, "execution_id": "ref", "snapshot_timestamp": f"{d}T21:00:00Z", "previous_snapshot_at": DATES[i - 1] if i else None} for i, d in enumerate(DATES)], "executions": executions, "attempts": attempts, "current": current, "partitions": [{"oid": str(10 + i), "relname": "d" + d.replace("-", ""), "boundary": f"FOR VALUES FROM ('{d}') TO ('{DATES[i + 1] if i + 1 < len(DATES) else '2026-09-01'}')"} for i, d in enumerate(DATES)], "receipts": receipts}
    return snap, {"dates": DATES, "db_identity": {"current_database": "db", "system_identifier": "7"}, "rows_by_date": {d: 3 for d in DATES}, "source_run_manifest_sha256": "source-sha"}


class RealChecksTest(unittest.TestCase):
    def test_missing_identity_is_not_a_match(self):
        snap, plan = fixture()
        snap["identity"] = {"read_only": "on"}
        plan["db_identity"] = {}
        check = next(c for c in assess_metadata(snap, plan) if c["id"] == "read_only_identity")
        self.assertEqual(check["status"], "FAIL")
    def test_realistic_baseline_passes_all_checks(self):
        self.assertTrue(all(x["status"] == "PASS" for x in assess_metadata(*fixture())))

    def test_missing_type_and_each_fk_fail(self):
        snap, plan = fixture(); snap["columns"][0].pop("type"); self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "service_columns_not_null")["status"], "FAIL")
        for i, row in enumerate(snap["constraints"]):
            if row["type"] == "f":
                bad = copy.deepcopy(snap); bad["constraints"][i]["target_table"] = "wrong"; self.assertEqual(next(x for x in assess_metadata(bad, plan) if x["id"] == "ordered_keys_and_constraints")["status"], "FAIL")

    def test_last_vd_ps_pins_and_pv_current_fail(self):
        snap, plan = fixture(); vd = [e for e in snap["executions"] if e["dataset"] == "version-dependents"][-1]; vd["input_metadata"]["lineage"]["population"]["manifest_sha256"] = "changed"; self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "cross_dataset_lineage")["status"], "FAIL")
        snap, plan = fixture(); snap["current"][0]["execution_id"] = "wrong"; self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "current_published_pointer")["status"], "FAIL")

    def test_missing_receipt_and_failed_reverify_are_reported(self):
        snap, plan = fixture(); snap["receipts"].pop(); self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "partition_receipts")["status"], "FAIL")
        snap, plan = fixture(); snap["attempts"][0]["status"] = "FAILED"; result = next(x for x in assess_metadata(snap, plan) if x["id"] == "active_attempt_association"); self.assertEqual(result["status"], "PASS"); self.assertFalse(result["evidence"]["prior_success_proven_by_association"])

    def test_ps_population_and_candidate_pins_and_fk_schema_fail(self):
        snap, plan = fixture(); ps = next(e for e in snap["executions"] if e["dataset"] == "package-snapshot"); del ps["input_metadata"]["input_manifest"]["population"]; self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "cross_dataset_lineage")["status"], "FAIL")
        snap, plan = fixture(); ps = next(e for e in snap["executions"] if e["dataset"] == "package-snapshot"); del ps["input_metadata"]["input_manifest"]["candidate"]; self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "cross_dataset_lineage")["status"], "FAIL")
        snap, plan = fixture(); fk = next(r for r in snap["constraints"] if r["type"] == "f"); fk["target_schema"] = "other"; self.assertEqual(next(x for x in assess_metadata(snap, plan) if x["id"] == "ordered_keys_and_constraints")["status"], "FAIL")
