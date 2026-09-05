"""Leakage events API — list, detail, evidence."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.leakage_event import LeakageEvent
from app.models.leakage_evidence import LeakageEvidence
from app.models.financial_calculation import FinancialCalculation
from app.models.lead import Lead
from app.schemas.schemas import LeakageEventDetail, LeakageListResponse

router = APIRouter(prefix="/api/leakage", tags=["leakage"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.get("", response_model=LeakageListResponse)
async def list_leakage_events(
    category: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List leakage events with filters."""
    org_id = _org_id()
    base = select(LeakageEvent).where(LeakageEvent.organization_id == org_id)

    if category:
        base = base.where(LeakageEvent.category == category)
    if status:
        base = base.where(LeakageEvent.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        base.order_by(LeakageEvent.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    events = list(result.scalars().all())

    items = []
    for event in events:
        lead = None
        if event.source_entity_type == "lead":
            lead = await db.get(Lead, event.source_entity_id)

        # Get financial info
        fc_result = await db.execute(
            select(FinancialCalculation)
            .where(FinancialCalculation.leakage_event_id == event.id)
            .limit(1)
        )
        fc = fc_result.scalars().first()

        items.append(LeakageEventDetail(
            id=str(event.id),
            category=event.category,
            title=event.title,
            status=event.status,
            tier=event.tier,
            lead_name=lead.name if lead else None,
            lead_id=str(event.source_entity_id),
            financial={
                "amount_inr": float(fc.amount_inr) if fc else None,
                "confidence": fc.confidence if fc else None,
                "tier": fc.tier if fc else None,
                "formula_id": fc.formula_id if fc else None,
                "formula_version": fc.formula_version if fc else None,
                "assumptions": fc.assumptions if fc else None,
                "data_source": fc.data_source if fc else None,
            } if fc else None,
            created_at=event.created_at.isoformat() if event.created_at else None,
        ))

    return LeakageListResponse(items=items, total=total)


@router.get("/{event_id}")
async def get_leakage_detail(event_id: str, db: AsyncSession = Depends(get_db)):
    """Get full leakage event detail with evidence and financial info."""
    event = await db.get(LeakageEvent, uuid.UUID(event_id))
    if not event:
        raise HTTPException(404, "Leakage event not found")

    # Get evidence
    evidence_result = await db.execute(
        select(LeakageEvidence).where(LeakageEvidence.leakage_event_id == event.id)
    )
    evidence_items = evidence_result.scalars().all()

    # Get financial calculations
    fc_result = await db.execute(
        select(FinancialCalculation).where(FinancialCalculation.leakage_event_id == event.id)
    )
    financial_calcs = fc_result.scalars().all()

    # Get lead
    lead = None
    if event.source_entity_type == "lead":
        lead = await db.get(Lead, event.source_entity_id)

    return {
        "id": str(event.id),
        "category": event.category,
        "title": event.title,
        "status": event.status,
        "tier": event.tier,
        "lead_name": lead.name if lead else None,
        "lead_id": str(event.source_entity_id),
        "lead_budget": float(lead.budget) if lead and lead.budget else None,
        "lead_status": lead.status if lead else None,
        "evidence": [
            {
                "id": str(e.id),
                "evidence_type": e.evidence_type,
                "evidence_payload": e.evidence_payload,
            }
            for e in evidence_items
        ],
        "financial_calculations": [
            {
                "id": str(fc.id),
                "tier": fc.tier,
                "amount_inr": float(fc.amount_inr),
                "confidence": fc.confidence,
                "formula_id": fc.formula_id,
                "formula_version": fc.formula_version,
                "assumptions": fc.assumptions,
                "data_source": fc.data_source,
                "calculated_at": fc.calculated_at.isoformat() if fc.calculated_at else None,
            }
            for fc in financial_calcs
        ],
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


@router.patch("/{event_id}/status")
async def update_leakage_status(
    event_id: str,
    status: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Update leakage event status."""
    event = await db.get(LeakageEvent, uuid.UUID(event_id))
    if not event:
        raise HTTPException(404, "Leakage event not found")

    valid_statuses = ["open", "acknowledged", "in_progress", "resolved", "dismissed"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid_statuses}")

    from app.services.audit_service import log_action
    await log_action(
        db, "leakage_status_changed", "leakage_event", str(event.id),
        before={"status": event.status},
        after={"status": status},
    )

    event.status = status
    await db.flush()

    return {"id": str(event.id), "status": event.status}
