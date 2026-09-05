"""Recommendations API — generate and list."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.leakage_event import LeakageEvent
from app.models.lead import Lead
from app.models.recommendation import Recommendation
from app.ai.recommendation_writer import generate_recommendation_copy
from app.ai.llm_provider import get_llm_provider
from app.schemas.schemas import RecommendationCreate, RecommendationResponse

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.post("/generate", response_model=RecommendationResponse)
async def generate_recommendation(
    body: RecommendationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Generate a recommendation for a leakage event."""
    org_id = _org_id()

    event = await db.get(LeakageEvent, uuid.UUID(body.leakage_event_id))
    if not event:
        raise HTTPException(404, "Leakage event not found")

    lead = None
    if event.source_entity_type == "lead":
        lead = await db.get(Lead, event.source_entity_id)

    # Build lead context for template substitution
    lead_context = {
        "lead_name": lead.name if lead else "Unknown",
        "status": lead.status or "unknown" if lead else "unknown",
        "budget": f"{float(lead.budget):,.0f}" if lead and lead.budget else "not disclosed",
        "project_name": "the project",
        "sales_rep_name": "the assigned representative",
    }

    # Get project name
    if lead and lead.project_id:
        from app.models.project import Project
        project = await db.get(Project, lead.project_id)
        if project:
            lead_context["project_name"] = project.name

    # Get sales rep name
    if lead and lead.sales_rep_id:
        from app.models.sales_rep import SalesRep
        rep = await db.get(SalesRep, lead.sales_rep_id)
        if rep:
            lead_context["sales_rep_name"] = rep.name

    # Deterministic playbook selection + template
    playbook_key, title, copy = generate_recommendation_copy(event.category, lead_context)

    # Try LLM personalization (graceful fallback to template)
    generated_by = "template"
    try:
        llm = get_llm_provider()
        personalized = await llm.personalize_recommendation(copy, lead_context)
        if personalized and personalized != copy:
            copy = personalized
            generated_by = "llm"
    except Exception:
        pass  # Fallback to template copy

    rec = Recommendation(
        organization_id=org_id,
        leakage_event_id=event.id,
        playbook_key=playbook_key,
        generated_copy=copy,
        generated_by=generated_by,
    )
    db.add(rec)
    await db.flush()

    return RecommendationResponse(
        id=str(rec.id),
        leakage_event_id=str(event.id),
        playbook_key=playbook_key,
        generated_copy=copy,
        generated_by=generated_by,
        lead_name=lead.name if lead else None,
        category=event.category,
        created_at=rec.created_at.isoformat() if rec.created_at else None,
    )


@router.get("", response_model=list[RecommendationResponse])
async def list_recommendations(db: AsyncSession = Depends(get_db)):
    """List all recommendations."""
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.organization_id == _org_id())
        .order_by(Recommendation.created_at.desc())
    )
    recs = result.scalars().all()

    items = []
    for rec in recs:
        event = await db.get(LeakageEvent, rec.leakage_event_id)
        lead = None
        if event and event.source_entity_type == "lead":
            lead = await db.get(Lead, event.source_entity_id)

        items.append(RecommendationResponse(
            id=str(rec.id),
            leakage_event_id=str(rec.leakage_event_id),
            playbook_key=rec.playbook_key,
            generated_copy=rec.generated_copy,
            generated_by=rec.generated_by,
            lead_name=lead.name if lead else None,
            category=event.category if event else None,
            created_at=rec.created_at.isoformat() if rec.created_at else None,
        ))

    return items
