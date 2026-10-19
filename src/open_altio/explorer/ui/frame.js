/* The page's frame: the side panel, its folded rail and the top bar on a phone, around each page.

   The side panel and the folded rail (railHtml) put every icon they share at the same height, so
   folding or opening never moves what a person reaches for: the fold button first, then Home, All
   cases, Tables and SQL, Rules, a host's places and Products, each with the rail's icon; the person's
   pinned products under Products, the one part that grows; Settings, with what a host adds around
   it, at the foot. How current the data is shows once on every page, top right (asOf). */

import { actions } from './events.js';
import { cardTables, host, slot } from './host.js';
import { icon, markSvg } from './icons.js';
import { popMenu } from './overlays.js';
import { current, productPath } from './router.js';
import { S, pinned, productLabel, releaseLast } from './state.js';
import { esc, store, tip } from './util.js';

export const sidePlace = (href, ic, label, here, attrs = '', after = '') => `<a class="row oa-side-row${here ? ' row-current' : ''}" href="${href}" ${attrs}>${icon(ic)}<span class="row-label">${esc(label)}</span>${after}</a>`;
export const railPlace = (href, ic, label, here, extra = '', after = '') => `<a class="oa-rail-item" href="${href}" aria-label="${esc(label)}" ${tip(label)} ${here ? 'aria-current="page"' : ''} ${extra}>${icon(ic)}${after}</a>`;
export const railButton = (act, ic, label, extra = '') => `<button type="button" class="oa-rail-item" data-act="${act}" aria-label="${esc(label)}" ${tip(label)} ${extra}>${icon(ic)}</button>`;

const NO_PINS = 'Pin a product to keep it here.';
function productRows(here) {
  if (!pinned().length) return `<li class="oa-side-note">${NO_PINS}</li>`;
  return pinned().map((p) => `<li class="chat-row oa-prod-row" draggable="true" data-prod="${esc(p.name)}" data-state="idle">
      <a class="row row-nested chat-open${here === `p:${p.name}` ? ' row-current' : ''}" href="${productPath(p.name)}" draggable="false" ${p.label ? tip(p.title || p.name) : ''}><span class="row-label">${esc(productLabel(p.name))}</span></a>
      <span class="chat-dots"><button type="button" class="icon-btn" data-act="prod-menu" data-prod="${esc(p.name)}" aria-haspopup="menu" aria-label="Options for ${esc(productLabel(p.name))}">${icon('dots')}</button></span>
    </li>`).join('');
}

function sidePanel(here) {
  return `<aside class="side-panel panel" aria-label="Side panel">
    <div class="side-brand">
      <a class="brand-home" href="/" aria-label="Open Altio, home">${markSvg()}<span class="brand-name">Open Altio</span></a>
      <button type="button" class="icon-btn side-collapse" data-act="side-close" aria-label="Collapse the side panel">${icon('panelLeftClose')}</button>
    </div>
    ${sidePlace('/', 'home', 'Home', here === 'home')}
    ${sidePlace('/all/overview', 'bullets', 'All cases', here === 'all')}
    ${S.showTables ? sidePlace('/release', 'database', 'Tables and SQL', here === 'release') : ''}
    ${sidePlace('/methods', 'numbers', 'How we clean FAERS', here === 'methods')}
    ${slot('side-places', here)}
    <section class="side-section oa-side-products">
      <h2 class="section-head oa-prod-head">${icon('folder')}<span>Products</span></h2>
      <ul class="oa-prod-list" id="oa-prod-list">${productRows(here)}</ul>
    </section>
    <section class="side-section oa-side-you">
      ${slot('side-you', here)}
      <button type="button" class="row oa-side-row" data-act="settings" aria-haspopup="dialog">${icon('settings')}<span class="row-label">Settings</span></button>
      ${slot('side-you-end', here)}
    </section>
  </aside>`;
}

// Improve this: the same place, top right, on every page, where notes are taken
export const improveBtn = () => (host.improve ? `<button type="button" class="btn oa-improve" data-act="improve">${icon('improve')}<span>Improve this</span></button>` : '');
// how current the data is, the one place each page says it: in the top bar on a phone, else top right
export const asOf = (quarter = S.release && releaseLast()) => (quarter ? `<p class="oa-asof">FDA data through ${esc(quarter)}</p>` : '');

// With the side panel folded, its places stay one click away: each as an icon that names itself, at
// the height the open panel gives it (sidePanel). Home is the way home; the mark is not repeated here.
function railHtml(here) {
  return `<nav class="side-rail oa-rail" aria-label="Open Altio">
    <button type="button" class="oa-rail-item" data-act="side-open" aria-label="Open the side panel" ${tip('Open the side panel')}>${icon('panelLeftOpen')}</button>
    <span class="oa-rail-line" aria-hidden="true"></span>
    ${railPlace('/', 'home', 'Home', here === 'home')}
    ${railPlace('/all/overview', 'bullets', 'All cases', here === 'all')}
    ${S.showTables ? railPlace('/release', 'database', 'Tables and SQL', here === 'release') : ''}
    ${railPlace('/methods', 'numbers', 'How we clean FAERS', here === 'methods')}
    ${slot('rail-places', here)}
    ${railButton('rail-products', 'folder', 'Products', `aria-haspopup="menu" ${String(here).startsWith('p:') ? 'aria-current="page"' : ''}`)}
    <span class="oa-spacer"></span>
    ${slot('rail-you', here)}
    ${railButton('settings', 'settings', 'Settings', 'aria-haspopup="dialog"')}
    ${slot('rail-you-end', here)}
  </nav>`;
}

