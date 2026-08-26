from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit


SECRET_NAME_RE = re.compile(r"(key|token|secret|authorization|credential)", re.IGNORECASE)
REDACTED = "<redacted>"
PERCENT_ESCAPE_RE = re.compile(r"%[0-9a-fA-F]{2}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def redact_mapping(
    values: dict[str, Any],
    secret_values: list[str] | None = None,
    sensitive_names: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    sensitive = {str(name).casefold() for name in (sensitive_names or [])}
    return {
        key: REDACTED
        if SECRET_NAME_RE.search(str(key)) or str(key).casefold() in sensitive
        else _redact_nested(value, secret_values or [], sensitive)
        for key, value in values.items()
    }


def _redact_nested(
    value: Any, secret_values: list[str], sensitive_names: set[str] | None = None
) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value, secret_values, sensitive_names)
    if isinstance(value, list):
        return [_redact_nested(item, secret_values, sensitive_names) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_nested(item, secret_values, sensitive_names) for item in value)
    if isinstance(value, str):
        return redact_text(value, secret_values)
    return value


def sanitize_url(
    url: str,
    secret_values: list[str] | None = None,
    sensitive_names: list[str] | set[str] | tuple[str, ...] | None = None,
) -> str:
    parts = urlsplit(url)
    sensitive = {str(name).casefold() for name in (sensitive_names or [])}
    safe_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        safe_value = value
        for secret in secret_values or []:
            if secret:
                for variant in secret_variants(secret):
                    safe_value = safe_value.replace(variant, REDACTED)
        safe_query.append(
            (
                key,
                REDACTED
                if SECRET_NAME_RE.search(key) or key.casefold() in sensitive
                else safe_value,
            )
        )
    safe_path = parts.path
    for secret in secret_values or []:
        if secret:
            for variant in secret_variants(secret):
                safe_path = safe_path.replace(variant, REDACTED)
    return urlunsplit((parts.scheme, parts.netloc, safe_path, urlencode(safe_query), ""))


def secret_variants(secret: str) -> set[str]:
    """Return raw and common serialized/encoded credential representations."""
    json_escaped = json.dumps(secret, ensure_ascii=False)[1:-1]
    json_ascii_escaped = json.dumps(secret, ensure_ascii=True)[1:-1]
    variants = {
        secret,
        json_escaped,
        json_ascii_escaped,
        html.escape(secret, quote=True),
    }
    frontier = set(variants)
    for _ in range(2):
        encoded = {
            candidate
            for value in frontier
            for candidate in (quote(value, safe=""), quote_plus(value, safe=""))
        }
        variants.update(encoded)
        frontier = encoded
    return variants


def _normalize_percent_escapes(value: str) -> str:
    return PERCENT_ESCAPE_RE.sub(lambda match: match.group(0).upper(), value)


def contains_secret(value: Any, secrets: list[str]) -> bool:
    needles = {
        _normalize_percent_escapes(variant)
        for secret in secrets
        if secret
        for variant in secret_variants(secret)
    }
    if not needles:
        return False
    return any(
        needle in _normalize_percent_escapes(fragment)
        for fragment in _text_fragments(value)
        for needle in needles
    )


def _text_fragments(value: Any, seen: set[int] | None = None):  # type: ignore[no-untyped-def]
    visited = seen if seen is not None else set()
    if isinstance(value, str):
        yield value
        html_decoded = html.unescape(value)
        if html_decoded != value:
            yield html_decoded
        stripped = value.lstrip()
        if stripped.startswith(("{", "[", '"')):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                decoded = None
            if decoded is not None and decoded != value:
                yield from _text_fragments(decoded, visited)
        return
    if isinstance(value, (bytes, bytearray)):
        yield bytes(value).decode("utf-8", errors="replace")
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        for key, item in value.items():
            yield from _text_fragments(key, visited)
            yield from _text_fragments(item, visited)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        for item in value:
            yield from _text_fragments(item, visited)
        return
    if value is not None:
        yield str(value)


def redact_text(value: str, secrets: list[str]) -> str:
    result = value
    for secret in secrets:
        if not secret:
            continue
        for variant in secret_variants(secret):
            result = result.replace(variant, REDACTED)
    return result
