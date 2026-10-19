/* A rule's row on the methods page, closed and opened. Closed: its title and line, then on a rule
   you can change what switching it off would change, in numbers, and on one nobody changes why.
   Opened, in three parts: the decision (what it is set to, its values), the why (each finding as a
   card: claim, how to read it, the chart, Shows / Why it matters / What we did) and a quiet foot
   (what it moved, the rule file, the code). Counts come from the release's methods.json (and, for
   a release built with someone's rules, Altio's own beside them); each rule's words and values
   from the rulebook. On a person's own copy each rule has its switch and its values are set in
   the open row; elsewhere the page only reads. A step with one switch for all its rules, WHO's
   drug classes, has it in its group's head; the API leaves the classes out wherever they are not
   shown. */

import { icon } from '../icons.js';
import { esc, num, tip } from '../util.js';
import { andList } from './charts.js';
import { anyChoice, fromApi, isOn, same, summary, valueIn } from './choices.js';
import { CARD_WORDS, DRUG_LINE, RULE_WORDS, SHARED_CHART } from './words.js';

const IN_ALTIO = "In Altio's standard release";
const outLink = (href, words) => `<a class="oa-rule-link" href="${esc(href)}" target="_blank" rel="noopener">${words}${icon('external')}</a>`;

function countsOf(M, release) {
  const d = M.funnel.duplicates || {};
  return {
    steps: Object.fromEntries(M.steps.map((s) => [s.id, { after: s.after.total, removed: s.removed?.total ?? null, afterEras: s.after, removedEras: s.removed }])),
    aeolus: d.set_aside_by_rule?.aeolus,
    mfr: d.set_aside_by_rule?.manufacturer_number,
    paddedGroups: d.padded_date_groups?.groups,
    paddedCases: d.padded_date_groups?.cases,
    notCompared: d.not_compared_by_aeolus,
    dupCases: d.cases,
    listed: M.funnel.deleted_lists?.caseids_listed,
    split: release.split_lines.length,
  };
}

// What the page works from: the /api/rules answer, the counts of this build and of Altio's
// standard one, and the choices the release was built with and those set since.
export function rulesContext(data) {
  const M = data.methods;
  const built = fromApi(data.built);
  const C = countsOf(M, data.release);
  const ex = anyChoice(built) && !!data.standard; // Altio's counts go beside this build's
  const A = ex ? countsOf(data.standard, data.release) : C;
  // the drug classes' cards are tagged documented; the API names the rule they are evidence for
  const classEvidence = data.classes?.evidence || {};
  // a rule's charts: the cards that name it (each card's `rules`, or a changed step's tag in a
  // release built before cards named every rule), and the classes' evidence
  const cardsFor = (name) => M.insights.filter((c) => (c.rules || c.tag.rules || []).includes(name) || (classEvidence[name] || []).includes(c.id));
  const link = (path) => `${M.code.repository}/blob/${M.code.ref}/${path}`;
  const R = [...data.rules, ...(data.named || []).map((r) => ({ ...r, named: true, always_on: true, values: [], step: {} }))];
  return { data, M, R, C, A, ex, built, pending: fromApi(data.saved ?? data.built), local: !!data.editable, cardsFor, link, numbers: M.numbers || {} };
}

const eraTip = (e) => (e ? tip(`AERS ${num(e.legacy)} · FAERS ${num(e.faers)}`) : '');
// Altio's number beside this build's, only for a release built with someone's rules, where they differ
const altioNote = (mine, altio, ex, unit = '') => (ex && mine !== altio ? ` <span class="oa-fda" ${tip(IN_ALTIO)}>Altio: ${num(altio)}${unit}</span>` : '');
const movedNum = (mine, altio, ex, unit) => (ex && mine === 0 && altio ? `<span class="oa-faint">None</span>${altioNote(mine, altio, ex, ` ${unit}`)}` : `${num(mine)} ${unit}${altioNote(mine, altio, ex)}`);
const both = (mine, altio, ex) => `${num(mine)}${altioNote(mine, altio, ex)}`;
const pct = (a, b) => (b ? `${((100 * a) / b).toFixed(1)}%` : '');

