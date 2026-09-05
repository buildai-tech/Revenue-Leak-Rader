"""
FastAPI application entry point.

- CORS configured via CORS_ORIGINS environment variable
- No auth middleware (V1 — deferred)
- Background job runner started on lifespan
- Health check at GET /api/health
- Demo organization is auto-ensured (idempotent, non-destructive)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings

settings = get_settings()

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)
logger = logging.getLogger("revenue_radar")


# ── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # Ensure upload directory exists
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Auto-create tables (additive only — never drops or truncates)
    from app.database import engine, Base
    import app.models  # ensure models registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Additive column alignment for pre-existing deployments.
        # `create_all` only creates missing TABLES — it never adds columns to an
        # existing table. These two nullable columns were introduced for the
        # Render ephemeral-storage fix (2026-09-05) so persisted preview
        # metadata can survive a /tmp restart. Idempotent + non-destructive.
        await conn.exec_driver_sql(
            "ALTER TABLE data_imports "
            "ADD COLUMN IF NOT EXISTS persisted_columns TEXT"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE data_imports "
            "ADD COLUMN IF NOT EXISTS persisted_preview_rows TEXT"
        )

    # Ensure the demo organization exists BEFORE any dependent records are
    # created (Phase 17 — tenancy integrity, idempotent & non-destructive).
    from app.database import async_session_factory
    from app.services.org_service import ensure_demo_organization
    async with async_session_factory() as session:
        await ensure_demo_organization(session)
        await session.commit()

    logger.info(
        "Revenue Leak Radar starting — env=%s db=%s",
        settings.APP_ENV,
        "sqlite" if "sqlite" in settings.DATABASE_URL else "postgresql",
    )
    yield
    logger.info("Revenue Leak Radar shutting down")


# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Revenue Leak Radar",
    description="Revenue intelligence for Indian real-estate businesses",
    version="1.0.0",
    lifespan=lifespan,
    # Hide /docs and /redoc in production to reduce attack surface
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return a safe error response — never expose internal stack traces."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


# ── Register routers ──────────────────────────────────────────────────────
from app.api.dashboard import router as dashboard_router
from app.api.imports import router as imports_router
from app.api.leads import router as leads_router
from app.api.leakage import router as leakage_router
from app.api.recommendations import router as recommendations_router
from app.api.interventions import router as interventions_router
from app.api.recovery import router as recovery_router
from app.api.reports import router as reports_router

app.include_router(dashboard_router)
app.include_router(imports_router)
app.include_router(leads_router)
app.include_router(leakage_router)
app.include_router(recommendations_router)
app.include_router(interventions_router)
app.include_router(recovery_router)
app.include_router(reports_router)


# ── Health check ─────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
async def health_check():
    """Health endpoint for load balancers and uptime monitors.

    Returns only safe, non-sensitive information.
    Does NOT expose API keys, DB credentials, or internal state.
    """
    return {
        "status": "healthy",
        "service": "revenue-leak-radar",
        "version": "1.0.0",
        "env": settings.APP_ENV,
    }


@app.get("/api/organization", tags=["system"])
async def get_organization():
    """Return demo organization info for the UI."""
    from app.config import get_settings
    s = get_settings()
    return {
        "id": s.DEMO_ORG_ID,
        "name": "GreenVista Realty Demo",
        "is_demo": True,
    }
