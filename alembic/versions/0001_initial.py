"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    role_enum = sa.Enum("admin", "editor", "member", name="roleenum")
    status_enum = sa.Enum("pending", "transcribing", "processing", "completed", "failed", name="sermonstatus")

    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("logo", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("avatar", sa.String(), nullable=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False)

    op.create_table(
        "sermons",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("speaker", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("audio_url", sa.String(), nullable=True),
        sa.Column("audio_size", sa.Integer(), nullable=True),
        sa.Column("audio_duration", sa.Integer(), nullable=True),
        sa.Column("audio_format", sa.String(), nullable=True),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("transcribed_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("recorded_by_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sermons_organization_id"), "sermons", ["organization_id"], unique=False)
    op.create_index(op.f("ix_sermons_recorded_by_id"), "sermons", ["recorded_by_id"], unique=False)

    op.create_table(
        "sermon_outputs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("sermon_id", sa.String(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcript_words", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("main_themes", sa.JSON(), nullable=True),
        sa.Column("key_verses", sa.JSON(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("estimated_read_time", sa.Integer(), nullable=True),
        sa.Column("processing_time", sa.Integer(), nullable=True),
        sa.Column("ai_model", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sermon_id"], ["sermons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sermon_id"),
    )
    op.create_index(op.f("ix_sermon_outputs_sermon_id"), "sermon_outputs", ["sermon_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_sermon_outputs_sermon_id"), table_name="sermon_outputs")
    op.drop_table("sermon_outputs")
    op.drop_index(op.f("ix_sermons_recorded_by_id"), table_name="sermons")
    op.drop_index(op.f("ix_sermons_organization_id"), table_name="sermons")
    op.drop_table("sermons")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("DROP TYPE IF EXISTS roleenum")
    op.execute("DROP TYPE IF EXISTS sermonstatus")
