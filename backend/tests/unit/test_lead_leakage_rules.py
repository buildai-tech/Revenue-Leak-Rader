from datetime import datetime, timedelta
from app.core.rules.lead_leakage import (
    LeadData,
    dead_but_recently_engaged,
    unresolved_questions,
    repeated_re_engagement,
    assigned_to_inactive_rep,
    no_followup_configurable_days,
    high_value_poor_followup,
    evaluate_all_rules,
)

def test_dead_but_recently_engaged():
    now = datetime(2026, 9, 2, 12, 0)
    lead = LeadData(
        lead_id="1",
        name="John Doe",
        status="dead",
        budget=5000000.0,
        sales_rep_name="Priya",
        sales_rep_active=True,
        created_at=now - timedelta(days=60),
        last_followup_at=now - timedelta(days=50),
        events=[
            {"event_type": "inbound_call", "occurred_at": now - timedelta(days=5)}
        ],
    )
    result = dead_but_recently_engaged(lead, now=now)
    assert result.triggered is True
    assert result.points == 25
    assert len(result.evidence) >= 2

def test_assigned_to_inactive_rep():
    lead = LeadData(
        lead_id="2",
        name="Jane Smith",
        status="new",
        budget=4000000.0,
        sales_rep_name="Deepak",
        sales_rep_active=False,
        created_at=datetime.utcnow(),
        last_followup_at=None,
    )
    result = assigned_to_inactive_rep(lead)
    assert result.triggered is True
    assert result.points == 15

def test_high_value_poor_followup():
    now = datetime(2026, 9, 2, 12, 0)
    lead = LeadData(
        lead_id="3",
        name="Rich Client",
        status="interested",
        budget=10000000.0,
        sales_rep_name="Priya",
        sales_rep_active=True,
        created_at=now - timedelta(days=30),
        last_followup_at=now - timedelta(days=25),
        events=[
            {"event_type": "outbound_call", "occurred_at": now - timedelta(days=25)}
        ],
    )
    result = high_value_poor_followup(lead)
    assert result.triggered is True
    assert result.points == 20
