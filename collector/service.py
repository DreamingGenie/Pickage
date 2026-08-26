from __future__ import annotations

import json
import inspect
import logging
import math
import os
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .config import SourceRegistry
from .contracts import COLLECTOR_VERSION, CollectionItem, CollectionRun, HttpExchange, Purpose
from .http_client import HttpClient
from .logging_utils import LOGGER, log_event
from .parser import parse_exchange
from .safety import redact_mapping, redact_text, sha256_bytes
from .storage import MetadataRepository
from .validator import Validator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


KST = timezone(timedelta(hours=9), name="Asia/Seoul")


class CollectionService:
    def __init__(
        self,
        registry: SourceRegistry | None = None,
        repository: MetadataRepository | None = None,
        http_client: HttpClient | None = None,
        validator: Validator | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.registry = registry or SourceRegistry()
        self.repository = repository or MetadataRepository()
        self.http_client = http_client or HttpClient()
        self.validator = validator or Validator()
        self.sleeper = sleeper

    def close(self) -> None:
        self.repository.close()

    def collect_live(
        self,
        source_id: str,
        params: dict[str, Any],
        *,
        purpose: Purpose = Purpose.CONTRACT_SMOKE,
        target: str | None = None,
        count: int = 1,
        interval_seconds: float = 0.0,
        allow_insecure_http: bool = False,
    ) -> CollectionRun:
        spec = self.registry.get(source_id)
        if not self.registry.supports_live(source_id):
            raise ValueError(
                f"{source_id} is file-only. Use collect-file with a downloaded provider file."
            )
        quota = self.registry.quota(source_id)
        if count < 1:
            raise ValueError("count must be at least 1")
        spec_limit = spec.get("max_calls_per_run")
        max_calls_per_run = int(spec_limit) if spec_limit is not None else 100
        if count > max_calls_per_run:
            raise ValueError(
                f"count={count} exceeds max_calls_per_run={max_calls_per_run} for {source_id}"
            )
        if interval_seconds < 0:
            raise ValueError("interval_seconds cannot be negative")
        # Fail before creating a run when credentials, required params, or HTTP risk acknowledgement are missing.
        _, _, _, secrets = self.http_client.prepare(
            spec, params, allow_insecure_http=allow_insecure_http
        )
        run = self._new_run(
            source_id,
            params,
            target,
            secrets=secrets,
            sensitive_params=spec.get("sensitive_params", []),
            sensitive_target=bool(spec.get("sensitive_target", False)),
        )
        policy = self.registry.policy(source_id)
        self.repository.begin_run(
            run, "LIVE", COLLECTOR_VERSION, secrets=secrets
        )
        quota_pool = str(quota["pool"])
        daily_quota = int(quota["daily_limit"])
        business_retry_factor = 2 if spec.get("business", {}).get("retryable_codes") else 1
        attempt_budget = (self.http_client.max_retries + 1) * business_retry_factor
        timeout_seconds = float(getattr(self.http_client, "timeout_seconds", 15.0))
        # A quota lease must outlive the slowest legal poll.  Each transport
        # attempt can consume the full timeout and Retry-After is capped at 60s.
        # Keep the default 15-minute floor for normal short requests.
        quota_lease_seconds = max(
            self.repository.DEFAULT_QUOTA_LEASE_SECONDS,
            math.ceil(
                attempt_budget * timeout_seconds
                + max(0, attempt_budget - 1) * 60
                + 60
            ),
        )
        quota_exhausted_codes = {
            str(code) for code in spec.get("business", {}).get("quota_exhausted_codes", [])
        }
        log_event(
            LOGGER,
            logging.INFO,
            "collection.started",
            "live collection started",
            secrets=secrets,
            run_id=run.run_id,
            source_id=source_id,
            purpose=purpose.value,
            target_sha256=sha256_bytes(run.target.encode("utf-8"))[:16],
            requested_count=count,
            quota_pool=quota_pool,
        )
        phase = "quota_reservation"
        try:
            phase = "quota_recovery"
            recovered_reservations = self.repository.recover_expired_quota()
            if recovered_reservations:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "quota.recovery_finished",
                    "expired reservations from interrupted runs were recovered",
                    run_id=run.run_id,
                    source_id=source_id,
                    recovered_reservations=recovered_reservations,
                )
            for index in range(count):
                poll_index = index + 1
                log_event(
                    LOGGER,
                    logging.INFO,
                    "poll.started",
                    "provider poll started",
                    secrets=secrets,
                    run_id=run.run_id,
                    source_id=source_id,
                    poll_index=poll_index,
                    requested_count=count,
                )
                quota_date = datetime.now(KST).date().isoformat()
                phase = "quota_reservation"
                reservation_id = self.repository.reserve_quota(
                    quota_pool,
                    quota_date,
                    attempt_budget,
                    daily_quota,
                    run_id=run.run_id,
                    lease_seconds=quota_lease_seconds,
                )
                quota_state = self.repository.quota_state(
                    quota_pool, quota_date, daily_quota
                )
                log_event(
                    LOGGER,
                    logging.INFO,
                    "quota.reserved",
                    "worst-case retry quota reserved before network I/O",
                    run_id=run.run_id,
                    source_id=source_id,
                    poll_index=poll_index,
                    quota_pool=quota_pool,
                    reservation_id=reservation_id,
                    kst_date=quota_date,
                    requested=attempt_budget,
                    lease_seconds=quota_lease_seconds,
                    **quota_state,
                )
                remaining_reservation = attempt_budget
                try:
                    phase = "http_and_parse"
                    exchange, batch = self._fetch_and_parse(
                        spec,
                        params,
                        allow_insecure_http=allow_insecure_http,
                        context={"run_id": run.run_id, "poll_index": poll_index},
                        secrets=secrets,
                    )
                    phase = "quota_consumption"
                    self.repository.consume_quota(
                        quota_pool,
                        quota_date,
                        exchange.attempts,
                        reservation_id,
                    )
                    remaining_reservation -= exchange.attempts
                    quota_state = self.repository.quota_state(
                        quota_pool, quota_date, daily_quota
                    )
                    log_event(
                        LOGGER,
                        logging.INFO,
                        "quota.consumed",
                        "actual transport attempts charged to quota",
                        run_id=run.run_id,
                        source_id=source_id,
                        poll_index=poll_index,
                        quota_pool=quota_pool,
                        reservation_id=reservation_id,
                        kst_date=quota_date,
                        consumed=exchange.attempts,
                        **quota_state,
                    )
                    item = CollectionItem(exchange=exchange, batch=batch)
                    run.items.append(item)
                    phase = "persistence"
                    self.repository.save_item(run, item, spec, policy)
                    log_event(
                        LOGGER,
                        logging.INFO,
                        "poll.finished",
                        "provider poll parsed and metadata persisted",
                        secrets=secrets,
                        run_id=run.run_id,
                        source_id=source_id,
                        poll_index=poll_index,
                        exchange_id=exchange.exchange_id,
                        http_status=exchange.http_status,
                        business_code=batch.business_code,
                        response_format=batch.response_format,
                        row_count=len(batch.rows),
                        body_bytes=exchange.body_bytes,
                    )
                finally:
                    self.repository.release_quota(
                        quota_pool,
                        quota_date,
                        remaining_reservation,
                        reservation_id,
                    )
                    if remaining_reservation:
                        quota_state = self.repository.quota_state(
                            quota_pool, quota_date, daily_quota
                        )
                        log_event(
                            LOGGER,
                            logging.DEBUG,
                            "quota.released",
                            "unused retry reservation released",
                            run_id=run.run_id,
                            source_id=source_id,
                            poll_index=poll_index,
                            quota_pool=quota_pool,
                            reservation_id=reservation_id,
                            kst_date=quota_date,
                            released=remaining_reservation,
                            **quota_state,
                        )
                if batch.business_code in quota_exhausted_codes:
                    run.failure_code = "PROVIDER_QUOTA_EXHAUSTED"
                    run.failure_message = (
                        f"Provider quota was exhausted at poll {poll_index} of {count}."
                    )
                    log_event(
                        LOGGER,
                        logging.WARNING,
                        "collection.stopped_quota_exhausted",
                        "provider business code reported quota exhaustion",
                        run_id=run.run_id,
                        source_id=source_id,
                        poll_index=poll_index,
                        business_code=batch.business_code,
                        requested_count=count,
                        completed_polls=len(run.items),
                    )
                    break
                if index + 1 < count and interval_seconds:
                    self.sleeper(interval_seconds)
        except Exception as exc:
            self._mark_failed(run, exc, secrets)
            self._log_failure(run, exc, phase, secrets)
        run.ended_at = _now_iso()
        self._finalize_and_report(
            run,
            spec,
            purpose,
            policy,
            evidence_mode="LIVE",
            secrets=secrets,
        )
        log_event(
            LOGGER,
            logging.ERROR if run.failure_code else logging.INFO,
            "collection.finished",
            "live collection finished",
            secrets=secrets,
            run_id=run.run_id,
            source_id=source_id,
            status="FAILED" if run.failure_code else "COMPLETE",
            failure_code=run.failure_code,
            observation_count=len(run.items),
            row_count=sum(len(item.batch.rows) for item in run.items),
            verdict=run.report.verdict.value,
        )
        return run

    def collect_fixture(
        self,
        source_id: str,
        fixture_path: str | Path,
        *,
        params: dict[str, Any] | None = None,
        purpose: Purpose = Purpose.CONTRACT_SMOKE,
        target: str | None = None,
    ) -> CollectionRun:
        return self.collect_fixtures(
            source_id,
            [fixture_path],
            params=params,
            purpose=purpose,
            target=target,
        )

    def collect_fixtures(
        self,
        source_id: str,
        fixture_paths: list[str | Path],
        *,
        params: dict[str, Any] | None = None,
        purpose: Purpose = Purpose.CONTRACT_SMOKE,
        target: str | None = None,
    ) -> CollectionRun:
        return self._collect_local_files(
            source_id,
            fixture_paths,
            params=params,
            purpose=purpose,
            target=target,
            evidence_mode="FIXTURE",
        )

    def collect_files(
        self,
        source_id: str,
        file_paths: list[str | Path],
        *,
        params: dict[str, Any] | None = None,
        purpose: Purpose = Purpose.CONTRACT_SMOKE,
        target: str | None = None,
    ) -> CollectionRun:
        """Ingest downloaded provider files without pretending they were live calls."""
        if not self.registry.supports_file(source_id):
            raise ValueError(
                f"{source_id} is not configured for provider-file ingestion; use validate-file for a fixture."
            )
        spec = self.registry.get(source_id)
        allowed = {f".{str(value).lower()}" for value in spec.get("file_formats", [])}
        unexpected = [
            str(path)
            for path in file_paths
            if Path(path).suffix.lower() not in allowed
        ]
        if unexpected:
            raise ValueError(
                f"Unsupported file extension for {source_id}; allowed={sorted(allowed)}, "
                f"inputs={unexpected}"
            )
        return self._collect_local_files(
            source_id,
            file_paths,
            params=params,
            purpose=purpose,
            target=target,
            evidence_mode="FILE",
        )

    def _collect_local_files(
        self,
        source_id: str,
        fixture_paths: list[str | Path],
        *,
        params: dict[str, Any] | None,
        purpose: Purpose,
        target: str | None,
        evidence_mode: str,
    ) -> CollectionRun:
        if not fixture_paths:
            raise ValueError("At least one fixture path is required")
        spec = self.registry.get(source_id)
        credential_env = spec.get("auth", {}).get("env")
        secrets = [str(os.environ.get(credential_env, ""))] if credential_env else []
        exchanges = [
            self._fixture_exchange(
                source_id,
                Path(fixture_path),
                params or {},
                secrets=secrets,
                evidence_mode=evidence_mode,
                sensitive_params=spec.get("sensitive_params", []),
            )
            for fixture_path in fixture_paths
        ]
        run = self._new_run(
            source_id,
            params or {},
            target,
            started_at=exchanges[0].requested_at,
            ended_at=exchanges[-1].body_completed_at,
            secrets=secrets,
            evidence_mode=evidence_mode,
            sensitive_params=spec.get("sensitive_params", []),
            sensitive_target=bool(spec.get("sensitive_target", False)),
        )
        policy = self.registry.policy(source_id)
        self.repository.begin_run(
            run, evidence_mode, COLLECTOR_VERSION, secrets=secrets
        )
        log_event(
            LOGGER,
            logging.INFO,
            "collection.started",
            "local provider file validation started",
            secrets=secrets,
            run_id=run.run_id,
            source_id=source_id,
            purpose=purpose.value,
            evidence_mode=evidence_mode,
            file_count=len(exchanges),
        )
        phase = "file_parse"
        try:
            for file_index, exchange in enumerate(exchanges, start=1):
                batch = parse_exchange(spec, exchange.body, exchange.content_type)
                item = CollectionItem(exchange=exchange, batch=batch)
                run.items.append(item)
                phase = "persistence"
                self.repository.save_item(run, item, spec, policy)
                log_event(
                    LOGGER,
                    logging.WARNING if batch.parse_error else logging.INFO,
                    "file.parsed",
                    "provider file parsed",
                    secrets=secrets,
                    run_id=run.run_id,
                    source_id=source_id,
                    file_index=file_index,
                    exchange_id=exchange.exchange_id,
                    response_format=batch.response_format,
                    row_count=len(batch.rows),
                    body_bytes=exchange.body_bytes,
                    parse_error_type=(batch.parse_error or "").split(":", 1)[0] or None,
                )
        except Exception as exc:
            self._mark_failed(run, exc, secrets)
            self._log_failure(run, exc, phase, secrets)
        run.ended_at = exchanges[-1].body_completed_at
        self._finalize_and_report(
            run,
            spec,
            purpose,
            policy,
            evidence_mode=evidence_mode,
            secrets=secrets,
        )
        log_event(
            LOGGER,
            logging.ERROR if run.failure_code else logging.INFO,
            "collection.finished",
            "local provider file validation finished",
            secrets=secrets,
            run_id=run.run_id,
            source_id=source_id,
            evidence_mode=evidence_mode,
            status="FAILED" if run.failure_code else "COMPLETE",
            failure_code=run.failure_code,
            observation_count=len(run.items),
            row_count=sum(len(item.batch.rows) for item in run.items),
            verdict=run.report.verdict.value,
        )
        return run

    def _finalize_and_report(
        self,
        run: CollectionRun,
        spec: Any,
        purpose: Purpose,
        policy: dict[str, Any],
        *,
        evidence_mode: str,
        secrets: list[str],
    ) -> None:
        """Persist terminal state and the validation report as one observable phase.

        SQLite/file failures here must not leave a run looking successful.  We
        mark the in-memory run failed, emit a phase-specific event, and make a
        best-effort second terminal-state update before re-raising to the CLI.
        """
        phase = "run_finalize"
        try:
            self.repository.finish_run(run)
            phase = "validation"
            run.report = self.validator.evaluate(
                run, spec, purpose, policy, evidence_mode=evidence_mode
            )
            phase = "report_persistence"
            self.repository.save_report(run.report)
        except Exception as exc:
            self._mark_failed(run, exc, secrets)
            log_event(
                LOGGER,
                logging.ERROR,
                "collection.finalization_failed",
                "terminal state or validation report could not be persisted",
                secrets=secrets,
                run_id=run.run_id,
                source_id=run.source_id,
                phase=phase,
                failure_code=run.failure_code,
                failure_message=run.failure_message,
                error_type=type(exc).__name__,
            )
            self._log_failure(run, exc, phase, secrets)
            try:
                # If report persistence failed after a COMPLETE update, correct
                # the collection_run row to FAILED.  If the DB itself is down,
                # the recovery failure below makes that limitation explicit.
                self.repository.finish_run(run)
            except Exception as recovery_exc:
                log_event(
                    LOGGER,
                    logging.ERROR,
                    "collection.failure_state_persistence_failed",
                    "failed run state could not be persisted",
                    secrets=secrets,
                    run_id=run.run_id,
                    source_id=run.source_id,
                    phase=phase,
                    error_type=type(recovery_exc).__name__,
                )
            raise

    @staticmethod
    def _mark_failed(
        run: CollectionRun, exc: Exception, secrets: list[str]
    ) -> None:
        run.failure_code = type(exc).__name__.upper()
        message = redact_text(str(exc), secrets).strip()
        run.failure_message = message or "Collection stopped before completion."

    @staticmethod
    def _log_failure(
        run: CollectionRun,
        exc: Exception,
        phase: str,
        secrets: list[str],
    ) -> None:
        """Log a concise error plus a redacted DEBUG traceback.

        Calling logger.exception directly can append an unredacted exception
        string after formatter output, so traceback text is sanitized first.
        """
        log_event(
            LOGGER,
            logging.ERROR,
            "collection.failed",
            "collection phase failed",
            secrets=secrets,
            run_id=run.run_id,
            source_id=run.source_id,
            phase=phase,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
            error_type=type(exc).__name__,
        )
        log_event(
            LOGGER,
            logging.DEBUG,
            "collection.traceback",
            "redacted traceback for debugging",
            secrets=secrets,
            run_id=run.run_id,
            source_id=run.source_id,
            phase=phase,
            traceback=redact_text(traceback.format_exc(), secrets),
        )

    def _fetch_and_parse(
        self,
        spec: Any,
        params: dict[str, Any],
        *,
        allow_insecure_http: bool,
        context: dict[str, Any] | None = None,
        secrets: list[str] | None = None,
    ) -> tuple[HttpExchange, Any]:
        total_attempts = 0
        retries = 0
        first_requested_at: str | None = None
        retry_history: list[dict[str, Any]] = []
        while True:
            fetch_kwargs: dict[str, Any] = {
                "allow_insecure_http": allow_insecure_http
            }
            # Older test/embedding clients predate correlation logging.  Pass
            # context when supported without forcing every adapter to change.
            fetch_parameters = inspect.signature(self.http_client.fetch).parameters
            if "context" in fetch_parameters or any(
                value.kind == inspect.Parameter.VAR_KEYWORD
                for value in fetch_parameters.values()
            ):
                fetch_kwargs["context"] = context
            exchange = self.http_client.fetch(spec, params, **fetch_kwargs)
            total_attempts += exchange.attempts
            first_requested_at = first_requested_at or exchange.requested_at
            batch = parse_exchange(spec, exchange.body, exchange.content_type)
            log_event(
                LOGGER,
                logging.WARNING if batch.parse_error else logging.INFO,
                "response.parsed",
                "provider response parsed",
                secrets=secrets or [],
                **(context or {}),
                source_id=spec.source_id,
                exchange_id=exchange.exchange_id,
                http_status=exchange.http_status,
                business_code=batch.business_code,
                response_format=batch.response_format,
                row_count=len(batch.rows),
                declared_count=batch.declared_count,
                parse_error_type=(batch.parse_error or "").split(":", 1)[0] or None,
            )
            retryable = {
                str(code) for code in spec.get("business", {}).get("retryable_codes", [])
            }
            if batch.business_code not in retryable or retries >= 1:
                if first_requested_at != exchange.requested_at:
                    first = datetime.fromisoformat(first_requested_at)
                    completed = datetime.fromisoformat(exchange.body_completed_at)
                    exchange.requested_at = first_requested_at
                    exchange.elapsed_ms = max(
                        0.0, (completed - first).total_seconds() * 1000
                    )
                exchange.retry_history = retry_history + exchange.retry_history
                exchange.attempts = total_attempts
                return exchange, batch
            retry_history.extend(exchange.retry_history)
            retry_history.append(
                {
                    "attempt": total_attempts,
                    "requested_at": exchange.requested_at,
                    "headers_received_at": exchange.headers_received_at,
                    "body_completed_at": exchange.body_completed_at,
                    "http_status": exchange.http_status,
                    "transport_error": exchange.transport_error,
                    "body_sha256": exchange.body_sha256,
                    "body_bytes": exchange.body_bytes,
                    "business_code": batch.business_code,
                    "business_message": redact_text(
                        batch.business_message or "", secrets or []
                    ),
                }
            )
            retries += 1
            log_event(
                LOGGER,
                logging.INFO,
                "business.retry_scheduled",
                "retryable provider business code will be retried once",
                secrets=secrets or [],
                **(context or {}),
                source_id=spec.source_id,
                business_code=batch.business_code,
                business_retry_index=retries,
            )
            self.sleeper(0.5)

    @staticmethod
    def _new_run(
        source_id: str,
        params: dict[str, Any],
        target: str | None,
        *,
        started_at: str | None = None,
        ended_at: str | None = None,
        secrets: list[str] | None = None,
        evidence_mode: str = "LIVE",
        sensitive_params: list[str] | None = None,
        sensitive_target: bool = False,
    ) -> CollectionRun:
        started = started_at or _now_iso()
        secret_values = secrets or []
        raw_target = target or CollectionService._derive_target(params)
        if sensitive_target:
            safe_target = "SENSITIVE_TARGET_SHA256:" + sha256_bytes(
                redact_text(raw_target, secret_values).encode("utf-8")
            )
        else:
            safe_target = redact_text(raw_target, secret_values)
        return CollectionRun(
            run_id=uuid.uuid4().hex,
            source_id=source_id,
            target=safe_target,
            started_at=started,
            ended_at=ended_at or started,
            params=redact_mapping(params, secret_values, sensitive_params),
            items=[],
            evidence_mode=evidence_mode,
        )

    @staticmethod
    def _derive_target(params: dict[str, Any]) -> str:
        ordered = (
            "busRouteId",
            "routeId",
            "station",
            "line",
            "link_id",
            "stdrDe",
            "stndDt",
            "stnIds",
            "USE_YM",
            "stSrch",
        )
        values = [f"{key}={params[key]}" for key in ordered if params.get(key) not in (None, "")]
        if params.get("nx") not in (None, "") and params.get("ny") not in (None, ""):
            values.append(f"grid={params['nx']},{params['ny']}")
        if all(params.get(key) not in (None, "") for key in ("startX", "startY", "endX", "endY")):
            values.append(
                "route_coords="
                + ",".join(
                    str(params[key]) for key in ("startX", "startY", "endX", "endY")
                )
            )
        return ";".join(values) if values else "ALL"

    @staticmethod
    def _fixture_exchange(
        source_id: str,
        fixture_path: Path,
        params: dict[str, Any],
        *,
        secrets: list[str] | None = None,
        evidence_mode: str = "FIXTURE",
        sensitive_params: list[str] | None = None,
    ) -> HttpExchange:
        if not fixture_path.is_file():
            raise ValueError(f"Input file does not exist or is not a file: {fixture_path}")
        raw = fixture_path.read_bytes()
        envelope: dict[str, Any] | None = None
        if fixture_path.suffix.lower() == ".json":
            try:
                candidate = json.loads(raw.decode("utf-8-sig"))
                if isinstance(candidate, dict) and (
                    candidate.get("fixture_version") or "raw_payload" in candidate
                ):
                    envelope = candidate
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        if envelope:
            body_value = envelope.get("body", envelope.get("raw_payload", ""))
            if isinstance(body_value, (dict, list)):
                body = json.dumps(body_value, ensure_ascii=False).encode("utf-8")
            else:
                body = str(body_value).encode("utf-8")
            requested = str(envelope.get("requested_at", "2026-08-25T00:00:00+00:00"))
            received_fallback = envelope.get("received_at")
            headers = str(
                envelope.get(
                    "headers_received_at",
                    received_fallback or "2026-08-25T00:00:00.050000+00:00",
                )
            )
            completed = str(
                envelope.get(
                    "body_completed_at",
                    received_fallback or "2026-08-25T00:00:00.100000+00:00",
                )
            )
            status = int(envelope.get("http_status", 200))
            default_content_type = (
                "application/xml"
                if isinstance(body_value, str) and body_value.lstrip().startswith("<")
                else "application/json"
            )
            content_type = str(envelope.get("content_type", default_content_type))
            transport_error = envelope.get("transport_error")
        else:
            body = raw
            if evidence_mode == "FIXTURE":
                requested = "2026-08-25T00:00:00+00:00"
                headers = "2026-08-25T00:00:00.050000+00:00"
                completed = "2026-08-25T00:00:00.100000+00:00"
            else:
                requested = _now_iso()
                headers = requested
                completed = _now_iso()
            status = 200
            content_types = {
                ".xml": "application/xml",
                ".json": "application/json",
                ".csv": "text/csv",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            content_type = content_types.get(
                fixture_path.suffix.lower(), "application/octet-stream"
            )
            transport_error = None
        return HttpExchange(
            exchange_id=uuid.uuid4().hex,
            source_id=source_id,
            safe_endpoint=f"{evidence_mode.lower()}://{source_id}/{redact_text(fixture_path.name, secrets or [])}",
            safe_params=redact_mapping(params, secrets or [], sensitive_params),
            requested_at=requested,
            headers_received_at=headers,
            body_completed_at=completed,
            http_status=status,
            content_type=content_type,
            body=body,
            body_sha256=sha256_bytes(body),
            body_bytes=len(body),
            attempts=1,
            elapsed_ms=max(
                0.0,
                (
                    datetime.fromisoformat(completed)
                    - datetime.fromisoformat(requested)
                ).total_seconds()
                * 1000,
            ),
            transport_error=str(transport_error) if transport_error else None,
        )
