from decimal import Decimal
import pytest
from app.core.financial_engine.tiers import Tier, TIER_DISPLAY
from app.core.financial_engine.confidence import calculate_confidence, ConfidenceInputs, calculate_lead_confidence
from app.core.financial_engine.formulas import (
    estimated_recoverable_leakage_v1,
    response_delay_impact_v1,
    recovery_score_financial_weight_v1,
    FinancialResult,
)

def test_confidence_formula():
    inputs = ConfidenceInputs(sample_size=100, fields_present=6, total_fields=6)
    conf = calculate_confidence(inputs)
    assert conf == 100.0

    inputs_half = ConfidenceInputs(sample_size=50, fields_present=3, total_fields=6)
    # (0.5 * 0.7 + 0.5 * 0.3) * 100 = 50.0
    conf_half = calculate_confidence(inputs_half)
    assert conf_half == 50.0

def test_estimated_recoverable_leakage_v1():
    budget = Decimal("5000000.00")  # ₹50L
    res = estimated_recoverable_leakage_v1(
        budget_inr=budget,
        confidence=85.0,
        data_source="CRM Import",
    )
    # 50L * 0.15 * 0.03 = 22,500
    assert res.amount_inr == Decimal("22500.00")
    assert res.tier == Tier.ESTIMATED_FINANCIAL_IMPACT
    assert res.formula_id == "estimated_recoverable_leakage"
    assert res.formula_version == "1.0"
    assert res.confidence == 85.0

def test_financial_result_validation():
    # Missing formula_id
    with pytest.raises(ValueError, match="formula_id is required"):
        FinancialResult(
            amount_inr=Decimal("100"),
            tier=Tier.ESTIMATED_FINANCIAL_IMPACT,
            confidence=50.0,
            formula_id="",
            formula_version="1.0",
            assumptions={},
            data_source="CRM",
        ).validate()
