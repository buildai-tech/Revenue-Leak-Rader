"""Import API — upload, preview, mapping, processing."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.data_import import DataImport
from app.models.column_mapping import ColumnMapping
from app.models.enums import ImportStatus
from app.services import import_service
from app.services.audit_service import log_action
from app.ai.llm_provider import get_llm_provider
from app.ai.column_mapper import TARGET_FIELDS, suggest_mappings, validate_no_collisions
from app.schemas.schemas import ImportPreview, ColumnMappingConfirm, ColumnMappingItem

router = APIRouter(prefix="/api/imports", tags=["imports"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _org_id() -> uuid.UUID:
    return uuid.UUID(settings.DEMO_ORG_ID)


@router.post("/upload", response_model=ImportPreview)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV or XLSX file and get a preview."""
    if not file.filename:
        raise HTTPException(400, "Filename required")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(400, "Only CSV and XLSX files supported")

    content = await file.read()
    data_import = await import_service.create_import(
        db, _org_id(), file.filename, ext, content,
    )

    return ImportPreview(
        id=str(data_import.id),
        filename=data_import.filename,
        file_type=data_import.file_type,
        status=data_import.status,
        columns=data_import.columns_list,
        preview_rows=data_import.preview_rows_list,
        row_count=len(data_import.preview_rows_list),
        created_at=data_import.created_at.isoformat() if data_import.created_at else None,
    )


@router.get("", response_model=list[ImportPreview])
async def list_imports(db: AsyncSession = Depends(get_db)):
    """List all imports."""
    result = await db.execute(
        select(DataImport)
        .where(DataImport.organization_id == _org_id())
        .order_by(DataImport.created_at.desc())
    )
    imports = result.scalars().all()
    return [
        ImportPreview(
            id=str(i.id),
            filename=i.filename,
            file_type=i.file_type,
            status=i.status,
            row_count=i.row_count,
            created_at=i.created_at.isoformat() if i.created_at else None,
        )
        for i in imports
    ]


@router.get("/{import_id}")
async def get_import(import_id: str, db: AsyncSession = Depends(get_db)):
    """Get import details with preview."""
    data_import = await db.get(DataImport, uuid.UUID(import_id))
    if not data_import:
        raise HTTPException(404, "Import not found")

    response = {
        "id": str(data_import.id),
        "filename": data_import.filename,
        "file_type": data_import.file_type,
        "status": data_import.status,
        "row_count": data_import.row_count,
        "error_message": data_import.error_message,
        "created_at": data_import.created_at.isoformat() if data_import.created_at else None,
    }

    # Include preview — prefer persisted metadata (survives /tmp restart on Render)
    # but try the raw file first if it still exists (freshest data).
    preview = None
    try:
        preview = import_service.read_file_preview(data_import.raw_storage_path)
    except Exception:
        preview = None

    if preview:
        response["columns"] = preview["columns"]
        response["preview_rows"] = preview["preview_rows"]
    else:
        response["columns"] = data_import.columns_list
        response["preview_rows"] = data_import.preview_rows_list

    # Include current mappings
    mappings_result = await db.execute(
        select(ColumnMapping).where(ColumnMapping.import_id == data_import.id)
    )
    mappings = mappings_result.scalars().all()
    response["mappings"] = [
        {
            "source_column": m.source_column,
            "target_field": m.target_field,
            "confidence": m.confidence,
            "confirmed": m.confirmed,
            "suggested_by": m.suggested_by,
        }
        for m in mappings
    ]

    return response


