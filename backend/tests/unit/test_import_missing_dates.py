"""
Regression tests for the 2026-09-05 production incident:

A CSV import completed with "Leads Created: 0" while the UI reported
"Pipeline Execution Complete!" for an 8-row file.

ROOT CAUSE (before fix):
    process_import() calls `_as_utc(parse_date(value))` for five optional
    timestamp targets (first_contact_at, last_followup_at, site_visit_at,
    negotiation_at, closed_at).  `_as_utc` did not tolerate None, so a
    missing/empty/unparseable optional date raised
    AttributeError: 'NoneType' object has no attribute 'tzinfo'.
    The per-row try/except swallowed it, counted an error, and skipped the
    row — every valid row was rejected, yet the import finished COMPLETED
    with zero leads.

FIX:
    `_as_utc(dt: datetime | None) -> datetime | None` now returns None when
    `dt is None` (mirroring the already-correct `_utc()` in
    app/core/derived.py).  Optional timestamps stay None on the Lead row;
    required `created_at` still falls back to ingestion time and is flagged.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.column_mapping import ColumnMapping
from app.models.data_import import DataImport
from app.models.enums import ImportStatus
from app.models.lead import Lead
from app.models.organization import Organization
from app.services import import_service


# A typical real-world CRM export: NO site-visit/negotiation/closed/contact
# date columns at all. Every optional timestamp is therefore missing — this
# is exactly the shape of the production CSV that produced 0 leads.
TYPICAL_CSV = (
    "Lead Name,Phone,Email,Status,Budget\n"
    "Aarav Sharma,+919876543210,aarav@example.com,New,2500000\n"
    "Ananya Verma,+919876543211,ananya@example.com,Contacted,3500000\n"
    "Rohan Mehta,+919876543212,rohan@example.com,New,4200000\n"
)

# Mixed CSV: some rows have a real enquiry date, others have unparseable
# or blank optional timestamps. No row may be silently dropped for it.
MIXED_CSV = (
    "Lead Name,Phone,Email,Enquiry Date,First Contact,Site Visit,Closed\n"
    "Aarav Sharma,+919876543210,aarav@example.com,2026-08-01 10:00:00,2026-08-01 11:00:00,2026-08-05 10:00:00,2026-08-12 10:00:00\n"
    "Ananya Verma,+919876543211,ananya@example.com,not-a-date,,,\n"
    "Rohan Mehta,+919876543212,rohan@example.com,2026-08-03 09:30:00,,2026-08-04 08:00:00,\n"
)


@pytest.fixture
async def test_session():
    """Isolated in-memory async SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _make_import(db, csv_text, column_names, mappings):
    """Create an org, an UPLOADED import with a real file, and confirmed mappings."""
    import tempfile
    from pathlib import Path

    org = Organization(id=uuid.uuid4(), name="Regression Org", is_demo=True)
    db.add(org)
    await db.flush()

    tmpdir = Path(tempfile.mkdtemp())
    csv_path = tmpdir / "leads.csv"
    csv_path.write_text(csv_text, encoding="utf-8")

    imp = DataImport(
        id=uuid.uuid4(),
        organization_id=org.id,
        filename="leads.csv",
        file_type="csv",
        raw_storage_path=str(csv_path),
        status=ImportStatus.UPLOADED.value,
        persisted_columns=json.dumps(column_names),
        persisted_preview_rows="[]",
    )
    db.add(imp)
    await db.flush()

    for source_column, target_field in mappings:
        db.add(ColumnMapping(
            organization_id=org.id,
            import_id=imp.id,
            source_column=source_column,
            target_field=target_field,
            confirmed=True,
            confidence=1.0,
            suggested_by="heuristic",
        ))
    await db.flush()
    return imp


# ── Regression: the exact production symptom — 0 leads on a valid CSV ───────

