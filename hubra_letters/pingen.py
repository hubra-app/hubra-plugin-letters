"""A small client for Pingen's API v2 (https://api.pingen.com/documentation).

Three calls per letter: a token (client credentials, cached until it
expires), a signed upload URL for the PDF, and the letter itself with
auto_send, so Pingen prints and posts it once its checks pass.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIMEOUT = 30


class PingenError(Exception):
    """Shown to the board, so it never carries secrets."""


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    organisation: str
    staging: bool = False
    delivery: str = "cheap"
    color: bool = False
    window: str = "right"

    @property
    def identity(self) -> str:
        return (
            "https://identity-staging.pingen.com"
            if self.staging
            else "https://identity.pingen.com"
        )

    @property
    def api(self) -> str:
        return (
            "https://api-staging.pingen.com"
            if self.staging
            else "https://api.pingen.com"
        )


# Access tokens, per worker process and so shared by every club it serves.
# The key holds a hash of the secret too: a club that enters another club's
# client ID with a wrong secret must not get that club's cached token.
_tokens: dict[tuple[str, str, bool], tuple[str, float]] = {}


def _key(cfg: Config) -> tuple[str, str, bool]:
    secret = hashlib.sha256(cfg.client_secret.encode()).hexdigest()
    return (cfg.client_id, secret, cfg.staging)


def _request(
    method: str, url: str, *, data: bytes | None = None, headers: dict | None = None
) -> dict:
    """One HTTP call; tests replace this."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            # A revoked or expired token: ask for a new one next time.
            _tokens.clear()
        detail = ""
        try:
            body = json.loads(exc.read() or b"{}")
            errors = body.get("errors") or []
            if errors:
                detail = str(errors[0].get("detail") or errors[0].get("title") or "")[
                    :200
                ]
            elif body.get("error_description"):
                detail = str(body["error_description"])[:200]
        except (ValueError, AttributeError):
            pass
        raise PingenError(
            f"Pingen answered HTTP {int(exc.code)}" + (f": {detail}" if detail else "")
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PingenError("Pingen can't be reached") from None
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def token(cfg: Config) -> str:
    key = _key(cfg)
    cached = _tokens.get(key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "scope": "letter batch organisation_read",
        }
    ).encode()
    got = _request(
        "POST",
        f"{cfg.identity}/auth/access-tokens",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    value = got.get("access_token")
    if not value:
        raise PingenError("Pingen didn't accept the client ID and secret")
    _tokens[key] = (value, time.time() + float(got.get("expires_in") or 3600))
    return value


def send(cfg: Config, pdf: bytes, filename: str) -> str:
    """Uploads one letter and has Pingen post it. Returns Pingen's letter id."""
    auth = {"Authorization": f"Bearer {token(cfg)}"}
    upload = _request("GET", f"{cfg.api}/file-upload", headers=auth)
    attrs = (upload.get("data") or {}).get("attributes") or {}
    url, signature = attrs.get("url"), attrs.get("url_signature")
    if not url or not signature:
        raise PingenError("Pingen gave no upload address")
    # Only ever upload over HTTPS (urllib would also open file:// and the like).
    if urllib.parse.urlsplit(str(url)).scheme != "https":
        raise PingenError("Pingen gave an upload address that isn't HTTPS")
    _request("PUT", url, data=pdf, headers={"Content-Type": "application/pdf"})
    body = {
        "data": {
            "type": "letters",
            "attributes": {
                "file_original_name": filename,
                "file_url": url,
                "file_url_signature": signature,
                "address_position": cfg.window,
                "auto_send": True,
                "delivery_product": cfg.delivery,
                "print_mode": "simplex",
                "print_spectrum": "color" if cfg.color else "grayscale",
            },
        }
    }
    made = _request(
        "POST",
        f"{cfg.api}/organisations/{urllib.parse.quote(cfg.organisation, safe='')}/letters",
        data=json.dumps(body).encode(),
        headers={
            **auth,
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        },
    )
    letter_id = (made.get("data") or {}).get("id")
    if not letter_id:
        raise PingenError("Pingen didn't create the letter")
    return str(letter_id)
