"""add lead lifecycle and detector provenance columns

Non-destructive, additive-only migration:
- leads: lifecycle timestamps, source aggregates, deterministic derived fields,
  data-quality flags.
- leakage_events: detector_id + severity provenance columns.

Every new column is nullable (or carries a server default of nothing), so no
existing row is modified or lost. Safe on SQLite and PostgreSQL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d9f1a2b4e7"
down_revision: Union[str, None] = "9c1f4e7a2b5d"
branch_labels: Union[str, None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("first_contact_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("site_visit_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("negotiation_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("total_touches", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("commission_rate", sa.Numeric(8, 5), nullable=True))
    op.add_column("leads", sa.Column("property_type", sa.String(length=100), nullable=True))
    op.add_column("leads", sa.Column("lost_reason", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("campaign_name", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("response_latency_minutes", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("site_visit_latency_days", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("sales_cycle_days", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("is_dark_lead", sa.Boolean(), nullable=True))
    op.add_column("leads", sa.Column("is_single_touch", sa.Boolean(), nullable=True))
    op.add_column("leads", sa.Column("funnel_max_stage", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("data_quality_flags", sa.JSON(), nullable=True))
    op.add_column("leads", sa.Column("created_at_is_estimated", sa.Boolean(), nullable=True))

    op.add_column("leakage_events", sa.Column("detector_id", sa.String(length=100), nullable=True))
    op.add_column("leakage_events", sa.Column("severity", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("leakage_events", "severity")
    op.drop_column("leakage_events", "detector_id")
    op.drop_column("leads", "created_at_is_estimated")
    op.drop_column("leads", "data_quality_flags")
    op.drop_column("leads", "funnel_max_stage")
    op.drop_column("leads", "is_single_touch")
    op.drop_column("leads", "is_dark_lead")
    op.drop_column("leads", "sales_cycle_days")
    op.drop_column("leads", "site_visit_latency_days")
    op.drop_column("leads", "response_latency_minutes")
    op.drop_column("leads", "campaign_name")
    op.drop_column("leads", "lost_reason")
    op.drop_column("leads", "property_type")
    op.drop_column("leads", "commission_rate")
    op.drop_column("leads", "total_touches")
    op.drop_column("leads", "closed_at")
    op.drop_column("leads", "negotiation_at")
    op.drop_column("leads", "site_visit_at")
    op.drop_column("leads", "first_contact_at")