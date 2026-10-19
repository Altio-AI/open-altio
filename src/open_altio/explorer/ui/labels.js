/* The label flags: whether today's US prescription label of a suspect drug lists a reaction
   (src/open_altio/explorer/labels.py, rule explorer-label-flags). Each flag in words and its tip,
   About the label flags, Label status's pane in the filters menu, and the lines under a case's
   reactions. A release without the flags shows none of them (labelsOn). */

import { actions } from './events.js';
import { host } from './host.js';
import { choice, dialog } from './overlays.js';
import { S, productLabel } from './state.js';
import { day, esc, tip } from './util.js';

// the flags' order, Unexpected only's ticks, the address's word for none ticked, and each flag's
// word and, for one not compared with the label, its reason (rule explorer-label-words; /api/release)
export const labelsOn = () => !!S.release?.labels;
export const labelRules = () => S.release.labels;
const said = (outcome) => labelRules().words[outcome] || '';
const reason = (outcome) => labelRules().reasons[outcome] || '';
const low = (s) => s.charAt(0).toLowerCase() + s.slice(1);

export const SUSPECTED = "FAERS reports are suspected events, not proven reactions. The flag only says whether today's label lists the event.";
// what Unexpected only means, in FDA's words, under the button that ticks it
export const UNEXPECTED_MEANS = 'FDA calls a reaction unexpected when it is "not listed in the current labeling for the drug product" (21 CFR 314.80).';

// what each flag means
const MEANS = {
  not_on_label: () => 'The label does not name this reaction or anything related to it.',
  forms_differ: () => 'The drug has labels for different forms, such as tablets and a gel, and they do not agree: one lists the reaction and another does not. The flag gives each form\'s answer.',
  uncertain: () => 'Not decided yet: the rules could not settle it and Altio has not reviewed it. A model\'s guess never shows as decided.',
  related: () => `The label names a related reaction, not this one. A more specific or more severe reaction than the label's counts as unexpected, so it is kept apart from ${said('on_label')}.`,
  on_label: () => 'The label names this reaction in one of its safety sections: the boxed warning, warnings and precautions, adverse reactions or contraindications. The flag says which.',
  procedure: () => 'A surgery or treatment, not a reaction. It can be the only sign of serious harm (a transplant or dialysis), so it is shown unless you hide it.',
  treated_disease: () => 'A disease the label lists among the diseases the drug treats (Indications). Usually the disease itself not improving; worsening of the treated disease can still be a real signal.',
  not_a_medical_event: () => 'Off label use, a product use error, exposure to or administration of a product, or lack of effect. Death and a condition aggravated are compared with the label like any other event.',
  no_label: () => 'We could not find a US prescription label for this drug (aspirin, sold over the counter, is one).',
};
// no answer yet, or not compared with the label: grey, with its tip
const grey = (outcome) => outcome === 'uncertain' || !!reason(outcome);
const SECTION = { boxed_warning: 'the boxed warning', warnings_and_precautions: 'warnings and precautions', warnings: 'warnings', precautions: 'precautions', adverse_reactions: 'adverse reactions', contraindications: 'contraindications' };
// each route family in plain words, as a label is named by it: "the by-mouth label"
const FORM = { by_mouth: 'by-mouth', under_tongue: 'under-the-tongue', injected: 'injected', inhaled: 'inhaled', nasal: 'nasal', rectal: 'rectal', vaginal: 'vaginal', transdermal: 'patch', skin: 'skin', eye: 'eye', ear: 'ear', other: 'other' };
const formName = (form) => FORM[form] || form;
const listed = (words, and = 'and') => (words.length < 2 ? words.join('') : `${words.slice(0, -1).join(', ')} ${and} ${words[words.length - 1]}`);
// one or more forms' labels: "by-mouth label", "by-mouth and skin labels"
const formsLabel = (forms) => `${listed(forms.map(formName))} label${forms.length > 1 ? 's' : ''}`;
// what a form's label says of the reaction, in the flags' words: "listed on the by-mouth label",
// "not compared on the skin label (the disease it treats)", "no skin label"
const formSays = (outcome, n) => (outcome === 'no_label' ? `no ${n}`
  : `${low(said(outcome))} on the ${n}${reason(outcome) ? ` (${reason(outcome)})` : ''}`);
