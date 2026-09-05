from app.core.rules.lead_leakage import RuleResult
from app.core.rules.lead_recovery_score import calculate_recovery_score

def test_recovery_score_calculation():
    rule_results = [
        RuleResult(rule="dead_but_recently_engaged", points=25, triggered=True, evidence=[{"type": "test", "detail": "test"}]),
        RuleResult(rule="unresolved_questions", points=15, triggered=True, evidence=[]),
        RuleResult(rule="assigned_to_inactive_rep", points=15, triggered=False, evidence=[]),
    ]
    score_result = calculate_recovery_score(rule_results)
    assert score_result.raw_score == 40
    assert score_result.score == round((40 / 105) * 100)
    assert score_result.risk_level == "medium"
    assert len(score_result.contributing_factors) == 2

def test_recovery_score_zero():
    rule_results = [
        RuleResult(rule="no_followup", points=10, triggered=False),
    ]
    score_result = calculate_recovery_score(rule_results)
    assert score_result.score == 0
    assert score_result.risk_level == "low"
