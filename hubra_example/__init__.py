"""Example: a notice board, the smallest plugin that uses every part.

Rename it before you build on it (see TEMPLATE.md): the plugin id, the
package name (hubra_<something>), the module code, the table and the
permission resource.
"""

from hubra.core.modules import Blueprint, Module, NavItem, SettingField

module = Module(
    code="example",
    name="Example",
    description="A notice board: short notes for the whole club",
    default_enabled=False,
    depends_on=("members",),
    blueprints=(
        Blueprint(
            "hubra_example.routes",
            "example_bp",
            "/api/v1/app/example",
        ),
    ),
    nav=(
        NavItem(
            "/app/example",
            "shell.nav.example",
            "note",
            section="more",
            order=90,
            perms=("example.notes.read",),
        ),
    ),
    settings=(
        SettingField(
            "max_notes",
            "int",
            default=50,
            label="Most notes on the board",
            description="Older notes are hidden once there are more",
        ),
    ),
    # Every table the plugin owns: new clubs get them, and autogenerate only
    # looks at these.
    tables=("example_notes",),
)
