"""Leakage event model — detected revenue leakage instances."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.timestamps import utc_now


class LeakageEvent(Base):
    __tablename__ = "leakage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "lead"
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    # Deterministic detector identity, e.g. "funnel_leakage.dark_leads"
    detector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Severity bucket assigned by the detector: critical | high | medium | low
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now
    )

    # Relationships
    evidence_items = relationship("LeakageEvidence", back_populates="leakage_event")
    financial_calculations = relationship("FinancialCalculation", back_populates="leakage_event")
    recommendations = relationship("Recommendation", back_populates="leakage_event")
