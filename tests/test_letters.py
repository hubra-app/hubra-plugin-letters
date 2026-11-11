"""The Letters plugin: who gets a letter, the PDF, and posting through Pingen.

Runs with Hubra's fixtures once the plugin is in plugins/letters of a Hubra
checkout (see README.md).
"""

from __future__ import annotations

import pytest

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/letters"


@pytest.fixture
def club(client, app, db, seeded_db):
    """Bea writes letters. Max and Lea get mail only on paper (Lea has no
    address); Ola reads her e-mail."""
    from hubra.core.models.member import Member

    set_modules(True, "letters")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    bea = _make_role_and_member(
        db, tier, name="Bea", permission_keys=["letters.letters.update"]
    )
    ids = {"bea": bea.id}
    for name in ("Max", "Lea", "Ola"):
        ids[name.lower()] = _make_role_and_member(db, tier, name=name).id
    for m in db.session.query(Member).all():
        m.private_email_verified = True
    max_ = db.session.get(Member, ids["max"])
    max_.private_email_verified = False
    max_.address_street, max_.address_house_no = "Bahnhofstrasse", "12"
    max_.address_postal_code, max_.address_city = "8001", "Zürich"
    db.session.get(Member, ids["lea"]).private_email_verified = False
    db.session.commit()
    return ids


def _pingen(app, monkeypatch, fail=0):
    """Pingen set up, its HTTP calls answered here."""
    from hubra_letters import pingen, services

    # Module settings live per club; the test install has none, so the
    # settings are handed in directly.
    cfg = {
        "pingen_client_id": "id",
        "pingen_client_secret": "secret",
        "pingen_organisation": "org-1",
        "pingen_staging": True,
    }
    monkeypatch.setattr(services, "config", lambda: cfg)
    calls = []
    left = {"fail": fail}

    def fake(method, url, *, data=None, headers=None):
        calls.append((method, url))
        if url.endswith("/auth/access-tokens"):
            return {"access_token": "tok", "expires_in": 3600}
        if url.endswith("/file-upload"):
            return {
                "data": {
                    "attributes": {
                        "url": "https://upload.test/x",
                        "url_signature": "sig",
                    }
                }
            }
        if method == "PUT":
            assert data.startswith(b"%PDF")
            return {}
        if left["fail"]:
            left["fail"] -= 1
            raise pingen.PingenError("Pingen answered HTTP 422: bad address")
        return {"data": {"id": f"pg-{len(calls)}"}}

    pingen._tokens.clear()
    monkeypatch.setattr(pingen, "_request", fake)
    return calls


def test_write_preview_and_print(client, club):
    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/letters").status_code == 403

    _login(client, "bea@test.ch")
    assert (
        client.post(
            f"{BASE}/letters", json={"subject": "x", "body": "y", "audience": "car"}
        ).status_code
        == 400
    )
    letter = client.post(
        f"{BASE}/letters",
        json={
            "subject": "Einladung GV",
            "body": "Liebe/r {vorname}\n\nWir laden dich ein.",
        },
    )
    assert letter.status_code == 201
    letter = letter.get_json()
    assert [r["name"] for r in letter["recipients"]] == ["Test Max"]
    assert letter["recipients"][0]["address"] == ["Bahnhofstrasse 12", "8001 Zürich"]
    assert [m["name"] for m in letter["missing"]] == ["Test Lea"]

    one = client.get(f"{BASE}/letters/{letter['id']}/preview.pdf")
    assert (
        one.status_code == 200
        and one.mimetype == "application/pdf"
        and one.data.startswith(b"%PDF")
    )
    assert client.get(f"{BASE}/letters/{letter['id']}/letters.pdf").data.startswith(
        b"%PDF"
    )

    picked = client.put(
        f"{BASE}/letters/{letter['id']}",
        json={
            "subject": "Einladung GV",
            "body": "Hallo",
            "audience": "picked",
            "memberIds": [club["ola"]],
        },
    ).get_json()
    assert picked["recipients"] == [] and [m["name"] for m in picked["missing"]] == [
        "Test Ola"
    ]
    assert client.post(f"{BASE}/letters/{letter['id']}/printed").status_code == 409

    client.put(
        f"{BASE}/letters/{letter['id']}",
        json={
            "subject": "Einladung GV",
            "body": "Hallo {name}",
            "audience": "picked",
            "memberIds": [club["max"]],
        },
    )
    done = client.post(f"{BASE}/letters/{letter['id']}/printed").get_json()
    assert done["status"] == "printed" and [i["status"] for i in done["sent"]] == [
        "printed"
    ]
    assert (
        client.put(
            f"{BASE}/letters/{letter['id']}", json={"subject": "a", "body": "b"}
        ).status_code
        == 409
    )


def test_fill_placeholders():
    from hubra_letters.render import Recipient, fill

    r = Recipient(1, "Max", "Muster", ["Max Muster"])
    assert (
        fill("Hallo {Vorname} {nachname}, {unknown}", r)
        == "Hallo Max Muster, {unknown}"
    )