// a drug class rule: what the release's classes count, in cases; none when built without them
function classesMoved(rule, cls) {
  if (!cls.present) return { text: 'Not built', tip: 'This release was built without the drug classes' };
  const c = cls.cases;
  if (c && rule.name === 'atc-index') return { text: `${num(c.with_a_coded_drug)} cases`, tip: 'Cases naming a drug WHO classes, each counted once' };
  if (c && rule.name === 'atc-class-choice') return { text: `${num(c.with_a_class)} with a class`, tip: 'Cases with a class, exact or broader, for at least one drug' };
  return null;
}

function classesFacts(rule, cls) {
  const c = cls.cases;
  if (!cls.present || !c) return [];
  if (rule.name === 'atc-index') return [
    ["WHO's index", esc(cls.index_year)],
    ['Cases naming a drug WHO classes', num(c.with_a_coded_drug)],
  ];
  if (rule.name === 'atc-class-choice') return [
    ['With a class for at least one drug', num(c.with_a_class)],
    ['With a drug given the class its uses share', num(c.with_a_shared_class)],
    ["With a drug whose class can't be told", num(c.with_cannot_tell)],
  ];
  return [];
}

// what a rule moved in this release, from the counts methods.json carries for it
function movedFor(rule, ctx) {
  const { C, A, M, ex, data } = ctx;
  if (rule.step.id === data.classes?.step) return classesMoved(rule, data.classes);
  const bothTip = 'Cases this rule grouped and set aside; a case both duplicate rules grouped counts under both';
  // a statistic is worked out from the cases, so it has nothing to count as taken out
  if (rule.step.id === 'statistics') return { text: 'No case removed', tip: 'It works numbers out and takes no case out' };
  switch (rule.name) {
    case 'transformed-suffix-T': return { text: 'None changed', tip: M.limits.find((l) => l.id === 'no_values_changed')?.text };
    case 'overlong-lines': return { text: `${num(C.split)} line${C.split === 1 ? '' : 's'} split`, tip: `FDA's ${andList(data.release.split_lines.map((x) => `${x.table.toUpperCase()} ${x.quarter.toUpperCase()}`))} file${C.split === 1 ? '' : 's'}, one line each` };
    case 'latest-version': return { html: movedNum(C.steps.latest_versions.removed, A.steps.latest_versions.removed, ex, 'earlier versions'), tipAttr: eraTip(!ex && C.steps.latest_versions.removedEras) };
    case 'deleted-cases': return { html: movedNum(C.steps.after_deleted_lists.removed, A.steps.after_deleted_lists.removed, ex, 'cases'), tipAttr: eraTip(!ex && C.steps.after_deleted_lists.removedEras) };
    case 'dedup-default': return { html: movedNum(C.aeolus, A.aeolus, ex, 'set aside'), tip: bothTip };
    case 'dup-manufacturer-number': return { html: movedNum(C.mfr, A.mfr, ex, 'set aside'), tip: bothTip };
    case 'dup-padded-event-dates': return { html: movedNum(C.paddedCases, A.paddedCases, ex, 'kept'), tip: `Cases in the ${num(C.paddedGroups)} groups this rule keeps whole, so none of them is set aside for its date` };
    case 'meddra-terms': return data.meddra ? { text: `MedDRA ${data.meddra.version}`, tip: 'The MedDRA version this release counts its reactions in' } : { text: 'No MedDRA', tip: "This release holds no MedDRA, so reactions are counted by FDA's text" };
    default: return null;
  }
}

