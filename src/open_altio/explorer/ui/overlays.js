/* What opens over the page: dialogs, menus, toasts and the tip a grey value carries; and the
   small helpers a form uses while the server answers. */

import { icon } from './icons.js';
import { esc, hovered, num, tip } from './util.js';

export const layer = () => document.getElementById('oa-layer');

// what each part does as menus close: a part that keeps a menu's state lets it go
const closing = [];
export const onClosing = (done) => closing.push(done);
export function closeMenus() {
  document.querySelectorAll('#oa-layer [popover]').forEach((m) => { try { m.hidePopover(); } catch { /* closed */ } m.remove(); });
  closing.forEach((done) => done());
}

export function dialog(heading, body, foot = '') {
  const dlg = document.createElement('dialog');
  dlg.className = 'dialog oa-dialog';
  dlg.innerHTML = `<div class="dialog-head"><h2 class="dialog-title">${heading}</h2><button type="button" class="icon-btn" data-act="close-dialog" aria-label="Close">${icon('close')}</button></div>
    <div class="dialog-body">${body}</div>${foot ? `<div class="dialog-foot">${foot}</div>` : ''}`;
  layer().appendChild(dlg);
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  dlg.showModal();
  return dlg;
}

// A menu under its anchor, as far left as it fits. With `fit` it stays inside the window: under its
// anchor where it fits, else over it, else beside it on the side with more room; where none of
// those holds it, on the roomier of under and over, as tall as that room and scrolling inside. With
// `beside` false it never goes beside: a menu of a whole line must leave that line to press.
export function place(menu, anchor, { fit = false, beside = true } = {}) {
  follow(menu, anchor);
  const r = anchor.getBoundingClientRect();
  const [top, left] = fit ? fitted(menu, r, beside) : [r.bottom + 6, Math.max(12, Math.min(r.left, window.innerWidth - menu.offsetWidth - 12))];
  menu.style.setProperty('--menu-top', `${top}px`);
  menu.style.setProperty('--menu-left', `${left}px`);
}
const EDGE = 12;
const GAP = 6;
function fitted(menu, r, beside) {
  const wide = window.innerWidth, high = window.innerHeight;
  menu.style.maxHeight = '';
  menu.style.overflowY = '';
  menu.style.maxWidth = `${wide - 2 * EDGE}px`;
  const w = menu.offsetWidth, h = menu.offsetHeight;
  const along = Math.max(EDGE, Math.min(r.left, wide - w - EDGE));
  const under = high - EDGE - (r.bottom + GAP), over = r.top - GAP - EDGE;
  if (h <= under) return [r.bottom + GAP, along];
  if (h <= over) return [r.top - GAP - h, along];
  const right = wide - EDGE - (r.right + GAP), left = r.left - GAP - EDGE;
  const tall = Math.min(h, high - 2 * EDGE);
  const scroll = (room) => { if (h > room) { menu.style.maxHeight = `${room}px`; menu.style.overflowY = 'auto'; } };
  if (beside && w <= Math.max(right, left)) {
    scroll(tall);
    return [Math.max(EDGE, Math.min(r.top, high - EDGE - tall)), right >= left ? r.right + GAP : r.left - GAP - w];
  }
  scroll(Math.max(under, over));
  return [under >= over ? r.bottom + GAP : Math.max(EDGE, r.top - GAP - h), along];
}

// Clicking the button that opened a menu closes it: the browser closes the menu as the click
// starts, so that is noted here and the click itself does not open the menu again. A press anywhere
// else outside an open menu only closes it, as a menu does on a desktop: the row, link or bar under
// it does nothing, so closing a menu never opens a row by the way.
let menuOpener = null;
let pressed = ''; // what the press now ending does to an open menu: 'opener', 'outside', or nothing
// the control a menu was opened from
export const openedBy = (el) => { menuOpener = el; };
const openMenu = () => [...document.querySelectorAll('.menu[popover]')].find((m) => m.matches(':popover-open'));
document.addEventListener('pointerdown', (e) => {
  const open = openMenu();
  if (!open || open.contains(e.target)) { pressed = ''; return; }
  const opener = e.target.closest?.('[data-act]');
  const own = opener && (opener === menuOpener || (opener.classList.contains('oa-filters-btn') && open.id === 'oa-filter-menu'));
  pressed = own ? 'opener' : 'outside';
}, true);
// whether the click now ending is the one that closed a menu; asked once per click
export function closedByThisClick() {
  const closed = pressed !== '';
  pressed = '';
  return closed;
}
// a press outside: closes the menus, and nothing under it hears the click (a click from a key,
// detail 0, had no press)
document.addEventListener('click', (e) => {
  if (pressed !== 'outside' || e.detail === 0) return;
  pressed = '';
  e.preventDefault();
  e.stopImmediatePropagation();
  closeMenus();
}, true);

// A menu stays where it was set against its button as the page scrolls or the window changes:
// whenever the button has moved, the menu moves by the same amount.
const followed = new Map();
function follow(menu, anchor) {
  const at = anchor.getBoundingClientRect();
  followed.set(menu, { menu, anchor, top: at.top, left: at.left });
}
function carry() {
  followed.forEach((f, menu) => {
    if (!menu.isConnected) { followed.delete(menu); return; }
    if (!f.anchor.isConnected) return;
    const at = f.anchor.getBoundingClientRect();
    const dy = at.top - f.top;
    const dx = at.left - f.left;
    if (!dy && !dx) return;
    const css = getComputedStyle(f.menu);
    f.menu.style.setProperty('--menu-top', `${parseFloat(css.top) + dy}px`);
    f.menu.style.setProperty('--menu-left', `${parseFloat(css.left) + dx}px`);
    f.top = at.top;
    f.left = at.left;
  });
}
document.addEventListener('scroll', carry, true);
window.addEventListener('resize', carry);

