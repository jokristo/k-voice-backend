"""add super_admin role value (SQLite stores role as text)

Revision ID: 0003_super_admin
Revises: 0002_nlp_metadata
Create Date: 2026-05-22
"""

from alembic import op

revision = "0003_super_admin"
down_revision = "0002_nlp_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite: role column accepts new enum values without DDL change.
    pass


def downgrade() -> None:
    pass
