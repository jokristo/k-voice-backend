"""organization billing fields

Revision ID: 0005_organization_billing
Revises: 0004_audio_uploaded_at
Create Date: 2026-05-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_organization_billing"
down_revision = "0004_audio_uploaded_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("billing_plan", sa.String(length=32), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("subscription_status", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column("organizations", sa.Column("payment_provider", sa.String(length=32), nullable=True))
    op.add_column(
        "organizations", sa.Column("external_subscription_id", sa.String(length=128), nullable=True)
    )
    op.add_column("organizations", sa.Column("paypal_plan_id", sa.String(length=64), nullable=True))
    op.add_column("organizations", sa.Column("subscription_started_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "subscription_started_at")
    op.drop_column("organizations", "paypal_plan_id")
    op.drop_column("organizations", "external_subscription_id")
    op.drop_column("organizations", "payment_provider")
    op.drop_column("organizations", "subscription_status")
    op.drop_column("organizations", "billing_plan")
