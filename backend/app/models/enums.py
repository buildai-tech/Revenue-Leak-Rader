"""Shared enums used across models."""
from __future__ import annotations

import enum


class ImportStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PREVIEWING = "previewing"
    MAPPING = "mapping"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InterventionStatus(str, enum.Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class LeakageStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class LeakageTier(str, enum.Enum):
    """Four-tier financial trust model — the core of the product."""
    OBSERVED_FACT = "observed_fact"
    MODEL_PREDICTION = "model_prediction"
    ESTIMATED_FINANCIAL_IMPACT = "estimated_financial_impact"
    CONFIRMED_RECOVERED_REVENUE = "confirmed_recovered_revenue"


class LeakageCategory(str, enum.Enum):
    DEAD_BUT_RECENTLY_ENGAGED = "dead_but_recently_engaged"
    UNRESOLVED_QUESTIONS = "unresolved_questions"
    REPEATED_RE_ENGAGEMENT = "repeated_re_engagement"
    ASSIGNED_TO_INACTIVE_REP = "assigned_to_inactive_rep"
    NO_FOLLOWUP = "no_followup"
    HIGH_VALUE_POOR_FOLLOWUP = "high_value_poor_followup"
    RESPONSE_DELAY = "response_delay"
    NEVER_CONTACTED = "never_contacted"


class OutcomeType(str, enum.Enum):
    CONVERTED = "converted"
    RE_ENGAGED = "re_engaged"
    LOST = "lost"
    NOT_INTERESTED = "not_interested"


class IdentityMergeMethod(str, enum.Enum):
    EXACT_PHONE = "exact_phone"
    EXACT_EMAIL = "exact_email"
    MANUAL = "manual"
