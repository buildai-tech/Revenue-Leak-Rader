from app.core.normalization.phone import normalize_phone, normalize_email

def test_normalize_phone_standard():
    assert normalize_phone("9876543210") == "9876543210"
    assert normalize_phone("+91 9876543210") == "9876543210"
    assert normalize_phone("+91-9876543210") == "9876543210"
    assert normalize_phone("09876543210") == "9876543210"
    assert normalize_phone("00919876543210") == "9876543210"
    assert normalize_phone("919876543210") == "9876543210"

def test_normalize_phone_invalid():
    assert normalize_phone("12345") is None
    assert normalize_phone("abcdefghij") is None
    assert normalize_phone(None) is None
    assert normalize_phone("1234567890") is None  # Does not start with 6/7/8/9

def test_normalize_email():
    assert normalize_email("Test.User@example.COM ") == "test.user@example.com"
    assert normalize_email("invalid-email") is None
    assert normalize_email(None) is None
