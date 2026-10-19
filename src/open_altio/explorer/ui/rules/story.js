/* How we clean FAERS, as one story in three levels. Narrow: the funnel from every report version
   FDA published to the cases you see. Read one way: the values every count and filter shares,
   FDA's above ours. Answer: four questions people bring, each a path that cleans what it needs,
   organizes it and ends in the answer. Every number is the release's: methods.json's steps and
   numbers, the counts of the manifest and of the licensed part the API passes on, and the cards.
   A part the release was built without is left out. Each box opens on its finding and on the rules
   that act there (homes.js). */

import { icon } from '../icons.js';
import { esc, num } from '../util.js';
import { rulesMark } from './homes.js';
import { DRUG_LINE } from './words.js';

const pct = (a, b) => (b ? `${((100 * a) / b).toFixed(1)}%` : '');
const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : num(n));
const sentenceCase = (s) => s.charAt(0) + s.slice(1).toLowerCase();

// ---- the small charts: every bar labelled in words; one accent for what changed ----
const counts = (rows) => {
  const top = Math.max(...rows.map(([, n]) => n), 1);
  return `<div class="oa-m-mini">${rows.map(([label, n]) => `<div class="oa-m-row"><span class="oa-m-lab" title="${esc(label)}">${esc(label)}</span><span class="oa-m-bar"><i class="oa-m-fill" style="width:max(3px, ${(100 * n) / top}%)"></i></span><span class="oa-m-num">${num(n)}</span></div>`).join('')}</div>`;
};
// two rows in one unit, FDA's and ours; a segment marked changed is the one accent
function beforeAfter(fda, ours) {
  const top = Math.max(...[fda, ours].map((r) => r.reduce((s, [, n]) => s + n, 0)));
  const row = (who, segs) => `<div class="oa-m-ba-row"><span class="oa-m-ba-who">${who}</span><span class="oa-m-ba-bar">${segs.map(([label, n, changed]) => `<span class="oa-m-seg${changed ? ' oa-m-seg-changed' : ''}" style="flex:0 0 ${(100 * n) / top}%" title="${esc(label)}: ${num(n)}">${esc(label)} <b>${short(n)}</b></span>`).join('')}</span></div>`;
  return `<div class="oa-m-ba">${row('FDA', fda)}${row('Ours', ours)}</div>`;
}
// a change in words on two lines, read top to bottom like everything else on the page
const twoLines = (fromN, fromWords, verb, toN, toWords, more = '') => `<div class="oa-m-two"><span><b>${num(fromN)}</b> ${esc(fromWords)}</span><span class="oa-m-two-to">${esc(verb)} <b>${num(toN)}</b> ${esc(toWords)}${more}</span></div>`;
// a card of the release drawn small: one bar per category of its one series
const cardBars = (card) => counts(card.chart.x.values.map((x, i) => [String(x), card.chart.series[0].values[i] || 0]));

