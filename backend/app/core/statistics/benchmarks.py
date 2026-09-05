"""
Statistical layer — empirical benchmarks, confidence intervals, uncertainty.

NO LLM IMPORTS ALLOWED in this package (same policy as financial_engine).

Principles (Phases 10/11):
- Never fabricate statistical significance. Every statistic reports the sample
  size it was computed from and whether that sample was sufficient.
- Insufficient samples → `sufficient=False` and callers must fall back to a
  documented, configured default (never to an invented "empirical" number).
- Correlation is never presented as causation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass
class EmpiricalResult:
    """Outcome of an empirical estimate with explicit sufficiency reporting."""
    value: float
    source: str                      # "empirical" | "configured_fallback"
    sample_size: int
    sufficient: bool
    insufficient_sample_size: bool   # explicit flag per Phase 10
    ci_low: float | None = None      # only when statistically justified
    ci_high: float | None = None
    note: str = ""


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile of a non-empty sequence (p in [0, 100])."""
    if not values:
        raise ValueError("percentile() requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (p / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[int(rank)])
    weight = rank - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    """Wilson score interval (95% by default) for a binomial proportion."""
    if total <= 0:
        return (0.0, 1.0)
    phat = successes / total
    denom = 1 + (z * z) / total
    center = (phat + (z * z) / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(
        (phat * (1 - phat) / total) + (z * z) / (4 * total * total)
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def empirical_sla_threshold(
    response_latencies_minutes: Sequence[float],
    min_sample: int,
    fallback_minutes: float,
) -> EmpiricalResult:
    """Empirical response-SLA benchmark = P75 of observed response latencies.

    When the contacted-lead sample is smaller than `min_sample`, the configured
    fallback SLA is returned and `insufficient_sample_size=True` is set — the
    benchmark is never presented as statistically derived when it is not.
    """
    n = len(response_latencies_minutes)
    if n >= min_sample and n > 0:
        return EmpiricalResult(
            value=round(percentile(response_latencies_minutes, 75), 2),
            source="empirical_p75",
            sample_size=n,
            sufficient=True,
            insufficient_sample_size=False,
            note=f"P75 of {n} observed response latencies",
        )
    return EmpiricalResult(
        value=fallback_minutes,
        source="configured_fallback",
        sample_size=n,
        sufficient=False,
        insufficient_sample_size=True,
        note=(
            f"Only {n} observed response latencies (minimum {min_sample}) — "
            "using the configured fallback SLA, not a derived benchmark"
        ),
    )


def recovery_rate_estimate(
    recovered_count: int,
    attempted_count: int,
    min_sample: int,
    default_probability: float,
) -> EmpiricalResult:
    """Estimate the probability that a detected leak is recovered.

    Uses the organization's own recorded recovery outcomes when there are at
    least `min_sample` attempts; otherwise returns the documented default with
    `insufficient_sample_size=True`. The Wilson interval is attached only when
    the empirical rate is used.
    """
    if attempted_count >= min_sample:
        rate = recovered_count / attempted_count
        lo, hi = wilson_interval(recovered_count, attempted_count)
        return EmpiricalResult(
            value=round(rate, 4),
            source="empirical_recovery_rate",
            sample_size=attempted_count,
            sufficient=True,
            insufficient_sample_size=False,
            ci_low=round(lo, 4),
            ci_high=round(hi, 4),
            note=(
                f"{recovered_count}/{attempted_count} recorded recovery outcomes "
                "converted; Wilson 95% interval attached"
            ),
        )
    return EmpiricalResult(
        value=default_probability,
        source="documented_default",
        sample_size=attempted_count,
        sufficient=False,
        insufficient_sample_size=True,
        note=(
            f"Only {attempted_count} recorded recovery outcomes (minimum "
            f"{min_sample}) — using the documented default recovery "
            f"probability {default_probability}; no confidence interval is "
            "statistically justified"
        ),
    )


@dataclass
class UncertaintyRange:
    """P10/P50/P90 uncertainty band around a recoverable-revenue estimate."""
    available: bool
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    method: str = "not_available"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "confidence_interval_available": self.available,
            "p10": self.p10,
            "p50": self.p50,
            "p90": self.p90,
            "method": self.method,
            "reason": self.reason,
        }


def exposure_uncertainty(
    exposure_total: float,
    rate: EmpiricalResult,
) -> UncertaintyRange:
    """P10/P50/P90 for recoverable revenue = exposure × recovery probability.

    The band is derived by propagating the Wilson 95% interval of the EMPIRICAL
    recovery rate (P10 = ci_low, P90 = ci_high). If the rate is a documented
    default (insufficient sample), NO interval is invented — per Phase 11 the
    response explicitly reports `confidence_interval_available=False` and why.
    """
    if rate.sufficient and rate.ci_low is not None and rate.ci_high is not None:
        return UncertaintyRange(
            available=True,
            p10=round(exposure_total * rate.ci_low, 2),
            p50=round(exposure_total * rate.value, 2),
            p90=round(exposure_total * rate.ci_high, 2),
            method="wilson_95pct_interval_on_empirical_recovery_rate",
            reason=rate.note,
        )
    return UncertaintyRange(
        available=False,
        method="not_available",
        reason=(
            "P10/P90 require an empirical recovery rate with a statistically "
            f"valid sample; only {rate.sample_size} recorded recovery outcomes "
            "are available. No interval is fabricated."
        ),
    )