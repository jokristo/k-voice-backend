"""add audio_uploaded_at for retention policy

Revision ID: 0004_audio_uploaded_at
Revises: 0003_super_admin
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_audio_uploaded_at"
down_revision = "0003_super_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sermons", sa.Column("audio_uploaded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("sermons", "audio_uploaded_at")
