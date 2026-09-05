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

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.data_import import DataImport
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.project import Project
from app.models.sales_rep import SalesRep
from app.models.column_mapping import ColumnMapping
from app.models.background_job import BackgroundJob
from app.models.enums import ImportStatus, JobStatus
from app.core.normalization.phone import normalize_phone, normalize_email
from app.core.normalization.dates import parse_date, normalize_status
from app.core.derived import compute_derived_fields, plan_lifecycle_events
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)
settings = get_settings()


def _as_utc(dt: datetime) -> datetime:
    """Normalize a parsed datetime to timezone-aware UTC (SQLite-safe)."""
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
    """Save uploaded file and create an import record."""
    import_id = uuid.uuid4()
    safe_name = sanitize_filename(filename)
    upload_dir = Path(settings.UPLOAD_DIR) / str(import_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / safe_name
    file_path.write_bytes(file_content)

    data_import = DataImport(
        id=import_id,
        organization_id=organization_id,
        filename=safe_name,
        file_type=file_type,
        raw_storage_path=str(file_path),
        status=ImportStatus.UPLOADED.value,
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


async def process_import(
    db: AsyncSession,
    import_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> dict[str, Any]:
    """Process a confirmed import — normalize, create leads, create events.

    Returns processing statistics.
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

            # ── Get or create project/rep ────────────────────────────────────
            project_id = await get_or_create_project(
                db, organization_id, mapped.get("project_name", "")
            )
            sales_rep_id = await get_or_create_sales_rep(
                db, organization_id, mapped.get("sales_rep_name", "")
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

            # ── Create lead (canonical schema) ───────────────────────────────
            lead = Lead(
                organization_id=organization_id,
                project_id=project_id,
                sales_rep_id=sales_rep_id,
                name=mapped["name"],
                phone_normalized=phone_normalized,
                phone_raw=phone_raw or None,
                email=email,
                status=status,
                status_raw=status_raw or None,
                budget=budget,
                source=mapped.get("source"),
                campaign_name=mapped.get("campaign_name"),
                property_type=mapped.get("property_type"),
                lost_reason=mapped.get("lost_reason"),
                commission_rate=commission_rate,
                total_touches=total_touches,
                created_at=created_at,
                created_at_is_estimated=created_at_is_estimated,
                last_followup_at=last_contact_at,
                first_contact_at=first_contact_at,
                site_visit_at=site_visit_at,
                negotiation_at=negotiation_at,
                closed_at=closed_at,
                response_latency_minutes=derived.response_latency_minutes,
                site_visit_latency_days=derived.site_visit_latency_days,
                sales_cycle_days=derived.sales_cycle_days,
                is_dark_lead=derived.is_dark_lead,
                is_single_touch=derived.is_single_touch,
                funnel_max_stage=derived.funnel_max_stage,
                data_quality_flags=derived.to_flags_dict(),
                created_from_import_id=import_id,
            )
            db.add(lead)
            await db.flush()
            stats["leads_created"] += 1

            # ── Generate lifecycle events from VERIFIED timestamps (Phase 3) ──
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
                db.add(LeadEvent(
                    organization_id=organization_id,
                    lead_id=lead.id,
                    event_type=plan["event_type"],
                    event_payload={
                        **plan["event_payload"],
                        "import_id": str(import_id),
                    },
                    occurred_at=plan["occurred_at"],
                    source="import",
                ))
                stats["events_created"] += 1

        except Exception as e:
            logger.error(f"Error processing row: {e}")
            stats["errors"] += 1

    data_import.status = ImportStatus.COMPLETED.value
    data_import.row_count = stats["total_rows"]
    await db.flush()

    await log_action(
        db, "import_processed", "data_import", str(import_id),
        after=stats,
    )

    return stats
