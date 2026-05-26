"""add nlp_metadata to sermon_outputs

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_nlp_metadata"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sermon_outputs", sa.Column("nlp_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sermon_outputs", "nlp_metadata")
