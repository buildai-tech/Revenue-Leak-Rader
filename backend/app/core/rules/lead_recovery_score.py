"""
Lead Recovery Score — weighted deterministic sum of leakage rule contributions.

NO LLM INVOLVEMENT — this is a pure deterministic calculation.

Weights (named constants, documented in ARCHITECTURE.md):
- dead_but_recently_engaged: 25 points max
- repeated_re_engagement: 20 points max
- high_value_poor_followup: 20 points max
- unresolved_questions: 15 points max
- assigned_to_inactive_rep: 15 points max
- no_followup: 10 points max

Maximum possible score: 105 (sum of all rule max points)
Score is normalized to 0-100 scale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.rules.lead_leakage import RuleResult


# Maximum possible raw score (sum of all max points)
MAX_RAW_SCORE = 105


@dataclass
class RecoveryScoreResult:
    """Lead Recovery Score with contributing factors breakdown."""
    score: int  # 0-100 normalized
    raw_score: int  # Raw sum of triggered rule points
    max_possible: int  # MAX_RAW_SCORE
    contributing_factors: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical


def calculate_recovery_score(rule_results: list[RuleResult]) -> RecoveryScoreResult:
    """Calculate the Lead Recovery Score from rule results.

    The score is a weighted deterministic sum of triggered rules,
    normalized to 0-100. Higher score = more recoverable (more leakage detected).

    Risk levels:
    - 0-25: low
    - 26-50: medium
    - 51-75: high
    - 76-100: critical
    """
    raw_score = 0
    contributing = []

    for r in rule_results:
        if r.triggered:
            raw_score += r.points
            contributing.append({
                "rule": r.rule,
                "points": r.points,
                "evidence": r.evidence,
            })

    # Normalize to 0-100
    normalized = round((raw_score / MAX_RAW_SCORE) * 100) if MAX_RAW_SCORE > 0 else 0
    normalized = min(100, max(0, normalized))

    # Determine risk level
    if normalized >= 76:
        risk_level = "critical"
    elif normalized >= 51:
        risk_level = "high"
    elif normalized >= 26:
        risk_level = "medium"
    else:
        risk_level = "low"

    return RecoveryScoreResult(
        score=normalized,
        raw_score=raw_score,
        max_possible=MAX_RAW_SCORE,
        contributing_factors=contributing,
        risk_level=risk_level,
    )
