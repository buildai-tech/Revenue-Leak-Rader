"""
Core V1 funnel leakage detectors (Phases 5 & 6).

Deterministic only — no LLM involvement, no NOW() in SQL (callers pass `now`).

Detector suite:
  1. dark_leads                     — created, old enough, never contacted
  2. response_sla_breach            — first response later than the SLA
  3. single_touch_abandonment       — one touch, then abandonment signals
  4. post_visit_followup_blackhole  — site visit with no verified follow-up
  5. negotiation_stage_rot          — stale, unclosed negotiation

Every detector returns a LeakCandidate with:
  lead evidence, severity, financial relevance (deal value), confidence method
  and provenance (detector_id). Confidence is always labeled
  "deterministic_heuristic" — no survival analysis (Cox) exists in V1 and none
  is claimed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.derived import (
    ABANDONMENT_STATUSES,
    WON_STATUSES,
    ACTIVE_PIPELINE_STATUSES,
)

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_utc(now: datetime | None) -> datetime:
    return _utc(now) or datetime.now(timezone.utc)


@dataclass
class FunnelLeadData:
    """Lightweight lead snapshot for funnel detection (no ORM dependency)."""
    lead_id: str
    name: str
    status: str | None
    deal_value: float | None
    created_at: datetime | None
    first_contact_at: datetime | None
    last_contact_at: datetime | None
    site_visit_at: datetime | None
    negotiation_at: datetime | None
    closed_at: datetime | None
    total_touches: int | None
    # Fallbacks for CRM-event data (seed/demo) that lacks imported timestamps:
    first_outbound_event_at: datetime | None = None
    last_outbound_event_at: datetime | None = None
    has_post_visit_followup_event: bool = False


@dataclass
class FunnelThresholds:
    """Configurable detector thresholds (defaults come from Settings)."""
    dark_lead_min_age_hours: float = 24.0
    sla_fallback_minutes: float = 60.0
    sla_empirical_min_sample: int = 20
    post_visit_followup_hours: float = 48.0
    negotiation_stale_days: float = 14.0
    single_touch_stale_days: float = 7.0


@dataclass
class LeakCandidate:
    """Output of a funnel detector — triggered or not."""
    detector_id: str
    category: str
    severity: str
    title: str
    points: int
    confidence_method: str = "deterministic_heuristic"
    triggered: bool = False
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _severity_by_deal_value(deal_value: float | None) -> str:
    if deal_value is None:
        return "medium"
    if deal_value >= 3_000_000:
        return "critical"
    if deal_value >= 1_000_000:
        return "high"
    return "medium"


def _effective_first_contact(lead: FunnelLeadData) -> datetime | None:
    """first_contact_at from import data; fall back to first outbound event."""
    return lead.first_contact_at or lead.first_outbound_event_at


def _effective_last_contact(lead: FunnelLeadData) -> datetime | None:
    """last_contact_at from import data; fall back to last outbound event."""
    return lead.last_contact_at or lead.last_outbound_event_at


# ── Detector 1 — Dark Leads ─────────────────────────────────────────────────

def dark_leads(
    lead: FunnelLeadData,
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
) -> LeakCandidate:
    """Lead created, old enough to be meaningfully uncontacted, first_contact_at NULL.

    A lead created seconds ago is NOT a leak — the minimum-age threshold guards
    against that. Won leads are excluded outright.
    """
    thresholds = thresholds or FunnelThresholds()
    now = _now_utc(now)
    result = LeakCandidate(
        detector_id="funnel_leakage.dark_leads",
        category="dark_leads",
        severity="high",
        title="Dark Lead — never contacted",
        points=25,
    )

    if lead.status and lead.status.lower() in WON_STATUSES:
        return result
    if _effective_first_contact(lead) is not None:
        return result
    if lead.created_at is None:
        return result

    created = _utc(lead.created_at)
    age_hours = (now - created).total_seconds() / 3600.0
    if age_hours < thresholds.dark_lead_min_age_hours:
        return result

    result.triggered = True
    if age_hours >= 24 * 30:
        result.severity = "critical"
    elif age_hours >= 24 * 7:
        result.severity = "high"
    else:
        result.severity = "low"

    result.evidence = [
        {"type": "lead_id", "detail": lead.lead_id},
        {"type": "detector", "detail": result.detector_id},
        {"type": "first_contact_missing", "detail": "first_contact_at is NULL and no contact event exists"},
        {"type": "age_hours", "detail": round(age_hours, 1)},
        {"type": "min_age_threshold_hours", "detail": thresholds.dark_lead_min_age_hours},
        {"type": "status", "detail": lead.status or "unknown"},
        {"type": "deal_value", "detail": lead.deal_value},
        {"type": "detected_at", "detail": now.isoformat()},
    ]
    return result


# ── Detector 2 — Response SLA Breach ────────────────────────────────────────

def response_sla_breach(
    lead: FunnelLeadData,
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
    sla_minutes: float | None = None,
    sla_source: str = "configured_fallback",
) -> LeakCandidate:
    """First response slower than the SLA benchmark.

    The SLA may be an empirical P75 (when sufficient history exists) or the
    configured fallback — `sla_source` records which, and the evidence always
    carries the actual response time, the benchmark, the breach amount and the
    deal value.
    """
    thresholds = thresholds or FunnelThresholds()
    now = _now_utc(now)
    benchmark = sla_minutes if sla_minutes is not None else thresholds.sla_fallback_minutes
    result = LeakCandidate(
        detector_id="funnel_leakage.response_sla_breach",
        category="response_sla_breach",
        severity="medium",
        title="Response SLA breach",
        points=20,
    )

    first = _effective_first_contact(lead)
    if first is None or lead.created_at is None:
        return result
    if lead.status and lead.status.lower() in WON_STATUSES:
        return result

    created = _utc(lead.created_at)
    first = _utc(first)
    latency_minutes = (first - created).total_seconds() / 60.0
    if latency_minutes < 0:
        # Invalid ordering is a data-quality problem, not an SLA breach.
        return result
    if latency_minutes <= benchmark:
        return result

    breach_minutes = latency_minutes - benchmark
    ratio = latency_minutes / benchmark if benchmark > 0 else float("inf")
    if ratio >= 4:
        result.severity = "critical"
    elif ratio >= 2:
        result.severity = "high"
    else:
        result.severity = "medium"

    result.triggered = True
    result.evidence = [
        {"type": "lead_id", "detail": lead.lead_id},
        {"type": "detector", "detail": result.detector_id},
        {"type": "actual_response_minutes", "detail": round(latency_minutes, 2)},
        {"type": "benchmark_minutes", "detail": benchmark},
        {"type": "benchmark_source", "detail": sla_source},
        {"type": "breach_minutes", "detail": round(breach_minutes, 2)},
        {"type": "deal_value", "detail": lead.deal_value},
        {"type": "detected_at", "detail": now.isoformat()},
    ]
    return result


# ── Detector 3 — Single-Touch Abandonment ───────────────────────────────────

def single_touch_abandonment(
    lead: FunnelLeadData,
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
) -> LeakCandidate:
    """Exactly one touch AND abandonment signals — never applied to won or
    actively-progressing leads.

    Triggered when total_touches == 1 AND either:
      - the lifecycle status indicates abandonment/unreachable/inactive/lost, or
      - the only touch is at least `single_touch_stale_days` old with nothing since.
    """
    thresholds = thresholds or FunnelThresholds()
    now = _now_utc(now)
    result = LeakCandidate(
        detector_id="funnel_leakage.single_touch_abandonment",
        category="single_touch_abandonment",
        severity="medium",
        title="Single-Touch Abandonment",
        points=15,
    )

    if lead.total_touches != 1:
        return result
    status_lower = (lead.status or "").lower()
    if status_lower in WON_STATUSES:
        return result  # legitimately won — not a leak

    status_abandoned = status_lower in ABANDONMENT_STATUSES
    stale = False
    last = _effective_last_contact(lead)
    if last is not None:
        stale = (now - _utc(last)).total_seconds() / 86400.0 >= thresholds.single_touch_stale_days

    if not (status_abandoned or stale):
        return result  # may still be actively progressing — not a leak

    result.severity = _severity_by_deal_value(lead.deal_value)
    result.triggered = True
    result.evidence = [
        {"type": "lead_id", "detail": lead.lead_id},
        {"type": "detector", "detail": result.detector_id},
        {"type": "total_touches", "detail": 1},
        {"type": "status", "detail": lead.status or "unknown"},
        {"type": "abandonment_status", "detail": status_abandoned},
        {"type": "stale_since_last_touch_days", "detail": (
            round((now - _utc(last)).total_seconds() / 86400.0, 1) if last else None
        )},
        {"type": "deal_value", "detail": lead.deal_value},
        {"type": "detected_at", "detail": now.isoformat()},
    ]
    return result


# ── Detector 4 — Post-Site-Visit Follow-Up Black Hole ───────────────────────

def post_visit_followup_blackhole(
    lead: FunnelLeadData,
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
) -> LeakCandidate:
    """Site visit completed, no VERIFIED subsequent contact, threshold elapsed.

    Default threshold: 48 hours (configurable). Verified subsequent contact is
    any of: last_contact_at / negotiation_at / closed_at AFTER the visit, or a
    follow-up event in the lead's timeline after the visit. `now` is passed in
    by the caller (application-side timestamp) — no dialect-specific NOW().
    """
    thresholds = thresholds or FunnelThresholds()
    now = _now_utc(now)
    result = LeakCandidate(
        detector_id="funnel_leakage.post_visit_followup_blackhole",
        category="post_visit_followup_blackhole",
        severity="high",
        title="Post-Site-Visit Follow-Up Black Hole",
        points=25,
    )

    if lead.site_visit_at is None:
        return result
    status_lower = (lead.status or "").lower()
    if status_lower in WON_STATUSES:
        return result

    visit = _utc(lead.site_visit_at)

    # Verified subsequent contact/follow-up after the visit?
    subsequent = [
        dt for dt in (
            _utc(lead.last_contact_at),
            _utc(lead.negotiation_at),
            _utc(lead.closed_at),
        ) if dt is not None and dt > visit
    ]
    if subsequent or lead.has_post_visit_followup_event:
        return result

    hours_since_visit = (now - visit).total_seconds() / 3600.0
    if hours_since_visit < thresholds.post_visit_followup_hours:
        return result

    if hours_since_visit >= 24 * 14:
        result.severity = "critical"
    elif hours_since_visit >= 24 * 7:
        result.severity = "high"
    else:
        result.severity = "medium"

    result.triggered = True
    result.evidence = [
        {"type": "lead_id", "detail": lead.lead_id},
        {"type": "detector", "detail": result.detector_id},
        {"type": "site_visit_at", "detail": visit.isoformat()},
        {"type": "hours_since_visit", "detail": round(hours_since_visit, 1)},
        {"type": "threshold_hours", "detail": thresholds.post_visit_followup_hours},
        {"type": "no_verified_followup", "detail": "No contact/negotiation/closure timestamp after the visit"},
        {"type": "deal_value", "detail": lead.deal_value},
        {"type": "detected_at", "detail": now.isoformat()},
    ]
    return result


# ── Detector 5 (Phase 6) — Negotiation Stage Rot ────────────────────────────

def negotiation_stage_rot(
    lead: FunnelLeadData,
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
) -> LeakCandidate:
    """Stale, unclosed negotiation.

    Uses negotiation_at + current status + deal_value with a configurable
    staleness threshold. Confidence method is explicitly
    "deterministic_heuristic" — no Cox / survival analysis exists in V1.
    """
    thresholds = thresholds or FunnelThresholds()
    now = _now_utc(now)
    result = LeakCandidate(
        detector_id="funnel_leakage.negotiation_stage_rot",
        category="negotiation_stage_rot",
        severity="high",
        title="Negotiation Stage Rot",
        points=20,
    )

    if lead.negotiation_at is None:
        return result
    if lead.closed_at is not None:
        return result  # negotiation reached an outcome — not rotting

    status_lower = (lead.status or "").lower()
    if status_lower in WON_STATUSES or status_lower in ABANDONMENT_STATUSES:
        return result  # outcome already recorded in status

    negot = _utc(lead.negotiation_at)
    stale_days = (now - negot).total_seconds() / 86400.0
    if stale_days < thresholds.negotiation_stale_days:
        return result

    ratio = stale_days / thresholds.negotiation_stale_days if thresholds.negotiation_stale_days > 0 else 0
    if ratio >= 3:
        result.severity = "critical"
    elif ratio >= 2:
        result.severity = "high"
    else:
        result.severity = "medium"

    result.triggered = True
    result.evidence = [
        {"type": "lead_id", "detail": lead.lead_id},
        {"type": "detector", "detail": result.detector_id},
        {"type": "negotiation_at", "detail": negot.isoformat()},
        {"type": "stale_days", "detail": round(stale_days, 1)},
        {"type": "stale_threshold_days", "detail": thresholds.negotiation_stale_days},
        {"type": "status", "detail": lead.status or "unknown"},
        {"type": "deal_value", "detail": lead.deal_value},
        {"type": "confidence_method", "detail": "deterministic_heuristic (no survival analysis in V1)"},
        {"type": "detected_at", "detail": now.isoformat()},
    ]
    return result


# ── Evaluate the full funnel detector suite ─────────────────────────────────

FUNNEL_DETECTORS = [
    dark_leads,
    response_sla_breach,
    single_touch_abandonment,
    post_visit_followup_blackhole,
    negotiation_stage_rot,
]

# Core V1 categories, in dashboard display order.
CORE_CATEGORIES = [
    "dark_leads",
    "response_sla_breach",
    "single_touch_abandonment",
    "post_visit_followup_blackhole",
    "negotiation_stage_rot",
]


def evaluate_funnel_leaks(
    lead: FunnelLeadData,
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
    sla_minutes: float | None = None,
    sla_source: str = "configured_fallback",
) -> list[LeakCandidate]:
    """Run every funnel detector against one lead (results include non-triggered)."""
    return [
        dark_leads(lead, now, thresholds),
        response_sla_breach(lead, now, thresholds, sla_minutes=sla_minutes, sla_source=sla_source),
        single_touch_abandonment(lead, now, thresholds),
        post_visit_followup_blackhole(lead, now, thresholds),
        negotiation_stage_rot(lead, now, thresholds),
    ]
