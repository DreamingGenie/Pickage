"""Explicitly approved reconstruction policy, separate from observed snapshot v1."""
from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

from .policy import canonical_bytes


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


def contract_sha256():
    root = Path(__file__).resolve().parents[2]
    names = ('history_policy.py', 'history_inputs.py', 'history_build.py', 'history_load.py', 'history.py', 'quality.py')
    paths = [Path(__file__).with_name(name) for name in names]
    paths += [Path(__file__).with_name('postgres.py'), root / 'pipeline/postgresql/postgres.py',
              root / 'pipeline/downloads/bronze.py', root / 'pipeline/downloads_interval/aggregate.py']
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(path.read_text(encoding='utf-8').encode() + b'\0')
    digest.update(canonical_bytes({'policy': policy_document(), 'duckdb': duckdb.__version__}))
    return digest.hexdigest()
