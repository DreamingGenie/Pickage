"""Small, opt-in structured logging helpers for the collector.

The library must not configure the process-wide logging system on import.  A
CLI (or an embedding application) calls :func:`configure_logging` explicitly;
until then the package remains quiet through a ``NullHandler``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, TextIO

from .safety import redact_mapping, redact_text


LOGGER_NAME = "collector"
LOGGER = logging.getLogger(LOGGER_NAME)
if not LOGGER.handlers:
    # Avoid the "no handler" warning while keeping library imports silent.
    LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return a collector logger without changing application logging setup."""
    return logging.getLogger(name)


def _redact_value(value: Any, secrets: list[str]) -> Any:
    """Redact strings recursively so a context object cannot leak credentials."""
    if isinstance(value, Mapping):
        return redact_mapping(dict(value), secrets)
    if isinstance(value, list):
        return [_redact_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, secrets) for item in value)
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def _redacted_context(context: Mapping[str, Any], secrets: Iterable[str]) -> dict[str, Any]:
    secret_values = [secret for secret in secrets if secret]
    return {key: _redact_value(value, secret_values) for key, value in context.items()}


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str = "",
    *,
    secrets: Iterable[str] = (),
    **context: Any,
) -> None:
    """Emit one event with safe, structured context.

    ``extra`` is used instead of interpolating a dict into the message, so the
    JSON formatter and the human formatter expose the same fields.  The
    formatter redacts once more as defense in depth for handlers installed by
    embedding applications.
    """
    secret_values = [secret for secret in secrets if secret]
    logger.log(
        level,
        redact_text(message, secret_values),
        extra={
            "collector_event": redact_text(event, secret_values),
            "collector_context": _redacted_context(context, secret_values),
        },
    )


class _EventFormatter(logging.Formatter):
    def __init__(self, *, json_lines: bool, secrets: Iterable[str]) -> None:
        super().__init__()
        self.json_lines = json_lines
        self.secrets = [secret for secret in secrets if secret]

    def _record_values(self, record: logging.LogRecord) -> tuple[str, str, dict[str, Any]]:
        event = getattr(record, "collector_event", record.name)
        message = redact_text(record.getMessage(), self.secrets)
        raw_context = getattr(record, "collector_context", {})
        context = _redacted_context(raw_context, self.secrets)
        return redact_text(str(event), self.secrets), message, context

    def format(self, record: logging.LogRecord) -> str:
        event, message, context = self._record_values(record)
        timestamp = datetime.now(timezone.utc).isoformat()
        if self.json_lines:
            payload = {
                "timestamp": timestamp,
                "level": record.levelname,
                "event": event,
                "message": message,
                "context": context,
            }
            return json.dumps(payload, ensure_ascii=False, default=str)

        fields = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
            for key, value in context.items()
        )
        suffix = f" {fields}" if fields else ""
        return f"{timestamp} {record.levelname} {event}: {message}{suffix}"


def configure_logging(
    level: int | str = logging.INFO,
    output_format: str = "text",
    secrets: Iterable[str] = (),
    *,
    format: str | None = None,
    secret_values: Iterable[str] | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure collector stderr logging and return the collector logger.

    Only handlers previously installed by this function are replaced.  This
    lets a host application keep its own logging handlers while the CLI gets a
    predictable stderr stream.  ``stream`` exists for tests and embedding;
    normal callers should leave it unset to use ``sys.stderr``.
    """
    # ``format``/``secret_values`` are readable aliases for callers wiring a
    # CLI flag or a service config; the original names remain supported.
    if format is not None:
        output_format = format
    if secret_values is not None:
        secrets = secret_values
    if output_format not in {"text", "json"}:
        raise ValueError("output_format must be 'text' or 'json'")
    logger = LOGGER
    logger.setLevel(level)
    for handler in list(logger.handlers):
        if getattr(handler, "_collector_configured", False):
            logger.removeHandler(handler)
            handler.close()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler._collector_configured = True  # type: ignore[attr-defined]
    handler.setFormatter(
        _EventFormatter(json_lines=output_format == "json", secrets=secrets)
    )
    logger.addHandler(handler)
    return logger
