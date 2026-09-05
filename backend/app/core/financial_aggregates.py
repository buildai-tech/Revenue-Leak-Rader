"""
Canonical financial aggregates (Phase 7/8) — the SINGLE source of truth for
every rupee figure shown on the dashboard and reports.

NO LLM IMPORTS ALLOWED in this module.

Exposure model (documented, mutually consistent):
- Every ESTIMATED_FINANCIAL_IMPACT row produced by lead_exposure_v2 carries the
  SAME canonical per-lead exposure for all leakage events of that lead.
- revenue_at_risk   = Σ per-lead MAX(exposure)                (deduplicated)
- pipeline_at_risk  = Σ per-lead MAX(exposure) for leads still in the active
                      pipeline (not won/lost)                 (subset of above)
- realized_loss     = Σ per-lead MAX(exposure) for leaking leads that ended
                      lost/dead with no confirmed recovery    (associated, not
                      proven causal)
- recoverable       = Σ per-lead MAX(exposure) × recovery_probability, where
                      the probability is empirical (org's own recovery outcomes,
                      Wilson interval attached) or the documented default.
- confirmed_recovered = Σ CONFIRMED_RECOVERED_REVENUE rows (separate figure).

Because every metric derives from the same per-lead maxima, the same monetary
exposure can never be counted twice.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.leakage_event import LeakageEvent
from app.models.financial_calculation import FinancialCalculation
from app.models.lead import Lead
from app.models.recovery_outcome import RecoveryOutcome
from app.models.intervention import Intervention
from app.models.recommendation import Recommendation
from app.core.financial_engine.tiers import Tier
from app.core.derived import ACTIVE_PIPELINE_STATUSES, ABANDONMENT_STATUSES, WON_STATUSES
from app.core.statistics.benchmarks import (
    recovery_rate_estimate,
    exposure_uncertainty,
    UncertaintyRange,
)


@dataclass
class FinancialSummary:
    """Canonical financial summary — every metric with definition + provenance."""
    revenue_at_risk: Decimal
    pipeline_at_risk: Decimal
    realized_loss: Decimal
    recoverable_opportunity: Decimal
    confirmed_recovered: Decimal
    leaking_lead_count: int
    recovery_rate: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    metric_definitions: list[dict[str, Any]] = field(default_factory=list)
    calculated_at: str = ""


async def canonical_per_lead_exposure(
    db: AsyncSession, organization_id: Any
) -> dict[str, Decimal]:
    """Maximum ESTIMATED_FINANCIAL_IMPACT per leaking lead (the dedup basis)."""
    stmt = (
        select(
            LeakageEvent.source_entity_id,
            func.max(FinancialCalculation.amount_inr).label("max_amount"),
        )
        .join(
            FinancialCalculation,
            FinancialCalculation.leakage_event_id == LeakageEvent.id,
        )
        .where(
            LeakageEvent.organization_id == organization_id,
            LeakageEvent.source_entity_type == "lead",
            FinancialCalculation.tier == Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        )
        .group_by(LeakageEvent.source_entity_id)
    )
    result = await db.execute(stmt)
    return {
        str(row.source_entity_id): Decimal(str(row.max_amount))
        for row in result.all()
        if row.max_amount is not None
    }


async def _lead_status_map(
    db: AsyncSession, organization_id: Any, lead_ids: list[str]
) -> dict[str, str | None]:
    if not lead_ids:
        return {}
    # Convert string IDs to uuid.UUID objects for the .in_() filter.
    # Do NOT use SQLAlchemy's Uuid type as a value converter — it is a
    # column type, not a scalar converter.
    uuid_ids = [uuid.UUID(lid) if not isinstance(lid, uuid.UUID) else lid for lid in lead_ids]
    stmt = select(Lead.id, Lead.status).where(
        Lead.id.in_(uuid_ids)
    )
    result = await db.execute(stmt)
    return {str(row.id): row.status for row in result.all()}


async def confirmed_recovered_total(
    db: AsyncSession, organization_id: Any
) -> Decimal:
    """Sum of CONFIRMED_RECOVERED_REVENUE (real money, separate from estimates)."""
    stmt = (
        select(func.coalesce(func.sum(FinancialCalculation.amount_inr), Decimal("0")))
        .where(
            FinancialCalculation.organization_id == organization_id,
            FinancialCalculation.tier == Tier.CONFIRMED_RECOVERED_REVENUE.value,
        )
    )
    total = (await db.execute(stmt)).scalar()
    return Decimal(str(total)) if total else Decimal("0")


async def _recovery_rate(db: AsyncSession, organization_id: Any) -> dict[str, Any]:
    """Empirical-or-default recovery probability from the org's own outcomes."""
    settings = get_settings()
    stmt = (
        select(RecoveryOutcome.outcome_type, func.count(RecoveryOutcome.id))
        .join(Intervention, Intervention.id == RecoveryOutcome.intervention_id)
        .where(RecoveryOutcome.organization_id == organization_id)
        .group_by(RecoveryOutcome.outcome_type)
    )
    rows = (await db.execute(stmt)).all()
    counts = {r[0]: int(r[1]) for r in rows}
    attempted = sum(counts.values())
    recovered = counts.get("converted", 0)
    rate = recovery_rate_estimate(
        recovered_count=recovered,
        attempted_count=attempted,
        min_sample=settings.RECOVERY_RATE_MIN_SAMPLE,
        default_probability=settings.RECOVERY_PROBABILITY_DEFAULT,
    )
    return {
        "probability": rate.value,
        "source": rate.source,
        "sample_size": rate.sample_size,
        "sufficient": rate.sufficient,
        "insufficient_sample_size": rate.insufficient_sample_size,
        "ci_low": rate.ci_low,
        "ci_high": rate.ci_high,
        "note": rate.note,
    }


