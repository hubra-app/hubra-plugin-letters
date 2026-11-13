# Letters

## Unreleased

- Letters carry the club's letterhead (logo, name, address, contact line,
  primary colour), the same as invoices and the board's PDFs. Hubra lays them
  out through `pdf.render` (hubra#332); the plugin no longer runs WeasyPrint
  itself. The recipient's address stays where the envelope's window is
  (right or left), and the footer shows no page count, since one print file
  holds every recipient's letter. Needs Hubra 0.2.6 or later (raise `hubra:`
  in plugin.yaml at release).
- Only drafts can be deleted. Sent and printed letters stay as the record of
  who got them; their addresses go after the retention period.
- The print PDF of every letter is made in the background: "Make print PDF",
  then a notification when it's ready, and the download. Works for clubs with
  thousands of members; the PDF is kept 7 days, deleted earlier when the
  letter changes. Needs `flask db upgrade` (new columns on letters_letters).
- Postal addresses of sent letters are deleted after 12 months (setting
  "Keep addresses", 0 keeps them); who got the letter stays. Runs daily.
- Deleting a letter deletes its recipient list too, and the daily job clears
  the name and address of members who were deleted (club schemas have no
  foreign keys, so the database didn't do it).
- Security: the Pingen token is cached per client ID *and* secret, a letter
  is never posted twice when the job overlaps or a click repeats, Pingen
  uploads only over HTTPS, and editing or retrying a letter is in the audit log.
- The menu entry moves to the new sidebar area **Kommunikation**, next to Mail,
  Messengers and Inbox. Needs a Hubra with that area (after 0.2.5); older
  versions show it under a heading of its own.
- The Pingen hint points at Einstellungen › Module › Briefe (the tab is called Module). German: "Empfänger/in" like the other gender forms in Hubra.

## 1.1.0

- Gives the standard roles access when a club first switches it on (`role_defaults`, docs/roles.md in hubra-app/hubra): Vorstand Bearbeiten, Aktuar/in Alles. Roles without access don't see it; their own data from it stays on their profile. Needs Hubra 0.2.5 or later.

## 1.0.0

First version: serial letters with placeholders to members without e-mail,
all members, a group or chosen members; one PDF for window envelopes (right
or left window); marking letters as printed; sending each letter by post
through the club's own Pingen account, with retries.
