"""
Import service — handles file upload, preview, column mapping, and processing pipeline.

The processing pipeline (triggered after mapping confirmation):
1. Read raw data
2. Normalize phone, email, dates, status
3. Create Lead + LeadEvent rows
4. Run identity resolution
5. Run leakage detection
6. Run financial calculations
"""
from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import insert, select, func, delete, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.data_import import DataImport
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.project import Project
from app.models.sales_rep import SalesRep
from app.models.column_mapping import ColumnMapping
from app.models.leakage_event import LeakageEvent
from app.models.leakage_evidence import LeakageEvidence
from app.models.financial_calculation import FinancialCalculation
from app.models.recommendation import Recommendation
from app.models.intervention import Intervention
from app.models.recovery_outcome import RecoveryOutcome
from app.models.identity_merge_log import IdentityMergeLog
from app.models.background_job import BackgroundJob
from app.models.timestamps import utc_now
from app.models.enums import ImportStatus, JobStatus
from app.core.normalization.phone import normalize_phone, normalize_email
from app.core.normalization.dates import parse_date, normalize_status
from app.core.derived import compute_derived_fields, plan_lifecycle_events
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)
settings = get_settings()


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a parsed datetime to timezone-aware UTC (SQLite-safe)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_amount(raw: str | None) -> Decimal | None:
    """Parse a deal value / budget string like '₹52,00,000' or '5200000'."""
    if not raw:
        return None
    try:
        cleaned = (
            str(raw).replace(",", "").replace("₹", "").replace("INR", "")
            .replace("Rs.", "").replace("Rs", "").strip()
        )
        if not cleaned:
            return None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_commission_rate(raw: str | None) -> Decimal | None:
    """Parse a commission rate.

    Accepts '2', '2%', '0.02', '2.5'. Values >= 1 are interpreted as
    percentages (2 → 0.02); values < 1 are treated as fractions (0.02).
    """
    if not raw:
        return None
    try:
        cleaned = str(raw).replace("%", "").strip()
        if not cleaned:
            return None
        value = Decimal(cleaned)
        if value >= 1:
            value = value / Decimal("100")
        if value <= 0 or value > 1:
            return None
        return value.quantize(Decimal("0.00001"))
    except (InvalidOperation, ValueError):
        return None


def _parse_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


def sanitize_filename(filename: str) -> str:
    """Sanitize an uploaded filename (Phase 18 — path traversal defense).

    - Keeps only the base name (strips any directory components, including
      `..\\`, `../`, and absolute paths).
    - Allows only [A-Za-z0-9._-]; everything else becomes `_`.
    - Collapses pathological names and caps length.
    """
    import re
    # Strip any path components for both separators
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    base = base.strip().strip(".")
    if not base:
        base = "upload"
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        sanitized = "upload"
    # Cap length, preserving the extension
    if len(sanitized) > 120:
        stem, dot, ext = sanitized.rpartition(".")
        if dot and len(ext) <= 10:
            sanitized = stem[: 120 - len(ext) - 1] + "." + ext
        else:
            sanitized = sanitized[:120]
    return sanitized


async def create_import(
    db: AsyncSession,
    organization_id: uuid.UUID,
    filename: str,
    file_type: str,
    file_content: bytes,
) -> DataImport:
    """Save uploaded file and create an import record.

    Persists ``persisted_columns`` and ``persisted_preview_rows`` to the database
    at upload time so that column-mapping suggestions can be reconstructed even
    when the ephemeral ``/tmp`` storage on Render is lost after a restart.
    """
    import_id = uuid.uuid4()
    safe_name = sanitize_filename(filename)
    upload_dir = Path(settings.UPLOAD_DIR) / str(import_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / safe_name
    file_path.write_bytes(file_content)

    # Read preview BEFORE writing the import record so a file-read error
    # (corrupt CSV, permission issue) surfaces as a clean 400 rather than a
    # half-created import.
    preview = read_file_preview(str(file_path))

    data_import = DataImport(
        id=import_id,
        organization_id=organization_id,
        filename=safe_name,
        file_type=file_type,
        raw_storage_path=str(file_path),
        status=ImportStatus.UPLOADED.value,
        persisted_columns=json.dumps(preview["columns"]),
        persisted_preview_rows=json.dumps(preview["preview_rows"]),
    )
    db.add(data_import)
    await db.flush()

    await log_action(db, "import_created", "data_import", str(import_id),
                     after={"filename": safe_name, "file_type": file_type})

    return data_import


def read_file_preview(file_path: str, max_rows: int = 10) -> dict[str, Any]:
    """Read a CSV/XLSX file and return a preview."""
    path = Path(file_path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, nrows=max_rows + 1)
    else:
        df = pd.read_csv(path, nrows=max_rows + 1)

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]

    return {
        "columns": list(df.columns),
        "preview_rows": df.head(max_rows).fillna("").to_dict(orient="records"),
        "total_preview_rows": len(df),
    }