// The story's items, from the release. A box's `why` names the finding it opens on; a box with
// none opens on its own card (title, guide, chart, shows, matters, did) or its first rule's.
export function storyOf(ctx) {
  const { M, data } = ctx;
  const n = ctx.numbers;
  const stepTitle = (id) => data.steps.find((s) => s.id === id)?.title || M.steps.find((s) => s.id === id)?.title;
  const step = (id) => M.steps.find((s) => s.id === id);
  const cardOf = (rule) => ctx.cardsFor(rule)[0];

  // 1. narrow: the funnel to the cases you see
  const FUNNEL = [
    { id: 'report_versions', unit: 'report versions', lead: 'transformed-suffix-T' },
    { id: 'latest_versions', unit: 'cases, each at its newest version', outWords: 'earlier versions set aside', why: 'carried_cases_counted_twice' },
    { id: 'after_deleted_lists', unit: 'cases FDA has not withdrawn', outWords: 'withdrawn cases left out', why: 'deleted_lists_unpublished' },
    { id: 'kept_after_duplicates', unit: 'cases you see', outWords: 'probable duplicates set aside', why: 'same_event_several_cases' },
  ].filter((b) => step(b.id)).map((b) => ({ ...b, name: stepTitle(b.id), count: step(b.id).after.total, removed: step(b.id).removed?.total }));
  const seen = FUNNEL.at(-1).count;

  // 2. read one way: what every count and filter shares
  const d = n.dates;
  const a = n.ages;
  const r = n.reporters;
  const e = n.routes;
  const BAND = [
    { id: 'dates', name: 'Dates', why: 'event_dates_padded',
      ...(d && { chart: beforeAfter([['Look like a full day', d.written.day]], [['Are a full day', d.read.day], ['Month or year', d.day_read_as_month_or_year, true]]),
        change: `${short(d.day_read_as_month_or_year)} padded dates now read as month or year.` }) },
    { id: 'demographics', name: 'Age, sex, weight and country', why: 'ages_without_a_unit',
      ...(a && { chart: twoLines(a.units.YR, 'ages given in years by FDA', 'read to', a.in_years, 'ages in years'),
        change: `${num(a.in_years - a.units.YR)} more ages in years, from ages given in other units or with no unit.` }) },
    { id: 'senders', name: 'Senders and reporters', why: 'occupation_code_changes',
      ...(r && { chart: beforeAfter([['OT', r.written.OT], ['HP or RN', r.written.HP + (r.written.RN || 0)]], [['Other health professional', r.read['3'], true]]),
        change: `OT and HP, ${short(r.read['3'])} cases, now one reporter type.` }) },
    { id: 'empty_fields', name: 'Empty fields', why: 'unknown_written_two_ways',
      ...(e && { chart: beforeAfter([['Blank', e.blank], ['Says unknown', e.says_unknown]], [['Not given', e.not_given, true]]),
        change: `${short(e.not_given)} drug routes, two ways of saying unknown, now one.` }) },
  ];

  // 3. answer: the boxes of the four paths
  const dn = n.drug_names;
  const rx = n.rxnorm;
  const fam = e?.families;
  const cls = n.classes;
  const st = data.release.statistics;
  const md = data.meddra?.numbers || {};
  const older = md.older_terms;
  const pts = md.terms?.meddra_terms;
  const ebgm = n.statistics?.stand_out?.EBGM;
  const missed = dn && dn.suspect_cases.by_ingredient - dn.suspect_cases.by_most_common_spelling;
  // ingredients by how many spellings FDA's files hold for each, from the counts by digits
  const spellings = dn && dn.spellings_per_ingredient.by_digits.flatMap(({ digits, ingredients }) => {
    const from = 10 ** (digits - 1);
    const label = `${num(digits === 1 ? 2 : from)} to ${num(10 * from - 1)} spellings`;
    return digits === 1 ? [['1 spelling', dn.spellings_per_ingredient.one], [label, ingredients - dn.spellings_per_ingredient.one]] : [[label, ingredients]];
  });
  const hundredPlus = dn && dn.spellings_per_ingredient.by_digits.filter((x) => x.digits >= 3).reduce((t, x) => t + x.ingredients, 0);
  const chosen = cls && ['dose', 'route', 'indication'].reduce((t, k) => t + (cls.chosen_by[k] || 0), 0);
  const CHOICE = [['only_code', 'Only one class'], ['cannot_tell', "Can't tell"], ['group_class', 'Group class'], ['route', 'By route'], ['shared_class', 'Shared class'], ['indication', 'By indication'], ['dose', 'By dose']];
  const flagsCard = cardOf('label-flags');
  const labelsCard = cardOf('label-choice');
  const BOXES = {
    drug_names: { name: 'Drug names', step: 'clean', rule: 'drug-names',
      ...(dn && { show: twoLines(dn.spellings, DRUG_LINE.spellings, DRUG_LINE.verb, dn.ingredients, DRUG_LINE.ingredients,
          ` and <b>${num(dn.combinations)}</b> ${esc(DRUG_LINE.combinations)}`),
        title: `${num(dn.written_two_or_more_ways)} of ${num(dn.ingredients)} ${DRUG_LINE.ingredients} are written two or more ways, ${num(hundredPlus)} of them 100 or more`,
        guide: "Bars: ingredients, by how many spellings FDA's files hold for each.", chart: counts(spellings),
        shows: `A search by each ingredient's most common spelling misses ${pct(missed, dn.suspect_cases.by_ingredient)} of its suspect cases.`,
        matters: 'A count by one name undercounts the medicine.', did: 'Read every drug name to its ingredients.' }) },
    rxnorm: { name: 'RxNorm codes', step: 'organize', rule: 'rxnorm-ingredients',
      ...(rx && { count: rx.codes, unit: 'RxNorm codes, one per drug',
        title: `${pct(rx.coded_records, rx.suspect_records)} of suspect drug records have an RxNorm code`, guide: 'Bars: suspect drug records, all of them and those with a code.',
        chart: counts([['Suspect drug records', rx.suspect_records], ['With a code', rx.coded_records]]), shows: `${num(rx.suspect_records - rx.coded_records)} have none, mostly drugs sold outside the US.`,
        matters: 'The code is what joins a drug to its FDA label.', did: 'Give each drug row the RxNorm code of its drug.' }) },
    routes: { name: 'Route families', step: 'clean', rule: 'drug-route',
      ...(fam && { show: twoLines(e.rows, 'routes as FDA wrote them', 'grouped into', fam.families, 'route families'),
        title: `${num(fam.one)} drug rows have one route family`, guide: 'Bars: drug rows by how many route families they could be in.',
        chart: counts([['One family', fam.one], ['Could be several', fam.several], ['Not known', fam.not_known]]),
        shows: `${num(fam.several)} could be several, like by mouth or under the tongue.`, matters: 'A label is read only for the routes a drug could take.',
        did: 'Give each drug row every family its route allows.' }) },
    labels: { name: 'FDA labels', step: 'organize', rule: 'label-choice', why: labelsCard?.id },
    terms: { name: 'Reaction terms', step: 'clean', rule: 'meddra-terms', why: older ? null : 'older_meddra_terms_missed',
      ...(n.terms && { show: pts ? twoLines(n.terms.texts, 'terms as written', 'read to', pts, `MedDRA ${data.meddra.version} terms`) : `<span class="oa-m-count"><b>${num(n.terms.texts)}</b> terms as written</span>` }),
      ...(older && { title: `${num(older.with_an_older_term)} cases carry a reaction term MedDRA has since replaced`, guide: "Bars: cases you see, those with an older term, and those a search on today's term misses.",
        chart: counts([['Cases you see', seen], ['With an older term', older.with_an_older_term], ["Missed by today's term", older.missed_by_todays_term]]),
        shows: `A search on today's term misses ${num(older.missed_by_todays_term)} of them.`, matters: "Counts by today's term would leave those cases out.",
        did: "Read every term to today's preferred term." }) },
    pairs: { name: 'Pairs', step: 'organize', rule: 'statistics-cases',
      ...(st && { count: st.pairs, unit: 'ingredient and term pairs',
        title: `${num(st.pairs)} ingredient and term pairs, from ${num(st.cases)} cases`, guide: 'Bars: what the statistics count.',
        chart: counts([['Cases', st.cases], ['Pairs', st.pairs], ['Terms', st.reactions], ['Ingredients', st.ingredients]]),
        shows: 'Each pair is one suspect ingredient with one reaction.', matters: 'Every statistic for a pair counts the same cases.',
        did: 'Count the cases naming a suspect ingredient and a reaction.' }) },
    classes: { name: 'WHO classes', step: 'organize', rule: 'atc-class-choice',
      ...(cls ? { count: cls.codes, unit: "classes from WHO's ATC index, a layer a host can switch off",
        title: `${num(chosen + (cls.chosen_by.shared_class || 0))} drug rows needed a choice among WHO classes; ${num(cls.chosen_by.cannot_tell || 0)} could not be told`,
        guide: 'Bars: drug rows WHO codes, by how their one class was chosen.',
        chart: counts(CHOICE.map(([k, w]) => [w, cls.chosen_by[k] || 0])),
        shows: `Dose, route or indication chose the class for ${num(chosen)} rows.`, matters: "One fixed class per substance would file some uses under another's.",
        did: 'One class per drug row, by dose, route or use.' } : { show: '<span class="oa-m-count">Not built in this release</span>' }) },
  };
  const top5 = (cls?.main_groups || []).slice(0, 5).map((g) => [sentenceCase(g.name), g.cases]);
  const ANSWERS = {
    a_cases: { name: 'Every report of the drug', rule: 'drug-names',
      ...(dn && { title: `A search by each ingredient's most common spelling misses ${num(missed)} of its suspect cases`, guide: 'Bars: suspect cases over every ingredient, found by one spelling and by the ingredient.',
        chart: counts([['By the most common spelling', dn.suspect_cases.by_most_common_spelling], ['By the ingredient', dn.suspect_cases.by_ingredient]]),
        shows: `${pct(missed, dn.suspect_cases.by_ingredient)} of suspect cases are under other spellings.`, matters: 'A count by one name undercounts the medicine.',
        did: 'Count a drug by its ingredients, whatever its name.' }) },
    a_flags: { name: 'Label flags', rule: 'label-flags', why: flagsCard?.id,
      ...(flagsCard && { title: flagsCard.title, guide: 'Bars: drug and reaction pairs, by the flag each gets.', chart: cardBars(flagsCard) }) },
    a_stats: { name: 'Statistics', rule: 'ebgm', note: 'A signal is not proof of cause.',
      ...(st && ebgm && { title: `${num(ebgm.pairs)} of ${num(st.pairs)} pairs stand out by default`, guide: 'Bars: pairs, all of them and those meeting the default screen.',
        chart: counts([['Pairs', st.pairs], ['Stand out', ebgm.pairs]]), shows: `${pct(ebgm.pairs, st.pairs)} meet the default EBGM screen.`,
        matters: 'A signal is not proof of cause.', did: 'Work out EBGM, PRR, ROR, RRR and IC for every pair.' }) },
    a_classes: { name: 'Class counts', rule: 'atc-class-choice', note: 'A host can switch the classes off.',
      ...(top5.length && { title: `${top5[0][0]} reach the most cases: ${num(top5[0][1])}`, guide: "Bars: cases you see in WHO's five largest main groups.",
        chart: counts(top5), shows: `${num(cls.rows_with_class)} drug rows have a class.`, matters: 'A drug can be set beside the others of its class.',
        did: 'One class per drug row, by dose, route or use.' }) },
  };
  const QUESTIONS = [
    { id: 'find', q: 'Find every report of my drug, however FDA spelled it', clean: ['drug_names'], boxes: ['rxnorm'], answer: 'a_cases' },
    { id: 'label', q: "Is this reaction on my drug's label?", clean: ['drug_names'], boxes: ['routes', 'labels'], answer: 'a_flags' },
    ...(data.classes ? [{ id: 'class', q: "How many cases does my drug's class have?", clean: ['drug_names'], boxes: ['classes'], answer: 'a_classes' }] : []),
    { id: 'signal', q: 'Is this reaction reported more than expected?', clean: ['drug_names', 'terms'], boxes: ['pairs'], answer: 'a_stats' },
  ];
  const ITEMS = Object.fromEntries([...FUNNEL, ...BAND, ...Object.entries({ ...BOXES, ...ANSWERS }).map(([id, t]) => ({ ...t, id }))].map((t) => [t.id, t]));
  // a box with no finding and no card of its own opens on its first rule's chart, where it has one
  Object.values(ITEMS).forEach((t) => { if (!t.why && !t.chart && t.lead) t.why = cardOf(t.lead)?.id; });
  const LEVELS = [
    { id: 'narrow', name: 'Narrow', claim: `${num(FUNNEL[0].count)} report versions narrow to ${num(seen)} cases`, sub: 'Each band is sized to what is left after its step. Press one for why, and for its rules.' },
    { id: 'read', name: 'Read one way', claim: 'Read one way, so every count and filter means the same', sub: "FDA's value above, ours below; the change in one colour." },
    { id: 'answer', name: 'Answer', claim: 'Organized to answer your questions', sub: 'Choose a question to follow it from cleaning to its answer.' },
  ];
  return { FUNNEL, BAND, ITEMS, QUESTIONS, LEVELS, seen };
}

