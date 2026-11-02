/* An opened event's cases table, its columns: every field FAERS gives for a case, grouped in plain
   words and picked from a Columns menu, each person's pick kept as a view choice. The columns
   shown at first are Received, Age, Sex, Suspect drugs, Role, Dose, Taken for, Onset,
   Dechallenge, Reporter and Seriousness, with Case always first. For each column this says its
   words, its group, the explorer filter its head's Show only sets (where the explorer has one),
   and how its cell reads a case: the case list's own fields, or with detail=columns what the case
   gives about the drug (`columns_T`, casecolumns.py). event-cases.js draws the table and
   event-heads.js its heads from it. */

import { NO_ONSET, OUTCOME, REPORTER, REPT, ROLE, SEX, labelOf, noOutcome } from './codes.js';
import { countryName } from './countries.js';
import { choice } from './overlays.js';
import { keepView, viewChoice } from './state.js';
import { MONTHS, companyName, day, days, esc, fix, tip } from './util.js';

const KEPT = 'event.columns';

// Each column: its words; filter, the explorer filter its head's Show only sets; num, a column of
// numbers; tip, what its head says on hover. Its width is the stylesheet's (--ec-<id>).
export const COLUMNS = {
  received: { words: 'Received', tip: 'The day FDA first received the case' },
  event: { words: 'Event date', tip: 'When the reaction happened, as far as FDA gives it: the day, the month or the year' },
  start: { words: 'Therapy start', tip: 'When the drug was started: the earliest day, month or year the report gives' },
  stop: { words: 'Therapy stop', tip: 'When the drug was stopped: the latest day, month or year the report gives' },
  age: { words: 'Age', filter: 'age', tip: "The patient's age when the reaction happened" },
  sex: { words: 'Sex', filter: 'sex', tip: "The patient's sex" },
  weight: { words: 'Weight', num: true, tip: "The patient's weight, in kilograms" },
  country: { words: 'Country', filter: 'country', many: true, tip: 'Where it happened, else the country of the person who reported it' },
  drugs: { words: 'Suspect drugs', filter: 'other_drug', many: true, tip: 'The drug first with its role, then the other suspect drugs' },
  // the drug's role in the case; its filter is the roles the page counts the drug in
  role: { words: 'Role', filter: 'prole', tip: "The drug's role in the case" },
  dose: { words: 'Dose', filter: 'dose', many: true, tip: "The drug's dose, as the report writes it" },
  route: { words: 'Route', filter: 'route', many: true, tip: 'How the drug was given, as the report writes it' },
  dose_form: { words: 'Dose form', filter: 'dose_form', many: true, tip: "The drug's dose form, as the report writes it" },
  indication: { words: 'Taken for', filter: 'indication', many: true, tip: 'What the drug was taken for, as the report says' },
  lot: { words: 'Lot', filter: 'lot', many: true, tip: "The drug's lot number" },
  onset: { words: 'Onset', filter: 'onset', num: true, tip: 'Days from starting the drug to the event' },
  dechal: { words: 'Dechallenge', filter: 'dechal', tip: 'Whether the reaction abated when the drug was stopped' },
  rechal: { words: 'Rechallenge', filter: 'rechal', tip: 'Whether the reaction came back when the drug was restarted' },
  reporter: { words: 'Reporter', filter: 'reporter', tip: 'Who reported the case' },
  report_type: { words: 'Report type', filter: 'report_type', tip: 'How the report came to FDA: expedited or periodic from a company, or direct' },
  company: { words: 'Company', tip: 'The company that sent the report, or sent straight to FDA' },
  reactions: { words: 'Other reactions', filter: 'other_reaction', many: true, tip: "The case's reactions besides this event" },
  outcome: { words: 'Seriousness', filter: 'outcome', tip: 'The seriousness criteria FDA gives for the case' },
};
// the menu's groups, in plain words, and their columns in its order
export const GROUPS = [
  ['Dates', ['received', 'event', 'start', 'stop']],
  ['Patient', ['age', 'sex', 'weight', 'country']],
  ['Drugs', ['drugs', 'role', 'dose', 'route', 'dose_form', 'indication', 'lot']],
  ['Course', ['onset', 'dechal', 'rechal', 'outcome']],
  ['Report', ['reporter', 'report_type', 'company', 'reactions']],
];
// the table's order: the groups', Seriousness kept last
const ORDER = [...GROUPS.flatMap(([, ids]) => ids).filter((id) => id !== 'outcome'), 'outcome'];
const DEFAULT = ['received', 'age', 'sex', 'drugs', 'role', 'dose', 'indication', 'onset', 'dechal', 'reporter', 'outcome'];