// A menu stays against its control as its rows change: one over the control keeps its foot there as
// it narrows, one under keeps its head, and it goes to the other side once it no longer fits where it
// is and fits better there. One beside its control stays as it was set.
function keepAgainst(menu) {
  let gap = null;
  const sizes = new ResizeObserver(() => {
    const f = followed.get(menu);
    if (!menu.isConnected || !f) { sizes.disconnect(); return; }
    if (!f.anchor.isConnected) return;
    const at = f.anchor.getBoundingClientRect(), now = menu.getBoundingClientRect();
    if (now.right <= at.left || now.left >= at.right) return;
    let over = now.top < at.top;
    gap ??= Math.max(0, over ? at.top - now.bottom : now.top - at.bottom);
    const high = menu.offsetHeight;
    const above = at.top - gap - EDGE, below = window.innerHeight - EDGE - at.bottom - gap;
    if (over ? high > above && below > above : high > below && above > below) over = !over;
    menu.style.setProperty('--menu-top', `${over ? Math.max(EDGE, at.top - gap - high) : at.bottom + gap}px`);
  });
  sizes.observe(menu);
  sizes.observe(followed.get(menu).anchor);
}

export function popMenu(anchor, html, cls = '') {
  closeMenus();
  const menu = document.createElement('div');
  menu.className = `menu ${cls}`;
  menu.setAttribute('popover', 'auto');
  menu.innerHTML = html;
  // inside a dialog, the menu belongs to the dialog: anything outside it cannot be clicked
  (anchor.closest('dialog') || layer()).appendChild(menu);
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed') menu.remove(); });
  menu.showPopover();
  menuOpener = anchor;
  follow(menu, anchor);
  const r = anchor.getBoundingClientRect();
  const below = r.bottom + 4 + menu.offsetHeight < window.innerHeight;
  menu.style.setProperty('--menu-top', `${below ? r.bottom + 4 : r.top - menu.offsetHeight - 4}px`);
  menu.style.setProperty('--menu-left', `${Math.max(12, Math.min(r.left, window.innerWidth - menu.offsetWidth - 12))}px`);
  keepAgainst(menu);
  return menu;
}

// a choice: its box (ticked, a dash when `on` is 'mixed', partly ticked, or a dot for one-of), its
// words, its count; `role` for one outside a menu
export const tickMark = (on) => (on === 'mixed' ? icon('minus') : on ? icon('check') : '');
// the dash is quiet, grey in the plain box, and says what it means: part of this class or group
export const partTip = (on, what) => (on === 'mixed' ? tip(`Part of this ${what} is ticked`) : '');
export function choice(on, label, count, attrs, { radio = false, note = '', role = '' } = {}) {
  return `<button type="button" class="menu-item oa-choice" role="${role || (radio ? 'menuitemradio' : 'menuitemcheckbox')}" aria-checked="${on}" ${attrs} ${count === 0 && !on ? 'data-state="empty"' : ''}>
    <span class="oa-tick${radio ? ' oa-tick-radio' : ''}" aria-hidden="true" ${partTip(on, 'group')}>${radio ? '' : tickMark(on)}</span>
    <span class="menu-choice-words">${esc(label)}${note ? ` <span class="oa-choice-note">${esc(note)}</span>` : ''}</span>${count == null ? '' : `<span class="choice-count">${num(count)}</span>`}</button>`;
}

// a slide switch moved to the part clicked
export function slideTo(part) {
  const sw = part.closest('.slide-switch');
  const parts = [...sw.querySelectorAll('.slide-switch-part')];
  sw.dataset.state = ['first', 'second', 'third'][parts.indexOf(part)];
  parts.forEach((b) => b.setAttribute('aria-checked', String(b === part)));
}

export function formProblem(box, message) {
  const p = box.querySelector('[data-problem]');
  p.textContent = message || '';
  p.hidden = !message;
}
export function busy(button, on) {
  button.disabled = on;
  if (on) button.setAttribute('aria-busy', 'true'); else button.removeAttribute('aria-busy');
}

export function toast(text) {
  const box = document.getElementById('oa-toasts');
  const t = document.createElement('p');
  t.className = 'oa-toast';
  t.textContent = text;
  box.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}
export function showProblem(err) { toast(`Could not load: ${err.message || err}`); }

// the tip: what a grey value or an icon is, over it while the pointer is there; a touch shows none,
// so a tap is never taken for a hover. Inside an open window or menu it goes into it, which the
// browser draws above everything else on the page.
let tipEl = null;
const tipBoxEl = () => (tipEl ||= document.getElementById('oa-tip'));
export function hideTip() { const t = tipBoxEl(); if (t) t.hidden = true; }
document.addEventListener('pointerover', (e) => {
  if (!hovered(e)) return;
  const el = e.target.closest?.('[data-tip]');
  if (!el) { hideTip(); return; }
  const tipBox = tipBoxEl();
  const home = el.closest('dialog[open], :popover-open') || document.body;
  if (tipBox.parentElement !== home) home.appendChild(tipBox);
  tipBox.textContent = el.dataset.tip;
  tipBox.hidden = false;
  const r = el.getBoundingClientRect();
  const w = tipBox.offsetWidth;
  tipBox.style.left = `${Math.max(8 + w / 2, Math.min(window.innerWidth - 8 - w / 2, r.left + r.width / 2))}px`;
  tipBox.style.top = `${r.top - 8}px`;
});
document.addEventListener('scroll', hideTip, true);
