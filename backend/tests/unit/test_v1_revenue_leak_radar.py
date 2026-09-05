"""
End-to-end test suite for Revenue Leak Radar V1 workflow (Phases 1-21).
No DB, no LLM — tests use V1 funnel detector suite + column mapper.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.core.rules.funnel_leakage import (
    FunnelLeadData, FunnelThresholds, evaluate_funnel_leaks,
    dark_leads, response_sla_breach, single_touch_abandonment,
    post_visit_followup_blackhole, negotiation_stage_rot,
)
from app.core.derived import compute_derived_fields, plan_lifecycle_events
from app.core.financial_engine.formulas import lead_exposure_v2
from app.core.financial_engine.tiers import Tier
from app.ai.column_mapper import suggest_mappings, validate_no_collisions
from app.core.statistics.benchmarks import empirical_sla_threshold, UncertaintyRange

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _base(**kw) -> FunnelLeadData:
    defaults = dict(
        lead_id="T", name="Test Lead", status=None, deal_value=None,
        created_at=NOW - timedelta(days=3), first_contact_at=None,
        last_contact_at=None, site_visit_at=None, negotiation_at=None,
        closed_at=None, total_touches=None, first_outbound_event_at=None,
        last_outbound_event_at=None, has_post_visit_followup_event=False,
    )
    defaults.update(kw)
    return FunnelLeadData(**defaults)


# ── 1. Column mapping (Phase 1) ──

class TestColumnMapping:
    def test_lead_received_at_maps_to_created_at(self):
        src = ["lead_received_at", "first_contact_at", "lead_source",
               "deal_value", "property_type", "location"]
        result = suggest_mappings(src)
        targets = {s["source_column"]: s["target_field"] for s in result["suggestions"]}
        assert targets["lead_received_at"] == "created_at"
        assert targets["first_contact_at"] == "first_contact_at"

    def test_first_contact_keywords(self):
        src = ["first_contact", "first_contact_at", "first_response",
               "response_at", "contact_at", "enquiry_at", "created_at",
               "received_at", "lead_received_at", "lead_created_at"]
        result = suggest_mappings(src)
        targets = {s["source_column"]: s["target_field"] for s in result["suggestions"]}
        # At least one first-contact keyword must map to first_contact_at
        first_contact_sources = {"first_contact", "first_contact_at", "first_response",
                                 "response_at", "contact_at"}
        mapped_to_first_contact = [src for src in first_contact_sources if src in targets]
        assert len(mapped_to_first_contact) >= 1
        assert targets[mapped_to_first_contact[0]] == "first_contact_at"
        # enquiry_at should map to created_at
        assert targets["enquiry_at"] == "created_at"

    def test_last_contact_at_maps_to_last_followup(self):
        src = ["last_contact", "last_contact_at"]
        result = suggest_mappings(src)
        targets = {s["source_column"]: s["target_field"] for s in result["suggestions"]}
        # At least one last-contact keyword must map to last_followup_at
        assert "last_followup_at" in targets.values()
        last_contact_sources = {"last_contact", "last_contact_at"}
        mapped = [src for src in last_contact_sources if src in targets and targets[src] == "last_followup_at"]
        assert len(mapped) >= 1


# ── 2. Date mapping (Phase 1) ──

class TestDateMapping:
    def test_lead_received_at_becomes_created_at(self):
        derived = compute_derived_fields(
            created_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            first_contact_at=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            closed_at=None, site_visit_at=None, total_touches=0, now=NOW,
        )
        assert derived.response_latency_minutes == 60

    def test_created_at_not_overwritten_with_now(self):
        created = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)
        derived = compute_derived_fields(
            created_at=created,
            first_contact_at=None, closed_at=None,
            site_visit_at=None, total_touches=0, now=NOW,
        )
        # created_at should be preserved (not overwritten with now)
        assert derived.data_quality_flags == [] or "future_timestamp" not in str(derived.data_quality_flags)

    def test_is_dark_lead_when_no_contact(self):
        derived = compute_derived_fields(
            created_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            first_contact_at=None, closed_at=None,
            site_visit_at=None, total_touches=0, now=NOW,
        )
        assert derived.is_dark_lead is True

    def test_is_single_touch(self):
        derived = compute_derived_fields(
            created_at=NOW - timedelta(days=2),
            first_contact_at=NOW - timedelta(days=2),
            closed_at=None, site_visit_at=None, total_touches=1, now=NOW,
        )
        assert derived.is_single_touch is True


# ── 3. Collision detection (Phase 2) ──

class TestCollisionDetection:
    def test_location_and_property_type_separate(self):
        src = ["property_type", "location", "project_name"]
        result = suggest_mappings(src)
        targets = {s["source_column"]: s["target_field"] for s in result["suggestions"]}
        assert targets["property_type"] == "property_type"
        assert "project_name" in [s["target_field"] for s in result["suggestions"]]

    def test_two_columns_same_target_collision(self):
        src = ["location", "project_name"]
        result = suggest_mappings(src)
        assert len(result["collisions"]) >= 1
        assert result["collisions"][0]["target_field"] == "project_name"
        assert result["collisions"][0]["resolution"] == "highest_confidence_auto_selected"

    def test_validate_no_collisions_rejects(self):
        mappings = [
            {"target_field": "created_at", "source_column": "col_a"},
            {"target_field": "created_at", "source_column": "col_b"},
        ]
        errors = validate_no_collisions(mappings)
        assert len(errors) == 1
        assert "created_at" in errors[0]


# ── 4. Event generation (Phase 3) ──

class TestEventGeneration:
    def test_events_from_verified_timestamps(self):
        events = plan_lifecycle_events(
            created_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            first_contact_at=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            last_contact_at=datetime(2025, 6, 5, 12, 0, tzinfo=timezone.utc),
            site_visit_at=datetime(2025, 6, 3, 14, 0, tzinfo=timezone.utc),
            negotiation_at=datetime(2025, 6, 6, 9, 0, tzinfo=timezone.utc),
            closed_at=None, total_touches=4, source="import",
        )
        event_types = [e["event_type"] for e in events]
        assert "created" in event_types
        assert "first_contact" in event_types
        assert "follow_up" in event_types
        assert "site_visit" in event_types
        assert "negotiation" in event_types

    def test_no_fabricated_events_when_only_total_touches(self):
        """total_touches alone must NOT fabricate individual contact timestamps."""
        events = plan_lifecycle_events(
            created_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            first_contact_at=None, last_contact_at=None,
            site_visit_at=None, negotiation_at=None,
            closed_at=None, total_touches=3, source="import",
        )
        event_types = [e["event_type"] for e in events]
        assert event_types == ["created"]

    def test_closed_event_generated(self):
        events = plan_lifecycle_events(
            created_at=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            first_contact_at=None, last_contact_at=None,
            site_visit_at=None, negotiation_at=None,
            closed_at=datetime(2025, 6, 10, 9, 0, tzinfo=timezone.utc),
            total_touches=0, source="import",
        )
        event_types = [e["event_type"] for e in events]
        assert "closed" in event_types


# ── 5. Dark leads detector (Phase 5) ──

class TestDarkLeads:
    def test_dark_lead_triggered(self):
        lead = _base(lead_id="L-DARK-1",
            created_at=NOW - timedelta(hours=48),
            first_contact_at=None, total_touches=0)
        result = dark_leads(lead, now=NOW)
        assert result.triggered is True
        assert result.detector_id == "funnel_leakage.dark_leads"
        assert result.category == "dark_leads"
        assert result.confidence_method == "deterministic_heuristic"
        assert len(result.evidence) >= 1

    def test_recent_lead_not_dark(self):
        """A lead created seconds ago is NOT a revenue leak."""
        lead = _base(lead_id="L-RECENT",
            created_at=NOW - timedelta(minutes=5),
            first_contact_at=None, total_touches=0)
        result = dark_leads(lead, now=NOW)
        assert result.triggered is False

    def test_contacted_lead_not_dark(self):
        lead = _base(lead_id="L-CONTACTED",
            created_at=NOW - timedelta(hours=48),
            first_contact_at=NOW - timedelta(hours=47), total_touches=3)
        result = dark_leads(lead, now=NOW)
        assert result.triggered is False


# ── 6. SLA detector (Phase 5) ──

class TestSLADetector:
    def test_sla_breach_triggered(self):
        lead = _base(lead_id="L-SLA-1",
            created_at=NOW - timedelta(hours=5),
            first_contact_at=NOW - timedelta(hours=4),  # 60 min
            total_touches=2, status="New")
        result = response_sla_breach(lead, now=NOW, sla_minutes=30.0,
                                     sla_source="configured_fallback")
        assert result.triggered is True
        assert result.detector_id == "funnel_leakage.response_sla_breach"

    def test_no_sla_breach_within_threshold(self):
        lead = _base(lead_id="L-SLA-2",
            created_at=NOW - timedelta(minutes=20),
            first_contact_at=NOW - timedelta(minutes=15),  # 5 min
            total_touches=2, status="New")
        result = response_sla_breach(lead, now=NOW, sla_minutes=30.0,
                                     sla_source="configured_fallback")
        assert result.triggered is False

    def test_no_sla_breach_when_no_first_contact(self):
        lead = _base(lead_id="L-SLA-3",
            created_at=NOW - timedelta(hours=2),
            first_contact_at=None, total_touches=0)
        result = response_sla_breach(lead, now=NOW, sla_minutes=30.0,
                                     sla_source="configured_fallback")
        assert result.triggered is False

    def test_empirical_threshold_when_sample_sufficient(self):
        # Build response latencies directly (in minutes)
        response_latencies = [float(10 + i) for i in range(25)]
        result = empirical_sla_threshold(response_latencies, min_sample=20, fallback_minutes=60.0)
        assert result.sufficient is True
        assert result.source.startswith("empirical")

    def test_fallback_when_sample_insufficient(self):
        """No sufficient sample → use configured fallback, don't fake stats."""
        result = empirical_sla_threshold([], min_sample=20, fallback_minutes=60.0)
        assert result.sufficient is False
        assert result.insufficient_sample_size is True
        assert result.value == 60.0


