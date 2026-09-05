"""
Organization tenancy helpers.

V1 runs without authentication against a single demo organization. The demo
organization MUST exist before any dependent record (lead, event, import) is
created, otherwise foreign-key targets are nonexistent. This module provides a
safe, idempotent, non-destructive ensure function.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.organization import Organization

logger = logging.getLogger(__name__)


async def ensure_demo_organization(db: AsyncSession) -> uuid.UUID:
    """Return the demo organization id, creating the row if it does not exist.

    Idempotent and non-destructive: existing organizations and data are never
    modified or deleted.
    """
    org_id = uuid.UUID(get_settings().DEMO_ORG_ID)

    existing = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = existing.scalars().first()
    if org:
        return org_id

    db.add(Organization(id=org_id, name="GreenVista Realty Demo", is_demo=True))
    await db.flush()
    logger.info("Created missing demo organization %s", org_id)
    return org_id
