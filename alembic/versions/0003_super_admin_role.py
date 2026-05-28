"""add super_admin role value

Revision ID: 0003_super_admin
Revises: 0002_nlp_metadata
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_super_admin"
down_revision = "0002_nlp_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite : colonne role en texte, pas de DDL
        return

    exists = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'roleenum' AND e.enumlabel = 'super_admin'
            """
        )
    ).fetchone()
    if not exists:
        op.execute("ALTER TYPE roleenum ADD VALUE 'super_admin'")


def downgrade() -> None:
    # PostgreSQL ne permet pas de retirer une valeur d'enum facilement
    pass
