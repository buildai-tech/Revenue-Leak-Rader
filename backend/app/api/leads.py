"""Leads API — list, search, filters, detail with recovery score."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.project import Project
from app.models.sales_rep import SalesRep
from app.models.leakage_event import LeakageEvent
from app.models.financial_calculation import FinancialCalculation
from app.core.rules.lead_leakage import LeadData, evaluate_all_rules
from app.core.rules.lead_recovery_score import calculate_recovery_score
from app.schemas.schemas import LeadListItem, LeadListResponse, LeadDetail

router = APIRouter(prefix="/api/leads", tags=["leads"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    sales_rep_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List leads with pagination, search, and filters."""
    org_id = _org_id()
    base = select(Lead).where(
        Lead.organization_id == org_id,
        Lead.merged_into_lead_id.is_(None),
    )

    if search:
        base = base.where(
            or_(
                Lead.name.ilike(f"%{search}%"),
                Lead.phone_normalized.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
            )
        )
    if status:
        base = base.where(Lead.status == status)
    if project_id:
        base = base.where(Lead.project_id == uuid.UUID(project_id))
    if sales_rep_id:
        base = base.where(Lead.sales_rep_id == uuid.UUID(sales_rep_id))

    # Count
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    leads_result = await db.execute(
        base.order_by(Lead.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    leads = list(leads_result.scalars().all())

    items = []
    for lead in leads:
        project = await db.get(Project, lead.project_id) if lead.project_id else None
        rep = await db.get(SalesRep, lead.sales_rep_id) if lead.sales_rep_id else None

        items.append(LeadListItem(
            id=str(lead.id),
            name=lead.name,
            phone_normalized=lead.phone_normalized,
            email=lead.email,
            status=lead.status,
            budget=float(lead.budget) if lead.budget else None,
            source=lead.source,
            project_name=project.name if project else None,
            sales_rep_name=rep.name if rep else None,
            created_at=lead.created_at.isoformat() if lead.created_at else None,
        ))

    return LeadListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead_detail(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get full lead detail with recovery score and activity timeline."""
    lead = await db.get(Lead, uuid.UUID(lead_id))
    if not lead:
        from fastapi import HTTPException
        raise HTTPException(404, "Lead not found")

    project = await db.get(Project, lead.project_id) if lead.project_id else None
    rep = await db.get(SalesRep, lead.sales_rep_id) if lead.sales_rep_id else None

    # Get events
    events_result = await db.execute(
        select(LeadEvent)
        .where(LeadEvent.lead_id == lead.id)
        .order_by(LeadEvent.occurred_at.asc())
    )
    events = list(events_result.scalars().all())

    # Calculate recovery score
    event_dicts = [
        {
            "event_type": e.event_type,
            "occurred_at": e.occurred_at,
            "event_payload": e.event_payload,
            "source": e.source,
        }
        for e in events
    ]
    lead_data = LeadData(
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
    rule_results = evaluate_all_rules(lead_data)
    recovery = calculate_recovery_score(rule_results)

    # Get leakage events for this lead
    leakage_result = await db.execute(
        select(LeakageEvent)
        .where(LeakageEvent.source_entity_id == lead.id)
        .order_by(LeakageEvent.created_at.desc())
    )
    leakage_events = leakage_result.scalars().all()

    return LeadDetail(
        id=str(lead.id),
        name=lead.name,
        phone_normalized=lead.phone_normalized,
        phone_raw=lead.phone_raw,
        email=lead.email,
        status=lead.status,
        status_raw=lead.status_raw,
        budget=float(lead.budget) if lead.budget else None,
        source=lead.source,
        project_name=project.name if project else None,
        project_id=str(lead.project_id) if lead.project_id else None,
        sales_rep_name=rep.name if rep else None,
        sales_rep_id=str(lead.sales_rep_id) if lead.sales_rep_id else None,
        recovery_score=recovery.score,
        risk_level=recovery.risk_level,
        contributing_factors=recovery.contributing_factors,
        events=[
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                "event_payload": e.event_payload,
                "source": e.source,
            }
            for e in events
        ],
        leakage_events=[
            {
                "id": str(le.id),
                "category": le.category,
                "title": le.title,
                "status": le.status,
                "created_at": le.created_at.isoformat() if le.created_at else None,
            }
            for le in leakage_events
        ],
        created_at=lead.created_at.isoformat() if lead.created_at else None,
        last_followup_at=lead.last_followup_at.isoformat() if lead.last_followup_at else None,
    )
