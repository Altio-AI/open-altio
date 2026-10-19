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

// a menu under its anchor, as far left as it fits
export function place(menu, anchor) {
  follow(menu, anchor);
  const r = anchor.getBoundingClientRect();
  const width = menu.offsetWidth;
  const left = Math.max(12, Math.min(r.left, window.innerWidth - width - 12));
  menu.style.setProperty('--menu-top', `${r.bottom + 6}px`);
  menu.style.setProperty('--menu-left', `${left}px`);
}

// Clicking the button that opened a menu closes it: the browser closes the menu as the click
// starts, so that is noted here and the click itself does not open the menu again.
let menuOpener = null;
let clickClosesMenu = false;
// the control a menu was opened from
export const openedBy = (el) => { menuOpener = el; };
document.addEventListener('pointerdown', (e) => {
  const opener = e.target.closest?.('[data-act]');
  const open = document.querySelector('#oa-layer [popover]:popover-open');
  clickClosesMenu = !!(open && opener && (opener === menuOpener || (opener.classList.contains('oa-filters-btn') && open.id === 'oa-filter-menu')));
}, true);
// whether the click now ending is the one that closed a menu; asked once per click
export function closedByThisClick() {
  const closed = clickClosesMenu;
  clickClosesMenu = false;
  return closed;
}

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
