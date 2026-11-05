"""Who gets a letter, the club's letterhead, and posting through Pingen."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from hubra.core.extensions import db
from hubra.core.models.group import GroupMembership
from hubra.core.models.member import Member

from . import pingen, render
from .models import LettersItem, LettersLetter

AUDIENCES = ("no_email", "all", "group", "picked")
MAX_TRIES = 3
PER_RUN = 25


def now() -> datetime:
    return datetime.now(timezone.utc)


def _setting(key: str) -> str:
    from hubra.core.services.settings import SettingService

    try:
        return SettingService.get(key, default="") or ""
    except Exception:  # noqa: BLE001 - a missing setting is empty
        return ""


def club() -> dict:
    """The letterhead: the club's name and the address from its bank details."""
    from hubra.core.services.email import club_display_name

    street = " ".join(
        x
        for x in (_setting("Club.Banking.Street"), _setting("Club.Banking.HouseNo"))
        if x
    )
    city = _setting("Club.Banking.City")
    town = " ".join(x for x in (_setting("Club.Banking.PostalCode"), city) if x)
    return {
        "name": club_display_name(),
        "lines": [x for x in (street, town) if x],
        "city": city,
    }


def config() -> dict:
    from hubra.core.modules import get_config

    return get_config("letters")


def window() -> str:
    return "left" if config().get("window") == "left" else "right"


def pingen_config() -> pingen.Config | None:
    cfg = config()
    if not (
        cfg.get("pingen_client_id")
        and cfg.get("pingen_client_secret")
        and cfg.get("pingen_organisation")
    ):
        return None
    return pingen.Config(
        client_id=str(cfg["pingen_client_id"]).strip(),
        client_secret=str(cfg["pingen_client_secret"]).strip(),
        organisation=str(cfg["pingen_organisation"]).strip(),
        staging=bool(cfg.get("pingen_staging")),
        delivery="fast" if cfg.get("pingen_delivery") == "fast" else "cheap",
        color=bool(cfg.get("pingen_color")),
        window=window(),
    )


def address_lines(m: Member) -> list[str] | None:
    """Name and postal address, or None when the address is incomplete."""
    street = " ".join(
        x for x in (m.address_street or "", m.address_house_no or "") if x
    ).strip()
    town = " ".join(
        x for x in (m.address_postal_code or "", m.address_city or "") if x
    ).strip()
    if not (street and m.address_postal_code and m.address_city):
        return None
    lines = [m.name, street, town]
    country = (m.address_country or "CH").upper()
    if country not in ("CH", "SCHWEIZ", "SWITZERLAND"):
        lines.append(country)
    return lines


def reachable_by_mail(m: Member) -> bool:
    """Like invoice reminders: only a confirmed address counts."""
    email = (m.email or "").strip().lower()
    return (
        bool(email)
        and not email.endswith(".invalid")
        and bool(m.private_email_verified)
    )


def members_for(letter: LettersLetter) -> list[Member]:
    query = (
        select(Member)
        .where(Member.status == "active")
        .where(Member.archived_at.is_(None))
    )
    if letter.audience == "group":
        query = query.join(
            GroupMembership, GroupMembership.member_id == Member.id
        ).where(GroupMembership.group_id == (letter.group_id or 0))
    elif letter.audience == "picked":
        query = query.where(Member.id.in_(list(letter.member_ids or []) or [0]))
    rows = list(db.session.scalars(query))
    if letter.audience == "no_email":
        rows = [m for m in rows if not reachable_by_mail(m)]
    rows.sort(key=lambda m: ((m.last_name or "").lower(), (m.first_name or "").lower()))
    return rows


def recipients(letter: LettersLetter) -> tuple[list[render.Recipient], list[Member]]:
    """(those with an address, those without)."""
    ok, missing = [], []
    for m in members_for(letter):
        lines = address_lines(m)
        if lines is None:
            missing.append(m)
        else:
            ok.append(
                render.Recipient(m.id, m.first_name or "", m.last_name or "", lines)
            )
    return ok, missing


def letters_html(
    letter: LettersLetter, people: list[render.Recipient], day: date | None = None
) -> str:
    head, side, day = club(), window(), day or date.today()
    return render.document(
        [
            render.letter_html(letter.subject, letter.body, r, head, side, day)
            for r in people
        ]
    )


def queue(letter: LettersLetter, people: list[render.Recipient], status: str) -> int:
    """Records one item per recipient (queued for Pingen, or printed)."""
    for r in people:
        db.session.add(
            LettersItem(
                letter_id=letter.id,
                member_id=r.member_id,
                name=r.name[:255],
                address="\n".join(r.lines),
                status=status,
                updated_at=now(),
            )
        )
    letter.status = "sending" if status == "queued" else "printed"
    letter.sent_at = now()
    return len(people)


def post_queued() -> dict:
    """Hands queued letters to Pingen, a few per run. Called every minute."""
    done = {"sent": 0, "failed": 0}
    items = list(
        db.session.scalars(
            select(LettersItem)
            .where(LettersItem.status == "queued")
            .order_by(LettersItem.id)
            .limit(PER_RUN)
        )
    )
    if not items:
        return done
    cfg = pingen_config()
    head, side = club(), window()
    letters: dict[int, LettersLetter] = {}
    for item in items:
        letter = letters.setdefault(
            item.letter_id, db.session.get(LettersLetter, item.letter_id)
        )
        item.tries += 1
        item.updated_at = now()
        if cfg is None:
            item.status, item.error = "failed", "Pingen is not set up"
            done["failed"] += 1
            continue
        lines = item.address.split("\n")
        first, _, last = (lines[0] if lines else "").partition(" ")
        r = render.Recipient(item.member_id, first, last, lines)
        try:
            pdf = render.pdf(
                render.document(
                    [
                        render.letter_html(
                            letter.subject, letter.body, r, head, side, date.today()
                        )
                    ]
                )
            )
            item.pingen_id = pingen.send(cfg, pdf, f"letter-{letter.id}-{item.id}.pdf")
            item.status, item.error = "sent", None
            done["sent"] += 1
        except pingen.PingenError as exc:
            item.error = str(exc)[:300]
            if item.tries >= MAX_TRIES:
                item.status = "failed"
                done["failed"] += 1
    for letter in letters.values():
        if (
            letter is not None
            and db.session.scalar(
                select(LettersItem.id)
                .where(LettersItem.letter_id == letter.id)
                .where(LettersItem.status == "queued")
                .limit(1)
            )
            is None
        ):
            letter.status = "sent"
    return done