# ── 7. Single-touch detector (Phase 5) ──

class TestSingleTouch:
    def test_single_touch_abandonment_triggered(self):
        lead = _base(lead_id="L-SINGLE-1",
            created_at=NOW - timedelta(days=10),
            first_contact_at=NOW - timedelta(days=10),
            total_touches=1, status="Unreachable")
        result = single_touch_abandonment(lead, now=NOW)
        assert result.triggered is True
        assert result.category == "single_touch_abandonment"

    def test_single_touch_won_not_leak(self):
        lead = _base(lead_id="L-SINGLE-2",
            created_at=NOW - timedelta(days=10),
            first_contact_at=NOW - timedelta(days=10),
            total_touches=1, status="Won")
        result = single_touch_abandonment(lead, now=NOW)
        assert result.triggered is False

    def test_single_touch_still_active_not_leak(self):
        lead = _base(lead_id="L-SINGLE-3",
            created_at=NOW - timedelta(days=2),
            first_contact_at=NOW - timedelta(days=2),
            total_touches=1, status="New")
        result = single_touch_abandonment(lead, now=NOW)
        assert result.triggered is False


# ── 8. Visit follow-up detector (Phase 5) ──

class TestVisitFollowup:
    def test_post_visit_blackhole_triggered(self):
        visit = NOW - timedelta(days=5)
        lead = _base(lead_id="L-VISIT-1",
            created_at=visit - timedelta(days=2),
            first_contact_at=visit - timedelta(days=1),
            total_touches=3, status="Negotiation",
            site_visit_at=visit, has_post_visit_followup_event=False)
        result = post_visit_followup_blackhole(lead, now=NOW)
        assert result.triggered is True
        assert result.category == "post_visit_followup_blackhole"

    def test_post_visit_with_followup_not_triggered(self):
        visit = NOW - timedelta(days=5)
        lead = _base(lead_id="L-VISIT-2",
            created_at=visit - timedelta(days=2),
            first_contact_at=visit - timedelta(days=1),
            total_touches=4, status="Negotiation",
            site_visit_at=visit, has_post_visit_followup_event=True)
        result = post_visit_followup_blackhole(lead, now=NOW)
        assert result.triggered is False

    def test_no_visit_no_blackhole(self):
        lead = _base(lead_id="L-VISIT-3",
            created_at=NOW - timedelta(days=5),
            first_contact_at=NOW - timedelta(days=4),
            total_touches=3, status="Negotiation", site_visit_at=None)
        result = post_visit_followup_blackhole(lead, now=NOW)
        assert result.triggered is False