// the columns shown, in the table's order (Case always first, and not among them)
export const shownColumns = () => {
  const on = viewChoice(KEPT, null);
  return ORDER.filter((id) => (Array.isArray(on) ? on : DEFAULT).includes(id));
};
export const changedColumns = () => {
  const on = shownColumns();
  return on.length !== DEFAULT.length || on.some((id) => !DEFAULT.includes(id));
};
export function flipColumn(id) {
  const on = shownColumns();
  keepView(KEPT, on.includes(id) ? on.filter((x) => x !== id) : ORDER.filter((x) => x === id || on.includes(x)));
}
// the table's least width: Case's and its columns' widths, each a variable the stylesheet sets, so
// the frame scrolls inside once they pass its width
export const tableWidth = () => `calc(${['case', ...shownColumns()].map((id) => `var(--ec-${id})`).join(' + ')})`;

export function columnsMenu() {
  const on = shownColumns();
  return `<p class="menu-heading">Show as columns</p>
    <div class="oa-ec-colgroups">${GROUPS.map(([words, ids]) => `<div class="oa-ec-colgroup"><p class="menu-heading">${esc(words)}</p>
      <div class="oa-choices">${ids.map((id) => choice(on.includes(id), COLUMNS[id].words, null, `data-act="ec-col" data-v="${id}"`)).join('')}</div></div>`).join('')}</div>
    <p class="menu-footnote">Case always shows. Your columns are kept in this browser.</p>`;
}

// ---- the cells ---------------------------------------------------------------------------------

export const faint = (words, hint) => `<span class="oa-faint"${hint ? ` ${tip(hint)}` : ''}>${esc(words)}</span>`;
export const NOT_GIVEN = faint('Not given');
const DECHAL_WORDS = { Y: ['Positive', 'The reaction abated when the drug was stopped'], N: ['Negative', 'The reaction did not abate when the drug was stopped'], D: ['Does not apply', 'FDA: does not apply'] };
const RECHAL_WORDS = { Y: ['Positive', 'The reaction came back when the drug was restarted'], N: ['Negative', 'The reaction did not come back when the drug was restarted'], D: ['Does not apply', 'FDA: does not apply'] };
// a report type in a word, its whole name on hover (FDA's rept_cod)
const REPORT_SHORT = { EXP: 'Expedited', PER: 'Periodic', DIR: 'Direct', '5DAY': '5-day', '30DAY': '30-day' };
const SHORT_REPORTER = { 5: 'Consumer' };
const roleTag = (r) => `<span class="oa-class-tag oa-ec-role" ${tip(ROLE[r] || r)}>${esc(r)}</span>`;

// a date as far as FDA gives it, as the table writes a day (04-Jan-2004): Jan-2004 for a month, 2004 for a year
function knownDay(iso, prec) {
  if (!iso || !prec) return '';
  const [y, m] = String(iso).split('-');
  if (prec === 8) return day(iso);
  return prec === 6 ? `${MONTHS[+m - 1]}-${y}` : y;
}
function dated(iso, prec, what) {
  const words = knownDay(iso, prec);
  if (!words) return NOT_GIVEN;
  return prec === 8 ? words : `<span ${tip(`FDA gives ${what} only to the ${prec === 6 ? 'month' : 'year'}`)}>${words}</span>`;
}
// a list of values: the first two, the rest in a tip
function listCell(values, sep = ', ') {
  if (!values?.length) return NOT_GIVEN;
  const rest = values.slice(2);
  return values.slice(0, 2).map(esc).join(sep) + (rest.length ? ` <span class="oa-more" ${tip(rest.join(sep))}>+${rest.length}</span>` : '');
}
function coded(words, code) {
  if (code === 'U') return faint('Unknown', 'FDA: unknown');
  return words[code] ? `<span ${tip(words[code][1])}>${words[code][0]}</span>` : NOT_GIVEN;
}
const ageText = (c) => (c.age_years_T == null ? '' : c.age_years_T < 2 ? `${Math.round(c.age_years_T * 12)} mo` : `${Math.floor(c.age_years_T)}`);
// the case's partial event date's first day, from FDA's yyyymmdd as written: 2010-03-01 for 201003
function eventFirst(c) {
  const r = String(c.event_dt || '');
  if (c.event_dt_prec_T === 6) return `${r.slice(0, 4)}-${r.slice(4, 6)}-01`;
  if (c.event_dt_prec_T === 4) return `${r.slice(0, 4)}-01-01`;
  return c.event_dt_T || '';
}

