/* The Compared tab's + Add a drug or class (event-compared.js): a menu under the toolbar's box. Where
   ctx.classes holds, it is the Drug class filter (classes.js) with this event's counts: its head and
   search box, Chosen and Left out pinned while ticks change, then every WHO class from the main
   groups as a tree, ticked as the filter ticks; typed words search every level, and the drugs under
   them. Otherwise it finds drugs only, and no class is asked for. A drug is found by its name or a
   spelling it is reported under; a drug ticked is compared, unticked it leaves the table. */

import { classRows, parentOf, pinned, press, whoLine, yearChip } from './classes.js';
import { actions } from './events.js';
import { choice, onClosing, openedBy, popMenu, showProblem } from './overlays.js';
import { esc, skeletonRows } from './util.js';
import { change, classesIn, classesKnown, found, ticksOf } from './event-compared-data.js';

let picking = null; // { cmp, typed, found: { q, drugs }, open, shut, ready, drugPin, classPin }

const has = (pk, d) => (ticksOf(pk.cmp.ctx)?.drugs || []).some((x) => x.name === d.name);
const drugRow = (pk, d) => choice(has(pk, d), d.title, null, `data-act="cmp-tick" data-name="${esc(d.name)}" data-title="${esc(d.title)}"`);

// the classes above a class, each listed, so a press can settle them and their names are known
const learnAbove = (ctx, code) => {
  const ups = [];
  for (let up = parentOf(code); up; up = parentOf(up)) ups.push(classesIn(ctx, { parent: up }));
  return Promise.all([classesIn(ctx), ...ups]);
};

function classesHtml(pk, q, drugs) {
  const { ctx } = pk.cmp;
  const r = classesKnown(ctx, q ? { q } : {});
  if (!pk.ready || !r || !drugs) return skeletonRows(3);
  const f = ticksOf(ctx);
  const words = q.toLowerCase();
  const key = words;
  const rows = [r, ...[...f.atc, ...f.atcOut].map((c) => classesKnown(ctx, { parent: parentOf(c) }))].filter(Boolean).flatMap((a) => [...a.classes, ...a.chosen, ...a.left_out]);
  const t = { f, q: words, words: q, open: pk.open, shut: pk.shut, kids: (code) => classesKnown(ctx, { parent: code })?.classes, pick: 'cmp-class', expand: 'cmp-expand' };
  // the drugs compared, pinned with the classes under Chosen
  if (pk.drugPin?.key !== key) pk.drugPin = { key, drugs: [...f.drugs] };
  const more = pk.drugPin.drugs.map((d) => drugRow(pk, d)).join('');
  const others = drugs.filter((d) => !pk.drugPin.drugs.some((c) => c.name === d.name));
  return classRows(t, r, pinned(pk, key, f, rows), { more })
    + (others.length ? `<p class="menu-heading">Drugs</p><div class="oa-choices">${others.map((d) => drugRow(pk, d)).join('')}</div>` : '');
}

function drugsHtml(pk, q, drugs) {
  const t = ticksOf(pk.cmp.ctx);
  if (pk.drugPin?.key !== q) pk.drugPin = { key: q, drugs: [...t.drugs] };
  const pin = pk.drugPin.drugs;
  const chosen = pin.length ? `<p class="menu-heading">Chosen</p><div class="oa-choices">${pin.map((d) => drugRow(pk, d)).join('')}</div>` : '';
  if (!q) return `${chosen}<p class="oa-pane-none">Type a drug's name or a spelling it is reported under.</p>`;
  if (!drugs) return chosen + skeletonRows(3);
  const others = drugs.filter((d) => !pin.some((c) => c.name === d.name));
  return chosen + (others.length ? `<p class="menu-heading">Drugs</p><div class="oa-choices">${others.map((d) => drugRow(pk, d)).join('')}</div>` : `<p class="oa-pane-none">No drug is named "${esc(q)}".</p>`);
}

function paint() {
  const pk = picking;
  const box = document.getElementById('oa-cmp-results');
  if (!pk || !box) return;
  const q = pk.typed.trim();
  const drugs = !q ? [] : pk.found?.q === q ? pk.found.drugs : null;
  // a pressed tick or expand mark keeps the focus once its row is drawn again
  const was = box.contains(document.activeElement) ? document.activeElement : null;
  const at = was && { act: was.dataset.act, code: was.dataset.code, name: was.dataset.name };
  const scroll = box.scrollTop;
  box.innerHTML = pk.cmp.ctx.classes ? classesHtml(pk, q, drugs) : drugsHtml(pk, q, drugs);
  box.scrollTop = scroll;
  if (at) [...box.querySelectorAll(`[data-act="${at.act}"]`)].find((b) => b.dataset.code === at.code && b.dataset.name === at.name)?.focus({ preventScroll: true });
}

