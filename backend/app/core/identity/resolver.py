"""
Identity resolution: exact phone → exact email → manual review queue.

No fuzzy matching in V1. Every merge logged with method, confidence, evidence.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.identity_merge_log import IdentityMergeLog
from app.models.enums import IdentityMergeMethod


@dataclass
class MergeDecision:
    """A proposed or executed merge between two leads."""
    primary_lead_id: uuid.UUID
    merged_lead_id: uuid.UUID
    method: str
    confidence: float
    evidence: dict[str, Any]


async def find_duplicates_by_phone(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[MergeDecision]:
    """Find leads with identical normalized phone numbers.

    Returns merge decisions where the oldest lead is the primary.
    """
    # Find phone numbers that appear more than once
    stmt = (
        select(Lead.phone_normalized, func.count(Lead.id))
        .where(
            Lead.organization_id == organization_id,
            Lead.phone_normalized.isnot(None),
            Lead.phone_normalized != "",
            Lead.merged_into_lead_id.is_(None),  # Not already merged
        )
        .group_by(Lead.phone_normalized)
        .having(func.count(Lead.id) > 1)
    )
    result = await db.execute(stmt)
    duplicate_phones = result.all()

    merge_decisions = []

    for phone, count in duplicate_phones:
        # Get all leads with this phone, ordered by created_at (oldest first)
        leads_stmt = (
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.phone_normalized == phone,
                Lead.merged_into_lead_id.is_(None),
            )
            .order_by(Lead.created_at.asc())
        )
        leads_result = await db.execute(leads_stmt)
        leads = list(leads_result.scalars().all())

        if len(leads) < 2:
            continue

        primary = leads[0]
        for duplicate in leads[1:]:
            merge_decisions.append(MergeDecision(
                primary_lead_id=primary.id,
                merged_lead_id=duplicate.id,
                method=IdentityMergeMethod.EXACT_PHONE.value,
                confidence=100.0,
                evidence={
                    "match_field": "phone_normalized",
                    "match_value": phone,
                    "primary_name": primary.name,
                    "merged_name": duplicate.name,
                },
            ))

    return merge_decisions


async def find_duplicates_by_email(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[MergeDecision]:
    """Find leads with identical email addresses (not already merged by phone).

    Returns merge decisions where the oldest lead is the primary.
    """
    stmt = (
        select(Lead.email, func.count(Lead.id))
        .where(
            Lead.organization_id == organization_id,
            Lead.email.isnot(None),
            Lead.email != "",
            Lead.merged_into_lead_id.is_(None),
        )
        .group_by(Lead.email)
        .having(func.count(Lead.id) > 1)
    )
    result = await db.execute(stmt)
    duplicate_emails = result.all()

    merge_decisions = []

    for email, count in duplicate_emails:
        leads_stmt = (
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.email == email,
                Lead.merged_into_lead_id.is_(None),
            )
            .order_by(Lead.created_at.asc())
        )
        leads_result = await db.execute(leads_stmt)
        leads = list(leads_result.scalars().all())

        if len(leads) < 2:
            continue

        primary = leads[0]
        for duplicate in leads[1:]:
            merge_decisions.append(MergeDecision(
                primary_lead_id=primary.id,
                merged_lead_id=duplicate.id,
                method=IdentityMergeMethod.EXACT_EMAIL.value,
                confidence=95.0,
                evidence={
                    "match_field": "email",
                    "match_value": email,
                    "primary_name": primary.name,
                    "merged_name": duplicate.name,
                },
            ))

    return merge_decisions


async def execute_merges(
    db: AsyncSession,
    organization_id: uuid.UUID,
    decisions: list[MergeDecision],
) -> int:
    """Execute merge decisions: mark duplicates as merged, log each merge."""
    merged_count = 0

    for decision in decisions:
        # Mark the duplicate lead as merged
        merged_lead = await db.get(Lead, decision.merged_lead_id)
        if merged_lead and merged_lead.merged_into_lead_id is None:
            merged_lead.merged_into_lead_id = decision.primary_lead_id

            # Create merge log entry
            log_entry = IdentityMergeLog(
                organization_id=organization_id,
                primary_lead_id=decision.primary_lead_id,
                merged_lead_id=decision.merged_lead_id,
                method=decision.method,
                confidence=decision.confidence,
                evidence=decision.evidence,
            )
            db.add(log_entry)
            merged_count += 1

    if merged_count > 0:
        await db.flush()

    return merged_count


async def resolve_identities(
    db: AsyncSession, organization_id: uuid.UUID
) -> dict[str, int]:
    """Run the full identity resolution cascade.

    Order: exact phone → exact email.
    Each step operates on leads not yet merged by a prior step.
    """
    # Step 1: Exact phone match
    phone_decisions = await find_duplicates_by_phone(db, organization_id)
    phone_merges = await execute_merges(db, organization_id, phone_decisions)

    # Step 2: Exact email match (only on remaining unmerged leads)
    email_decisions = await find_duplicates_by_email(db, organization_id)
    email_merges = await execute_merges(db, organization_id, email_decisions)

    return {
        "phone_merges": phone_merges,
        "email_merges": email_merges,
        "total_merges": phone_merges + email_merges,
    }