// decided by the term alone, whatever the label
const TERM_ONLY = new Set(['procedure', 'not_a_medical_event']);
const HOW = { rule: 'Decided by rule.', 'rule: umbrella': 'Decided by rule.', model_reviewed: 'Decided by the model, then reviewed by Altio.' };

// a flag in a line of words: "Listed", "Not compared (a procedure)"
export const flagWords = (outcome) => (reason(outcome) ? `${said(outcome)} (${reason(outcome)})` : said(outcome));
// DailyMed's page for the version of the label the flags were read from, not its newest
export const dailymed = (label) => `https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=${encodeURIComponent(label.setid)}&version=${encodeURIComponent(label.version)}`;
// the day the release's labels are as of, the last of DailyMed's days applied (rule label-refresh)
export const labelsAsOf = () => (labelRules().as_of ? ` Labels as of ${day(labelRules().as_of)}.` : '');
// what the link opens, and when the labels are checked against DailyMed (rule label-refresh)
export const versionTip = () => `The version these flags were read from. Labels are checked against DailyMed every day at ${labelRules().checked_at_utc} UTC; the newest may differ until then.`;
const sentence = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// a label read, as every screen names it (rule explorer-label-names): its product, its
// ingredients and, only where the labels read here differ by form, its forms, then its date.
// "Diovan HCT (hydrochlorothiazide and valsartan) label, 13-Feb-2026", "dexamethasone injected
// label, 30-Jun-2026"; labelnames.py gives the parts
export function labelName(label) {
  const ingredients = listed(label.ingredients);
  const forms = label.forms.length ? `${listed(label.forms.map(formName))} ` : '';
  return `${label.product ? `${label.product} (${ingredients})` : ingredients} ${forms}label, ${day(label.date)}`;
}
// the label linked, saying where the link goes and which version it opens
export const labelLink = (label) => `<a href="${dailymed(label)}" target="_blank" rel="noopener" ${tip(versionTip())}>${esc(labelName(label))}, on DailyMed</a>`;

// Forms differ's split, each form's answer, forms with the same answer together: "listed on the
// by-mouth and under-the-tongue labels, not listed on the skin label"
export function formsSplit(flag) {
  const by = new Map();
  (flag.families || []).forEach(([form, outcome]) => by.set(outcome, [...(by.get(outcome) || []), form]));
  return [...by].map(([outcome, forms]) => formSays(outcome, formsLabel(forms))).join(', ');
}

// A flag read on another form's label, because none of the forms the report could be has a label
// or the report does not say the form, is compared there and says which: "listed on the injected
// label" and "no by-mouth label"
const formsOf = (flag) => flag.forms || [];
const otherForm = (flag) => !!flag.judged_on?.length && !flag.judged_on.some((f) => formsOf(flag).includes(f))
  && flag.outcome !== 'forms_differ' && !TERM_ONLY.has(flag.outcome);
const formRead = (flag) => formSays(flag.outcome, formsLabel(flag.judged_on));
// a drug's row (`row`) speaks for its reports
const formMissing = (flag) => (formsOf(flag).length ? `no ${listed(formsOf(flag).map(formName), 'or')} label` : flag.row ? 'its reports do not say the form' : 'the report does not say the form');
const andMissing = (flag) => `; ${formMissing(flag)}`;

