"""
Recovery service — the ONLY code path that creates CONFIRMED_RECOVERED_REVENUE.

Service-layer guard: no other service/endpoint may create financial_calculations
rows with tier=CONFIRMED_RECOVERED_REVENUE. This is enforced by:
1. This guard check in record_outcome()
2. The FinancialResult.validate() rejection in formulas.py
3. A unit test (test_confirmed_recovery_guard.py) proving it
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import Intervention
from app.models.recovery_outcome import RecoveryOutcome
from app.models.financial_calculation import FinancialCalculation
from app.models.leakage_event import LeakageEvent
from app.models.recommendation import Recommendation
from app.core.financial_engine.tiers import Tier
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)


async def record_outcome(
    db: AsyncSession,
    organization_id: uuid.UUID,
    intervention_id: uuid.UUID,
    outcome_type: str,
    booking_amount_inr: Decimal | None = None,
    evidence: dict[str, Any] | None = None,
) -> RecoveryOutcome:
    """Record a recovery outcome — the ONLY path to CONFIRMED_RECOVERED_REVENUE."""

    intervention = await db.get(Intervention, intervention_id)
    if not intervention:
        raise ValueError(f"Intervention {intervention_id} not found")
    if intervention.organization_id != organization_id:
        raise ValueError("Intervention does not belong to this organization")

    # Create the outcome
    outcome = RecoveryOutcome(
        organization_id=organization_id,
        intervention_id=intervention_id,
        outcome_type=outcome_type,
        booking_amount_inr=booking_amount_inr,
        confirmed_at=datetime.now(timezone.utc),
        evidence=evidence,
    )
    db.add(outcome)
    await db.flush()

    # If converted with a booking amount, create the CONFIRMED_RECOVERED_REVENUE row
    if outcome_type == "converted" and booking_amount_inr and booking_amount_inr > 0:
        # Trace back to the leakage event
        recommendation = await db.get(Recommendation, intervention.recommendation_id)
        if recommendation:
            # Phase 7 guard: never duplicate a confirmed recovery for the same
            # leak. Record the outcome regardless, but only one financial row.
            existing_fc = await db.execute(
                select(FinancialCalculation).where(
                    FinancialCalculation.leakage_event_id == recommendation.leakage_event_id,
                    FinancialCalculation.tier == Tier.CONFIRMED_RECOVERED_REVENUE.value,
                ).limit(1)
            )
            already_confirmed = existing_fc.scalars().first() is not None

            if not already_confirmed:
                fc = FinancialCalculation(
                    organization_id=organization_id,
                    leakage_event_id=recommendation.leakage_event_id,
                    tier=Tier.CONFIRMED_RECOVERED_REVENUE.value,
                    amount_inr=booking_amount_inr,
                    confidence=100.0,  # Confirmed by definition
                    formula_id="confirmed_recovery",
                    formula_version="1.0",
                    assumptions={
                        "outcome_id": str(outcome.id),
                        "intervention_id": str(intervention_id),
                        "booking_amount_inr": float(booking_amount_inr),
                        "confirmed_at": outcome.confirmed_at.isoformat(),
                    },
                    data_source="Recovery Outcome Recording",
                )
                db.add(fc)

            # Update leakage event status
            leakage_event = await db.get(LeakageEvent, recommendation.leakage_event_id)
            if leakage_event:
                leakage_event.status = "resolved"

    # Update intervention status to closed
    intervention.status = "closed"
    await db.flush()

    await log_action(
        db, "outcome_recorded", "recovery_outcome", str(outcome.id),
        after={
            "outcome_type": outcome_type,
            "booking_amount_inr": float(booking_amount_inr) if booking_amount_inr else None,
        },
    )

    return outcome
