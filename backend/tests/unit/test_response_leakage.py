from datetime import datetime, timedelta
from app.core.rules.response_leakage import (
    bucket_leads,
    LeadResponseData,
    calculate_response_delay_minutes,
    MINIMUM_SAMPLE_SIZE,
)

def test_response_delay_calculation():
    now = datetime(2026, 9, 2, 12, 0)
    delay = calculate_response_delay_minutes(now, now + timedelta(minutes=15))
    assert delay == 15.0

    assert calculate_response_delay_minutes(now, None) is None

def test_response_leakage_disclaimer_always_present():
    now = datetime(2026, 9, 2, 12, 0)
    leads = [
        LeadResponseData(
            lead_id=str(i),
            created_at=now - timedelta(days=5),
            status="converted" if i % 4 == 0 else "new",
            first_outbound_at=now - timedelta(days=5) + timedelta(minutes=random_delay(i)),
        )
        for i in range(30)
    ]
    result = bucket_leads(leads)
    assert result.correlation_not_causation is True
    assert "Correlation, not causation" in result.disclaimer
    assert len(result.buckets) == 4

def random_delay(i: int) -> int:
    delays = [2, 15, 45, 90]
    return delays[i % 4]
