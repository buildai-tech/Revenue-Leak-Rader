"""
Revenue-at-risk deduplication.

A lead flagged under multiple leakage categories must NOT be double-counted
in the deduplicated revenue-at-risk sum. This module implements that logic.

The dedup is per source_entity_id (lead ID) — if a lead has multiple
leakage events, only the highest financial impact is counted.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leakage_event import LeakageEvent
from app.models.financial_calculation import FinancialCalculation
from app.core.financial_engine.tiers import Tier


async def deduplicated_revenue_at_risk(
    db: AsyncSession, organization_id: Any
) -> Decimal:
    """Calculate the deduplicated revenue at risk.

    For each unique lead (source_entity_id), takes the maximum
    ESTIMATED_FINANCIAL_IMPACT across all its leakage events.
    This prevents double-counting when a lead triggers multiple rules.

    Returns the sum of these per-lead maximums.
    """
    # Subquery: max financial impact per lead (source_entity_id)
    subq = (
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
            FinancialCalculation.tier == Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        )
        .group_by(LeakageEvent.source_entity_id)
        .subquery()
    )

    # Sum all per-lead maximums
    stmt = select(func.coalesce(func.sum(subq.c.max_amount), Decimal("0")))
    result = await db.execute(stmt)
    total = result.scalar()
    return Decimal(str(total)) if total else Decimal("0")


async def confirmed_recovered_total(
    db: AsyncSession, organization_id: Any
) -> Decimal:
    """Sum of all CONFIRMED_RECOVERED_REVENUE amounts.

    This is always a separate figure from revenue-at-risk.
    """
    stmt = (
        select(func.coalesce(func.sum(FinancialCalculation.amount_inr), Decimal("0")))
        .where(
            FinancialCalculation.organization_id == organization_id,
            FinancialCalculation.tier == Tier.CONFIRMED_RECOVERED_REVENUE.value,
        )
    )
    result = await db.execute(stmt)
    total = result.scalar()
    return Decimal(str(total)) if total else Decimal("0")
