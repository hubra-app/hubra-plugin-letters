import { registerPlugin } from '@hubra/plugin-sdk'
import { IconMailForward } from '@tabler/icons-react'
import { LetterScreen } from './LetterScreen'
import { LettersScreen } from './LettersScreen'
import translations from './translations.json'

registerPlugin({
  id: 'letters',
  routes: [
    { path: 'letters', module: 'letters', perm: 'letters.letters.update', component: LettersScreen },
    { path: 'letters/new', module: 'letters', perm: 'letters.letters.update', component: LetterScreen },
    { path: 'letters/:id', module: 'letters', perm: 'letters.letters.update', component: LetterScreen },
  ],
  // The nav entry in hubra_letters/__init__.py names this icon.
  icons: { 'mail-forward': IconMailForward },
  translations,
})