let timer = 0;
function findNow() {
  clearTimeout(timer);
  const pk = picking;
  const q = pk.typed.trim();
  paint();
  if (!q) return;
  timer = setTimeout(async () => {
    try {
      const { ctx } = pk.cmp;
      const [drugs] = await Promise.all([found(q, ctx.drug), ctx.classes ? classesIn(ctx, { q }) : null]);
      if (picking === pk && pk.typed.trim() === q) { pk.found = { q, drugs }; paint(); }
    } catch (err) { showProblem(err); }
  }, 110);
}

// the menu under the box, as wide as it or wider, inside the window; `typed` what was typed in the box
export function openPicker(input, cmp, typed = '') {
  if (!cmp) return;
  const { ctx } = cmp;
  const anchor = input.closest('.search-bar') || input;
  const head = ctx.classes ? `<div class="oa-pane-head oa-atc-head"><p class="menu-heading">Drug class (ATC)</p>${yearChip()}</div>` : '<p class="menu-heading">Drugs</p>';
  const said = ctx.classes ? 'Find a class or a drug' : 'Find a drug';
  const hint = ctx.classes ? 'Type a class, a code or a substance' : 'Type a drug or a substance';
  const foot = ctx.classes ? `A case counts when a drug in a ticked role is in a ticked class. ${whoLine()}` : `Each drug ticked is counted as ${esc(cmp.own)} is, in the same window and filters.`;
  const menu = popMenu(anchor, `<div class="oa-cmp-picker">${head}
      <input class="field-input oa-menu-search oa-cmp-find" id="oa-cmp-find" type="search" autocomplete="off" spellcheck="false" aria-label="${said}" placeholder="${hint}">
      <div class="oa-term-results oa-cmp-results" id="oa-cmp-results">${skeletonRows(3)}</div>
      <p class="menu-footnote">${foot}</p></div>`, 'oa-cmp-menu');
  openedBy(anchor);
  const pk = { cmp, typed, found: null, open: new Set(), shut: new Set(), ready: !ctx.classes };
  picking = pk;
  const find = menu.querySelector('#oa-cmp-find');
  find.value = typed;
  find.focus();
  if (ctx.classes) {
    // the main groups, and every class above a ticked one, before the first rows: Chosen comes whole
    const t = ticksOf(ctx);
    Promise.all([classesIn(ctx), ...[...(t?.atc || []), ...(t?.atcOut || [])].map((c) => learnAbove(ctx, c))])
      .then(() => { pk.ready = true; if (picking === pk) paint(); }, showProblem);
  }
  findNow();
}

document.addEventListener('input', (e) => {
  if (e.target.id !== 'oa-cmp-find' || !picking) return;
  picking.typed = e.target.value;
  picking.open.clear(); picking.shut.clear();
  findNow();
});
onClosing(() => { picking = null; });

actions({
  'cmp-tick': (el) => {
    const pk = picking;
    if (!pk) return;
    const d = { name: el.dataset.name, title: el.dataset.title };
    change(pk.cmp.ctx, (t) => { t.drugs = t.drugs.some((x) => x.name === d.name) ? t.drugs.filter((x) => x.name !== d.name) : [...t.drugs, d]; });
    paint();
  },
  'cmp-expand': (el) => {
    const pk = picking;
    if (!pk) return;
    const code = el.dataset.code;
    if (el.getAttribute('aria-expanded') === 'true') { pk.open.delete(code); pk.shut.add(code); } else {
      pk.shut.delete(code); pk.open.add(code);
      classesIn(pk.cmp.ctx, { parent: code }).then(() => { if (picking === pk) paint(); }, showProblem);
    }
    paint();
  },
  // a class ticks or unticks every class under it, and the classes above settle, as in the Drug class filter
  'cmp-class': async (el) => {
    const pk = picking;
    if (!pk) return;
    const code = el.dataset.code;
    const { ctx } = pk.cmp;
    try { await learnAbove(ctx, code); } catch (err) { showProblem(err); return; }
    if (picking !== pk) return;
    const names = Object.fromEntries((pk.classPin ? Object.values(pk.classPin.known) : []).map((c) => [c.code, c.name]));
    const inView = [classesKnown(ctx, pk.typed.trim() ? { q: pk.typed.trim() } : {}), classesKnown(ctx, { parent: parentOf(code) }), classesKnown(ctx, { parent: code })];
    inView.filter(Boolean).forEach((a) => a.classes.forEach((c) => { names[c.code] = c.name; }));
    change(ctx, (t) => {
      press(t, code);
      [...t.atc, ...t.atcOut].forEach((c) => { if (names[c]) t.names[c] ||= names[c]; });
    });
    paint();
  },
});
