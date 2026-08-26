from __future__ import annotations

import email.utils
import logging
import os
import random
import socket
import string
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import SourceSpec
from .contracts import HttpExchange
from .logging_utils import LOGGER, log_event
from .safety import redact_mapping, sanitize_url, sha256_bytes


class ConfigurationError(RuntimeError):
    pass


class _RejectRedirectHandler(HTTPRedirectHandler):
    """Keep query/path credentials on the configured provider origin.

    Redirects are rejected deliberately: a provider could otherwise redirect
    a URL containing a path/query API key to an unrelated host.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


class HttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        max_response_bytes: int = 10_000_000,
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if max_retries < 0 or max_retries > 5:
            raise ValueError("max_retries must be between 0 and 5")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_response_bytes = max_response_bytes
        self.clock = clock
        self.sleeper = sleeper
        self.jitter = jitter
        self.opener = build_opener(_RejectRedirectHandler())

    def prepare(
        self,
        spec: SourceSpec,
        params: dict[str, Any],
        *,
        allow_insecure_http: bool,
    ) -> tuple[str, str, dict[str, Any], list[str]]:
        merged = dict(spec.get("default_params", {}))
        merged.update({key: str(value) for key, value in params.items()})
        missing = [name for name in spec.get("required_params", []) if not merged.get(name)]
        if missing:
            raise ConfigurationError(f"Missing required parameters: {', '.join(missing)}")

        auth = spec.get("auth", {})
        credential_env = auth.get("env")
        secret = os.environ.get(credential_env, "") if credential_env else ""
        if credential_env and not secret:
            raise ConfigurationError(f"Missing credential environment variable: {credential_env}")

        template = spec.get("endpoint_template")
        if template.lower().startswith("http://") and not allow_insecure_http:
            raise ConfigurationError(
                "This provider exposes an HTTP-only endpoint. Re-run with --allow-insecure-http "
                "only after accepting the query/path credential transport risk."
            )

        path_values = dict(spec.get("path_defaults", {}))
        path_values.update(merged)
        if auth.get("location") == "path":
            path_values[auth.get("name", "key")] = secret

        encoded_path_values = {key: quote(str(value), safe="") for key, value in path_values.items()}
        try:
            url = template.format(**encoded_path_values)
        except KeyError as exc:
            raise ConfigurationError(f"Missing path parameter: {exc.args[0]}") from exc

        path_keys = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(template)
            if field_name
        }
        optional_path_params = [
            str(name) for name in spec.get("optional_path_params", [])
        ]
        populated_optional = [
            index
            for index, name in enumerate(optional_path_params)
            if path_values.get(name) not in (None, "")
        ]
        if populated_optional:
            last_index = max(populated_optional)
            missing_prefix = [
                name
                for name in optional_path_params[:last_index]
                if path_values.get(name) in (None, "")
            ]
            if missing_prefix:
                raise ConfigurationError(
                    "Optional path parameters must be supplied in order; missing: "
                    + ", ".join(missing_prefix)
                )
            # Seoul Open Data expresses filters as trailing path segments.  Add
            # only the populated prefix so an unfiltered call keeps the exact
            # documented `/start/end/` URL instead of producing `///`.
            url = url.rstrip("/") + "/"
            url += "/".join(
                quote(str(path_values[name]), safe="")
                for name in optional_path_params[: last_index + 1]
            )
            url += "/"

        path_keys.update(optional_path_params)
        query_params = {key: value for key, value in merged.items() if key not in path_keys}
        if auth.get("location") == "query":
            query_params[auth.get("name", "serviceKey")] = secret
        if query_params:
            url = f"{url}?{urlencode(query_params)}"

        sensitive_params = spec.get("sensitive_params", [])
        safe_url = sanitize_url(url, [secret], sensitive_params)
        safe_params = redact_mapping(merged, [secret], sensitive_params)
        return url, safe_url, safe_params, [secret]

    def fetch(
        self,
        spec: SourceSpec,
        params: dict[str, Any],
        *,
        allow_insecure_http: bool = False,
        context: Mapping[str, Any] | None = None,
    ) -> HttpExchange:
        correlation = dict(context or {})
        url, safe_url, safe_params, secrets = self.prepare(
            spec, params, allow_insecure_http=allow_insecure_http
        )
        attempts = 0
        last_exchange: HttpExchange | None = None
        first_requested_at: str | None = None
        retry_history: list[dict[str, Any]] = []
        while attempts <= self.max_retries:
            attempts += 1
            last_exchange = self._attempt(
                spec,
                url,
                safe_url,
                safe_params,
                attempts,
                correlation,
                secrets,
            )
            first_requested_at = first_requested_at or last_exchange.requested_at
            if not self._should_retry(last_exchange) or attempts > self.max_retries:
                if first_requested_at != last_exchange.requested_at:
                    first = datetime.fromisoformat(first_requested_at)
                    completed = datetime.fromisoformat(last_exchange.body_completed_at)
                    last_exchange.requested_at = first_requested_at
                    last_exchange.elapsed_ms = max(
                        0.0, (completed - first).total_seconds() * 1000
                    )
                last_exchange.retry_history = retry_history
                return last_exchange
            retry_history.append(
                {
                    "attempt": attempts,
                    "requested_at": last_exchange.requested_at,
                    "headers_received_at": last_exchange.headers_received_at,
                    "body_completed_at": last_exchange.body_completed_at,
                    "http_status": last_exchange.http_status,
                    "transport_error": last_exchange.transport_error,
                    "body_sha256": last_exchange.body_sha256,
                    "body_bytes": last_exchange.body_bytes,
                }
            )
            delay = self._retry_delay(attempts, last_exchange.retry_after)
            # Keep retries visible without logging the response body or the
            # original URL, both of which may contain provider credentials.
            log_event(
                LOGGER,
                logging.INFO,
                "http.retry_scheduled",
                "transient response will be retried",
                secrets=secrets,
                **{
                    **correlation,
                    "source_id": spec.source_id,
                    "attempt": attempts,
                    "next_attempt": attempts + 1,
                    "http_status": last_exchange.http_status,
                    "transport_error": last_exchange.transport_error,
                    "delay_seconds": round(delay, 3),
                },
            )
            self.sleeper(delay)
        assert last_exchange is not None
        return last_exchange

    def _attempt(
        self,
        spec: SourceSpec,
        url: str,
        safe_url: str,
        safe_params: dict[str, Any],
        attempt: int,
        context: Mapping[str, Any],
        secrets: list[str],
    ) -> HttpExchange:
        requested = self.clock()
        headers_received: datetime | None = None
        status: int | None = None
        content_type: str | None = None
        body = b""
        transport_error: str | None = None
        retry_after: str | None = None
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.1"},
        )
        log_event(
            LOGGER,
            logging.DEBUG,
            "http.attempt_started",
            "HTTP attempt started",
            secrets=secrets,
            **{
                **context,
                "source_id": spec.source_id,
                "attempt": attempt,
                "safe_endpoint": safe_url,
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                headers_received = self.clock()
                status = response.status
                content_type = response.headers.get("Content-Type")
                retry_after = response.headers.get("Retry-After")
                body = self._bounded_read(response)
        except HTTPError as exc:
            headers_received = self.clock()
            status = exc.code
            content_type = exc.headers.get("Content-Type") if exc.headers else None
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                body = self._bounded_read(exc)
            except ValueError:
                body = b""
            transport_error = f"HTTPError:{exc.code}"
        except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            transport_error = type(exc).__name__
        except ValueError as exc:
            transport_error = f"ResponseRejected:{exc}"
        completed = self.clock()
        elapsed_ms = max(0.0, (completed - requested).total_seconds() * 1000)
        exchange = HttpExchange(
            exchange_id=uuid.uuid4().hex,
            source_id=spec.source_id,
            safe_endpoint=safe_url,
            safe_params=safe_params,
            requested_at=iso(requested),
            headers_received_at=iso(headers_received) if headers_received else None,
            body_completed_at=iso(completed),
            http_status=status,
            content_type=content_type,
            body=body,
            body_sha256=sha256_bytes(body),
            body_bytes=len(body),
            attempts=attempt,
            elapsed_ms=elapsed_ms,
            transport_error=transport_error,
            retry_after=retry_after,
        )
        log_event(
            LOGGER,
            logging.INFO,
            "http.attempt_finished",
            "HTTP attempt finished",
            secrets=secrets,
            **{
                **context,
                "source_id": spec.source_id,
                "attempt": attempt,
                "exchange_id": exchange.exchange_id,
                "safe_endpoint": safe_url,
                "http_status": status,
                "transport_error": transport_error,
                "body_bytes": len(body),
                "elapsed_ms": round(elapsed_ms, 3),
            },
        )
        return exchange

    def _bounded_read(self, response: Any) -> bytes:
        body = response.read(self.max_response_bytes + 1)
        if len(body) > self.max_response_bytes:
            raise ValueError(f"response exceeds {self.max_response_bytes} bytes")
        return body

    @staticmethod
    def _should_retry(exchange: HttpExchange) -> bool:
        if exchange.http_status in (408, 425, 429):
            return True
        if exchange.http_status is not None and 500 <= exchange.http_status <= 599:
            return True
        return exchange.http_status is None and exchange.transport_error is not None

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                try:
                    target = email.utils.parsedate_to_datetime(retry_after)
                    return max(0.0, min((target - self.clock()).total_seconds(), 60.0))
                except (TypeError, ValueError):
                    pass
        base = min(0.5 * (2 ** (attempt - 1)), 8.0)
        return self.jitter(base * 0.8, base * 1.2)