def test_send_by_post_through_pingen(app, client, db, club, monkeypatch):
    from hubra_letters import services
    from hubra_letters.models import LettersItem

    _login(client, "bea@test.ch")
    letter = client.post(
        f"{BASE}/letters", json={"subject": "Beitrag", "body": "Hallo {vorname}"}
    ).get_json()
    refused = client.post(f"{BASE}/letters/{letter['id']}/send")
    assert (
        refused.status_code == 409
        and refused.get_json()["error"] == "PINGEN_NOT_SET_UP"
    )

    calls = _pingen(app, monkeypatch, fail=services.MAX_TRIES)
    assert client.get(f"{BASE}/options").get_json()["pingen"] is True
    sent = client.post(f"{BASE}/letters/{letter['id']}/send").get_json()
    assert sent["status"] == "sending" and [i["status"] for i in sent["sent"]] == [
        "queued"
    ]

    # Pingen refuses it three times: the letter is marked failed.
    with app.test_request_context():
        for _ in range(services.MAX_TRIES):
            services.post_queued()
            db.session.commit()
    item = db.session.query(LettersItem).one()
    assert (
        item.status == "failed" and "422" in item.error and "secret" not in item.error
    )
    assert any(
        "api-staging.pingen.com/organisations/org-1/letters" in u for _, u in calls
    )

    # Tried again, it goes through.
    assert (
        client.post(f"{BASE}/letters/{letter['id']}/retry").get_json()["status"]
        == "sending"
    )
    with app.test_request_context():
        assert services.post_queued() == {"sent": 1, "failed": 0}
        db.session.commit()
    after = client.get(f"{BASE}/letters/{letter['id']}").get_json()
    assert after["status"] == "sent" and after["sent"][0]["status"] == "sent"
    assert after["items"] == {"sent": 1}
    assert client.delete(f"{BASE}/letters/{letter['id']}").status_code == 204


def test_pingen_token_cache_is_per_secret(monkeypatch):
    """Another club's client ID with a wrong secret doesn't get its token."""
    from hubra_letters import pingen

    asked = []

    def fake(method, url, *, data=None, headers=None):
        asked.append(data)
        if b"client_secret=right" in data:
            return {"access_token": "tok-right", "expires_in": 3600}
        raise pingen.PingenError("Pingen answered HTTP 401")

    pingen._tokens.clear()
    monkeypatch.setattr(pingen, "_request", fake)
    right = pingen.Config("shared-id", "right", "org-a")
    wrong = pingen.Config("shared-id", "guess", "org-b")
    assert pingen.token(right) == "tok-right"
    with pytest.raises(pingen.PingenError):
        pingen.token(wrong)
    assert len(asked) == 2


def test_pingen_upload_only_over_https(monkeypatch):
    from hubra_letters import pingen

    def fake(method, url, *, data=None, headers=None):
        if url.endswith("/auth/access-tokens"):
            return {"access_token": "tok", "expires_in": 3600}
        if url.endswith("/file-upload"):
            return {
                "data": {
                    "attributes": {"url": "file:///etc/passwd", "url_signature": "s"}
                }
            }
        raise AssertionError(f"unexpected call {method} {url}")

    pingen._tokens.clear()
    monkeypatch.setattr(pingen, "_request", fake)
    with pytest.raises(pingen.PingenError, match="HTTPS"):
        pingen.send(pingen.Config("id", "secret", "org"), b"%PDF", "x.pdf")


def test_send_twice_queues_once(app, client, db, club, monkeypatch):
    from hubra_letters.models import LettersItem

    _pingen(app, monkeypatch)
    _login(client, "bea@test.ch")
    letter = client.post(
        f"{BASE}/letters", json={"subject": "Beitrag", "body": "Hallo"}
    ).get_json()
    assert client.post(f"{BASE}/letters/{letter['id']}/send").status_code == 200
    again = client.post(f"{BASE}/letters/{letter['id']}/send")
    assert again.status_code == 409 and again.get_json()["error"] == "LETTER_SENT"
    assert db.session.query(LettersItem).count() == 1


def test_old_addresses_are_forgotten(app, client, db, club, monkeypatch):
    from datetime import timedelta

    from hubra_letters import services
    from hubra_letters.models import LettersItem, LettersLetter

    _login(client, "bea@test.ch")
    letter = client.post(
        f"{BASE}/letters", json={"subject": "GV", "body": "Hallo"}
    ).get_json()
    client.post(f"{BASE}/letters/{letter['id']}/printed")
    row = db.session.get(LettersLetter, letter["id"])

    cfg = {"keep_addresses_months": 12}
    monkeypatch.setattr(services, "config", lambda: cfg)
    with app.test_request_context():
        assert services.forget_addresses() == 0  # just sent
        row.sent_at = services.now() - timedelta(days=400)
        db.session.commit()
        cfg["keep_addresses_months"] = 0
        assert services.forget_addresses() == 0  # 0 keeps them
        cfg["keep_addresses_months"] = 12
        assert services.forget_addresses() == 1
        db.session.commit()
    item = db.session.query(LettersItem).one()
    assert item.address == "" and item.name == "Test Max"
    sent = client.get(f"{BASE}/letters/{letter['id']}").get_json()["sent"]
    assert sent[0]["address"] == [] and sent[0]["name"] == "Test Max"
