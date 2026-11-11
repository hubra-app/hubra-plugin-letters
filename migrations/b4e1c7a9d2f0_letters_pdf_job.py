"""letters: the print PDF is built in the background

Revision ID: b4e1c7a9d2f0
Revises: 7d2b6e0a1c35
Create Date: 2026-11-11 15:00:00

"""

import sqlalchemy as sa
from alembic import op

from hubra.core.plugins.ops import columns, has_table

revision = "b4e1c7a9d2f0"
down_revision = "7d2b6e0a1c35"
branch_labels = None
depends_on = None

COLUMNS = (
    ("pdf_status", sa.String(10)),
    ("pdf_key", sa.String(120)),
    ("pdf_count", sa.Integer()),
    ("pdf_error", sa.String(300)),
    ("pdf_by", sa.Integer()),
    ("pdf_at", sa.DateTime(timezone=True)),
)


def upgrade():
    if not has_table("letters_letters"):
        return
    have = columns("letters_letters")
    for name, kind in COLUMNS:
        if name not in have:
            op.add_column("letters_letters", sa.Column(name, kind, nullable=True))


def downgrade():
    if not has_table("letters_letters"):
        return
    have = columns("letters_letters")
    for name, _kind in COLUMNS:
        if name in have:
            op.drop_column("letters_letters", name)