function factsFor(rule, ctx) {
  const { C, A, ex, data } = ctx;
  if (rule.step.id === data.classes?.step) return classesFacts(rule, data.classes);
  const s = (id) => C.steps[id];
  const a = (id) => A.steps[id];
  switch (rule.name) {
    case 'overlong-lines': return [['Lines split back into two reports', num(C.split)]];
    case 'latest-version': return [
      ['Report versions FDA published', both(s('report_versions').after, a('report_versions').after, ex)],
      ['Earlier versions set aside', both(s('latest_versions').removed, a('latest_versions').removed, ex)],
      ['Cases, one version each', both(s('latest_versions').after, a('latest_versions').after, ex)],
    ];
    case 'deleted-cases': return [
      ["Cases on FDA's lists", num(C.listed)],
      ['Taken out of this release', both(s('after_deleted_lists').removed, a('after_deleted_lists').removed, ex)],
      ['Cases left', both(s('after_deleted_lists').after, a('after_deleted_lists').after, ex)],
    ];
    case 'dedup-default': return [
      ['Cases looked at', both(C.dupCases, A.dupCases, ex)],
      ['Set aside by this rule', both(C.aeolus, A.aeolus, ex)],
      ['Could not be checked: a detail is missing', `${both(C.notCompared, A.notCompared, ex)} <span class="oa-faint" ${tip('Of the cases looked at')}>${pct(C.notCompared, C.dupCases)}</span>`],
    ];
    case 'dup-manufacturer-number': return [
      ['Set aside by this rule', both(C.mfr, A.mfr, ex)],
      ['Set aside by either duplicate rule', both(s('kept_after_duplicates').removed, a('kept_after_duplicates').removed, ex)],
    ];
    case 'dup-padded-event-dates': return [
      ['Groups kept whole', both(C.paddedGroups, A.paddedGroups, ex)],
      ['Cases in them', both(C.paddedCases, A.paddedCases, ex)],
    ];
    case 'meddra-terms': {
      const m = data.meddra;
      if (!m) return [['MedDRA version', "None: reactions are counted by FDA's text"]];
      const free = m.free_text_indications;
      return [
        ['MedDRA version', esc(m.version)],
        ['Reactions counted', 'Each under its current PT'],
        ['A term MedDRA later split', 'Older reports stay under the term they were coded in: search with the SMQ to find them all'],
        ['Indications of free text', `${num(free.rows)} ${free.rows === 1 ? 'row' : 'rows'} (${num(free.texts)} ${free.texts === 1 ? 'text' : 'texts'}), shown as FDA wrote them`],
      ];
    }
    default: return [];
  }
}

// ---- a value, in plain words, and the control that sets it on a person's own copy ----
function valueWords(v, def) {
  if (def.type === 'bool') return v ? 'Yes' : 'No';
  if (def.type === 'choice') return def.options.find(([o]) => same(o, v))?.[1] ?? String(v);
  if (def.type === 'list') return v.length > 3 ? `${v.slice(0, 3).join(', ')} and ${v.length - 3} more` : v.join(', ');
  return String(v);
}
export const choicesOf = (def) => (def.type === 'bool' ? [[true, 'Yes'], [false, 'No']] : def.options);
export const altioValue = (def) => ` <span class="oa-fda" ${tip("Altio's standard")}>Altio: ${esc(valueWords(def.standard, def))}</span>`;

function valueControl(rule, def, ctx) {
  const v = valueIn(ctx.pending, rule, def.key);
  const note = same(v, def.standard) ? '' : altioValue(def);
  // a list or words are set in the rule file only; elsewhere than a person's own copy, nothing is set
  const fileOnly = def.type === 'list' || def.type === 'text';
  if (!ctx.local || fileOnly) {
    const words = `<span ${def.type === 'list' ? `class="oa-has-tip" ${tip(v.join(', '))}` : ''}>${esc(valueWords(v, def))}</span>`;
    return `${words}${note}${ctx.local ? '<span class="oa-faint oa-value-file">Set in the rule file only</span>' : ''}`;
  }
  const where = `data-rule="${esc(rule.name)}" data-key="${esc(def.key)}"`;
  if (def.type === 'number') {
    return `<span class="oa-value-box" data-state="${note ? 'changed' : ''}"><input class="oa-value-input" inputmode="decimal" autocomplete="off" ${where} value="${esc(v)}" aria-label="${esc(def.label)}"></span><span class="oa-value-note">${note}</span>`;
  }
  const options = choicesOf(def);
  const at = Math.max(0, options.findIndex(([o]) => same(o, v)));
  const state = ['first', 'second', 'third'][at];
  return `<div class="slide-switch oa-value-switch" role="radiogroup" aria-label="${esc(def.label)}" data-state="${state}" ${options.length > 2 ? `data-parts="${options.length}"` : ''}>${options.map(([, w], i) => `<button type="button" class="slide-switch-part" role="radio" aria-checked="${i === at}" data-act="rule-value" ${where} data-i="${i}">${esc(w)}</button>`).join('')}</div><span class="oa-value-note">${note}</span>`;
}

