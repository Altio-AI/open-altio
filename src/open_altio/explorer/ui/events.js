/* What clicks do. Each part names what its controls do by their data-act (actions), and one
   listener on the page hands each click to the part whose act it is. */

import { closeMenus, closedByThisClick, hideTip } from './overlays.js';

// a data-act -> (the element clicked, the event); every part's, and a host's
export const ACTS = {};
export const actions = (acts) => Object.assign(ACTS, acts);

// every dialog's Close and Cancel
actions({ 'close-dialog': (el) => el.closest('dialog')?.close() });

document.addEventListener('click', (e) => {
  hideTip();
  const el = e.target.closest('[data-act]');
  if (!el || el.tagName === 'SELECT' || el.tagName === 'INPUT') return;
  if (closedByThisClick()) { closeMenus(); return; }
  const act = ACTS[el.dataset.act];
  if (act) act(el, e);
});

// Enter and Space on a row or a role="button" with an act do what a click does; typing stays typing
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  if (e.target.matches('input, textarea, select')) return;
  const el = e.target.closest('tr[data-act], [role="button"][data-act]');
  if (el) { e.preventDefault(); ACTS[el.dataset.act]?.(el, e); }
});
