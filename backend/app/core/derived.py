"""
Deterministic derived fields + lifecycle event planning for imported leads.

NO LLM involvement. Pure functions over timestamp/aggregate inputs so the same
logic can run inside the import pipeline, the seed script, and unit tests.

Derived fields (Phase 4):
    response_latency_minutes = first_contact_at - created_at
    site_visit_latency_days  = site_visit_at  - created_at
    sales_cycle_days         = closed_at      - created_at
    is_dark_lead             = first_contact_at IS NULL
    is_single_touch          = total_touches == 1
    funnel_max_stage         = highest stage with verified timestamp evidence

Validation policy (Phase 4) — anomalies are FLAGGED, data is never silently
discarded or rewritten:
    first_contact_at < created_at   → flag "first_contact_before_created"
    any timestamp in the future     → flag "future_timestamp:<field>"
    closed_at < site_visit_at       → flag "closed_before_site_visit"
    any out-of-order stage pair     → flag "impossible_stage_order"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Canonical funnel stages — the ordinal IS the stage definition.
FUNNEL_STAGES: dict[str, int] = {
    "created": 0,
    "first_contact": 1,
    "follow_up": 2,
    "site_visit": 3,
    "negotiation": 4,
    "closed": 5,
}


@dataclass
class DerivedFields:
    """Deterministic derived field bundle for one lead."""
    response_latency_minutes: float | None = None
    site_visit_latency_days: float | None = None
    sales_cycle_days: float | None = None
    is_dark_lead: bool = True
    is_single_touch: bool = False
    funnel_max_stage: int = 0
    data_quality_flags: list[str] = field(default_factory=list)

    def to_flags_dict(self) -> dict[str, Any]:
        """Serialize flags for the lead.data_quality_flags JSON column."""
        return {"flags": self.data_quality_flags}


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _flag_future(when: datetime | None, name: str, now: datetime, flags: list[str]) -> None:
    if when is not None and when > now:
        flags.append(f"future_timestamp:{name}")


def compute_derived_fields(
    created_at: datetime,
    first_contact_at: datetime | None = None,
    last_contact_at: datetime | None = None,
    site_visit_at: datetime | None = None,
    negotiation_at: datetime | None = None,
    closed_at: datetime | None = None,
    total_touches: int | None = None,
    now: datetime | None = None,
) -> DerivedFields:
    """Compute all derived fields + validation flags for a single lead.

    `created_at` is required (importers must always supply a fallback — an
    estimated created_at is flagged by the importer separately).
    """
    now = _utc(now) or datetime.now(timezone.utc)
    created = _utc(created_at)
    first = _utc(first_contact_at)
    last = _utc(last_contact_at)
    visit = _utc(site_visit_at)
    negot = _utc(negotiation_at)
    closed = _utc(closed_at)

    out = DerivedFields()
    flags = out.data_quality_flags

    # ── Future timestamp policy: keep value, flag it ────────────────────────
    _flag_future(created, "created_at", now, flags)
    _flag_future(first, "first_contact_at", now, flags)
    _flag_future(last, "last_contact_at", now, flags)
    _flag_future(visit, "site_visit_at", now, flags)
    _flag_future(negot, "negotiation_at", now, flags)
    _flag_future(closed, "closed_at", now, flags)

    # ── response_latency_minutes ────────────────────────────────────────────
    if created and first:
        delta_min = (first - created).total_seconds() / 60.0
        if delta_min < 0:
            flags.append("first_contact_before_created")
        else:
            out.response_latency_minutes = round(delta_min, 2)

    # ── site_visit_latency_days ─────────────────────────────────────────────
    if created and visit:
        delta_days = (visit - created).total_seconds() / 86400.0
        if delta_days < 0:
            flags.append("site_visit_before_created")
        else:
            out.site_visit_latency_days = round(delta_days, 2)

    # ── sales_cycle_days ────────────────────────────────────────────────────
    if created and closed:
        delta_days = (closed - created).total_seconds() / 86400.0
        if delta_days < 0:
            flags.append("closed_before_created")
        else:
            out.sales_cycle_days = round(delta_days, 2)

    # ── closed_at < site_visit_at ───────────────────────────────────────────
    if closed and visit and closed < visit:
        flags.append("closed_before_site_visit")

    # ── Impossible stage ordering (any decrease along the funnel) ───────────
    ordered = [("first_contact", first), ("follow_up", last), ("site_visit", visit),
               ("negotiation", negot), ("closed", closed)]
    prev_name, prev_dt = "created", created
    for name, dt in ordered:
        if dt is None:
            continue
        if prev_dt is not None and dt < prev_dt:
            flags.append(f"impossible_stage_order:{name}_before_{prev_name}")
        prev_name, prev_dt = name, dt

    # ── Booleans ────────────────────────────────────────────────────────────
    out.is_dark_lead = first is None
    out.is_single_touch = (total_touches == 1)

    # ── funnel_max_stage (highest stage with VERIFIED timestamp evidence) ───
    stage = 0
    if last is not None:
        stage = max(stage, FUNNEL_STAGES["follow_up"])
    if first is not None:
        stage = max(stage, FUNNEL_STAGES["first_contact"])
    if visit is not None:
        stage = max(stage, FUNNEL_STAGES["site_visit"])
    if negot is not None:
        stage = max(stage, FUNNEL_STAGES["negotiation"])
    if closed is not None:
        stage = max(stage, FUNNEL_STAGES["closed"])
    out.funnel_max_stage = stage

    return out


def plan_lifecycle_events(
    created_at: datetime,
    first_contact_at: datetime | None = None,
    last_contact_at: datetime | None = None,
    site_visit_at: datetime | None = None,
    negotiation_at: datetime | None = None,
    closed_at: datetime | None = None,
    total_touches: int | None = None,
    source: str = "import",
) -> list[dict[str, Any]]:
    """Plan lifecycle events from VERIFIED source timestamps only (Phase 3).

    Event types: created → first_contact → follow_up → site_visit →
    negotiation → closed.

    Rules:
    - An event is created ONLY when a supporting source timestamp exists.
    - Individual follow-up touch timestamps are NOT fabricated. When only the
      aggregate `total_touches` is available, the aggregate is preserved in the
      follow_up event payload (and on the lead row) instead.
    - Out-of-order timestamps are still emitted (evidence is preserved) — the
      anomaly is carried by data_quality_flags, not silently dropped.
    """
    events: list[dict[str, Any]] = []

    events.append({
        "event_type": "created",
        "occurred_at": created_at,
        "event_payload": {"source": source},
    })

    if first_contact_at is not None:
        events.append({
            "event_type": "first_contact",
            "occurred_at": first_contact_at,
            "event_payload": {"source": source},
        })

    # FOLLOW_UP only when subsequent contact information exists beyond the
    # first contact itself (a last_contact equal to the first contact with a
    # single touch adds no information).
    if last_contact_at is not None:
        is_only_touch = (
            first_contact_at is not None
            and last_contact_at == first_contact_at
            and (total_touches or 0) <= 1
        )
        if not is_only_touch:
            payload: dict[str, Any] = {"source": source}
            if total_touches is not None:
                payload["note"] = (
                    "Aggregate last-contact timestamp from source data; "
                    "individual touch timestamps are not available."
                )
                payload["total_touches"] = total_touches
            events.append({
                "event_type": "follow_up",
                "occurred_at": last_contact_at,
                "event_payload": payload,
            })

    if site_visit_at is not None:
        events.append({
            "event_type": "site_visit",
            "occurred_at": site_visit_at,
            "event_payload": {"source": source},
        })

    if negotiation_at is not None:
        events.append({
            "event_type": "negotiation",
            "occurred_at": negotiation_at,
            "event_payload": {"source": source},
        })

    if closed_at is not None:
        events.append({
            "event_type": "closed",
            "occurred_at": closed_at,
            "event_payload": {"source": source},
        })

    return events


# ── Status vocabularies shared by detectors ─────────────────────────────────

# Statuses meaning the deal is genuinely over-and-lost (or unreachable).
ABANDONMENT_STATUSES = {"lost", "dead", "not_interested", "junk", "unreachable", "inactive", "closed"}
# Statuses meaning the deal was WON — never a leak.
WON_STATUSES = {"converted", "booked", "won", "closed_won"}
# Statuses meaning the lead is still moving through the pipeline.
ACTIVE_PIPELINE_STATUSES = {"new", "contacted", "interested", "qualified", "followup", "in_progress", "negotiation", "site_visit"}
