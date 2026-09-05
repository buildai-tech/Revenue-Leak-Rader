"""Dashboard API — Command Center endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import get_settings
from app.services import dashboard_service
from app.schemas.schemas import (
    DashboardSummary, LeakageBreakdownItem, HighPriorityIssue,
    RecoveryPipeline, RecentRecovery,
)
from app.core.rules.response_leakage import (
    bucket_leads, LeadResponseData,
)
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.schemas.schemas import ResponseLeakageResponse, ResponseBucketSchema

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(db: AsyncSession = Depends(get_db)):
    return await dashboard_service.get_summary(db, _org_id())


@router.get("/leakage-breakdown", response_model=list[LeakageBreakdownItem])
async def get_leakage_breakdown(db: AsyncSession = Depends(get_db)):
    return await dashboard_service.get_leakage_breakdown(db, _org_id())


@router.get("/high-priority", response_model=list[HighPriorityIssue])
async def get_high_priority(limit: int = 20, db: AsyncSession = Depends(get_db)):
    return await dashboard_service.get_high_priority_issues(db, _org_id(), limit)


@router.get("/recovery-pipeline", response_model=RecoveryPipeline)
async def get_recovery_pipeline(db: AsyncSession = Depends(get_db)):
    return await dashboard_service.get_recovery_pipeline(db, _org_id())


@router.get("/recent-recoveries", response_model=list[RecentRecovery])
async def get_recent_recoveries(limit: int = 10, db: AsyncSession = Depends(get_db)):
    return await dashboard_service.get_recent_recoveries(db, _org_id(), limit)


@router.get("/response-leakage", response_model=ResponseLeakageResponse)
async def get_response_leakage(db: AsyncSession = Depends(get_db)):
    """Response leakage analysis with bucketed response times and conversion rates."""
    org_id = _org_id()

    # Get all leads and their first outbound event
    leads_result = await db.execute(
        select(Lead).where(
            Lead.organization_id == org_id,
            Lead.merged_into_lead_id.is_(None),
        )
    )
    leads = list(leads_result.scalars().all())

    lead_response_data = []
    for lead in leads:
        # Find first outbound event
        events_result = await db.execute(
            select(LeadEvent)
            .where(
                LeadEvent.lead_id == lead.id,
                LeadEvent.event_type.in_(["outbound_call", "outbound_message", "outbound_email", "followup"]),
            )
            .order_by(LeadEvent.occurred_at.asc())
            .limit(1)
        )
        first_outbound = events_result.scalars().first()

        lead_response_data.append(LeadResponseData(
            lead_id=str(lead.id),
            created_at=lead.created_at,
            status=lead.status,
            first_outbound_at=first_outbound.occurred_at if first_outbound else None,
        ))

    analysis = bucket_leads(lead_response_data)

    return ResponseLeakageResponse(
        buckets=[
            ResponseBucketSchema(
                bucket_key=b.bucket_key,
                bucket_label=b.bucket_label,
                lead_count=b.lead_count,
                converted_count=b.converted_count,
                conversion_rate=b.conversion_rate,
                sample_too_small=b.sample_too_small,
                avg_response_minutes=b.avg_response_minutes,
            )
            for b in analysis.buckets
        ],
        never_contacted=ResponseBucketSchema(
            bucket_key=analysis.never_contacted.bucket_key,
            bucket_label=analysis.never_contacted.bucket_label,
            lead_count=analysis.never_contacted.lead_count,
            converted_count=analysis.never_contacted.converted_count,
            conversion_rate=analysis.never_contacted.conversion_rate,
            sample_too_small=analysis.never_contacted.sample_too_small,
            avg_response_minutes=analysis.never_contacted.avg_response_minutes,
        ) if analysis.never_contacted else None,
        total_leads=analysis.total_leads,
        leads_with_response=analysis.leads_with_response,
        baseline_conversion_rate=analysis.baseline_conversion_rate,
        correlation_not_causation=analysis.correlation_not_causation,
        disclaimer=analysis.disclaimer,
    )
