"""Separate artifact-generation identity from the checks used by each load attempt."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import hashlib
from pathlib import Path

import duckdb

from pipeline.preprocessing.package_snapshot.history_policy import policy_document
from pipeline.postgresql.package_snapshot.load import contract_sha256 as load_contract_sha256
from pipeline.preprocessing.package_snapshot.policy import canonical_bytes

ROOT = REPO_ROOT

# Include orchestration and source readers conservatively: they can change the
# interval or population passed to the SQL even when history_build.py is unchanged.
# Keep quality validators out; the output schema/projection lives in its own file.
BUILD_FILES = (
    'pipeline/preprocessing/package_snapshot/history_policy.py',
    'pipeline/preprocessing/package_snapshot/history_inputs.py',
    'pipeline/preprocessing/package_snapshot/history_build.py',
    'pipeline/postgresql/package_snapshot/history.py',
    'pipeline/preprocessing/package_snapshot/quality_schema.py',
    'pipeline/preprocessing/package_snapshot/policy.py',
    'pipeline/downloads/bronze.py',
    'pipeline/preprocessing/downloads_interval/aggregate.py',
    'pipeline/preprocessing/curated/build.py',
    'pipeline/preprocessing/curated/storage.py',
    'pipeline/postgresql/input.py',
    'pipeline/preprocessing/common/curated_input.py',
    'pipeline/preprocessing/snapshot/input.py',
    'pipeline/preprocessing/snapshot/build.py',
    'pipeline/preprocessing/snapshot/policy.py',
    'pipeline/preprocessing/snapshot/projects.py',
)
VALIDATOR_FILES = (
    'pipeline/postgresql/package_snapshot/history.py',
    'pipeline/postgresql/package_snapshot/history_load.py',
    'pipeline/preprocessing/package_snapshot/history_inputs.py',
    'pipeline/preprocessing/package_snapshot/history_policy.py',
    'pipeline/preprocessing/package_snapshot/policy.py',
    'pipeline/downloads/bronze.py',
)


def _contract(files, metadata):
    # The ordered paths and versioned metadata are part of the digest. This
    # module is not hashed wholesale: editing the validator file list must not
    # invalidate an otherwise identical build contract. Bump the corresponding
    # format version when changing hash framing or text-normalization rules.
    digest = hashlib.sha256(canonical_bytes(metadata) + b'\0')
    for name in files:
        digest.update(name.encode('utf-8') + b'\0')
        digest.update((ROOT / name).read_text(encoding='utf-8').encode('utf-8') + b'\0')
    return digest.hexdigest()


def build_contract_sha256():
    return _contract(BUILD_FILES, {'format': 'package-snapshot-history-build-v1',
                                  'policy': policy_document(), 'duckdb': duckdb.__version__})


def validator_contract_sha256():
    # Reuse the loader's explicit V1-V3 schema and shared validator dependency
    # scope. An unrelated migration must not change either contract.
    return _contract(VALIDATOR_FILES, {'format': 'package-snapshot-history-validator-v1',
                                      'load_contract_sha256': load_contract_sha256(),
                                      'policy': policy_document(), 'duckdb': duckdb.__version__})
