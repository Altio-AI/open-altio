/* Updates to Open Altio, newest first, from updates.txt: each line a day, the band's short line,
   " | ", and the history's full line. Home's band says the newest on every visit until its close
   is pressed, and again once a newer one comes; Home's release card always says it, and from two
   on opens the history, its newest updates showing (rule explorer-lists' updates_shown) and the
   older ones scrolling inside the menu. Read as the page starts, so Home is drawn with them. */

import { actions } from './events.js';
import { refreshed } from './frame.js';
import { icon } from './icons.js';
import { popMenu } from './overlays.js';
import { listLength } from './state.js';
import { esc, store, tip } from './util.js';

const CLOSED = 'update-closed'; // the newest update whose band this browser closed
const parse = (text) => text.split('\n').filter((line) => /^\d{4}-\d{2}-\d{2} /.test(line)).map((line) => {
  const [short, full] = line.slice(11).split(' | ').map((w) => w.trim());
  return { day: line.slice(0, 10), short, full: full || short };
});
let all = null; // the updates once read; none where the file could not be
const reading = fetch('/ui/updates.txt').then((r) => (r.ok ? r.text() : '')).catch(() => '').then((text) => { all = parse(text); return all; });
export const readUpdates = () => reading;
export const updatesRead = () => all !== null;

// the band shows until its close is pressed for the newest update; seeing it changes nothing
const keyOf = (u) => `${u.day} ${u.short}`;
const bandShown = () => !!all?.length && store.get(CLOSED, '') !== keyOf(all[0]);

// the band under the greeting: the newest update's short line, the history at its end from two on,
// and its close
export function updateBand() {
  if (!bandShown()) return '';
  const words = `<span class="oa-update-words">${esc(all[0].short)}</span>`;
  const open = all.length > 1
    ? `<button type="button" class="oa-update-open" data-act="updates" aria-haspopup="menu">${words}<span class="oa-update-all"><span class="oa-update-all-words">All updates</span>${icon('chevronRight')}</span></button>`
    : words;
  return `<div class="oa-update" id="oa-update">${icon('bell')}${open}<button type="button" class="icon-btn oa-update-x" data-act="update-hide" aria-label="Hide this update" ${tip('Hide this update')}>${icon('close')}</button></div>`;
}

// the release card's line on the newest update, and from two on its link to the history
export const latestLine = () => (all?.length ? `<p class="oa-faint oa-release-kind oa-update-latest">Latest update: ${esc(all[0].short)}</p>` : '');
export const allUpdatesLink = () => (all?.length > 1 ? '<button type="button" class="oa-link" data-act="updates" aria-haspopup="menu">All updates</button>' : '');

actions({
  updates: (el) => {
    const menu = popMenu(el, `<p class="menu-heading">Updates</p>${all.map((u) => `<p class="menu-note oa-update-row"><span class="oa-update-day">${esc(refreshed(u.day))}</span><span>${esc(u.full)}</span></p>`).join('')}`, 'oa-updates');
    const last = menu.querySelectorAll('.oa-update-row')[listLength('updates_shown') - 1];
    if (!last) return;
    menu.style.setProperty('--updates-height', `${last.offsetTop + last.offsetHeight + parseFloat(getComputedStyle(menu).paddingBottom)}px`);
    // against its control again at its capped height: under it where it fits, else over it
    const r = el.getBoundingClientRect(), h = menu.offsetHeight;
    menu.style.setProperty('--menu-top', `${r.bottom + 4 + h < window.innerHeight ? r.bottom + 4 : Math.max(12, r.top - h - 4)}px`);
  },
  'update-hide': () => {
    store.set(CLOSED, keyOf(all[0]));
    document.getElementById('oa-update')?.remove();
  },
});
