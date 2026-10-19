/* Settings: light or dark, and whether Tables and SQL shows in the side panel, both kept in this
   browser; a host adds its own rows. */

import { actions } from './events.js';
import { redrawSide } from './frame.js';
import { slot } from './host.js';
import { dialog, slideTo } from './overlays.js';
import { S, applyTheme } from './state.js';
import { store } from './util.js';

function openSettings() {
  dialog('Settings', `<div class="oa-setting-row"><div><p class="oa-setting-name">Appearance</p><p class="note-faint">Kept in this browser only.</p></div>
    <div class="slide-switch" role="radiogroup" aria-label="Appearance" data-state="${S.theme === 'dark' ? 'second' : 'first'}">
      <button type="button" class="slide-switch-part" role="radio" aria-checked="${S.theme === 'light'}" data-act="theme" data-v="light">Light</button>
      <button type="button" class="slide-switch-part" role="radio" aria-checked="${S.theme === 'dark'}" data-act="theme" data-v="dark">Dark</button></div></div>
    <div class="oa-setting-row"><div><p class="oa-setting-name">Tables and SQL</p><p class="note-faint">The release's tables, their downloads and the SQL box, in the side panel. Kept in this browser only.</p></div>
    <div class="slide-switch" role="radiogroup" aria-label="Tables and SQL" data-state="${S.showTables ? 'first' : 'second'}">
      <button type="button" class="slide-switch-part" role="radio" aria-checked="${S.showTables}" data-act="show-tables" data-v="show">Show</button>
      <button type="button" class="slide-switch-part" role="radio" aria-checked="${!S.showTables}" data-act="show-tables" data-v="hide">Hide</button></div></div>
    ${slot('settings')}`);
}

actions({
  settings: () => openSettings(),
  'show-tables': (el) => {
    S.showTables = el.dataset.v === 'show'; store.set('showTables', S.showTables);
    slideTo(el);
    // the side panel and home follow at once; the page itself still opens from a link
    redrawSide();
    document.querySelectorAll('[data-tables-link]').forEach((x) => { x.hidden = !S.showTables; });
  },
  theme: (el) => {
    S.theme = el.dataset.v; store.set('theme', S.theme); applyTheme();
    slideTo(el);
  },
});
