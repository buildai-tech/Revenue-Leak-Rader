"""Data import model — tracks CSV/XLSX uploads."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ImportStatus
from app.models.timestamps import utc_now


class DataImport(Base):
    __tablename__ = "data_imports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # csv, xlsx
    raw_storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ImportStatus.UPLOADED.value
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Persisted metadata so column-mapping suggestions survive ephemeral-storage
    # restarts on Render (where /tmp files are lost on cold-start).
    # Stored as JSON strings; accessed via the columns_preview_rows helpers.
    persisted_columns: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    persisted_preview_rows: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utc_now
    )

    @property
    def columns_list(self) -> list[str]:
        """Decode persisted columns JSON, or return [] if not set."""
        if not self.persisted_columns:
            return []
        try:
            return json.loads(self.persisted_columns)
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def preview_rows_list(self) -> list[dict]:
        """Decode persisted preview rows JSON, or return [] if not set."""
        if not self.persisted_preview_rows:
            return []
        try:
            return json.loads(self.persisted_preview_rows)
        except (json.JSONDecodeError, TypeError):
            return []