function valuesBlock(rule, ctx) {
  const rows = rule.values.map((def) => `<div class="oa-rule-value" data-key="${esc(def.key)}"><span class="oa-rule-value-label">${esc(def.label)}</span><span class="oa-rule-value-set">${valueControl(rule, def, ctx)}</span><p class="oa-rule-value-problem" role="alert" hidden></p></div>`);
  return `<div class="oa-rule-values">${rows.join('')}</div>`;
}

// ---- an opened row: the decision, the why, then a quiet foot ----
const low = (t) => (/^[A-Z]{2}/.test(t) ? t : t.charAt(0).toLowerCase() + t.slice(1));
// the one grey line that says how to read a chart, from what the chart draws
export function guideOf(c) {
  const y = low(c.y.label);
  const x = low(c.x.label);
  const names = andList(c.series.map((x2) => low(x2.name)));
  if (c.type === 'stacked_bar') return `Bars: ${y}, by ${x}${c.series.length > 1 ? `, split by ${names}` : ''}.`;
  if (c.type === 'stacked_area') return `Areas: ${y}, by ${x}, split by ${names}.`;
  return c.series.length > 1 ? `Lines: ${y}, by ${x}, for ${names}.` : `Line: ${y}, by ${x}.`;
}
export const threeLines = (l, did = esc(l.did)) => `<dl class="oa-m-lines">${l.shows ? `<dt>Shows</dt><dd>${esc(l.shows)}</dd>` : ''}${l.matters ? `<dt>Why it matters</dt><dd>${esc(l.matters)}</dd>` : ''}${l.did ? `<dt>What we did</dt><dd>${did}</dd>` : ''}</dl>`;
// a card's lines: those the release's cards bring, else the finding's own two sentences under our words;
// with no subtitle under the title, Shows opens with what a bar or row is when it does not say so
const READS = /\b(each|every|one)\s+(bar|row|line|point|dot|column|cell|square)\b|^(bars?|lines?|areas?):/i;
export const showsRead = (shows, guide) => (!shows ? guide : READS.test(shows) || !guide ? shows : `${guide} ${shows}`);
function linesOf(card) {
  const l = { ...CARD_WORDS[card.id], shows: card.two_sentences, ...card.lines };
  return { ...l, shows: showsRead(l.shows, l.guide || guideOf(card.chart)) };
}
// a finding as the Why card: the claim, the chart, three short lines
export function whyCard(card, level = 'h4') {
  const l = linesOf(card);
  const c = card.chart;
  const legend = c.series.length > 1 ? `<ul class="oa-legend">${c.series.map((x, k) => `<li><span class="oa-key oa-s${k}"></span>${esc(x.name)}</li>`).join('')}</ul>` : '';
  return `<figure class="oa-evidence oa-m-card"><${level} class="oa-claim oa-m-title">${esc(card.title)}</${level}>
    <div class="oa-evidence-chart" data-card="${esc(card.id)}"></div>${legend}${threeLines(l)}</figure>`;
}

