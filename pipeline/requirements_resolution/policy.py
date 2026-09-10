"""Explicit, reproducible choices for the requirements calculation."""
from __future__ import annotations

import hashlib
import json

from pipeline.snapshot.policy import policy_document as snapshot_document
from pipeline.snapshot.policy import policy_sha256 as snapshot_sha256

POLICY_VERSION = "requirements-resolution-v1"
KINDS = {"dependencies": "Dependencies", "peerDependencies": "PeerDependencies",
         "optionalDependencies": "OptionalDependencies"}


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def sha256(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def make_policy(*, kinds, unknown_published_at, unresolved, decision_reference):
    if (not isinstance(kinds, (list, tuple)) or not kinds
            or any(kind not in KINDS for kind in kinds) or len(set(kinds)) != len(kinds)):
        raise ValueError("Select distinct supported dependency kinds explicitly")
    if list(kinds) != ["dependencies"]:
        raise ValueError("Only regular dependencies are approved for this contract")
    if unknown_published_at not in ("include", "exclude"):
        raise ValueError("Select the NULL publication-date policy explicitly")
    if unresolved not in ("partial", "fail"):
        raise ValueError("Select the unresolved-result policy explicitly")
    if not isinstance(decision_reference, str) or not decision_reference.strip():
        raise ValueError("A policy decision reference is required")
    document = {
        "policy_version": POLICY_VERSION,
        "kinds": sorted(kinds),
        "excluded_kinds": {"peerDependencies": "USER_SELECTED_REGULAR_DEPENDENCIES_ONLY",
                           "optionalDependencies": "USER_SELECTED_REGULAR_DEPENDENCIES_ONLY"},
        "excluded_raw_preservation": "approved_requirements_bronze_reference",
        "unknown_published_at": unknown_published_at,
        "unresolved": unresolved,
        "decision_reference": decision_reference.strip(),
        "snapshot_policy": {"document": snapshot_document(), "sha256": snapshot_sha256()},
        "source_population": "all_curated_release_versions_at_exact_snapshot",
        "target_population": "same_snapshot_release_versions_valid_stable_semver",
        "semver_options": {"loose": False, "includePrerelease": False},
        "equal_precedence_tie": "original_version_utf16_ascending",
        "unsupported_specifiers": ["alias", "tag", "git", "file", "directory", "remote"],
        "edge_grain": ["snapshot_at", "source_package_id", "source_version",
                       "target_package_id", "target_version"],
        "complete_requires": "every_source_has_known_requirements_and_every_selected_declaration_resolves",
        "publication_gate": "complete_observed_declarations_only",
        "upstream_processing_completeness": "unverified_dependencies_processed_not_projected",
    }
    return {"document": document, "sha256": sha256(document)}


def validate_policy(policy):
    if not isinstance(policy, dict) or not isinstance(policy.get("document"), dict):
        raise ValueError("Policy document missing")
    doc = policy["document"]
    expected = make_policy(kinds=doc.get("kinds"), unknown_published_at=doc.get("unknown_published_at"),
                           unresolved=doc.get("unresolved"), decision_reference=doc.get("decision_reference"))
    if policy != expected:
        raise ValueError("Policy is changed, incomplete, or uses an unsupported contract")
    return doc