def count_file_rows(file_path: str) -> int:
    """Count total rows in a file."""
    path = Path(file_path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    return len(df)


async def get_or_create_project(
    db: AsyncSession, organization_id: uuid.UUID, project_name: str
) -> uuid.UUID:
    """Get or create a project by name."""
    if not project_name or not project_name.strip():
        return None
    project_name = project_name.strip()
    result = await db.execute(
        select(Project).where(
            Project.organization_id == organization_id,
            Project.name == project_name,
        )
    )
    project = result.scalars().first()
    if project:
        return project.id

    new_project = Project(
        organization_id=organization_id,
        name=project_name,
    )
    db.add(new_project)
    await db.flush()
    return new_project.id


async def get_or_create_sales_rep(
    db: AsyncSession, organization_id: uuid.UUID, rep_name: str
) -> uuid.UUID:
    """Get or create a sales rep by name."""
    if not rep_name or not rep_name.strip():
        return None
    rep_name = rep_name.strip()
    result = await db.execute(
        select(SalesRep).where(
            SalesRep.organization_id == organization_id,
            SalesRep.name == rep_name,
        )
    )
    rep = result.scalars().first()
    if rep:
        return rep.id

    new_rep = SalesRep(
        organization_id=organization_id,
        name=rep_name,
    )
    db.add(new_rep)
    await db.flush()
    return new_rep.id


async def _name_to_id(
    db: AsyncSession,
    organization_id: uuid.UUID,
    name: str | None,
    model: type[Project] | type[SalesRep],
    cache: dict[str, uuid.UUID],
) -> uuid.UUID | None:
    """Resolve a project/rep name to its id, caching lookups per import run.

    Name → id resolution is read-heavy (the same handful of project/rep names
    repeats across thousands of rows). A verified SELECT keyed by name happens
    at most once per unique name per run; missing names create + flush once.
    """
    if not name or not name.strip():
        return None
    key = name.strip()
    if key in cache:
        return cache[key]

    row = (await db.execute(
        select(model.id).where(
            model.organization_id == organization_id,
            model.name == key,
        )
    )).scalars().first()
    if row is not None:
        cache[key] = row
        return row

    new_obj = model(organization_id=organization_id, name=key)
    db.add(new_obj)
    await db.flush()
    cache[key] = new_obj.id
    return new_obj.id


async def process_import(
    db: AsyncSession,
    import_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    batch_size: int = 500,
    on_progress: Any = None,  # async callable(batched_rows, stats) after each flush
) -> dict[str, Any]:
    """Process a confirmed import — normalize, create leads, create events.

    Bulk path: project/rep name lookups are cached per run, and leads +
    lifecycle events are inserted as single-multi-row statements per batch
    (core ``Insert`` executemany) instead of one awaited flush per row. Row
    normalization + deterministic derived fields are unchanged — this is a
    pure performance refactor with identical output.

    Returns processing statistics (same shape as before).
    """
    data_import = await db.get(DataImport, import_id)
    if not data_import:
        raise ValueError(f"Import {import_id} not found")

    data_import.status = ImportStatus.PROCESSING.value
    await db.flush()

    # Get confirmed mappings
    mappings_result = await db.execute(
        select(ColumnMapping).where(
            ColumnMapping.import_id == import_id,
            ColumnMapping.confirmed == True,
        )
    )
    mappings = {m.source_column: m.target_field for m in mappings_result.scalars().all()}

    if not mappings:
        data_import.status = ImportStatus.FAILED.value
        data_import.error_message = "No confirmed column mappings found"
        await db.flush()
        return {"error": "No confirmed mappings"}

    # Read the full file
    path = Path(data_import.raw_storage_path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df.columns = [str(c).strip() for c in df.columns]

    # ── Idempotency guard (non-destructive): never double-process an import ──
    existing_result = await db.execute(
        select(func.count(Lead.id)).where(Lead.created_from_import_id == import_id)
    )
    if (existing_result.scalar() or 0) > 0:
        return {
            "total_rows": data_import.row_count or 0,
            "leads_created": 0,
            "events_created": 0,
            "errors": 0,
            "already_processed": True,
        }

    stats = {
        "total_rows": len(df),
        "leads_created": 0,
        "events_created": 0,
        "errors": 0,
        "flags_raised": 0,
        "estimated_created_at": 0,
    }

    ingest_now = datetime.now(timezone.utc)

    # Per-import caches: repeated project/rep names are resolved from memory,
    # never via a fresh query per row.
    project_cache: dict[str, uuid.UUID] = {}
    rep_cache: dict[str, uuid.UUID] = {}

    lead_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        try:
            # Map columns to target fields
            mapped = {}
            for source_col, target_field in mappings.items():
                if source_col in row:
                    val = row[source_col]
                    if pd.notna(val):
                        mapped[target_field] = str(val).strip()

            if "name" not in mapped or not mapped["name"]:
                stats["errors"] += 1
                continue

            # ── Normalize scalar fields ─────────────────────────────────────
            phone_raw = mapped.get("phone_raw", "")
            phone_normalized = normalize_phone(phone_raw)
            email = normalize_email(mapped.get("email", ""))
            status_raw = mapped.get("status", "")
            status = normalize_status(status_raw)

            # ── Parse timestamps (canonical schema, Phase 1) ─────────────────
            created_at = parse_date(mapped.get("created_at", ""))
            created_at_is_estimated = False
            if created_at is None:
                # Phase 1 policy: never silently replace a real source timestamp.
                # Only when NO valid source timestamp exists do we fall back to
                # ingestion time — and we flag that estimate on the lead.
                created_at = ingest_now
                created_at_is_estimated = True
                stats["estimated_created_at"] += 1
            created_at = _as_utc(created_at)

            first_contact_at = _as_utc(parse_date(mapped.get("first_contact_at", "")))
            last_contact_at = _as_utc(parse_date(mapped.get("last_followup_at", "")))
            site_visit_at = _as_utc(parse_date(mapped.get("site_visit_at", "")))
            negotiation_at = _as_utc(parse_date(mapped.get("negotiation_at", "")))
            closed_at = _as_utc(parse_date(mapped.get("closed_at", "")))

            # ── Parse numeric / aggregate fields ─────────────────────────────
            budget = _parse_amount(mapped.get("budget", ""))
            commission_rate = _parse_commission_rate(mapped.get("commission_rate", ""))
            total_touches = _parse_int(mapped.get("total_touches", ""))

            # ── Get or create project/rep (cached per import run) ───────────
            project_id = await _name_to_id(
                db, organization_id, mapped.get("project_name", ""),
                Project, project_cache,
            )
            sales_rep_id = await _name_to_id(
                db, organization_id, mapped.get("sales_rep_name", ""),
                SalesRep, rep_cache,
            )

            # ── Deterministic derived fields + validation flags (Phase 4) ────
            derived = compute_derived_fields(
                created_at=created_at,
                first_contact_at=first_contact_at,
                last_contact_at=last_contact_at,
                site_visit_at=site_visit_at,
                negotiation_at=negotiation_at,
                closed_at=closed_at,
                total_touches=total_touches,
                now=ingest_now,
            )
            if created_at_is_estimated:
                derived.data_quality_flags.append("created_at_estimated_from_ingestion_time")
            stats["flags_raised"] += len(derived.data_quality_flags)

            lead_id = uuid.uuid4()

            # ── Stage lead row (schema-identical to the ORM Lead) ───────────
            lead_rows.append({
                "id": lead_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "sales_rep_id": sales_rep_id,
                "name": mapped["name"],
                "phone_normalized": phone_normalized,
                "phone_raw": phone_raw or None,
                "email": email,
                "status": status,
                "status_raw": status_raw or None,
                "budget": budget,
                "source": mapped.get("source"),
                "campaign_name": mapped.get("campaign_name"),
                "property_type": mapped.get("property_type"),
                "lost_reason": mapped.get("lost_reason"),
                "commission_rate": commission_rate,
                "total_touches": total_touches,
                "created_at": created_at,
                "created_at_is_estimated": created_at_is_estimated,
                "last_followup_at": last_contact_at,
                "first_contact_at": first_contact_at,
                "site_visit_at": site_visit_at,
                "negotiation_at": negotiation_at,
                "closed_at": closed_at,
                "response_latency_minutes": derived.response_latency_minutes,
                "site_visit_latency_days": derived.site_visit_latency_days,
                "sales_cycle_days": derived.sales_cycle_days,
                "is_dark_lead": derived.is_dark_lead,
                "is_single_touch": derived.is_single_touch,
                "funnel_max_stage": derived.funnel_max_stage,
                "data_quality_flags": derived.to_flags_dict(),
                "created_from_import_id": import_id,
            })
            stats["leads_created"] += 1

            # ── Stage lifecycle events from VERIFIED timestamps (Phase 3) ────
            for plan in plan_lifecycle_events(
                created_at=created_at,
                first_contact_at=first_contact_at,
                last_contact_at=last_contact_at,
                site_visit_at=site_visit_at,
                negotiation_at=negotiation_at,
                closed_at=closed_at,
                total_touches=total_touches,
                source="import",
            ):
                event_rows.append({
                    "id": uuid.uuid4(),
                    "organization_id": organization_id,
                    "lead_id": lead_id,
                    "event_type": plan["event_type"],
                    "event_payload": {
                        **plan["event_payload"],
                        "import_id": str(import_id),
                    },
                    "occurred_at": plan["occurred_at"],
                    "source": "import",
                    "created_at": utc_now(),
                })
                stats["events_created"] += 1

            # ── Flush a batch: one executemany per table instead of per row ──
            if len(lead_rows) >= batch_size:
                await db.execute(insert(Lead), lead_rows)
                if event_rows:
                    await db.execute(insert(LeadEvent), event_rows)
                lead_rows.clear()
                event_rows.clear()
                if on_progress is not None:
                    await on_progress(stats["total_rows"], stats)

        except Exception as e:
            logger.error(f"Error processing row: {e}")
            stats["errors"] += 1

    # Final partial batch
    if lead_rows:
        await db.execute(insert(Lead), lead_rows)
        if event_rows:
            await db.execute(insert(LeadEvent), event_rows)

    data_import.status = ImportStatus.COMPLETED.value
    data_import.row_count = stats["total_rows"]
    await db.flush()

    await log_action(
        db, "import_processed", "data_import", str(import_id),
        after=stats,
    )

    return stats


async def delete_import(
    db: AsyncSession,
    import_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> dict[str, Any]:
    """Permanently delete an imported batch and clean up its derived records.

    Preserves referential integrity by safely removing records in reverse
    dependency order:
      1. Unlink leads merged into leads of this batch (merged_into_lead_id = None)
      2. Delete identity merge logs referencing this batch's leads
      3. Delete recovery outcomes, interventions, recommendations,
         calculations & evidence for leakage events tied to this batch's leads
      4. Delete leakage events tied to this batch's leads
      5. Delete lead lifecycle events tied to this batch's leads
      6. Delete leads created from this import
      7. Delete column mappings for this import
      8. Delete the DataImport record itself
      9. Clean up raw storage files/directory on disk
      10. Audit log the deletion
    """
    stmt = select(DataImport).where(DataImport.id == import_id)
    res = await db.execute(stmt)
    data_import = res.scalar_one_or_none()
    if not data_import:
        raise HTTPException(status_code=404, detail="Import batch not found")
    if data_import.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Forbidden: batch belongs to another organization")

    # 1. Find all lead IDs created by this import
    leads_res = await db.execute(
        select(Lead.id).where(Lead.created_from_import_id == import_id)
    )
    lead_ids = [row[0] for row in leads_res.all()]

    deleted_leakage_count = 0
    if lead_ids:
        # 1a. Unlink any other leads that were merged into these leads
        await db.execute(
            update(Lead)
            .where(Lead.merged_into_lead_id.in_(lead_ids))
            .values(merged_into_lead_id=None)
        )

        # 1b. Delete identity merge logs referencing these leads
        await db.execute(
            delete(IdentityMergeLog).where(
                or_(
                    IdentityMergeLog.primary_lead_id.in_(lead_ids),
                    IdentityMergeLog.merged_lead_id.in_(lead_ids),
                )
            )
        )

        # 1c. Find leakage events tied to these leads
        leakage_res = await db.execute(
            select(LeakageEvent.id).where(
                LeakageEvent.source_entity_type == "lead",
                LeakageEvent.source_entity_id.in_(lead_ids),
            )
        )
        leakage_ids = [row[0] for row in leakage_res.all()]
        deleted_leakage_count = len(leakage_ids)

        if leakage_ids:
            # Find recommendations tied to these leakage events
            rec_res = await db.execute(
                select(Recommendation.id).where(
                    Recommendation.leakage_event_id.in_(leakage_ids)
                )
            )
            rec_ids = [row[0] for row in rec_res.all()]

            if rec_ids:
                # Find interventions tied to these recommendations
                int_res = await db.execute(
                    select(Intervention.id).where(
                        Intervention.recommendation_id.in_(rec_ids)
                    )
                )
                int_ids = [row[0] for row in int_res.all()]

                if int_ids:
                    # Delete recovery outcomes
                    await db.execute(
                        delete(RecoveryOutcome).where(RecoveryOutcome.intervention_id.in_(int_ids))
                    )
                    # Delete interventions
                    await db.execute(
                        delete(Intervention).where(Intervention.id.in_(int_ids))
                    )

                # Delete recommendations
                await db.execute(
                    delete(Recommendation).where(Recommendation.id.in_(rec_ids))
                )

            # Delete leakage evidence and financial calculations
            await db.execute(
                delete(LeakageEvidence).where(LeakageEvidence.leakage_event_id.in_(leakage_ids))
            )
            await db.execute(
                delete(FinancialCalculation).where(FinancialCalculation.leakage_event_id.in_(leakage_ids))
            )

            # Delete leakage events
            await db.execute(
                delete(LeakageEvent).where(LeakageEvent.id.in_(leakage_ids))
            )

        # 1d. Delete lead lifecycle events
        await db.execute(
            delete(LeadEvent).where(LeadEvent.lead_id.in_(lead_ids))
        )

        # 1e. Delete leads
        await db.execute(
            delete(Lead).where(Lead.id.in_(lead_ids))
        )

    # 2. Delete column mappings
    await db.execute(
        delete(ColumnMapping).where(ColumnMapping.import_id == import_id)
    )

    # 3. Delete the DataImport record
    filename = data_import.filename
    raw_storage_path = data_import.raw_storage_path
    await db.delete(data_import)
    await db.flush()

    # 4. Safe file storage cleanup
    if raw_storage_path:
        try:
            file_p = Path(raw_storage_path)
            if file_p.exists():
                file_p.unlink()
            parent_dir = file_p.parent
            if parent_dir.name == str(import_id) and parent_dir.exists():
                import shutil
                shutil.rmtree(parent_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("Could not delete storage file %s: %s", raw_storage_path, e)

    # 5. Audit log
    await log_action(
        db,
        "import_deleted",
        "data_import",
        str(import_id),
        before={"filename": filename, "leads_count": len(lead_ids)},
    )

    return {
        "status": "deleted",
        "import_id": str(import_id),
        "filename": filename,
        "deleted_leads": len(lead_ids),
        "deleted_leakage_events": deleted_leakage_count,
    }


async def clear_organization_imports(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> dict[str, Any]:
    """Delete all imported batches and their derived records for an organization.

    Preserves the organization, sales reps, projects, and base schema.
    """
    stmt = select(DataImport.id).where(DataImport.organization_id == organization_id)
    res = await db.execute(stmt)
    import_ids = [row[0] for row in res.all()]

    total_deleted_leads = 0
    total_deleted_leakage = 0
    for imp_id in import_ids:
        del_res = await delete_import(db, imp_id, organization_id)
        total_deleted_leads += del_res.get("deleted_leads", 0)
        total_deleted_leakage += del_res.get("deleted_leakage_events", 0)

    await log_action(
        db,
        "all_imports_cleared",
        "organization",
        str(organization_id),
        before={"batches_count": len(import_ids), "leads_count": total_deleted_leads},
    )

    return {
        "status": "cleared",
        "deleted_batches": len(import_ids),
        "deleted_leads": total_deleted_leads,
        "deleted_leakage_events": total_deleted_leakage,
    }

