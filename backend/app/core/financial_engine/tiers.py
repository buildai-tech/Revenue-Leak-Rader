"""
Four-tier financial trust model.

NO LLM IMPORTS ALLOWED in this file or any file in this package.

Each tier represents a different level of certainty and must be displayed
with appropriate labeling in the UI (TierBadge component).
"""
from __future__ import annotations

import enum


class Tier(str, enum.Enum):
    """Four-tier financial trust model — the core credibility mechanism."""

    OBSERVED_FACT = "observed_fact"
    MODEL_PREDICTION = "model_prediction"
    ESTIMATED_FINANCIAL_IMPACT = "estimated_financial_impact"
    CONFIRMED_RECOVERED_REVENUE = "confirmed_recovered_revenue"


# Display labels for UI TierBadge component
TIER_DISPLAY = {
    Tier.OBSERVED_FACT: {
        "label": "Observed Fact",
        "description": "Raw count or aggregate from data — no assumptions applied",
        "color": "blue",
    },
    Tier.MODEL_PREDICTION: {
        "label": "Model Prediction",
        "description": "Scored/ruled judgment with confidence value",
        "color": "purple",
    },
    Tier.ESTIMATED_FINANCIAL_IMPACT: {
        "label": "Estimated Financial Impact",
        "description": "Prediction × disclosed financial assumptions",
        "color": "amber",
    },
    Tier.CONFIRMED_RECOVERED_REVENUE: {
        "label": "Confirmed Recovered",
        "description": "Real recovery from a recorded outcome with booking amount",
        "color": "green",
    },
}
