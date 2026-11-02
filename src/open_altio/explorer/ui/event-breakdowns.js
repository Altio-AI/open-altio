/* An opened event's breakdowns, a section of its Overview under the chart and the tiles
   (overviewSection 'breakdowns', event-overview.js): the groups of rule breakdown-lines, Clinical
   picture, Causality and Data quality, one line per field. Each line shows the value its field's
   pick names, its share before the window and in it among the reports that give the field, the
   change in points and how many of the window's reports give the field, all from /api/breakdowns
   under the event's filters and window. A whole line is pressed: it lists every value of its field
   with its count (event-breakdowns-menu.js); the press puts the value the line shows on the event's
   line as its filter, and ticking the list changes that filter.
   Each line's tip says it in words; no line under the groups explains them. A number turns the
   warning color only where a host asks for the lines' alarm (ctx.screens, { breakdowns: { points,
   strength } }). While an answer comes the lines it replaces stay, quieter, so nothing moves. */

import { actions } from './events.js';
import { overviewSection } from './event-overview.js';
import { api } from './server.js';
import { esc, num, tip } from './util.js';
import { BLANK, alarmOf, askedOf, days, pct, valueWords } from './event-breakdowns-values.js';
import { openValues, repaintValues, valuesOpen } from './event-breakdowns-menu.js';

// what each group is about, under its name
const ABOUT = {
  clinical: 'How serious, and who is affected',
  causality: 'Timing, dechallenge, dose, other drugs',
  quality: 'How far the reports can be trusted',
};
// the lines drawn while the first answer comes: the rule's, as it ships
const FIRST = {
  clinical: ['Seriousness', 'Age', 'Sex', 'Pregnancy', 'Taken for'],
  causality: ['Time to onset', 'Dechallenge', 'Rechallenge', 'Drug role', 'Dose', 'Other drugs'],
  quality: ['Reporter', 'Literature', 'Country', 'Report type', 'Key details', 'Duplicates'],
};
const GROUP_NAMES = { clinical: 'Clinical picture', causality: 'Causality', quality: 'Data quality' };
const TIPS = {
  pregnancy: "Counted from MedDRA's pregnancy terms among each case's reactions: a report that codes no pregnancy term is missed, so this undercounts.",
};

const arrow = (d) => (d >= 0 ? '▲' : '▼');
// the fields that have no value ticked (no case shows)
const noneOf = (ctx) => (ctx.filters || []).filter((f) => !f.values.length).map((f) => f.field);

// ---- a line -------------------------------------------------------------------------------------
function shownWords(line) {
  const s = line.shown;
  if (!s) return 'None given';
  if (s.pick === 'median_days') return 'Median';
  if (s.pick === 'highest_strength') return `${s.value} (highest)`;
  const named = line.values.find((v) => v.value === s.value)?.name;
  return valueWords(line, s.value, named);
}
function numbers(line) {
  const s = line.shown;
  if (!s) return { was: null, now: null, change: null };
  if (s.pick === 'median_days') {
    const now = s.window.days == null ? BLANK : `${days(s.window.days)} ${s.window.days === 1 ? 'day' : 'days'}`;
    return { was: s.before.days == null ? null : days(s.before.days), now, change: s.change, wasWords: `${days(s.before.days)} days` };
  }
  return { was: s.before.share == null ? null : pct(s.before.share), now: pct(s.window.share), change: s.change };
}

// While a line's list is open the lines say nothing on hover: the list is what the reader looks at
const said = (o, words) => (valuesOpen(o) ? `aria-label="${esc(words)}"` : tip(words));
// no case shows: a line gives nothing, and only the field with nothing ticked still opens its list
const pressable = (ctx, line) => {
  const none = noneOf(ctx);
  return !none.length || (none.length === 1 && none[0] === line.filter);
};
const pressed = (line) => `role="button" tabindex="0" aria-haspopup="menu" data-act="bd-line" data-v="${esc(line.field)}"`;

