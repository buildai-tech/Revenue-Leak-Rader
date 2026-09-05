"""Audit log service — writes audit entries with fixed system actor."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, SYSTEM_ACTOR


async def log_action(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Create an audit log entry."""
    entry = AuditLog(
        actor=SYSTEM_ACTOR,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
    )
    db.add(entry)
    await db.flush()
