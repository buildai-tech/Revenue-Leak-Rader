"""
Named, versioned formula functions for financial calculations.

NO LLM IMPORTS ALLOWED in this package.

Every formula function:
1. Has a unique formula_id and formula_version
2. Returns a FinancialResult dataclass
3. Documents its assumptions explicitly
4. Is independently unit-testable

Formulas:
- estimated_recoverable_leakage_v1: lead.budget × recovery_probability × contribution_margin
- response_delay_impact_v1: (baseline_conversion - bucket_conversion) × avg_deal_value × lead_count
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.financial_engine.tiers import Tier


@dataclass
class FinancialResult:
    """Output of every formula function — all fields required for persistence."""
    amount_inr: Decimal
    tier: Tier
    confidence: float
    formula_id: str
    formula_version: str
    assumptions: dict[str, Any]
    data_source: str

    def validate(self) -> None:
        """Reject if any required field is missing or invalid."""
        if self.tier not in Tier:
            raise ValueError(f"Invalid tier: {self.tier}")
        if not self.formula_id:
            raise ValueError("formula_id is required")
        if not self.formula_version:
            raise ValueError("formula_version is required")
        if not self.data_source:
            raise ValueError("data_source is required")
        if self.confidence < 0 or self.confidence > 100:
            raise ValueError(f"confidence must be 0-100, got {self.confidence}")
        if self.tier == Tier.CONFIRMED_RECOVERED_REVENUE:
            raise ValueError(
                "CONFIRMED_RECOVERED_REVENUE cannot be created by formula functions. "
                "It can only be created by the outcome-recording endpoint."
            )


# ── Formula: Estimated Recoverable Leakage ─────────────────────────────

# Default assumptions for Bengaluru residential real estate
DEFAULT_RECOVERY_PROBABILITY = Decimal("0.15")  # 15% of leaked leads recoverable
DEFAULT_CONTRIBUTION_MARGIN = Decimal("0.03")    # 3% brokerage / margin on deal value

def estimated_recoverable_leakage_v1(
    budget_inr: Decimal,
    confidence: float,
    data_source: str,
    recovery_probability: Decimal = DEFAULT_RECOVERY_PROBABILITY,
    contribution_margin: Decimal = DEFAULT_CONTRIBUTION_MARGIN,
) -> FinancialResult:
    """Estimate the financial impact of a leaked lead.

    Formula: budget × recovery_probability × contribution_margin

    This produces an ESTIMATED_FINANCIAL_IMPACT tier result.
    The assumptions (recovery_probability, contribution_margin) are
    explicitly stored and visible in the API/UI.
    """
    amount = budget_inr * recovery_probability * contribution_margin

    result = FinancialResult(
        amount_inr=amount.quantize(Decimal("0.01")),
        tier=Tier.ESTIMATED_FINANCIAL_IMPACT,
        confidence=confidence,
        formula_id="estimated_recoverable_leakage",
        formula_version="1.0",
        assumptions={
            "recovery_probability": float(recovery_probability),
            "contribution_margin": float(contribution_margin),
            "lead_budget_inr": float(budget_inr),
            "formula": "budget × recovery_probability × contribution_margin",
        },
        data_source=data_source,
    )
    result.validate()
    return result


# ── Formula: Canonical Per-Lead Exposure (Phase 7/8) ─────────────────────

def lead_exposure_v2(
    deal_value_inr: Decimal,
    commission_rate: Decimal | None,
    confidence: float,
    data_source: str,
    default_margin: Decimal = DEFAULT_CONTRIBUTION_MARGIN,
) -> FinancialResult:
    """CANONICAL revenue exposure of one leaking lead (per-lead, per-detector row).

    Formula: effective_commission = deal_value × commission_rate
             (commission_rate from source data when present, else the
              documented default margin)
             exposure = effective_commission

    This is the commission revenue the business fails to collect if the lead is
    lost. It is IDENTICAL for every leakage event of the same lead — exposure
    to the same deal is never additive across detectors. Aggregations MUST
    deduplicate per lead (see core/financial_aggregates.py); summing raw rows
    across categories would double-count the same deal.
    """
    rate = commission_rate if commission_rate is not None else default_margin
    amount = deal_value_inr * rate

    result = FinancialResult(
        amount_inr=amount.quantize(Decimal("0.01")),
        tier=Tier.ESTIMATED_FINANCIAL_IMPACT,
        confidence=confidence,
        formula_id="lead_exposure_v2",
        formula_version="2.0",
        assumptions={
            "deal_value_inr": float(deal_value_inr),
            "commission_rate": float(rate),
            "commission_rate_source": "source_data" if commission_rate is not None else "documented_default",
            "exposure_scope": "per_lead_canonical",
            "formula": "exposure = deal_value × effective_commission_rate",
            "dedup_note": (
                "Exposure is per lead; aggregate revenue_at_risk takes the MAX "
                "per lead across detectors — never the sum of raw rows."
            ),
        },
        data_source=data_source,
    )
    result.validate()
    return result


def recoverable_opportunity_v1(
    exposure_inr: Decimal,
    recovery_probability: float,
    confidence: float,
    data_source: str,
    probability_source: str = "documented_default",
    sample_size: int = 0,
) -> FinancialResult:
    """Recoverable Revenue Opportunity for one lead.

    Formula: recoverable = exposure × recovery_probability

    recovery_probability comes from the org's own recovery-outcome history when
    the sample is sufficient, otherwise from the documented default. The
    probability SOURCE is stored in assumptions — a default is never presented
    as empirical.
    """
    amount = exposure_inr * Decimal(str(recovery_probability))

    result = FinancialResult(
        amount_inr=amount.quantize(Decimal("0.01")),
        tier=Tier.ESTIMATED_FINANCIAL_IMPACT,
        confidence=confidence,
        formula_id="recoverable_opportunity_v1",
        formula_version="1.0",
        assumptions={
            "exposure_inr": float(exposure_inr),
            "recovery_probability": float(recovery_probability),
            "recovery_probability_source": probability_source,
            "recovery_rate_sample_size": sample_size,
            "formula": "recoverable = exposure × recovery_probability",
            "dedup_note": (
                "One recoverable value per lead (max across its leakage events); "
                "never summed across detectors."
            ),
        },
        data_source=data_source,
    )
    result.validate()
    return result


# ── Formula: Response Delay Financial Impact ────────────────────────────

def response_delay_impact_v1(
    baseline_conversion_rate: float,
    bucket_conversion_rate: float,
    average_deal_value_inr: Decimal,
    lead_count: int,
    confidence: float,
    data_source: str,
    bucket_label: str,
) -> FinancialResult:
    """Estimate revenue impact from response delays.

    Formula: (baseline_conversion - bucket_conversion) × avg_deal_value × lead_count

    This produces an ESTIMATED_FINANCIAL_IMPACT tier result.
    """
    conversion_gap = Decimal(str(max(baseline_conversion_rate - bucket_conversion_rate, 0)))
    amount = conversion_gap * average_deal_value_inr * Decimal(str(lead_count))

    result = FinancialResult(
        amount_inr=amount.quantize(Decimal("0.01")),
        tier=Tier.ESTIMATED_FINANCIAL_IMPACT,
        confidence=confidence,
        formula_id="response_delay_impact",
        formula_version="1.0",
        assumptions={
            "baseline_conversion_rate": baseline_conversion_rate,
            "bucket_conversion_rate": bucket_conversion_rate,
            "conversion_gap": float(conversion_gap),
            "average_deal_value_inr": float(average_deal_value_inr),
            "lead_count": lead_count,
            "bucket": bucket_label,
            "formula": "(baseline_conv - bucket_conv) × avg_deal_value × lead_count",
        },
        data_source=data_source,
    )
    result.validate()
    return result


# ── Formula: Lead Recovery Score Financial Weight ───────────────────────

def recovery_score_financial_weight_v1(
    budget_inr: Decimal,
    recovery_score: int,
    confidence: float,
    data_source: str,
) -> FinancialResult:
    """Weight the lead's budget by its recovery score to estimate recoverable amount.

    Formula: budget × (recovery_score / 100) × contribution_margin

    Higher recovery scores indicate more recoverable leads.
    """
    score_factor = Decimal(str(recovery_score)) / Decimal("100")
    amount = budget_inr * score_factor * DEFAULT_CONTRIBUTION_MARGIN

    result = FinancialResult(
        amount_inr=amount.quantize(Decimal("0.01")),
        tier=Tier.ESTIMATED_FINANCIAL_IMPACT,
        confidence=confidence,
        formula_id="recovery_score_financial_weight",
        formula_version="1.0",
        assumptions={
            "recovery_score": recovery_score,
            "score_factor": float(score_factor),
            "contribution_margin": float(DEFAULT_CONTRIBUTION_MARGIN),
            "lead_budget_inr": float(budget_inr),
            "formula": "budget × (recovery_score/100) × contribution_margin",
        },
        data_source=data_source,
    )
    result.validate()
    return result
