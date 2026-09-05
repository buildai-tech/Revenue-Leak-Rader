"""
Response leakage detection.

Computes response_delay = first_outbound_response.occurred_at - lead.created_at
Buckets: <5min, 5-30min, 30-60min, >60min, never_contacted
Conversion rate per bucket from organization's own data.
Minimum sample size gate (default 20).

ALWAYS includes "Correlation, not causation" — this is a hard requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


# ── Configuration ───────────────────────────────────────────────────────

MINIMUM_SAMPLE_SIZE = 20

# Response time bucket boundaries (in minutes)
BUCKET_BOUNDARIES = [
    (0, 5, "under_5_min", "< 5 minutes"),
    (5, 30, "5_to_30_min", "5-30 minutes"),
    (30, 60, "30_to_60_min", "30-60 minutes"),
    (60, float("inf"), "over_60_min", "> 60 minutes"),
]

CONVERTED_STATUSES = {"converted", "booked", "won", "closed_won"}


@dataclass
class ResponseBucket:
    """One response-time bucket with its conversion statistics."""
    bucket_key: str
    bucket_label: str
    lead_count: int
    converted_count: int
    conversion_rate: float | None  # None if sample_too_small
    sample_too_small: bool
    avg_response_minutes: float | None


@dataclass
class ResponseLeakageResult:
    """Complete response leakage analysis."""
    buckets: list[ResponseBucket] = field(default_factory=list)
    never_contacted: ResponseBucket | None = None
    total_leads: int = 0
    leads_with_response: int = 0
    baseline_conversion_rate: float | None = None
    correlation_not_causation: bool = True  # ALWAYS TRUE — hard requirement
    disclaimer: str = "Correlation, not causation: response time correlates with conversion but does not prove a causal relationship."


@dataclass
class LeadResponseData:
    """Lightweight lead data for response leakage analysis."""
    lead_id: str
    created_at: datetime
    status: str | None
    first_outbound_at: datetime | None


def _ensure_utc(dt: datetime | str | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_response_delay_minutes(
    created_at: datetime, first_outbound_at: datetime | None
) -> float | None:
    """Calculate response delay in minutes, or None if never contacted."""
    c_at = _ensure_utc(created_at)
    f_at = _ensure_utc(first_outbound_at)
    if not f_at or not c_at:
        return None
    delta = f_at - c_at
    return max(0.0, delta.total_seconds() / 60)


def bucket_leads(leads: list[LeadResponseData]) -> ResponseLeakageResult:
    """Bucket leads by response time and compute conversion rates.

    Returns ResponseLeakageResult with all buckets, baseline conversion,
    and the mandatory "Correlation, not causation" disclaimer.
    """
    result = ResponseLeakageResult(total_leads=len(leads))

    # Initialize buckets
    bucket_data: dict[str, list[LeadResponseData]] = {
        b[2]: [] for b in BUCKET_BOUNDARIES
    }
    never_contacted: list[LeadResponseData] = []

    # Classify each lead
    for lead in leads:
        delay = calculate_response_delay_minutes(lead.created_at, lead.first_outbound_at)

        if delay is None:
            never_contacted.append(lead)
            continue

        result.leads_with_response += 1

        for low, high, key, label in BUCKET_BOUNDARIES:
            if low <= delay < high:
                bucket_data[key].append(lead)
                break

    # Compute conversion rates per bucket
    all_converted = sum(
        1 for l in leads
        if l.status and l.status.lower() in CONVERTED_STATUSES
    )
    if len(leads) >= MINIMUM_SAMPLE_SIZE:
        result.baseline_conversion_rate = round(all_converted / len(leads) * 100, 2)

    for low, high, key, label in BUCKET_BOUNDARIES:
        leads_in_bucket = bucket_data[key]
        count = len(leads_in_bucket)
        converted = sum(
            1 for l in leads_in_bucket
            if l.status and l.status.lower() in CONVERTED_STATUSES
        )

        sample_too_small = count < MINIMUM_SAMPLE_SIZE

        # Calculate avg response time for this bucket
        delays = [
            calculate_response_delay_minutes(l.created_at, l.first_outbound_at)
            for l in leads_in_bucket
        ]
        delays_valid = [d for d in delays if d is not None]
        avg_delay = round(sum(delays_valid) / len(delays_valid), 1) if delays_valid else None

        result.buckets.append(ResponseBucket(
            bucket_key=key,
            bucket_label=label,
            lead_count=count,
            converted_count=converted,
            conversion_rate=round(converted / count * 100, 2) if count > 0 and not sample_too_small else None,
            sample_too_small=sample_too_small,
            avg_response_minutes=avg_delay,
        ))

    # Never contacted bucket
    nc_count = len(never_contacted)
    nc_converted = sum(
        1 for l in never_contacted
        if l.status and l.status.lower() in CONVERTED_STATUSES
    )
    result.never_contacted = ResponseBucket(
        bucket_key="never_contacted",
        bucket_label="Never Contacted",
        lead_count=nc_count,
        converted_count=nc_converted,
        conversion_rate=round(nc_converted / nc_count * 100, 2) if nc_count >= MINIMUM_SAMPLE_SIZE else None,
        sample_too_small=nc_count < MINIMUM_SAMPLE_SIZE,
        avg_response_minutes=None,
    )

    return result
