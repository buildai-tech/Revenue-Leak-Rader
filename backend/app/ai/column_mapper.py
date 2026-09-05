"""
Heuristic column mapper — keyword and similarity matching.

Used as fallback when LLM is unavailable, and as the basis for
LLM-suggested mappings (LLM refines heuristic suggestions).

Phase 1/2 requirements implemented here:
- Extended fuzzy keyword coverage for timestamp fields
  (received_at, lead_received_at, enquiry_at, first_contact_at, response_at,
   last_contact_at, …)
- One-target-one-source collision validation: if two source columns map to the
  same target field, the highest-confidence mapping wins, the loser is reported
  as a collision (never silently overwritten), and the caller may override.
"""
from __future__ import annotations

from typing import Any


# Known target fields and their likely source column names.
# NOTE: keywords are matched against a normalized source column name
# (lowercase, spaces/dashes → underscores). Exact match wins (confidence 1.0);
# substring containment scores by length ratio.
_FIELD_KEYWORDS: dict[str, list[str]] = {
    "name": ["name", "lead_name", "customer_name", "client_name", "full_name", "contact_name"],
    "phone_raw": ["phone", "mobile", "contact_number", "phone_number", "mob", "cell", "tel"],
    "email": ["email", "email_id", "email_address", "mail"],
    "status": ["status", "lead_status", "current_status", "stage", "disposition", "funnel_status"],
    "budget": ["budget", "deal_value", "amount", "value", "price", "expected_value", "deal_size", "deal_amount"],
    "source": ["lead_source", "source", "channel", "medium", "origin", "source_name"],
    "campaign_name": ["campaign_name", "campaign", "campaign_id", "utm_campaign"],
    "project_name": ["project", "project_name", "location", "site", "community", "project_id"],
    "property_type": ["property_type", "property", "unit_type", "configuration", "config", "property_kind"],
    "sales_rep_name": ["salesperson_id", "salesperson", "agent", "sales_rep", "assigned_to", "rep", "owner", "assigned"],
    # ── Timestamps (Phase 1 extended keyword coverage) ──────────────────────
    "created_at": [
        "received_at", "lead_received_at", "enquiry_at", "enquiry_date",
        "created_at", "lead_created_at", "created", "created_date",
        "lead_date", "registration_date", "date_received", "enquiry_received_at",
    ],
    "first_contact_at": [
        "first_contact", "first_contact_at", "first_contact_date",
        "first_response", "first_response_at", "response_at",
        "first_contacted_at", "contact_at",
    ],
    "last_followup_at": [
        "last_contact", "last_contact_at", "last_followup", "last_followup_at",
        "last_activity", "last_activity_at", "last_response", "last_response_at",
        "follow_up_date", "followup_date", "last_touch_at",
    ],
    "site_visit_at": [
        "site_visit", "site_visit_at", "site_visit_date", "visit_date",
        "visit_at", "sitevisit_at", "site_visit_completed_at",
    ],
    "negotiation_at": [
        "negotiation", "negotiation_at", "negotiation_date",
        "negotiation_start", "negotiation_started_at", "negotiation_begin_at",
    ],
    "closed_at": [
        "closed_at", "closed_date", "close_date", "deal_closed_at",
        "closure_date", "closed_on", "deal_closed_on",
    ],
    "total_touches": [
        "total_touches", "touches", "touch_count", "number_of_touches",
        "num_touches", "interactions", "interaction_count", "contact_count",
    ],
    "commission_rate": ["commission_rate", "commission", "commission_pct", "commission_percent"],
    "lost_reason": ["lost_reason", "rejection_reason", "drop_reason", "reason", "reason_lost"],
}

# Canonical target-field list for the import wizard (order = UI display order).
TARGET_FIELDS: list[str] = [
    "name", "phone_raw", "email", "status", "budget", "commission_rate",
    "source", "campaign_name", "project_name", "property_type", "sales_rep_name",
    "created_at", "first_contact_at", "last_followup_at", "site_visit_at",
    "negotiation_at", "closed_at", "total_touches", "lost_reason",
]

