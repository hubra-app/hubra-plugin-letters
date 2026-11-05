# Hubra plugin template

Start a new [Hubra](https://hubra.club) plugin from here. The template is a
small plugin that works and uses every part a plugin has: a notice board
with one table, an API, a screen in the club app, a module setting, a
migration, tests, and the workflow that tests, signs and releases it.

**Plugin id** `example` · **Package** `hubra_example` · **Module** `example` · **Works with** Hubra `>=0.2,<1`

## Make a new plugin

1. **Create the repository.** Click **Use this template** and name it
   `hubra-plugin-<id>` in `hubra-app`. The Marketplace
   ([hubra-app/hubra-plugins](https://github.com/hubra-app/hubra-plugins))
   lists every public `hubra-plugin-*` repository there once it has a release.
2. **Rename everything called example.** Use the same name in every place:

   | Where | Example | Yours |
   | --- | --- | --- |
   | `plugin.yaml` `id`, `name`, `description`, `homepage`, `tags` | `example` | `<id>` |
   | Package folder and `package:` (must start with `hubra_`) | `hubra_example` | `hubra_<name>` |
   | Module code (`plugin.yaml` `modules:`, `Module(code=...)`, `module:` in `frontend/src/index.tsx`) | `example` | must not clash with a Hubra module |
   | Blueprint name, which sets the permission prefix | `example_bp` gives `example.notes.read` | `<name>_bp` |
   | Table names, in `models.py`, `tables=` and the migration | `example_notes` | prefix them with your id |
   | API path | `/api/v1/app/example` | `/api/v1/app/<id>` (the club area; plugins cannot add platform or global routes) |
   | Club-app route and nav entry | `/app/example` | |
   | Translations (`shell.nav.example`, `example.*`) | | |

   Then replace the migration with your own (`0a1b2c3d4e5f_example_notes.py`)
   and set `version: "1.0.0"` and the first `CHANGELOG.md` entry.
3. **Set up the repository** (Settings):
   - **Rules › Rulesets › Import a ruleset:** import both files from
     [`.github/rulesets/`](.github/rulesets/). `main.json` protects `main`
     (pull request, required check `test`, no force push or delete);
     `tags.json` makes `v*` tags permanent once published.
   - **Environments › New environment** `plugin-signing`: add the secret
     `HUBRA_SIGNING_KEY` (the official plugin key; never a repository or
     organisation secret), add yourself as required reviewer, and limit
     deployment to tags `v*`.
   - Optional repository secret `MARKETPLACE_TOKEN` (Actions: write on
     hubra-app/hubra-plugins), so a release is listed at once instead of
     within the hour.
   - **Code security:** turn on secret scanning, push protection and private
     vulnerability reporting.

## Layout

```
plugin.yaml              # id, version, Hubra range, package, modules, requires
hubra_example/
  __init__.py            # module = Module(...): blueprint, nav entry, setting, tables
  models.py              # SQLAlchemy models (one copy per club schema)
  routes.py              # the API, with permission_required(...)
migrations/              # Alembic revisions of this plugin only
frontend/src/
  index.tsx              # registerPlugin({...}): routes, icons, translations
  NotesScreen.tsx        # the screen
  api.ts                 # calls to the plugin's API
  translations.json      # en-GB and de-CH
tests/test_example.py    # runs with Hubra's pytest fixtures
CHANGELOG.md             # "## <version>" sections, shown before updating
.releaseignore           # kept out of the release zip
.github/workflows/release.yml
.github/rulesets/        # importable rulesets for main and v* tags
```

What a plugin can do (settings, event hooks, Celery tasks, tabs on built-in
screens, slots, connected apps) is in
[plugins/README.md](https://github.com/hubra-app/hubra/blob/main/plugins/README.md)
and [hubra/modules/README.md](https://github.com/hubra-app/hubra/blob/main/app/backend/hubra/modules/README.md).
[hubra-plugin-keys](https://github.com/hubra-app/hubra-plugin-keys) is a
bigger real plugin to compare with.

## Develop

Clone the repository into `plugins/<id>` of a Hubra checkout:

```
cd hubra/app/backend
pytest ../../plugins/<id>                       # tests, with Hubra's fixtures
flask plugins revision <id> -m "..." --autogenerate   # with HUBRA_PLUGINS_AUTOINSTALL=<id>
cd ../frontend
npm run typecheck:plugins
npm run build:plugin -- ../../plugins/<id>      # --watch while you work
```

With `HUBRA_PLUGINS_AUTOINSTALL=<id>` a local Hubra loads the plugin from the
checkout without installing it.

## Release

Bump `version` in `plugin.yaml`, add a `## <version>` section to
`CHANGELOG.md` and merge. Then tag the merged commit on main and push the tag:

```sh
git switch main && git pull
git tag v<version> && git push origin v<version>
```

The workflow tests the plugin and builds its frontend, the `plugin-signing`
job signs it after your approval, and only then is the GitHub release
`v<version>` published, with `<id>-<version>.zip` and its `.sha256` attached. Files
listed in `.releaseignore` stay out of the zip. Releases are immutable, so a
published version never changes: fix a bad one with a new version. The template itself is never signed.

Migrations must keep the previous version working (add columns and tables,
drop them a release later): a rollback in the plugin catalogue does not undo
them.
