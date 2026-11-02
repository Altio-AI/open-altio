/* An opened event's question in words, for its cases' export: the window and the day it counts by,
   each filter the event narrows by, and whether probable duplicates are in. */

import { NONE, OUTCOME, REPORTER, ROLE, SEX, labelOf } from './codes.js';
import { countryName } from './countries.js';
import { ages } from './state.js';
import { companyName, day } from './util.js';

const LABELS = { sex: 'Sex', age: 'Age', country: 'Country', outcome: 'Outcome', reporter: 'Who reported', sender: 'Company', prole: 'Roles' };
const WORDS = {
  sex: (v) => labelOf(SEX, v),
  age: (v) => (v === NONE ? 'Not given' : ages()[v] || v),
  country: (v) => (v === NONE ? 'Not given' : countryName(v)),
  outcome: (v) => labelOf(OUTCOME, v),
  reporter: (v) => labelOf(REPORTER, v),
  sender: (v) => companyName(v),
  prole: (v) => `${v} (${ROLE[v] || v})`,
};

// [label, words] for each part of the pane's question past its drug and event
export function filterLines(P) {
  const w = P.ctx.window || {};
  const from = w.received_from || w.event_from, to = w.received_to || w.event_to;
  const by = P.ctx.dateField === 'event' ? 'the day the event happened' : 'the day FDA received the case';
  const lines = from || to ? [['Window', `${from ? day(from) : 'The start'} to ${to ? day(to) : 'the end'}, by ${by}`]] : [];
  for (const f of P.filters) if (LABELS[f.field]) lines.push([LABELS[f.field], f.values.map(WORDS[f.field]).join(', ')]);
  lines.push(['Duplicates', P.dedupAll() ? 'Included, flagged' : 'Left out']);
  return lines;
}
