/* What an opened event's breakdown lines read, for the lines (event-breakdowns.js), the list a line
   opens (event-breakdowns-menu.js) and + Add a filter (event-fields.js): the question as
   /api/breakdowns is asked, each value of a line in words, and a line's values as its list shows them. */

import { NONE, OUTCOME, REPORTER, ROLE, SEX } from './codes.js';
import { countryName } from './countries.js';
import { ages } from './state.js';
import { num } from './util.js';

const CHALLENGE = { Y: 'Positive', N: 'Negative', D: 'Does not apply' };
const REPORT_TYPE = { EXP: 'Expedited', PER: 'Periodic', DIR: 'Direct', '5DAY': '5-day', '30DAY': '30-day' };
const COUNTS = ['none', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
// the order a list reads in, where its field has one
const ORDER = { seriousness: Object.keys(OUTCOME), role: Object.keys(ROLE), dechal: ['Y', 'N', 'D'], rechal: ['Y', 'N', 'D'] };

// a number there is none of
export const BLANK = '–';
export const pct = (v) => (v == null ? BLANK : v > 0 && v < 0.01 ? 'under 1%' : `${Math.round(100 * v)}%`);
export const days = (v) => (v == null ? BLANK : Number.isInteger(v) ? num(v) : v.toFixed(1));
const bandLabel = (id) => ages()[id] || id;

// A value of a line in words: FDA's codes and Open Altio's bands as the explorer names them, a
// value the page cannot name from a code by the words the answer gives (`named`)
export function valueWords(line, value, named = null) {
  if (value === NONE) {
    return { other_drugs: 'No other drug', literature: 'Cites no article' }[line.field] || 'Not given';
  }
  switch (line.field) {
    case 'seriousness': return value === 'serious' ? 'Any serious outcome' : OUTCOME[value] || value;
    case 'age': return { children: 'Children', older: 'Older people' }[value] || bandLabel(value);
    case 'sex': return SEX[value] || value;
    case 'pregnancy': return value === 'yes' ? 'In a pregnancy' : 'No pregnancy term';
    case 'dechal': case 'rechal': return CHALLENGE[value] || value;
    case 'role': return ROLE[value] || value;
    case 'reporter': return { health_professionals: 'Health professional', lawyers: 'Lawyer' }[value] || REPORTER[value] || value;
    case 'literature': return value === 'cites' ? 'Cites an article' : value;
    case 'country': return countryName(value);
    case 'report_type': return REPORT_TYPE[value] || value;
    case 'key_details': {
      const all = line.shown?.pick === 'all_given' ? line.shown.value : null;
      return all != null && +value === all ? `All ${COUNTS[all] || all} given` : `${value} of ${all ?? '?'} given`;
    }
    case 'onset': return `${days(value)} ${value === 1 ? 'day' : 'days'}`;
    default: return named || String(value);
  }
}

// the words each filter's value came with, where no code names it, as a line's values came
const said = new Map();
export const wordsOf = (filter, value) => said.get(`${filter}|${value}`);

// The event's question as /api/breakdowns is asked: its settings, filters and window, the period
// before it, its reactions, and a host's points and strengths; `without` leaves a filter out
export const alarmOf = (ctx) => (ctx.screens || []).find((s) => s?.breakdowns)?.breakdowns || null;
export function askedOf(ctx, without = '') {
  const p = new URLSearchParams(ctx.query({}, { without }));
  for (const [k, v] of Object.entries(ctx.before || {})) if (v) p.set(k, v);
  const alarm = alarmOf(ctx);
  if (alarm?.points != null) p.set('points', alarm.points);
  for (const s of alarm?.strength || []) p.append('strength', s);
  for (const [k, v] of [...p]) if (v === '') p.delete(k);
  return `${p}&${ctx.reaction.map((r) => `reaction=${encodeURIComponent(r)}`).join('&')}`;
}

// the reports that do not give the field, where FAERS has one and some do not
function notGiven(line) {
  if (line.window.given_share == null && line.before.given_share == null) return [];
  const [now, before] = [line.window.cases - line.window.given, line.before.cases - line.before.given];
  return now || before ? [{ value: NONE, words: 'Not given', now, before, note: '' }] : [];
}
// Each value of the line as its list shows it, Not given last: { value (the filter's), words, now,
// before, note (its shares before the window and in it) }
export function rowsOf(line) {
  const note = (v) => (v.before.share == null && v.window.share == null ? '' : `${pct(v.before.share)} → ${pct(v.window.share)}`);
  const row = (v, words) => ({ value: String(v.value), words, now: v.window.cases, before: v.before.cases, note: note(v) });
  let rows;
  if (line.field === 'onset') rows = [...(line.bands || []).map((b) => row(b, b.name)), ...notGiven(line)];
  else {
    let values = line.values.filter((v) => !(line.field === 'seriousness' && v.value === 'serious'));
    const order = line.field === 'age' ? Object.keys(ages()) : ORDER[line.field];
    if (order) values = order.flatMap((k) => values.filter((v) => v.value === k)).concat(values.filter((v) => !order.includes(v.value)));
    values = [...values.filter((v) => v.value !== NONE), ...values.filter((v) => v.value === NONE)];
    rows = values.map((v) => row(v, valueWords(line, v.value, v.name)));
    // what the line can show and each seriousness criterion stay in the list when no case gives them
    const absent = [...new Set([...shownValues(line), ...(line.field === 'seriousness' ? Object.keys(OUTCOME) : [])])]
      .filter((v) => v !== NONE && !rows.some((r) => r.value === v))
      .map((v) => ({ value: v, words: valueWords(line, v), now: 0, before: 0, note: '' }));
    const given = [...rows.filter((r) => r.value !== NONE), ...absent];
    if (order) given.sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value));
    rows = [...given, ...rows.filter((r) => r.value === NONE)];
    if (!values.some((v) => v.value === NONE)) rows.push(...notGiven(line));
  }
  if (line.filter) for (const r of rows) said.set(`${line.filter}|${r.value}`, r.words);
  return rows;
}

// the filter's values that pick the value the line shows; none where it shows no value of its filter
export const shownValues = (line) => (line.filter ? (line.shown?.values || []).map(String) : []);
