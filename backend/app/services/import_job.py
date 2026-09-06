"""
Import pipeline background worker.

A large import must NOT be processed inside the browser-facing HTTP request —
the client would have to stay connected for the whole run and a disconnect
would cancel the pipeline. Instead ``POST /imports/{id}/map`` now just records
the mappings and enqueues a ``background_jobs`` row; this module's asyncio
worker (started on FastAPI lifespan) picks pending jobs up and runs the
pipeline (process → identity → leakage) with status/progress persisted to the
same job row, which the frontend polls.

Mechanism choice: the project already has a ``background_jobs`` table and the
app already daemonizes async work (column-mapping refinement). No Redis /
Celery / external queue is required — one uvicorn worker, one consumer.

Restart safety: jobs stuck in ``running`` at startup are marked ``failed`` so
a Render restart never silently leaves a half-finished import in limbo.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models.background_job import BackgroundJob
from app.models.data_import import DataImport
from app.models.enums import ImportStatus, JobStatus
from app.models.timestamps import utc_now

logger = logging.getLogger(__name__)

JOB_TYPE = "import_process"
BOOT_PAUSE_S = 2.0  # brief initial delay so the worker doesn't race startup
POLL_INTERVAL_S = 1.0


def _now_tz() -> datetime:
    return datetime.now(timezone.utc)


async def claim_next_job() -> uuid.UUID | None:
    """Atomically claim (pending→running) the oldest import job, if any."""
    async with async_session_factory() as db:
        job = (await db.execute(
            select(BackgroundJob)
            .where(
                BackgroundJob.job_type == JOB_TYPE,
                BackgroundJob.status == JobStatus.PENDING.value,
            )
            .order_by(BackgroundJob.created_at)
            .limit(1)
        )).scalars().first()
        if job is None:
            return None
        job.status = JobStatus.RUNNING.value
        job.started_at = utc_now()
        await db.commit()
        return job.id


async def execute_job(
    job_id: uuid.UUID,
    session_factory=async_session_factory,
) -> None:
    """Run one import pipeline job to completion (or mark it failed).

    `session_factory` is injectable so tests can drive the job against their
    own scratch database; production uses the app session factory.
    """
    try:
        async with session_factory() as db:
            job = await db.get(BackgroundJob, job_id)
            if not job or job.status not in (
                JobStatus.PENDING.value,
                JobStatus.RUNNING.value,
            ):
                return

            import_id = uuid.UUID((job.payload or {}).get("import_id", ""))
            data_import = await db.get(DataImport, import_id)
            if not data_import:
                raise ValueError(f"DataImport {import_id} not found")

            org_id = data_import.organization_id
            data_import.status = ImportStatus.PROCESSING.value
            job.payload = {
                **(job.payload or {}),
                "stage": "process_import",
                "processed_rows": 0,
                "total_rows": data_import.row_count or 0,
                "leads_created": 0,
                "errors": 0,
                "import_stats": None,
                "merge_stats": None,
                "leakage_stats": None,
            }
            await db.commit()

            from app.services.import_service import process_import
            from app.core.identity.resolver import resolve_identities
            from app.services.leakage_service import detect_leakage_for_organization

            def _make_progress(total: int):
                async def _on_progress(_total: int, stats: dict[str, Any]):
                    job.payload = {
                        **(job.payload or {}),
                        "stage": "process_import",
                        "processed_rows": stats["leads_created"],
                        "total_rows": total,
                        "leads_created": stats["leads_created"],
                        "errors": stats["errors"],
                    }
                    await db.commit()
                return _on_progress

            stats = await process_import(
                db, import_id, org_id,
                on_progress=_make_progress(data_import.row_count or 0),
            )

            job.payload = {
                **(job.payload or {}),
                "stage": "identity",
                "processed_rows": stats["total_rows"],
                "leads_created": stats["leads_created"],
                "errors": stats["errors"],
                "import_stats": stats,
            }
            await db.commit()

            merge_stats = await resolve_identities(db, org_id)

            job.payload = {
                **(job.payload or {}),
                "stage": "leakage",
                "merge_stats": merge_stats,
            }
            await db.commit()

            leakage_stats = await detect_leakage_for_organization(db, org_id)

            # detect_leakage_for_organization expunges the whole session per
            # chunk (bounded-memory batching) — reload job + import so the
            # terminal status writes below are persisted, not lost on detach.
            job = await db.get(BackgroundJob, job_id)
            data_import = await db.get(DataImport, import_id)

            data_import.status = ImportStatus.COMPLETED.value
            data_import.row_count = stats.get("total_rows", data_import.row_count)
            data_import.error_message = None
            job.status = JobStatus.COMPLETED.value
            job.finished_at = _now_tz()
            job.error = None
            job.payload = {
                **(job.payload or {}),
                "stage": "done",
                "processed_rows": stats.get("total_rows", 0),
                "import_stats": stats,
                "merge_stats": merge_stats,
                "leakage_stats": leakage_stats,
            }
            await db.commit()

            logger.info(
                "Import job %s completed: %s leads, %s errors, %s leakage events",
                job_id, stats.get("leads_created"), stats.get("errors"),
                leakage_stats.get("total_events"),
            )

    except Exception as exc:
        logger.exception("Import job %s failed", job_id)
        async with session_factory() as db:
            job = await db.get(BackgroundJob, job_id)
            if job:
                import_id = uuid.UUID((job.payload or {}).get("import_id", ""))
                data_import = await db.get(DataImport, import_id)
                message = f"Pipeline failed: {type(exc).__name__}"
                job.status = JobStatus.FAILED.value
                job.error = message
                job.finished_at = _now_tz()
                if data_import:
                    data_import.status = ImportStatus.FAILED.value
                    data_import.error_message = message
                await db.commit()


async def run_import_worker(loop_stop: asyncio.Event) -> None:
    """Worker loop — claim and run one job at a time until asked to stop."""
    try:
        await asyncio.sleep(BOOT_PAUSE_S)
        while not loop_stop.is_set():
            job_id = await claim_next_job()
            if job_id is None:
                try:
                    await asyncio.wait_for(loop_stop.wait(), timeout=POLL_INTERVAL_S)
                except asyncio.TimeoutError:
                    pass
                continue
            await execute_job(job_id)
    except asyncio.CancelledError:
        logger.info("Import worker cancelled (shutdown)")
        raise
    except Exception:
        logger.exception("Import worker crashed")


async def mark_startup_interrupted_jobs() -> None:
    """After a restart, any job left in ``running`` was killed mid-flight.

    It cannot be resumed safely (partial rows may exist), so mark it + its
    import `failed` with a clear, non-destructive message. The user re-runs by
    confirming the (already persisted) mappings again.
    """
    async with async_session_factory() as db:
        jobs = (await db.execute(
            select(BackgroundJob).where(
                BackgroundJob.job_type == JOB_TYPE,
                BackgroundJob.status == JobStatus.RUNNING.value,
            )
        )).scalars().all()
        for job in jobs:
            try:
                import_id = uuid.UUID((job.payload or {}).get("import_id", ""))
            except (TypeError, ValueError):
                import_id = None
            job.status = JobStatus.FAILED.value
            job.error = "Interrupted by server restart — re-run the mapping to retry"
            job.finished_at = _now_tz()
            if import_id:
                data_import = await db.get(DataImport, import_id)
                if data_import and data_import.status == ImportStatus.PROCESSING.value:
                    data_import.status = ImportStatus.FAILED.value
                    data_import.error_message = job.error
        await db.commit()
        if jobs:
            logger.info("Marked %d interrupted import job(s) failed after restart", len(jobs))