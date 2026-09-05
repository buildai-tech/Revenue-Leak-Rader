"""Reports API — aggregated data for the reports page."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.lead import Lead
from app.models.leakage_event import LeakageEvent
from app.models.financial_calculation import FinancialCalculation
from app.models.intervention import Intervention
from app.models.recovery_outcome import RecoveryOutcome
from app.models.sales_rep import SalesRep
from app.models.project import Project
from app.core.financial_engine.tiers import Tier

router = APIRouter(prefix="/api/reports", tags=["reports"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.get("/overview")
async def report_overview(db: AsyncSession = Depends(get_db)):
    """High-level report overview with real aggregated numbers."""
    org_id = _org_id()

    total_leads = (await db.execute(
        select(func.count(Lead.id)).where(
            Lead.organization_id == org_id,
            Lead.merged_into_lead_id.is_(None),
        )
    )).scalar() or 0

    total_leakage = (await db.execute(
        select(func.count(LeakageEvent.id)).where(LeakageEvent.organization_id == org_id)
    )).scalar() or 0

    total_impact = (await db.execute(
        select(func.coalesce(func.sum(FinancialCalculation.amount_inr), 0)).where(
            FinancialCalculation.organization_id == org_id,
            FinancialCalculation.tier == Tier.ESTIMATED_FINANCIAL_IMPACT.value,
        )
    )).scalar() or 0

    total_recovered = (await db.execute(
        select(func.coalesce(func.sum(FinancialCalculation.amount_inr), 0)).where(
            FinancialCalculation.organization_id == org_id,
            FinancialCalculation.tier == Tier.CONFIRMED_RECOVERED_REVENUE.value,
        )
    )).scalar() or 0

    total_interventions = (await db.execute(
        select(func.count(Intervention.id)).where(Intervention.organization_id == org_id)
    )).scalar() or 0

    # Leakage by category
    category_result = await db.execute(
        select(
            LeakageEvent.category,
            func.count(LeakageEvent.id).label("count"),
        )
        .where(LeakageEvent.organization_id == org_id)
        .group_by(LeakageEvent.category)
    )
    by_category = [{"category": r.category, "count": r.count} for r in category_result.all()]

    # Leakage by project
    project_result = await db.execute(
        select(
            Project.name.label("project_name"),
            func.count(LeakageEvent.id).label("count"),
        )
        .join(Lead, Lead.id == LeakageEvent.source_entity_id)
        .join(Project, Project.id == Lead.project_id)
        .where(LeakageEvent.organization_id == org_id)
        .group_by(Project.name)
    )
    by_project = [{"project": r.project_name, "count": r.count} for r in project_result.all()]

    return {
        "total_leads": total_leads,
        "total_leakage_events": total_leakage,
        "leakage_rate": round(total_leakage / total_leads * 100, 1) if total_leads > 0 else 0,
        "total_estimated_impact": float(total_impact),
        "total_confirmed_recovered": float(total_recovered),
        "total_interventions": total_interventions,
        "by_category": by_category,
        "by_project": by_project,
    }