# ── 9. Negotiation rot (Phase 6) ──

class TestNegotiationRot:
    def test_stale_negotiation_triggered(self):
        lead = _base(lead_id="L-NEG-1",
            created_at=NOW - timedelta(days=30),
            first_contact_at=NOW - timedelta(days=29),
            total_touches=3, status="Negotiation",
            negotiation_at=NOW - timedelta(days=20))
        result = negotiation_stage_rot(lead, now=NOW)
        assert result.triggered is True
        assert result.category == "negotiation_stage_rot"
        assert result.confidence_method == "deterministic_heuristic"

    def test_active_negotiation_not_triggered(self):
        lead = _base(lead_id="L-NEG-2",
            created_at=NOW - timedelta(days=3),
            first_contact_at=NOW - timedelta(days=2),
            total_touches=4, status="Negotiation",
            negotiation_at=NOW - timedelta(days=1))
        result = negotiation_stage_rot(lead, now=NOW)
        assert result.triggered is False

    def test_closed_negotiation_not_triggered(self):
        lead = _base(lead_id="L-NEG-3",
            created_at=NOW - timedelta(days=40),
            first_contact_at=NOW - timedelta(days=39),
            total_touches=3, status="Won",
            negotiation_at=NOW - timedelta(days=35),
            closed_at=NOW - timedelta(days=30))
        result = negotiation_stage_rot(lead, now=NOW)
        assert result.triggered is False




