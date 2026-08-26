from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = PACKAGE_DIR / ".env.local"
DEFAULT_SOURCE_PATH = PACKAGE_DIR / "config" / "sources.json"
DEFAULT_POLICY_PATH = PACKAGE_DIR / "config" / "provider_policies.json"
DEFAULT_QUOTA_OVERRIDE_PATH = PACKAGE_DIR / "config" / "quota_limits.local.json"
SOURCE_KINDS = {"API", "FILE", "HYBRID"}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_env_file(path: str | Path = DEFAULT_ENV_PATH) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    data: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def display_name(self) -> str:
        return str(self.data.get("display_name", self.source_id))


class SourceRegistry:
    def __init__(
        self,
        source_path: str | Path = DEFAULT_SOURCE_PATH,
        policy_path: str | Path = DEFAULT_POLICY_PATH,
        local_policy_path: str | Path | None = None,
        quota_override_path: str | Path | None = None,
    ) -> None:
        source_doc = json.loads(Path(source_path).read_text(encoding="utf-8"))
        policy_doc = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        if local_policy_path and Path(local_policy_path).exists():
            local_doc = json.loads(Path(local_policy_path).read_text(encoding="utf-8"))
            policy_doc = _deep_merge(policy_doc, local_doc)
        self.version = str(source_doc["version"])
        self._sources = source_doc["sources"]
        self._policies = policy_doc.get("sources", {})
        quota_doc: dict[str, Any] = {}
        if quota_override_path and Path(quota_override_path).exists():
            quota_doc = json.loads(Path(quota_override_path).read_text(encoding="utf-8"))
        self._quota_overrides = quota_doc.get("sources", {})
        self.default_policy = policy_doc.get(
            "default", {"raw": "DENY", "normalized": "DENY", "reason": "UNVERIFIED"}
        )
        self._validate_source_contracts()
        self._validate_quota_pools()

    def list(self) -> list[SourceSpec]:
        return [SourceSpec(key, deepcopy(value)) for key, value in sorted(self._sources.items())]

    def get(self, source_id: str) -> SourceSpec:
        try:
            return SourceSpec(source_id, deepcopy(self._sources[source_id]))
        except KeyError as exc:
            known = ", ".join(sorted(self._sources))
            raise KeyError(f"Unknown source '{source_id}'. Known sources: {known}") from exc

    def policy(self, source_id: str) -> dict[str, Any]:
        policy = _deep_merge(self.default_policy, self._policies.get(source_id, {}))
        self._validate_policy(source_id, policy)
        return policy

    def quota(self, source_id: str) -> dict[str, Any]:
        if not self.supports_live(source_id):
            raise ValueError(
                f"Live API collection is not available for file-only source {source_id}"
            )
        quota = self._quota_definition(source_id)
        self._validate_quota(source_id, quota, require_runnable=True)
        return quota

    def supports_live(self, source_id: str) -> bool:
        """Return whether the source has a callable provider endpoint."""
        return str(self.get(source_id).get("source_kind", "API")) in {"API", "HYBRID"}

    def supports_file(self, source_id: str) -> bool:
        """Return whether provider files are an intended collection path."""
        return str(self.get(source_id).get("source_kind", "API")) in {"FILE", "HYBRID"}

    def quota_status(self, source_id: str) -> str:
        try:
            return str(self.quota(source_id)["status"])
        except ValueError:
            return "UNCONFIRMED"

    def _validate_quota_pools(self) -> None:
        unknown_sources = set(self._quota_overrides) - set(self._sources)
        if unknown_sources:
            raise ValueError(
                "Quota override references unknown sources: "
                + ", ".join(sorted(unknown_sources))
            )
        known_limits: dict[str, int] = {}
        for source_id in self._sources:
            if not self.supports_live(source_id):
                continue
            quota = self._quota_definition(source_id)
            self._validate_quota(source_id, quota, require_runnable=False)
            if quota["status"] == "UNCONFIRMED":
                continue
            pool = str(quota["pool"])
            limit = int(quota["daily_limit"])
            prior = known_limits.get(pool)
            if prior is not None and prior != limit:
                raise ValueError(
                    f"Quota pool {pool} has inconsistent limits: {prior} and {limit}"
                )
            known_limits[pool] = limit

    def _validate_source_contracts(self) -> None:
        """Reject incomplete registry entries before a collection starts.

        API and file sources intentionally have different requirements.  This
        keeps static reference files in the same validation registry without
        pretending that they have an endpoint, credential, or call quota.
        """
        for source_id, data in self._sources.items():
            kind = str(data.get("source_kind", "API"))
            if kind not in SOURCE_KINDS:
                raise ValueError(f"Invalid source_kind for {source_id}: {kind}")
            if kind in {"API", "HYBRID"}:
                if not str(data.get("endpoint_template") or "").strip():
                    raise ValueError(f"Callable source {source_id} requires endpoint_template")
                auth = data.get("auth")
                if not isinstance(auth, dict) or not str(auth.get("env") or "").strip():
                    raise ValueError(f"Callable source {source_id} requires auth.env")
                if not str(data.get("quota_pool") or "").strip():
                    raise ValueError(f"Callable source {source_id} requires quota_pool")
                optional_path_params = data.get("optional_path_params", [])
                if not isinstance(optional_path_params, list) or any(
                    not str(value).strip() for value in optional_path_params
                ):
                    raise ValueError(
                        f"optional_path_params for {source_id} must be a list of names"
                    )
                if len(set(optional_path_params)) != len(optional_path_params):
                    raise ValueError(
                        f"optional_path_params for {source_id} contains duplicates"
                    )
            if kind in {"FILE", "HYBRID"}:
                formats = data.get("file_formats")
                if not isinstance(formats, list) or not formats:
                    raise ValueError(f"File source {source_id} requires file_formats")
                unsupported = {
                    str(value).lower() for value in formats
                } - {"csv", "xlsx", "json", "xml"}
                if unsupported:
                    raise ValueError(
                        f"Unsupported file_formats for {source_id}: {', '.join(sorted(unsupported))}"
                    )
            for field, pattern in data.get("format_patterns", {}).items():
                try:
                    re.compile(str(pattern))
                except re.error as exc:
                    raise ValueError(
                        f"Invalid format pattern for {source_id}.{field}: {exc}"
                    ) from exc
            for contract in data.get("wide_field_contracts", []):
                try:
                    re.compile(str(contract["pattern"]))
                    expected = int(contract["expected"])
                except (KeyError, TypeError, ValueError, re.error) as exc:
                    raise ValueError(
                        f"Invalid wide_field_contract for {source_id}: {contract!r}"
                    ) from exc
                if expected < 1:
                    raise ValueError(
                        f"wide_field_contract expected count must be positive for {source_id}"
                    )

    def _quota_definition(self, source_id: str) -> dict[str, Any]:
        spec = self.get(source_id)
        quota = {
            "status": spec.get("quota_status", "UNCONFIRMED"),
            "pool": spec.get("quota_pool"),
            "daily_limit": spec.get("daily_quota"),
            "verified_at": spec.get("quota_verified_at"),
            "review_ticket": spec.get("quota_review_ticket"),
            "evidence": spec.get("quota_evidence"),
        }
        override = self._quota_overrides.get(source_id)
        if override is None:
            return quota
        if not isinstance(override, dict):
            raise ValueError(f"Quota override for {source_id} must be an object")
        allowed = {
            "status",
            "pool",
            "daily_limit",
            "verified_at",
            "review_ticket",
            "evidence",
        }
        unknown = set(override) - allowed
        if unknown:
            raise ValueError(
                f"Unknown quota override fields for {source_id}: {', '.join(sorted(unknown))}"
            )
        base_status = str(quota["status"])
        base_pool = str(quota.get("pool") or "")
        if base_status != "UNCONFIRMED":
            raise ValueError(
                f"Quota override is not allowed for confirmed source {source_id}"
            )
        # A local review may supply a conservative limit, but it cannot split
        # one credential into artificial pools and thereby bypass accounting.
        if override.get("status") != "LOCAL_OVERRIDE":
            raise ValueError(
                f"Quota override for {source_id} must declare status=LOCAL_OVERRIDE"
            )
        if str(override.get("pool") or "") != base_pool:
            raise ValueError(
                f"Quota pool for {source_id} is immutable and must remain {base_pool}"
            )
        quota.update(deepcopy(override))
        return quota

    @staticmethod
    def _validate_quota(
        source_id: str, quota: dict[str, Any], *, require_runnable: bool
    ) -> None:
        status = str(quota.get("status", "UNCONFIRMED"))
        allowed_statuses = {
            "VERIFIED_SERVICE_LIMIT",
            "VERIFIED_SHARED_LIMIT",
            "CONSERVATIVE_SHARED_LIMIT",
            "LOCAL_OVERRIDE",
            "UNCONFIRMED",
        }
        if status not in allowed_statuses:
            raise ValueError(f"Invalid quota status for {source_id}: {status}")
        if status == "UNCONFIRMED":
            if require_runnable:
                raise ValueError(
                    f"Live collection is blocked for {source_id}: quota limit/reset is unconfirmed. "
                    "Add a reviewed local quota override."
                )
            return
        pool = str(quota.get("pool") or "").strip()
        limit = quota.get("daily_limit")
        if not pool or isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(
                f"Runnable quota for {source_id} requires a pool and positive integer daily_limit"
            )
        if status == "LOCAL_OVERRIDE":
            ticket = str(quota.get("review_ticket") or "").strip()
            verified_at = str(quota.get("verified_at") or "").strip()
            placeholder = ticket.upper().startswith("REPLACE_") or verified_at == "YYYY-MM-DD"
            if not ticket or not verified_at or placeholder:
                raise ValueError(
                    f"Local quota override for {source_id} requires review_ticket and verified_at"
                )
            try:
                date.fromisoformat(verified_at)
            except ValueError as exc:
                raise ValueError(
                    f"Quota override verified_at for {source_id} must be YYYY-MM-DD"
                ) from exc

    @staticmethod
    def _validate_policy(source_id: str, policy: dict[str, Any]) -> None:
        allowed_values = {"DENY", "ALLOW_LOCAL_ONLY"}
        for artifact_kind in ("raw", "normalized"):
            value = policy.get(artifact_kind)
            if value not in allowed_values:
                raise ValueError(
                    f"Invalid {artifact_kind} policy for {source_id}: {value!r}. "
                    f"Allowed values: {', '.join(sorted(allowed_values))}"
                )
        if "ALLOW_LOCAL_ONLY" in {policy.get("raw"), policy.get("normalized")}:
            ticket = str(policy.get("review_ticket", "")).strip()
            reviewed_at = str(policy.get("reviewed_at", "")).strip()
            placeholder = ticket.upper().startswith("REPLACE_") or reviewed_at == "YYYY-MM-DD"
            if not ticket or not reviewed_at or placeholder:
                raise ValueError(
                    f"Persistence policy for {source_id} requires review_ticket and reviewed_at"
                )
            try:
                date.fromisoformat(reviewed_at)
            except ValueError as exc:
                raise ValueError(
                    f"Persistence policy reviewed_at for {source_id} must be YYYY-MM-DD"
                ) from exc