function lineHtml(o, line, why) {
  const { ctx } = o;
  const name = `<span class="oa-bd-name">${esc(line.name)}</span>`;
  if (why) {
    return `<div class="oa-bd-line" data-field="${esc(line.field)}" ${tip(`${line.name}: not available. ${why}`)}>${name}<span class="oa-bd-val oa-bd-quiet">Not available</span><span class="oa-bd-chg">${BLANK}</span><span class="oa-bd-given">${BLANK}</span></div>`;
  }
  if (ctx.none) {
    const opens = line.field !== 'duplicates' && pressable(ctx, line);
    return `<div class="oa-bd-line" data-field="${esc(line.field)}"${opens ? ` ${pressed(line)}` : ''} ${said(o, `${line.name}: no case shows, as a filter has nothing ticked.`)}>${name}<span class="oa-bd-val oa-bd-quiet">${BLANK}</span><span class="oa-bd-chg">${BLANK}</span><span class="oa-bd-given">${BLANK}</span></div>`;
  }
  if (line.field === 'duplicates') return dupsHtml(line, name);
  const hot = !!alarmOf(ctx) && !!line.alarm;
  const words = shownWords(line);
  const n = numbers(line);
  const change = n.change == null ? BLANK : `${arrow(n.change)}${Math.abs(Math.round(n.change))}`;
  const given = line.window.given_share;
  const was = n.was == null ? '' : `<span class="oa-bd-was">${esc(n.was)} →</span> `;
  const about = `${line.name}: ${words}${n.was == null ? '' : `, ${n.wasWords || n.was} before the window`}, ${n.now === BLANK ? 'none' : n.now} in the window${given == null ? '' : `, given in ${pct(given)} of the window's reports`}.${hot ? ' Past the alarm rule.' : ''}${TIPS[line.field] ? ` ${TIPS[line.field]}` : ''} ${line.filter && line.shown?.values?.length ? 'Press to filter by it and list every value.' : 'Press to list every value.'}`;
  return `<div class="oa-bd-line" data-field="${esc(line.field)}" ${pressed(line)} ${said(o, about)}>
    ${name}<span class="oa-bd-val"><span class="oa-bd-vname">${esc(words)}</span> <span class="oa-bd-nums">${was}<strong${hot ? ' data-hot="true"' : ''}>${esc(n.now)}</strong></span></span>
    <span class="oa-bd-chg"${hot ? ' data-hot="true"' : ''}>${change}</span><span class="oa-bd-given">${given == null ? BLANK : pct(given)}</span></div>`;
}
// Duplicates: how many copies the window set aside, and where they are
function dupsHtml(line, name) {
  const n = line.shown?.window?.cases;
  const words = n == null ? 'Counted, as the product is set.' : `${num(n)} left out of the window. <button type="button" class="oa-link oa-bd-tocases" data-act="ev-tab" data-v="cases">See them in Cases</button>`;
  return `<div class="oa-bd-line oa-bd-dups" data-field="duplicates">${name}<span class="oa-bd-dwords">${words}</span></div>`;
}

function groupsHtml(o) {
  const b = o.answer;
  const head = (key, title) => `<p class="oa-bd-gt"><span class="oa-bd-gtitle">${esc(title)}</span> <span class="oa-bd-gsub">${esc(ABOUT[key] || '')}</span></p><span class="oa-bd-gh">Change</span><span class="oa-bd-gh">Given in</span>`;
  // a waiting line is built as the line that comes, so it stands exactly where that will
  const waiting = (nm) => (nm === 'Duplicates'
    ? `<div class="oa-bd-line oa-bd-dups"><span class="oa-bd-name">${esc(nm)}</span><span class="oa-bd-dwords"><span class="skeleton oa-bd-dsk">0 left out of the window. See them in Cases</span></span></div>`
    : `<div class="oa-bd-line"><span class="oa-bd-name">${esc(nm)}</span><span class="oa-bd-val"><span class="skeleton oa-bd-sk">&nbsp;</span></span><span class="oa-bd-chg">&nbsp;</span><span class="oa-bd-given">&nbsp;</span></div>`);
  const groups = b ? b.groups : Object.keys(FIRST).map((group) => ({ group, name: GROUP_NAMES[group] }));
  return groups.map((g) => {
    const lines = b ? b.lines.filter((l) => l.group === g.group).map((l) => lineHtml(o, l, b.not_available?.[l.field])).join('')
      : FIRST[g.group].map(waiting).join('');
    return `<section class="oa-bd-group" data-group="${esc(g.group)}">${head(g.group, g.name)}${lines}</section>`;
  }).join('');
}

// ---- the section ---------------------------------------------------------------------------------
function paint(o) {
  const el = o.box.querySelector('.oa-bd');
  el.innerHTML = groupsHtml(o);
  if (o.waiting && o.answer) el.setAttribute('data-state', 'loading'); else el.removeAttribute('data-state');
  repaintValues(o);
}
function load(o) {
  const asked = askedOf(o.ctx);
  if (o.asked === asked) return;
  o.asked = asked;
  o.waiting = true;
  api(`/api/breakdowns?${asked}`).then((got) => {
    if (o.asked !== asked) return;
    o.answer = got;
    o.waiting = false;
    paint(o);
  }).catch(() => { if (o.asked === asked) { o.waiting = false; paint(o); } });
}

function draw(box, ctx) {
  const o = { box, ctx, asked: '', answer: null, waiting: false, paint: () => paint(o) };
  box.innerHTML = '<div class="oa-bd"></div>';
  box.querySelector('.oa-bd').breakdowns = o;
  load(o);
  paint(o);
  return {
    update(next) { o.ctx = next; load(o); paint(o); },
  };
}
overviewSection('breakdowns', { order: 1, draw });

actions({
  'bd-line': (el) => {
    const o = el.closest('.oa-bd')?.breakdowns;
    const line = o?.answer?.lines.find((l) => l.field === el.dataset.v);
    if (line) openValues(o, line, el);
  },
});
