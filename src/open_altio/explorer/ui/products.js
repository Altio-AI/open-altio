/* Pinning a product, and the pinned products in the side panel: the pin on a found product and on
   a product's page, each row's options (rename, unpin) and dragging a row to reorder them. They are
   kept in this browser. */

import { actions } from './events.js';
import { repaintSide } from './frame.js';
import { icon } from './icons.js';
import { closeMenus, popMenu, toast } from './overlays.js';
import { render } from './router.js';
import { S, isPinned, keepProducts, pinsChanged, productLabel, setPinned } from './state.js';
import { esc, tip } from './util.js';

const productRow = (name) => document.querySelector(`.oa-prod-row[data-prod="${CSS.escape(name)}"]`);

// the one control that pins a product and unpins it, wherever the product shows
const pinWords = (name, on) => ({ label: `${on ? 'Unpin' : 'Pin'} ${productLabel(name)}`, tip: on ? 'Unpin from the side panel' : 'Pin to the side panel' });
export function pinButton(name) {
  const on = isPinned(name);
  const w = pinWords(name, on);
  return `<button type="button" class="icon-btn oa-pin" data-act="pin" data-prod="${esc(name)}" aria-pressed="${on}" aria-label="${esc(w.label)}" ${tip(w.tip)}>${icon('pin')}</button>`;
}
function paintPins(name) {
  const on = isPinned(name);
  const w = pinWords(name, on);
  document.querySelectorAll(`.oa-pin[data-prod="${CSS.escape(name)}"]`).forEach((b) => {
    b.setAttribute('aria-pressed', String(on));
    b.setAttribute('aria-label', w.label);
    b.dataset.tip = w.tip;
  });
}
function pin(name, on) {
  setPinned(name, on);
  paintPins(name);
  repaintSide();
  toast(on ? `${productLabel(name)} is pinned to the side panel.` : `${productLabel(name)} is unpinned.`);
}

// a pinned product's options
const productMenu = (name) => `<button type="button" class="menu-item" data-act="prod-rename" data-prod="${esc(name)}">${icon('pencil')}<span>Rename</span></button>
       <button type="button" class="menu-item" data-act="prod-unpin" data-prod="${esc(name)}">${icon('pin')}<span>Unpin</span></button>`;

function openProductMenu(btn) {
  const row = btn.closest('.oa-prod-row');
  row.dataset.state = 'menu';
  const menu = popMenu(btn, productMenu(btn.dataset.prod));
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed' && row.isConnected && row.dataset.state !== 'renaming') row.dataset.state = 'idle'; });
}

function renameProduct(name) {
  closeMenus();
  const row = productRow(name);
  if (!row) return;
  row.dataset.state = 'renaming';
  row.draggable = false;
  const p = S.products.find((x) => x.name === name);
  const box = document.createElement('div');
  box.className = 'chat-rename';
  box.innerHTML = `<input class="chat-rename-input" value="${esc(productLabel(name))}" aria-label="Rename ${esc(productLabel(name))}" maxlength="60">`;
  row.prepend(box);
  const input = box.querySelector('input');
  input.focus(); input.select();
  let done = false;
  const finish = (save) => {
    if (done) return; done = true;
    if (save) {
      const v = input.value.trim();
      p.label = v && v !== (p.title || p.name) ? v : '';
      keepProducts();
    }
    render();
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
  input.addEventListener('blur', () => finish(true));
}

let dragName = null;
document.addEventListener('dragstart', (e) => {
  const row = e.target.closest?.('.oa-prod-row');
  if (!row) return;
  dragName = row.dataset.prod;
  row.classList.add('oa-dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', dragName);
});
document.addEventListener('dragover', (e) => {
  const row = e.target.closest?.('.oa-prod-row');
  if (!row || !dragName) return;
  e.preventDefault();
  const r = row.getBoundingClientRect();
  document.querySelectorAll('.oa-prod-row[data-drop]').forEach((x) => x.removeAttribute('data-drop'));
  if (row.dataset.prod !== dragName) row.dataset.drop = e.clientY < r.top + r.height / 2 ? 'before' : 'after';
});
document.addEventListener('drop', (e) => {
  const row = e.target.closest?.('.oa-prod-row');
  if (!row || !dragName) return;
  e.preventDefault();
  const where = row.dataset.drop;
  const moving = S.products.find((p) => p.name === dragName);
  if (where && moving) {
    S.products = S.products.filter((p) => p !== moving);
    const at = S.products.findIndex((p) => p.name === row.dataset.prod) + (where === 'after' ? 1 : 0);
    S.products.splice(at, 0, moving);
    keepProducts();
    pinsChanged();
  }
  dragName = null;
  repaintSide();
});
document.addEventListener('dragend', () => {
  dragName = null;
  document.querySelectorAll('.oa-prod-row').forEach((x) => { x.classList.remove('oa-dragging'); x.removeAttribute('data-drop'); });
});

actions({
  pin: (el) => pin(el.dataset.prod, el.getAttribute('aria-pressed') !== 'true'),
  'prod-menu': (el, e) => { e.preventDefault(); openProductMenu(el); },
  'prod-rename': (el) => renameProduct(el.dataset.prod),
  'prod-unpin': (el) => { closeMenus(); pin(el.dataset.prod, false); },
});
