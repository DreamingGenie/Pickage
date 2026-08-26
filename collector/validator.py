from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .config import SourceSpec
from .contracts import (
    AggregateVerdict,
    CheckStatus,
    CollectionRun,
    Purpose,
    PurposeEligibility,
    QualityCheck,
    ValidationReport,
    ValidationScope,
)
from .logging_utils import LOGGER, log_event


KST = timezone(timedelta(hours=9), name="Asia/Seoul")
EMPTY_VALUES = (None, "")


def _value_ci(row: dict[str, Any], names: Iterable[str]) -> Any:
    lowered = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(str(name).casefold())
        if value not in EMPTY_VALUES:
            return value
    return None


def canonical_value(spec: SourceSpec, row: dict[str, Any], field: str) -> Any:
    return _value_ci(row, spec.get("aliases", {}).get(field, [field]))


def _parse_datetime(raw: Any, formats: list[str]) -> datetime | None:
    if raw in EMPTY_VALUES:
        return None
    if isinstance(raw, datetime):
        value = raw
    else:
        text = str(raw).strip()
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            value = None
            for fmt in formats:
                try:
                    value = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if value is None:
                return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(timezone.utc)


def source_time(spec: SourceSpec, row: dict[str, Any]) -> datetime | None:
    raw = canonical_value(spec, row, "source_time")
    if raw not in EMPTY_VALUES:
        return _parse_datetime(raw, spec.get("source_time_formats", []))
    base_date = canonical_value(spec, row, "base_date")
    base_time = canonical_value(spec, row, "base_time")
    if base_date not in EMPTY_VALUES and base_time not in EMPTY_VALUES:
        digits = f"{base_date}{str(base_time).zfill(4)}"
        return _parse_datetime(digits, ["%Y%m%d%H%M"])
    return None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _check(
    code: str,
    name: str,
    status: CheckStatus,
    message: str,
    **metrics: Any,
) -> QualityCheck:
    return QualityCheck(code=code, name=name, status=status, message=message, metrics=metrics)


