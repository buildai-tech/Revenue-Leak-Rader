"""Recovery outcome model — the ONLY source of CONFIRMED_RECOVERED_REVENUE."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    intervention_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("interventions.id"), nullable=False, index=True
    )
    outcome_type: Mapped[str] = mapped_column(String(50), nullable=False)
    booking_amount_inr: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    intervention = relationship("Intervention", back_populates="recovery_outcomes")
