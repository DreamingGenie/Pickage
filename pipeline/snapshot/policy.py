"""Pure, database-independent policy for deps.dev snapshot timestamps."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

POLICY_VERSION = "snapshot-time-v1"
_TIMESTAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?P<fraction>\.\d{1,6})?(?P<zone>Z|[+-]\d{2}:\d{2}| UTC)$"
)
_NAIVE_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$"
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def policy_document() -> dict:
    """Return the serializable contract used to produce policy outputs."""
    return {
        "policy_version": POLICY_VERSION,
        "timestamp": {
            "timezone": "UTC",
            "preserve_microseconds": True,
            "source_timestamps_preserved": True,
            "naive_utc_requires_explicit_adapter": True,
        },
        "calendar": {
            "source": "user-selected Projects.SnapshotAt inventory",
            "date_field": "UTC calendar date",
            "download_interval": "[previous_snapshot_at, snapshot_at)",
            "same_utc_date_conflict": "reject",
            "cadence_assumption": None,
            "null_reasons": [
                "NO_PREVIOUS_SNAPSHOT",
                "OUTSIDE_AVAILABLE_RANGE",
                "MISSING_DAILY_VALUES",
            ],
        },
        "projects": {
            "observation": "exact snapshot instant equality only",
            "historical_latest_reuse": "rejected",
            "population": "same snapshot population",
            "mismatch": {"eligible": None, "reason": "OBSERVED_SNAPSHOT_MISMATCH"},
            "not_release": {"eligible": False, "reason": "NOT_RELEASE"},
            "published_after": {"eligible": False, "reason": "PUBLISHED_AFTER_SNAPSHOT"},
            "published_unknown": {"eligible": True, "reason": "PUBLISHED_AT_UNKNOWN"},
        },
        "scope": {
            "database_readiness": False,
            "metric_calculation": False,
        },
    }


def policy_sha256() -> str:
    payload = json.dumps(
        policy_document(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_timestamp(value: str, *, allow_naive_utc: bool = False) -> datetime:
    """Parse a full timestamp and return an aware UTC datetime."""
    if not isinstance(value, str):
        raise TypeError("timestamp must be a string")
    if allow_naive_utc and _NAIVE_TIMESTAMP.fullmatch(value):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"invalid timestamp: {value!r}") from exc
    match = _TIMESTAMP.fullmatch(value)
    if not match:
        raise ValueError("timestamp must be full ISO datetime with timezone")
    fraction = match.group("fraction")
    zone = match.group("zone")
    # The regex deliberately requires a zone. This branch documents the only
    # accepted adapter escape hatch for raw BigQuery values represented as
    # naive strings by a caller.
    if zone == " UTC":
        zone = "Z"
    if zone not in {"Z"}:
        offset_hours, offset_minutes = (int(part) for part in zone[1:].split(":"))
        if offset_hours > 23 or offset_minutes > 59:
            raise ValueError(f"invalid timestamp offset: {value!r}")
    try:
        parsed = datetime.fromisoformat(
            f"{match.group('date')}T{match.group('time')}{fraction or ''}{zone}"
        )
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        if not allow_naive_utc:
            raise ValueError("naive timestamp requires allow_naive_utc=True")
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(parsed: datetime) -> str:
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_date(value: str, name: str) -> date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError(f"{name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {name}: {value!r}") from exc


def build_calendar(timestamps: Iterable[str]) -> list[dict]:
    grouped: dict[datetime, list[str]] = {}
    for source in timestamps:
        parsed = parse_timestamp(source)
        grouped.setdefault(parsed, []).append(source)
    ordered = sorted(grouped)
    by_day: dict[date, datetime] = {}
    for parsed in ordered:
        utc_day = parsed.date()
        prior = by_day.get(utc_day)
        if prior is not None and prior != parsed:
            raise ValueError(f"multiple snapshot instants on UTC date {utc_day.isoformat()}")
        by_day[utc_day] = parsed

    rows: list[dict] = []
    previous: tuple[date, datetime] | None = None
    for parsed in ordered:
        current_day = parsed.date()
        previous_day = previous[0] if previous else None
        interval_days = (current_day - previous_day).days if previous_day else None
        rows.append(
            {
                "snapshot_at": current_day.isoformat(),
                "snapshot_timestamp": _canonical_timestamp(parsed),
                "source_timestamps": grouped[parsed],
                "previous_snapshot_at": previous_day.isoformat() if previous_day else None,
                "previous_snapshot_timestamp": _canonical_timestamp(previous[1]) if previous else None,
                "download_start_inclusive": previous_day.isoformat() if previous_day else None,
                "download_end_exclusive": current_day.isoformat(),
                "interval_days": interval_days,
                "interval_reason": "NO_PREVIOUS_SNAPSHOT" if previous is None else None,
            }
        )
        previous = (current_day, parsed)
    return rows


def assess_download_coverage(
    row: dict,
    *,
    available_start: str,
    available_end: str,
    missing_dates: Iterable[str] = (),
) -> dict:
    """Assess a half-open calendar interval using caller-supplied observations."""
    if not isinstance(row, dict):
        raise ValueError("row must be a mapping")
    start = row.get("download_start_inclusive")
    end = row.get("download_end_exclusive")
    current = row.get("snapshot_at")
    previous = row.get("previous_snapshot_at")
    interval_days = row.get("interval_days")
    reason = row.get("interval_reason")
    if not isinstance(end, str) or not isinstance(current, str):
        raise ValueError("row must contain snapshot_at and download_end_exclusive")
    end_day = _parse_date(end, "download_end_exclusive")
    current_day = _parse_date(current, "snapshot_at")
    if end_day != current_day:
        raise ValueError("download_end_exclusive must equal snapshot_at")
    snapshot_timestamp = row.get("snapshot_timestamp")
    if not isinstance(snapshot_timestamp, str) or parse_timestamp(snapshot_timestamp).date() != current_day:
        raise ValueError("snapshot_timestamp must resolve to snapshot_at")
    available_first = _parse_date(available_start, "available_start")
    available_last = _parse_date(available_end, "available_end")
    if available_first > available_last:
        raise ValueError("available_start must not be after available_end")
    if start is None:
        if previous is not None or interval_days is not None or reason != "NO_PREVIOUS_SNAPSHOT":
            raise ValueError("first snapshot row has inconsistent interval fields")
        return {"eligible": False, "null_reason": "NO_PREVIOUS_SNAPSHOT", "expected_days": None, "missing_days": []}
    start_day = _parse_date(start, "download_start_inclusive")
    if previous != start:
        raise ValueError("previous_snapshot_at must equal download_start_inclusive")
    if start_day >= end_day:
        raise ValueError("download_start_inclusive must be before download_end_exclusive")
    expected_days = (end_day - start_day).days
    if interval_days != expected_days or reason is not None:
        raise ValueError("interval fields do not match calendar boundaries")
    in_range = available_first <= start_day and available_last >= end_day - timedelta(days=1)
    missing: set[str] = set()
    for value in missing_dates:
        missing_day = _parse_date(value, "missing date")
        if start_day <= missing_day < end_day:
            missing.add(missing_day.isoformat())
    if not in_range:
        reason = "OUTSIDE_AVAILABLE_RANGE"
        eligible = False
    elif missing:
        reason = "MISSING_DAILY_VALUES"
        eligible = False
    else:
        reason = None
        eligible = True
    return {
        "eligible": eligible,
        "null_reason": reason,
        "expected_days": expected_days,
        "missing_days": sorted(missing),
    }


def select_project_observation(snapshot_timestamp: str, observation_timestamps: Iterable[str]) -> dict:
    target = parse_timestamp(snapshot_timestamp)
    matches = []
    for value in observation_timestamps:
        parsed = parse_timestamp(value)
        if parsed == target:
            matches.append(parsed)
    return {
        "selected_snapshot_timestamp": _canonical_timestamp(target) if matches else None,
        "reason": None if matches else "NO_EXACT_OBSERVATION",
    }


def version_eligibility(*, snapshot_timestamp: str, observed_snapshot_timestamp: str, published_at: str | None, is_release: bool) -> dict:
    if not isinstance(is_release, bool):
        raise TypeError("is_release must be bool")
    snapshot = parse_timestamp(snapshot_timestamp)
    observed = parse_timestamp(observed_snapshot_timestamp)
    if observed != snapshot:
        return {"eligible": None, "reason": "OBSERVED_SNAPSHOT_MISMATCH"}
    if not is_release:
        return {"eligible": False, "reason": "NOT_RELEASE"}
    if published_at is None:
        return {"eligible": True, "reason": "PUBLISHED_AT_UNKNOWN"}
    if parse_timestamp(published_at) > snapshot:
        return {"eligible": False, "reason": "PUBLISHED_AFTER_SNAPSHOT"}
    return {"eligible": True, "reason": None}
