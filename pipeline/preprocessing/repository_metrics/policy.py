"""User-approved repository selection policy, separate from snapshot-time-v1."""
import hashlib
import json

from pipeline.preprocessing.snapshot.policy import policy_document as snapshot_policy_document
from pipeline.preprocessing.snapshot.policy import policy_sha256 as snapshot_policy_sha256


def policy_document():
    return {
        "policy_version": "repository-metrics-v2",
        "snapshot_policy": snapshot_policy_document(),
        "snapshot_policy_sha256": snapshot_policy_sha256(),
        "repository_source": "approved_version_keys_join_same_snapshot_versions_full",
        "candidate_order": ["ordinal DESC", "published_at DESC NULLS LAST", "version ASC"],
        "url_normalization": "pipeline.preprocessing.curated.repository.normalize_repository_url",
        "url_max_length": 200,
        "identity": ["provider", "full_project_path"],
        "project_path_comparison": {"github.com": "lowercase", "gitlab.com": "exact"},
        "selected_url": "preserve_original_normalized_url_case",
        "missing_observation": "retain_selected_repository_and_null_metrics",
        "observation": "exact SnapshotAt equality",
        "duplicate_observation": "collapse_equal_stars_open_issues_pairs",
        "conflicting_observation": "null_both_metrics_and_preserve_evidence",
        "invalid_metric_value": "null_metrics_and_preserve_evidence",
        "metric_range": "NULL or integer between 0 and 2147483647",
        "shared_repository": "reuse_observation_without_summing",
        "historical_alias_resolution": "no_network_or_silent_redirect_replacement",
    }


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def policy_sha256():
    return hashlib.sha256(canonical_bytes(policy_document())).hexdigest()
