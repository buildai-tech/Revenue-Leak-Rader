"""
Unit tests for the AI column-mapping endpoint's graceful degradation.

Regression coverage for the 2026-09-05 production incident: when the NVIDIA
provider raises (missing SDK / invalid credentials / outage), the
`/api/imports/{id}/suggestions` endpoint must fall back to deterministic
heuristic suggestions instead of raising — otherwise the mapping pre-fill
fails in the UI, the import gets confirmed with zero mappings, and the batch
is marked FAILED ("No confirmed column mappings found").

Also proves the full import pipeline completes while the NVIDIA provider is
down: a temporary AI failure must never fail an import.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai import llm_provider as llm_provider_module
from app.api import imports as imports_api
from app.database import Base
from app.models.data_import import DataImport
from app.models.enums import ImportStatus
from app.models.organization import Organization
from app.schemas.schemas import ColumnMappingConfirm, ColumnMappingItem

# NOTE: every optional timestamp target must be present and parseable —
# process_import wraps parse_date() results in _as_utc(), which rejects None.
SAMPLE_CSV = (
    "Lead Name,Phone,Email,Enquiry Date,First Contact,Last Followup,Site Visit,Negotiation,Closed\n"
    "Aarav Sharma,+919876543210,aarav@example.com,2026-08-01 10:00:00,2026-08-01 11:00:00,2026-08-02 10:00:00,2026-08-05 10:00:00,2026-08-10 10:00:00,2026-08-12 10:00:00\n"
    "Ananya Verma,+919876543211,ananya@example.com,2026-08-01 10:30:00,2026-08-01 12:00:00,2026-08-03 10:00:00,2026-08-06 10:00:00,2026-08-11 10:00:00,2026-08-13 10:00:00\n"
)


class _ExplodingProvider:
    """Simulates every NVIDIA failure mode (missing SDK, bad key, outage)."""

    async def suggest_column_mappings(self, source_columns, target_fields, sample_data):
        raise RuntimeError("simulated NVIDIA provider outage")


class _GoodLlmProvider:
    """Simulates a healthy NVIDIA provider returning one high-confidence map."""

    async def suggest_column_mappings(self, source_columns, target_fields, sample_data):
        return [{"source": "Email", "target": "email", "confidence": 0.98}]


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


@pytest.fixture
async def import_with_file(test_session, tmp_path):
    """A demo org + an UPLOADED import backed by a real CSV file on disk."""
    org = Organization(id=uuid.uuid4(), name="AI Fallback Test Org", is_demo=True)
    test_session.add(org)
    await test_session.flush()

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

    imp = DataImport(
        id=uuid.uuid4(),
        organization_id=org.id,
        filename="sample.csv",
        file_type="csv",
        raw_storage_path=str(csv_path),
        status=ImportStatus.UPLOADED.value,
        persisted_columns=json.dumps([
            "Lead Name", "Phone", "Email", "Enquiry Date", "First Contact",
            "Last Followup", "Site Visit", "Negotiation", "Closed",
        ]),
        persisted_preview_rows=json.dumps([
            {
                "Lead Name": "Aarav Sharma", "Phone": "+919876543210",
                "Email": "aarav@example.com", "Enquiry Date": "2026-08-01 10:00:00",
            },
        ]),
    )
    test_session.add(imp)
    await test_session.flush()
    return imp


# ── GET /api/imports/{id}/suggestions ─────────────────────────────────────
@pytest.mark.asyncio
async def test_suggestions_fall_back_to_heuristics_when_nvidia_fails(
    test_session, import_with_file, monkeypatch
):
    def _exploding_factory():
        return _ExplodingProvider()

    monkeypatch.setattr(imports_api, "get_llm_provider", _exploding_factory)

    response = await imports_api.get_mapping_suggestions(
        str(import_with_file.id), test_session
    )

    # A payload is returned (200-equivalent) — never an exception/500.
    assert response["suggestions"], "heuristic fallback must produce suggestions"
    assert all(s.get("suggested_by") != "llm" for s in response["suggestions"])
    assert response["collision_errors"] == []

    # The import record itself is untouched — definitely not FAILED.
    await test_session.refresh(import_with_file)
    assert import_with_file.status == ImportStatus.UPLOADED.value
    assert import_with_file.error_message is None


@pytest.mark.asyncio
async def test_suggestions_survive_missing_preview_file(
    test_session, import_with_file, monkeypatch
):
    """Ephemeral-storage restarts (Render /tmp) delete the raw file — the
    endpoint must degrade gracefully, not 500, and still return heuristic
    suggestions from the persisted column metadata."""
    import os

    os.unlink(import_with_file.raw_storage_path)

    monkeypatch.setenv("LLM_PROVIDER", "noop")
    llm_provider_module.get_settings.cache_clear()
    try:
        response = await imports_api.get_mapping_suggestions(
            str(import_with_file.id), test_session
        )
    finally:
        llm_provider_module.get_settings.cache_clear()

        # Heuristic suggestions from persisted columns — never empty, never a 500.
    assert response["suggestions"], "heuristic suggestions must be returned even when the raw file is missing"
    assert response["target_fields"]
    assert response["collision_errors"] == []
    # Source should be heuristic (NoOp provider == heuristic, not LLM)
    assert response["source"] == "heuristic"


@pytest.mark.asyncio
async def test_suggestions_use_llm_output_when_available(
    test_session, import_with_file, monkeypatch
):
    def _good_factory():
        return _GoodLlmProvider()

    monkeypatch.setattr(imports_api, "get_llm_provider", _good_factory)

    response = await imports_api.get_mapping_suggestions(
        str(import_with_file.id), test_session
    )

    llm_picked = [s for s in response["suggestions"] if s.get("suggested_by") == "llm"]
    assert llm_picked, "LLM suggestion should be surfaced with suggested_by='llm'"
    assert llm_picked[0]["source_column"] == "Email"
    assert llm_picked[0]["target_field"] == "email"
    assert llm_picked[0]["confidence"] == 0.98


@pytest.mark.asyncio
async def test_suggestions_work_with_default_noop_provider(
    test_session, import_with_file, monkeypatch
):
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    llm_provider_module.get_settings.cache_clear()
    try:
        response = await imports_api.get_mapping_suggestions(
            str(import_with_file.id), test_session
        )
    finally:
        llm_provider_module.get_settings.cache_clear()

    assert response["suggestions"]
    assert response["collision_errors"] == []


# ── Full pipeline: NVIDIA down must NOT fail the import ───────────────────
@pytest.mark.asyncio
async def test_import_completes_when_nvidia_unavailable(
    test_session, import_with_file, monkeypatch
):
    """Confirm mappings and process the import while the NVIDIA provider is
    down — the import must complete, never become FAILED."""
    def _exploding_factory():
        return _ExplodingProvider()

    monkeypatch.setattr(imports_api, "get_llm_provider", _exploding_factory)

    body = ColumnMappingConfirm(
        mappings=[
            ColumnMappingItem(source_column="Lead Name", target_field="name"),
            ColumnMappingItem(source_column="Phone", target_field="phone_raw"),
            ColumnMappingItem(source_column="Email", target_field="email"),
            ColumnMappingItem(source_column="Enquiry Date", target_field="created_at"),
            ColumnMappingItem(source_column="First Contact", target_field="first_contact_at"),
            ColumnMappingItem(source_column="Last Followup", target_field="last_followup_at"),
            ColumnMappingItem(source_column="Site Visit", target_field="site_visit_at"),
            ColumnMappingItem(source_column="Negotiation", target_field="negotiation_at"),
            ColumnMappingItem(source_column="Closed", target_field="closed_at"),
        ]
    )

    result = await imports_api.confirm_mappings(
        str(import_with_file.id), body, test_session
    )

    stats = result["import_stats"]
    assert "error" not in stats, "import must not fail because NVIDIA is down"
    assert stats["leads_created"] == 2
    assert stats["events_created"] >= 1

    await test_session.refresh(import_with_file)
    assert import_with_file.status == ImportStatus.COMPLETED.value
    assert import_with_file.row_count == 2
    assert import_with_file.error_message is None


# ── Neither file nor persisted metadata → sanitized error ──────────────────
@pytest.mark.asyncio
async def test_suggestions_missing_file_and_no_metadata_raises_sanitized_error(
    test_session, tmp_path, monkeypatch
):
    """If the raw file AND the persisted preview metadata are both absent, the
    endpoint must raise a clear, sanitized 409 — never a 500, never a raw path
    or stack trace leaking."""

    from fastapi import HTTPException

    org = Organization(id=uuid.uuid4(), name="No-Metadata Org", is_demo=True)
    test_session.add(org)
    await test_session.flush()

    missing_path = tmp_path / "does_not_exist.csv"

    imp = DataImport(
        id=uuid.uuid4(),
        organization_id=org.id,
        filename="lost.csv",
        file_type="csv",
        raw_storage_path=str(missing_path),
        status=ImportStatus.UPLOADED.value,
        # persisted_columns / persisted_preview_rows left as None → no metadata
    )
    test_session.add(imp)
    await test_session.flush()

    monkeypatch.setenv("LLM_PROVIDER", "noop")
    llm_provider_module.get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await imports_api.get_mapping_suggestions(str(imp.id), test_session)
    finally:
        llm_provider_module.get_settings.cache_clear()

    assert exc_info.value.status_code == 409
    detail = str(exc_info.value.detail)
    # Sanitized: never leak the underlying path or an internal error.
    assert str(missing_path) not in detail
    assert "re-upload" in detail.lower()