from datetime import datetime
from app.core.normalization.dates import parse_date, normalize_status

def test_parse_date_formats():
    assert parse_date("2026-09-02") == datetime(2026, 9, 2, 0, 0)
    assert parse_date("02/09/2026") == datetime(2026, 9, 2, 0, 0)
    assert parse_date("02-09-2026") == datetime(2026, 9, 2, 0, 0)
    assert parse_date("02/09/2026 14:30:00") == datetime(2026, 9, 2, 14, 30, 0)
    assert parse_date("invalid") is None
    assert parse_date(None) is None

def test_normalize_status():
    assert normalize_status("Fresh") == "new"
    assert normalize_status("Site Visit Done") == "qualified"
    assert normalize_status("Closed Lost") == "lost"
    assert normalize_status("Dead") == "dead"
    assert normalize_status("Booked") == "converted"
    assert normalize_status(None) is None
