"""Compare fresh full DB aggregates with pinned, previously recorded results.

Matching aggregates are not proof of all source keys/values being identical.
NULL sums are kept distinct from numeric zero.
"""
from __future__ import annotations


def assess_rollups(scans: dict, metadata: dict, source_results: dict) -> list[dict]:
    executions = metadata["executions"]
    checks = []

    def record(name, failures, **evidence):
        checks.append({"id": name, "status": "FAIL" if failures else "PASS",
                       "evidence": {**evidence, "failure_count": len(failures),
                                    "failures": failures[:30]}})

    population = [e for e in executions if e["dataset"] == "package-version" and e["status"] == "PUBLISHED"]
    for table in ("package", "version"):
        actual = scans.get(table, {})
        expected = population[0]["actual_counts"].get(table) if len(population) == 1 else None
        failures = []
        if expected is None or actual.get("rows") != expected:
            failures.append({"field": "rows", "expected": expected, "actual": actual.get("rows")})
        if actual.get("invalid") != 0:
            failures.append({"field": "invalid", "actual": actual.get("invalid")})
        record(table + "_full_rollup", failures, rows=actual.get("rows"),
               null_published_at=actual.get("null_published_at"))

    for dataset, table in (("package-snapshot", "package_snapshot"),
                           ("version-dependents", "package_version_snapshot")):
        published = [e for e in executions if e["dataset"] == dataset and e["status"] == "PUBLISHED"]
        expected = {e["snapshot_at"]: e for e in published}
        actual_rows = scans.get(table, [])
        actual = {r["snapshot_at"]: r for r in actual_rows}
        failures = []
        if not expected or set(actual) != set(expected) or len(actual) != len(actual_rows) or len(expected) != len(published):
            failures.append({"field": "date_coverage", "expected_dates": len(expected),
                             "actual_dates": len(actual), "missing": sorted(set(expected)-set(actual)),
                             "extra": sorted(set(actual)-set(expected))})
        for day in sorted(set(actual) & set(expected)):
            row, execution = actual[day], expected[day]
            wanted = {"rows": execution["actual_counts"].get(table), "invalid": 0}
            if dataset == "version-dependents":
                quality = execution["input_metadata"].get("quality", {})
                for field, key in (("zero_rows", "zero_target_versions"),
                                   ("positive_rows", "positive_target_versions"),
                                   ("dependents_sum", "distinct_edges"),
                                   ("max_dependents", "max_dependents_count")):
                    value = quality.get(key)
                    if value is None:
                        failures.append({"date": day, "field": key, "reason": "missing quality metric"})
                    wanted[field] = str(value) if field == "dependents_sum" and value is not None else value
            else:
                source = source_results.get(day)
                if source is None:
                    failures.append({"date": day, "field": "source_result", "reason": "missing pinned validation receipt"})
                else:
                    validation = source.get("database", {}).get("validation", source.get("validation", {}))
                    if validation.get("rows") != wanted["rows"]:
                        failures.append({"date": day, "field": "receipt_rows", "actual": validation.get("rows"), "expected": wanted["rows"]})
                    for metric in ("downloads", "stars", "open_issues"):
                        for suffix, group in (("nonnull", "nonnull"), ("sum", "sums")):
                            values = validation.get(group, {})
                            if metric not in values:
                                failures.append({"date": day, "field": metric + "_" + suffix, "reason": "missing receipt metric"})
                            value = values.get(metric)
                            wanted[metric + "_" + suffix] = str(value) if suffix == "sum" and value is not None else value
            for field, value in wanted.items():
                if field not in row or row[field] != value:
                    failures.append({"date": day, "field": field, "expected": value, "actual": row.get(field)})
        record(table + "_full_rollup", failures, dates=len(actual), rows=sum(r["rows"] for r in actual_rows),
               comparison="fresh full DB aggregate versus saved producer/load evidence",
               all_source_keys_values_proven=False)
    return checks
