/* An opened event's Compared tab (event.js): the event's numbers for its drug beside any other drugs
   and WHO's classes, before and in the window. A toolbar, + Add a drug or class
   (event-compared-picker.js) and "N compared with [drug], highest EB05 first · each score's change
   during the window"; under it one plain table that fills the room left on the screen and scrolls
   inside, its heads staying. The event's drug sits on top in a faint tint, then each row added; a
   class opens to the classes and drugs in it. Every row is counted the same way, in the window and
   the line's filters (event-compared-data.js counts, event-compared-table.js draws). Every head but
   Change sorts from its menu, the event's drug staying on top. A drug's name opens the same event
   for that drug, read only, in this window and these filters (event-compared-view.js). A host's mark
   of its own drugs comes through `event-drug-mark`, its thresholds through ctx.screens, and where
   ctx.classes is false this tab is of single drugs: no class is asked for or drawn. */

import { registerEventPane } from './event.js';
import { stickY, sticks } from './event-stick.js';
import { actions } from './events.js';
import { icon } from './icons.js';
import { whoLine } from './classes.js';
import { closeMenus, popMenu } from './overlays.js';
import { S } from './state.js';
import { esc, num } from './util.js';
import { change, countedAs, inSentence, membersOf, numbersOf, offNumbers, onNumbers, ownCodes, picksOf, titleOf } from './event-compared-data.js';
import { openPicker } from './event-compared-picker.js';
import { columnsHtml } from './event-compared-extra.js';
import { colgroup, headHtml, ordered, rowHtml, sortMenu, sortOf, waitRow } from './event-compared-table.js';
import { closeView, openView } from './event-compared-view.js';

// ---- one opened event's comparison ------------------------------------------------------------
class Compared {
  constructor(pane, ctx) {
    this.pane = pane;
    this.ctx = ctx;
    this.sort = { col: 'eb05', dir: 'desc' };
    this.extras = []; // the statistics added as columns, in the order added
    this.bounds = {}; // an added column's bound: rows below it are left out
    this.open = new Map(); // a class's code -> open or shut, as pressed
    this.last = new Map(); // a row's key -> the numbers it last showed, kept while it is asked again
    this.repaint = () => this.paintRows();
    onNumbers(this.repaint);
  }

  get event() { return inSentence(this.ctx.row?.pt || this.ctx.reaction.join(', ')); }
  get own() { return titleOf(this.ctx.drug); }
  // a row's numbers as they come; what it last showed, faint, while it is asked again
  withNumbers(n) {
    const r = numbersOf(this.ctx, n);
    if (r.done) { this.last.set(n.key, r); return { ...n, r }; }
    const was = this.last.get(n.key);
    return was ? { ...n, r: was, stale: true } : { ...n, r };
  }
  // a class starts open where the event's drug is in it, the way down to it, until pressed
  isOpen(code) {
    return this.open.has(code) ? this.open.get(code) : (ownCodes[this.ctx.drug] || []).some((c) => c.startsWith(code));
  }
  // the rows to draw, in order: the event's drug, then each row added, what an open class holds under it
  lines() {
    const ctx = this.ctx;
    const own = this.withNumbers({ kind: 'drug', name: ctx.drug, title: this.own, own: true, pinned: true, lvl: 0, top: true, key: 'own' });
    const out = [own];
    const picks = picksOf(ctx);
    if (!picks) return { own, out, count: null };
    const walk = (nodes) => {
      for (const d of ordered(nodes.map((n) => this.withNumbers(n)), this.sort).filter((x) => this.holds(x))) {
        if (d.kind === 'class') d.open = this.isOpen(d.code);
        out.push(d);
        if (d.kind !== 'class' || !d.open) continue;
        const inside = membersOf(ctx, d);
        if (inside) walk(inside);
        else out.push({ wait: d.lvl + 1 });
      }
    };
    walk(picks.map((p) => ({ ...p, lvl: 0, top: true, own: p.name === ctx.drug })));
    return { own, out, count: picks.length };
  }

  // a row stays unless an added column has a bound its number is below (a row not yet counted stays)
  holds(d) {
    return d.pinned || Object.entries(this.bounds).every(([id, v]) => v == null || !d.r?.done || (d.r.extra?.[id]?.now ?? -Infinity) >= v);
  }

