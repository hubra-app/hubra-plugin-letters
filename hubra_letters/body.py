"""Reading request bodies and writing replies."""

from __future__ import annotations

from datetime import date

from flask import request
from sqlalchemy import select

from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.member import Member
from hubra.core.permissions import member_has_permission


class Invalid(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _text(data, key: str, limit: int, required: bool = False) -> str | None:
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise Invalid(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise Invalid(f"{key} must be text")
    value = value.strip()
    if len(value) > limit:
        raise Invalid(f"{key} is longer than {limit} characters")
    return value


def _int(data, key: str, low: int, high: int, default=None) -> int | None:
    value = data.get(key, default)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise Invalid(f"{key} must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise Invalid(f"{key} must be a whole number") from None
    if not low <= number <= high:
        raise Invalid(f"{key} must be between {low} and {high}")
    return number


def _date(data, key: str, required: bool = False) -> date | None:
    value = data.get(key)
    if not value:
        if required:
            raise Invalid(f"{key} is required")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise Invalid(f"{key} must be a date (YYYY-MM-DD)") from None


def _bool(data, key: str) -> bool:
    value = data.get(key)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _get(model, row_id: int):
    row = db.session.get(model, row_id)
    if row is None:
        return None, api_error("NOT_FOUND", "not found", 404)
    return row, None


# ── Output ───────────────────────────────────────────────────────────────────


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _num(value) -> float | None:
    return float(value) if value is not None else None


def _names(ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        m.id: m.name
        for m in db.session.scalars(select(Member).where(Member.id.in_(ids)))
    }


def _can(member, key: str) -> bool:
    return bool(member) and member_has_permission(member, key)
