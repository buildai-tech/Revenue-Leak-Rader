"""Recommendation model — playbook-selected actions for leakage events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.timestamps import utc_now


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    leakage_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("leakage_events.id"), nullable=False, index=True
    )
    playbook_key: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_copy: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(50), nullable=False)  # "template", "llm"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now
    )

    leakage_event = relationship("LeakageEvent", back_populates="recommendations")
    interventions = relationship("Intervention", back_populates="recommendation")