  html() {
    const add = this.ctx.classes ? 'Add a drug or class' : 'Add a drug';
    return `<section class="oa-cmp" data-cmp>
      <div class="oa-cmp-main">
        <div class="oa-cmp-tools">
          <div class="search-bar oa-cmp-search"><span class="search-icon">${icon('plus')}</span><input class="search-input oa-cmp-add" type="search" autocomplete="off" spellcheck="false" aria-haspopup="menu" aria-label="${add} to the comparison" placeholder="${add}"></div>
          <p class="oa-cmp-count"></p>
          <button type="button" class="btn oa-et-columns" data-act="cmp-columns" aria-haspopup="menu">${icon('bullets')}<span class="oa-et-columns-words">Columns</span></button>
        </div>
        <div class="dashboard-frame oa-cmp-frame"><table class="dashboard-table oa-cmp-table" style="min-width:${this.minWidth()}px">${colgroup(this.extras)}<thead>${this.headHtml()}</thead><tbody></tbody></table></div>
        <p class="oa-cmp-foot">${this.footHtml()}</p>
      </div>
      <div class="oa-cmp-view" hidden></div>
    </section>`;
  }

  // the columns keep their room; the frame scrolls where the screen is narrower
  minWidth() { return 1290 + 156 * this.extras.length; }

  headHtml() { return headHtml(this.sort, this.event, this.ctx.classes, this.extras); }

  countWords(n) {
    // the words are there before the number, so the line keeps its height as it comes
    return `<strong>${n == null ? '<span class="skeleton"></span>' : num(n)}</strong> compared with ${esc(inSentence(this.own))}, ${esc(sortOf(this.sort.col).said(this.sort.dir))} · each score's change during the window`;
  }
  footHtml() {
    const { roles, unit } = countedAs(this.ctx);
    const said = roles.join() === 'PS,SS' ? 'primary or secondary suspect' : roles.map((r) => (S.release.drugs.roles.find(([c]) => c === r)?.[1] || r).toLowerCase()).join(' or ');
    const how = unit === 'exact' ? 'that product alone' : 'any product containing it';
    return `${esc(`Each drug counted the same way, in the same window and filters: ${how}, as ${said}.`)}${this.ctx.classes ? ` ${whoLine()}` : ''}`;
  }

  paint() {
    this.pane.innerHTML = this.html();
    this.paintRows();
  }
  paintRows() {
    const box = this.pane.querySelector(':scope > .oa-cmp');
    if (!box || !this.pane.isConnected) return;
    const { out, count } = this.lines();
    // each statistic's one scale: a little past the highest value drawn, at least 2
    const tops = {};
    for (const stat of ['eb05', 'prr']) {
      tops[stat] = 1.06 * Math.max(2, ...out.filter((d) => d.r?.done && d.r[stat]).flatMap((d) => [d.r[stat].before, d.r[stat].now]).filter((v) => v != null));
    }
    const frame = box.querySelector('.oa-cmp-frame');
    const top = frame.scrollTop;
    box.querySelector(':scope > .oa-cmp-main .oa-cmp-count').innerHTML = this.countWords(count);
    box.querySelector('.oa-cmp-table tbody').innerHTML = out.map((d) => (d.wait != null ? waitRow(d.wait) : rowHtml(this.ctx, d, tops, this.event, this.extras))).join('');
    frame.scrollTop = top;
    this.fit();
  }
  paintHeads() {
    const group = this.pane.querySelector('.oa-cmp-table colgroup');
    if (group) group.outerHTML = colgroup(this.extras);
    this.pane.querySelector('.oa-cmp-table').style.minWidth = `${this.minWidth()}px`;
    const head = this.pane.querySelector('.oa-cmp-table thead');
    if (head) head.innerHTML = this.headHtml();
    this.paintRows();
  }

  // The table fills the room under the layers that stay at the top, its line under it, and scrolls
  // inside, as tall as its rows up to the screen's foot; where nothing sticks it is as tall as its rows.
  fit() {
    const frame = this.pane.querySelector('.oa-cmp-frame');
    if (!frame || this.pane.hidden) return;
    frame.style.maxHeight = '';
    if (!sticks(this.pane)) return;
    const foot = this.pane.querySelector('.oa-cmp-foot');
    const fr = frame.getBoundingClientRect();
    const under = foot ? foot.getBoundingClientRect().bottom - fr.bottom : 0;
    const top = stickY(this.pane, 4) + fr.top - this.pane.getBoundingClientRect().top;
    frame.style.maxHeight = `${Math.max(220, Math.floor(window.innerHeight - top - under - 10))}px`;
  }

