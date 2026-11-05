import { registerPlugin } from '@hubra/plugin-sdk'
import { IconNote } from '@tabler/icons-react'
import { NotesScreen } from './NotesScreen'
import translations from './translations.json'

// Everything here shows only while the module is on for the club and the
// person has `perm`. Other places to add things: `tabs` (a tab on a built-in
// screen) and `slots` (account.cards, inventory.item, settings.module.actions).
registerPlugin({
  id: 'example',
  routes: [
    {
      path: 'example',
      module: 'example',
      perm: 'example.notes.read',
      component: NotesScreen,
    },
  ],
  // The nav entry in hubra_example/__init__.py names this icon.
  icons: { note: IconNote },
  translations,
})