// Below 1024 the side panel is a drawer over the page; from 1024 it sits beside it, folded by default
// until 1440. A person's own open or fold choice is kept for the wide screens.
const narrow = () => window.innerWidth < 1024;
function sideState() {
  if (narrow()) return S.drawer ? 'open' : 'closed';
  return S.side || (window.innerWidth >= 1440 ? 'open' : 'closed');
}
const paintSide = () => document.querySelector('.frame')?.setAttribute('data-side-panel-state', sideState());
let sideWasNarrow = narrow();
window.addEventListener('resize', () => {
  if (narrow() !== sideWasNarrow) { sideWasNarrow = narrow(); S.drawer = false; }
  paintSide();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && S.drawer) { S.drawer = false; paintSide(); }
});

export function framed(content, here) {
  return `<div class="frame" data-page="${here === 'home' ? 'home' : 'product'}" data-side-panel-state="${sideState()}" data-right-panel-state="closed">
    ${sidePanel(here)}
    <div class="oa-scrim" data-act="side-close" aria-hidden="true"></div>
    <div class="frame-page">
      <header class="oa-topbar">
        <button type="button" class="icon-btn oa-menu-btn" data-act="side-open" aria-label="Open the menu">${icon('menu')}</button>
        <a class="brand-home" href="/" aria-label="Open Altio, home">${markSvg()}<span class="brand-name">Open Altio</span></a>
        <span class="oa-spacer"></span>
        ${asOf()}
        ${host.improve ? `<button type="button" class="btn oa-improve-top" data-act="improve" aria-label="Improve this">${icon('improve')}<span class="oa-improve-words">Improve this</span></button>` : ''}
      </header>
      <div class="oa-corner">${asOf()}${improveBtn()}</div>
      ${railHtml(here)}
      ${content}
    </div>
  </div>`;
}

// where the frame is: a scope's key ('all', 'p:<product>') or the page's name
const currentKey = () => { const r = current(); return r?.scope ? (r.scope.product ? `p:${r.scope.product}` : 'all') : r?.page; };
export function repaintSide() {
  const list = document.getElementById('oa-prod-list');
  if (list) list.innerHTML = productRows(currentKey());
}
// the side panel and the rail drawn again, as a setting changes what they hold
export function redrawSide() {
  const side = document.querySelector('.side-panel');
  if (side) side.outerHTML = sidePanel(currentKey());
  const rail = document.querySelector('.oa-rail');
  if (rail) rail.outerHTML = railHtml(currentKey());
}

actions({
  'rail-products': (el) => {
    popMenu(el, pinned().length
      ? `<p class="menu-heading">Products</p>${pinned().map((x) => `<a class="menu-item" href="${productPath(x.name)}">${esc(productLabel(x.name))}</a>`).join('')}`
      : `<p class="oa-pane-none">${NO_PINS} Find one from Home.</p>`, 'oa-rail-menu');
    const r = el.getBoundingClientRect();
    const m = document.querySelector('.oa-rail-menu');
    if (m) { m.style.setProperty('--menu-left', `${r.right + 8}px`); m.style.setProperty('--menu-top', `${r.top}px`); }
  },
  'side-close': () => { if (narrow()) S.drawer = false; else { S.side = 'closed'; store.set('side', S.side); } paintSide(); },
  'side-open': () => { if (narrow()) S.drawer = true; else { S.side = 'open'; store.set('side', S.side); } paintSide(); },
});

// Lists read row by row become cards on phones; each cell is labelled with its column's name.
// Number tables (SQL results) are not listed: they scroll inside their frame.
let labelQueued = false;
function labelCells() {
  labelQueued = false;
  const cards = cardTables.join(', ');
  document.querySelectorAll(`#app table:is(${cards}), #oa-layer table:is(${cards})`).forEach((t) => {
    const heads = [...(t.tHead?.rows[0]?.cells || [])].map((h) => h.innerText.replace(/\s+/g, ' ').trim());
    t.classList.add('oa-cardable');
    for (const body of t.tBodies) for (const row of body.rows) [...row.cells].forEach((c, i) => { if (heads[i] && c.colSpan === 1) c.dataset.label = heads[i]; });
  });
}
new MutationObserver(() => { if (!labelQueued) { labelQueued = true; requestAnimationFrame(labelCells); } })
  .observe(document.body, { childList: true, subtree: true });
