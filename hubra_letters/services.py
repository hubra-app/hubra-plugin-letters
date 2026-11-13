"""Who gets a letter, the club's letterhead, and posting through Pingen."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from hubra.core.extensions import db
from hubra.core.models.group import GroupMembership
from hubra.core.models.member import Member

from . import pingen, render
from .models import LettersItem, LettersLetter

AUDIENCES = ("no_email", "all", "group", "picked")
KEEP_MONTHS = 12
PDF_KEEP_DAYS = 7  # how long a built print PDF (full of addresses) stays
FILE_OWNER = "letters"
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


def _claim(skip: list[int]) -> LettersItem | None:
    """The next queued letter no other run is working on.

    The row stays locked until this run commits, so a second run of the
    job (the last one took longer than a minute) skips it instead of
    posting the same letter twice.
    """
    query = select(LettersItem).where(LettersItem.status == "queued")
    if skip:
        query = query.where(LettersItem.id.notin_(skip))
    return db.session.scalar(
        query.order_by(LettersItem.id).limit(1).with_for_update(skip_locked=True)
    )


def post_queued() -> dict:
    """Hands queued letters to Pingen, a few per run. Called every minute.

    Each letter is committed on its own right after Pingen took it, so a
    crash half way through doesn't leave posted letters queued to go again.
    """
    done = {"sent": 0, "failed": 0}
    cfg = pingen_config()
    head, side = club(), window()
    touched: set[int] = set()
    seen: list[int] = []
    while len(seen) < PER_RUN:
        item = _claim(seen)
        if item is None:
            break
        seen.append(item.id)
        touched.add(item.letter_id)
        letter = db.session.get(LettersLetter, item.letter_id)
        item.tries += 1
        item.updated_at = now()
        if cfg is None or letter is None:
            item.status = "failed"
            item.error = "Pingen is not set up" if cfg is None else "Letter is gone"
            done["failed"] += 1
            db.session.commit()
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
                ),
                render.fill(letter.subject, r),
            )
            item.pingen_id = pingen.send(cfg, pdf, f"letter-{letter.id}-{item.id}.pdf")
            item.status, item.error = "sent", None
            done["sent"] += 1
        except pingen.PingenError as exc:
            item.error = str(exc)[:300]
            if item.tries >= MAX_TRIES:
                item.status = "failed"
                done["failed"] += 1
        db.session.commit()
    for letter_id in touched:
        letter = db.session.get(LettersLetter, letter_id)
        if (
            letter is not None
            and letter.status == "sending"
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


def keep_months() -> int:
    """How long sent letters keep their addresses; 0 keeps them for good."""
    try:
        months = int(config().get("keep_addresses_months", KEEP_MONTHS))
    except (TypeError, ValueError):
        months = KEEP_MONTHS
    return max(months, 0)


def forget_addresses(today: datetime | None = None) -> int:
    """Deletes the postal addresses of letters sent longer ago than the club
    keeps them (data protection: only as long as needed). The name stays, so
    the list of who got a letter is still there. Returns how many."""
    months = keep_months()
    if not months:
        return 0
    before = (today or now()) - timedelta(days=round(months * 30.44))
    old = select(LettersLetter.id).where(
        LettersLetter.sent_at.is_not(None), LettersLetter.sent_at < before
    )
    done = db.session.execute(
        update(LettersItem)
        .where(LettersItem.letter_id.in_(old))
        .where(LettersItem.status != "queued")
        .where(LettersItem.address != "")
        .values(address="", error=None)
        .execution_options(synchronize_session=False)
    )
    return done.rowcount or 0


def purge_orphans() -> int:
    """Clears what a deleted member or letter left behind.

    Club schemas are copies of the public tables without their foreign keys,
    so ON DELETE CASCADE / SET NULL never runs inside a club: a member
    deleted on request would keep their name and address here. Returns how
    many rows were changed.
    """
    members = select(Member.id)
    n = (
        db.session.execute(
            delete(LettersItem)
            .where(LettersItem.letter_id.notin_(select(LettersLetter.id)))
            .execution_options(synchronize_session=False)
        ).rowcount
        or 0
    )
    n += (
        db.session.execute(
            update(LettersItem)
            .where(LettersItem.member_id.is_not(None))
            .where(LettersItem.member_id.notin_(members))
            .values(member_id=None, name="", address="", error=None)
            .execution_options(synchronize_session=False)
        ).rowcount
        or 0
    )
    n += (
        db.session.execute(
            update(LettersLetter)
            .where(LettersLetter.created_by.is_not(None))
            .where(LettersLetter.created_by.notin_(members))
            .values(created_by=None)
            .execution_options(synchronize_session=False)
        ).rowcount
        or 0
    )
    n += (
        db.session.execute(
            update(LettersLetter)
            .where(LettersLetter.pdf_by.is_not(None))
            .where(LettersLetter.pdf_by.notin_(members))
            .values(pdf_by=None)
            .execution_options(synchronize_session=False)
        ).rowcount
        or 0
    )
    return n


# ── The print PDF, built in the background ──────────────────────────────────


def drop_pdf(letter: LettersLetter) -> None:
    """Forget the letter's built PDF (the file goes with the commit)."""
    from hubra.core import files

    if letter.pdf_key:
        try:
            files.remove(letter.pdf_key)
        except files.FileNotFound:
            pass
    letter.pdf_status = letter.pdf_key = letter.pdf_error = None
    letter.pdf_count = letter.pdf_at = None


