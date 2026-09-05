"""
Multi-format date parsing for Indian CRM data.

Handles: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD Mon YYYY, DD-Mon-YY,
         ISO 8601, and various other common formats.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

# Ordered by specificity — most specific formats first
_FORMATS = [
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
]


def parse_date(raw: str | None) -> Optional[datetime]:
    """Try to parse a date string using multiple common formats.

    Returns a datetime object on success, None on failure.
    """
    if not raw:
        return None

    cleaned = str(raw).strip()
    if not cleaned:
        return None

    for fmt in _FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    return None


def normalize_status(raw: str | None) -> str | None:
    """Normalize CRM lead status to a canonical value."""
    if not raw:
        return None

    status = str(raw).strip().lower()

    # Map common CRM status strings to canonical values
    _STATUS_MAP = {
        # Active/New
        "new": "new",
        "fresh": "new",
        "new lead": "new",
        "uncontacted": "new",
        # Contacted
        "contacted": "contacted",
        "called": "contacted",
        "phone contacted": "contacted",
        "email sent": "contacted",
        # Interested / Qualified
        "interested": "interested",
        "hot": "interested",
        "warm": "interested",
        "qualified": "qualified",
        "site visit scheduled": "qualified",
        "site visit done": "qualified",
        "sv done": "qualified",
        "sv scheduled": "qualified",
        # Negotiation
        "negotiation": "negotiation",
        "follow up": "followup",
        "followup": "followup",
        "follow-up": "followup",
        "in progress": "in_progress",
        # Converted / Won
        "converted": "converted",
        "booked": "converted",
        "booking done": "converted",
        "won": "converted",
        "closed won": "converted",
        # Lost / Dead
        "lost": "lost",
        "dead": "dead",
        "closed": "closed",
        "closed lost": "lost",
        "not interested": "not_interested",
        "junk": "junk",
        "duplicate": "duplicate",
        "invalid": "invalid",
    }

    return _STATUS_MAP.get(status, status)