// ---- drawing the story ----
function funnel(ctx, S) {
  const top = S.FUNNEL[0].count;
  return `<ol class="oa-m-funnel">${S.FUNNEL.map((b, i) => {
    const w = b.count / top;
    const next = (S.FUNNEL[i + 1] || b).count / top;
    const clip = `polygon(${50 - 50 * w}% 0, ${50 + 50 * w}% 0, ${50 + 50 * next}% 100%, ${50 - 50 * next}% 100%)`;
    return `<li class="oa-m-band-row" data-last="${i === S.FUNNEL.length - 1}">
      <button type="button" class="oa-m-band" data-act="m-box" data-item="${b.id}" style="clip-path:${clip}" aria-label="${esc(b.name)}"><span class="oa-m-band-num">${num(b.count)}</span><span class="oa-m-band-unit">${esc(b.unit)}</span></button>
      <span class="oa-m-out">${b.removed ? `<strong>${num(b.removed)}</strong> ${esc(b.outWords)}` : 'As FDA published them'}<button type="button" class="oa-m-out-rules" data-act="m-box" data-item="${b.id}">${rulesMark(ctx, b.id)}</button></span></li>`;
  }).join('')}</ol>`;
}
const bandTile = (ctx, t) => `<button type="button" class="oa-m-tile" data-act="m-box" data-item="${t.id}"><span class="oa-card-sub oa-m-kind">${esc(t.name)}</span>${t.chart || ''}${t.change ? `<span class="oa-m-change">${esc(t.change)}</span>` : ''}${rulesMark(ctx, t.id)}</button>`;
function box(ctx, S, id) {
  const b = S.ITEMS[id];
  const body = b.show || (b.count != null ? `<span class="oa-m-count"><b>${num(b.count)}</b> ${esc(b.unit)}</span>` : '');
  return `<button type="button" class="oa-m-box" data-act="m-box" data-item="${id}" data-step="${b.step}"><span class="oa-m-box-name">${esc(b.name)}</span>${body}${rulesMark(ctx, id)}</button>`;
}
function answerBox(ctx, S, id) {
  const a = S.ITEMS[id];
  const head = a.title ? `<span class="oa-m-answer-title">${esc(a.title)}</span><span class="oa-m-read">${esc(a.guide)}</span>${a.chart}` : `<span class="oa-m-box-name">${esc(a.name)}</span>`;
  return `<button type="button" class="oa-m-box oa-m-answer" data-act="m-box" data-item="${id}" data-step="answer">${head}${a.note ? `<span class="oa-m-note">${esc(a.note)}</span>` : ''}${rulesMark(ctx, id)}</button>`;
}
const down = `<span class="oa-m-down" aria-hidden="true">${icon('chevronDown')}</span>`;
// one question's path, top to bottom: what it cleans (side by side where it needs two), what it organizes, its answer
export const path = (ctx, S, q) => `<div class="oa-m-path-clean" style="--n:${q.clean.length}">${q.clean.map((id) => box(ctx, S, id)).join('')}</div>${down}
  ${q.boxes.map((id) => box(ctx, S, id)).join(down)}${down}${answerBox(ctx, S, q.answer)}`;
