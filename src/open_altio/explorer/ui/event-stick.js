/* The layers that stay at the top of the page while an opened event scrolls past (event.js), top
   down: the events table's heads, the event's own row, its line and its bar of tabs; a pane's own
   heads may stick under them at --ev-st4. Each is CSS sticky, so nothing jumps as it sticks; this
   module reads each part's height and sets the tops they stick at (--ev-st0 to --ev-st4 on the
   table), so they stack with no gap and no overlap. The row is copied into the top of its open
   cell, laid exactly over the row, and the copy sticks while the event is in view, then leaves with
   it: a table row would stick for the whole table. They stick only while the page alone scrolls
   under them: where the table is wider than its frame, the frame scrolls sideways and nothing
   sticks (data-ev-fits). */

const px = (v) => `${Math.round(v * 100) / 100}px`;
const pad = (el, side) => parseFloat(getComputedStyle(el)[`padding${side}`]) || 0;

// The copy's place at the top of the event's box, filled by restack.
export const COPY = '<div class="oa-ev-copy" aria-hidden="true"><table class="dashboard-table oa-et-table"><colgroup></colgroup><tbody></tbody></table></div>';

// the box stuck now: { box, sizes, rows }
let at = null;
let queued = false;
export function restack() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => { queued = false; stackNow(); });
}

// Watch the event's box in its table: the sizes that set the tops, and the rows the copy follows.
// An event opened inside another's pane sticks nothing: the layers of the one around it stay.
export function stick(box) {
  if (box.parentElement?.closest('.oa-ev')) return;
  at?.sizes.disconnect();
  at?.rows.disconnect();
  at = { box, sizes: new ResizeObserver(restack), rows: new MutationObserver(restack) };
  const table = box.closest('table');
  if (!table) return;
  const page = box.closest('.frame-page');
  const bar = page?.querySelector(':scope > .oa-topbar');
  [table.parentElement, table, table.tHead, bar, box.querySelector('.oa-ev-linewrap'), box.querySelector('.oa-ev-bar')]
    .filter(Boolean).forEach((el) => at.sizes.observe(el));
  at.rows.observe(table.tBodies[0], { childList: true });
  restack();
}

// the open row's copy: its cells the row's own, its columns as wide as the heads, as wide as the
// table, and pulled up over the row by its margins, which give the room back under it; it keeps the
// row's key and press, so a press on it closes the row as a press on the row does
function layCopy(table, row, copy) {
  const box = at.box;
  const inner = copy.firstElementChild;
  inner.tBodies[0].replaceChildren(Object.assign(row.cloneNode(true), { tabIndex: -1 }));
  inner.querySelector('colgroup').innerHTML = [...table.tHead.rows[0].cells].map((h) => `<col style="width: ${px(h.getBoundingClientRect().width)}">`).join('');
  inner.style.width = px(table.getBoundingClientRect().width);
  const h = row.getBoundingClientRect().height;
  const top = pad(box, 'Top');
  copy.style.height = px(h);
  copy.style.margin = `${px(-(h + top))} ${px(-pad(box, 'Right'))} ${px(top)} ${px(-pad(box, 'Left'))}`;
  return h;
}

function stackNow() {
  const box = at?.box;
  const table = box?.isConnected && box.closest('table');
  if (!table) return;
  const frame = table.parentElement;
  frame.dataset.evFits = String(table.scrollWidth <= frame.clientWidth + 1);
  // flush with the page's top edge, or under a phone's top bar, which sticks there itself
  const page = box.closest('.frame-page');
  const bar = page?.querySelector(':scope > .oa-topbar');
  const st0 = bar?.getClientRects().length ? bar.getBoundingClientRect().height : -(page ? pad(page, 'Top') : 0);
  const row = box.closest('tr')?.previousElementSibling;
  const copy = box.querySelector(':scope > .oa-ev-copy');
  const st1 = st0 + table.tHead.getBoundingClientRect().height;
  const st2 = st1 + (row && copy ? layCopy(table, row, copy) : 0);
  const st3 = st2 + (box.querySelector('.oa-ev-linewrap')?.getBoundingClientRect().height || 0);
  const st4 = st3 + (box.querySelector('.oa-ev-bar')?.getBoundingClientRect().height || 0);
  [st0, st1, st2, st3, st4].forEach((v, i) => table.style.setProperty(`--ev-st${i}`, px(v)));
}
window.addEventListener('resize', restack);

// where layer n (0 the heads, 1 the row, 2 the line, 3 the bar, 4 under the bar) sits in the window
// once it has stuck
export function stickY(box, n) {
  const table = box.closest('table');
  const page = box.closest('.frame-page');
  if (!table || !page) return NaN;
  return page.getBoundingClientRect().top + pad(page, 'Top') + (parseFloat(getComputedStyle(table).getPropertyValue(`--ev-st${n}`)) || 0);
}
// whether the layers stick at all: the table fits its frame
export const sticks = (box) => box.closest('.oa-et-frame')?.dataset.evFits === 'true';
