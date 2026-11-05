## What changes

## Release

- [ ] `version` in `plugin.yaml` bumped (if this goes into a release)
- [ ] `CHANGELOG.md` has a `## <version>` section
- [ ] New tables have a migration (`has_table()` guarded) and are listed in `tables=`

## Tested

- [ ] `pytest ../../plugins/<id>` in a Hubra checkout
- [ ] `npm run typecheck:plugins` in `app/frontend`
