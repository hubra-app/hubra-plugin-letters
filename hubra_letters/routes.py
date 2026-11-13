"""Letters API: /api/v1/app/letters (all of it needs letters.letters.update).

GET    /options                    window, letterhead, groups, whether Pingen is set up
GET    /letters                    newest first
POST   /letters                    {subject, body, audience, groupId?, memberIds?}
GET    /letters/<id>               with its recipients (and who has no address)
PUT    /letters/<id>               same body; only while it is a draft
DELETE /letters/<id>                only drafts; sent and printed letters stay
GET    /letters/<id>/preview.pdf   the letter for one recipient (?member=<id>, else the first)
POST   /letters/<id>/letters.pdf   builds every letter in one PDF, in the background
GET    /letters/<id>/letters.pdf   that PDF, once it is ready (see "pdf" in the letter)
POST   /letters/<id>/printed       records the letters as printed and posted by hand
POST   /letters/<id>/send          has Pingen print and post each letter
POST   /letters/<id>/retry         queues the failed letters again
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import delete, func, select

from hubra.core.auth.helpers import get_current_member
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.group import Group
from hubra.core.permissions import permission_required
from hubra.core.utils import log_audit

from . import render, services
from .body import Invalid, _body, _get, _int, _iso, _names, _text
from .models import LettersItem, LettersLetter

letters_bp = Blueprint("letters_bp", __name__)

LABEL = "Write letters, print them and send them by post"
MAX_PICKED = 2000


@letters_bp.errorhandler(Invalid)
def _invalid(exc: Invalid):
    return api_error("VALIDATION_ERROR", exc.message, 400)


def _counts(ids) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}
    if not ids:
        return out
    rows = db.session.execute(
        select(LettersItem.letter_id, LettersItem.status, func.count())
        .where(LettersItem.letter_id.in_(ids))
        .group_by(LettersItem.letter_id, LettersItem.status)
    )
    for letter_id, status, n in rows:
        out.setdefault(letter_id, {})[status] = n
    return out


def _letter(letter: LettersLetter, counts: dict, names: dict) -> dict:
    return {
        "id": letter.id,
        "subject": letter.subject,
        "body": letter.body,
        "audience": letter.audience,
        "groupId": letter.group_id,
        "memberIds": list(letter.member_ids or []),
        "status": letter.status,
        "sentAt": _iso(letter.sent_at),
        "createdBy": names.get(letter.created_by),
        "createdAt": _iso(letter.created_at),
        "updatedAt": _iso(letter.updated_at),
        "items": counts,
        "pdf": {
            "status": letter.pdf_status,
            "count": letter.pdf_count,
            "error": letter.pdf_error,
            "at": _iso(letter.pdf_at),
        },
    }


def _detail(letter: LettersLetter) -> dict:
    out = _letter(
        letter, _counts([letter.id]).get(letter.id, {}), _names([letter.created_by])
    )
    if letter.status == "draft":
        ok, missing = services.recipients(letter)
        out["recipients"] = [
            {"memberId": r.member_id, "name": r.name, "address": r.lines[1:]}
            for r in ok
        ]
        out["missing"] = [{"memberId": m.id, "name": m.name} for m in missing]
    else:
        items = db.session.scalars(
            select(LettersItem)
            .where(LettersItem.letter_id == letter.id)
            .order_by(LettersItem.name)
        )
        out["sent"] = [
            {
                "id": i.id,
                "memberId": i.member_id,
                "name": i.name,
                "address": i.address.split("\n")[1:],
                "status": i.status,
                "error": i.error,
                "updatedAt": _iso(i.updated_at),
            }
            for i in items
        ]
    return out


def _read(letter: LettersLetter, data: dict) -> None:
    letter.subject = _text(data, "subject", 200, required=True)
    letter.body = _text(data, "body", 20000, required=True)
    audience = data.get("audience") or "no_email"
    if audience not in services.AUDIENCES:
        raise Invalid("audience must be one of " + ", ".join(services.AUDIENCES))
    letter.audience = audience
    letter.group_id = None
    letter.member_ids = None
    if audience == "group":
        group_id = _int(data, "groupId", 1, 2**31 - 1)
        if not group_id or db.session.get(Group, group_id) is None:
            raise Invalid("groupId must be a group")
        letter.group_id = group_id
    elif audience == "picked":
        ids = data.get("memberIds")
        if not isinstance(ids, list) or not ids or len(ids) > MAX_PICKED:
            raise Invalid(f"memberIds must list 1 to {MAX_PICKED} members")
        if not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            raise Invalid("memberIds must be member ids")
        letter.member_ids = sorted(set(ids))
    letter.updated_at = services.now()


def _draft(letter_id: int, lock: bool = False):
    """The letter while it is a draft. *lock* holds its row until the commit,
    so two clicks on "send" can't queue every letter twice."""
    if lock:
        letter = db.session.get(LettersLetter, letter_id, with_for_update=True)
        err = None if letter else api_error("NOT_FOUND", "not found", 404)
    else:
        letter, err = _get(LettersLetter, letter_id)
    if err:
        return None, err
    if letter.status != "draft":
        return None, api_error(
            "LETTER_SENT", "This letter was already printed or sent.", 409
        )
    return letter, None


