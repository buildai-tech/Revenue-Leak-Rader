"""Interventions API — CRUD with status flow."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.intervention import Intervention
from app.models.recommendation import Recommendation
from app.models.leakage_event import LeakageEvent
from app.models.lead import Lead
from app.services.audit_service import log_action
from app.schemas.schemas import InterventionCreate, InterventionUpdate, InterventionResponse

router = APIRouter(prefix="/api/interventions", tags=["interventions"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.post("", response_model=InterventionResponse)
async def create_intervention(
    body: InterventionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new intervention."""
    org_id = _org_id()

    rec = await db.get(Recommendation, uuid.UUID(body.recommendation_id))
    if not rec:
        raise HTTPException(404, "Recommendation not found")

    intervention = Intervention(
        organization_id=org_id,
        recommendation_id=rec.id,
        assigned_rep_name=body.assigned_rep_name,
        status="pending",
        notes=body.notes,
    )
    db.add(intervention)
    await db.flush()

    await log_action(
        db, "intervention_created", "intervention", str(intervention.id),
        after={"assigned_rep_name": body.assigned_rep_name, "status": "pending"},
    )

    return await _to_response(db, intervention)


@router.get("", response_model=list[InterventionResponse])
async def list_interventions(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List interventions, optionally filtered by status."""
    stmt = select(Intervention).where(Intervention.organization_id == _org_id())
    if status:
        stmt = stmt.where(Intervention.status == status)
    stmt = stmt.order_by(Intervention.created_at.desc())

    result = await db.execute(stmt)
    interventions = result.scalars().all()

    return [await _to_response(db, i) for i in interventions]


@router.patch("/{intervention_id}", response_model=InterventionResponse)
async def update_intervention(
    intervention_id: str,
    body: InterventionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update intervention status/notes."""
    intervention = await db.get(Intervention, uuid.UUID(intervention_id))
    if not intervention:
        raise HTTPException(404, "Intervention not found")

    before = {"status": intervention.status, "notes": intervention.notes}

    if body.status:
        valid = ["pending", "contacted", "in_progress", "closed"]
        if body.status not in valid:
            raise HTTPException(400, f"Invalid status. Must be one of: {valid}")
        intervention.status = body.status
    if body.notes is not None:
        intervention.notes = body.notes
    if body.assigned_rep_name is not None:
        intervention.assigned_rep_name = body.assigned_rep_name

    await db.flush()

    await log_action(
        db, "intervention_updated", "intervention", str(intervention.id),
        before=before,
        after={"status": intervention.status, "notes": intervention.notes},
    )

    return await _to_response(db, intervention)


async def _to_response(db: AsyncSession, intervention: Intervention) -> InterventionResponse:
    """Convert an intervention to its API response shape."""
    rec = await db.get(Recommendation, intervention.recommendation_id)
    event = await db.get(LeakageEvent, rec.leakage_event_id) if rec else None
    lead = None
    if event and event.source_entity_type == "lead":
        lead = await db.get(Lead, event.source_entity_id)

    return InterventionResponse(
        id=str(intervention.id),
        recommendation_id=str(intervention.recommendation_id),
        assigned_rep_name=intervention.assigned_rep_name,
        status=intervention.status,
        notes=intervention.notes,
        lead_name=lead.name if lead else None,
        category=event.category if event else None,
        playbook_key=rec.playbook_key if rec else None,
        created_at=intervention.created_at.isoformat() if intervention.created_at else None,
        updated_at=intervention.updated_at.isoformat() if intervention.updated_at else None,
    )