@router.get("/{import_id}/suggestions")
async def get_mapping_suggestions(import_id: str, db: AsyncSession = Depends(get_db)):
    """Get AI-suggested column mappings (heuristic + optional LLM refinement).

    Phase 2: collision detection runs on the heuristic suggestions and the
    result is returned alongside them so the UI can show what was auto-selected
    and what was dropped.

    Resilience (production incident 2026-09-05): the AI provider call is
    best-effort. Any NVIDIA failure — missing SDK, invalid credentials,
    outage, rate limit, malformed output — is logged (never the API key)
    and the endpoint degrades to the deterministic heuristic suggestions
    so a temporary AI failure can never fail an import.
    """
    data_import = await db.get(DataImport, uuid.UUID(import_id))
    if not data_import:
        raise HTTPException(404, "Import not found")

    # A missing/unreadable raw file (e.g. ephemeral /tmp storage restart on
    # Render) must not 500 — fall back to the persisted column/preview metadata
    # that was captured at upload time.
    preview = None
    try:
        preview = import_service.read_file_preview(data_import.raw_storage_path)
    except Exception as exc:
        logger.warning(
            "Could not read stored preview file for import %s (%s: %s) — "
            "falling back to persisted metadata",
            import_id, type(exc).__name__, exc,
        )

    if preview:
        source_columns = preview["columns"]
        sample_rows = preview["preview_rows"][:3]
    else:
        source_columns = data_import.columns_list
        sample_rows = data_import.preview_rows_list[:3]

    # If neither the raw file nor persisted preview metadata is available
    # (e.g. an import uploaded before the persistence fix, then the server
    # restarted), we cannot reconstruct the columns at all. Surface a clear,
    # sanitized message — never a filesystem path or stack trace.
    if not source_columns:
        raise HTTPException(
            status_code=409,
            detail=(
                "The source file for this import is no longer available on the "
                "server, and no column metadata was persisted for it. Please "
                "delete this batch and re-upload the CSV to continue."
            ),
        )

    # Best-effort AI refinement — NVIDIA failures must never break imports.
    # NOTE: the OpenAI SDK never includes the API key in exception messages.
    from app.ai.llm_provider import NoOpLLMProvider
    llm_suggestions: list[dict[str, Any]] = []
    llm_provider_obj = get_llm_provider()
    provider_is_noop = isinstance(llm_provider_obj, NoOpLLMProvider)

    if not provider_is_noop:
        try:
            llm_suggestions = await llm_provider_obj.suggest_column_mappings(
                source_columns, TARGET_FIELDS, sample_rows,
            )
        except Exception as exc:
            logger.warning(
                "AI column-mapping provider unavailable for import %s (%s: %s) — "
                "falling back to heuristic suggestions",
                import_id, type(exc).__name__, exc,
            )
            llm_suggestions = []

    # Phase 2: enforce one-target-one-source on EVERY source of suggestions.
    if llm_suggestions and not isinstance(llm_suggestions, list):
        llm_suggestions = []
    mapping_result = suggest_mappings(source_columns, TARGET_FIELDS)
    heuristic_suggestions = mapping_result["suggestions"]
    collisions = mapping_result["collisions"]

    # Track the provenance so the UI can report which source was used.
    provider_error: str | None = None
    mapping_source = "heuristic"

    # If the LLM returned structured suggestions (list of {source_column,
    # target_field}), use them — but still enforce collision resolution.
    chosen = heuristic_suggestions
    if not provider_is_noop and isinstance(llm_suggestions, list) and llm_suggestions:
        try:
            selected = [
                {
                    "source_column": str(s.get("source", s.get("source_column", ""))),
                    "target_field": str(s.get("target", s.get("target_field", ""))),
                    "confidence": s.get("confidence", 0.9),
                    "suggested_by": "llm",
                }
                for s in llm_suggestions
                if s.get("source") or s.get("source_column")
            ]
            if selected:
                chosen = selected
                mapping_source = "llm"
        except Exception:
            chosen = heuristic_suggestions
            provider_error = "LLM response parsing failed"
    elif provider_is_noop:
        provider_error = "LLM not configured — using heuristic suggestions"
    elif not llm_suggestions:
        provider_error = "NVIDIA provider unavailable — using heuristic suggestions"

    errors = validate_no_collisions(chosen)
    return {
        "suggestions": chosen,
        "collisions": collisions,
        "target_fields": TARGET_FIELDS,
        "source": mapping_source,
        "provider_error": provider_error,
        "collision_errors": errors,
    }


@router.post("/{import_id}/map")
async def confirm_mappings(
    import_id: str,
    body: ColumnMappingConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Confirm column mappings and trigger processing."""
    data_import = await db.get(DataImport, uuid.UUID(import_id))
    if not data_import:
        raise HTTPException(404, "Import not found")

    org_id = _org_id()

    # Phase 2: one-target-one-source validation — never allow two source
    # columns to silently overwrite the same target field.
    mapping_items = [
        {
            "source_column": m.source_column,
            "target_field": m.target_field,
        }
        for m in body.mappings
    ]
    collision_errors = validate_no_collisions(mapping_items)
    if collision_errors:
        raise HTTPException(
            400,
            f"Column mapping collision detected. {collision_errors[0]} "
            "Select exactly one source column per target field.",
        )

    # Save confirmed mappings
    for mapping in body.mappings:
        cm = ColumnMapping(
            organization_id=org_id,
            import_id=data_import.id,
            source_column=mapping.source_column,
            target_field=mapping.target_field,
            confirmed=True,
            confidence=mapping.confidence or 1.0,
            suggested_by=mapping.suggested_by or "user",
        )
        db.add(cm)

    await db.flush()

    await log_action(
        db, "mappings_confirmed", "data_import", str(data_import.id),
        after={"mappings_count": len(body.mappings)},
    )

    # Process the import
    data_import.status = ImportStatus.MAPPING.value
    await db.flush()

    stats = await import_service.process_import(db, data_import.id, org_id)

    # Run identity resolution
    from app.core.identity.resolver import resolve_identities
    merge_stats = await resolve_identities(db, org_id)

    # Run leakage detection
    from app.services.leakage_service import detect_leakage_for_organization
    leakage_stats = await detect_leakage_for_organization(db, org_id)

    return {
        "import_stats": stats,
        "merge_stats": merge_stats,
        "leakage_stats": leakage_stats,
    }


@router.delete("/{import_id}")
async def delete_import_batch(
    import_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an imported batch and safely clean up all derived records."""
    try:
        parsed_id = uuid.UUID(import_id)
    except ValueError:
        raise HTTPException(400, "Invalid import ID format")

    result = await import_service.delete_import(db, parsed_id, _org_id())
    return result


@router.post("/reset")
@router.delete("/demo/clear")
async def clear_demo_imports(
    db: AsyncSession = Depends(get_db),
):
    """Clear all imported demo batches and derived records for the demo organization."""
    result = await import_service.clear_organization_imports(db, _org_id())
    return result

