"""
Recommendation writer — deterministic playbook selection + optional LLM personalization.

Playbook selection is deterministic (category → playbook_key lookup).
LLM only personalizes the copy — never selects the playbook.
"""
from __future__ import annotations

from typing import Any


# ── Playbook Templates ──────────────────────────────────────────────────
# Each leakage category maps to exactly one playbook.
# The template uses {variable} substitution.

PLAYBOOKS: dict[str, dict[str, str]] = {
    "dead_but_recently_engaged": {
        "playbook_key": "reactivation_outreach",
        "title": "Re-engagement Outreach",
        "template": (
            "This lead ({lead_name}) was marked as {status} but has shown recent engagement activity. "
            "Recommended action: Reach out within 24 hours with a personalized message acknowledging "
            "their renewed interest. Reference their previous interactions and offer an updated "
            "consultation or site visit for {project_name}."
        ),
    },
    "unresolved_questions": {
        "playbook_key": "response_recovery",
        "title": "Unanswered Query Follow-up",
        "template": (
            "Lead {lead_name} sent messages that remain unanswered. This represents a direct "
            "service failure. Recommended action: Respond immediately, apologize for the delay, "
            "and address their specific questions. Offer a direct line for future queries."
        ),
    },
    "repeated_re_engagement": {
        "playbook_key": "persistent_interest_capture",
        "title": "Persistent Interest Capture",
        "template": (
            "Lead {lead_name} has made multiple attempts to re-engage after being marked {status}. "
            "This indicates strong, persistent interest. Recommended action: Assign a senior rep "
            "for a personal consultation. Consider offering an exclusive viewing or incentive."
        ),
    },
    "assigned_to_inactive_rep": {
        "playbook_key": "reassignment",
        "title": "Lead Reassignment",
        "template": (
            "Lead {lead_name} is assigned to {sales_rep_name} who is currently inactive. "
            "Recommended action: Immediately reassign to an active team member. Contact the lead "
            "to introduce their new point of contact and ensure continuity."
        ),
    },
    "no_followup": {
        "playbook_key": "followup_activation",
        "title": "Follow-up Activation",
        "template": (
            "Lead {lead_name} has not received any follow-up contact. "
            "Recommended action: Initiate contact within 4 hours. Reference their original inquiry "
            "source and offer to answer any initial questions about {project_name}."
        ),
    },
    "high_value_poor_followup": {
        "playbook_key": "high_value_recovery",
        "title": "High-Value Lead Recovery",
        "template": (
            "Lead {lead_name} has a budget of ₹{budget} but has received insufficient follow-up. "
            "This is a high-priority recovery opportunity. Recommended action: Assign to a senior "
            "consultant, schedule a personalized site visit, and provide a detailed proposal "
            "for {project_name}."
        ),
    },
    "response_delay": {
        "playbook_key": "speed_to_lead",
        "title": "Speed-to-Lead Improvement",
        "template": (
            "Response time analysis shows delayed initial contact. "
            "Recommended action: Implement automated acknowledgment within 2 minutes, "
            "followed by personal outreach within 15 minutes during business hours."
        ),
    },
    "never_contacted": {
        "playbook_key": "immediate_outreach",
        "title": "Immediate First Contact",
        "template": (
            "Lead {lead_name} has never been contacted despite registering interest. "
            "Recommended action: Make immediate contact via phone, followed by a welcome email "
            "with relevant project information for {project_name}."
        ),
    },
}


def select_playbook(category: str) -> dict[str, str]:
    """Deterministic playbook selection — category → playbook.

    This is NOT an LLM decision. The mapping is a fixed lookup.
    """
    return PLAYBOOKS.get(category, {
        "playbook_key": "generic_followup",
        "title": "General Follow-up",
        "template": "Review this lead and determine the appropriate next action based on their engagement history.",
    })


def generate_recommendation_copy(
    category: str,
    lead_context: dict[str, Any],
) -> tuple[str, str, str]:
    """Generate recommendation copy using the playbook template.

    Returns (playbook_key, title, generated_copy).
    """
    playbook = select_playbook(category)
    copy = playbook["template"]

    # Simple variable substitution
    for key, value in lead_context.items():
        copy = copy.replace(f"{{{key}}}", str(value))

    return playbook["playbook_key"], playbook["title"], copy
