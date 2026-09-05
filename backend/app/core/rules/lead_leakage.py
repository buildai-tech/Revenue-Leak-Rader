"""
Lead leakage detection rules.

Each rule:
1. Is independently implemented and tested
2. Outputs {rule, points, evidence}
3. Is purely deterministic — no LLM involvement
4. Is documented in ARCHITECTURE.md

Rules:
- dead_but_recently_engaged: status dead/closed/lost + recent inbound event
- unresolved_questions: inbound message with no subsequent outbound
- repeated_re_engagement: ≥2 re-engagement events after dead status
- assigned_to_inactive_rep: lead assigned to rep with is_active=false
- no_followup_configurable_days: no outbound event within N days
- high_value_poor_followup: budget above threshold + fewer than M follow-ups
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _ensure_utc(dt: datetime | str | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class RuleResult:
    """Output of each leakage detection rule."""
    rule: str
    points: int
    evidence: list[dict[str, Any]] = field(default_factory=list)
    triggered: bool = False


@dataclass
class LeadData:
    """Lightweight lead data for rule evaluation — no ORM dependency."""
    lead_id: str
    name: str
    status: str | None
    budget: float | None
    sales_rep_name: str | None
    sales_rep_active: bool | None
    created_at: datetime | None
    last_followup_at: datetime | None
    events: list[dict[str, Any]] = field(default_factory=list)


# ── Configuration Constants (named, documented in ARCHITECTURE.md) ──────

# Days threshold for "recent" engagement on a dead lead
RECENT_ENGAGEMENT_DAYS = 30

# Days threshold for no follow-up rule
NO_FOLLOWUP_DEFAULT_DAYS = 7

# Budget threshold for "high value" (₹30 Lakh)
HIGH_VALUE_BUDGET_THRESHOLD = 3_000_000.0

# Minimum follow-ups expected for high-value leads
HIGH_VALUE_MIN_FOLLOWUPS = 3

# Days window for unresolved questions
UNRESOLVED_QUESTION_DAYS = 3

# Dead statuses
DEAD_STATUSES = {"dead", "closed", "lost", "not_interested", "junk"}


def _get_events_by_type(events: list[dict], event_type: str) -> list[dict]:
    """Filter events by type."""
    return [e for e in events if e.get("event_type") == event_type]


def _get_inbound_events(events: list[dict]) -> list[dict]:
    """Get inbound events (messages, calls, visits from the lead)."""
    inbound_types = {"inbound_call", "inbound_message", "inbound_email", "site_visit", "walk_in"}
    return [e for e in events if e.get("event_type") in inbound_types]


def _get_outbound_events(events: list[dict]) -> list[dict]:
    """Get outbound events (calls, messages from the sales team)."""
    outbound_types = {"outbound_call", "outbound_message", "outbound_email", "followup"}
    return [e for e in events if e.get("event_type") in outbound_types]


def dead_but_recently_engaged(lead: LeadData, now: datetime | None = None) -> RuleResult:
    """Detect leads marked dead/closed/lost that have recent inbound engagement.

    Points: 25 (high — this is the most actionable leakage type)
    """
    now = _ensure_utc(now) or datetime.now(timezone.utc)
    result = RuleResult(rule="dead_but_recently_engaged", points=0)

    if not lead.status or lead.status.lower() not in DEAD_STATUSES:
        return result

    inbound = _get_inbound_events(lead.events)
    cutoff = now - timedelta(days=RECENT_ENGAGEMENT_DAYS)

    recent_inbound = [
        e for e in inbound
        if e.get("occurred_at") and _ensure_utc(e["occurred_at"]) > cutoff
    ]

    if recent_inbound:
        result.triggered = True
        result.points = 25
        result.evidence = [
            {"type": "status_check", "detail": f"Lead marked as '{lead.status}'"},
            {"type": "recent_engagement", "detail": f"{len(recent_inbound)} inbound event(s) in last {RECENT_ENGAGEMENT_DAYS} days"},
        ]
        for e in recent_inbound[:3]:  # Show up to 3 recent events
            result.evidence.append({
                "type": "event_detail",
                "detail": f"{e.get('event_type')} on {e.get('occurred_at', 'unknown date')}",
            })

    return result


def unresolved_questions(lead: LeadData, now: datetime | None = None) -> RuleResult:
    """Detect inbound messages with no subsequent outbound response.

    Points: 15
    """
    now = _ensure_utc(now) or datetime.now(timezone.utc)
    result = RuleResult(rule="unresolved_questions", points=0)

    inbound = _get_inbound_events(lead.events)
    outbound = _get_outbound_events(lead.events)

    if not inbound:
        return result

    # Sort events by time
    inbound_sorted = sorted(inbound, key=lambda e: _ensure_utc(e.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc))
    outbound_sorted = sorted(outbound, key=lambda e: _ensure_utc(e.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc))

    # Find inbound events with no subsequent outbound within the window
    unresolved_count = 0
    for ib in inbound_sorted:
        ib_time = _ensure_utc(ib.get("occurred_at"))
        if not ib_time:
            continue
        deadline = ib_time + timedelta(days=UNRESOLVED_QUESTION_DAYS)
        # Check if any outbound happened between ib_time and deadline
        has_response = any(
            ob.get("occurred_at") and ib_time < _ensure_utc(ob["occurred_at"]) <= deadline
            for ob in outbound_sorted
        )
        if not has_response and ib_time < now:
            unresolved_count += 1

    if unresolved_count > 0:
        result.triggered = True
        result.points = 15
        result.evidence = [
            {"type": "unresolved_count", "detail": f"{unresolved_count} inbound message(s) without response within {UNRESOLVED_QUESTION_DAYS} days"},
        ]

    return result


def repeated_re_engagement(lead: LeadData) -> RuleResult:
    """Detect ≥2 re-engagement events after dead status.

    Points: 20
    """
    result = RuleResult(rule="repeated_re_engagement", points=0)

    if not lead.status or lead.status.lower() not in DEAD_STATUSES:
        return result

    # Look for status change to dead, then count subsequent inbound events
    inbound = _get_inbound_events(lead.events)
    status_changes = [e for e in lead.events if e.get("event_type") == "status_change"]

    # Find when the lead was marked dead
    dead_time = None
    for sc in sorted(status_changes, key=lambda e: _ensure_utc(e.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc)):
        payload = sc.get("event_payload", {}) or {}
        new_status = payload.get("new_status", "").lower()
        if new_status in DEAD_STATUSES:
            dead_time = _ensure_utc(sc.get("occurred_at"))

    if dead_time is None:
        # If no explicit status_change event, count all inbound as re-engagement
        # since the lead IS currently dead
        if len(inbound) >= 2:
            result.triggered = True
            result.points = 20
            result.evidence = [
                {"type": "re_engagement_count", "detail": f"{len(inbound)} inbound events on a '{lead.status}' lead"},
            ]
        return result

    # Count inbound events after the dead timestamp
    re_engagements = [
        e for e in inbound
        if e.get("occurred_at") and _ensure_utc(e["occurred_at"]) > dead_time
    ]

    if len(re_engagements) >= 2:
        result.triggered = True
        result.points = 20
        result.evidence = [
            {"type": "status_check", "detail": f"Lead marked '{lead.status}'"},
            {"type": "re_engagement_count", "detail": f"{len(re_engagements)} re-engagement(s) after being marked dead"},
        ]

    return result


def assigned_to_inactive_rep(lead: LeadData) -> RuleResult:
    """Detect leads assigned to inactive sales reps.

    Points: 15
    """
    result = RuleResult(rule="assigned_to_inactive_rep", points=0)

    if lead.sales_rep_active is not None and not lead.sales_rep_active:
        result.triggered = True
        result.points = 15
        result.evidence = [
            {"type": "inactive_rep", "detail": f"Assigned to '{lead.sales_rep_name}' who is marked inactive"},
        ]

    return result


def no_followup_configurable_days(
    lead: LeadData,
    now: datetime | None = None,
    days: int = NO_FOLLOWUP_DEFAULT_DAYS,
) -> RuleResult:
    """Detect leads with no outbound event within N days.

    Points: 10
    """
    now = _ensure_utc(now) or datetime.now(timezone.utc)
    result = RuleResult(rule="no_followup", points=0)

    # Skip dead/converted leads — those don't need followup
    skip_statuses = DEAD_STATUSES | {"converted", "booked", "won", "duplicate", "invalid"}
    if lead.status and lead.status.lower() in skip_statuses:
        return result

    outbound = _get_outbound_events(lead.events)
    cutoff = now - timedelta(days=days)

    recent_outbound = [
        e for e in outbound
        if e.get("occurred_at") and _ensure_utc(e["occurred_at"]) > cutoff
    ]

    if not recent_outbound:
        result.triggered = True
        result.points = 10
        last_outbound_dt = max(
            (_ensure_utc(e.get("occurred_at")) for e in outbound if e.get("occurred_at")),
            default=None,
        )
        result.evidence = [
            {"type": "no_followup", "detail": f"No outbound contact in the last {days} days"},
        ]
        if last_outbound_dt:
            days_since = (now - last_outbound_dt).days
            result.evidence.append(
                {"type": "last_contact", "detail": f"Last outbound was {days_since} days ago"}
            )
        else:
            result.evidence.append(
                {"type": "never_contacted", "detail": "No outbound contact ever recorded"}
            )

    return result


def high_value_poor_followup(
    lead: LeadData,
    budget_threshold: float = HIGH_VALUE_BUDGET_THRESHOLD,
    min_followups: int = HIGH_VALUE_MIN_FOLLOWUPS,
) -> RuleResult:
    """Detect high-value leads with insufficient follow-up activity.

    Points: 20
    """
    result = RuleResult(rule="high_value_poor_followup", points=0)

    if not lead.budget or lead.budget < budget_threshold:
        return result

    # Skip dead/converted leads
    skip_statuses = DEAD_STATUSES | {"converted", "booked", "won"}
    if lead.status and lead.status.lower() in skip_statuses:
        return result

    outbound = _get_outbound_events(lead.events)

    if len(outbound) < min_followups:
        result.triggered = True
        result.points = 20
        result.evidence = [
            {"type": "high_value", "detail": f"Budget ₹{lead.budget:,.0f} (above ₹{budget_threshold:,.0f} threshold)"},
            {"type": "poor_followup", "detail": f"Only {len(outbound)} outbound contact(s) (minimum {min_followups} expected)"},
        ]

    return result


# ── Run all rules ───────────────────────────────────────────────────────

ALL_RULES = [
    dead_but_recently_engaged,
    unresolved_questions,
    repeated_re_engagement,
    assigned_to_inactive_rep,
    no_followup_configurable_days,
    high_value_poor_followup,
]


def evaluate_all_rules(lead: LeadData, now: datetime | None = None) -> list[RuleResult]:
    """Run all leakage rules against a lead, return all results (including non-triggered)."""
    results = []
    for rule_fn in ALL_RULES:
        if rule_fn in (dead_but_recently_engaged, unresolved_questions, no_followup_configurable_days):
            results.append(rule_fn(lead, now=now))
        else:
            results.append(rule_fn(lead))
    return results
