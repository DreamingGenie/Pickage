"""Secret loading for Phase 0 spike scripts.

Loads scripts/spikes/.env.local (gitignored, never committed) and exposes
keys by logical name. Never print or log the actual value anywhere.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_LOCAL = Path(__file__).resolve().parent.parent / ".env.local"
load_dotenv(_ENV_LOCAL)


class MissingSecretError(RuntimeError):
    pass


def require_key(name: str) -> str:
    """Return the named env var or raise, without ever echoing a value."""
    value = os.environ.get(name)
    if not value:
        raise MissingSecretError(
            f"{name} is not set. Copy templates/.env.example to "
            f"scripts/spikes/.env.local and fill in {name} (value itself "
            f"stays local, never paste it into chat/logs)."
        )
    return value


def redact(value: str, keep: int = 4) -> str:
    """first4...last4 style redaction for any incidental logging."""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"
