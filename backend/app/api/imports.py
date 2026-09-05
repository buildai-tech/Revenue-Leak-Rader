"""Import API — upload, preview, mapping, processing."""
from __future__ import annotations

import asyncio
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

# In-memory cache of non-blocking LLM column-mapping refinement results, keyed
# by import id. The mapping UI never waits on the AI: deterministic heuristic
# suggestions are returned immediately and the AI result upgrades subsequent
# requests once it lands. A single-entry per import keeps memory trivial.
_llm_mapping_cache: dict[str, dict[str, Any]] = {}


def _select_llm_suggestions(raw: Any) -> list[dict[str, Any]] | None:
    """Normalize a raw LLM mapping response into the canonical suggestion shape."""
    if not isinstance(raw, list):
        return None
    try:
        selected = [
            {
                "source_column": str(s.get("source", s.get("source_column", ""))),
                "target_field": str(s.get("target", s.get("target_field", ""))),
                "confidence": s.get("confidence", 0.9),
                "suggested_by": "llm",
            }
            for s in raw
            if s.get("source") or s.get("source_column")
        ]
        return selected or None
    except Exception:
        return None


async def _run_llm_refinement(
    import_id: str, source_columns: list[str], sample_rows: list[dict]
) -> None:
    """Best-effort background AI column-mapping refinement.

    Daemonized with asyncio so the suggestions endpoint returns instantly.
    Any failure (outage, invalid key, garbage output, cancel) is logged and
    leaves the previously-returned heuristic suggestions untouched — a
    temporary AI failure can never block or break the mapping UI.
    """
    entry = _llm_mapping_cache.setdefault(import_id, {
        "done": False, "suggestions": None, "source": "heuristic", "error": None,
    })
    try:
        provider = get_llm_provider()
        raw = await provider.suggest_column_mappings(
            source_columns, TARGET_FIELDS, sample_rows,
        )
        selected = _select_llm_suggestions(raw)
        entry["done"] = True
        entry["suggestions"] = selected
        if selected:
            entry["source"] = "llm"
        else:
            entry["error"] = (
                "AI mapping refinement returned nothing usable — "
                "using heuristic suggestions"
            )
    except asyncio.CancelledError:
        entry["done"] = True
        entry["error"] = (
            "AI mapping refinement was cancelled — using heuristic suggestions"
        )
        raise
    except Exception as exc:
        logger.warning(
            "AI column-mapping refinement failed for import %s (%s: %s) — "
            "heuristic suggestions are already returned",
            import_id, type(exc).__name__, exc,
        )
        entry["done"] = True
        entry["error"] = (
            "AI mapping refinement failed — using heuristic suggestions"
        )


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
    """Get column mappings (deterministic heuristic + optional LLM refinement).

    Phase 2: collision detection runs on the heuristic suggestions and the
    result is returned alongside them so the UI can show what was auto-selected
    and what was dropped.

    Performance (production incident 2026-09-05): this endpoint NEVER waits on
    the AI. The deterministic heuristic suggestions are computed locally and
    returned immediately; when an NVIDIA provider is configured, the LLM
    refinement is dispatched as a background task and its result upgrades
    subsequent requests (``refinement_pending`` tells the client whether to
    re-fetch). Any NVIDIA failure — missing SDK, invalid credentials, outage,
    rate limit, malformed output — is logged (never the API key) and leaves
    the already-returned heuristic suggestions in place.
    """
    data_import = await db.get(DataImport, uuid.UUID(import_id))
    if not data_import:
        raise HTTPException(404, "Import not found")

    # Source columns — prefer the persisted metadata captured at upload time
    # (no file re-parse, survives ephemeral /tmp restarts), falling back to the
    # raw file only for imports uploaded before the persistence fix.
    source_columns = data_import.columns_list
    sample_rows = data_import.preview_rows_list[:3]
    if not source_columns:
        try:
            preview = import_service.read_file_preview(
                data_import.raw_storage_path
            )
            source_columns = preview["columns"]
            sample_rows = preview["preview_rows"][:3]
        except Exception as exc:
            logger.warning(
                "Could not read stored preview file for import %s (%s: %s) — "
                "falling back to persisted metadata",
                import_id, type(exc).__name__, exc,
            )

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

    # Deterministic local baseline — computed synchronously in microseconds.
    mapping_result = suggest_mappings(source_columns, TARGET_FIELDS)
    heuristic_suggestions = mapping_result["suggestions"]
    collisions = mapping_result["collisions"]

    # AI refinement is best-effort and NEVER on the response path: NVIDIA
    # failures, outages, or rate limits must not delay the mapping UI. The
    # deterministic heuristic suggestions are returned immediately; the LLM
    # runs in a background task and its result upgrades later requests.
    from app.ai.llm_provider import NoOpLLMProvider
    llm_provider_obj = get_llm_provider()
    provider_is_noop = isinstance(llm_provider_obj, NoOpLLMProvider)

    chosen = heuristic_suggestions
    mapping_source = "heuristic"
    provider_error: str | None = None
    refinement_pending = False

    if provider_is_noop:
        provider_error = "LLM not configured — using heuristic suggestions"
    else:
        cache_key = str(data_import.id)
        cached = _llm_mapping_cache.get(cache_key)
        if cached is None:
            # First request for this import → return heuristics NOW and let the
            # LLM refinement finish in the background (frontend polls once ready).
            asyncio.create_task(_run_llm_refinement(
                cache_key, source_columns, sample_rows,
            ))
            refinement_pending = True
        elif not cached["done"]:
            refinement_pending = True
        else:
            provider_error = cached.get("error")
            if cached.get("suggestions"):
                chosen = cached["suggestions"]
                mapping_source = cached.get("source", "llm")

    errors = validate_no_collisions(chosen)
    return {
        "suggestions": chosen,
        "collisions": collisions,
        "target_fields": TARGET_FIELDS,
        "source": mapping_source,
        "provider_error": provider_error,
        "collision_errors": errors,
        "refinement_pending": refinement_pending,
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

