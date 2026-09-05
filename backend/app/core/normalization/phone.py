"""
Indian phone number normalization.

Rules:
- Strip all whitespace, hyphens, dots, parentheses
- Remove country code +91 or 0091
- Remove leading 0 (landline-style)
- Validate: result must be exactly 10 digits
- Return normalized 10-digit string, or None if invalid
"""
from __future__ import annotations

import re


_NON_DIGIT = re.compile(r"[^\d]")
_COUNTRY_CODE = re.compile(r"^(?:0{0,2}91|\\+91)")


def normalize_phone(raw: str | None) -> str | None:
    """Normalize an Indian phone number to a 10-digit string, or return None."""
    if not raw:
        return None

    # Strip all non-digit characters except leading +
    cleaned = raw.strip()
    # Handle +91 prefix
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("0091"):
        cleaned = cleaned[4:]
    elif cleaned.startswith("91") and len(cleaned.replace(" ", "").replace("-", "")) >= 12:
        cleaned = cleaned[2:]

    # Remove all non-digit characters
    digits = _NON_DIGIT.sub("", cleaned)

    # Remove leading 0 (trunk prefix)
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # Validate: must be exactly 10 digits
    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return None


def normalize_email(raw: str | None) -> str | None:
    """Normalize email to lowercase, stripped."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if "@" in cleaned and "." in cleaned.split("@")[-1]:
        return cleaned
    return None
