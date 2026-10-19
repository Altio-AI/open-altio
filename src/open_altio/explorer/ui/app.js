/* Open Altio's explorer in the browser: every screen drawn from the /api answers
   (src/open_altio/explorer/api.py). Each part of the page is a module of its own here; this one
   loads them, starts the page, and is what a host's page modules import (a host, such as the
   hosted service, adds its own screens through extend()). */

// the clicks' listener first, so a click an act has handled is no link to follow (router.js)
import './events.js';
import './home.js';
import './scope.js';
import './charts.js';
import './cases.js';
import './casedialog.js';
import './labels.js';
import './filtermenu.js';
import './drugs.js';
import './terms.js';
import './cmq.js';
import './exports.js';
import './settings.js';
import './products.js';
import './tables.js';
import './sql.js';
import './improve.js';
import './rules/page.js';
import { host } from './host.js';
import { render } from './router.js';
import { api } from './server.js';
import { S, applyTheme } from './state.js';
import { esc } from './util.js';

applyTheme();

// Who is here and what they may see, then the first page. A page module that draws its own screens
// (the hosted service's sign-in) decides that itself.
async function startHere() {
  S.me = await api('/api/me');
  S.release = await api('/api/release');
}
async function boot() {
  await (host.start || startHere)();
  render();
}
// A host's page modules come after this one on the page (src/open_altio/explorer/pages.py); every
// module on it has run, and so extended the page, by DOMContentLoaded.
document.addEventListener('DOMContentLoaded', () => boot().catch((err) => {
  document.getElementById('app').innerHTML = `<main class="door"><div class="door-card panel"><h1 class="door-brand">Open Altio</h1><p class="banner">The server did not answer: ${esc(err.message)}</p></div></main>`;
}), { once: true });

// what a page module may use
export { takeDownload } from './downloads.js';
export { ACTS } from './events.js';
export { openPane } from './filtermenu.js';
export { framed, improveBtn, railButton, railPlace, sidePlace } from './frame.js';
export { extend } from './host.js';
export { icon, markSvg } from './icons.js';
export { busy, choice, closeMenus, dialog, formProblem, layer, openedBy, place, popMenu, showProblem, toast } from './overlays.js';
export { addressParts, current, go, here, pageAt, putAddress, render } from './router.js';
export { api, post } from './server.js';
export { S, meddraOn, rereadStored } from './state.js';
export { quartersOf, rowsIn } from './tablewords.js';
export { day, esc, num, size, store, tip, trim } from './util.js';
