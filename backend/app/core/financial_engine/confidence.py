"""
Confidence calculation — a real, documented formula based on sample size
and data completeness. Never an LLM guess, never a hardcoded constant.

NO LLM IMPORTS ALLOWED in this package.

Formula documented in ARCHITECTURE.md:
  base_confidence = min(sample_size / reference_sample, 1.0)
  completeness_factor = fields_present / total_fields
  confidence = base_confidence * 0.7 + completeness_factor * 0.3
  Result is clamped to [0.0, 1.0] and expressed as a percentage (0-100).
"""
from __future__ import annotations

from dataclasses import dataclass

# Reference sample size — the minimum sample needed for full confidence
# on the sample-size dimension
REFERENCE_SAMPLE_SIZE = 100


@dataclass
class ConfidenceInputs:
    """Inputs to the confidence calculation."""
    sample_size: int
    fields_present: int
    total_fields: int


def calculate_confidence(inputs: ConfidenceInputs) -> float:
    """Calculate confidence score (0-100) from sample size and data completeness.

    Formula:
        base_confidence = min(sample_size / REFERENCE_SAMPLE_SIZE, 1.0)
        completeness_factor = fields_present / total_fields
        confidence = (base_confidence × 0.7) + (completeness_factor × 0.3)
        return confidence × 100, clamped to [0, 100]

    Returns:
        Float confidence score from 0 to 100.
    """
    if inputs.total_fields == 0:
        return 0.0

    base_confidence = min(inputs.sample_size / REFERENCE_SAMPLE_SIZE, 1.0)
    completeness_factor = inputs.fields_present / inputs.total_fields

    confidence = (base_confidence * 0.7) + (completeness_factor * 0.3)
    return round(max(0.0, min(100.0, confidence * 100)), 2)


def calculate_lead_confidence(
    has_phone: bool,
    has_email: bool,
    has_budget: bool,
    has_project: bool,
    has_sales_rep: bool,
    has_events: bool,
    event_count: int = 0,
) -> float:
    """Calculate confidence for a single lead's financial estimate.

    Measures data completeness of the lead's profile fields and
    uses the event count as a proxy for sample size.
    """
    total_fields = 6
    present = sum([has_phone, has_email, has_budget, has_project, has_sales_rep, has_events])

    return calculate_confidence(
        ConfidenceInputs(
            sample_size=max(event_count, 1),
            fields_present=present,
            total_fields=total_fields,
        )
    )