// the tip on a flag: its words, what it says, how it was decided, the label read, and that a
// report is a suspicion
export function flagTip(flag, drug) {
  const how = HOW[flag.decided_by] || '';
  const unknownForm = Array.isArray(flag.forms) && !flag.forms.length && !flag.row ? ' The report does not say which form was taken.' : '';
  const word = said(flag.outcome);
  const named = `${word}, ${reason(flag.outcome)}`; // Not compared, a procedure
  const says = otherForm(flag)
    ? `${sentence(formRead(flag))}${andMissing(flag)}.${flag.outcome === 'on_label' && SECTION[flag.section] ? ` It names it in ${SECTION[flag.section]}.` : ''} ${flag.outcome === 'uncertain' ? 'Not decided yet.' : how}`
    : {
      not_on_label: `${word} on today's label. ${how}`,
      forms_differ: `${word}: ${formsSplit(flag)}.${unknownForm} ${how}`,
      uncertain: `${word}: the rules could not settle it against today's label, and Altio has not reviewed it.`,
      related: `${word}: today's label names a related reaction, not this one. ${how}`,
      on_label: `${word} on today's label, in ${SECTION[flag.section] || 'a safety section'}. ${how}`,
      procedure: `${named}: a surgery or treatment, not a reaction. It can be the only sign of serious harm (a transplant or dialysis), so it is shown unless you hide it. ${how}`,
      treated_disease: `${named}: today's label lists it among the diseases the drug treats (Indications). Usually the disease itself not improving; worsening of the treated disease can still be a real signal. ${how}`,
      not_a_medical_event: `${named}: off label use, a product use error, exposure to or administration of a product, or lack of effect. ${how}`,
      no_label: `${named}: we could not find a US prescription label for ${drug}.`,
    }[flag.outcome];
  const dated = flag.label ? ` ${sentence(labelName(flag.label))}, on DailyMed.${labelsAsOf()}` : '';
  // a product's row whose reports disagree, all reading unexpected: the others
  const others = flag.others?.length ? ` Other reports of it read: ${flag.others.map(flagWords).join(', ')}.` : '';
  return `${says}${others}${dated} ${SUSPECTED}`.replace(/\s+/g, ' ').trim();
}

// a flag in its words, grey where it is no answer, with its tip: Not compared with its reason in
// grey under it; Forms differ as each form's answer; `detail` adds the section or, read on another
// form's label, which label decided
export function flagWord(flag, drug, { detail = false } = {}) {
  if (!flag) return '';
  const words = flag.outcome === 'forms_differ' ? sentence(formsSplit(flag)) : detail && otherForm(flag) ? sentence(formRead(flag)) : said(flag.outcome);
  const word = `<span class="oa-has-tip${grey(flag.outcome) ? ' oa-faint' : ''}" data-flag="${flag.outcome}" ${tip(flagTip(flag, drug))}>${esc(words)}</span>`;
  if (!detail) return `${word}${flagReason(flag)}`;
  if (otherForm(flag)) return `${word}<span class="oa-faint">${esc(andMissing(flag))}</span>`;
  const more = flag.outcome === 'on_label' && SECTION[flag.section] ? SECTION[flag.section].replace(/^the /, '') : '';
  return `${word}${more ? `<span class="oa-faint">, ${esc(more)}</span>` : ''}`;
}
// why a flag was not compared, a grey line of its own under the flag
const flagReason = (flag) => (reason(flag.outcome) ? `<span class="oa-faint oa-flag-reason">${esc(reason(flag.outcome))}</span>` : '');

// a flag's tick box in Label status: its word, with a reason in grey beside it
export const flagChoice = (on, outcome, count, attrs) => choice(on, said(outcome), count, attrs, { note: reason(outcome) });

// Label status in words, in the flags' order; the strip and the filters menu say it this way
export const labelWords = (ticked) => (ticked.length ? labelRules().outcomes.filter((k) => ticked.includes(k)).map(flagWords).join(', ') : 'None');
const sameSet = (a, b) => !!a && a.length === b.length && b.every((k) => a.includes(k));
export const isUnexpectedOnly = (ticked) => sameSet(ticked, labelRules().unexpected_only);

// Label status's pane in the filters menu: Unexpected only, then a tick box per flag with its cases
export function labelPane(sc, under) {
  const { outcomes, unexpected_only: unexpected } = labelRules();
  const ticked = sc.f.label || outcomes;
  const counts = sc.labelCounts || {};
  return `<p class="menu-heading">Label status</p>
    <div class="oa-year-quick"><button type="button" class="oa-smq-scope" data-act="label-unexpected" aria-pressed="${isUnexpectedOnly(sc.f.label)}">Unexpected only</button></div>
    <div class="oa-choices">${outcomes.map((k) => flagChoice(ticked.includes(k), k, counts[k] ?? 0, `data-act="opt-label" data-v="${k}"`)).join('')}</div>
    <p class="menu-footnote">${under}Every flag shows from the start. Unexpected only ticks ${esc(labelWords(unexpected).replace(/, ([^,]*)$/, ' and $1'))}. ${esc(UNEXPECTED_MEANS)} A case counts when at least one of its reactions has a ticked flag for ${esc(productLabel(sc.product))}, against today's label, so a case can count under several. <button type="button" class="oa-link" data-act="about">About the label flags</button></p>`;
}

