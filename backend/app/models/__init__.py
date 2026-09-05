"""
Models package — import all models so Alembic and SQLAlchemy can discover them.
"""
from app.models.organization import Organization
from app.models.project import Project
from app.models.sales_rep import SalesRep
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.data_import import DataImport
from app.models.column_mapping import ColumnMapping
from app.models.identity_merge_log import IdentityMergeLog
from app.models.leakage_event import LeakageEvent
from app.models.leakage_evidence import LeakageEvidence
from app.models.financial_calculation import FinancialCalculation
from app.models.recommendation import Recommendation
from app.models.intervention import Intervention
from app.models.recovery_outcome import RecoveryOutcome
from app.models.background_job import BackgroundJob
from app.models.audit_log import AuditLog
from app.models.enums import (
    ImportStatus,
    JobStatus,
    InterventionStatus,
    LeakageStatus,
    LeakageTier,
    LeakageCategory,
    OutcomeType,
    IdentityMergeMethod,
)

__all__ = [
    "Organization",
    "Project",
    "SalesRep",
    "Lead",
    "LeadEvent",
    "DataImport",
    "ColumnMapping",
    "IdentityMergeLog",
    "LeakageEvent",
    "LeakageEvidence",
    "FinancialCalculation",
    "Recommendation",
    "Intervention",
    "RecoveryOutcome",
    "BackgroundJob",
    "AuditLog",
    "ImportStatus",
    "JobStatus",
    "InterventionStatus",
    "LeakageStatus",
    "LeakageTier",
    "LeakageCategory",
    "OutcomeType",
    "IdentityMergeMethod",
]