// the drug first with its role, then up to two other suspects; the rest in a tip
function drugsCell(own) {
  const all = own.suspects || [];
  const mine = all.filter((s) => s[2]);
  const shown = all.slice(0, mine.length + 2), rest = all.slice(shown.length);
  // a combination's name may wrap after its backslash (SACUBITRIL\ VALSARTAN), never inside an ingredient
  return shown.map(([name, role]) => `${esc(name).replaceAll('\\', '\\<wbr>')}&nbsp;${roleTag(role)}`).join(', ')
    + (rest.length ? ` <span class="oa-more" ${tip(rest.map(([name, role]) => `${name} ${role}`).join(', '))}>+${rest.length}</span>` : '');
}

// The cell of column `id` for case `c`: its html and its class
export function cellOf(id, c) {
  const own = c.columns_T || {};
  switch (id) {
    case 'received': return [day(c.group_first_dt_T), 'oa-ec-nowrap'];
    case 'event': return [dated(eventFirst(c), c.event_dt_prec_T, 'the event date'), 'oa-ec-nowrap'];
    case 'start': case 'stop': return [own[id] ? dated(own[id][0], own[id][1], `the therapy ${id}`) : NOT_GIVEN, 'oa-ec-nowrap'];
    case 'age': { const a = ageText(c); return [a ? esc(a) : NOT_GIVEN]; }
    case 'sex': return [c.sex_T ? `<span ${tip(labelOf(SEX, c.sex_T))}>${esc(c.sex_T)}</span>` : NOT_GIVEN];
    case 'weight': return [c.wt_kg_T == null ? NOT_GIVEN : `${fix(c.wt_kg_T, 1)} kg`, 'oa-num'];
    case 'country': return [c.country_T ? esc(countryName(c.country_T)) : NOT_GIVEN];
    case 'drugs': return [own.suspects?.length ? drugsCell(own) : NOT_GIVEN];
    case 'role': return [own.role ? `<span ${tip(ROLE[own.role] || own.role)}>${esc(own.role)}</span>` : NOT_GIVEN];
    case 'dose': return [listCell(own.dose, '; ')]; // a dose's own words hold commas (50 MG, BID)
    case 'route': case 'dose_form': case 'indication': case 'lot': return [listCell(own[id])];
    case 'onset': {
      if (own.onset != null) return [`<span ${tip('Days from the first dose, day 1, to the event')}>${days(own.onset)}</span>`, 'oa-num'];
      const why = NO_ONSET[own.onset_why];
      return [why ? faint('Not given', why[1]) : NOT_GIVEN, 'oa-num'];
    }
    case 'dechal': return [coded(DECHAL_WORDS, own.dechal)];
    case 'rechal': return [coded(RECHAL_WORDS, own.rechal)];
    case 'reporter': {
      const r = c.reporter_type_T;
      if (!r) return [NOT_GIVEN];
      return [`<span ${SHORT_REPORTER[r] ? tip(labelOf(REPORTER, r)) : ''}>${esc(SHORT_REPORTER[r] || labelOf(REPORTER, r))}</span>`];
    }
    case 'report_type': return [c.rept_cod ? `<span ${tip(REPT[c.rept_cod] || c.rept_cod)}>${esc(REPORT_SHORT[c.rept_cod] || c.rept_cod)}</span>` : NOT_GIVEN];
    case 'company': return [c.direct_T ? esc(companyName('_direct')) : c.company_T ? esc(c.company_T) : NOT_GIVEN];
    case 'reactions': return [own.other_reaction?.length ? listCell(own.other_reaction) : faint('None other')];
    case 'outcome': return [c.outcomes_T?.length ? esc(c.outcomes_T.map((o) => labelOf(OUTCOME, o)).join(', ')) : faint('Not given', noOutcome(c.rept_cod))];
    default: return [''];
  }
}
