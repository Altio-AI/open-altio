/* A breakdown line pressed (event-breakdowns.js): the press puts the value the line shows on the
   event's line as its filter, once, and lists every value of its field, each with its cases in the
   window and its share before the window and in it among the reports that give the field, counted
   under the event's other filters, so the list keeps its counts whatever is ticked in it. A line
   with no value of its filter to show (Time to onset's median) filters nothing as it opens, and its
   list shows every box ticked. Unticking one keeps the others, ticking the last one left out shows
   every case again, Deselect all leaves none (no case shows) and Show all ticks them all again, as
   + Add a filter does. A pick is the line's filter (its `filter`, an explorer parameter), put on
   the event's line with ctx.setFilter, so every pane counts under it. A line with no filter lists
   its values with nothing to change. Pressing the line again closes the list. */

import { actions } from './events.js';
import { choice, onClosing, openedBy, place, popMenu } from './overlays.js';
import { api } from './server.js';
import { esc, num, tip } from './util.js';
import { askedOf, rowsOf, shownValues, wordsOf } from './event-breakdowns-values.js';

// the list open now: { o (the section), field, asked, rows (null while they come), menu }
let open = null;
function closed() {
  if (!open) return;
  const { o } = open;
  open = null;
  o.paint();
}
onClosing(closed);
export const valuesOpen = (o) => open?.o === o;

// the line's filter as the event holds it: undefined while every value is ticked
const pickedOf = (ctx, name) => (ctx.filters || []).find((f) => f.field === name)?.values;
const lineOf = (at) => at.o.answer.lines.find((l) => l.field === at.field);

function listHtml() {
  const { o } = open;
  const line = lineOf(open);
  const head = `<p class="menu-heading">${esc(line.name)}</p><p class="oa-bd-key">Before the window → in it, among the reports that give it</p>`;
  if (!open.rows) return `${head}<div class="oa-choices oa-bd-values">${'<span class="skeleton skeleton-row"></span>'.repeat(4)}</div>`;
  const name = line.filter;
  const picked = name ? pickedOf(o.ctx, name) : undefined;
  const on = (v) => picked === undefined || picked.includes(v);
  // a picked value no case of these gives still shows, so it can be unticked
  const known = new Set(open.rows.map((r) => r.value));
  for (const v of (picked || []).filter((x) => !known.has(x))) open.rows.push({ value: v, words: wordsOf(name, v) || v, now: 0, before: 0, note: '' });
  const rows = open.rows.map((r, i) => {
    const said = `${r.words}: ${num(r.before)} ${r.before === 1 ? 'case' : 'cases'} before the window, ${num(r.now)} in it`;
    return choice(on(r.value), r.words, r.now, `data-act="bd-value" data-i="${i}"${name ? '' : ' aria-disabled="true"'} ${tip(said)}`, { note: r.note });
  }).join('') || '<p class="oa-pane-none">No case gives this field.</p>';
  const every = picked === undefined;
  const foot = name ? `<p class="menu-footnote oa-bd-foot"><button type="button" class="oa-link" data-act="bd-all" data-all="${every ? 'none' : 'every'}">${every ? 'Deselect all' : 'Show all'}</button></p>
    <p class="menu-footnote">Counts are the window's cases under the other filters. Once some are unticked, the ticked ones are on the line above.</p>` : '';
  return `${head}<div class="oa-choices oa-bd-values">${rows}</div>${foot}`;
}

function markLine(at) {
  const el = at.o.box.querySelector(`.oa-bd-line[data-field="${CSS.escape(at.field)}"]`);
  el?.setAttribute('aria-expanded', 'true');
  return el;
}
// the list drawn again, the focus staying on what it was on
function paintList() {
  const { menu } = open;
  if (!menu.isConnected) return;
  const at = document.activeElement;
  const was = menu.contains(at) ? (at.dataset.i != null ? `[data-i="${at.dataset.i}"]` : '[data-act="bd-all"]') : '';
  menu.innerHTML = listHtml();
  if (was) menu.querySelector(was)?.focus({ preventScroll: true });
}
// Its values, counted under every filter of the event but the line's own
function ask(at) {
  at.asked = askedOf(at.o.ctx, lineOf(at).filter || '');
  const asked = at.asked;
  api(`/api/breakdowns?${asked}`).then((got) => {
    if (open !== at || at.asked !== asked) return;
    at.rows = rowsOf(got.lines.find((l) => l.field === at.field));
    paintList();
    const el = markLine(at);
    if (el) place(at.menu, el.querySelector('.oa-bd-name') || el, { fit: true, beside: false });
  }).catch(() => { if (open === at && at.asked === asked) { at.rows = []; paintList(); } });
}
// after the section is drawn again: the list follows the line's new copy, its ticks and the question
export function repaintValues(o) {
  if (open?.o !== o || !open.menu.isConnected) return;
  const el = markLine(open);
  if (el) openedBy(el);
  if (open.asked !== askedOf(o.ctx, lineOf(open).filter || '')) ask(open);
  paintList();
}

export function openValues(o, line, el) {
  const { ctx } = o;
  const had = line.filter ? pickedOf(ctx, line.filter) : undefined;
  const pick = shownValues(line);
  const adds = pick.length > 0 && !pick.every((v) => had?.includes(v));
  const anchor = el.querySelector('.oa-bd-name') || el;
  // the menu first: opening one closes any other, and a closing list lets go of `open`
  const menu = popMenu(anchor, '', 'oa-bd-menu');
  // with no filter of its own, the line's answer is its list; this also learns the values' words
  const rows = rowsOf(line);
  const here = { o, field: line.field, asked: '', rows: had === undefined ? rows : null, menu };
  open = here;
  menu.innerHTML = listHtml();
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed' && open === here) closed(); });
  place(here.menu, anchor, { fit: true, beside: false });
  openedBy(el);
  markLine(here);
  ask(here);
  if (adds) ctx.setFilter(line.filter, [...new Set([...(had || []), ...pick])]);
  o.paint();
}

// a value pressed: from every box ticked, the others stay picked; the last one left out ticked
// again is no filter; with none ticked, it is the only one
function press(v) {
  const line = lineOf(open);
  const all = open.rows.map((r) => r.value);
  const picked = pickedOf(open.o.ctx, line.filter);
  let next;
  if (picked === undefined) next = all.filter((x) => x !== v);
  else if (picked.includes(v)) next = picked.filter((x) => x !== v);
  else next = [...picked, v];
  if (next.length && all.every((x) => next.includes(x))) next = null;
  open.o.ctx.setFilter(line.filter, next);
}

actions({
  'bd-value': (el) => {
    if (!open?.rows || el.getAttribute('aria-disabled') === 'true') return;
    press(open.rows[+el.dataset.i].value);
  },
  'bd-all': (el) => {
    if (open?.rows) open.o.ctx.setFilter(lineOf(open).filter, el.dataset.all === 'none' ? [] : null);
  },
});
