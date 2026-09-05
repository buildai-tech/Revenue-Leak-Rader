"""Test leakage detection after migration."""
import asyncio
import uuid
from app.database import async_session_factory
from app.services.leakage_service import detect_leakage_for_organization
from app.config import get_settings

async def main():
    settings = get_settings()
    org_id = uuid.UUID(settings.DEMO_ORG_ID)
    async with async_session_factory() as db:
        stats = await detect_leakage_for_organization(db, org_id)
        print("Detection stats:", stats)
        await db.commit()

asyncio.run(main())