class Validator:
    def evaluate(
        self,
        run: CollectionRun,
        spec: SourceSpec,
        purpose: Purpose,
        policy: dict[str, Any],
        *,
        evidence_mode: str,
    ) -> ValidationReport:
        rows = [row for item in run.items for row in item.batch.rows]
        checks: list[QualityCheck] = []
        checks.append(self._collection_check(run))
        checks.append(self._transport_check(run, evidence_mode))
        checks.append(self._timing_check(run))
        checks.append(self._business_check(run, spec, evidence_mode))
        checks.append(self._parse_check(run))
        checks.append(self._row_check(rows))
        checks.append(self._schema_check(rows, spec))
        checks.append(self._wide_schema_check(rows, spec))
        checks.append(self._identity_check(rows, spec))
        checks.append(self._mapping_check(spec))
        checks.append(self._target_check(rows, run.params, spec))
        checks.append(self._declared_count_check(run, spec))

        time_check, time_metrics = self._source_time_check(run, rows, spec)
        checks.append(time_check)
        duplicate_check, duplicate_metrics = self._duplicate_check(run, rows, spec)
        checks.append(duplicate_check)
        domain_check, domain_metrics = self._domain_check(rows, spec)
        checks.append(domain_check)
        transition_check, transition_metrics = self._transition_check(run, spec)
        checks.append(transition_check)
        checks.append(self._policy_check(policy))

        metrics = {
            "observation_count": len(run.items),
            "row_count": len(rows),
            "successful_http_count": sum(
                1
                for item in run.items
                if item.exchange.http_status is not None
                and 200 <= item.exchange.http_status < 300
            ),
            **time_metrics,
            **duplicate_metrics,
            **domain_metrics,
            **transition_metrics,
        }
        purposes = {Purpose.CONTRACT_SMOKE, Purpose.STRUCTURE, purpose}
        for configured in spec.get("purposes", []):
            purposes.add(Purpose(configured))
        eligibility = [
            self._eligibility(candidate, checks, metrics, spec, policy, evidence_mode)
            for candidate in sorted(purposes, key=lambda value: value.value)
        ]
        selected = next(item for item in eligibility if item.purpose == purpose)
        limitations = self._limitations(run, spec, policy, evidence_mode, metrics)
        scope = ValidationScope(
            source_id=spec.source_id,
            provider=str(spec.get("provider", "UNKNOWN")),
            endpoint=str(
                spec.get("file_source_url", "LOCAL_PROVIDER_FILE")
                if evidence_mode == "FILE"
                else spec.get("endpoint_template", "UNKNOWN")
            ),
            purpose=purpose,
            target=run.target,
            window_started_at=run.started_at,
            window_ended_at=run.ended_at,
            policy_version="sha256:"
            + hashlib.sha256(
                json.dumps(policy, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            profile_version="PROFILED" if spec.get("profiled", False) else "UNPROFILED",
            evidence_mode=evidence_mode,
        )
        manifest_payload = {
            "scope": asdict(scope),
            "checks": [asdict(check) for check in checks],
            "metrics": metrics,
            "eligibility": [asdict(item) for item in eligibility],
        }
        manifest = hashlib.sha256(
            json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        report = ValidationReport(
            report_id=uuid.uuid4().hex,
            run_id=run.run_id,
            scope=scope,
            verdict=selected.verdict,
            checks=checks,
            eligibility=eligibility,
            metrics=metrics,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            limitations=limitations,
            manifest_sha256=manifest,
        )
        failed_codes = [check.code for check in checks if check.status == CheckStatus.FAIL]
        warning_codes = [
            check.code
            for check in checks
            if check.status in {CheckStatus.WARN, CheckStatus.NOT_EVALUATED}
        ]
        log_event(
            LOGGER,
            logging.WARNING if report.verdict == AggregateVerdict.UNUSABLE else logging.INFO,
            "validation.finished",
            "purpose-scoped validation completed",
            run_id=run.run_id,
            source_id=run.source_id,
            purpose=purpose.value,
            evidence_mode=evidence_mode,
            verdict=report.verdict.value,
            row_count=len(rows),
            observation_count=len(run.items),
            failed_check_codes=failed_codes,
            warning_check_codes=warning_codes,
            eligibility_reason_codes=selected.reason_codes,
        )
        return report

    @staticmethod
    def _collection_check(run: CollectionRun) -> QualityCheck:
        if run.failure_code:
            return _check(
                "DQ-COLLECTION",
                "collection_completion",
                CheckStatus.FAIL,
                "Collection stopped before the requested window completed.",
                failure_code=run.failure_code,
                failure_message=run.failure_message,
                completed_observations=len(run.items),
            )
        return _check(
            "DQ-COLLECTION",
            "collection_completion",
            CheckStatus.PASS,
            "The requested collection window completed.",
            completed_observations=len(run.items),
        )

    @staticmethod
    def _transport_check(run: CollectionRun, evidence_mode: str) -> QualityCheck:
        good = [
            item
            for item in run.items
            if item.exchange.http_status is not None
            and 200 <= item.exchange.http_status < 300
            and item.exchange.transport_error is None
        ]
        recovered_retries = sum(len(item.exchange.retry_history) for item in run.items)
        if len(good) == len(run.items) and good and not recovered_retries:
            message = (
                "All local provider files were read successfully."
                if evidence_mode == "FILE"
                else "All exchanges returned HTTP 2xx without retry."
            )
            return _check("DQ-TRANSPORT", "file_input" if evidence_mode == "FILE" else "transport", CheckStatus.PASS, message, success=len(good), total=len(run.items), recovered_retries=0)
        if len(good) == len(run.items) and good:
            return _check("DQ-TRANSPORT", "transport", CheckStatus.WARN, "All logical exchanges recovered, but one or more transport/business retries were required.", success=len(good), total=len(run.items), recovered_retries=recovered_retries)
        if good:
            return _check("DQ-TRANSPORT", "transport", CheckStatus.WARN, "Only part of the collection window returned HTTP 2xx.", success=len(good), total=len(run.items))
        return _check("DQ-TRANSPORT", "transport", CheckStatus.FAIL, "No exchange returned a usable HTTP response.", success=0, total=len(run.items))

    @staticmethod
    def _timing_check(run: CollectionRun) -> QualityCheck:
        invalid = 0
        missing_headers = 0
        latencies = []
        for item in run.items:
            exchange = item.exchange
            requested = _parse_datetime(exchange.requested_at, [])
            completed = _parse_datetime(exchange.body_completed_at, [])
            headers = _parse_datetime(exchange.headers_received_at, [])
            if not requested or not completed or completed < requested:
                invalid += 1
                continue
            if headers is None:
                missing_headers += 1
            elif headers < requested or completed < headers:
                invalid += 1
            latencies.append(exchange.elapsed_ms)
        if invalid:
            return _check("DQ-021", "collector_timestamps", CheckStatus.FAIL, "Request/header/body timing order is invalid.", invalid=invalid, missing_headers=missing_headers)
        status = CheckStatus.WARN if missing_headers else CheckStatus.PASS
        return _check("DQ-021", "collector_timestamps", status, "Collector boundary timestamps are ordered." if not missing_headers else "Header time is absent on failed exchanges.", invalid=0, missing_headers=missing_headers, min_elapsed_ms=min(latencies, default=None), max_elapsed_ms=max(latencies, default=None))

    @staticmethod
    def _business_check(
        run: CollectionRun, spec: SourceSpec, evidence_mode: str
    ) -> QualityCheck:
        business = spec.get("business", {})
        success = {str(code) for code in business.get("success_codes", [])}
        empty = {str(code) for code in business.get("empty_codes", [])}
        codes = [item.batch.business_code for item in run.items]
        if evidence_mode == "FILE" and all(code is None for code in codes):
            return _check(
                "DQ-014",
                "provider_business_status",
                CheckStatus.NOT_EVALUATED,
                "Downloaded files do not contain an API business envelope.",
                codes=codes,
            )
        recovered_codes = [
            history.get("business_code")
            for item in run.items
            for history in item.exchange.retry_history
            if history.get("business_code") is not None
        ]
        failures = [code for code in codes if code is not None and code not in success and code not in empty]
        if failures:
            return _check("DQ-014", "provider_business_status", CheckStatus.FAIL, "Provider business status indicates an error even if HTTP was 2xx.", codes=codes, failing_codes=failures)
        unknown = sum(1 for code in codes if code is None)
        if unknown:
            status = CheckStatus.WARN if any(item.batch.rows for item in run.items) else CheckStatus.FAIL
            return _check("DQ-014", "provider_business_status", status, "Provider business code was not found in every response.", codes=codes, missing=unknown)
        recovered_failures = [
            code
            for code in recovered_codes
            if code not in success and code not in empty
        ]
        if recovered_failures:
            return _check("DQ-014", "provider_business_status", CheckStatus.WARN, "The final provider status succeeded after retryable business errors.", codes=codes, recovered_codes=recovered_codes)
        return _check("DQ-014", "provider_business_status", CheckStatus.PASS, "Provider business status is successful or an explicit no-data code.", codes=codes, recovered_codes=recovered_codes)

    @staticmethod
    def _parse_check(run: CollectionRun) -> QualityCheck:
        errors = [item.batch.parse_error for item in run.items if item.batch.parse_error]
        if errors:
            return _check("DQ-PARSE", "response_parse", CheckStatus.FAIL, "At least one response could not be parsed.", errors=errors)
        return _check("DQ-PARSE", "response_parse", CheckStatus.PASS, "All response bodies were parsed.", formats=[item.batch.response_format for item in run.items])

    @staticmethod
    def _row_check(rows: list[dict[str, Any]]) -> QualityCheck:
        if rows:
            return _check("DQ-ROWS", "row_presence", CheckStatus.PASS, "At least one provider row was extracted.", row_count=len(rows))
        return _check("DQ-ROWS", "row_presence", CheckStatus.NOT_EVALUATED, "The response had no data rows; field usability cannot be evaluated.", row_count=0)

    @staticmethod
    def _schema_check(rows: list[dict[str, Any]], spec: SourceSpec) -> QualityCheck:
        required = spec.get("required_fields", [])
        if not rows:
            return _check("DQ-SCHEMA", "required_field_coverage", CheckStatus.NOT_EVALUATED, "No rows were available for schema validation.", required_fields=required)
        coverage = {}
        completely_missing = []
        partially_missing = []
        for field in required:
            present = sum(1 for row in rows if canonical_value(spec, row, field) not in EMPTY_VALUES)
            coverage[field] = {"present": present, "total": len(rows), "ratio": _ratio(present, len(rows))}
            if present == 0:
                completely_missing.append(field)
            elif present < len(rows):
                partially_missing.append(field)
        if completely_missing:
            return _check("DQ-SCHEMA", "required_field_coverage", CheckStatus.FAIL, "One or more core fields are absent from all rows.", coverage=coverage, missing=completely_missing)
        if partially_missing:
            return _check("DQ-SCHEMA", "required_field_coverage", CheckStatus.WARN, "Core fields are missing in part of the response.", coverage=coverage, partial=partially_missing)
        return _check("DQ-SCHEMA", "required_field_coverage", CheckStatus.PASS, "All core fields are populated in every row.", coverage=coverage)

    @staticmethod
    def _wide_schema_check(rows: list[dict[str, Any]], spec: SourceSpec) -> QualityCheck:
        """Validate repeated time-bucket columns by name, never by position.

        Several Seoul files wrap midnight or contain 39/48 measurement columns.
        A total column count cannot detect a shifted or missing time bucket, so
        each configured regular expression is evaluated against every row.
        """
        contracts = spec.get("wide_field_contracts", [])
        if not contracts:
            return _check(
                "DQ-WIDE-SCHEMA",
                "repeated_field_contract",
                CheckStatus.NOT_EVALUATED,
                "This source has no repeated-field contract.",
            )
        if not rows:
            return _check(
                "DQ-WIDE-SCHEMA",
                "repeated_field_contract",
                CheckStatus.NOT_EVALUATED,
                "No rows were available for repeated-field validation.",
            )
        results: list[dict[str, Any]] = []
        mismatch_count = 0
        for contract in contracts:
            pattern = re.compile(str(contract["pattern"]), re.IGNORECASE)
            expected = int(contract["expected"])
            counts = [sum(1 for key in row if pattern.fullmatch(str(key))) for row in rows]
            mismatches = sum(1 for count in counts if count != expected)
            mismatch_count += mismatches
            results.append(
                {
                    "name": contract.get("name", "unnamed"),
                    "expected": expected,
                    "minimum_observed": min(counts),
                    "maximum_observed": max(counts),
                    "mismatched_rows": mismatches,
                }
            )
        status = CheckStatus.FAIL if mismatch_count else CheckStatus.PASS
        return _check(
            "DQ-WIDE-SCHEMA",
            "repeated_field_contract",
            status,
            "Repeated time-bucket columns were matched by header name.",
            contracts=results,
            mismatched_rows=mismatch_count,
        )

    @staticmethod
    def _identity_check(rows: list[dict[str, Any]], spec: SourceSpec) -> QualityCheck:
        fields = spec.get("identity_fields", [])
        if not rows or not fields:
            return _check("DQ-IDENTITY", "identity_coverage", CheckStatus.NOT_EVALUATED, "Identity coverage is not evaluable for this response.", fields=fields)
        identity_mode = spec.get("identity_mode", "ALL")
        predicate = any if identity_mode == "ANY" else all
        complete = sum(
            1
            for row in rows
            if predicate(canonical_value(spec, row, field) not in EMPTY_VALUES for field in fields)
        )
        ratio = _ratio(complete, len(rows))
        if complete == 0:
            return _check("DQ-IDENTITY", "identity_coverage", CheckStatus.FAIL, "No row has the required composite identity.", complete=complete, total=len(rows), ratio=ratio)
        status = CheckStatus.PASS if complete == len(rows) else CheckStatus.WARN
        return _check("DQ-IDENTITY", "identity_coverage", status, "Composite identity coverage was measured.", complete=complete, total=len(rows), ratio=ratio, fields=fields)

    @staticmethod
    def _mapping_check(spec: SourceSpec) -> QualityCheck:
        mapping_status = str(spec.get("mapping_status", "UNVERIFIED"))
        if mapping_status == "VERIFIED":
            return _check("DQ-006", "internal_id_mapping", CheckStatus.PASS, "A versioned internal ID or spatial mapping is configured.", mapping_status=mapping_status)
        return _check("DQ-006", "internal_id_mapping", CheckStatus.NOT_EVALUATED, "Internal transit/link/weather-grid mapping has not been verified for model use.", mapping_status=mapping_status)

    @staticmethod
    def _target_check(rows: list[dict[str, Any]], params: dict[str, Any], spec: SourceSpec) -> QualityCheck:
        comparisons = []
        if params.get("busRouteId"):
            comparisons.append(("route_id", str(params["busRouteId"])))
        if params.get("link_id"):
            comparisons.append(("link_id", str(params["link_id"])))
        if params.get("routeId"):
            comparisons.append(("route_id", str(params["routeId"])))
        if params.get("station"):
            comparisons.append(("station_name", str(params["station"])))
        if not comparisons or not rows:
            return _check("DQ-TARGET", "requested_target_match", CheckStatus.NOT_EVALUATED, "No comparable target field was available.", comparisons=comparisons)
        mismatch = 0
        comparable = 0
        for field, expected in comparisons:
            for row in rows:
                actual = canonical_value(spec, row, field)
                if actual not in EMPTY_VALUES:
                    comparable += 1
                    if str(actual) != expected:
                        mismatch += 1
        if comparable == 0:
            return _check("DQ-TARGET", "requested_target_match", CheckStatus.NOT_EVALUATED, "Response did not expose a comparable target field.", comparisons=comparisons)
        status = CheckStatus.FAIL if mismatch else CheckStatus.PASS
        return _check("DQ-TARGET", "requested_target_match", status, "Requested and observed target values were compared.", comparable=comparable, mismatch=mismatch, comparisons=comparisons)

    @staticmethod
    def _declared_count_check(run: CollectionRun, spec: SourceSpec) -> QualityCheck:
        pairs = [(item.batch.declared_count, len(item.batch.rows)) for item in run.items if item.batch.declared_count is not None]
        if not pairs:
            return _check("DQ-COUNT", "declared_vs_parsed_count", CheckStatus.NOT_EVALUATED, "No declared count was available.")
        if not spec.get("expect_declared_count_equals_rows", False):
            return _check("DQ-COUNT", "declared_vs_parsed_count", CheckStatus.PASS, "Declared total count was recorded; equality is not required for paged responses.", pairs=pairs)
        mismatches = [(declared, parsed) for declared, parsed in pairs if declared != parsed]
        status = CheckStatus.WARN if mismatches else CheckStatus.PASS
        return _check("DQ-COUNT", "declared_vs_parsed_count", status, "Declared and parsed counts were compared for an all-rows response.", pairs=pairs, mismatches=mismatches)

    @staticmethod
    def _source_time_check(run: CollectionRun, rows: list[dict[str, Any]], spec: SourceSpec) -> tuple[QualityCheck, dict[str, Any]]:
        expects_time = "source_time" in spec.get("aliases", {}) or (
            "base_date" in spec.get("aliases", {}) and "base_time" in spec.get("aliases", {})
        )
        if not rows or not expects_time:
            return (
                _check("DQ-001", "source_time", CheckStatus.NOT_EVALUATED, "Provider source time is unavailable or there are no rows."),
                {"source_time_count": 0, "source_time_missing": len(rows), "source_time_span_seconds": None, "max_source_lag_seconds": None, "stale_row_count": None, "future_row_count": None, "out_of_order_count": None},
            )
        row_exchanges = [
            (row, _parse_datetime(item.exchange.body_completed_at, []))
            for item in run.items
            for row in item.batch.rows
        ]
        parsed_times = [source_time(spec, row) for row, _ in row_exchanges]
        valid = [value for value in parsed_times if value is not None]
        missing = len(rows) - len(valid)
        future = sum(
            1
            for (_, completed), value in zip(row_exchanges, parsed_times)
            if value is not None
            and completed is not None
            and value > completed + timedelta(minutes=5)
        )
        lags = [
            (completed - value).total_seconds()
            for (_, completed), value in zip(row_exchanges, parsed_times)
            if value is not None and completed is not None
        ]
        freshness = spec.get("freshness_seconds")
        stale = sum(1 for lag in lags if freshness is not None and lag > freshness)
        span = (max(valid) - min(valid)).total_seconds() if valid else None
        out_of_order = 0
        by_identity: dict[tuple[str, ...], datetime] = {}
        identity_fields = spec.get("identity_fields", [])
        for row, observed_at in zip(rows, parsed_times):
            if observed_at is None:
                continue
            key = tuple(str(canonical_value(spec, row, field) or "") for field in identity_fields)
            previous = by_identity.get(key)
            if previous and observed_at < previous:
                out_of_order += 1
            by_identity[key] = observed_at
        metrics = {
            "source_time_count": len(valid),
            "source_time_missing": missing,
            "source_time_span_seconds": span,
            "max_source_lag_seconds": max(lags, default=None),
            "stale_row_count": stale if freshness is not None else None,
            "future_row_count": future,
            "out_of_order_count": out_of_order,
        }
        if not valid or future:
            return _check("DQ-001", "source_time", CheckStatus.FAIL, "Source time is absent from every row or is implausibly in the future.", **metrics), metrics
        if missing or stale or out_of_order:
            return _check("DQ-001", "source_time", CheckStatus.WARN, "Source time has missing, stale, or out-of-order rows. Freshness threshold remains a profile candidate until approved.", **metrics), metrics
        return _check("DQ-001", "source_time", CheckStatus.PASS, "Source time is present and ordered for the tested window.", **metrics), metrics

    @staticmethod
    def _duplicate_check(run: CollectionRun, rows: list[dict[str, Any]], spec: SourceSpec) -> tuple[QualityCheck, dict[str, Any]]:
        body_hashes = [item.exchange.body_sha256 for item in run.items]
        duplicate_bodies = len(body_hashes) - len(set(body_hashes))
        fields = spec.get("natural_key", [])
        seen: dict[tuple[str, ...], str] = {}
        duplicate_rows = 0
        revisions = 0
        for row in rows:
            key = tuple(str(canonical_value(spec, row, field) or "") for field in fields)
            fingerprint = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            if key in seen:
                if seen[key] == fingerprint:
                    duplicate_rows += 1
                else:
                    revisions += 1
            else:
                seen[key] = fingerprint
        metrics = {
            "duplicate_body_count": duplicate_bodies,
            "duplicate_row_count": duplicate_rows,
            "revision_count": revisions,
            "effective_event_count": len(seen),
            "raw_row_count": len(rows),
        }
        status = CheckStatus.WARN if duplicate_bodies or duplicate_rows or revisions else CheckStatus.PASS
        return _check("DQ-002", "deduplication", status, "Body repetition, logical duplicates, and revisions are reported separately.", **metrics), metrics

    @staticmethod
    def _domain_check(rows: list[dict[str, Any]], spec: SourceSpec) -> tuple[QualityCheck, dict[str, Any]]:
        invalid_numeric = 0
        unknown_enum = 0
        eta_zero = 0
        eta_count = 0
        sentinel_count = 0
        invalid_format = 0
        configured_ranges = spec.get("numeric_ranges", {})
        configured_enums = spec.get("allowed_values", {})
        configured_formats = {
            field: re.compile(str(pattern))
            for field, pattern in spec.get("format_patterns", {}).items()
        }
        wide_contracts = [
            (re.compile(str(item["pattern"]), re.IGNORECASE), item)
            for item in spec.get("wide_field_contracts", [])
        ]
        for row in rows:
            for field in ("speed", "travel_time", "average_speed", "eta_seconds"):
                raw = canonical_value(spec, row, field)
                if raw in EMPTY_VALUES:
                    continue
                try:
                    number = float(str(raw))
                    if not math.isfinite(number) or number < 0:
                        invalid_numeric += 1
                    if field == "eta_seconds":
                        eta_count += 1
                        if number == 0:
                            eta_zero += 1
                except ValueError:
                    invalid_numeric += 1
            for field, bounds in configured_ranges.items():
                raw = canonical_value(spec, row, field)
                if raw in EMPTY_VALUES:
                    continue
                try:
                    number = float(str(raw))
                    minimum = bounds.get("min")
                    maximum = bounds.get("max")
                    if (
                        not math.isfinite(number)
                        or (minimum is not None and number < float(minimum))
                        or (maximum is not None and number > float(maximum))
                    ):
                        invalid_numeric += 1
                except (TypeError, ValueError):
                    invalid_numeric += 1
            for field, allowed in configured_enums.items():
                raw = canonical_value(spec, row, field)
                if raw not in EMPTY_VALUES and str(raw) not in {str(item) for item in allowed}:
                    unknown_enum += 1
            for field, pattern in configured_formats.items():
                raw = canonical_value(spec, row, field)
                if raw not in EMPTY_VALUES and not pattern.fullmatch(str(raw).strip()):
                    invalid_format += 1
            for pattern, contract in wide_contracts:
                minimum = contract.get("numeric_min")
                maximum = contract.get("numeric_max")
                for key, raw in row.items():
                    if not pattern.fullmatch(str(key)) or raw in EMPTY_VALUES:
                        continue
                    try:
                        number = float(str(raw))
                        if (
                            not math.isfinite(number)
                            or (minimum is not None and number < float(minimum))
                            or (maximum is not None and number > float(maximum))
                        ):
                            invalid_numeric += 1
                    except (TypeError, ValueError):
                        invalid_numeric += 1
            value = canonical_value(spec, row, "value")
            if value not in EMPTY_VALUES:
                try:
                    number = float(str(value))
                    if number >= 900 or number <= -900:
                        sentinel_count += 1
                except ValueError:
                    pass
            stop_flag = canonical_value(spec, row, "stop_flag")
            if stop_flag not in EMPTY_VALUES and str(stop_flag) not in {"0", "1"}:
                unknown_enum += 1
            arrival_code = canonical_value(spec, row, "arrival_code")
            if arrival_code not in EMPTY_VALUES and str(arrival_code) not in {"0", "1", "2", "3", "4", "5", "99"}:
                unknown_enum += 1
        metrics = {
            "invalid_numeric_count": invalid_numeric,
            "unknown_enum_count": unknown_enum,
            "eta_zero_count": eta_zero,
            "eta_value_count": eta_count,
            "eta_zero_ratio": _ratio(eta_zero, eta_count),
            "missing_sentinel_count": sentinel_count,
            "invalid_format_count": invalid_format,
        }
        status = CheckStatus.FAIL if invalid_numeric or invalid_format else (CheckStatus.WARN if unknown_enum or sentinel_count else CheckStatus.PASS)
        return _check("DQ-DOMAIN", "domain_values", status, "Numeric, enum, ETA-zero, and weather sentinel values were profiled.", **metrics), metrics

    @staticmethod
    def _transition_check(run: CollectionRun, spec: SourceSpec) -> tuple[QualityCheck, dict[str, Any]]:
        validator = spec.get("validator")
        transitions = 0
        widths: list[float] = []
        if validator == "bus_position":
            state_field = "stop_flag"
            identity_fields = ["route_id", "vehicle_id", "section_id"]
            is_transition = lambda before, after: before == "0" and after == "1"
        elif validator in {"subway_arrival", "subway_arrival_bulk"}:
            state_field = "arrival_code"
            identity_fields = ["line_id", "station_id", "train_id", "direction"]
            is_transition = lambda before, after: before != "1" and after == "1"
        else:
            return _check("DQ-ACTUAL", "actual_interval_transition", CheckStatus.NOT_EVALUATED, "This endpoint is not a state-transition Actual source."), {"actual_interval_count": 0, "max_actual_interval_width_seconds": None}
        # ETA values are predictions, not observations.  An Actual candidate
        # is counted only when the same vehicle/train changes state across two
        # different polls in the same conservative KST service-date bucket.
        previous: dict[tuple[str, ...], tuple[str, datetime, int]] = {}
        for poll_index, item in enumerate(run.items):
            for row in item.batch.rows:
                observed_at = source_time(spec, row)
                state = canonical_value(spec, row, state_field)
                if observed_at is None or state in EMPTY_VALUES:
                    continue
                service_date = observed_at.astimezone(KST).date().isoformat()
                key = tuple(
                    str(canonical_value(spec, row, field) or "")
                    for field in identity_fields
                ) + (service_date,)
                prior = previous.get(key)
                if (
                    prior
                    and poll_index > prior[2]
                    and observed_at > prior[1]
                    and is_transition(prior[0], str(state))
                ):
                    transitions += 1
                    widths.append((observed_at - prior[1]).total_seconds())
                if prior is None or observed_at > prior[1]:
                    previous[key] = (str(state), observed_at, poll_index)
        metrics = {"actual_interval_count": transitions, "max_actual_interval_width_seconds": max(widths, default=None)}
        status = CheckStatus.PASS if transitions else CheckStatus.NOT_EVALUATED
        message = "State transitions produced interval-censored Actual candidates." if transitions else "No qualifying state transition was observed; ETA rows were not promoted to Actual."
        return _check("DQ-ACTUAL", "actual_interval_transition", status, message, **metrics), metrics

    @staticmethod
    def _policy_check(policy: dict[str, Any]) -> QualityCheck:
        raw = policy.get("raw", "DENY")
        normalized = policy.get("normalized", "DENY")
        allowed = raw == "ALLOW_LOCAL_ONLY" or normalized == "ALLOW_LOCAL_ONLY"
        reviewed = bool(policy.get("review_ticket") and policy.get("reviewed_at"))
        if allowed and not reviewed:
            return _check("DQ-POLICY", "provider_retention_policy", CheckStatus.FAIL, "Persistence was enabled without review provenance.", raw=raw, normalized=normalized, reason=policy.get("reason"), review_ticket=policy.get("review_ticket"), reviewed_at=policy.get("reviewed_at"))
        if allowed:
            return _check("DQ-POLICY", "provider_retention_policy", CheckStatus.PASS, "At least one reviewed local persistence path is enabled.", raw=raw, normalized=normalized, reason=policy.get("reason"), review_ticket=policy.get("review_ticket"), reviewed_at=policy.get("reviewed_at"))
        return _check("DQ-POLICY", "provider_retention_policy", CheckStatus.WARN, "Persistent raw and normalized storage remain default-deny until policy review.", raw=raw, normalized=normalized, reason=policy.get("reason"), review_ticket=None, reviewed_at=None)

    @staticmethod
    def _eligibility(
        purpose: Purpose,
        checks: list[QualityCheck],
        metrics: dict[str, Any],
        spec: SourceSpec,
        policy: dict[str, Any],
        evidence_mode: str,
    ) -> PurposeEligibility:
        check_by_code = {check.code: check for check in checks}
        blockers = [
            code
            for code in ("DQ-COLLECTION", "DQ-TRANSPORT", "DQ-021", "DQ-014", "DQ-PARSE", "DQ-SCHEMA", "DQ-WIDE-SCHEMA", "DQ-IDENTITY", "DQ-TARGET", "DQ-001", "DQ-DOMAIN", "DQ-POLICY")
            if check_by_code.get(code) and check_by_code[code].status == CheckStatus.FAIL
        ]
        configured = {Purpose(value) for value in spec.get("purposes", [])}
        if purpose not in {Purpose.CONTRACT_SMOKE, Purpose.STRUCTURE} and purpose not in configured:
            return PurposeEligibility(purpose, AggregateVerdict.UNUSABLE, ["PURPOSE_NOT_SUPPORTED"], "The source is not configured for this purpose.")
        if blockers:
            return PurposeEligibility(purpose, AggregateVerdict.UNUSABLE, blockers, "Hard transport, business, parse, schema, identity, target, or domain checks failed.")
        if purpose in {Purpose.CONTRACT_SMOKE, Purpose.STRUCTURE}:
            if metrics["row_count"] == 0:
                return PurposeEligibility(purpose, AggregateVerdict.CONDITIONAL, ["NO_DATA_ROWS"], "Transport/envelope may be valid, but no row schema was demonstrated.")
            return PurposeEligibility(purpose, AggregateVerdict.USABLE, [], "The tested fixture/window is usable for parser and contract validation only.")
        if evidence_mode == "FIXTURE":
            return PurposeEligibility(purpose, AggregateVerdict.CONDITIONAL, ["FIXTURE_EVIDENCE_ONLY"], "Fixture evidence cannot establish live or model usability.")
        if purpose in {Purpose.HISTORICAL_MODEL, Purpose.HISTORICAL_DISTRIBUTION} and policy.get("normalized") != "ALLOW_LOCAL_ONLY":
            return PurposeEligibility(purpose, AggregateVerdict.UNUSABLE, ["NORMALIZED_RETENTION_NOT_ALLOWED"], "A historical distribution cannot be built without approved normalized/derived retention.")
        reasons = []
        purpose_checks = (
            "DQ-TRANSPORT",
            "DQ-014",
            "DQ-PARSE",
            "DQ-SCHEMA",
            "DQ-IDENTITY",
            "DQ-TARGET",
            "DQ-001",
            "DQ-COUNT",
            "DQ-DOMAIN",
        )
        non_pass = [
            code
            for code in purpose_checks
            if check_by_code.get(code)
            and check_by_code[code].status
            in {CheckStatus.WARN, CheckStatus.NOT_EVALUATED}
        ]
        reasons.extend(f"{code}_NOT_PASS" for code in non_pass)
        if not spec.get("profiled", False):
            reasons.append("THRESHOLD_PROFILE_NOT_APPROVED")
        if metrics.get("source_time_count", 0) == 0 and purpose in {Purpose.REALTIME_FEATURE, Purpose.ACTUAL_LABEL}:
            reasons.append("SOURCE_TIME_NOT_AVAILABLE")
        if metrics.get("stale_row_count"):
            reasons.append("STALE_ROWS_OBSERVED")
        if purpose == Purpose.ACTUAL_LABEL and metrics.get("actual_interval_count", 0) == 0 and spec.get("validator") != "bis_history":
            reasons.append("NO_STATE_TRANSITION_ACTUAL")
        mapping_check = check_by_code.get("DQ-006")
        if mapping_check and mapping_check.status != CheckStatus.PASS:
            reasons.append("INTERNAL_ID_MAPPING_NOT_VERIFIED")
        if purpose in {Purpose.HISTORICAL_MODEL, Purpose.HISTORICAL_DISTRIBUTION}:
            support = spec.get("historical_support")
            if not isinstance(support, dict):
                reasons.append("HISTORICAL_SUPPORT_GATE_NOT_CONFIGURED")
            else:
                metric_name = str(support.get("metric", ""))
                minimum = support.get("minimum")
                allowed_metrics = {"actual_interval_count", "effective_event_count"}
                if (
                    metric_name not in allowed_metrics
                    or not isinstance(minimum, int)
                    or minimum < 1
                ):
                    reasons.append("HISTORICAL_SUPPORT_GATE_INVALID")
                elif metrics.get(metric_name, 0) < minimum:
                    reasons.append("NO_DISTRIBUTION_SUPPORT")
        if spec.get("semantic_level", "").startswith("STRUCTURE_ONLY"):
            reasons.append("LIVE_CONTRACT_UNVERIFIED")
        if reasons:
            return PurposeEligibility(purpose, AggregateVerdict.CONDITIONAL, reasons, "The response is structurally usable, but purpose-specific evidence is incomplete.")
        return PurposeEligibility(purpose, AggregateVerdict.USABLE, [], "All configured checks for this target and window passed.")

    @staticmethod
    def _limitations(
        run: CollectionRun,
        spec: SourceSpec,
        policy: dict[str, Any],
        evidence_mode: str,
        metrics: dict[str, Any],
    ) -> list[str]:
        limitations = []
        if run.failure_code:
            limitations.append(
                f"Collection ended early ({run.failure_code}); this report covers only persisted observations before the failure."
            )
        if evidence_mode == "FIXTURE":
            limitations.append("Fixture evidence validates parser/contracts only; it is not live-provider evidence.")
        if not spec.get("profiled", False):
            limitations.append("Freshness, coverage, and support thresholds are not yet approved from a long-run profile.")
        if policy.get("raw") != "ALLOW_LOCAL_ONLY":
            limitations.append("Raw response persistence was denied by the current provider policy.")
        if policy.get("normalized") != "ALLOW_LOCAL_ONLY":
            limitations.append("Normalized cross-session persistence was denied by the current provider policy.")
        if len(run.items) < 2:
            limitations.append("A single snapshot cannot establish cadence, transition yield, or historical support.")
        if evidence_mode == "LIVE" and spec.get("transport_security") == "HTTP_ONLY_UPSTREAM":
            limitations.append("The official upstream is HTTP-only; live collection requires an explicit risk acknowledgement.")
        if spec.get("validator") in {"bus_position", "subway_arrival", "subway_arrival_bulk"}:
            limitations.append("State transitions require different polls and use KST calendar date as a conservative service-day boundary until the operating-day rule is verified.")
        if metrics.get("source_time_count", 0) == 0:
            limitations.append("Provider source time was not available, so provider-side freshness could not be established.")
        return limitations
