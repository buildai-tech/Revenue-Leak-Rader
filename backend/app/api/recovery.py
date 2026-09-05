"""Recovery API — record outcomes (the ONLY path to CONFIRMED_RECOVERED_REVENUE)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.services.recovery_service import record_outcome
from app.schemas.schemas import RecoveryOutcomeCreate, RecoveryOutcomeResponse

router = APIRouter(prefix="/api/recovery", tags=["recovery"])
settings = get_settings()


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.post("/record", response_model=RecoveryOutcomeResponse)
async def record_recovery_outcome(
    body: RecoveryOutcomeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Record a recovery outcome. Only converted outcomes with booking amounts
    create CONFIRMED_RECOVERED_REVENUE financial calculations."""
    try:
        outcome = await record_outcome(
            db=db,
            organization_id=_org_id(),
            intervention_id=uuid.UUID(body.intervention_id),
            outcome_type=body.outcome_type,
            booking_amount_inr=Decimal(str(body.booking_amount_inr)) if body.booking_amount_inr else None,
            evidence=body.evidence,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return RecoveryOutcomeResponse(
        id=str(outcome.id),
        intervention_id=str(outcome.intervention_id),
        outcome_type=outcome.outcome_type,
        booking_amount_inr=float(outcome.booking_amount_inr) if outcome.booking_amount_inr else None,
        confirmed_at=outcome.confirmed_at.isoformat() if outcome.confirmed_at else None,
    )
