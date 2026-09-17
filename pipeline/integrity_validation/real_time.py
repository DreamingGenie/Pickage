"""Pure UTC and [P,S) metadata checks without timestamp precision loss."""
from datetime import date

from pipeline.preprocessing.snapshot.policy import parse_timestamp


def assess_time(metadata):
    refs = {r["snapshot_at"]: r for r in metadata["references"]}
    failures = []
    checked = 0
    for execution in metadata["executions"]:
        dataset, day = execution["dataset"], execution["snapshot_at"]
        if dataset == "snapshot-reference" or execution["status"] != "PUBLISHED":
            continue
        checked += 1
        try:
            ref = refs[day]
            instant = parse_timestamp(ref["snapshot_timestamp"])
            if instant.date().isoformat() != day:
                raise ValueError("reference date and UTC timestamp disagree")
            if parse_timestamp(execution["snapshot_timestamp"], allow_naive_utc=True) != instant:
                raise ValueError("execution timestamp differs from reference")
            manifest = execution["input_metadata"]
            if dataset == "package-snapshot":
                interval = manifest["interval"]
                previous = ref["previous_snapshot_at"]
                expected_days = (date.fromisoformat(day)-date.fromisoformat(previous)).days if previous else None
                for key, value in {"snapshot_at": day, "previous_snapshot_at": previous,
                                   "download_end_exclusive": day, "download_start_inclusive": previous,
                                   "interval_days": expected_days}.items():
                    if key not in interval or interval[key] != value:
                        raise ValueError("interval mismatch: " + key)
                if ref["interval_days"] != expected_days:
                    raise ValueError("reference interval_days mismatch")
                if parse_timestamp(manifest["snapshot_timestamp"]) != instant or parse_timestamp(interval["snapshot_timestamp"]) != instant:
                    raise ValueError("manifest timestamp differs from reference")
                previous_time = interval["previous_snapshot_timestamp"]
                if (previous is None and previous_time is not None) or (previous and parse_timestamp(previous_time) != parse_timestamp(refs[previous]["snapshot_timestamp"])):
                    raise ValueError("previous timestamp differs from reference")
            elif dataset == "version-dependents":
                if parse_timestamp(manifest["snapshot_timestamp"]) != instant or parse_timestamp(manifest["quality"]["snapshot_timestamp"]) != instant:
                    raise ValueError("VD timestamp differs from reference")
        except (ValueError, KeyError, TypeError) as error:
            failures.append({"execution_id": execution["execution_id"], "reason": str(error)})
    return {"id": "utc_and_download_interval_metadata", "status": "FAIL" if failures or not checked else "PASS",
            "evidence": {"checked_executions": checked, "failure_count": len(failures), "failures": failures[:30],
                         "scope": "metadata timestamps and [P,S) boundaries; payload temporal eligibility not scanned"}}
