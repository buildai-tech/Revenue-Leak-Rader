"""
Leakage detection service — orchestrates detector evaluation, creates leakage
events, evidence rows, and canonical financial calculations.

Phases 5-7 wiring:
- Evaluates the V1 funnel detector suite (dark leads, response SLA, single
  touch, post-visit black hole, negotiation rot) PLUS the legacy CRM-event
  rules.
- Computes the response-SLA benchmark once per run: empirical P75 when the
  contacted-lead sample is sufficient, otherwise the configured fallback — the
  source is recorded in evidence either way.
- Deduplicates per (lead, category): re-running detection never creates a
  second leakage event for the same leak.
- Creates ONE canonical financial calculation per leakage event using
  lead_exposure_v2 (per-lead exposure); aggregates deduplicate per lead.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.sales_rep import SalesRep
from app.models.leakage_event import LeakageEvent
from app.models.leakage_evidence import LeakageEvidence
from app.models.financial_calculation import FinancialCalculation
from app.core.rules.lead_leakage import (
    LeadData, evaluate_all_rules, RuleResult,
)
from app.core.rules.funnel_leakage import (
    FunnelLeadData, FunnelThresholds, evaluate_funnel_leaks, LeakCandidate,
)
from app.core.rules.lead_recovery_score import calculate_recovery_score
from app.core.financial_engine.formulas import lead_exposure_v2
from app.core.financial_engine.confidence import calculate_lead_confidence
from app.core.financial_engine.tiers import Tier
from app.core.statistics.benchmarks import empirical_sla_threshold
from app.core.derived import compute_derived_fields

logger = logging.getLogger(__name__)

# A re-run never re-creates leaks already tracked in these statuses.
_ACTIVE_LEAK_STATUSES = ("open", "acknowledged", "in_progress")


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_lead_data(lead: Lead, events: list[LeadEvent], rep: SalesRep | None) -> LeadData:
    """Convert ORM objects to the lightweight LeadData used by rules."""
    event_dicts = [
        {
            "event_type": e.event_type,
            "occurred_at": e.occurred_at,
            "event_payload": e.event_payload,
            "source": e.source,
        }
        for e in events
    ]

    return LeadData(
        lead_id=str(lead.id),
        name=lead.name,
        status=lead.status,
        budget=float(lead.budget) if lead.budget else None,
        sales_rep_name=rep.name if rep else None,
        sales_rep_active=rep.is_active if rep else None,
        created_at=lead.created_at,
        last_followup_at=lead.last_followup_at,
        events=event_dicts,
    )


def _build_funnel_lead_data(lead: Lead, events: list[LeadEvent]) -> FunnelLeadData:
    """Build the funnel detector input, with CRM-event fallbacks.

    Imported lifecycle timestamps take precedence; for seed/CRM data without
    them, the first/last outbound event stand in as first/last contact, and a
    follow-up event after the site visit counts as verified follow-up.
    """
    outbound = [e for e in events if e.event_type in
                ("outbound_call", "outbound_message", "outbound_email", "followup")]
    first_outbound = min((e.occurred_at for e in outbound), default=None)
    last_outbound = max((e.occurred_at for e in outbound), default=None)

    visit = _utc(lead.site_visit_at)
    has_post_visit_followup = False
    if visit is not None:
        has_post_visit_followup = any(
            e.occurred_at and _utc(e.occurred_at) > visit for e in outbound
        )

    return FunnelLeadData(
        lead_id=str(lead.id),
        name=lead.name,
        status=lead.status,
        deal_value=float(lead.budget) if lead.budget else None,
        created_at=_utc(lead.created_at),
        first_contact_at=_utc(lead.first_contact_at),
        last_contact_at=_utc(lead.last_followup_at),
        site_visit_at=visit,
        negotiation_at=_utc(lead.negotiation_at),
        closed_at=_utc(lead.closed_at),
        total_touches=lead.total_touches,
        first_outbound_event_at=_utc(first_outbound),
        last_outbound_event_at=_utc(last_outbound),
        has_post_visit_followup_event=has_post_visit_followup,
    )


async def compute_empirical_sla(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> tuple[float, str, dict[str, Any]]:
    """Empirical response-SLA benchmark for the org (P75 of observed latencies).

    Returns (sla_minutes, source, benchmark_info). Falls back to the configured
    SLA when the sample is insufficient — never pretends the fallback is
    statistically derived.
    """
    settings = get_settings()
    result = await db.execute(
        select(Lead.response_latency_minutes).where(
            Lead.organization_id == organization_id,
            Lead.merged_into_lead_id.is_(None),
            Lead.response_latency_minutes.isnot(None),
        )
    )
    latencies = [float(v) for (v,) in result.all() if v is not None]

    empirical = empirical_sla_threshold(
        response_latencies_minutes=latencies,
        min_sample=settings.RESPONSE_SLA_EMPIRICAL_MIN_SAMPLE,
        fallback_minutes=settings.RESPONSE_SLA_FALLBACK_MINUTES,
    )
    info = {
        "sla_minutes": empirical.value,
        "sla_source": empirical.source,
        "sample_size": empirical.sample_size,
        "sufficient": empirical.sufficient,
        "insufficient_sample_size": empirical.insufficient_sample_size,
        "note": empirical.note,
    }
    return empirical.value, empirical.source, info


async def _existing_leak_categories(db: AsyncSession, lead_id: uuid.UUID) -> set[str]:
    """Categories already tracked for this lead (open leaks) — dedup basis."""
    result = await db.execute(
        select(LeakageEvent.category).where(
            LeakageEvent.source_entity_id == lead_id,
            LeakageEvent.source_entity_type == "lead",
            LeakageEvent.status.in_(_ACTIVE_LEAK_STATUSES),
        )
    )
    return {row[0] for row in result.all()}


def _candidate_to_result(candidate: LeakCandidate) -> RuleResult:
    """Adapt a funnel LeakCandidate to the legacy RuleResult shape."""
    return RuleResult(
        rule=candidate.category,
        points=candidate.points,
        evidence=candidate.evidence,
        triggered=candidate.triggered,
    )


def _default_thresholds() -> FunnelThresholds:
    """Detector thresholds from configuration (env-overridable)."""
    s = get_settings()
    return FunnelThresholds(
        dark_lead_min_age_hours=s.DARK_LEAD_MIN_AGE_HOURS,
        sla_fallback_minutes=s.RESPONSE_SLA_FALLBACK_MINUTES,
        sla_empirical_min_sample=s.RESPONSE_SLA_EMPIRICAL_MIN_SAMPLE,
        post_visit_followup_hours=s.POST_VISIT_FOLLOWUP_HOURS,
        negotiation_stale_days=s.NEGOTIATION_STALE_DAYS,
    )


async def detect_leakage_for_lead(
    db: AsyncSession,
    lead: Lead,
    organization_id: uuid.UUID,
    data_source: str = "Import Pipeline",
    now: datetime | None = None,
    thresholds: FunnelThresholds | None = None,
    sla_minutes: float | None = None,
    sla_source: str = "configured_fallback",
) -> dict[str, Any]:
    """Run all detectors against a single lead.

    Creates leakage events + evidence + canonical financial calculations for
    every TRIGGERED detector not already tracked for this lead (dedup per
    (lead, category)).
    """
    now = _utc(now) or datetime.now(timezone.utc)
    thresholds = thresholds or _default_thresholds()

    # Load events and rep
    events_result = await db.execute(
        select(LeadEvent).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.occurred_at)
    )
    events = list(events_result.scalars().all())

    rep = None
    if lead.sales_rep_id:
        rep = await db.get(SalesRep, lead.sales_rep_id)

    # ── Refresh derived fields if the lead predates them (non-destructive) ──
    if lead.is_dark_lead is None and lead.created_at is not None:
        derived = compute_derived_fields(
            created_at=lead.created_at,
            first_contact_at=lead.first_contact_at,
            last_contact_at=lead.last_followup_at,
            site_visit_at=lead.site_visit_at,
            negotiation_at=lead.negotiation_at,
            closed_at=lead.closed_at,
            total_touches=lead.total_touches,
            now=now,
        )
        lead.response_latency_minutes = derived.response_latency_minutes
        lead.site_visit_latency_days = derived.site_visit_latency_days
        lead.sales_cycle_days = derived.sales_cycle_days
        lead.is_dark_lead = derived.is_dark_lead
        lead.is_single_touch = derived.is_single_touch
        lead.funnel_max_stage = derived.funnel_max_stage
        if derived.data_quality_flags:
            lead.data_quality_flags = derived.to_flags_dict()
        await db.flush()

    # ── Funnel detectors (V1 core suite) ────────────────────────────────────
    funnel_lead = _build_funnel_lead_data(lead, events)
    candidates = evaluate_funnel_leaks(
        funnel_lead,
        now=now,
        thresholds=thresholds,
        sla_minutes=sla_minutes,
        sla_source=sla_source,
    )

    # ── Legacy CRM-event rules (preserved) ──────────────────────────────────
    lead_data = _build_lead_data(lead, events, rep)
    legacy_results = evaluate_all_rules(lead_data, now=now)

    all_results: list[RuleResult] = [_candidate_to_result(c) for c in candidates]
    all_results.extend(legacy_results)
    triggered = [r for r in all_results if r.triggered]

    # ── Dedup per (lead, category) ──────────────────────────────────────────
    already_tracked = await _existing_leak_categories(db, lead.id)
    new_results = [r for r in triggered if r.rule not in already_tracked]

    # Recovery score considers every triggered rule (old + new)
    recovery_score = calculate_recovery_score(all_results)

    # Lead-level confidence for the canonical financial calculation
    confidence = calculate_lead_confidence(
        has_phone=bool(lead.phone_normalized),
        has_email=bool(lead.email),
        has_budget=bool(lead.budget and lead.budget > 0),
        has_project=bool(lead.project_id),
        has_sales_rep=bool(lead.sales_rep_id),
        has_events=len(events) > 0,
        event_count=len(events),
    )

    detector_ids = {c.category: c.detector_id for c in candidates}
    severities = {c.category: c.severity for c in candidates}

    created_events = []
    for rule_result in new_results:
        leakage_event = LeakageEvent(
            organization_id=organization_id,
            category=rule_result.rule,
            source_entity_type="lead",
            source_entity_id=lead.id,
            tier=Tier.MODEL_PREDICTION.value,
            title=_generate_title(rule_result.rule, lead),
            status="open",
            detector_id=detector_ids.get(rule_result.rule),
            severity=severities.get(rule_result.rule),
        )
        db.add(leakage_event)
        await db.flush()

        for ev in rule_result.evidence:
            evidence = LeakageEvidence(
                organization_id=organization_id,
                leakage_event_id=leakage_event.id,
                evidence_type=ev.get("type", "unknown"),
                evidence_payload=ev,
            )
            db.add(evidence)

        # Canonical financial calculation (per-lead exposure, Phase 7)
        if lead.budget and lead.budget > 0:
            financial_result = lead_exposure_v2(
                deal_value_inr=lead.budget,
                commission_rate=lead.commission_rate,
                confidence=confidence,
                data_source=data_source,
            )
            fc = FinancialCalculation(
                organization_id=organization_id,
                leakage_event_id=leakage_event.id,
                tier=financial_result.tier.value,
                amount_inr=financial_result.amount_inr,
                confidence=financial_result.confidence,
                formula_id=financial_result.formula_id,
                formula_version=financial_result.formula_version,
                assumptions=financial_result.assumptions,
                data_source=financial_result.data_source,
            )
            db.add(fc)

        created_events.append(leakage_event)

    await db.flush()

    return {
        "lead_id": str(lead.id),
        "rules_triggered": len(triggered),
        "rules_new": len(new_results),
        "rules_deduplicated": len(triggered) - len(new_results),
        "recovery_score": recovery_score.score,
        "risk_level": recovery_score.risk_level,
        "leakage_events_created": len(created_events),
    }


async def detect_leakage_for_organization(
    db: AsyncSession,
    organization_id: uuid.UUID,
    data_source: str = "Import Pipeline",
) -> dict[str, Any]:
    """Run leakage detection across all unmerged leads in the organization.

    The response-SLA benchmark is computed once per run and shared by every
    lead (empirical P75 when the sample allows, otherwise the configured
    fallback — the source is recorded either way).
    """
    result = await db.execute(
        select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.merged_into_lead_id.is_(None),
        )
    )
    leads = list(result.scalars().all())

    sla_minutes, sla_source, sla_info = await compute_empirical_sla(db, organization_id)
    thresholds = _default_thresholds()

    stats = {
        "total_leads": len(leads),
        "leads_with_leakage": 0,
        "total_events": 0,
        "deduplicated_skips": 0,
        "sla_benchmark": sla_info,
    }

    for lead in leads:
        detection = await detect_leakage_for_lead(
            db, lead, organization_id, data_source,
            thresholds=thresholds, sla_minutes=sla_minutes, sla_source=sla_source,
        )
        if detection["rules_triggered"] > 0:
            stats["leads_with_leakage"] += 1
        stats["total_events"] += detection["leakage_events_created"]
        stats["deduplicated_skips"] += detection["rules_deduplicated"]

    return stats


def _generate_title(category: str, lead: Lead) -> str:
    """Generate a human-readable title for a leakage event."""
    titles = {
        "dark_leads": f"Dark Lead — never contacted — {lead.name}",
        "response_sla_breach": f"Response SLA Breach — {lead.name}",
        "single_touch_abandonment": f"Single-Touch Abandonment — {lead.name}",
        "post_visit_followup_blackhole": f"Post-Visit Follow-Up Black Hole — {lead.name}",
        "negotiation_stage_rot": f"Negotiation Stage Rot — {lead.name}",
        "dead_but_recently_engaged": f"Dead Lead with Recent Engagement — {lead.name}",
        "unresolved_questions": f"Unanswered Customer Query — {lead.name}",
        "repeated_re_engagement": f"Repeated Re-engagement on Dead Lead — {lead.name}",
        "assigned_to_inactive_rep": f"Lead Assigned to Inactive Rep — {lead.name}",
        "no_followup": f"No Follow-up Activity — {lead.name}",
        "high_value_poor_followup": f"High-Value Lead with Poor Follow-up — {lead.name}",
    }
    return titles.get(category, f"Leakage Detected — {lead.name}")
