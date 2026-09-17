"""Explicitly approved reconstruction policy, separate from observed snapshot v1."""
from __future__ import annotations

import hashlib
from pipeline.preprocessing.package_snapshot.policy import canonical_bytes


def policy_document():
    return {
        'policy_version': 'package-snapshot-history-v1',
        'approval': 'User approved publication-date-based reconstruction on 2026-09-09',
        'history_kind': 'RECONSTRUCTED_FROM_CURRENT_APPROVED_VERSIONS',
        'population': 'At least one approved release with known published_at <= exact target timestamp',
        'unknown_publication': 'Exclude from historical eligibility; preserve excluded counts and source references',
        'repository': 'Valid repository of eligible version ordered ordinal DESC, published_at DESC, version ASC',
        'repository_comparison': {'github.com': 'lowercase', 'gitlab.com': 'exact'},
        'observation': 'Projects SnapshotAt equals exact target timestamp; never carry observations across dates',
        'conflicts': 'Conflicting metric pairs yield NULL metrics and a quality reason',
        'downloads': 'Actual UTC [previous snapshot date, target snapshot date) valid-value sum; publish partial sums',
        'unavailable': 'NULL with reason; actual zero remains zero',
        'existing_snapshot': 'Preserve independently verified previously published observed snapshots',
        'limitations': ['Current approved universe omits packages absent from the base snapshot',
                       'Repository metadata may have changed after a historical version was published',
                       'Reconstructed eligibility and mapping are not historical package observations'],
    }


def policy_sha256():
    return hashlib.sha256(canonical_bytes(policy_document())).hexdigest()
