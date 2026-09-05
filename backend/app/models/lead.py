"""Lead model — the core entity of the product."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.timestamps import utc_now


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    sales_rep_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_reps.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_normalized: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    phone_raw: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now
    )
    last_followup_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Lifecycle timestamps imported from source data (all verifiable) ────
    first_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    site_visit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    negotiation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Aggregate / source fields preserved from the import ────────────────
    total_touches: Mapped[int | None] = mapped_column(nullable=True)
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campaign_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Deterministic derived fields (computed at import time) ─────────────
    response_latency_minutes: Mapped[float | None] = mapped_column(nullable=True)
    site_visit_latency_days: Mapped[float | None] = mapped_column(nullable=True)
    sales_cycle_days: Mapped[float | None] = mapped_column(nullable=True)
    is_dark_lead: Mapped[bool | None] = mapped_column(nullable=True)
    is_single_touch: Mapped[bool | None] = mapped_column(nullable=True)
    # Highest stage with verified timestamp evidence:
    # 0=created 1=first_contact 2=follow_up 3=site_visit 4=negotiation 5=closed
    funnel_max_stage: Mapped[int | None] = mapped_column(nullable=True)
    data_quality_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_is_estimated: Mapped[bool | None] = mapped_column(nullable=True)

    merged_into_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("leads.id"), nullable=True
    )
    created_from_import_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_imports.id"), nullable=True
    )

    # Relationships
    project = relationship("Project", back_populates="leads")
    sales_rep = relationship("SalesRep", back_populates="leads")
    events = relationship("LeadEvent", back_populates="lead", order_by="LeadEvent.occurred_at")
    merged_into = relationship("Lead", remote_side="Lead.id", foreign_keys=[merged_into_lead_id])
