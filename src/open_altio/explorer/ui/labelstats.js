/* Statistics' label parts, on a drug's Statistics tab of a release with the label flags: the Label
   column after Reaction (each pair's flag, which /api/statistics gives with its rows), sorting by
   it, the line above the table naming the label, and the Filters menu's Label status with Only
   reactions that pass the cutoffs under it, on the strip too. Label status narrows the pairs on
   the server (`label`, as filters.py reads it); the cutoffs tick is the Thresholds menu's list
   (screens.js), every pair or the pairs a screen passes. statistics.js plugs these in. */

import { actions } from './events.js';
import { openPane } from './filtermenu.js';
import { icon } from './icons.js';
import { UNEXPECTED_MEANS, flagChoice, flagWord, flagWords, isUnexpectedOnly, labelLink, labelRules, labelWords, labelsOn, requestLabel } from './labels.js';
import { choice, place, popMenu } from './overlays.js';
import { current } from './router.js';
import { everyPair, listedBy, screenOf, screenWords } from './screens.js';
import { esc, tip } from './util.js';

const scopeHere = () => current()?.scope;
// a drug's page of a release with the flags: the only place the label parts show
const labelled = (sc) => !!sc?.product && labelsOn();
// what Label status ticks (null: every flag, as the list opens), kept with the tab's own view
const ticksOf = (sc) => sc.stat?.ticks ?? null;
let changed = () => {}; // the tab's reload, told the scope

// the tab's reload, called when Label status changes
export function onLabelChange(reload) { changed = reload; }

export const LABEL_TIP = 'Whether today\'s US prescription label names the reaction. Point at a flag for how it was decided and the label it was read on';
// the column after Reaction, among the tab's columns
export const labelColumn = {
  id: 'label', head: 'Label', reads: [], tip: LABEL_TIP, cls: 'oa-label-col', when: labelled,
  cell: (r) => flagWord(r.label, r.ingredient),
};

// Label status as /api/statistics reads it; every tick on asks for nothing
export function labelParams(sc, p) {
  const ticks = ticksOf(sc);
  if (labelled(sc) && ticks) (ticks.length ? ticks : [labelRules().nothing_ticked]).forEach((k) => p.append('label', k));
}

// the list holds only the pairs a screen passes
const passing = () => listedBy() !== 'all' && screenOf(listedBy()).preset !== 'none';

// the one line above the table: the labels the flags read, each named and linked once, and
// About the label flags
export function labelLead(sc, found) {
  if (!labelled(sc) || !found) return '';
  const about = '<button type="button" class="oa-link" data-act="about">About the label flags</button>';
  const labels = found.labels || [];
  if (!labels.length) return `<p class="oa-label-lead">We could not find a US prescription label for this drug, so its reactions show ${esc(flagWords('no_label'))}.${requestLabel(sc.product)} ${about}</p>`;
  const which = `today's US prescription label${labels.length > 1 ? 's' : ''}: ${labels.map(labelLink).join('; ')}`;
  return `<p class="oa-label-lead">Label compares each reaction with ${which}. ${about}</p>`;
}

// the toolbar's Filters button, beside Thresholds
export const labelButton = (sc) => (labelled(sc) ? `<button type="button" class="btn oa-filters-btn" data-act="stat-filters" aria-haspopup="menu" aria-label="Filters">${icon('filter')}<span class="oa-btn-words">Filters</span></button>` : '');

// the strip's item for Label status, with its remove; '' while every tick is on
export function labelStrip(sc) {
  const ticks = ticksOf(sc);
  if (!labelled(sc) || !ticks) return '';
  const words = labelWords(ticks);
  return `<div class="oa-strip-items"><span class="oa-strip-item">
      <button type="button" class="oa-strip-edit" data-act="stat-filters" ${tip(`Label status: ${words}`)}><span class="oa-strip-name">Label status</span><span class="oa-strip-value">${esc(words)}</span></button>
      <button type="button" class="icon-btn oa-strip-x" data-act="stat-unfilter" aria-label="Remove the Label status filter">${icon('close')}</button></span></div>`;
}

