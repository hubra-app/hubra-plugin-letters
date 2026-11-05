"""example_notes

Runs in public and in every club's schema, tracked in its own version table
(alembic_version_example). has_table() keeps it safe to run twice.

Revision ID: 0a1b2c3d4e5f
Revises:
Create Date: 2026-11-02 12:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table

revision = "0a1b2c3d4e5f"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if has_table("example_notes"):
        return
    op.create_table(
        "example_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("example_notes")
