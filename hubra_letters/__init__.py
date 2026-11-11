"""Letters: serial letters to members, on paper.

The board writes a letter with placeholders ({vorname}, {name} …), picks who
gets it (members without e-mail, everyone, a group, or a list) and either
downloads one PDF to print for window envelopes or has Pingen
(https://www.pingen.com, a Swiss print-and-post service) print and post each
letter. Pingen needs the club's own API client, entered in the module's
settings; nothing leaves Hubra until someone presses "send".

Permission:
    letters.letters.update   write letters, print them and send them by post
"""

from hubra.core.modules import Blueprint, Module, NavItem, Schedule, SettingField

module = Module(
    code="letters",
    # Access the standard roles get when a club first switches it on
    # (docs/roles.md in hubra-app/hubra).
    role_defaults={"board": "edit", "secretary": "all"},
    name="Letters",
    description="Serial letters as PDF or by post (Pingen)",
    default_enabled=False,
    depends_on=("members",),
    blueprints=(
        Blueprint("hubra_letters.routes", "letters_bp", "/api/v1/app/letters"),
    ),
    nav=(
        NavItem(
            "/app/letters",
            "shell.nav.letters",
            "mail-forward",
            section="communication",
            order=33,
            perms=("letters.letters.update",),
        ),
    ),
    settings=(
        SettingField(
            "window",
            "choice",
            default="right",
            choices=("right", "left"),
            label="Address window",
            description="Where the envelopes' window is: right (Swiss C5/6) or left",
        ),
        SettingField(
            "pingen_client_id",
            "str",
            label="Pingen client ID",
            description="From Pingen › Settings › API (client credentials)",
        ),
        SettingField("pingen_client_secret", "secret", label="Pingen client secret"),
        SettingField(
            "pingen_organisation",
            "str",
            label="Pingen organisation ID",
            description="The UUID of your organisation at Pingen",
        ),
        SettingField(
            "pingen_delivery",
            "choice",
            default="cheap",
            choices=("cheap", "fast"),
            label="Pingen delivery",
            description="cheap: B-Post, fast: A-Post",
        ),
        SettingField("pingen_color", "bool", default=False, label="Print in colour"),
        SettingField(
            "pingen_staging",
            "bool",
            default=False,
            label="Pingen test system",
            description="Send to Pingen's staging system: nothing is printed",
        ),
        SettingField(
            "keep_addresses_months",
            "int",
            default=12,
            label="Keep addresses (months)",
            description=(
                "After this many months the postal addresses of sent letters are"
                " deleted; who got the letter stays. 0 keeps them."
            ),
        ),
    ),
    tasks=("hubra_letters.tasks",),
    schedule=(
        Schedule("letters-post-minutely", "hubra_letters.tasks.post", 60.0),
        Schedule("letters-forget-daily", "hubra_letters.tasks.forget", 86400.0),
    ),
    tables=("letters_letters", "letters_items"),
)
