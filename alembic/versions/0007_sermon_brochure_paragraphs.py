"""Add brochure_paragraphs to sermon_outputs

Revision ID: 0007_sermon_brochure
Revises: 0006_organization_location
Create Date: 2026-06-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_sermon_brochure"
down_revision: Union[str, None] = "0006_organization_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sermon_outputs", sa.Column("brochure_paragraphs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sermon_outputs", "brochure_paragraphs")
