"""
Synthetic 10,000-row import performance regression test.

Guards the 2026-09-06 optimization: a 10k-row CSV must import through the
whole pipeline (process → identity → leakage) without the per-row DB round
trips the old code made. Baseline before the fix (local SQLite):
65,043 DB round-trips, 531.8s total, 18.8 rows/s.

This test verifies correctness (10,000 leads, 0 errors, COMPLETED import,
positive leakage + merge stats) AND bounds the pipeline to a small number of
round-trips — a hard cap that any reintroduction of per-row `flush()` breaks.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.expression import Select

from app.database import Base
from app.models.column_mapping import ColumnMapping
from app.models.data_import import DataImport
from app.models.enums import ImportStatus
from app.models.lead import Lead
from app.models.organization import Organization
from app.services.import_service import process_import
from app.core.identity.resolver import resolve_identities
from app.services.leakage_service import detect_leakage_for_organization

N_ROWS = 10_000
ROUND_TRIP_CAP = 2_000  # old code needed ~65k; optimized should be a few hundred
WALL_CLOCK_CAP_S = 300  # very generous CI hygiene ceiling, not a benchmark

MAPPINGS = {
    "full_name": "name", "phone": "phone_raw", "email": "email",
    "status": "status", "budget": "budget", "project_name": "project_name",
    "sales_rep_name": "sales_rep_name", "created_at": "created_at",
    "last_followup_at": "last_followup_at", "total_touches": "total_touches",
    "campaign_name": "campaign_name", "property_type": "property_type",
}


class CountingSession(AsyncSession):
    round_trips = 0
    reads = 0
    writes = 0

    async def execute(self, stmt, *a, **k):
        if isinstance(stmt, Select):
            CountingSession.reads += 1
        else:
            CountingSession.writes += 1
        CountingSession.round_trips += 1
        return await super().execute(stmt, *a, **k)

    async def flush(self, *a, **k):
        CountingSession.round_trips += 1
        CountingSession.writes += 1
        return await super().flush(*a, **k)


@pytest.fixture
async def counting_db(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=CountingSession, expire_on_commit=False)
    CountingSession.round_trips = 0
    CountingSession.reads = 0
    CountingSession.writes = 0
    yield factory
    await engine.dispose()


def _make_csv(path, n: int) -> None:
    """Realistic CRM export: ~2% duplicate phone/email pairs for identity merges."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)
    rows = []
    for i in range(n):
        if i % 50 == 49 and i > 0:
            dup_of = i - 49
            phone = f"+91 98{i % 10:02d}{dup_of:08d}"
            email = f"cust{dup_of}@acme.in"
        else:
            phone = f"+91 98{i % 10:02d}{i:08d}"
            email = f"cust{i}@acme.in"
        contacted = i % 2 == 0
        rows.append({
            "full_name": f"Customer Number {i}",
            "phone": phone,
            "email": email,
            "status": ["new", "contacted", "negotiation", "won", "lost"][i % 5],
            "budget": f"RS.{1000000 + i * 13000:,}" if i % 7 != 3 else "",
            "project_name": f"Project {i % 10}",
            "sales_rep_name": f"Rep {i % 20}",
            "created_at": (old + timedelta(days=i % 40)).isoformat(),
            "last_followup_at": (now - timedelta(days=30)).isoformat() if contacted else "",
            "total_touches": str(i % 6) if contacted else "",
            "campaign_name": f"Campaign {i % 3}" if i % 5 else "",
            "property_type": ["2BHK", "3BHK", "Villa"][i % 3] if i % 4 else "",
        })
    pd.DataFrame(rows).to_csv(path, index=False)


async def _make_import(db, csv_path, mappings) -> DataImport:
    org = Organization(id=uuid.uuid4(), name="10K Perf Org", is_demo=True)
    db.add(org)
    await db.flush()

    imp = DataImport(
        id=uuid.uuid4(),
        organization_id=org.id,
        filename="leads_10k.csv",
        file_type="csv",
        raw_storage_path=str(csv_path),
        status=ImportStatus.UPLOADED.value,
        persisted_columns=json.dumps(list(mappings.keys())),
        persisted_preview_rows="[]",
    )
    db.add(imp)
    await db.flush()

    for source_column, target_field in mappings.items():
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


@pytest.mark.asyncio
async def test_10k_import_pipeline_is_batched_and_correct(counting_db, tmp_path, capsys):
    factory = counting_db
    csv_path = tmp_path / "leads_10k.csv"
    _make_csv(csv_path, N_ROWS)

    async with factory() as db:
        imp = await _make_import(db, csv_path, MAPPINGS)
        org_id = imp.organization_id

        t1 = time.perf_counter()
        import_stats = await process_import(db, imp.id, org_id)
        t2 = time.perf_counter()
        merge_stats = await resolve_identities(db, org_id)
        t3 = time.perf_counter()
        leakage_stats = await detect_leakage_for_organization(db, org_id)
        t4 = time.perf_counter()
        await db.commit()

    # ── Correctness ─────────────────────────────────────────────────────
    assert import_stats["total_rows"] == N_ROWS
    assert import_stats["leads_created"] == N_ROWS
    assert import_stats["errors"] == 0
    assert import_stats["events_created"] >= N_ROWS

    captured = capsys.readouterr()
    assert "Error processing row" not in captured.out + captured.err

    async with factory() as db:
        data_import = await db.get(DataImport, imp.id)
        assert data_import.status == ImportStatus.COMPLETED.value
        assert data_import.row_count == N_ROWS
        assert data_import.error_message is None

        leads_count = (await db.execute(
            select(Lead).where(Lead.created_from_import_id == imp.id)
        )).scalars().all()
        assert len(leads_count) == N_ROWS

    assert leakage_stats["total_leads"] == N_ROWS - merge_stats["total_merges"]
    assert leakage_stats["total_events"] > 0
    assert leakage_stats["sla_benchmark"]["sla_source"] in ("empirical", "configured_fallback")

    # ── Performance bounds ──────────────────────────────────────────────
    total_s = t4 - t1
    assert CountingSession.round_trips < ROUND_TRIP_CAP, (
        f"pipeline made {CountingSession.round_trips} DB round-trips "
        f"(cap {ROUND_TRIP_CAP}) — per-row flush reintroduced?"
    )
    assert total_s < WALL_CLOCK_CAP_S, (
        f"pipeline took {total_s:.1f}s (cap {WALL_CLOCK_CAP_S}s)"
    )

    print(
        "\n[bench] 10k import: "
        f"process={t2-t1:.2f}s resolve={t3-t2:.2f}s leakage={t4-t3:.2f}s "
        f"total={total_s:.2f}s rows/s={N_ROWS/total_s:.1f} "
        f"DB_RT={CountingSession.round_trips} "
        f"(reads={CountingSession.reads} writes={CountingSession.writes}) "
        f"leads={import_stats['leads_created']} errors={import_stats['errors']} "
        f"events={import_stats['events_created']} "
        f"leakage_events={leakage_stats['total_events']} "
        f"merges={merge_stats.get('total_merges', 0)}"
    )