"""Financial calculation model — every rupee figure with full provenance."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, ForeignKey, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.timestamps import utc_now


class FinancialCalculation(Base):
    __tablename__ = "financial_calculations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    leakage_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("leakage_events.id"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    formula_id: Mapped[str] = mapped_column(String(100), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(20), nullable=False)
    assumptions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_source: Mapped[str] = mapped_column(String(255), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now
    )

    leakage_event = relationship("LeakageEvent", back_populates="financial_calculations")
