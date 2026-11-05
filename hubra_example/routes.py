"""Example blueprint: /api/v1/app/example.

``permission_required(resource, action, label)`` checks the club role of the
signed-in member; the permission (here ``example.notes.read``) shows up in
Settings › Roles by itself.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from hubra.api.auth.helpers import get_current_member
from hubra.api.permissions import permission_required
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.modules import get_config

from .models import ExampleNote

example_bp = Blueprint("example_bp", __name__)


def _dict(note: ExampleNote) -> dict:
    return {
        "id": note.id,
        "text": note.text,
        "authorId": note.author_id,
        "createdAt": note.created_at.isoformat() if note.created_at else None,
    }


@example_bp.get("/notes")
@permission_required("notes", "read", "View notes")
def list_notes():
    limit = int(get_config("example").get("max_notes") or 50)
    notes = db.session.scalars(
        select(ExampleNote).order_by(ExampleNote.id.desc()).limit(limit)
    ).all()
    return jsonify([_dict(n) for n in notes]), 200


@example_bp.post("/notes")
@permission_required("notes", "write", "Write notes")
def add_note():
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return api_error("VALIDATION_ERROR", "text is required", 400)
    if len(text) > 2000:
        return api_error("VALIDATION_ERROR", "text: at most 2000 characters", 400)
    member = get_current_member()
    note = ExampleNote(text=text, author_id=member.id if member else None)
    db.session.add(note)
    db.session.commit()
    return jsonify(_dict(note)), 201


@example_bp.delete("/notes/<int:note_id>")
@permission_required("notes", "write", "Write notes")
def delete_note(note_id: int):
    note = db.session.get(ExampleNote, note_id)
    if note is None:
        return api_error("NOT_FOUND", "no such note", 404)
    db.session.delete(note)
    db.session.commit()
    return "", 204