def _pdf(data: bytes, name: str, inline: bool) -> Response:
    how = "inline" if inline else "attachment"
    return Response(
        data,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'{how}; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@letters_bp.get("/options")
@permission_required("letters", "update", LABEL)
def options():
    groups = db.session.scalars(select(Group).order_by(Group.name))
    return jsonify(
        {
            "window": services.window(),
            "letterhead": services.club(),
            "pingen": services.pingen_config() is not None,
            "groups": [{"id": g.id, "name": g.name} for g in groups],
        }
    )


@letters_bp.get("/letters")
@permission_required("letters", "update", LABEL)
def list_letters():
    rows = list(
        db.session.scalars(select(LettersLetter).order_by(LettersLetter.id.desc()))
    )
    counts = _counts([r.id for r in rows])
    names = _names(r.created_by for r in rows)
    return jsonify([_letter(r, counts.get(r.id, {}), names) for r in rows])


@letters_bp.post("/letters")
@permission_required("letters", "update", LABEL)
def create_letter():
    member = get_current_member()
    letter = LettersLetter(created_by=member.id)
    _read(letter, _body())
    db.session.add(letter)
    db.session.flush()
    log_audit(member.id, "letters.create", "LettersLetter", letter.id, letter.subject)
    db.session.commit()
    return jsonify(_detail(letter)), 201


@letters_bp.get("/letters/<int:letter_id>")
@permission_required("letters", "update", LABEL)
def get_letter(letter_id: int):
    letter, err = _get(LettersLetter, letter_id)
    if err:
        return err
    return jsonify(_detail(letter))


@letters_bp.put("/letters/<int:letter_id>")
@permission_required("letters", "update", LABEL)
def update_letter(letter_id: int):
    member = get_current_member()
    letter, err = _draft(letter_id)
    if err:
        return err
    _read(letter, _body())
    services.drop_pdf(letter)
    log_audit(member.id, "letters.update", "LettersLetter", letter.id, letter.subject)
    db.session.commit()
    return jsonify(_detail(letter))


@letters_bp.delete("/letters/<int:letter_id>")
@permission_required("letters", "update", LABEL)
def delete_letter(letter_id: int):
    member = get_current_member()
    letter, err = _get(LettersLetter, letter_id)
    if err:
        return err
    if letter.status != "draft":
        # Sent and printed letters stay as the record of who got them; their
        # addresses go after keep_addresses_months (services.forget_addresses).
        return api_error(
            "LETTER_KEPT",
            "Only drafts can be deleted; sent and printed letters stay as a record.",
            409,
        )
    log_audit(member.id, "letters.delete", "LettersLetter", letter.id, letter.subject)
    services.drop_pdf(letter)
    # Explicitly: inside a club schema the foreign key's CASCADE doesn't exist.
    db.session.execute(delete(LettersItem).where(LettersItem.letter_id == letter.id))
    db.session.delete(letter)
    db.session.commit()
    return "", 204


@letters_bp.get("/letters/<int:letter_id>/preview.pdf")
@permission_required("letters", "update", LABEL)
def preview(letter_id: int):
    letter, err = _get(LettersLetter, letter_id)
    if err:
        return err
    ok, _missing = services.recipients(letter)
    wanted = request.args.get("member", type=int)
    pick = next((r for r in ok if r.member_id == wanted), None) if wanted else None
    if pick is None:
        pick = (
            ok[0]
            if ok
            else render.Recipient(
                None,
                "Vorname",
                "Nachname",
                ["Vorname Nachname", "Strasse 1", "8000 Ort"],
            )
        )
    return _pdf(
        render.pdf(
            services.letters_html(letter, [pick]), render.fill(letter.subject, pick)
        ),
        f"letter-{letter.id}-preview.pdf",
        True,
    )


@letters_bp.post("/letters/<int:letter_id>/letters.pdf")
@permission_required("letters", "update", LABEL)
def build_all(letter_id: int):
    member = get_current_member()
    letter = db.session.get(LettersLetter, letter_id, with_for_update=True)
    if letter is None:
        return api_error("NOT_FOUND", "not found", 404)
    if letter.pdf_status != "building":
        ok, _missing = services.recipients(letter)
        if not ok:
            return api_error(
                "NO_RECIPIENTS", "No one with a postal address gets this letter.", 409
            )
        services.ask_pdf(letter, member.id)
        log_audit(member.id, "letters.pdf", "LettersLetter", letter.id, letter.subject)
        db.session.commit()
    return jsonify(_detail(letter)), 202


@letters_bp.get("/letters/<int:letter_id>/letters.pdf")
@permission_required("letters", "update", LABEL)
def all_letters(letter_id: int):
    letter, err = _get(LettersLetter, letter_id)
    if err:
        return err
    data = services.read_pdf(letter)
    if data is None:
        return api_error(
            "PDF_NOT_READY", "Build the PDF first; it is not ready yet.", 409
        )
    return _pdf(data, f"letters-{letter.id}.pdf", False)


@letters_bp.post("/letters/<int:letter_id>/printed")
@permission_required("letters", "update", LABEL)
def mark_printed(letter_id: int):
    member = get_current_member()
    letter, err = _draft(letter_id, lock=True)
    if err:
        return err
    ok, _missing = services.recipients(letter)
    if not ok:
        return api_error(
            "NO_RECIPIENTS", "No one with a postal address gets this letter.", 409
        )
    services.queue(letter, ok, "printed")
    log_audit(member.id, "letters.printed", "LettersLetter", letter.id, letter.subject)
    db.session.commit()
    return jsonify(_detail(letter))


@letters_bp.post("/letters/<int:letter_id>/send")
@permission_required("letters", "update", LABEL)
def send(letter_id: int):
    member = get_current_member()
    letter, err = _draft(letter_id, lock=True)
    if err:
        return err
    if services.pingen_config() is None:
        return api_error(
            "PINGEN_NOT_SET_UP",
            "Enter the club's Pingen API client in the Letters settings first.",
            409,
        )
    ok, _missing = services.recipients(letter)
    if not ok:
        return api_error(
            "NO_RECIPIENTS", "No one with a postal address gets this letter.", 409
        )
    services.queue(letter, ok, "queued")
    log_audit(
        member.id,
        "letters.send",
        "LettersLetter",
        letter.id,
        f"{letter.subject} ({len(ok)})",
    )
    db.session.commit()
    return jsonify(_detail(letter))


@letters_bp.post("/letters/<int:letter_id>/retry")
@permission_required("letters", "update", LABEL)
def retry(letter_id: int):
    member = get_current_member()
    letter, err = _get(LettersLetter, letter_id)
    if err:
        return err
    if services.pingen_config() is None:
        return api_error(
            "PINGEN_NOT_SET_UP",
            "Enter the club's Pingen API client in the Letters settings first.",
            409,
        )
    failed = list(
        db.session.scalars(
            select(LettersItem)
            .where(LettersItem.letter_id == letter.id)
            .where(LettersItem.status == "failed")
        )
    )
    for item in failed:
        item.status, item.tries, item.error, item.updated_at = (
            "queued",
            0,
            None,
            services.now(),
        )
    if failed:
        letter.status = "sending"
        log_audit(
            member.id,
            "letters.retry",
            "LettersLetter",
            letter.id,
            f"{letter.subject} ({len(failed)})",
        )
    db.session.commit()
    return jsonify(_detail(letter))
