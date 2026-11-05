"""Letters as HTML and PDF (WeasyPrint), laid out for window envelopes."""

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


CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "DejaVu Sans", "Helvetica", sans-serif; font-size: 10.5pt;
       line-height: 1.45; color: #111; }
.letter { position: relative; width: 210mm; min-height: 297mm; padding: 105mm 22mm 25mm 22mm; }
.letter + .letter { page-break-before: always; }
.club { position: absolute; top: 18mm; left: 22mm; right: 22mm; font-size: 9pt; color: #444; }
.club strong { color: #111; font-size: 11pt; }
.window { position: absolute; width: 85mm; }
.sender { font-size: 7pt; color: #555; border-bottom: 0.3pt solid #999; padding-bottom: 1mm;
          margin-bottom: 2mm; white-space: nowrap; overflow: hidden; }
.address { font-size: 10.5pt; line-height: 1.35; }
.date { margin-bottom: 8mm; }
h1 { font-size: 11.5pt; margin: 0 0 6mm; }
p { margin: 0 0 3.5mm; }
"""


def letter_html(
    subject: str, body: str, r: Recipient, club: dict, window: str, day: date
) -> str:
    left, top = WINDOWS.get(window, WINDOWS["right"])
    sender = " · ".join(x for x in [club.get("name"), *club.get("lines", [])] if x)
    place = club.get("city")
    when = f"{place}, {long_date(day)}" if place else long_date(day)
    address = "<br>".join(html.escape(x) for x in r.lines)
    club_block = "<br>".join(
        [f"<strong>{html.escape(club.get('name') or '')}</strong>"]
        + [html.escape(x) for x in club.get("lines", [])]
    )
    return f"""
<section class="letter">
  <div class="club">{club_block}</div>
  <div class="window" style="left:{left}mm; top:{top}mm">
    <div class="sender">{html.escape(sender)}</div>
    <div class="address">{address}</div>
  </div>
  <div class="date">{html.escape(when)}</div>
  <h1>{html.escape(fill(subject, r))}</h1>
  {_paragraphs(fill(body, r))}
</section>"""


def document(sections: list[str]) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(sections)}</body></html>"


def pdf(html_text: str) -> bytes:
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    # Self-contained: nothing is loaded from disk or the network.
    return HTML(
        string=html_text, url_fetcher=URLFetcher(allowed_protocols={"data"})
    ).write_pdf()
