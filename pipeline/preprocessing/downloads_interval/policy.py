"""Versioned policy for snapshot interval download aggregation."""
from __future__ import annotations

import hashlib
import json

POLICY_VERSION = "downloads-interval-v1"


def policy_document() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "interval": "[previous_snapshot_at, snapshot_at)",
        "aggregation": "sum non-null values with imputed_gap=false",
        "partial_results": "publish valid-value sum with PARTIAL status",
        "empty_results": "NULL with UNAVAILABLE status",
        "zero_values": "actual zero is valid and preserved",
        "null_reason_precedence": [
            "NO_PREVIOUS_SNAPSHOT", "OUTSIDE_TARGET_LIST", "NOT_FOUND",
            "OUTSIDE_AVAILABLE_RANGE", "MISSING_DAILY_VALUES",
        ],
        "daily_quality_reasons": [
            "ROW_MISSING", "NULL_VALUE", "IMPUTED_GAP", "OUTSIDE_AVAILABLE_RANGE",
        ],
        "grain": "(package_id, snapshot_at)",
    }


def policy_sha256() -> str:
    payload = json.dumps(policy_document(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
