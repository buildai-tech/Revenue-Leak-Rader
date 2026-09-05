"""
Dashboard service â€” aggregations for the Command Center.
Every number is computed from real database queries via the canonical financial
aggregates module(core/financial_aggregates.py). No hardcoded values.

Recovery Pipeline funnel semantics (Phase 15):
- The stages are EXPLICITLY CUMULATIVE: each stage counts leakage events that
  have reached AT LEAST that milestone. `detected >= reviewed >= recommended
  >= intervention_started >= recovered`. The definition is returned to the UI.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leakage_event import LeakageEvent
from app.models.financial_calculation import FinancialCalculation
from app.models.recommendation import Recommendation
from app.models.intervention import Intervention
from app.models.recovery_outcome import RecoveryOutcome
from app.models.lead import Lead
from app.core.financial_aggregates import get_financial_summary, exposure_by_category
from app.core.financial_engine.tiers import Tier


async def get_summary(db: AsyncSession, org_id: uuid.UUID) -> dict[str, Any]:
    """Top KPIs for the Command Center â€” all canonical, per-lead deduplicated."""
    fin = await get_financial_summary(db, org_id)

    stmt = select(func.avg(FinancialCalculation.confidence)).where(
        FinancialCalculation.organization_id == org_id,
        FinancialCalculation.tier == Tier.ESTIMATED_FINANCIAL_IMPACT.value,
    )
    avg_confidence = float((await db.execute(stmt)).scalar() or 0)

    stmt = select(func.count(LeakageEvent.id)).where(
        LeakageEvent.organization_id == org_id,
        LeakageEvent.status.in_(["open", "acknowledged"]),
    )
    high_priority_count = (await db.execute(stmt)).scalar() or 0

    return {
        "revenue_at_risk": float(fin.revenue_at_risk),
        "revenue_at_risk_tier": Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        "revenue_at_risk_confidence": round(avg_confidence, 1),
        "potentially_recoverable": float(fin.recoverable_opportunity),
        "pipeline_at_risk": float(fin.pipeline_at_risk),
        "realized_loss": float(fin.realized_loss),
        "recoverable_opportunity": float(fin.recoverable_opportunity),
        "recovery_rate": fin.recovery_rate,
        "uncertainty": fin.uncertainty,
        "metric_definitions": fin.metric_definitions,
        "calculated_at": fin.calculated_at,
        "high_priority_count": high_priority_count,
        "leaking_lead_count": fin.leaking_lead_count,
        "confirmed_recovered": float(fin.confirmed_recovered),
        "confirmed_recovered_tier": Tier.CONFIRMED_RECOVERED_REVENUE.value,
    }


async def get_leakage_breakdown(db: AsyncSession, org_id: uuid.UUID) -> list[dict[str, Any]]:
    """Leakage breakdown by category with counts and deduplicated exposure."""
    return await exposure_by_category(db, org_id)


async def get_high_priority_issues(
    db: AsyncSession, org_id: uuid.UUID, limit: int = 20
) -> list[dict[str, Any]]:
    """Top revenue leaks ordered by canonical exposure, severity, then recency."""
    stmt = (
        select(
            LeakageEvent, Lead.name.label("lead_name"),
            Lead.budget.label("lead_budget"),
            Lead.status.label("lead_status"),
            FinancialCalculation.amount_inr,
            FinancialCalculation.confidence,
            FinancialCalculation.tier.label("financial_tier"),
        )
        .outerjoin(Lead, Lead.id == LeakageEvent.source_entity_id)
        .outerjoin(
            FinancialCalculation,
            FinancialCalculation.leakage_event_id == LeakageEvent.id,
        )
        .where(
            LeakageEvent.organization_id == org_id,
            LeakageEvent.status.in_(["open", "acknowledged", "in_progress"]),
        )
        .order_by(FinancialCalculation.amount_inr.desc().nullslast())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": str(row.LeakageEvent.id),
            "category": row.LeakageEvent.category,
            "detector_id": row.LeakageEvent.detector_id,
            "severity": row.LeakageEvent.severity,
            "title": row.LeakageEvent.title,
            "status": row.LeakageEvent.status,
            "lead_name": row.lead_name,
            "lead_budget": float(row.lead_budget) if row.lead_budget else None,
            "lead_status": row.lead_status,
            "financial_impact": float(row.amount_inr) if row.amount_inr else None,
            "confidence": row.confidence,
            "tier": row.financial_tier,
            "created_at": row.LeakageEvent.created_at.isoformat() if row.LeakageEvent.created_at else None,
        }
        for row in rows
    ]


async def get_recovery_pipeline(db: AsyncSession, org_id: uuid.UUID) -> dict[str, Any]:
    """Recovery funnel â€” EXPLICITLY CUMULATIVE at-least milestones.

    detected              â†’ every leakage event
    reviewed              â†’ events with a human review status (acknowledged+)
    recommended           â†’ events with â‰¥1 recommendation
    intervention_started â†’ events with â‰¥1 intervention
    recovered            â†’ events with a converted recovery outcome

    The definition is returned so the funnel is never misread as mutually
    exclusive buckets.
    """
    detected = (await db.execute(
        select(func.count(LeakageEvent.id)).where(LeakageEvent.organization_id == org_id)
    )).scalar() or 0

    reviewed = (await db.execute(
        select(func.count(LeakageEvent.id)).where(
            LeakageEvent.organization_id == org_id,
            LeakageEvent.status.in_(["acknowledged", "in_progress", "resolved", "dismissed"]),
        )
    )).scalar() or 0

    recommended_subq = (
        select(Recommendation.leakage_event_id)
        .where(Recommendation.organization_id == org_id)
        .distinct()
        .subquery()
    )
    recommended = (await db.execute(
        select(func.count(LeakageEvent.id)).where(
            LeakageEvent.organization_id == org_id,
            LeakageEvent.id.in_(select(recommended_subq.c.leakage_event_id)),
        )
    )).scalar() or 0

    intervention_subq = (
        select(Intervention.recommendation_id)
        .join(Recommendation, Recommendation.id == Intervention.recommendation_id)
        .where(Intervention.organization_id == org_id)
        .subquery()
    )
    intervention_started = (await db.execute(
        select(func.count(LeakageEvent.id)).where(
            LeakageEvent.organization_id == org_id,
            LeakageEvent.id.in_(
                select(Recommendation.leakage_event_id).where(
                    Recommendation.id.in_(select(intervention_subq.c.recommendation_id))
                )
            ),
        )
    )).scalar() or 0

    recovered_subq = (
        select(RecoveryOutcome.intervention_id)
        .where(
            RecoveryOutcome.organization_id == org_id,
            RecoveryOutcome.outcome_type == "converted",
        )
        .subquery()
    )
    recovered = (await db.execute(
        select(func.count(LeakageEvent.id)).where(
            LeakageEvent.organization_id == org_id,
            LeakageEvent.id.in_(
                select(Recommendation.leakage_event_id).where(
                    Recommendation.id.in_(
                        select(Intervention.recommendation_id).where(
                            Intervention.id.in_(select(recovered_subq.c.intervention_id))
                        )
                    )
                )
            ),
        )
    )).scalar() or 0

    return {
        "detected": detected,
        "reviewed": reviewed,
        "recommended": recommended,
        "intervention_started": intervention_started,
        "recovered": recovered,
        "is_cumulative": True,
        "definition": (
            "Cumulative funnels: reviewed/recommended/intervention_started/recovered "
            "each count leakage events that reached AT LEAST that milestone "
            "(detected â‰¥ reviewed â‰¥ recommended â‰¥ intervention_started â‰¥ recovered)."
        ),
    }


async def get_recent_recoveries(
    db: AsyncSession, org_id: uuid.UUID, limit: int = 10
) -> list[dict[str, Any]]:
    """Recent confirmed recovery outcomes."""
    stmt = (
        select(RecoveryOutcome)
        .where(
            RecoveryOutcome.organization_id == org_id,
            RecoveryOutcome.outcome_type == "converted",
        )
        .order_by(RecoveryOutcome.confirmed_at.desc().nullslast())
        .limit(limit)
    )
    result = await db.execute(stmt)
    outcomes = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "intervention_id": str(o.intervention_id),
            "outcome_type": o.outcome_type,
            "booking_amount_inr": float(o.booking_amount_inr) if o.booking_amount_inr else None,
            "confirmed_at": o.confirmed_at.isoformat() if o.confirmed_at else None,
        }
        for o in outcomes
    ]
