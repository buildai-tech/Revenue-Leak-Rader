from decimal import Decimal
import pytest
from app.core.financial_engine.tiers import Tier
from app.core.financial_engine.formulas import FinancialResult

def test_confirmed_recovery_rejected_in_formulas():
    """Verify that CONFIRMED_RECOVERED_REVENUE cannot be created via formula functions."""
    result = FinancialResult(
        amount_inr=Decimal("100000.00"),
        tier=Tier.CONFIRMED_RECOVERED_REVENUE,
        confidence=100.0,
        formula_id="fake_formula",
        formula_version="1.0",
        assumptions={},
        data_source="Test",
    )
    with pytest.raises(ValueError, match="CONFIRMED_RECOVERED_REVENUE cannot be created by formula functions"):
        result.validate()