// what switching a rule off would change, from the counts the release carries for it
function offWords(rule, ctx) {
  const { C, data, numbers: n } = ctx;
  const also = tip('A case another rule also sets aside stays set aside');
  switch (rule.name) {
    case 'overlong-lines': return `${num(C.split)} run-on line${C.split === 1 ? '' : 's'} stay${C.split === 1 ? 's' : ''} as one, and the second report is lost.`;
    case 'deleted-cases': return `up to <span class="oa-has-tip" ${tip('Some may then be set aside as duplicates')}>${num(C.steps.after_deleted_lists.removed)}</span> cases FDA withdrew come back.`;
    case 'dedup-default': return `up to <span class="oa-has-tip" ${also}>${num(C.aeolus)}</span> cases it set aside come back.`;
    case 'dup-manufacturer-number': return `up to <span class="oa-has-tip" ${also}>${num(C.mfr)}</span> cases it set aside come back.`;
    case 'dup-padded-event-dates': return `the ${num(C.paddedCases)} cases in the ${num(C.paddedGroups)} groups it keeps whole can be set aside again.`;
    case 'event-date-precision': return n.dates ? `${num(n.dates.day_read_as_month_or_year)} event dates written as a full day but known only to the month or year read as full days again.` : null;
    case 'reporter-type': return n.reporters ? `OT and HP stay two reporter types, ${num(n.reporters.written.OT)} and ${num(n.reporters.written.HP)} cases.` : null;
    case 'drug-names': return n.drug_names ? `the ${num(n.drug_names.spellings)} ${DRUG_LINE.spellings} are not ${DRUG_LINE.verb} their ${num(n.drug_names.ingredients)} ${DRUG_LINE.ingredients} and ${num(n.drug_names.combinations)} ${DRUG_LINE.combinations}.` : null;
    case 'rxnorm-ingredients': return n.rxnorm ? `the ${num(n.rxnorm.coded_records)} suspect drug records with an RxNorm code have none.` : null;
    case 'atc-index': {
      const c = data.classes?.cases;
      return c ? `no drug classes for the ${num(c.with_a_coded_drug)} cases that name a drug WHO classes; nothing else changes.` : null;
    }
    default: return null;
  }
}
// the one line on a rule you can change: what Off changes, in numbers where the release counts it
export function offLine(rule, ctx) {
  if (rule.step.switch && rule.step.switch !== rule.name) return `Switched on and off with its whole step, ${esc(rule.step.title)}.`;
  if (rule.always_on) return '';
  const off = offWords(rule, ctx);
  return off ? `<strong>Off:</strong> ${off}` : '';
}

// a rule nobody can change: always on with nothing to set, or a rule the build has no switch for
export const changeable = (rule) => !rule.always_on || rule.values.length > 0;
export const fixedWhy = (rule) => (rule.named ? 'Not a switch of the build: it is set in its rule file.' : rule.why_locked);

// the decision: what it is set to and its values
function decision(rule, ctx) {
  if (!changeable(rule)) return '';
  const state = rule.always_on ? `<strong>Always on.</strong> ${esc(rule.why_locked)}` : '';
  return `<div class="oa-m-decide">${state ? `<p class="oa-m-state">${state}</p>` : ''}${rule.values.length ? valuesBlock(rule, ctx) : ''}</div>`;
}

// the foot: what it moved, as one compact row, and where to read it
function ruleFoot(facts, links) {
  return `<div class="oa-m-rule-foot">${facts.length ? `<dl class="oa-m-moved">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>` : ''}
    <p class="oa-rule-links">${links.join('')}</p></div>`;
}

function body(rule, ctx) {
  const all = ctx.cardsFor(rule.name);
  const cards = all.filter((c) => !ctx.shownAbove?.has(c.id));
  // the why: each finding as a card; a rule with none says why it matters and what we did
  const above = all.length > cards.length ? '<p class="oa-m-why-above">Its evidence is the finding at the top.</p>' : '';
  const l = RULE_WORDS[rule.name];
  const shared = SHARED_CHART[rule.name] ? `<p class="oa-m-why-above">${esc(SHARED_CHART[rule.name])}</p>` : '';
  const why = shared + (cards.length ? above + cards.map((c) => whyCard(c)).join('') : above || (l ? threeLines(l) : `<p class="oa-rule-plain">${esc(rule.text)}</p>`));
  const links = [outLink(ctx.link(rule.file), 'The rule file'), rule.code ? outLink(ctx.link(rule.code), 'The code') : ''];
  return `<div class="oa-rule-body oa-m-rule-body" id="rule-body-${esc(rule.name)}">
    ${decision(rule, ctx)}
    <div class="oa-m-why">${why}</div>
    ${ruleFoot(rule.named ? [] : factsFor(rule, ctx), links)}
  </div>`;
}