// the menu's pane: Unexpected only, a tick box per flag with its reactions in the list, then
// Only reactions that pass the cutoffs
function pane(sc) {
  const { outcomes, unexpected_only: unexpected } = labelRules();
  const ticks = ticksOf(sc) || outcomes;
  const counts = sc.stat?.label?.counts || {};
  const screen = passing() ? `${listedBy()}'s threshold: ${screenWords(listedBy())}` : 'set in Thresholds';
  return `<p class="menu-heading">Label status</p>
    <div class="oa-year-quick"><button type="button" class="oa-smq-scope" data-act="stat-unexpected" aria-pressed="${isUnexpectedOnly(ticksOf(sc))}">Unexpected only</button></div>
    <div class="oa-choices">${outcomes.map((k) => flagChoice(ticks.includes(k), k, counts[k] || 0, `data-act="stat-label" data-v="${k}"`)).join('')}</div>
    <p class="menu-heading">Cutoffs</p>
    <div class="oa-choices">${choice(passing(), 'Only reactions that pass the cutoffs', null, 'data-act="stat-pass"')}</div>
    <p class="menu-footnote">Against today's US prescription label. Every flag shows from the start. Unexpected only ticks ${esc(labelWords(unexpected).replace(/, ([^,]*)$/, ' and $1'))}. ${esc(UNEXPECTED_MEANS)} The cutoffs are ${esc(screen)}. Counts are reactions in the list before Label status narrows it. <button type="button" class="oa-link" data-act="about">About the label flags</button></p>`;
}

function paintMenu(sc) {
  const rows = document.getElementById('oa-label-rows');
  const opts = document.getElementById('oa-label-options');
  if (rows) rows.innerHTML = `<button type="button" class="menu-item oa-filter-row" data-act="stat-filter-row" aria-expanded="true"><span>Label status</span><span class="filter-value">${esc(ticksOf(sc) ? labelWords(ticksOf(sc)) : 'Every flag')}</span>${icon('chevronRight')}</button>`;
  if (opts) opts.innerHTML = pane(sc);
}

function openFilters(anchor) {
  const sc = scopeHere();
  const menu = popMenu(anchor, `<div class="oa-sheet-bar"><button type="button" class="btn btn-quiet oa-sheet-back" data-act="sheet-back">${icon('arrowLeft')}<span>Filters</span></button><span class="oa-sheet-title">Filters</span><button type="button" class="btn btn-primary oa-sheet-done" data-act="sheet-done">Done</button></div><div class="oa-filter-rows" id="oa-label-rows"></div><div class="oa-filter-options" id="oa-label-options"></div>`, 'oa-filter-menu oa-label-menu');
  menu.id = 'oa-label-menu';
  menu.dataset.pane = 'rows';
  paintMenu(sc);
  place(menu, anchor);
  // its one filter's options at once, on a phone too
  openPane(menu.querySelector('.oa-filter-row'));
}

// Label status changed: the list is asked for again, and the menu shows the new ticks
function tick(sc, ticks) {
  sc.stat.ticks = ticks;
  paintMenu(sc);
  changed(sc);
}

// the list came back: the menu's counts follow it
export function labelsPainted(sc) { if (document.getElementById('oa-label-menu')) paintMenu(sc); }

actions({
  // from the strip too, the menu opens under the toolbar's button
  'stat-filters': (el) => { if (labelled(scopeHere())) openFilters(document.querySelector('.oa-filters-btn[data-act="stat-filters"]') || el); },
  'stat-filter-row': (el) => openPane(el),
  'stat-label': (el) => {
    const sc = scopeHere(); const all = labelRules().outcomes; const on = ticksOf(sc) || all; const v = el.dataset.v;
    const next = all.filter((k) => (k === v ? !on.includes(k) : on.includes(k)));
    tick(sc, next.length === all.length ? null : next);
  },
  'stat-unexpected': () => { const sc = scopeHere(); if (!isUnexpectedOnly(ticksOf(sc))) tick(sc, [...labelRules().unexpected_only]); },
  'stat-pass': () => { everyPair(passing()); paintMenu(scopeHere()); },
  'stat-unfilter': () => tick(scopeHere(), null),
});
