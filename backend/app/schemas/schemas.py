"""Pydantic schemas for API requests/responses."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Dashboard ───────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    revenue_at_risk: float
    revenue_at_risk_tier: str
    revenue_at_risk_confidence: float
    potentially_recoverable: float
    high_priority_count: int
    confirmed_recovered: float
    confirmed_recovered_tier: str

class LeakageBreakdownItem(BaseModel):
    category: str
    event_count: int
    affected_leads: int
    exposure: float
    additivity_note: str

class HighPriorityIssue(BaseModel):
    id: str
    category: str
    title: str
    status: str
    lead_name: str
    lead_budget: Optional[float] = None
    lead_status: Optional[str] = None
    financial_impact: Optional[float] = None
    confidence: Optional[float] = None
    tier: Optional[str] = None
    created_at: Optional[str] = None

class RecoveryPipeline(BaseModel):
    detected: int
    reviewed: int
    recommended: int
    intervention_started: int
    recovered: int
    is_cumulative: bool
    definition: str

class RecentRecovery(BaseModel):
    id: str
    intervention_id: str
    outcome_type: str
    booking_amount_inr: Optional[float] = None
    confirmed_at: Optional[str] = None


# ── Imports ─────────────────────────────────────────────────────────────

class ImportPreview(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    columns: list[str] = []
    preview_rows: list[dict[str, Any]] = []
    row_count: Optional[int] = None
    created_at: Optional[str] = None

class ColumnMappingItem(BaseModel):
    source_column: str
    target_field: str
    confidence: Optional[float] = None
    suggested_by: Optional[str] = None

class ColumnMappingConfirm(BaseModel):
    mappings: list[ColumnMappingItem]

class ImportStatus(BaseModel):
    id: str
    status: str
    row_count: Optional[int] = None
    error_message: Optional[str] = None


# ── Leads ───────────────────────────────────────────────────────────────

class LeadListItem(BaseModel):
    id: str
    name: str
    phone_normalized: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    source: Optional[str] = None
    project_name: Optional[str] = None
    sales_rep_name: Optional[str] = None
    recovery_score: Optional[int] = None
    risk_level: Optional[str] = None
    created_at: Optional[str] = None

class LeadDetail(BaseModel):
    id: str
    name: str
    phone_normalized: Optional[str] = None
    phone_raw: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    status_raw: Optional[str] = None
    budget: Optional[float] = None
    source: Optional[str] = None
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    sales_rep_name: Optional[str] = None
    sales_rep_id: Optional[str] = None
    recovery_score: int = 0
    risk_level: str = "low"
    contributing_factors: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    leakage_events: list[dict[str, Any]] = []
    created_at: Optional[str] = None
    last_followup_at: Optional[str] = None

class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    page: int
    page_size: int


# ── Leakage ─────────────────────────────────────────────────────────────

class LeakageEventDetail(BaseModel):
    id: str
    category: str
    title: str
    status: str
    tier: str
    lead_name: Optional[str] = None
    lead_id: Optional[str] = None
    evidence: list[dict[str, Any]] = []
    financial: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None

class LeakageListResponse(BaseModel):
    items: list[LeakageEventDetail]
    total: int


# ── Recommendations ────────────────────────────────────────────────────

class RecommendationCreate(BaseModel):
    leakage_event_id: str

class RecommendationResponse(BaseModel):
    id: str
    leakage_event_id: str
    playbook_key: str
    generated_copy: str
    generated_by: str
    lead_name: Optional[str] = None
    category: Optional[str] = None
    created_at: Optional[str] = None


# ── Interventions ──────────────────────────────────────────────────────

class InterventionCreate(BaseModel):
    recommendation_id: str
    assigned_rep_name: Optional[str] = None
    notes: Optional[str] = None

class InterventionUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    assigned_rep_name: Optional[str] = None

class InterventionResponse(BaseModel):
    id: str
    recommendation_id: str
    assigned_rep_name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    lead_name: Optional[str] = None
    category: Optional[str] = None
    playbook_key: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Recovery ───────────────────────────────────────────────────────────

class RecoveryOutcomeCreate(BaseModel):
    intervention_id: str
    outcome_type: str
    booking_amount_inr: Optional[float] = None
    evidence: Optional[dict[str, Any]] = None

class RecoveryOutcomeResponse(BaseModel):
    id: str
    intervention_id: str
    outcome_type: str
    booking_amount_inr: Optional[float] = None
    confirmed_at: Optional[str] = None


# ── Response Leakage ───────────────────────────────────────────────────

class ResponseBucketSchema(BaseModel):
    bucket_key: str
    bucket_label: str
    lead_count: int
    converted_count: int
    conversion_rate: Optional[float] = None
    sample_too_small: bool
    avg_response_minutes: Optional[float] = None

class ResponseLeakageResponse(BaseModel):
    buckets: list[ResponseBucketSchema]
    never_contacted: Optional[ResponseBucketSchema] = None
    total_leads: int
    leads_with_response: int
    baseline_conversion_rate: Optional[float] = None
    correlation_not_causation: bool = True
    disclaimer: str = "Correlation, not causation: response time correlates with conversion but does not prove a causal relationship."
