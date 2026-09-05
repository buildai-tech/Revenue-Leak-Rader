"""
Unit tests for imported batch deletion and demo data reset.
Validates:
- Successful cascading cleanup of all derived records (leads, events, leakage, recommendations, interventions)
- 404 on nonexistent batch
- 403 on cross-organization batch deletion
- Preservation of unrelated leads, organization, and referential integrity
- Clear demo imports functionality
"""
from __future__ import annotations

import uuid
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.database import Base
from app.models.organization import Organization
from app.models.data_import import DataImport
from app.models.column_mapping import ColumnMapping
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.leakage_event import LeakageEvent
from app.models.leakage_evidence import LeakageEvidence
from app.models.financial_calculation import FinancialCalculation
from app.models.recommendation import Recommendation
from app.models.intervention import Intervention
from app.models.recovery_outcome import RecoveryOutcome
from app.models.identity_merge_log import IdentityMergeLog
from app.services.import_service import delete_import, clear_organization_imports


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


@pytest.mark.asyncio
async def test_delete_nonexistent_import(test_session: AsyncSession):
    org_id = uuid.uuid4()
    nonexistent_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await delete_import(test_session, nonexistent_id, org_id)

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_delete_import_wrong_organization(test_session: AsyncSession):
    org_1 = Organization(id=uuid.uuid4(), name="Org 1", is_demo=True)
    org_2 = Organization(id=uuid.uuid4(), name="Org 2", is_demo=False)
    test_session.add_all([org_1, org_2])
    await test_session.flush()

    imp = DataImport(
        id=uuid.uuid4(),
        organization_id=org_1.id,
        filename="leads.csv",
        file_type="csv",
        raw_storage_path="",
        status="completed",
    )
    test_session.add(imp)
    await test_session.flush()

    # Attempt to delete with Org 2 credentials
    with pytest.raises(HTTPException) as exc_info:
        await delete_import(test_session, imp.id, org_2.id)

    assert exc_info.value.status_code == 403
    assert "forbidden" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_delete_import_success_cascades_safely(test_session: AsyncSession):
    org = Organization(id=uuid.uuid4(), name="GreenVista Realty Demo", is_demo=True)
    test_session.add(org)
    await test_session.flush()

    # 1. Create an imported batch
    imp = DataImport(
        id=uuid.uuid4(),
        organization_id=org.id,
        filename="march_batch.csv",
        file_type="csv",
        raw_storage_path="",
        status="completed",
        row_count=2,
    )
    test_session.add(imp)

    # 2. Column mapping
    mapping = ColumnMapping(
        id=uuid.uuid4(),
        organization_id=org.id,
        import_id=imp.id,
        source_column="Lead Name",
        target_field="name",
        confirmed=True,
    )
    test_session.add(mapping)

    # 3. Create 2 leads from this import
    lead1 = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Aarav Sharma",
        phone_normalized="+919876543210",
        budget=Decimal("7500000"),
        created_from_import_id=imp.id,
    )
    lead2 = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Ananya Verma",
        phone_normalized="+919876543211",
        budget=Decimal("5000000"),
        created_from_import_id=imp.id,
    )

    # 4. Create an unrelated lead (not from this import) to ensure it stays intact!
    unrelated_lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Unrelated Seed Lead",
        created_from_import_id=None,
    )
    test_session.add_all([lead1, lead2, unrelated_lead])
    await test_session.flush()

    # 5. Lead merged into lead1
    unrelated_lead.merged_into_lead_id = lead1.id

    # 6. Merge log referencing lead1
    merge_log = IdentityMergeLog(
        id=uuid.uuid4(),
        organization_id=org.id,
        primary_lead_id=lead1.id,
        merged_lead_id=unrelated_lead.id,
        method="phone",
        confidence=1.0,
    )
    test_session.add(merge_log)

    from datetime import datetime, timezone
    event1 = LeadEvent(
        id=uuid.uuid4(),
        organization_id=org.id,
        lead_id=lead1.id,
        event_type="inquiry_received",
        occurred_at=datetime.now(timezone.utc),
        source="import",
    )
    test_session.add(event1)

    # 8. Leakage event tied to lead1
    leakage = LeakageEvent(
        id=uuid.uuid4(),
        organization_id=org.id,
        category="funnel_leakage",
        source_entity_type="lead",
        source_entity_id=lead1.id,
        tier="estimated_financial_impact",
        title="Dark Lead detected",
    )
    test_session.add(leakage)
    await test_session.flush()

    # 9. Evidence & Financial Calculation
    evidence = LeakageEvidence(
        id=uuid.uuid4(),
        organization_id=org.id,
        leakage_event_id=leakage.id,
        evidence_type="funnel_state",
    )
    calc = FinancialCalculation(
        id=uuid.uuid4(),
        organization_id=org.id,
        leakage_event_id=leakage.id,
        tier="estimated_financial_impact",
        amount_inr=Decimal("150000"),
        confidence=0.85,
        formula_id="lead_exposure_v2",
        formula_version="2.0",
        data_source="crm",
    )
    test_session.add_all([evidence, calc])

    # 10. Recommendation -> Intervention -> Recovery Outcome
    rec = Recommendation(
        id=uuid.uuid4(),
        organization_id=org.id,
        leakage_event_id=leakage.id,
        playbook_key="whatsapp_followup",
        generated_copy="Hello, following up...",
        generated_by="template",
    )
    test_session.add(rec)
    await test_session.flush()

    intervention = Intervention(
        id=uuid.uuid4(),
        organization_id=org.id,
        recommendation_id=rec.id,
        status="completed",
    )
    test_session.add(intervention)
    await test_session.flush()

    outcome = RecoveryOutcome(
        id=uuid.uuid4(),
        organization_id=org.id,
        intervention_id=intervention.id,
        outcome_type="site_visit_scheduled",
        booking_amount_inr=Decimal("50000"),
    )
    test_session.add(outcome)
    await test_session.commit()

    # Verify everything exists before deletion
    assert (await test_session.execute(select(DataImport).where(DataImport.id == imp.id))).scalar_one_or_none() is not None
    assert (await test_session.execute(select(Lead).where(Lead.id == lead1.id))).scalar_one_or_none() is not None
    assert (await test_session.execute(select(LeakageEvent).where(LeakageEvent.id == leakage.id))).scalar_one_or_none() is not None

    # Execute deletion
    result = await delete_import(test_session, imp.id, org.id)
    await test_session.commit()

    assert result["status"] == "deleted"
    assert result["deleted_leads"] == 2
    assert result["deleted_leakage_events"] == 1

    # Verify all records tied to import are permanently removed
    assert (await test_session.execute(select(DataImport).where(DataImport.id == imp.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(ColumnMapping).where(ColumnMapping.import_id == imp.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(Lead).where(Lead.id == lead1.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(Lead).where(Lead.id == lead2.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(LeadEvent).where(LeadEvent.id == event1.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(LeakageEvent).where(LeakageEvent.id == leakage.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(LeakageEvidence).where(LeakageEvidence.id == evidence.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(FinancialCalculation).where(FinancialCalculation.id == calc.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(Recommendation).where(Recommendation.id == rec.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(Intervention).where(Intervention.id == intervention.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(RecoveryOutcome).where(RecoveryOutcome.id == outcome.id))).scalar_one_or_none() is None
    assert (await test_session.execute(select(IdentityMergeLog).where(IdentityMergeLog.id == merge_log.id))).scalar_one_or_none() is None

    # Verify unrelated records and organization remain intact
    surviving_org = (await test_session.execute(select(Organization).where(Organization.id == org.id))).scalar_one_or_none()
    assert surviving_org is not None
    assert surviving_org.name == "GreenVista Realty Demo"

    surviving_lead = (await test_session.execute(select(Lead).where(Lead.id == unrelated_lead.id))).scalar_one_or_none()
    assert surviving_lead is not None
    assert surviving_lead.name == "Unrelated Seed Lead"
    # Merged reference to the deleted lead was safely unlinked to NULL
    assert surviving_lead.merged_into_lead_id is None


@pytest.mark.asyncio
async def test_clear_organization_imports(test_session: AsyncSession):
    org = Organization(id=uuid.uuid4(), name="Demo Org", is_demo=True)
    test_session.add(org)
    await test_session.flush()

    # Create 2 import batches
    imp1 = DataImport(id=uuid.uuid4(), organization_id=org.id, filename="b1.csv", file_type="csv", raw_storage_path="")
    imp2 = DataImport(id=uuid.uuid4(), organization_id=org.id, filename="b2.csv", file_type="csv", raw_storage_path="")
    test_session.add_all([imp1, imp2])
    await test_session.flush()

    lead1 = Lead(id=uuid.uuid4(), organization_id=org.id, name="L1", created_from_import_id=imp1.id)
    lead2 = Lead(id=uuid.uuid4(), organization_id=org.id, name="L2", created_from_import_id=imp2.id)
    test_session.add_all([lead1, lead2])
    await test_session.commit()

    res = await clear_organization_imports(test_session, org.id)
    await test_session.commit()

    assert res["status"] == "cleared"
    assert res["deleted_batches"] == 2
    assert res["deleted_leads"] == 2

    remaining_imports = (await test_session.execute(select(DataImport).where(DataImport.organization_id == org.id))).scalars().all()
    assert len(remaining_imports) == 0

    remaining_leads = (await test_session.execute(select(Lead).where(Lead.organization_id == org.id))).scalars().all()
    assert len(remaining_leads) == 0

    # Organization itself remains intact
    assert (await test_session.execute(select(Organization).where(Organization.id == org.id))).scalar_one_or_none() is not None