const picker = (ctx, S, chosen) => `<div class="oa-m-picker" role="tablist" aria-label="Questions" style="--n:${S.QUESTIONS.length}">${S.QUESTIONS.map((q, i) => `<button type="button" class="oa-m-pick" role="tab" aria-selected="${q.id === chosen.id}" data-act="m-pick" data-q="${q.id}"><span class="oa-step-n">${i + 1}</span><span>${esc(q.q)}</span></button>`).join('')}</div>
  <div class="oa-m-path" id="oa-m-path" role="tabpanel">${path(ctx, S, chosen)}</div>`;
const flow = (words) => `<div class="oa-m-flow" aria-hidden="true"><span class="oa-m-flow-line"></span><span class="oa-m-flow-words">${esc(words)}</span>${icon('chevronDown')}</div>`;
export function levels(ctx, S, chosen) {
  const bodies = {
    narrow: () => funnel(ctx, S) + flow(`${num(S.seen)} cases, read one way`),
    read: () => `<div class="oa-m-tiles">${S.BAND.map((t) => bandTile(ctx, t)).join('')}</div>${flow(`Then organized for ${S.QUESTIONS.length} questions`)}`,
    answer: () => picker(ctx, S, chosen),
  };
  return S.LEVELS.map((l, i) => `<section class="oa-m-level" id="${l.id}">
      <div class="oa-m-level-head"><span class="oa-step-n">${i + 1}</span><div><h2 class="oa-claim">${esc(l.claim)}</h2><p class="oa-claim-sub">${esc(l.sub)}</p></div></div>
      ${bodies[l.id]()}</section>`).join('');
}