// where no label was found, a quiet link that opens Improve this with the request written (improve.js)
export const requestLabel = (drug) => (host.improve
  ? ` <button type="button" class="oa-link oa-request-label" data-act="request-label" data-drug="${esc(drug)}" data-part="Label for ${esc(drug)}">Request this label</button>`
  : '');

// the case dialog: under a reaction, one quiet line per suspect drug with its flag for it
export function reactionLines(found, pt) {
  return (found?.drugs || []).filter((d) => d.flags[pt]).map((d) => `<span class="oa-label-line"><span class="oa-label-drug">${esc(d.name)}</span><span>${flagWord(d.flags[pt], d.name, { detail: true })}</span>${otherForm(d.flags[pt]) ? '' : flagReason(d.flags[pt])}</span>`).join('');
}

// the labels a case's flags were read against, each named and linked once, under its reactions;
// a drug with no one label says why
export function labelSources(found) {
  const drugs = found?.drugs || [];
  if (!drugs.length) return '';
  const none = (d) => !d.coded || Object.values(d.flags).some((f) => f.outcome === 'no_label');
  const named = new Map();
  drugs.forEach((d) => named.set(d.label?.setid ?? d.name, d.label ? labelLink(d.label) : `${esc(d.name)}: ${none(d) ? `no label found.${requestLabel(d.name)}` : 'its forms\' labels'}`));
  return `<p class="oa-note oa-label-sources">Against today's US prescription labels: ${[...named.values()].join('; ')}. <button type="button" class="oa-link" data-act="about">About the label flags</button></p>`;
}

// About the label flags: the suspected-events line first, what each flag means, how each was decided
export function openAbout() {
  document.getElementById('oa-about')?.close();
  const flags = labelRules().outcomes.map((k) => `<dt>${esc(said(k))}${reason(k) ? `<span class="oa-faint oa-flag-reason">${esc(reason(k))}</span>` : ''}</dt><dd>${esc(MEANS[k]())}</dd>`).join('');
  const dlg = dialog('About the label flags', `<p><strong>${esc(SUSPECTED)}</strong></p>
    <p>For each suspect drug and reaction, Open Altio says whether the drug's US prescription label names the reaction. It reads <strong>today's label</strong>: the newest one on DailyMed, not the label in force when the case was reported. Each flag names that label by its product, its ingredients and its date, and the label is linked to DailyMed from the list or the case it flags. A label's forms are named only where the drug has different labels for different forms. Where the report's form has no label of its own, or the report does not say the form, the flag is read on the label of the drug's other forms and says which: ${esc(sentence(formSays('on_label', formsLabel(['injected']))))}; no by-mouth label.</p>
    <dl class="field-list oa-fields oa-about-list">${flags}</dl>
    <h3 class="case-section">How each was decided</h3>
    <dl class="field-list oa-fields oa-about-list">
      <dt>By rule</dt><dd>Fixed rules read the label's safety sections and compare them with the reaction's MedDRA term. The same label always gives the same answer.</dd>
      <dt>By model, reviewed by Altio</dt><dd>Where the rules cannot settle it, a model suggests an answer with the label's sentence as its evidence. It shows only once Altio has accepted it. Until then the flag reads ${esc(said('uncertain'))}.</dd>
    </dl>
    <p class="oa-note">A trial product (a study drug, a placebo or a blinded drug) has no flag: its label is not known.</p>`);
  dlg.id = 'oa-about';
  dlg.classList.add('oa-about');
  document.activeElement?.blur(); // quiet focus: nothing lit until the keyboard is used
}

actions({ about: () => openAbout() });
