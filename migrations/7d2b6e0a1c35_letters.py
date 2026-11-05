"""letters: letters and the letters sent

Runs in public and in every club's schema, tracked in its own version table
(alembic_version_letters). has_table() keeps it safe to run twice.

Revision ID: 7d2b6e0a1c35
Revises:
Create Date: 2026-11-05 18:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table

revision = "7d2b6e0a1c35"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    if not has_table("letters_letters"):
        op.create_table(
            "letters_letters",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("subject", sa.String(200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("audience", sa.String(10), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=True),
            sa.Column("member_ids", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(10), nullable=False),
            _ts("sent_at"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            _ts("created_at", nullable=False),
            _ts("updated_at", nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["created_by"], ["members.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("letters_items"):
        op.create_table(
            "letters_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("letter_id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("address", sa.Text(), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("pingen_id", sa.String(64), nullable=True),
            sa.Column("error", sa.String(300), nullable=True),
            sa.Column("tries", sa.Integer(), nullable=False),
            _ts("updated_at", nullable=False),
            sa.ForeignKeyConstraint(
                ["letter_id"], ["letters_letters.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_letters_items_letter_id", "letters_items", ["letter_id"])


def downgrade():
    for table in ("letters_items", "letters_letters"):
        if has_table(table):
            op.drop_table(table)