// on, on and changed, or off: what a rule's state reads in the choices given
export function stateWord(rule, choices) {
  if (!isOn(choices, rule.name)) return 'Off';
  return choices[rule.name]?.values ? 'On, changed' : 'On';
}

// the state: a switch on a person's own copy, a tag elsewhere; an always-on rule is locked
function stateCell(rule, ctx, label = rule.title) {
  if (rule.always_on) return `<span class="oa-chip oa-chip-quiet oa-has-tip" ${tip(`Always on: ${rule.why_locked}`)}>Always on</span>`;
  const on = isOn(ctx.pending, rule.name);
  const word = stateWord(rule, ctx.pending);
  if (!ctx.local) return `<span class="oa-chip ${on ? 'oa-chip-quiet' : 'oa-chip-aside'}">${word}</span>`;
  return `<button type="button" class="switch oa-rule-switch" role="switch" aria-checked="${on}" data-act="rule-switch" data-rule="${esc(rule.name)}" aria-label="${esc(label)}"><span class="switch-track"></span><span class="oa-switch-word">${word}</span></button>`;
}

export function ruleRow(rule, ctx, open) {
  const moved = rule.named ? null : movedFor(rule, ctx);
  const movedHtml = moved
    ? `<span class="oa-has-tip" ${moved.tipAttr || (moved.tip ? tip(moved.tip) : '')}>${moved.html || esc(moved.text)}</span>`
    : rule.named ? '' : `<span class="oa-faint oa-has-tip" ${tip("This release's methods carry no count for this rule")}>Not counted</span>`;
  const switched = rule.step.switch; // its step's one switch, in the step's head
  // under the line: what Off changes on a rule you can change, why on one nobody changes
  const under = changeable(rule) ? offLine(rule, ctx) : `Fixed: ${esc(fixedWhy(rule))}`;
  return `<li class="oa-rule" id="rule-${esc(rule.name)}" data-open="${open}" data-on="${isOn(ctx.pending, switched || rule.name)}">
    <div class="oa-rule-head" role="button" tabindex="0" data-act="rule-toggle" data-id="${esc(rule.name)}" aria-expanded="${open}" aria-controls="rule-body-${esc(rule.name)}">
      <span class="oa-rule-chev">${icon('chevronDown')}</span>
      <span class="oa-rule-words"><span class="oa-rule-name">${esc(rule.title)}</span><span class="oa-rule-line">${esc(rule.line)}</span>${under ? `<span class="oa-m-under">${under}</span>` : ''}</span>
      <span class="oa-rule-state">${switched || !changeable(rule) ? '' : stateCell(rule, ctx)}</span>
      <span class="oa-rule-moved">${movedHtml}</span>
    </div>
    ${open ? body(rule, ctx) : ''}
  </li>`;
}

// the choices a release was built with, each named in plain words with Altio's value beside it
export function differenceRows(ctx, row) {
  return Object.entries(ctx.built).map(([name, c]) => {
    const rule = ctx.R.find((r) => r.name === name);
    if (!rule) return '';
    const what = Object.entries(c.values || {}).map(([key, v]) => {
      const def = rule.values.find((x) => x.key === key);
      return `${esc(def.label)}: ${esc(valueWords(v, def))}${altioValue(def)}`;
    }).join('; ');
    // a step's one switch is named as the step
    const named = rule.step.switch === rule.name ? { ...rule, title: rule.step.title } : rule;
    return row(named, c.on === false ? 'Off' : 'Changed', what);
  }).join('');
}

export function yoursBox(ctx) {
  const rows = differenceRows(ctx, (rule, word, what) => `<li><span class="oa-chip ${word === 'Off' ? 'oa-chip-aside' : ''}">${word}</span><a href="/methods?open=${encodeURIComponent(rule.name)}">${esc(rule.title)}</a>${what ? `<span class="oa-yours-what">${what}</span>` : ''}</li>`);
  return `<section class="oa-yours" aria-label="Your rules">
    <p class="oa-yours-head"><strong>${esc(summary(ctx.built))}</strong></p>
    <ul class="oa-yours-list">${rows}</ul>
    ${ctx.local && ctx.data.file ? '<p class="oa-yours-file">Saved as rules.toml beside the release. <button type="button" class="oa-link" data-act="rules-download">Download your rules</button></p>' : ''}
  </section>`;
}

