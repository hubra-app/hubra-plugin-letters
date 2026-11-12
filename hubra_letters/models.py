"""The Letters tables (one copy per club schema)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hubra.core.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LettersLetter(db.Model):
    __tablename__ = "letters_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # no_email, all, group, picked
    audience: Mapped[str] = mapped_column(
        String(10), default="no_email", nullable=False
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL")
    )
    member_ids: Mapped[list | None] = mapped_column(JSON)
    # draft, sending (Pingen at work), sent, printed (PDF marked as posted)
    status: Mapped[str] = mapped_column(String(10), default="draft", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    # The print PDF of every letter, built in the background:
    # building, ready, failed (None: none asked for). The file sits in
    # Hubra's file store (pdf_key) and is deleted after a few days.
    pdf_status: Mapped[str | None] = mapped_column(String(10))
    pdf_key: Mapped[str | None] = mapped_column(String(120))
    pdf_count: Mapped[int | None] = mapped_column(Integer)
    pdf_error: Mapped[str | None] = mapped_column(String(300))
    pdf_by: Mapped[int | None] = mapped_column(Integer)
    pdf_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LettersItem(db.Model):
    """One letter to one member, once it is sent."""

    __tablename__ = "letters_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    letter_id: Mapped[int] = mapped_column(
        ForeignKey("letters_letters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL")
    )
    # The name and address it went to, as they were then.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    # queued, sent (handed to Pingen), failed, printed
    status: Mapped[str] = mapped_column(String(10), default="queued", nullable=False)
    pingen_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(300))
    tries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
