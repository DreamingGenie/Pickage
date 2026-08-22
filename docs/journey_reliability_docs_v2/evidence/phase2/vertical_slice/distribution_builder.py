"""Residual/Actual samples -> LegDistribution (EV2 vertical slice).

PD-020: no arbitrary pre-fixed "minimum N" - this module labels confidence
from the sample count it actually has (LOW/INSUFFICIENT below a small,
documented threshold) rather than asserting a fixed universal cutoff is
"enough". The thresholds below are this fixture's own transparent choice,
not a validated statistical minimum-support result (that calibration work
is still open per PD-040 / 00_MASTER_INDEX.md item 5).
"""
from __future__ import annotations

import statistics
from datetime import datetime

from schema import (
    ConfidenceLabel,
    DistributionKind,
    LegDistribution,
    Quantiles,
    UncertaintyCoverage,
    ValidationScope,
)


def _confidence_label(n: int) -> ConfidenceLabel:
    if n == 0:
        return ConfidenceLabel.INSUFFICIENT
    if n < 5:
        return ConfidenceLabel.INSUFFICIENT
    if n < 20:
        return ConfidenceLabel.LOW
    if n < 100:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.HIGH


def build_empirical_leg_distribution(
    leg_id: str,
    samples_sec: list[float],
    observation_start_at: datetime | None,
    observation_end_at: datetime | None,
    rule_version: str,
    samples_ref: str | None = None,
    validation_scope: ValidationScope = ValidationScope.UNVALIDATED,
) -> LegDistribution:
    n = len(samples_sec)
    quantiles = Quantiles()
    if n >= 2:
        sorted_s = sorted(samples_sec)
        quantiles.p50 = statistics.median(sorted_s)
        if n >= 10:
            q = statistics.quantiles(sorted_s, n=10)
            quantiles.p10 = q[0]
            quantiles.p90 = q[8]
    elif n == 1:
        quantiles.p50 = samples_sec[0]

    return LegDistribution(
        distribution_id=f"dist-{leg_id}-{rule_version}",
        leg_id=leg_id,
        distribution_kind=DistributionKind.EMPIRICAL_SAMPLES,
        sample_count=n,
        observation_start_at=observation_start_at,
        observation_end_at=observation_end_at,
        quantiles_sec=quantiles,
        samples_ref=samples_ref,
        confidence_label=_confidence_label(n),
        uncertainty_coverage=UncertaintyCoverage.PARTIAL if n > 0 else UncertaintyCoverage.UNMODELED,
        rule_version=rule_version,
        artifact_version="phase2-vertical-slice-v1",
        validation_scope=validation_scope,
    )


def build_static_reference_distribution(
    leg_id: str, point_value_sec: float, rule_version: str, note: str
) -> LegDistribution:
    return LegDistribution(
        distribution_id=f"dist-{leg_id}-{rule_version}",
        leg_id=leg_id,
        distribution_kind=DistributionKind.STATIC_REFERENCE,
        sample_count=None,
        quantiles_sec=Quantiles(p50=point_value_sec),
        fallback_level=note,
        confidence_label=ConfidenceLabel.LOW,
        uncertainty_coverage=UncertaintyCoverage.UNMODELED,
        rule_version=rule_version,
        artifact_version="phase2-vertical-slice-v1",
        validation_scope=ValidationScope.UNVALIDATED,
    )
