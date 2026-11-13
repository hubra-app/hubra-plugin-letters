"""Letters as HTML and PDF, laid out for window envelopes.

Hubra puts them on the club's letterhead (``pdf.render``, docs/contracts.md
"PDFs" in hubra-app/hubra): logo, name and address at the top of every
page, the contact line at the bottom. This module writes the letters: the
sender line and address in the envelope's window, the date, the subject and
the text.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date

MONTHS_DE = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip

# Where the recipient's address sits (mm from the page's top left corner).
# Right: Swiss C5/6 envelopes with the window on the right; left: DIN 5008.
WINDOWS = {"right": (118, 52), "left": (22, 52)}
# The letterhead's page margins (top, left), from Hubra's templates/pdf/
# base.html: the letter is placed inside them, the window stays on the page.
PAGE_TOP, PAGE_LEFT = 34, 15
# Where the text starts, mm from the top of the page (below the window).
TEXT_TOP = 105


@dataclass
class Recipient:
    member_id: int | None
    first_name: str
    last_name: str
    lines: list[str]  # name and address, one per line

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def long_date(day: date) -> str:
    return f"{day.day}. {MONTHS_DE[day.month - 1]} {day.year}"


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def fill(text: str, r: Recipient) -> str:
    """{vorname}, {nachname}, {name} (and English names) for this recipient."""
    values = {
        "vorname": r.first_name,
        "first_name": r.first_name,
        "nachname": r.last_name,
        "last_name": r.last_name,
        "name": r.name,
    }
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1).lower(), m.group(0)), text)


def _paragraphs(text: str) -> str:
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        safe = html.escape(block.strip())
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        out.append("<p>" + safe.replace("\n", "<br>") + "</p>")
    return "\n".join(out)


CSS = f"""
.letter {{ position: relative; padding-top: {TEXT_TOP - PAGE_TOP}mm; padding-left: 7mm;
           padding-right: 7mm; font-size: 10.5pt; line-height: 1.45; color: #111; }}
.letter + .letter {{ page-break-before: always; }}
.window {{ position: absolute; width: 85mm; }}
.sender {{ font-size: 7pt; color: #555; border-bottom: 0.3pt solid #999; padding-bottom: 1mm;
          margin-bottom: 2mm; white-space: nowrap; overflow: hidden; }}
.address {{ font-size: 10.5pt; line-height: 1.35; }}
.date {{ margin-bottom: 8mm; }}
.letter h1 {{ font-size: 11.5pt; margin: 0 0 6mm; }}
.letter p {{ margin: 0 0 3.5mm; }}
/* One file holds every recipient's letter: a page count across all of
   them would read "Seite 7 / 40" to a member. */
.footer .page {{ display: none; }}
"""


def letter_html(
    subject: str, body: str, r: Recipient, club: dict, window: str, day: date
) -> str:
    left, top = WINDOWS.get(window, WINDOWS["right"])
    sender = " · ".join(x for x in [club.get("name"), *club.get("lines", [])] if x)
    place = club.get("city")
    when = f"{place}, {long_date(day)}" if place else long_date(day)
    address = "<br>".join(html.escape(x) for x in r.lines)
    # The window is placed from the page's corner, the letter from the
    # letterhead's margins.
    return f"""
<section class="letter">
  <div class="window" style="left:{left - PAGE_LEFT}mm; top:{top - PAGE_TOP}mm">
    <div class="sender">{html.escape(sender)}</div>
    <div class="address">{address}</div>
  </div>
  <div class="date">{html.escape(when)}</div>
  <h1>{html.escape(fill(subject, r))}</h1>
  {_paragraphs(fill(body, r))}
</section>"""


def document(sections: list[str]) -> str:
    """The body for ``pdf.render``: the letters and their style."""
    return f"<style>{CSS}</style>{''.join(sections)}"


def pdf(body_html: str, title: str) -> bytes:
    """The letters on the club's letterhead, laid out by Hubra."""
    import base64

    from hubra.core.contracts import SYSTEM, call

    # SYSTEM: the route or job already checked who may print the letter.
    out = call(
        "pdf.render", title=title[:200] or "Brief", body_html=body_html, actor=SYSTEM
    )
    return base64.b64decode(out["pdf_base64"])