  update(ctx) {
    this.ctx = ctx;
    const foot = this.pane.querySelector('.oa-cmp-foot');
    if (foot) foot.innerHTML = this.footHtml();
    this.paintRows();
    if (this.viewing) openView(this, this.viewing);
  }
  close() {
    offNumbers(this.repaint);
    closeView(this);
  }
}

const shown = new WeakMap(); // the section -> its comparison
const of = (el) => shown.get(el.closest('.oa-cmp'));

registerEventPane('compared', {
  label: 'Compared',
  order: 2,
  draw: (pane, ctx) => {
    const cmp = new Compared(pane, ctx);
    cmp.paint();
    shown.set(pane.querySelector('.oa-cmp'), cmp);
    return { update: (next) => cmp.update(next), close: () => cmp.close() };
  },
});
window.addEventListener('resize', () => document.querySelectorAll('.oa-cmp').forEach((el) => of(el)?.fit()));

let sorting = null; // the comparison whose head menu is open
let picking = null; // the comparison whose Columns menu is open
actions({
  'cmp-columns': (el) => {
    const cmp = of(el);
    if (!cmp) return;
    picking = cmp;
    popMenu(el, columnsHtml(cmp.extras), 'oa-cmp-sortmenu');
  },
  'cmp-col': (el) => {
    if (!picking) return;
    const id = el.dataset.v, on = picking.extras.includes(id);
    picking.extras = on ? picking.extras.filter((x) => x !== id) : [...picking.extras, id];
    if (on) { delete picking.bounds[id]; if (picking.sort.col === id) picking.sort = { col: 'eb05', dir: 'desc' }; }
    closeMenus();
    picking.paintHeads();
  },
  'cmp-unbound': (el) => {
    if (!sorting) return;
    delete sorting.bounds[el.dataset.v];
    const box = el.closest('.oa-et-bound');
    box.querySelector('input').value = '';
    box.querySelector('input').dataset.changed = 'false';
    el.dataset.state = 'off';
    sorting.paintRows();
  },
  'cmp-head': (el) => {
    const cmp = of(el);
    if (!cmp) return;
    sorting = cmp;
    popMenu(el, sortMenu(cmp.sort, el.dataset.v, cmp.own, cmp.ctx.classes, cmp.bounds), 'oa-cmp-sortmenu');
  },
  'cmp-sort': (el) => {
    if (!sorting) return;
    sorting.sort = { col: el.dataset.v, dir: el.dataset.dir };
    closeMenus();
    sorting.paintHeads();
  },
  'cmp-remove': (el) => {
    const cmp = of(el);
    if (!cmp) return;
    const [kind, what] = [el.dataset.key.slice(0, 1), el.dataset.key.slice(2)];
    change(cmp.ctx, (t) => {
      if (kind === 'd') { t.drugs = t.drugs.filter((d) => d.name !== what); return; }
      t.atc = t.atc.filter((c) => c !== what);
      t.atcOut = t.atcOut.filter((o) => t.atc.some((c) => o !== c && o.startsWith(c)));
    });
  },
  'cmp-toggle': (el) => {
    const cmp = of(el);
    if (!cmp) return;
    const code = el.dataset.code;
    cmp.open.set(code, !cmp.isOpen(code));
    cmp.paintRows();
  },
  'cmp-go': (el) => { const cmp = of(el); if (cmp) openView(cmp, el.dataset.name); },
});

// the toolbar's box: a press opens the picker under it, and what is typed there goes on in it
document.addEventListener('click', (e) => {
  const box = e.target.closest?.('.oa-cmp-add');
  if (box && !document.querySelector('.oa-cmp-menu')) openPicker(box, of(box));
});
document.addEventListener('input', (e) => {
  const box = e.target.closest?.('.oa-cmp-add');
  if (!box) return;
  const typed = box.value;
  box.value = '';
  openPicker(box, of(box), typed);
});

// a bound typed in an added column's menu narrows the rows at once
document.addEventListener('input', (e) => {
  const id = e.target.dataset?.cmpBound;
  if (!id || !sorting) return;
  const raw = e.target.value.trim(), v = raw === '' ? null : Number(raw);
  if (v != null && !Number.isFinite(v)) return;
  if (v == null) delete sorting.bounds[id]; else sorting.bounds[id] = v;
  e.target.dataset.changed = String(v != null);
  e.target.closest('.oa-et-bound')?.querySelector('.oa-et-reset')?.setAttribute('data-state', v == null ? 'off' : 'on');
  sorting.paintRows();
});
