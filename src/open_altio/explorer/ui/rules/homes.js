/* Where each rule lives on the methods page: every rule acts in one box of the story, and that box
   holds it. Closed, a box says how many of its rules can be changed and how many are fixed;
   opened, it shows its finding, then "You can change" (each rule with its switch and what Off
   changes) and "Fixed" (each with why), each opening to its Why card, then the findings measured
   there and left as FDA wrote them. There is no list of rules apart from the boxes: a test opens
   every box and finds each rule of /api/rules in exactly one. */

import { dialog } from '../overlays.js';
import { esc, num } from '../util.js';
import { changeable, docRow, group, ruleRow, showsRead, threeLines, whyCard } from './rows.js';

// each box and the rules that act there, the story's order
export const HOME = {
  report_versions: ['transformed-suffix-T', 'overlong-lines'],
  latest_versions: ['latest-version'],
  after_deleted_lists: ['deleted-cases'],
  kept_after_duplicates: ['dedup-default', 'dup-manufacturer-number', 'dup-padded-event-dates', 'dup-shown-copy', 'reaction-term-case'],
  dates: ['event-date-precision', 'date-limits', 'time-to-onset', 'therapy-duration'],
  demographics: ['age-in-years', 'age-bands', 'sex-codes', 'weight-in-kg', 'legacy-country', 'country-not-given', 'eu-member-state'],
  senders: ['reporter-type', 'company-names'],
  empty_fields: ['not-given', 'no-drug-or-reaction'],
  drug_names: ['drug-names'],
  rxnorm: ['rxnorm-ingredients'],
  a_cases: ['explorer-drug-counts'],
  routes: ['drug-route'],
  labels: ['label-source', 'label-choice', 'label-sections', 'label-own-ingredients'],
  a_flags: ['label-flags', 'label-dictionary', 'label-negation', 'label-population', 'label-table-rows', 'label-umbrella', 'label-treated-disease', 'label-not-a-medical-event', 'label-procedure', 'label-coding', 'label-groups'],
  classes: ['atc-index', 'atc-spelling-bridges', 'atc-group-classes', 'atc-class-choice', 'statistics-classes'],
  terms: ['meddra-terms', 'legacy-term-spelling', 'meddra-version'],
  pairs: ['statistics-cases'],
  a_stats: ['ebgm', 'prr', 'ror', 'rrr', 'ic', 'ror-strata'],
};
// the findings measured and left as FDA wrote them, in the box they are about
const DOCS = {
  kept_after_duplicates: ['duplicate_check_needs_fields'],
  dates: ['drug_seq_repeated'],
  demographics: ['ages_without_a_unit', 'sex_not_specified_for_empty', 'country_empty_rising'],
  senders: ['sender_names_unstable', 'rept_cod_combination_products'],
  empty_fields: ['no_outcome_not_non_serious', 'no_adverse_event_serious_outcome', 'unknown_indication_placeholder'],
};
export const homeOf = Object.fromEntries(Object.entries(HOME).flatMap(([id, names]) => names.map((n) => [n, id])));
// the rules of a box this release and this view have
export const listed = (ctx, id) => (HOME[id] || []).map((n) => ctx.R.find((r) => r.name === n)).filter(Boolean);

// the quiet line on a closed box: what can be changed there, and what is fixed
export function rulesMark(ctx, id) {
  const rs = listed(ctx, id);
  if (!rs.length) return '';
  const can = rs.filter(changeable).length;
  const fixed = rs.length - can;
  const rules = (k) => `rule${k === 1 ? '' : 's'}`;
  const words = [
    can && (ctx.local ? `${num(can)} ${rules(can)} you can change` : `${num(can)} ${rules(can)} can be changed`),
    fixed && `${num(fixed)}${can ? '' : ` ${rules(fixed)}`} fixed`,
  ].filter(Boolean).join(' · ');
  return `<span class="oa-m-rules-mark">${words}</span>`;
}

// the Why card at the top of an opened box: its finding, else its own card
function topCard(ctx, S, id) {
  const t = S.ITEMS[id];
  const found = t.why && ctx.M.insights.find((c) => c.id === t.why);
  if (found) return { html: whyCard(found, 'h3'), shown: [found.id] };
  if (!t.title || !t.chart) return { html: '', shown: [] };
  const rule = ctx.R.find((r) => r.name === t.rule);
  const did = rule ? `<a class="oa-m-did" href="${esc(ctx.link(rule.file))}" target="_blank" rel="noopener">${esc(t.did)}</a>` : esc(t.did);
  return { html: `<div class="oa-evidence oa-m-card"><h3 class="oa-claim oa-m-title">${esc(t.title)}</h3>${t.chart}${threeLines({ ...t, shows: showsRead(t.shows, t.guide) }, did)}</div>`, shown: [] };
}

// a box's rules: what you can change, then what is fixed, then what was measured and left alone
function boxRules(ctx, id, shown) {
  const rs = listed(ctx, id);
  const can = rs.filter(changeable);
  const fixed = rs.filter((r) => !changeable(r));
  ctx.shownAbove = new Set(shown);
  const list = (rules) => `<ul class="oa-rule-list">${rules.map((r) => ruleRow(r, ctx, false)).join('')}</ul>`;
  const section = (title, body) => `<section class="oa-m-rules-group"><h3 class="oa-card-sub">${title}</h3>${body}</section>`;
  // a step with one switch for all its rules (WHO's drug classes) shows it in its head
  const step = can[0]?.step;
  const oneSwitch = step?.switch && can.every((r) => r.step.id === step.id);
  const canBody = oneSwitch ? group(step.id, null, step.title, step.sentence, can, ctx, new Set()) : list(can);
  const carded = new Set(rs.flatMap((r) => ctx.cardsFor(r.name).map((c) => c.id)));
  const docs = (DOCS[id] || []).filter((c) => !shown.includes(c) && !carded.has(c)).map((c) => ctx.M.insights.find((x) => x.id === c)).filter(Boolean);
  return [
    can.length ? section(ctx.local ? 'You can change' : 'On your own copy, you can change', canBody) : '',
    fixed.length ? section('Fixed', list(fixed)) : '',
    docs.length ? section('Measured and left as FDA wrote it', `<ul class="oa-rule-list">${docs.map((c) => docRow(c)).join('')}</ul>`) : '',
  ].join('');
}

// a box opened in a dialog: its finding and its rules; the Rebuild bar comes with it while it is open
export function openBox(ctx, S, id, onClose) {
  const top = topCard(ctx, S, id);
  const dlg = dialog(esc(S.ITEMS[id].name), `${top.html}${boxRules(ctx, id, top.shown)}`);
  dlg.classList.add('oa-m-dialog');
  dlg.dataset.box = id;
  const bar = document.getElementById('oa-rebuild');
  if (bar) dlg.append(bar);
  // closed, the bar goes back to the foot of the page
  dlg.addEventListener('close', () => { if (bar) document.querySelector('.oa-m-page')?.append(bar); onClose(); });
  return dlg;
}
