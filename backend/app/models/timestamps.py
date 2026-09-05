"""
Cross-database timestamp defaults.

`datetime.now(timezone.utc)` is evaluated by SQLAlchemy on the Python side and
sent as a bound parameter, so ORM inserts work identically on SQLite (dev) and
PostgreSQL (prod) without relying on any database-specific SQL function.

The timestamp columns keep their `server_default=func.now()` as a database-side
fallback for non-ORM writes; SQLAlchemy renders that as CURRENT_TIMESTAMP on
SQLite and now() on PostgreSQL, so it is safe on both backends.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Python-side default for timestamp columns (works on every backend)."""
    return datetime.now(timezone.utc)
