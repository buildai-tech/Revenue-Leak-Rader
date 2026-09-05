"""
Application configuration via Pydantic Settings.
Reads from environment variables / .env file.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — every value has a sensible default for local dev."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(Path(__file__).resolve().parent.parent, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./revenue_radar.db"
    DATABASE_URL_SYNC: str = "sqlite:///./revenue_radar.db"

    # ── LLM ───────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "noop"  # "noop" | "nvidia"
    # OpenAI (kept for completeness, not used by default)
    OPENAI_API_KEY: str = ""
    # NVIDIA NIM
    NVIDIA_API_KEY: str = ""
    NVIDIA_MODEL: str = "meta/llama-3.1-70b-instruct"  # NVIDIA NIM catalog default

    # ── Demo ──────────────────────────────────────────────────────────────
    DEMO_ORG_ID: str = "550e8400-e29b-41d4-a716-446655440000"

    # ── Detector thresholds (all overridable via env) ─────────────────────
    # Dark leads: a lead younger than this is NOT a leak — it has not yet had
    # a fair chance to be contacted.
    DARK_LEAD_MIN_AGE_HOURS: float = 24.0
    # Response SLA fallback (minutes) — used ONLY when the empirical benchmark
    # cannot be computed (insufficient sample size).
    RESPONSE_SLA_FALLBACK_MINUTES: float = 60.0
    # Minimum contacted-lead sample size before an empirical SLA benchmark is trusted.
    RESPONSE_SLA_EMPIRICAL_MIN_SAMPLE: int = 20
    # Post-site-visit follow-up black hole window (hours).
    POST_VISIT_FOLLOWUP_HOURS: float = 48.0
    # Negotiation rot: stale negotiation threshold (days).
    NEGOTIATION_STALE_DAYS: float = 14.0

    # ── Financial model ───────────────────────────────────────────────────
    # Recoverable-opportunity default probability, used ONLY when the org's own
    # recovery-outcome history cannot support an empirical rate.
    RECOVERY_PROBABILITY_DEFAULT: float = 0.15
    # Minimum recorded recovery outcomes before an empirical recovery rate is used.
    RECOVERY_RATE_MIN_SAMPLE: int = 20
    # Commission/margin fallback when a lead has no commission_rate of its own.
    DEFAULT_CONTRIBUTION_MARGIN: float = 0.03

    # ── Statistics ────────────────────────────────────────────────────────
    # Minimum sample size for cohort statistics (buckets, conversion rates).
    STATISTICAL_MIN_SAMPLE: int = 20

    # ── File uploads ──────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"

    # ── App ───────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── CORS ──────────────────────────────────────────────────────────────
    # Comma-separated list of allowed frontend origins.
    # In production, set CORS_ORIGINS to your Vercel frontend URL.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ── Server ────────────────────────────────────────────────────────────
    # PORT is injected automatically by Render and other PaaS providers.
    # Leave unset for local development (uvicorn default: 8000).
    PORT: int = 8000

    @model_validator(mode="after")
    def _normalise_database_urls(self) -> "Settings":
        """
        Render (and most PaaS providers) inject a plain ``postgresql://`` or
        ``postgres://`` DATABASE_URL.  SQLAlchemy's async engine requires the
        ``+asyncpg`` driver suffix.  This validator rewrites the URL
        transparently so the app starts correctly on Render without any manual
        environment-variable tweaking.

        Rules
        -----
        * DATABASE_URL      → always uses ``postgresql+asyncpg://``  (async engine)
        * DATABASE_URL_SYNC → always uses ``postgresql://``            (Alembic / psycopg2)
        * SQLite URLs are left untouched.
        """
        _ASYNC_PREFIX = "postgresql+asyncpg://"
        _SYNC_PREFIX  = "postgresql://"

        # Normalise DATABASE_URL → async driver
        url = self.DATABASE_URL
        if url.startswith(("postgres://", "postgresql://")):
            # Strip any existing scheme (e.g. "postgres://", "postgresql://")
            rest = url.split("://", 1)[1]
            self.DATABASE_URL = _ASYNC_PREFIX + rest
        elif url.startswith("postgresql+asyncpg://"):
            pass  # already correct
        # sqlite+aiosqlite:// — leave as-is

        # Normalise DATABASE_URL_SYNC → sync psycopg2 driver
        sync_url = self.DATABASE_URL_SYNC
        if sync_url.startswith(("postgres://", "postgresql://")):
            rest = sync_url.split("://", 1)[1]
            self.DATABASE_URL_SYNC = _SYNC_PREFIX + rest
        elif sync_url.startswith("postgresql+asyncpg://"):
            # If someone accidentally put the async URL in DATABASE_URL_SYNC,
            # strip it back to the sync driver for Alembic compatibility.
            rest = sync_url.split("://", 1)[1]
            self.DATABASE_URL_SYNC = _SYNC_PREFIX + rest
        # sqlite:// — leave as-is

        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
