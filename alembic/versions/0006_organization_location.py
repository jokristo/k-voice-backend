"""organization city country dial_code

Revision ID: 0006_organization_location
Revises: 0005_organization_billing
Create Date: 2026-05-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_organization_location"
down_revision = "0005_organization_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("organizations", sa.Column("country", sa.String(length=128), nullable=True))
    op.add_column("organizations", sa.Column("dial_code", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "dial_code")
    op.drop_column("organizations", "country")
    op.drop_column("organizations", "city")