// a step with one switch for all its rules, the switch in its head
export function group(id, number, title, sentence, rules, ctx, openIds) {
  const switched = rules.find((r) => r.name === r.step.switch);
  const cls = ctx.data.classes;
  const cite = cls?.step === id && cls.citation ? `<p class="oa-note oa-rule-group-cite">Cite as: ${esc(cls.citation)}</p>` : '';
  return `<section class="oa-rule-group${switched ? ' oa-rule-group-switched' : ''}" id="step-${esc(id)}" ${switched ? `data-on="${isOn(ctx.pending, switched.name)}"` : ''}>
    <div class="oa-rule-group-head">
      <span class="oa-step-n ${number ? '' : 'oa-step-n-end'}" aria-hidden="true">${number || icon('check')}</span>
      <div class="oa-rule-group-words"><h2 class="oa-rule-group-title">${esc(title)}</h2>${sentence ? `<p class="oa-note">${esc(sentence)}</p>` : ''}${cite}</div>
      ${switched ? `<span class="oa-rule-group-state">${stateCell(switched, ctx, title)}</span>` : ''}
    </div>
    <ul class="oa-rule-list">${rules.map((r) => ruleRow(r, ctx, openIds.has(r.name))).join('')}</ul>
  </section>`;
}

// a finding measured and left as FDA wrote it, as a row that opens to its card
const docBody = (card) => `<div class="oa-rule-body oa-rule-body-doc oa-m-rule-body"><div class="oa-m-why">${whyCard(card)}</div></div>`;
export const docRow = (c, open = false) => `<li class="oa-rule oa-rule-doc" id="rule-card-${esc(c.id)}" data-open="${open}">
      <div class="oa-rule-head" role="button" tabindex="0" data-act="rule-toggle" data-id="card-${esc(c.id)}" aria-expanded="${open}">
        <span class="oa-rule-chev">${icon('chevronDown')}</span>
        <span class="oa-rule-words"><span class="oa-rule-name">${esc(c.title)}</span></span>
        <span class="oa-rule-state"></span><span class="oa-rule-moved"><span class="oa-faint">Not changed</span></span>
      </div>
      ${open ? docBody(c) : ''}
    </li>`;

// what the release does not do, each a row that opens to its sentence or two
const limitBody = (l) => `<div class="oa-rule-body oa-rule-body-doc"><p class="oa-note oa-limit-text">${esc(l.text)}</p></div>`;
export const limitsList = (M) => (M.limits.length ? `<section class="oa-rule-group oa-rule-group-plain" id="limits">
      <div class="oa-rule-group-head"><div class="oa-rule-group-words"><h2 class="oa-rule-group-title">What we do not do</h2></div></div>
      <ul class="oa-rule-list">${M.limits.map((l) => `<li class="oa-rule oa-rule-doc" id="rule-limit-${esc(l.id)}" data-open="false">
        <div class="oa-rule-head" role="button" tabindex="0" data-act="rule-toggle" data-id="limit-${esc(l.id)}" aria-expanded="false">
          <span class="oa-rule-chev">${icon('chevronDown')}</span>
          <span class="oa-rule-words"><span class="oa-rule-name">${esc(l.title)}</span></span>
        </div>
      </li>`).join('')}</ul></section>` : '');

// a row's body, put in when the row opens
export function openRow(li, ctx) {
  const id = li.querySelector('.oa-rule-head').dataset.id;
  const html = id.startsWith('card-') ? docBody(ctx.M.insights.find((c) => `card-${c.id}` === id))
    : id.startsWith('limit-') ? limitBody(ctx.M.limits.find((l) => `limit-${l.id}` === id))
    : body(ctx.R.find((r) => r.name === id), ctx);
  li.insertAdjacentHTML('beforeend', html);
}