@pytest.mark.asyncio
async def test_typical_csv_without_date_columns_creates_leads(test_session, monkeypatch, capsys):
    """A CSV with only name/phone/email/status/budget must create a lead per row.

    Before the fix every row crashed on `_as_utc(None)` and the import
    "completed" with leads_created == 0.
    """
    mappings = [
        ("Lead Name", "name"), ("Phone", "phone_raw"), ("Email", "email"),
        ("Status", "status"), ("Budget", "budget"),
    ]
    imp = await _make_import(
        test_session, TYPICAL_CSV,
        ["Lead Name", "Phone", "Email", "Status", "Budget"], mappings,
    )

    stats = await import_service.process_import(test_session, imp.id, imp.organization_id)

    assert stats["total_rows"] == 3
    assert stats["leads_created"] == 3
    assert stats["errors"] == 0
    assert stats["events_created"] >= 3  # one "created" event per lead

    await test_session.refresh(imp)
    assert imp.status == ImportStatus.COMPLETED.value

    # No per-row processing errors must have been logged to the server console.
    captured = capsys.readouterr()
    assert "Error processing row" not in captured.out + captured.err

    # Leads really exist in the database with nullable optional timestamps.
    leads = (await test_session.execute(select(Lead))).scalars().all()
    assert len(leads) == 3
    for lead in leads:
        assert lead.created_from_import_id == imp.id
        assert lead.created_at is not None
        assert lead.created_at_is_estimated is True  # no source created_at
        assert lead.first_contact_at is None
        assert lead.closed_at is None


# ── Regression: mixed parseable / unparseable / blank optional dates ─────────

@pytest.mark.asyncio
async def test_mixed_dates_still_create_leads(test_session, monkeypatch, capsys):
    """Rows with unparseable or blank optional timestamps must not be rejected.

    An unparseable enquiry date falls back to ingestion time (flagged
    estimated); the other optionals simply stay None.
    """
    mappings = [
        ("Lead Name", "name"), ("Phone", "phone_raw"), ("Email", "email"),
        ("Enquiry Date", "created_at"), ("First Contact", "first_contact_at"),
        ("Site Visit", "site_visit_at"), ("Closed", "closed_at"),
    ]
    imp = await _make_import(
        test_session, MIXED_CSV,
        ["Lead Name", "Phone", "Email", "Enquiry Date", "First Contact",
         "Site Visit", "Closed"], mappings,
    )

    stats = await import_service.process_import(test_session, imp.id, imp.organization_id)

    assert stats["total_rows"] == 3
    assert stats["leads_created"] == 3
    assert stats["errors"] == 0

    leads = (await test_session.execute(select(Lead))).scalars().all()
    assert len(leads) == 3

    # Row 1: all dates present → not estimated, site_visit populated.
    row1 = next(l for l in leads if l.email == "aarav@example.com")
    assert row1.created_at_is_estimated is False
    assert row1.first_contact_at is not None
    assert row1.site_visit_at is not None
    assert row1.closed_at is not None

    # Row 2: unparseable enquiry date → ingestion-time fallback, flagged.
    row2 = next(l for l in leads if l.email == "ananya@example.com")
    assert row2.created_at_is_estimated is True
    assert row2.first_contact_at is None
    assert row2.site_visit_at is None

    # Row 3: parseable created_at, blank contact/site/closed → None stays None.
    row3 = next(l for l in leads if l.email == "rohan@example.com")
    assert row3.created_at_is_estimated is False
    assert row3.first_contact_at is None
    assert row3.site_visit_at is not None
    assert row3.closed_at is None

    # Invalid rows must STILL be rejected in the normal, pre-existing way:
    # a missing required `name` is rejected, not silently dropped by crash.
    captured = capsys.readouterr()
    assert "Error processing row" not in captured.out + captured.err


# ── Regression: required-field validation is preserved ───────────────────────

@pytest.mark.asyncio
async def test_rows_missing_name_are_still_rejected(test_session):
    """The fix must not weaken validation — rows without a mapped `name`
    are still rejected and counted as errors."""
    csv = (
        "Lead Name,Phone,Email\n"
        "Aarav Sharma,+919876543210,aarav@example.com\n"
        ",+919876543211,anon@example.com\n"
        " ,+919876543212,anon2@example.com\n"
    )
    mappings = [("Lead Name", "name"), ("Phone", "phone_raw"), ("Email", "email")]
    imp = await _make_import(
        test_session, csv, ["Lead Name", "Phone", "Email"], mappings,
    )

    stats = await import_service.process_import(test_session, imp.id, imp.organization_id)

    assert stats["leads_created"] == 1
    assert stats["errors"] == 2  # blank and whitespace-only `name` rows