# Confidence floor for a suggestion to be kept at all
_MIN_CONFIDENCE = 0.3


def _normalize_column(name: str) -> str:
    return (
        name.strip().lower()
        .replace(" ", "_").replace("-", "_").replace(".", "_")
    )


def _score_source_against_target(source_lower: str, keywords: list[str]) -> float:
    """Best similarity score of a source column against one target's keywords."""
    best = 0.0
    for keyword in keywords:
        if source_lower == keyword:
            return 1.0
        if keyword in source_lower or source_lower in keyword:
            score = len(keyword) / max(len(source_lower), len(keyword))
            if score > best:
                best = score
    return best


def suggest_mappings(
    source_columns: list[str], target_fields: list[str] | None = None
) -> dict[str, Any]:
    """Suggest column → field mappings with one-target-one-source validation.

    Returns:
        {
          "suggestions": [{source_column, target_field, confidence, suggested_by}],
          "collisions":  [{target_field, winner: {source_column, confidence},
                           dropped: [{source_column, confidence}],
                           resolution: "highest_confidence_auto_selected"}],
        }

    Collision policy (Phase 2): when two source columns both match the same
    target field, the highest-confidence mapping is auto-selected and the other
    candidates are reported as dropped collisions. Data is never silently
    overwritten — the caller/UI can override before confirm.
    """
    targets = target_fields if target_fields is not None else TARGET_FIELDS

    # 1. Best target per source column
    per_source: list[dict[str, Any]] = []
    for source in source_columns:
        source_lower = _normalize_column(source)
        best_target = None
        best_conf = 0.0
        for target in targets:
            keywords = _FIELD_KEYWORDS.get(target, [])
            if not keywords:
                continue
            score = _score_source_against_target(source_lower, keywords)
            if score > best_conf:
                best_target = target
                best_conf = round(score, 2)
        if best_target and best_conf >= _MIN_CONFIDENCE:
            per_source.append({
                "source_column": source,
                "target_field": best_target,
                "confidence": best_conf,
                "suggested_by": "heuristic",
            })

    # 2. One-target-one-source collision resolution
    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in per_source:
        by_target.setdefault(item["target_field"], []).append(item)

    suggestions: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    for target, candidates in by_target.items():
        candidates_sorted = sorted(candidates, key=lambda c: c["confidence"], reverse=True)
        winner = candidates_sorted[0]
        suggestions.append(winner)
        if len(candidates_sorted) > 1:
            collisions.append({
                "target_field": target,
                "winner": {
                    "source_column": winner["source_column"],
                    "confidence": winner["confidence"],
                },
                "dropped": [
                    {"source_column": c["source_column"], "confidence": c["confidence"]}
                    for c in candidates_sorted[1:]
                ],
                "resolution": "highest_confidence_auto_selected",
            })

    # Stable, deterministic ordering (canonical target order, then source name)
    suggestions.sort(key=lambda s: (TARGET_FIELDS.index(s["target_field"]), s["source_column"]))
    collisions.sort(key=lambda c: c["target_field"])
    return {"suggestions": suggestions, "collisions": collisions}


def heuristic_suggest(
    source_columns: list[str], target_fields: list[str] | None = None
) -> list[dict[str, Any]]:
    """Backward-compatible helper: collision-resolved suggestion list only."""
    return suggest_mappings(source_columns, target_fields)["suggestions"]


def validate_no_collisions(mappings: list[dict[str, Any]]) -> list[str]:
    """Validate user-confirmed mappings: at most one source column per target.

    Returns a list of human-readable collision errors (empty when valid).
    """
    seen: dict[str, list[str]] = {}
    for m in mappings:
        target = m.get("target_field")
        source = m.get("source_column")
        if target:
            seen.setdefault(target, []).append(source or "?")
    return [
        f"Target field '{target}' is mapped by multiple source columns: {', '.join(sources)}. "
        "Select exactly one source column per target field."
        for target, sources in sorted(seen.items())
        if len(sources) > 1
    ]