def ask_pdf(letter: LettersLetter, member_id: int) -> None:
    """Queue the PDF of every letter; the job tells *member_id* when it's ready."""
    drop_pdf(letter)
    letter.pdf_status, letter.pdf_by, letter.pdf_at = "building", member_id, now()
    _queue(letter.id)


def _queue(letter_id: int) -> None:
    """Hands the build to a worker once the request commits (tests replace it)."""
    from hubra.core.tasks.after_commit import delay_after_commit

    from .tasks import build_pdf as task

    delay_after_commit(task, letter_id)


def build_pdf(letter_id: int) -> str:
    """The job: renders every letter into one PDF and stores it."""
    from hubra.core import files

    letter = db.session.get(LettersLetter, letter_id, with_for_update=True)
    if letter is None or letter.pdf_status != "building":
        return "skipped"
    ok, _missing = recipients(letter)
    try:
        if not ok:
            raise ValueError("No one with a postal address gets this letter.")
        data = render.pdf(letters_html(letter, ok), letter.subject)
        stored = files.put(FILE_OWNER, data, "application/pdf")
    except files.FileTooLarge:
        letter.pdf_status = "failed"
        letter.pdf_error = (
            "The PDF is larger than the club may store. Send it in parts"
            " (for example by group) or by post through Pingen."
        )
    except Exception as exc:  # noqa: BLE001 - shown to the board, never raised
        letter.pdf_status = "failed"
        letter.pdf_error = (
            str(exc)[:300]
            if isinstance(exc, ValueError)
            else "The PDF could not be made."
        )
    else:
        letter.pdf_status, letter.pdf_key = "ready", stored.key
        letter.pdf_count, letter.pdf_error = len(ok), None
    letter.pdf_at = now()
    if letter.pdf_by:
        _tell(letter)
    return letter.pdf_status


def read_pdf(letter: LettersLetter) -> bytes | None:
    from hubra.core import files

    if letter.pdf_status != "ready" or not letter.pdf_key:
        return None
    try:
        return files.read(letter.pdf_key)
    except files.FileNotFound:
        return None


def drop_old_pdfs(today: datetime | None = None) -> int:
    """Built PDFs hold every address: they go after PDF_KEEP_DAYS."""
    before = (today or now()) - timedelta(days=PDF_KEEP_DAYS)
    old = list(
        db.session.scalars(
            select(LettersLetter)
            .where(LettersLetter.pdf_status.in_(("ready", "failed")))
            .where(LettersLetter.pdf_at < before)
        )
    )
    for letter in old:
        drop_pdf(letter)
    return len(old)


def _tell(letter: LettersLetter) -> None:
    """A bell notification for whoever asked for the PDF."""
    from hubra.core.notifications.services import notify_member

    who = db.session.get(Member, letter.pdf_by)
    if who is None:
        return
    de = (getattr(who, "language", None) or "de").lower().startswith("de")
    ready = letter.pdf_status == "ready"
    if ready:
        title = "Brief-PDF bereit" if de else "Letters PDF ready"
        msg = (
            f"«{letter.subject}»: {letter.pdf_count} Briefe zum Drucken."
            if de
            else f"“{letter.subject}”: {letter.pdf_count} letters to print."
        )
    else:
        title = "Brief-PDF fehlgeschlagen" if de else "Letters PDF failed"
        msg = (
            f"«{letter.subject}»: Details beim Brief."
            if de
            else f"“{letter.subject}”: details on the letter."
        )
    notify_member(
        who.id,
        "success" if ready else "warning",
        title,
        msg,
        link=f"/app/letters/{letter.id}",
    )
