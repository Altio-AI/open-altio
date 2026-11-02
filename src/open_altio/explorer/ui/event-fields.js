/* The fields of an opened event's + Add a filter (event-filters.js) that read what the drug's records
   give and the report, beyond the case's own fields: each with its words, the heading over its values,
   how a value reads, and where its values and their counts in the window come from. A field with a
   breakdown line lists its line's values (event-breakdowns-menu.js), counted under the event's other
   filters, the onset in its bands; Route, Dose form and Lot are counted by /api/count; Other reactions
   are the case's reactions besides the event's own, counted by event. */

import { NONE } from './codes.js';
import { api } from './server.js';
import { askedOf, rowsOf, wordsOf } from './event-breakdowns-values.js';

// the words the answers gave a value that has no code to name it by, as a field's values came
const names = new Map();
const said = (id) => (v) => (v === NONE ? 'Not given' : wordsOf(id, v) || names.get(`${id}|${v}`) || v);
const kept = (id, rows) => rows.map(([v, n, words]) => { names.set(`${id}|${v}`, words); return [v, n]; });

// a field with a breakdown line: the line's values in the window, each by its filter's value
const fromLine = (field) => async (ev, id) => {
  const got = await api(`/api/breakdowns?${askedOf(ev.context(), id)}`);
  const line = got.lines.find((l) => l.field === field);
  return line ? rowsOf(line).map((r) => [r.value, r.now]) : [];
};
// counted by the field itself (rule counted-question)
const counted = async (ev, id) => {
  const got = await api(`/api/count?by=${id}&${ev.queryWithout(id)}&${ev.reactionsAs('pt')}`);
  return kept(id, got.counts.map(([v, n]) => [v ?? NONE, n, v ?? 'Not given']));
};
// each reaction the cases name besides the event's own
const otherReactions = async (ev, id) => {
  const got = await api(`/api/count?by=event&${ev.queryWithout(id)}&${ev.reactionsAs('pt')}`);
  const own = new Set(ev.reactions.map((r) => r.toLowerCase()));
  return kept(id, got.counts.filter(([v]) => v && !own.has(v.toLowerCase())).map(([v, n]) => [v, n, v]));
};

export const MORE_FIELDS = {
  other_drug: { words: 'Other drugs', heading: 'Show the cases where another drug is', name: said('other_drug'), values: fromLine('other_drugs') },
  dose: { words: 'Dose', heading: 'Show the cases whose dose is', name: said('dose'), values: fromLine('dose') },
  route: { words: 'Route', heading: 'Show the cases where the drug was given', name: said('route'), values: counted },
  dose_form: { words: 'Dose form', heading: 'Show the cases whose dose form is', name: said('dose_form'), values: counted },
  indication: { words: 'Taken for', heading: 'Show the cases where the drug was taken for', name: said('indication'), values: fromLine('indication') },
  lot: { words: 'Lot', heading: 'Show the cases whose lot is', name: said('lot'), values: counted },
  onset: { words: 'Onset', heading: 'Show the cases whose onset is', name: said('onset'), values: fromLine('onset') },
  dechal: { words: 'Dechallenge', heading: 'Show the cases whose dechallenge is', name: said('dechal'), values: fromLine('dechal') },
  rechal: { words: 'Rechallenge', heading: 'Show the cases whose rechallenge is', name: said('rechal'), values: fromLine('rechal') },
  report_type: { words: 'Report type', heading: 'Show the cases sent as', name: said('report_type'), values: fromLine('report_type') },
  other_reaction: { words: 'Other reactions', heading: 'Show the cases that also report', name: said('other_reaction'), values: otherReactions },
};