def metric_definitions(recovery_rate_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Dashboard-facing definitions — formula, data source, provenance per metric."""
    return [
        {
            "metric": "revenue_at_risk",
            "label": "Estimated Revenue Exposure (Revenue at Risk)",
            "definition": (
                "Total commission revenue the business fails to collect if every "
                "currently-detected leaking lead is lost. Deduplicated per lead — "
                "a lead flagged by several detectors is counted once."
            ),
            "formula": "Σ over leaking leads of MAX(per-detector exposure); exposure = deal_value × effective_commission_rate",
            "data_source": "leakage_events ⨝ financial_calculations (tier=estimated_financial_impact)",
            "tier": Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        },
        {
            "metric": "pipeline_at_risk",
            "label": "Pipeline at Risk",
            "definition": (
                "Subset of Revenue at Risk from leads still moving through the "
                "active pipeline (not won, not lost) — recovery is still possible."
            ),
            "formula": "Σ per-lead MAX(exposure) where lead.status ∈ active-pipeline statuses",
            "data_source": "leads.status ⨝ deduplicated exposure",
            "tier": Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        },
        {
            "metric": "realized_loss",
            "label": "Actual Realized Loss (associated)",
            "definition": (
                "Commission value on leaking leads that ended lost/dead with no "
                "confirmed recovery. ASSOCIATED with detected leaks — this is not "
                "a proven causal attribution."
            ),
            "formula": "Σ per-lead MAX(exposure) where lead.status ∈ lost/dead AND no confirmed recovery",
            "data_source": "leads.status ⨝ deduplicated exposure",
            "tier": Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        },
        {
            "metric": "recoverable_opportunity",
            "label": "Recoverable Revenue Opportunity",
            "definition": (
                "Share of Revenue at Risk that could realistically be recovered "
                "through interventions, using the organization's own recovery "
                "history when statistically sufficient."
            ),
            "formula": "Σ per-lead MAX(exposure) × recovery_probability",
            "data_source": (
                f"recovery_probability: {recovery_rate_info.get('source')} "
                f"(n={recovery_rate_info.get('sample_size')})"
            ),
            "tier": Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        },
        {
            "metric": "confirmed_recovered",
            "label": "Confirmed Recovered",
            "definition": (
                "Real booking value from recorded recovery outcomes — the only "
                "fact-tier monetary metric."
            ),
            "formula": "Σ financial_calculations.amount_inr where tier=confirmed_recovered_revenue",
            "data_source": "recovery_outcomes (recorded via intervention outcomes)",
            "tier": Tier.CONFIRMED_RECOVERED_REVENUE.value,
        },
    ]


async def get_financial_summary(db: AsyncSession, organization_id: Any) -> FinancialSummary:
    """Compute every canonical metric in one pass (per-lead deduplicated)."""
    settings = get_settings()
    per_lead = await canonical_per_lead_exposure(db, organization_id)
    statuses = await _lead_status_map(db, organization_id, list(per_lead.keys()))

    revenue_at_risk = Decimal("0")
    pipeline_at_risk = Decimal("0")
    realized_loss = Decimal("0")
    for lead_id, exposure in per_lead.items():
        revenue_at_risk += exposure
        status = (statuses.get(lead_id) or "").lower()
        if status in ACTIVE_PIPELINE_STATUSES:
            pipeline_at_risk += exposure
        if status in ABANDONMENT_STATUSES:
            realized_loss += exposure

    recovered = await confirmed_recovered_total(db, organization_id)
    rate_info = await _recovery_rate(db, organization_id)

    recoverable = (revenue_at_risk * Decimal(str(rate_info["probability"]))).quantize(Decimal("0.01"))
    uncertainty: UncertaintyRange = exposure_uncertainty(
        float(revenue_at_risk), _rate_to_empirical(rate_info)
    )

    from datetime import datetime, timezone
    return FinancialSummary(
        revenue_at_risk=revenue_at_risk.quantize(Decimal("0.01")),
        pipeline_at_risk=pipeline_at_risk.quantize(Decimal("0.01")),
        realized_loss=realized_loss.quantize(Decimal("0.01")),
        recoverable_opportunity=recoverable,
        confirmed_recovered=recovered,
        leaking_lead_count=len(per_lead),
        recovery_rate=rate_info,
        uncertainty=uncertainty.to_dict(),
        metric_definitions=metric_definitions(rate_info),
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )


def _rate_to_empirical(rate_info: dict[str, Any]):
    from app.core.statistics.benchmarks import EmpiricalResult
    return EmpiricalResult(
        value=rate_info["probability"],
        source=rate_info["source"],
        sample_size=rate_info["sample_size"],
        sufficient=rate_info["sufficient"],
        insufficient_sample_size=rate_info["insufficient_sample_size"],
        ci_low=rate_info.get("ci_low"),
        ci_high=rate_info.get("ci_high"),
        note=rate_info.get("note", ""),
    )


async def exposure_by_category(
    db: AsyncSession, organization_id: Any
) -> list[dict[str, Any]]:
    """Per-category leakage stats — counts, affected leads, deduped exposure.

    Within one category a lead appears at most once (per-(lead, category)
    detector dedup upstream), so each category total is per-lead deduplicated.
    Cross-category totals are NOT additive — revenue_at_risk is the canonical
    deduplicated total.
    """
    stmt = (
        select(
            LeakageEvent.category,
            func.count(LeakageEvent.id).label("event_count"),
            func.count(func.distinct(LeakageEvent.source_entity_id)).label("lead_count"),
        )
        .where(
            LeakageEvent.organization_id == organization_id,
            LeakageEvent.source_entity_type == "lead",
        )
        .group_by(LeakageEvent.category)
    )
    result = await db.execute(stmt)

    per_lead = await canonical_per_lead_exposure(db, organization_id)

    # Per-lead exposure attributed to each category where the lead leaks
    cat_stmt = select(
        LeakageEvent.category,
        LeakageEvent.source_entity_id,
    ).where(
        LeakageEvent.organization_id == organization_id,
        LeakageEvent.source_entity_type == "lead",
    )
    cat_rows = (await db.execute(cat_stmt)).all()
    category_exposure: dict[str, Decimal] = {}
    for row in cat_rows:
        exposure = per_lead.get(str(row.source_entity_id))
        if exposure is not None:
            category_exposure[row.category] = (
                category_exposure.get(row.category, Decimal("0")) + exposure
            )

    items = []
    for row in result.all():
        category = row.category
        items.append({
            "category": category,
            "event_count": int(row.event_count or 0),
            "affected_leads": int(row.lead_count or 0),
            # Deduplicated per-lead exposure within this category
            "exposure": float(category_exposure.get(category, Decimal("0"))),
            # NOTE: raw per-event sums are NOT additive across detectors;
            # `exposure` is the per-lead deduplicated figure used by KPIs.
            "additivity_note": (
                "Category exposures overlap (a lead can leak in several "
                "categories); the canonical total is revenue_at_risk, not the "
                "sum of categories."
            ),
        })
    items.sort(key=lambda i: i["exposure"], reverse=True)
    return items